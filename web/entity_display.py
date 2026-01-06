"""
Entity Display Configuration Handler

Loads entity_display.yaml and provides functions to render entity properties
based on configurable display rules.
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional


# Cache for loaded config
_config_cache = None
_config_mtime = None


def get_config_path() -> Path:
    """Get path to entity display config file."""
    return Path(__file__).parent.parent / 'config' / 'entity_display.yaml'


def load_config() -> Dict[str, Any]:
    """Load entity display configuration, with caching."""
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
            _config_cache = {'entity_types': {}}

    return _config_cache


def get_entity_type_from_uri(parent_uri: str) -> Optional[str]:
    """Extract entity type name from parent URI."""
    if not parent_uri:
        return None

    # Extract the last part after # or /
    if '#' in parent_uri:
        return parent_uri.split('#')[-1]
    elif '/' in parent_uri:
        return parent_uri.split('/')[-1]
    return parent_uri


def get_display_config(entity_type: str) -> Dict[str, Any]:
    """Get display configuration for an entity type."""
    config = load_config()
    entity_types = config.get('entity_types', {})

    # Try exact match first
    if entity_type in entity_types:
        return entity_types[entity_type]

    # Try case-insensitive match
    for key in entity_types:
        if key.lower() == entity_type.lower():
            return entity_types[key]

    # Return default config
    return entity_types.get('_default', {'show_all': True})


def render_badge(value: Any, badge_config: Dict[str, Any]) -> Dict[str, Any]:
    """Render a badge based on configuration."""
    if value is None:
        return None

    str_value = str(value)

    # Determine color
    color = badge_config.get('color', 'secondary')
    color_map = badge_config.get('color_map', {})
    if color_map:
        # Check for matching value in color map
        for map_key, map_color in color_map.items():
            if str_value.lower() == map_key.lower():
                color = map_color
                break

    # Apply transform
    transform = badge_config.get('transform')
    if transform == 'uppercase':
        str_value = str_value.upper()
    elif transform == 'lowercase':
        str_value = str_value.lower()
    elif transform == 'capitalize':
        str_value = str_value.capitalize()

    # Handle percentage type
    badge_type = badge_config.get('type', 'text')
    if badge_type == 'percentage':
        try:
            float_val = float(value)
            str_value = f"{int(float_val * 100)}%"
        except (ValueError, TypeError):
            pass

    return {
        'value': str_value,
        'color': color
    }


def render_field(value: Any, field_config: Dict[str, Any], all_props: Dict[str, Any] = None) -> Dict[str, Any]:
    """Render a field based on configuration."""
    if value is None:
        return None

    result = {
        'label': field_config.get('label', field_config.get('field', 'Value')),
        'value': str(value),
        'style': field_config.get('style')
    }

    # Handle badge suffix
    badge_suffix = field_config.get('badge_suffix')
    if badge_suffix and all_props and badge_suffix in all_props:
        result['badge'] = {
            'value': str(all_props[badge_suffix]),
            'color': 'light'
        }

    return result


def render_entity_properties(properties: Dict[str, Any], parent_uri: str = None) -> Dict[str, Any]:
    """
    Render entity properties based on configuration.

    Returns:
        {
            'badges': [{'value': 'PRO', 'color': 'success'}, ...],
            'fields': [{'label': 'Claim', 'value': '...', 'style': 'bold'}, ...],
            'extra': [{'label': 'key', 'value': 'val'}, ...]  # For show_all fallback
        }
    """
    if not properties:
        return {'badges': [], 'fields': [], 'extra': []}

    # Get entity type from parent_uri
    entity_type = get_entity_type_from_uri(parent_uri)
    config = get_display_config(entity_type) if entity_type else get_display_config('_default')

    result = {
        'badges': [],
        'fields': [],
        'extra': []
    }

    used_fields = set()

    # Process badges
    for badge_config in config.get('badges', []):
        field_name = badge_config.get('field')
        if field_name and field_name in properties:
            badge = render_badge(properties[field_name], badge_config)
            if badge:
                result['badges'].append(badge)
                used_fields.add(field_name)

    # Process fields
    for field_config in config.get('fields', []):
        field_name = field_config.get('field')
        pattern = field_config.get('pattern')

        if pattern:
            # Handle pattern matching (e.g., option1, option2, ...)
            matching_fields = []
            for key in properties:
                if key.startswith(pattern):
                    matching_fields.append((key, properties[key]))
                    used_fields.add(key)

            if matching_fields:
                # Sort by any numeric suffix
                def sort_key(item):
                    match = re.search(r'(\d+)$', item[0])
                    return int(match.group(1)) if match else 0

                matching_fields.sort(key=sort_key)

                list_values = [str(v) for k, v in matching_fields]
                result['fields'].append({
                    'label': field_config.get('label', pattern),
                    'list_items': list_values,
                    'style': field_config.get('style', 'list')
                })

        elif field_name and field_name in properties:
            field = render_field(properties[field_name], field_config, properties)
            if field:
                result['fields'].append(field)
                used_fields.add(field_name)

                # Also mark badge_suffix as used
                badge_suffix = field_config.get('badge_suffix')
                if badge_suffix:
                    used_fields.add(badge_suffix)

    # Handle show_all for default/fallback
    if config.get('show_all'):
        exclude = set(config.get('exclude_fields', []))
        for key, value in properties.items():
            if key not in used_fields and key not in exclude:
                result['extra'].append({
                    'label': key,
                    'value': str(value) if not isinstance(value, list) else ', '.join(str(v) for v in value)
                })

    return result


def get_all_entity_types() -> List[str]:
    """Get list of all configured entity types."""
    config = load_config()
    return [k for k in config.get('entity_types', {}).keys() if k != '_default']
