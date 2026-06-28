"""
Entity extraction from ontology content.

Parses RDF content and extracts OWL classes, properties, and individuals
into OntologyEntity records.

Extraction passes:
1. Standard OWL types: owl:Class, owl:ObjectProperty, owl:DatatypeProperty
2. Named individuals: owl:NamedIndividual (with full property collection)
3. Catch-all: any labeled URI resource not captured above (handles domain-typed
   individuals like proethica:Obligation instances, and OBO-style bare resources)
"""

from datetime import datetime, timezone

import rdflib
from rdflib import RDF, RDFS, OWL
from rdflib.namespace import SKOS
from sqlalchemy import select

from web.models import db, OntologyEntity

# OWL/SKOS structural types to skip in the catch-all pass. ConceptScheme is
# captured by its own pass below, so the catch-all must not also grab it.
_OWL_STRUCTURAL_TYPES = frozenset([
    OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty,
    OWL.NamedIndividual, OWL.Ontology, OWL.Restriction, OWL.AllDisjointClasses,
    OWL.AllDifferent, OWL.FunctionalProperty, OWL.InverseFunctionalProperty,
    OWL.SymmetricProperty, OWL.TransitiveProperty, OWL.IrreflexiveProperty,
    OWL.AsymmetricProperty, OWL.ReflexiveProperty,
    SKOS.ConceptScheme,
])


_IAO_DEFINITION = rdflib.URIRef('http://purl.obolibrary.org/obo/IAO_0000115')
PROETHICA_NS = 'http://proethica.org/ontology/'
PROETHICA_INTERMEDIATE_NS = 'http://proethica.org/ontology/intermediate#'
PROETHICA_CORE_NS = 'http://proethica.org/ontology/core#'


def _first(g, subject, predicate):
    """Deterministic single value among the (unordered) RDF objects of a predicate: an @en literal if
    present, else the lexicographically first. next() over multiple values is non-deterministic, which makes
    the content_hash unstable and breaks embedding preservation (which is keyed on (uri, content_hash))."""
    vals = list(g.objects(subject, predicate))
    if not vals:
        return None
    en = [v for v in vals if getattr(v, 'language', None) == 'en']
    return str(sorted(en or vals, key=str)[0])


def _label(g, subject):
    return _first(g, subject, RDFS.label)


def _comment_or_definition(g, subject):
    """rdfs:comment if present, else iao:0000115 (OBO textual definition), else skos:definition; each picked
    deterministically (see _first). OWL classes carry the formal definition on iao:0000115 and SKOS concepts
    on skos:definition, so a class/concept lacking rdfs:comment still gets a description on the page."""
    return (_first(g, subject, RDFS.comment)
            or _first(g, subject, _IAO_DEFINITION)
            or _first(g, subject, SKOS.definition))


def _pick_best_parent(g, class_uri):
    """Best rdfs:subClassOf parent: proethica intermediate > core > other proethica > any named (BFO/IAO/OBO)
    superclass. Proethica-first keeps the category-walk CTEs terminating at the proethica boundary; the named
    fallback lets a core class (whose only named parent is BFO) root in the BFO tree for the Class Hierarchy.
    Blank-node restrictions are excluded. Returns a URI string or None."""
    all_parents = [str(p) for p in g.objects(class_uri, RDFS.subClassOf)]
    if not all_parents:
        return None
    intermediate = [p for p in all_parents if p.startswith(PROETHICA_INTERMEDIATE_NS)]
    core = [p for p in all_parents if p.startswith(PROETHICA_CORE_NS)]
    other = [p for p in all_parents if p.startswith(PROETHICA_NS) and p not in intermediate and p not in core]
    if intermediate:
        return intermediate[0]
    if core:
        return core[0]
    if other:
        return other[0]
    named = [p for p in all_parents if p.startswith('http')]
    return named[0] if named else None


