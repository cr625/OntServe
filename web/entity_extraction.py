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
# schema.org soft domain: a non-logical "applies to" hint (Pellet ignores it, unlike rdfs:domain). Lets a
# property surface on a class's entity page without imposing an OWL domain constraint the corpus might violate
# (the relatedTo family's subject is sometimes the bearer Agent, not the Role facet, and Agent is disjoint
# with Role -- so rdfs:domain Role would make those cases inconsistent).
_SCHEMA_DOMAIN_INCLUDES = rdflib.URIRef('http://schema.org/domainIncludes')
_SCHEMA_RANGE_INCLUDES = rdflib.URIRef('http://schema.org/rangeIncludes')

# OWL property characteristics, captured into the properties JSON so the ontology
# detail view can badge them (Symmetric on professionalPeerOf, Asymmetric +
# Irreflexive on prevailsOver, ...). Kept as display names, not URIs.
_OWL_PROPERTY_CHARACTERISTICS = (
    (OWL.FunctionalProperty, 'Functional'),
    (OWL.InverseFunctionalProperty, 'InverseFunctional'),
    (OWL.SymmetricProperty, 'Symmetric'),
    (OWL.AsymmetricProperty, 'Asymmetric'),
    (OWL.TransitiveProperty, 'Transitive'),
    (OWL.ReflexiveProperty, 'Reflexive'),
    (OWL.IrreflexiveProperty, 'Irreflexive'),
)


def _most_specific_type(g, type_uris):
    """Deterministic most-specific rdf:type for an individual's parent_uri.

    The previous rule took the first type in rdflib iteration order, which is
    nondeterministic and often surfaced the generic layer ('instance of Role')
    on multi-typed case individuals. Drops any candidate that is a transitive
    superclass (within this graph) of another candidate, then prefers:
    non-core over the generic proeth-core layer, occupational over the
    relational archetypes (edge-derived secondary classifications, see
    _RELATIONAL_ARCHETYPE_URIS), alphabetical as the stable final tiebreak.
    Mirrors the deepest-chain selection the entity-page hierarchy applies
    (web/ontology_routes/helpers.py), graph-locally."""
    candidates = [u for u in type_uris if u]
    if not candidates:
        return None
    refs = {u: rdflib.URIRef(u) for u in candidates}
    supers = set()
    for u in candidates:
        for ancestor in g.transitive_objects(refs[u], RDFS.subClassOf):
            ancestor_str = str(ancestor)
            if ancestor_str != u and ancestor_str in refs:
                supers.add(ancestor_str)
    remaining = [u for u in candidates if u not in supers] or candidates
    remaining.sort(key=lambda u: (
        u.startswith(PROETHICA_CORE_NS),
        u in _RELATIONAL_ARCHETYPE_URIS,
        u))
    return remaining[0]


def _property_metadata(g, prop, kind, soft_typing=False):
    """The properties-JSON dict for a property row.

    kind ('object' | 'datatype' | 'annotation') lets the detail view group the
    flat entity_type='property' rows; characteristics carries the OWL property
    characteristics; soft_typing marks a domain/range that came from the
    schema:domainIncludes/rangeIncludes hints rather than rdfs:domain/range
    (a non-logical "applies to" the view must not present as a hard OWL
    constraint); deprecated keeps its existing shape (the ProEthica commit
    matcher filters on properties->>'deprecated')."""
    meta = {'kind': kind}
    characteristics = [name for t, name in _OWL_PROPERTY_CHARACTERISTICS
                       if (prop, RDF.type, t) in g]
    if characteristics:
        meta['characteristics'] = characteristics
    if soft_typing:
        meta['soft_typing'] = True
    if (prop, OWL.deprecated, rdflib.Literal(True)) in g:
        meta['deprecated'] = True
    return meta
PROETHICA_NS = 'http://proethica.org/ontology/'
PROETHICA_INTERMEDIATE_NS = 'http://proethica.org/ontology/intermediate#'
PROETHICA_CORE_NS = 'http://proethica.org/ontology/core#'

# The four Kong (2020) relational archetype classes. R1 (extraction
# architecture spec): relational typing is EDGE-PRIMARY -- these defined
# classes (Role and employedBy some Role, ...) are materialized from the actor
# edges a role facet bears, as a SECONDARY classification beside the
# occupational type. The card's "instance of" should therefore headline the
# occupational class; the archetypes stay visible as the edges themselves and
# in the full type list. Closed, spec-ratified set. Referenced by
# _most_specific_type (defined above; resolved at call time).
_RELATIONAL_ARCHETYPE_URIS = frozenset(
    f'{PROETHICA_INTERMEDIATE_NS}{name}' for name in (
        'ProviderClientRole', 'ProfessionalPeerRole',
        'EmployerRelationshipRole', 'PublicResponsibilityRole',
    ))


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


