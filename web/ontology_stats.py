"""
Helper functions for computing ontology statistics.

Provides generic stats computation from TTL content when OntologyEntity
records aren't populated, and display_config based customization.
"""

from rdflib import Graph, RDF, RDFS, OWL, Namespace
from collections import defaultdict
import re


def compute_stats_from_ttl(ttl_content: str) -> dict:
    """Compute ontology statistics directly from TTL content.

    Used as fallback when OntologyEntity records aren't populated.

    Args:
        ttl_content: Raw TTL string

    Returns:
        Dict with entity counts and relationship info
    """
    if not ttl_content:
        return {
            'classes': [],
            'object_properties': [],
            'datatype_properties': [],
            'individuals': [],
            'relationships': {
                'hierarchical': 0,
                'domain': 0,
                'range': 0,
                'total': 0
            },
            'from_ttl': True
        }

    g = Graph()
    try:
        g.parse(data=ttl_content, format='turtle')
    except Exception as e:
        return {
            'error': str(e),
            'classes': [],
            'object_properties': [],
            'datatype_properties': [],
            'individuals': [],
            'relationships': {'hierarchical': 0, 'domain': 0, 'range': 0, 'total': 0},
            'from_ttl': True
        }

    # Count classes
    classes = []
    for s in g.subjects(RDF.type, OWL.Class):
        label = g.value(s, RDFS.label)
        comment = g.value(s, RDFS.comment)
        classes.append({
            'uri': str(s),
            'label': str(label) if label else extract_local_name(str(s)),
            'comment': str(comment) if comment else None
        })

    # Also check for rdfs:Class
    for s in g.subjects(RDF.type, RDFS.Class):
        if s not in [c['uri'] for c in classes]:
            label = g.value(s, RDFS.label)
            comment = g.value(s, RDFS.comment)
            classes.append({
                'uri': str(s),
                'label': str(label) if label else extract_local_name(str(s)),
                'comment': str(comment) if comment else None
            })

    # Count object properties
    object_properties = []
    for s in g.subjects(RDF.type, OWL.ObjectProperty):
        label = g.value(s, RDFS.label)
        comment = g.value(s, RDFS.comment)
        domain = g.value(s, RDFS.domain)
        range_val = g.value(s, RDFS.range)
        object_properties.append({
            'uri': str(s),
            'label': str(label) if label else extract_local_name(str(s)),
            'comment': str(comment) if comment else None,
            'domain': str(domain) if domain else None,
            'range': str(range_val) if range_val else None
        })

    # Count datatype properties
    datatype_properties = []
    for s in g.subjects(RDF.type, OWL.DatatypeProperty):
        label = g.value(s, RDFS.label)
        comment = g.value(s, RDFS.comment)
        datatype_properties.append({
            'uri': str(s),
            'label': str(label) if label else extract_local_name(str(s)),
            'comment': str(comment) if comment else None
        })

    # Count named individuals
    individuals = []
    for s in g.subjects(RDF.type, OWL.NamedIndividual):
        label = g.value(s, RDFS.label)
        comment = g.value(s, RDFS.comment)
        individuals.append({
            'uri': str(s),
            'label': str(label) if label else extract_local_name(str(s)),
            'comment': str(comment) if comment else None
        })

    # Count relationships
    hierarchical = len(list(g.triples((None, RDFS.subClassOf, None))))
    domain_count = len(list(g.triples((None, RDFS.domain, None))))
    range_count = len(list(g.triples((None, RDFS.range, None))))

    return {
        'classes': classes,
        'object_properties': object_properties,
        'datatype_properties': datatype_properties,
        'individuals': individuals,
        'relationships': {
            'hierarchical': hierarchical,
            'domain': domain_count,
            'range': range_count,
            'total': hierarchical + domain_count + range_count
        },
        'from_ttl': True
    }