def extract_entities_from_content(ontology, content, format_hint='turtle'):
    """
    Extract entities from ontology content and store them in the database.

    Clears existing entities for the ontology before extracting new ones.

    Args:
        ontology: Ontology model instance
        content: RDF content string
        format_hint: RDF format ('turtle', 'xml', 'json-ld', etc.)

    Returns:
        dict: Entity counts by type {'class': N, 'property': N, 'individual': N}
    """
    # Auto-detect format if needed
    if not format_hint or format_hint == 'turtle':
        if '<?xml' in content or '<rdf:RDF' in content or 'xmlns:rdf' in content:
            format_hint = 'xml'
        elif '@prefix' in content or '@base' in content:
            format_hint = 'turtle'
        else:
            format_hint = 'turtle'  # Default fallback

    # Parse content with detected format
    g = rdflib.Graph()
    try:
        g.parse(data=content, format=format_hint)
    except Exception as parse_error:
        # Try alternative formats if parsing fails
        if format_hint == 'turtle':
            try:
                g.parse(data=content, format='xml')
                format_hint = 'xml'
            except Exception:
                raise parse_error
        elif format_hint == 'xml':
            try:
                g.parse(data=content, format='turtle')
                format_hint = 'turtle'
            except Exception:
                raise parse_error
        else:
            raise parse_error

    # Clear existing entities for this ontology, capturing their embeddings first so an entity whose
    # (uri, content_hash) is unchanged keeps its vector across the re-extract (no embedding blanking on
    # reload -- the prior bug where only tools/refresh preserved embeddings and the web/sync paths did not).
    stmt = select(OntologyEntity).where(OntologyEntity.ontology_id == ontology.id)
    entities_to_clear = db.session.execute(stmt).scalars().all()
    prev_emb = {e.uri: (e.content_hash, e.embedding) for e in entities_to_clear}
    for entity in entities_to_clear:
        db.session.delete(entity)

    entity_counts = {'class': 0, 'property': 0, 'individual': 0}
    captured_uris = set()
    new_entities = []

    now = datetime.now(timezone.utc)

    # Predicates to skip when collecting class properties. skos:definition is
    # surfaced as the entity comment, so it is not also repeated as a property.
    class_skip_predicates = {RDF.type, RDFS.label, RDFS.comment, RDFS.subClassOf, SKOS.definition}

    # --- Pass 1: Standard OWL classes ---
    for cls in g.subjects(RDF.type, OWL.Class):
        if isinstance(cls, rdflib.BNode) or not str(cls).startswith('http'):
            continue  # anonymous class expression (owl:intersectionOf / owl:Restriction), not a named class;
                      # its BNode id is random per parse, which would make the URI + content_hash unstable
        label = _label(g, cls)
        label_str = str(label) if label else None
        comment_str = _comment_or_definition(g, cls)

        # Collect additional properties (e.g., discoveredInCase, importance)
        properties = _collect_properties(g, cls, class_skip_predicates)

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='class',
            uri=str(cls),
            label=label_str,
            comment=comment_str,
            parent_uri=_pick_best_parent(g, cls),
            properties=properties if properties else None,
            content_hash=OntologyEntity.compute_content_hash(str(cls), label_str, comment_str),
            updated_at=now
        )
        new_entities.append(entity)
        captured_uris.add(str(cls))
        entity_counts['class'] += 1

    # --- Pass 2: OWL object properties ---
    for prop in g.subjects(RDF.type, OWL.ObjectProperty):
        label = _label(g, prop)
        comment = next(g.objects(prop, RDFS.comment), None)
        domain = next(g.objects(prop, RDFS.domain), None)
        range_val = next(g.objects(prop, RDFS.range), None)
        label_str = str(label) if label else None
        comment_str = str(comment) if comment else None

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='property',
            uri=str(prop),
            label=label_str,
            comment=comment_str,
            domain=str(domain) if domain else None,
            range=str(range_val) if range_val else None,
            content_hash=OntologyEntity.compute_content_hash(str(prop), label_str, comment_str),
            updated_at=now
        )
        new_entities.append(entity)
        captured_uris.add(str(prop))
        entity_counts['property'] += 1

    # --- Pass 3: OWL datatype properties ---
    for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
        label = _label(g, prop)
        comment = next(g.objects(prop, RDFS.comment), None)
        domain = next(g.objects(prop, RDFS.domain), None)
        range_val = next(g.objects(prop, RDFS.range), None)
        label_str = str(label) if label else None
        comment_str = str(comment) if comment else None

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='property',
            uri=str(prop),
            label=label_str,
            comment=comment_str,
            domain=str(domain) if domain else None,
            range=str(range_val) if range_val else None,
            content_hash=OntologyEntity.compute_content_hash(str(prop), label_str, comment_str),
            updated_at=now
        )
        new_entities.append(entity)
        captured_uris.add(str(prop))
        entity_counts['property'] += 1

    # --- Pass 3b: OWL annotation properties ---
    # The definitional-field annotations (distinguishingFeatures, professionalScope, typicalQualifications,
    # associatedVirtues) and the D-tuple metadata (dtupleComponent, componentOf) are owl:AnnotationProperty.
    # Capture them as 'property' entities like object/datatype properties so a SHACL sh:path that targets one
    # resolves to a page (otherwise the Definitional Attributes column renders it as plain <code>, not a link).
    # MUST stay in sync with tools/refresh_entity_extraction.py, which has the same pass; the startup sync uses
    # THIS extractor, so omitting it here silently reverts the tool's capture on every web restart.
    for prop in g.subjects(RDF.type, OWL.AnnotationProperty):
        uri_str = str(prop)
        if not uri_str.startswith('http') or uri_str in captured_uris:
            continue
        label = _label(g, prop)
        comment = next(g.objects(prop, RDFS.comment), None)
        domain = next(g.objects(prop, RDFS.domain), None)
        range_val = next(g.objects(prop, RDFS.range), None)
        label_str = str(label) if label else None
        comment_str = str(comment) if comment else None
        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='property',
            uri=uri_str,
            label=label_str,
            comment=comment_str,
            domain=str(domain) if domain else None,
            range=str(range_val) if range_val else None,
            content_hash=OntologyEntity.compute_content_hash(uri_str, label_str, comment_str),
            updated_at=now
        )
        new_entities.append(entity)
        captured_uris.add(uri_str)
        entity_counts['property'] += 1

    # --- Pass 4: Named individuals (with full property collection) ---
    skip_predicates = {RDF.type, RDFS.label, RDFS.comment, SKOS.definition}
    for indiv in g.subjects(RDF.type, OWL.NamedIndividual):
        uri_str = str(indiv)
        if uri_str in captured_uris:
            continue

        label = _label(g, indiv)
        label_str = str(label) if label else None
        comment_str = _comment_or_definition(g, indiv)

        # Get rdf:type URIs excluding owl:NamedIndividual for parent_uri
        types = [str(t) for t in g.objects(indiv, RDF.type)
                 if t != OWL.NamedIndividual]
        # A skos:Concept that is serialized as a NamedIndividual (e.g. a borrowed
        # crosswalk term) is a vocabulary concept, not a case individual. Type it
        # 'concept' so the UI does not label it "Individual", which here means a
        # unique case entity. Prefer a real class over skos:Concept for "instance of".
        is_concept = (indiv, RDF.type, SKOS.Concept) in g
        entity_type = 'concept' if is_concept else 'individual'
        non_skos_types = [t for t in types if t != str(SKOS.Concept)]
        parent_uri = (non_skos_types or types or [None])[0]

        # Collect all non-standard properties into JSON
        properties = _collect_properties(g, indiv, skip_predicates)
        if len(types) > 1:
            properties['rdf_types'] = types

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type=entity_type,
            uri=uri_str,
            label=label_str,
            comment=comment_str,
            parent_uri=parent_uri,
            properties=properties if properties else None,
            content_hash=OntologyEntity.compute_content_hash(uri_str, label_str, comment_str),
            updated_at=now
        )
        new_entities.append(entity)
        captured_uris.add(uri_str)
        entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1

    # --- Pass 5: SKOS concept schemes (resolvable vocabulary nodes) ---
    # A skos:ConceptScheme groups borrowed crosswalk terms (e.g. the IFC actor
    # roles). Terms carry skos:inScheme pointing here, so the scheme must resolve
    # to its own page rather than 404. entity_type 'scheme' keeps it out of the
    # class/property/individual lists while staying directly resolvable.
    scheme_skip_predicates = {RDF.type, RDFS.label, RDFS.comment, SKOS.definition}
    for scheme in g.subjects(RDF.type, SKOS.ConceptScheme):
        uri_str = str(scheme)
        if uri_str in captured_uris:
            continue

        label = _label(g, scheme)
        label_str = str(label) if label else None
        comment_str = _comment_or_definition(g, scheme)
        properties = _collect_properties(g, scheme, scheme_skip_predicates)

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='scheme',
            uri=uri_str,
            label=label_str,
            comment=comment_str,
            properties=properties if properties else None,
            content_hash=OntologyEntity.compute_content_hash(uri_str, label_str, comment_str),
            updated_at=now
        )
        new_entities.append(entity)
        captured_uris.add(uri_str)
        entity_counts['scheme'] = entity_counts.get('scheme', 0) + 1

    # --- Pass 6: Catch-all for labeled resources not captured above ---
    # Handles domain-typed individuals (e.g., rdf:type proethica:Obligation),
    # OBO-style bare resources, and other non-standard patterns.
    for subj in set(g.subjects(RDFS.label, None)):
        uri_str = str(subj)
        if uri_str in captured_uris:
            continue
        if isinstance(subj, rdflib.BNode):
            continue

        # Skip resources whose only type is an OWL structural type
        types = list(g.objects(subj, RDF.type))
        if types and all(t in _OWL_STRUCTURAL_TYPES for t in types):
            continue

        label = _label(g, subj)
        label_str = str(label) if label else None
        comment_str = _comment_or_definition(g, subj)

        # Determine entity_type and parent_uri from rdf:type
        domain_types = [str(t) for t in types if t not in _OWL_STRUCTURAL_TYPES]
        parent_uri = domain_types[0] if domain_types else None

        # Domain-typed -> individual; untyped -> individual (bare resource with label)
        entity_type = 'individual'

        properties = _collect_properties(g, subj, skip_predicates)
        if len(domain_types) > 1:
            properties['rdf_types'] = domain_types

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type=entity_type,
            uri=uri_str,
            label=label_str,
            comment=comment_str,
            parent_uri=parent_uri,
            properties=properties if properties else None,
            content_hash=OntologyEntity.compute_content_hash(uri_str, label_str, comment_str),
            updated_at=now
        )
        new_entities.append(entity)
        captured_uris.add(uri_str)
        entity_counts['individual'] += 1

    # Restore embeddings for entities whose (uri, content_hash) is unchanged, then persist all.
    for e in new_entities:
        prev = prev_emb.get(e.uri)
        if prev is not None and prev[0] == e.content_hash and prev[1] is not None:
            e.embedding = prev[1]
        db.session.add(e)

    return entity_counts


def _collect_properties(g, subject, skip_predicates):
    """Collect all non-standard properties on a subject into a JSON-friendly dict."""
    properties = {}
    for pred, obj in g.predicate_objects(subject):
        if pred in skip_predicates:
            continue
        pred_str = str(pred)
        key = pred_str.rsplit('#', 1)[-1] if '#' in pred_str else pred_str.rsplit('/', 1)[-1]
        val = str(obj)
        if key in properties:
            existing = properties[key]
            if isinstance(existing, list):
                existing.append(val)
            else:
                properties[key] = [existing, val]
        else:
            properties[key] = val
    return properties
