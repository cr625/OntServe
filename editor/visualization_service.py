"""
Cytoscape.js visualization data builders for the ontology editor.

Converts OntologyEntity records and owlready2 outputs into Cytoscape.js
node/edge JSON. Extracted from editor/routes.py visualization routes.
"""

import logging
import os
import tempfile
from typing import Optional

from sqlalchemy import select

from web.models import db, Ontology, OntologyEntity
from .utils import EntityTypeMapper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _uri_fragment(uri: str) -> str:
    """Extract the local name from a URI."""
    if '#' in uri:
        return uri.split('#')[-1]
    return uri.split('/')[-1]


def _make_external_node(parent_uri: str) -> dict:
    """Build a Cytoscape.js node for an external ontology class (BFO/IAO/RO)."""
    if 'BFO_' in parent_uri:
        display_name = f"BFO:{parent_uri.split('_')[-1]}"
        color = '#E3F2FD'
    elif 'IAO_' in parent_uri:
        display_name = f"IAO:{parent_uri.split('_')[-1]}"
        color = '#E8F5E8'
    elif 'RO_' in parent_uri:
        display_name = f"RO:{parent_uri.split('_')[-1]}"
        color = '#FFF3E0'
    else:
        display_name = _uri_fragment(parent_uri)
        color = '#F5F5F5'

    prefix = display_name.split(':')[0] if ':' in display_name else 'external'
    return {
        'group': 'nodes',
        'data': {
            'id': parent_uri,
            'label': display_name,
            'name': display_name,
            'uri': parent_uri,
            'type': 'external_class',
            'entity_type': 'external_class',
            'description': f'External class from {prefix} ontology',
            'comment': f'External class from {prefix} ontology',
            'is_inferred': False,
            'is_external': True,
            'color': color,
            'restrictions': 0,
            'namespace': parent_uri.split('#')[0] if '#' in parent_uri else '/'.join(parent_uri.split('/')[:-1]),
        },
        'classes': 'class-node external-class',
    }


# ---------------------------------------------------------------------------
# Builder: basic entity visualization (enhanced_get_visualization route)
# ---------------------------------------------------------------------------

_XSD_NS = 'http://www.w3.org/2001/XMLSchema#'
_RDFS_LITERAL = 'http://www.w3.org/2000/01/rdf-schema#Literal'


def _is_deprecated(entity) -> bool:
    props = entity.properties if isinstance(entity.properties, dict) else {}
    return props.get('deprecated') in (True, 'true')


def _uri_list(value) -> list:
    """Normalize a domain/range JSON value (null, string, or list) to URIs."""
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _is_datatype_uri(uri: str) -> bool:
    return uri.startswith(_XSD_NS) or uri == _RDFS_LITERAL


def build_basic_visualization(ontology_name: str) -> dict:
    """Build Cytoscape.js data from database entities.

    Classes (and other non-property entities) become nodes with subClassOf
    edges from parent_uri. Object properties are rendered as labeled
    domain -> range edges rather than isolated nodes; datatype and annotation
    properties (literal-valued or without a class range) are omitted from the
    class graph and reported in the statistics, the same convention as a UML
    class diagram showing associations but not attributes. Deprecated entities
    are excluded. Returns a dict suitable for jsonify().
    """
    ontology, entities = _load_ontology_entities(ontology_name)
    if ontology is None:
        return {'success': False, 'error': f'Ontology {ontology_name} not found'}

    deprecated_excluded = sum(1 for e in entities if _is_deprecated(e))
    entities = [e for e in entities if not _is_deprecated(e)]

    node_entities = [e for e in entities if e.entity_type != 'property']
    property_entities = [e for e in entities if e.entity_type == 'property']

    nodes = []
    edges = []
    entity_uris = {e.uri for e in node_entities}
    external_refs = set()
    edge_id = 0

    for entity in node_entities:
        nodes.append({
            'group': 'nodes',
            'data': {
                'id': entity.uri,
                'label': entity.label or _uri_fragment(entity.uri),
                'name': entity.label or _uri_fragment(entity.uri),
                'uri': entity.uri,
                'type': entity.entity_type,
                'entity_type': entity.entity_type,
                'description': entity.comment or '',
                'comment': entity.comment or '',
                'is_inferred': False,
                'restrictions': 0,
                'namespace': entity.uri.split('#')[0] if '#' in entity.uri else '/'.join(entity.uri.split('/')[:-1]),
            },
            'classes': f'class-node entity-{entity.entity_type}',
        })

        if entity.parent_uri:
            if entity.parent_uri not in entity_uris:
                external_refs.add(entity.parent_uri)
            edges.append({
                'group': 'edges',
                'data': {
                    'id': f'subClassOf_{edge_id}',
                    'source': entity.uri,
                    'target': entity.parent_uri,
                    'type': 'subClassOf',
                    'is_inferred': False,
                },
                'classes': 'explicit subClassOf-edge',
            })
            edge_id += 1

    # Object properties as labeled domain -> range edges.
    object_property_edges = 0
    omitted_properties = 0
    for prop in property_entities:
        domains = _uri_list(prop.domain)
        object_ranges = [r for r in _uri_list(prop.range) if not _is_datatype_uri(r)]
        if not domains or not object_ranges:
            omitted_properties += 1
            continue
        label = prop.label or _uri_fragment(prop.uri)
        for d in domains:
            for r in object_ranges:
                for endpoint in (d, r):
                    if endpoint not in entity_uris:
                        external_refs.add(endpoint)
                edges.append({
                    'group': 'edges',
                    'data': {
                        'id': f'property_{edge_id}',
                        'source': d,
                        'target': r,
                        'label': label,
                        'uri': prop.uri,
                        'type': 'objectProperty',
                        'description': prop.comment or '',
                        'is_inferred': False,
                    },
                    'classes': 'explicit property-edge',
                })
                edge_id += 1
                object_property_edges += 1

    for uri in external_refs:
        nodes.append(_make_external_node(uri))

    counts = _count_by_type(nodes)
    return {
        'success': True,
        'visualization': {'nodes': nodes, 'edges': edges},
        'statistics': {
            'total_entities': len(nodes),
            'entity_type_counts': counts,
            'object_property_edges': object_property_edges,
            'omitted_datatype_properties': omitted_properties,
            'deprecated_excluded': deprecated_excluded,
            'inferred_count': 0,
            'consistency_check': True,
        },
        'message': (f"Retrieved {len(nodes)} entities, {object_property_edges} object-property "
                    f"edges ({omitted_properties} literal-valued properties not shown)"),
    }