def compute_category_counts(ttl_content: str, categories: list) -> dict:
    """Compute entity counts by category using rdfs:subClassOf relationships.

    For ProEthica ontologies, entities are organized via rdfs:subClassOf
    relationships to core concept types (Role, Principle, Obligation, etc.)

    Args:
        ttl_content: Raw TTL string
        categories: List of category configs with 'prefix' keys

    Returns:
        Dict mapping category labels to counts
    """
    if not ttl_content or not categories:
        return {}

    g = Graph()
    try:
        g.parse(data=ttl_content, format='turtle')
    except Exception:
        return {}

    counts = {}

    # Known namespaces for ProEthica core concepts
    PROETH_CORE = Namespace('http://proethica.org/ontology/core#')
    PROETH = Namespace('http://proethica.org/ontology/intermediate#')

    for cat in categories:
        prefix = cat.get('prefix', '')
        label = cat.get('label', prefix)

        # Count subclasses of the core concept type
        counted_uris = set()

        # Check proeth-core:Prefix
        for s, p, o in g.triples((None, RDFS.subClassOf, PROETH_CORE[prefix])):
            counted_uris.add(str(s))

        # Also check proeth:Prefix (intermediate namespace)
        for s, p, o in g.triples((None, RDFS.subClassOf, PROETH[prefix])):
            counted_uris.add(str(s))

        count = len(counted_uris)

        # Fallback: count by local name containing the prefix if no subClassOf found
        if count == 0:
            class_uris = set()
            for s in g.subjects(RDF.type, OWL.Class):
                class_uris.add(str(s))

            for uri in class_uris:
                local_name = extract_local_name(uri)
                # Check if local name contains the prefix (e.g., "FundamentalEthicalPrinciple" contains "Principle")
                if prefix in local_name:
                    count += 1

        counts[label] = count

    return counts


def extract_local_name(uri: str) -> str:
    """Extract local name from URI."""
    if '#' in uri:
        return uri.split('#')[-1]
    elif '/' in uri:
        return uri.split('/')[-1]
    return uri


def compute_category_entities(ttl_content: str, categories: list) -> dict:
    """Compute entities grouped by category for the Concepts tab.

    Args:
        ttl_content: Raw TTL string
        categories: List of category configs with 'prefix' keys

    Returns:
        Dict mapping category labels to lists of entities
    """
    if not ttl_content or not categories:
        return {}

    g = Graph()
    try:
        g.parse(data=ttl_content, format='turtle')
    except Exception:
        return {}

    result = {}

    PROETH_CORE = Namespace('http://proethica.org/ontology/core#')
    PROETH = Namespace('http://proethica.org/ontology/intermediate#')

    for cat in categories:
        prefix = cat.get('prefix', '')
        label = cat.get('label', prefix)
        color = cat.get('color', '#6c757d')
        icon = cat.get('icon', 'bi-circle')

        entities = []

        # Find subclasses of the core concept type
        for s, p, o in g.triples((None, RDFS.subClassOf, PROETH_CORE[prefix])):
            entity_label = g.value(s, RDFS.label)
            comment = g.value(s, RDFS.comment)
            entities.append({
                'uri': str(s),
                'label': str(entity_label) if entity_label else extract_local_name(str(s)),
                'comment': str(comment) if comment else None
            })

        # Also check intermediate namespace
        for s, p, o in g.triples((None, RDFS.subClassOf, PROETH[prefix])):
            uri_str = str(s)
            if uri_str not in [e['uri'] for e in entities]:
                entity_label = g.value(s, RDFS.label)
                comment = g.value(s, RDFS.comment)
                entities.append({
                    'uri': uri_str,
                    'label': str(entity_label) if entity_label else extract_local_name(uri_str),
                    'comment': str(comment) if comment else None
                })

        # Sort by label
        entities.sort(key=lambda x: x['label'])

        result[label] = {
            'entities': entities,
            'count': len(entities),
            'color': color,
            'icon': icon,
            'prefix': prefix
        }

    return result


