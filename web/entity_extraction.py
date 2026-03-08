"""
Entity extraction from ontology content.

Parses RDF content and extracts OWL classes, properties, and individuals
into OntologyEntity records.
"""

import rdflib
from rdflib import RDF, RDFS, OWL
from sqlalchemy import select

from web.models import db, OntologyEntity


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

    # Extract classes
    for cls in g.subjects(RDF.type, OWL.Class):
        label = next(g.objects(cls, RDFS.label), None)
        comment = next(g.objects(cls, RDFS.comment), None)
        subclass_of = list(g.objects(cls, RDFS.subClassOf))

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='class',
            uri=str(cls),
            label=str(label) if label else None,
            comment=str(comment) if comment else None,
            parent_uri=str(subclass_of[0]) if subclass_of else None
        )
        db.session.add(entity)
        entity_counts['class'] += 1

    # Extract object properties
    for prop in g.subjects(RDF.type, OWL.ObjectProperty):
        label = next(g.objects(prop, RDFS.label), None)
        comment = next(g.objects(prop, RDFS.comment), None)
        domain = next(g.objects(prop, RDFS.domain), None)
        range_val = next(g.objects(prop, RDFS.range), None)

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='property',
            uri=str(prop),
            label=str(label) if label else None,
            comment=str(comment) if comment else None,
            domain=str(domain) if domain else None,
            range=str(range_val) if range_val else None
        )
        db.session.add(entity)
        entity_counts['property'] += 1

    # Extract datatype properties
    for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
        label = next(g.objects(prop, RDFS.label), None)
        comment = next(g.objects(prop, RDFS.comment), None)
        domain = next(g.objects(prop, RDFS.domain), None)
        range_val = next(g.objects(prop, RDFS.range), None)

        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='property',
            uri=str(prop),
            label=str(label) if label else None,
            comment=str(comment) if comment else None,
            domain=str(domain) if domain else None,
            range=str(range_val) if range_val else None
        )
        db.session.add(entity)
        entity_counts['property'] += 1

    return entity_counts
