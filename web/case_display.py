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


# Cache for ontology hierarchy mapping (type_name -> root concept)
_hierarchy_cache = None


def _build_hierarchy_map() -> Dict[str, str]:
    """Build a mapping from any proethica class name to its root concept (Role, Principle, etc.).

    Walks the parent_uri chain in proethica-intermediate and proethica-core to resolve
    each class to one of the 9 base concepts.
    """
    global _hierarchy_cache
    if _hierarchy_cache is not None:
        return _hierarchy_cache

    root_concepts = {'Role', 'Principle', 'Obligation', 'State', 'Resource',
                     'Action', 'Event', 'Capability', 'Constraint'}

    try:
        from web.models import OntologyEntity, Ontology, db
        from sqlalchemy import select

        # Load all classes from intermediate + extended + core ontologies
        ontology_names = ['proethica-intermediate', 'proethica-intermediate-extended',
                          'proethica-core', 'engineering-ethics']
        ont_ids = []
        for name in ontology_names:
            ont = db.session.execute(select(Ontology).where(Ontology.name == name)).scalar()
            if ont:
                ont_ids.append(ont.id)

        if not ont_ids:
            _hierarchy_cache = {}
            return _hierarchy_cache

        entities = db.session.execute(
            select(OntologyEntity).where(
                OntologyEntity.ontology_id.in_(ont_ids),
                OntologyEntity.entity_type.in_(['class', 'Class']),
            )
        ).scalars().all()

        # Build URI -> (label, parent_uri) index.
        # When duplicate URIs exist across ontologies, prefer the entry
        # with a non-self-referencing parent_uri (avoids broken chains
        # from re-imported classes in extended ontologies).
        uri_to_info = {}
        for e in entities:
            label = e.label or e.uri.split('#')[-1].split('/')[-1]
            existing = uri_to_info.get(e.uri)
            if existing:
                # Skip if new entry's parent_uri is self-referencing
                if e.parent_uri == e.uri:
                    continue
                # Overwrite only if existing has no parent or is self-referencing
                if not existing[1] or existing[1] == e.uri:
                    uri_to_info[e.uri] = (label, e.parent_uri)
            else:
                uri_to_info[e.uri] = (label, e.parent_uri)

        # For each class, walk up the parent chain to find a root concept.
        # Index by BOTH the human label ("Case Precedent") and the URI
        # fragment ("CasePrecedent"), since callers may use either form.
        result = {}
        for uri, (label, parent_uri) in uri_to_info.items():
            # Extract CamelCase fragment from URI for alternate key
            uri_frag = uri.split('#')[-1].split('/')[-1]

            if label in root_concepts:
                result[label] = label
                result[uri_frag] = label
                continue

            # Walk up parent chain (max 10 levels)
            visited = set()
            current_uri = parent_uri
            found_root = None
            for _ in range(10):
                if not current_uri or current_uri in visited:
                    break
                visited.add(current_uri)
                info = uri_to_info.get(current_uri)
                if info:
                    parent_label, grandparent_uri = info
                    if parent_label in root_concepts:
                        found_root = parent_label
                        break
                    current_uri = grandparent_uri
                else:
                    # Try extracting label from URI directly
                    frag = current_uri.split('#')[-1].split('/')[-1]
                    if frag in root_concepts:
                        found_root = frag
                    break

            if found_root:
                result[label] = found_root
                result[uri_frag] = found_root

        _hierarchy_cache = result
    except Exception:
        _hierarchy_cache = {}

    return _hierarchy_cache