def compute_axioms(ttl_content: str) -> dict:
    """Extract axioms from ontology for the Axioms tab.

    Args:
        ttl_content: Raw TTL string

    Returns:
        Dict with subclass_axioms, property_axioms, etc.
    """
    if not ttl_content:
        return {'subclass': [], 'equivalent': [], 'disjoint': [], 'property_constraints': []}

    g = Graph()
    try:
        g.parse(data=ttl_content, format='turtle')
    except Exception:
        return {'subclass': [], 'equivalent': [], 'disjoint': [], 'property_constraints': []}

    # SubClassOf axioms
    subclass_axioms = []
    for s, p, o in g.triples((None, RDFS.subClassOf, None)):
        # Skip blank nodes
        if str(s).startswith('_:') or str(o).startswith('_:'):
            continue
        subclass_axioms.append({
            'subject': extract_local_name(str(s)),
            'subject_uri': str(s),
            'object': extract_local_name(str(o)),
            'object_uri': str(o)
        })

    # EquivalentClass axioms
    equivalent_axioms = []
    for s, p, o in g.triples((None, OWL.equivalentClass, None)):
        if str(s).startswith('_:') or str(o).startswith('_:'):
            continue
        equivalent_axioms.append({
            'class1': extract_local_name(str(s)),
            'class1_uri': str(s),
            'class2': extract_local_name(str(o)),
            'class2_uri': str(o)
        })

    # DisjointWith axioms
    disjoint_axioms = []
    for s, p, o in g.triples((None, OWL.disjointWith, None)):
        if str(s).startswith('_:') or str(o).startswith('_:'):
            continue
        disjoint_axioms.append({
            'class1': extract_local_name(str(s)),
            'class1_uri': str(s),
            'class2': extract_local_name(str(o)),
            'class2_uri': str(o)
        })

    # Property constraints (domain/range)
    property_constraints = []
    for s in g.subjects(RDF.type, OWL.ObjectProperty):
        domain = g.value(s, RDFS.domain)
        range_val = g.value(s, RDFS.range)
        if domain or range_val:
            property_constraints.append({
                'property': extract_local_name(str(s)),
                'property_uri': str(s),
                'domain': extract_local_name(str(domain)) if domain else None,
                'domain_uri': str(domain) if domain else None,
                'range': extract_local_name(str(range_val)) if range_val else None,
                'range_uri': str(range_val) if range_val else None
            })

    return {
        'subclass': sorted(subclass_axioms, key=lambda x: x['subject']),
        'equivalent': equivalent_axioms,
        'disjoint': disjoint_axioms,
        'property_constraints': sorted(property_constraints, key=lambda x: x['property'])
    }


def get_display_config(ontology) -> dict:
    """Get display configuration from ontology meta_data.

    Args:
        ontology: Ontology model instance

    Returns:
        Display config dict or empty dict
    """
    if not ontology.meta_data:
        return {}

    return ontology.meta_data.get('display_config', {})