def _fragment_label(uri):
    """Display fallback when a resource carries no rdfs:label: the URI fragment
    with underscores split and CamelCase spaced (DesignEngineerRole ->
    'Design Engineer Role'). Lean per-case class redeclarations carry no labels
    by design; without this they render as raw camel-case fragments next to the
    spaced labels of individuals."""
    import re as _re
    frag = str(uri).rsplit('#', 1)[-1].rsplit('/', 1)[-1]
    frag = frag.replace('_', ' ')
    frag = _re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', frag)
    frag = _re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', frag)
    return frag.strip()


def _comment_or_definition(g, subject, prefer_iao_definition=False):
    """rdfs:comment if present, else iao:0000115 (OBO textual definition), else skos:definition; each picked
    deterministically (see _first). OWL classes carry the formal definition on iao:0000115 and SKOS concepts
    on skos:definition, so a class/concept lacking rdfs:comment still gets a description on the page.

    prefer_iao_definition=True flips the precedence to iao:0000115 first: the class pass uses it so that the
    stored comment (the MCP 'definition'/'description' serving field) carries the formal iao:0000115 definition
    when one exists, matching uri_resolution.py and the entity page Definition card, which already prefer 115.
    Properties/individuals/schemes keep rdfs:comment-first (their documentation is on rdfs:comment)."""
    if prefer_iao_definition:
        order = (_IAO_DEFINITION, RDFS.comment, SKOS.definition)
    else:
        order = (RDFS.comment, _IAO_DEFINITION, SKOS.definition)
    for predicate in order:
        value = _first(g, subject, predicate)
        if value is not None:
            return value
    return None


_PROPERTY_SIGNAL_PREDICATES = (
    OWL.inverseOf, RDFS.domain, RDFS.range, RDFS.subPropertyOf,
    OWL.equivalentProperty, OWL.propertyChainAxiom, OWL.propertyDisjointWith,
)


def _is_untyped_property(g, subj):
    """True if an otherwise-untyped labeled resource carries a property-only predicate, so the
    catch-all should classify it 'property' rather than fall through to 'individual'. Every
    predicate checked is property-specific in OWL -- owl:inverseOf, rdfs:domain, rdfs:range,
    rdfs:subPropertyOf, owl:equivalentProperty, owl:propertyChainAxiom, owl:propertyDisjointWith --
    so a resource bearing any of them (as subject, or as the object of owl:inverseOf) is a property
    and no individual is a false positive. Covers the PROV-O inverse relations (hadDerivation,
    wasUsedBy, ...), which W3C declares via owl:inverseOf with no rdf:type, and which otherwise
    land in the individual bucket."""
    for pred in _PROPERTY_SIGNAL_PREDICATES:
        if next(g.objects(subj, pred), None) is not None:
            return True
    if next(g.subjects(OWL.inverseOf, subj), None) is not None:
        return True
    return False


def _class_expr_uris(g, node):
    """Resolve an rdfs:domain / rdfs:range object to NAMED class URIs. A URIRef -> [uri]; an anonymous
    owl:unionOf class (e.g. a domain of (Action or Event)) -> its named members; any other anonymous
    expression (a restriction or intersection) -> [] (no nameable class). Keeps a blank-node id from being
    stored as if it were a class URI, which otherwise rendered as 'n0de...' in the entity view's From column."""
    if node is None:
        return []
    if isinstance(node, rdflib.URIRef):
        return [str(node)]
    from rdflib.collection import Collection
    union = next(g.objects(node, OWL.unionOf), None)
    if union is not None:
        return [str(m) for m in Collection(g, union) if isinstance(m, rdflib.URIRef)]
    return []