# ---------------------------------------------------------------------------
# Builder: owlready2-based hierarchy visualization
# ---------------------------------------------------------------------------

def build_hierarchy_visualization(ontology_name: str) -> dict:
    """Build Cytoscape.js data by loading ontology content through owlready2.

    Returns a dict suitable for jsonify().
    """
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.session.execute(stmt).scalar_one_or_none()
    if not ontology:
        return {'success': False, 'error': f'Ontology {ontology_name} not found'}

    if not ontology.current_content:
        return {'success': False, 'error': 'No content found for ontology'}

    try:
        import owlready2
        import rdflib as _rdflib
    except ImportError:
        return {'success': False, 'error': 'owlready2 not available'}

    try:
        return _build_hierarchy_from_owlready(ontology)
    except Exception as exc:
        logger.error("Hierarchy extraction failed for %s: %s", ontology_name, exc)
        return {'success': False, 'error': f'Hierarchy extraction failed: {exc}'}


def _build_hierarchy_from_owlready(ontology: Ontology) -> dict:
    """Internal: parse content with owlready2, extract class hierarchy."""
    import owlready2
    import rdflib as _rdflib

    content = ontology.current_content
    if not content.strip().startswith('<?xml'):
        g = _rdflib.Graph()
        g.parse(data=content, format='turtle')
        content = g.serialize(format='xml')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.owl', delete=False) as f:
        f.write(content)
        temp_file = f.name

    try:
        world = owlready2.World()
        onto = world.get_ontology(f'file://{temp_file}').load()

        nodes = []
        edges = []
        class_nodes = {}

        for cls in onto.classes():
            class_name = cls.name or str(cls).split('.')[-1]
            node_id = str(cls)
            class_nodes[node_id] = {
                'group': 'nodes',
                'data': {
                    'id': node_id,
                    'label': class_name,
                    'name': class_name,
                    'uri': str(cls),
                    'type': 'class',
                    'entity_type': 'class',
                    'description': f'Class: {class_name}',
                    'namespace': getattr(getattr(cls, 'namespace', None), 'base_iri', '') or '',
                },
                'classes': 'class-node',
            }
            nodes.append(class_nodes[node_id])

        edge_id = 0
        for cls in onto.classes():
            for parent in cls.is_a:
                if hasattr(parent, 'name') and str(parent) in class_nodes:
                    edges.append({
                        'group': 'edges',
                        'data': {
                            'id': f'edge_{edge_id}',
                            'source': str(cls),
                            'target': str(parent),
                            'relationship': 'subClassOf',
                            'type': 'subClassOf',
                            'label': 'subClassOf',
                        },
                        'classes': 'hierarchy-edge',
                    })
                    edge_id += 1

        # Properties are deliberately NOT added as nodes here: with no edges
        # they render as singletons. The basic view carries object properties
        # as domain -> range edges; this view is the pure class hierarchy.
        return {
            'success': True,
            'message': f'Extracted {len(nodes)} nodes and {len(edges)} hierarchical relationships',
            'visualization': {'nodes': nodes, 'edges': edges},
            'statistics': {
                'total_nodes': len(nodes),
                'total_edges': len(edges),
                'classes': len(class_nodes),
                'properties': 0,
                'hierarchical_relationships': len(edges),
            },
        }
    finally:
        os.unlink(temp_file)


# ---------------------------------------------------------------------------
# Shared DB access
# ---------------------------------------------------------------------------

def _load_ontology_entities(
    ontology_name: str,
    limit: Optional[int] = None,
) -> tuple:
    """Load an Ontology and its entities. Returns (ontology, entities) or (None, [])."""
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.session.execute(stmt).scalar_one_or_none()
    if not ontology:
        return None, []

    entity_stmt = select(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id
    )
    if limit:
        entity_stmt = entity_stmt.limit(limit)
    entities = db.session.execute(entity_stmt).scalars().all()
    return ontology, entities


def _count_by_type(nodes: list) -> dict:
    """Count nodes by entity type."""
    counts = {}
    for n in nodes:
        t = n['data'].get('type', 'unknown')
        counts[t] = counts.get(t, 0) + 1
    return counts