def match_entity_to_concept_type(entity_type: str, concept_types: List[str]) -> Optional[str]:
    """
    Match an entity type name to one of the 9-concept types.

    Matching order:
      1. Exact match against concept_types
      2. Suffix match (e.g., 'CompetenceConstraint' ends with 'Constraint')
      3. Ontology hierarchy walk (resolves 'MilitaryOfficial' -> 'Role')
      4. Prefix match: a known hierarchy key is a prefix of entity_type
         (handles variant URIs like 'ClientRelationshipEstablished' when
         'ClientRelationship' -> State exists in the hierarchy)
      5. Case-insensitive lookup on the hierarchy map

    Args:
        entity_type: The entity type name from parent_uri (e.g., 'ExpertInterpretation')
        concept_types: List of expected concept type names (e.g., ['Role', 'Action', 'State'])

    Returns:
        The matching concept type, or None if no match
    """
    if not entity_type:
        return None

    # 1. Exact match
    if entity_type in concept_types:
        return entity_type

    # 2. Suffix match (e.g., 'EnvironmentalEngineerRole' ends with 'Role')
    for concept_type in concept_types:
        if entity_type.endswith(concept_type):
            return concept_type

    # 3. Ontology hierarchy walk
    hierarchy = _build_hierarchy_map()
    root = hierarchy.get(entity_type)
    if root and root in concept_types:
        return root

    # 4. Prefix match: find the longest hierarchy key that is a prefix
    #    of entity_type (e.g., 'ClientRelationship' matches
    #    'ClientRelationshipEstablished')
    best_prefix = ''
    best_root = None
    for key, key_root in hierarchy.items():
        if (entity_type.startswith(key)
                and len(key) > len(best_prefix)
                and key_root in concept_types):
            best_prefix = key
            best_root = key_root
    if best_root:
        return best_root

    # 5. Case-insensitive lookup
    entity_lower = entity_type.lower()
    for key, key_root in hierarchy.items():
        if key.lower() == entity_lower and key_root in concept_types:
            return key_root

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

        # Find matching section.
        # Priority: conceptCategory property (set at commit time) > exact type match > hierarchy walk
        matched = False
        matched_type = None

        # Check conceptCategory property first (reliable, set by ProEthica at commit)
        props = getattr(entity, 'properties', None) or {}
        concept_cat = props.get('conceptCategory')
        if concept_cat and concept_cat in type_to_section:
            matched_type = concept_cat
        elif entity_type:
            # Fall back to type-name matching for legacy data
            if entity_type in type_to_section:
                matched_type = entity_type
            else:
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


# Canonical reading order for the case page. Drives BOTH the sidebar nav and
# the body so the two cannot drift apart (the prior template listed YAML
# sections and the bespoke panels in different orders). Ids are either YAML
# section ids or the three bespoke panel ids (competition / citations /
# conclusions). Any YAML section not named here is appended in its original
# order, just before "other".
PAGE_BLOCK_ORDER = [
    'nine_concepts',     # the extracted entities (foundation)
    'competition',       # panel: how the obligations compete / prevail
    'citations',         # panel: NSPE provisions grounding the conclusions
    'decision_points',
    'arguments',
    'questions',
    'conclusions',       # panel: synthesized ethical conclusions (cited-by targets)
    'validation',
    'analysis',
    'other',
]

_PANEL_META = {
    'competition': {'title': 'Obligation Competition', 'icon': 'bi bi-shield-exclamation'},
    'citations': {'title': 'Cited NSPE Provisions', 'icon': 'bi bi-link-45deg'},
    'conclusions': {'title': 'Conclusions', 'icon': 'bi bi-chat-left-quote'},
}


def _section_count(section: Dict) -> int:
    """Total entity count for a section, summing subsections when present."""
    if section.get('subsections'):
        return sum(len(s.get('entities', [])) for s in section['subsections'])
    return len(section.get('entities', []))