def _domain_range_value(uris):
    """A single class URI stays a string (the common case, unchanged); a union stays a list; nothing -> None."""
    if not uris:
        return None
    return uris[0] if len(uris) == 1 else uris


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
        label_str = str(label) if label else _fragment_label(cls)
        comment_str = _comment_or_definition(g, cls, prefer_iao_definition=True)

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
        hard_domain = next(g.objects(prop, RDFS.domain), None)
        hard_range = next(g.objects(prop, RDFS.range), None)
        domain = hard_domain or next(g.objects(prop, _SCHEMA_DOMAIN_INCLUDES), None)
        range_val = hard_range or next(g.objects(prop, _SCHEMA_RANGE_INCLUDES), None)
        soft = (hard_domain is None and domain is not None) \
            or (hard_range is None and range_val is not None)
        label_str = str(label) if label else None
        # rdfs:comment, else the OBO/SKOS textual definition -- mirrors the class branch (_comment_or_definition)
        # so a property documented only with skos:definition (e.g. the relatedTo relationship vocab) still shows
        # a description on the entity page instead of a blank Description cell.
        comment_str = _comment_or_definition(g, prop)

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='property',
            properties=_property_metadata(g, prop, 'object', soft_typing=soft),
            uri=str(prop),
            label=label_str,
            comment=comment_str,
            domain=_domain_range_value(_class_expr_uris(g, domain)),
            range=_domain_range_value(_class_expr_uris(g, range_val)),
            content_hash=OntologyEntity.compute_content_hash(str(prop), label_str, comment_str),
            updated_at=now
        )
        new_entities.append(entity)
        captured_uris.add(str(prop))
        entity_counts['property'] += 1

    # --- Pass 3: OWL datatype properties ---
    for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
        label = _label(g, prop)
        hard_domain = next(g.objects(prop, RDFS.domain), None)
        hard_range = next(g.objects(prop, RDFS.range), None)
        domain = hard_domain or next(g.objects(prop, _SCHEMA_DOMAIN_INCLUDES), None)
        range_val = hard_range or next(g.objects(prop, _SCHEMA_RANGE_INCLUDES), None)
        soft = (hard_domain is None and domain is not None) \
            or (hard_range is None and range_val is not None)
        label_str = str(label) if label else None
        # rdfs:comment, else the OBO/SKOS textual definition -- mirrors the class branch (_comment_or_definition)
        # so a property documented only with skos:definition (e.g. the relatedTo relationship vocab) still shows
        # a description on the entity page instead of a blank Description cell.
        comment_str = _comment_or_definition(g, prop)

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='property',
            properties=_property_metadata(g, prop, 'datatype', soft_typing=soft),
            uri=str(prop),
            label=label_str,
            comment=comment_str,
            domain=_domain_range_value(_class_expr_uris(g, domain)),
            range=_domain_range_value(_class_expr_uris(g, range_val)),
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
        hard_domain = next(g.objects(prop, RDFS.domain), None)
        hard_range = next(g.objects(prop, RDFS.range), None)
        domain = hard_domain or next(g.objects(prop, _SCHEMA_DOMAIN_INCLUDES), None)
        range_val = hard_range or next(g.objects(prop, _SCHEMA_RANGE_INCLUDES), None)
        soft = (hard_domain is None and domain is not None) \
            or (hard_range is None and range_val is not None)
        label_str = str(label) if label else None
        # rdfs:comment, else the OBO/SKOS textual definition -- mirrors the class branch (_comment_or_definition)
        # so a property documented only with skos:definition (e.g. the relatedTo relationship vocab) still shows
        # a description on the entity page instead of a blank Description cell.
        comment_str = _comment_or_definition(g, prop)
        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='property',
            properties=_property_metadata(g, prop, 'annotation', soft_typing=soft),
            uri=uri_str,
            label=label_str,
            comment=comment_str,
            domain=_domain_range_value(_class_expr_uris(g, domain)),
            range=_domain_range_value(_class_expr_uris(g, range_val)),
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
        parent_uri = _most_specific_type(g, non_skos_types or types)

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
        parent_uri = _most_specific_type(g, domain_types)

        # An untyped labeled resource that carries a property-only predicate (owl:inverseOf,
        # rdfs:domain/range, rdfs:subPropertyOf, ...) is a property, not the individual fallback --
        # e.g. the PROV-O-inverses relations, which W3C declares with owl:inverseOf and no rdf:type.
        # The guard requires NO rdf:type at all, so a domain-typed case individual is never touched.
        if not domain_types and _is_untyped_property(g, subj):
            entity_type = 'property'
            parent_uri = None
            domain_col = _domain_range_value(_class_expr_uris(g, next(g.objects(subj, RDFS.domain), None)))
            range_col = _domain_range_value(_class_expr_uris(g, next(g.objects(subj, RDFS.range), None)))
        else:
            # Domain-typed -> individual; untyped bare resource with label -> individual
            entity_type = 'individual'
            domain_col = None
            range_col = None

        properties = _collect_properties(g, subj, skip_predicates)
        if entity_type == 'property':
            # Inverse-declared relations with no rdf:type (e.g. the PROV-O
            # inverses) are object properties; give them the same kind marker
            # the typed passes write so the detail view groups them.
            properties.update(_property_metadata(g, subj, 'object'))
        if len(domain_types) > 1:
            properties['rdf_types'] = domain_types

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type=entity_type,
            uri=uri_str,
            label=label_str,
            comment=comment_str,
            parent_uri=parent_uri,
            domain=domain_col,
            range=range_col,
            properties=properties if properties else None,
            content_hash=OntologyEntity.compute_content_hash(uri_str, label_str, comment_str),
            updated_at=now
        )
        new_entities.append(entity)
        captured_uris.add(uri_str)
        entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1

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
