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
from sqlalchemy import select

from web.models import db, OntologyEntity

# OWL structural types to skip in the catch-all pass
_OWL_STRUCTURAL_TYPES = frozenset([
    OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty,
    OWL.NamedIndividual, OWL.Ontology, OWL.Restriction, OWL.AllDisjointClasses,
    OWL.AllDifferent, OWL.FunctionalProperty, OWL.InverseFunctionalProperty,
    OWL.SymmetricProperty, OWL.TransitiveProperty, OWL.IrreflexiveProperty,
    OWL.AsymmetricProperty, OWL.ReflexiveProperty,
])


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

    # Clear existing entities for this ontology
    stmt = select(OntologyEntity).where(OntologyEntity.ontology_id == ontology.id)
    entities_to_clear = db.session.execute(stmt).scalars().all()
    for entity in entities_to_clear:
        db.session.delete(entity)

    entity_counts = {'class': 0, 'property': 0, 'individual': 0}
    captured_uris = set()

    now = datetime.now(timezone.utc)

    # Predicates to skip when collecting class properties
    class_skip_predicates = {RDF.type, RDFS.label, RDFS.comment, RDFS.subClassOf}

    # --- Pass 1: Standard OWL classes ---
    for cls in g.subjects(RDF.type, OWL.Class):
        label = next(g.objects(cls, RDFS.label), None)
        comment = next(g.objects(cls, RDFS.comment), None)
        subclass_of = list(g.objects(cls, RDFS.subClassOf))
        label_str = str(label) if label else None
        comment_str = str(comment) if comment else None

        # Collect additional properties (e.g., discoveredInCase, importance)
        properties = _collect_properties(g, cls, class_skip_predicates)

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='class',
            uri=str(cls),
            label=label_str,
            comment=comment_str,
            parent_uri=str(subclass_of[0]) if subclass_of else None,
            properties=properties if properties else None,
            content_hash=OntologyEntity.compute_content_hash(str(cls), label_str, comment_str),
            updated_at=now
        )
        db.session.add(entity)
        captured_uris.add(str(cls))
        entity_counts['class'] += 1

    # --- Pass 2: OWL object properties ---
    for prop in g.subjects(RDF.type, OWL.ObjectProperty):
        label = next(g.objects(prop, RDFS.label), None)
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
        db.session.add(entity)
        captured_uris.add(str(prop))
        entity_counts['property'] += 1

    # --- Pass 3: OWL datatype properties ---
    for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
        label = next(g.objects(prop, RDFS.label), None)
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
        db.session.add(entity)
        captured_uris.add(str(prop))
        entity_counts['property'] += 1

    # --- Pass 4: Named individuals (with full property collection) ---
    skip_predicates = {RDF.type, RDFS.label, RDFS.comment}
    for indiv in g.subjects(RDF.type, OWL.NamedIndividual):
        uri_str = str(indiv)
        if uri_str in captured_uris:
            continue

        label = next(g.objects(indiv, RDFS.label), None)
        comment = next(g.objects(indiv, RDFS.comment), None)
        label_str = str(label) if label else None
        comment_str = str(comment) if comment else None

        # Get rdf:type URIs excluding owl:NamedIndividual for parent_uri
        types = [str(t) for t in g.objects(indiv, RDF.type)
                 if t != OWL.NamedIndividual]
        parent_uri = types[0] if types else None

        # Collect all non-standard properties into JSON
        properties = _collect_properties(g, indiv, skip_predicates)
        if len(types) > 1:
            properties['rdf_types'] = types

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='individual',
            uri=uri_str,
            label=label_str,
            comment=comment_str,
            parent_uri=parent_uri,
            properties=properties if properties else None,
            content_hash=OntologyEntity.compute_content_hash(uri_str, label_str, comment_str),
            updated_at=now
        )
        db.session.add(entity)
        captured_uris.add(uri_str)
        entity_counts['individual'] += 1

    # --- Pass 5: Catch-all for labeled resources not captured above ---
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

        label = next(g.objects(subj, RDFS.label), None)
        comment = next(g.objects(subj, RDFS.comment), None)
        label_str = str(label) if label else None
        comment_str = str(comment) if comment else None

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
        db.session.add(entity)
        captured_uris.add(uri_str)
        entity_counts['individual'] += 1

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