def build_ordered_blocks(case_sections: List[Dict], competition=None,
                         citations=None, conclusions=None) -> List[Dict]:
    """Build one ordered list of renderable page blocks for nav + body parity.

    Each block is a dict with: kind ('section'|'panel'), id, title, icon,
    count, and (for sections) the section object. Only blocks with content are
    returned. The bespoke ``conclusions`` panel supersedes the YAML
    ``conclusions`` section when the panel has data, so the redundant YAML
    section is dropped (it previously produced a duplicate "Conclusions" entry
    and an ``id="section-conclusions"`` collision).
    """
    sections_by_id = {s['id']: s for s in case_sections}

    panel_present = {
        'competition': bool(competition and getattr(competition, 'has_edges', competition.get('has_edges') if isinstance(competition, dict) else False)),
        'citations': bool(citations and (citations.get('has_citations') if isinstance(citations, dict) else getattr(citations, 'has_citations', False))),
        'conclusions': bool(conclusions and (conclusions.get('has_conclusions') if isinstance(conclusions, dict) else getattr(conclusions, 'has_conclusions', False))),
    }

    def _panel_count(name):
        if name == 'competition':
            return len(competition.get('clusters', [])) if isinstance(competition, dict) else len(getattr(competition, 'clusters', []))
        if name == 'citations':
            return citations.get('provision_count', 0) if isinstance(citations, dict) else getattr(citations, 'provision_count', 0)
        if name == 'conclusions':
            return conclusions.get('count', 0) if isinstance(conclusions, dict) else getattr(conclusions, 'count', 0)
        return 0

    blocks = []
    consumed_sections = set()

    for block_id in PAGE_BLOCK_ORDER:
        if block_id in _PANEL_META:
            if not panel_present.get(block_id):
                continue
            # Drop the redundant YAML section of the same id (panel wins).
            consumed_sections.add(block_id)
            meta = _PANEL_META[block_id]
            blocks.append({
                'kind': 'panel',
                'id': block_id,
                'title': meta['title'],
                'icon': meta['icon'],
                'count': _panel_count(block_id),
            })
        else:
            section = sections_by_id.get(block_id)
            if not section:
                continue
            consumed_sections.add(block_id)
            count = _section_count(section)
            if count <= 0:
                continue
            blocks.append({
                'kind': 'section',
                'id': block_id,
                'title': section.get('title', block_id),
                'icon': section.get('icon'),
                'count': count,
                'section': section,
            })

    # Append any YAML sections not named in PAGE_BLOCK_ORDER, in their original
    # order, before the trailing "other" block if one was emitted.
    extra = [s for s in case_sections
             if s['id'] not in consumed_sections and _section_count(s) > 0]
    if extra:
        insert_at = len(blocks)
        for i, b in enumerate(blocks):
            if b['id'] == 'other':
                insert_at = i
                break
        extra_blocks = [{
            'kind': 'section', 'id': s['id'], 'title': s.get('title', s['id']),
            'icon': s.get('icon'), 'count': _section_count(s), 'section': s,
        } for s in extra]
        blocks[insert_at:insert_at] = extra_blocks

    return blocks


_concept_meta_cache = None


def concept_type_meta(concept_type: str) -> Optional[Dict[str, str]]:
    """Return {abbrev, color, icon, name} for one of the 9 core concept types
    (Role, Principle, ...), sourced from the nine_concepts subsections in
    case_display.yaml. None for unknown types. Used to colour-code individuals
    consistently across the case page and the entity detail page."""
    global _concept_meta_cache
    if _concept_meta_cache is None:
        cache: Dict[str, Dict[str, str]] = {}
        cfg = load_config()
        for section in cfg.get('default', {}).get('sections', []):
            if section.get('id') != 'nine_concepts':
                continue
            for sub in section.get('subsections', []):
                for et in sub.get('entity_types', []):
                    # The entity_type (Role, Capability, ...) is the singular
                    # concept name; the subsection title is the plural section name.
                    cache[et] = {
                        'abbrev': sub.get('abbrev'),
                        'color': sub.get('color'),
                        'icon': sub.get('icon'),
                        'name': et,
                    }
        _concept_meta_cache = cache
    return _concept_meta_cache.get(concept_type) if concept_type else None


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
