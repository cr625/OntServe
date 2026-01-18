"""
Case Display Configuration Handler

Loads case_display.yaml and provides functions to organize case ontology
entities into meaningful sections for display.
"""

import os
import re
import yaml
import fnmatch
from pathlib import Path
from typing import Dict, Any, List, Optional


# Cache for loaded config
_config_cache = None
_config_mtime = None


def get_config_path() -> Path:
    """Get path to case display config file."""
    return Path(__file__).parent.parent / 'config' / 'case_display.yaml'


def load_config() -> Dict[str, Any]:
    """Load case display configuration, with caching."""
    global _config_cache, _config_mtime

    config_path = get_config_path()

    # Check if file has been modified
    current_mtime = config_path.stat().st_mtime if config_path.exists() else None

    if _config_cache is None or _config_mtime != current_mtime:
        if config_path.exists():
            with open(config_path, 'r') as f:
                _config_cache = yaml.safe_load(f)
            _config_mtime = current_mtime
        else:
            _config_cache = {'default': {'sections': []}, 'domains': {}}

    return _config_cache


def is_case_ontology(ontology_name: str, entities: List[Any] = None) -> bool:
    """
    Determine if an ontology is a case ontology.

    Args:
        ontology_name: Name of the ontology
        entities: Optional list of entities to check for case-specific types

    Returns:
        True if this appears to be a case ontology
    """
    config = load_config()
    detection = config.get('case_detection', {})

    # Check name patterns
    name_patterns = detection.get('name_patterns', [])
    for pattern in name_patterns:
        if fnmatch.fnmatch(ontology_name, pattern):
            return True

    # Check for required entity types if entities provided
    if entities:
        required_types = detection.get('required_entity_types', [])
        if required_types:
            entity_types = set()
            for entity in entities:
                if entity.parent_uri:
                    # Extract type name from URI
                    type_name = entity.parent_uri.split('#')[-1].split('/')[-1]
                    entity_types.add(type_name)

            # Check if all required types are present
            if all(rt in entity_types for rt in required_types):
                return True

    return False


def get_domain_from_ontology(ontology_name: str) -> str:
    """
    Extract domain from ontology name.

    For now, defaults to 'engineering' for ProEthica cases.
    Future: could be stored in ontology metadata.
    """
    if ontology_name.startswith('proethica-'):
        return 'engineering'
    return 'default'


def get_display_config(domain: str = None) -> Dict[str, Any]:
    """
    Get display configuration for a domain.

    Args:
        domain: Domain name (e.g., 'engineering', 'medical')

    Returns:
        Display configuration with sections
    """
    config = load_config()

    # Get base default config
    default_config = config.get('default', {'sections': []})

    if not domain or domain == 'default':
        return default_config

    # Get domain-specific config
    domains = config.get('domains', {})
    domain_config = domains.get(domain)

    if not domain_config:
        return default_config

    # Handle inheritance
    if domain_config.get('inherit') == 'default':
        # Start with default, apply overrides
        result = {'sections': list(default_config.get('sections', []))}

        # Apply section overrides
        overrides = domain_config.get('section_overrides', {})
        for section in result['sections']:
            section_id = section.get('id')
            if section_id in overrides:
                section.update(overrides[section_id])

        return result

    return domain_config


def get_entity_type_name(entity) -> Optional[str]:
    """Extract entity type name from parent_uri."""
    if not entity.parent_uri:
        return None

    # Extract the last part after # or /
    uri = entity.parent_uri
    if '#' in uri:
        return uri.split('#')[-1]
    elif '/' in uri:
        return uri.split('/')[-1]
    return uri


def match_entity_to_concept_type(entity_type: str, concept_types: List[str]) -> Optional[str]:
    """
    Match an entity type name to one of the 9-concept types.

    Handles both exact matches and suffix matches (e.g., 'EnvironmentalEngineerRole' -> 'Role').

    Args:
        entity_type: The entity type name from parent_uri (e.g., 'EnvironmentalEngineerRole')
        concept_types: List of expected concept type names (e.g., ['Role', 'Action', 'State'])

    Returns:
        The matching concept type, or None if no match
    """
    if not entity_type:
        return None

    # First try exact match
    if entity_type in concept_types:
        return entity_type

    # Then try suffix match (e.g., 'EnvironmentalEngineerRole' ends with 'Role')
    for concept_type in concept_types:
        if entity_type.endswith(concept_type):
            return concept_type

    return None