def build_stats_context(ontology, entities: dict, relationships: dict) -> dict:
    """Build complete stats context for template.

    Combines OntologyEntity data with display_config and TTL-based fallback.

    Args:
        ontology: Ontology model instance
        entities: Dict from route handler (classes, properties, individuals)
        relationships: Dict from route handler

    Returns:
        Enhanced stats context dict
    """
    display_config = get_or_create_display_config(ontology)

    # Check if we have entity data
    has_entities = bool(entities.get('classes') or entities.get('properties') or entities.get('individuals'))

    stats = {
        'display_config': display_config,
        'display_style': display_config.get('display_style', 'default'),
        'has_entities': has_entities,
    }

    # If no entities but we have TTL content, compute from TTL
    if not has_entities and ontology.current_content:
        ttl_stats = compute_stats_from_ttl(ontology.current_content)
        stats['from_ttl'] = True
        stats['ttl_classes'] = ttl_stats['classes']
        stats['ttl_object_properties'] = ttl_stats['object_properties']
        stats['ttl_datatype_properties'] = ttl_stats['datatype_properties']
        stats['ttl_individuals'] = ttl_stats['individuals']
        stats['ttl_relationships'] = ttl_stats['relationships']
        stats['class_count'] = len(ttl_stats['classes'])
        stats['property_count'] = len(ttl_stats['object_properties']) + len(ttl_stats['datatype_properties'])
        stats['individual_count'] = len(ttl_stats['individuals'])
    else:
        stats['from_ttl'] = False
        stats['class_count'] = len(entities.get('classes', []))
        stats['property_count'] = len(entities.get('properties', []))
        stats['individual_count'] = len(entities.get('individuals', []))

    # Category counts and entities (for domain-specific views like ProEthica)
    featured_categories = display_config.get('featured_categories', [])
    if featured_categories and ontology.current_content:
        stats['category_counts'] = compute_category_counts(
            ontology.current_content,
            featured_categories
        )
        stats['category_entities'] = compute_category_entities(
            ontology.current_content,
            featured_categories
        )
        # Calculate total entities in categories
        stats['category_total'] = sum(
            cat_data['count'] for cat_data in stats['category_entities'].values()
        )
    else:
        stats['category_entities'] = {}
        stats['category_total'] = 0

    # Axioms (subClassOf, equivalentClass, disjointWith, property constraints)
    if ontology.current_content:
        stats['axioms'] = compute_axioms(ontology.current_content)
    else:
        stats['axioms'] = {'subclass': [], 'equivalent': [], 'disjoint': [], 'property_constraints': []}

    # Banner config
    stats['banner'] = display_config.get('banner', {})
    stats['show_banner'] = bool(stats['banner'].get('title'))

    return stats


# Default display configs for known ontologies
DEFAULT_DISPLAY_CONFIGS = {
    'proethica-intermediate': {
        'display_style': 'proethica',
        'banner': {
            'title': 'ProEthica Intermediate Layer',
            'subtitle': 'Nine-Component Framework for Professional Ethics',
            'icon': 'bi-layers',
            'color': 'primary'
        },
        'featured_categories': [
            {'label': 'Roles', 'prefix': 'Role', 'color': '#0d6efd', 'icon': 'bi-person-badge'},
            {'label': 'Principles', 'prefix': 'Principle', 'color': '#fd7e14', 'icon': 'bi-compass'},
            {'label': 'Obligations', 'prefix': 'Obligation', 'color': '#dc3545', 'icon': 'bi-clipboard-check'},
            {'label': 'States', 'prefix': 'State', 'color': '#6f42c1', 'icon': 'bi-flag'},
            {'label': 'Resources', 'prefix': 'Resource', 'color': '#20c997', 'icon': 'bi-book'},
            {'label': 'Actions', 'prefix': 'Action', 'color': '#198754', 'icon': 'bi-lightning'},
            {'label': 'Events', 'prefix': 'Event', 'color': '#ffc107', 'icon': 'bi-calendar-event'},
            {'label': 'Capabilities', 'prefix': 'Capability', 'color': '#0dcaf0', 'icon': 'bi-gear'},
            {'label': 'Constraints', 'prefix': 'Constraint', 'color': '#6c757d', 'icon': 'bi-exclamation-triangle'}
        ],
        'description': 'Bridges core ethical concepts with domain-specific professional ethics knowledge.'
    }
}


def get_or_create_display_config(ontology) -> dict:
    """Get display config, falling back to defaults for known ontologies.

    Args:
        ontology: Ontology model instance

    Returns:
        Display config dict
    """
    # First check meta_data
    config = get_display_config(ontology)
    if config:
        return config

    # Fall back to defaults for known ontologies
    return DEFAULT_DISPLAY_CONFIGS.get(ontology.name, {})