def organize_entities_for_case(entities: List[Any], domain: str = None) -> Dict[str, Any]:
    """
    Organize entities into sections based on case display configuration.

    Args:
        entities: List of OntologyEntity objects
        domain: Domain for display configuration

    Returns:
        Dictionary with:
            - sections: List of section dicts with their entities
            - stats: Summary statistics
    """
    config = get_display_config(domain)
    sections_config = config.get('sections', [])

    # Build mapping of entity type to section
    type_to_section = {}
    for section in sections_config:
        section_id = section.get('id')

        # Handle subsections
        if 'subsections' in section:
            for subsection in section['subsections']:
                for entity_type in subsection.get('entity_types', []):
                    type_to_section[entity_type] = (section_id, subsection.get('id'))
        else:
            for entity_type in section.get('entity_types', []):
                type_to_section[entity_type] = (section_id, None)

    # Initialize result sections
    result_sections = []
    section_entities = {}  # section_id -> entities or subsection_id -> entities

    for section in sections_config:
        section_id = section.get('id')
        section_data = {
            'id': section_id,
            'title': section.get('title', section_id),
            'description': section.get('description'),
            'icon': section.get('icon'),
            'collapsed': section.get('collapsed', False),
            'max_preview': section.get('max_preview', 10),
            'entities': [],
            'subsections': None
        }

        if 'subsections' in section:
            section_data['subsections'] = []
            for subsection in section['subsections']:
                section_data['subsections'].append({
                    'id': subsection.get('id'),
                    'title': subsection.get('title', subsection.get('id')),
                    'icon': subsection.get('icon'),
                    'color': subsection.get('color'),
                    'abbrev': subsection.get('abbrev'),
                    'entities': []
                })

        result_sections.append(section_data)
        section_entities[section_id] = section_data

    # Categorize entities
    uncategorized = []
    stats = {
        'total': len(entities),
        'by_type': {},
        'by_section': {}
    }

    # Build list of all known concept types for flexible matching
    all_concept_types = list(type_to_section.keys())

    for entity in entities:
        entity_type = get_entity_type_name(entity)

        # Track stats
        if entity_type:
            stats['by_type'][entity_type] = stats['by_type'].get(entity_type, 0) + 1

        # Find matching section - try exact match first, then suffix match
        matched = False
        matched_type = None

        if entity_type:
            # First try exact match
            if entity_type in type_to_section:
                matched_type = entity_type
            else:
                # Try suffix match (e.g., 'EnvironmentalEngineerRole' -> 'Role')
                matched_type = match_entity_to_concept_type(entity_type, all_concept_types)

        if matched_type and matched_type in type_to_section:
            section_id, subsection_id = type_to_section[matched_type]
            section = section_entities.get(section_id)

            if section:
                if subsection_id and section.get('subsections'):
                    # Add to subsection
                    for subsection in section['subsections']:
                        if subsection['id'] == subsection_id:
                            subsection['entities'].append(entity)
                            matched = True
                            break
                else:
                    section['entities'].append(entity)
                    matched = True

        if not matched:
            uncategorized.append(entity)

    # Add uncategorized to "other" section
    other_section = section_entities.get('other')
    if other_section:
        other_section['entities'].extend(uncategorized)

    # Calculate section stats
    for section in result_sections:
        section_count = len(section['entities'])
        if section.get('subsections'):
            section_count = sum(len(s['entities']) for s in section['subsections'])
        stats['by_section'][section['id']] = section_count

    # Filter out empty sections (except "other" which we keep if non-empty)
    non_empty_sections = []
    for section in result_sections:
        has_entities = len(section['entities']) > 0
        if section.get('subsections'):
            has_entities = any(len(s['entities']) > 0 for s in section['subsections'])

        if has_entities or section['id'] == 'other' and len(section['entities']) > 0:
            non_empty_sections.append(section)

    return {
        'sections': non_empty_sections,
        'stats': stats
    }


def get_section_summary(sections: List[Dict]) -> List[Dict]:
    """
    Get summary information for each section (for sidebar/nav).

    Returns list of {id, title, count, icon}
    """
    summary = []
    for section in sections:
        count = len(section.get('entities', []))
        if section.get('subsections'):
            count = sum(len(s.get('entities', [])) for s in section['subsections'])

        if count > 0:
            summary.append({
                'id': section['id'],
                'title': section['title'],
                'count': count,
                'icon': section.get('icon')
            })

    return summary
