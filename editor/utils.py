"""
OntServe Editor Utilities

Utility classes for entity mapping, hierarchy building, and other helper functions.
"""

import logging
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

# Handle imports based on context
try:
    from web.models import OntologyEntity, Ontology
except ImportError:
    try:
        from ..web.models import OntologyEntity, Ontology
    except ImportError:
        from models import OntologyEntity, Ontology

logger = logging.getLogger(__name__)


class EntityTypeMapper:
    """
    Maps between different entity type representations and provides
    consistency across the ontology editor system.
    """
    
    # ProEthica entity types mapping
    PROETHICA_TYPES = {
        'role': 'Role',
        'condition': 'Condition', 
        'resource': 'Resource',
        'action': 'Action',
        'event': 'Event',
        'capability': 'Capability'
    }
    
    # Base RDF types
    BASE_TYPES = {
        'class': 'Class',
        'property': 'Property',
        'individual': 'Individual'
    }
    
    # Combined mapping
    ALL_TYPES = {**BASE_TYPES, **PROETHICA_TYPES}
    
    @classmethod
    def get_display_name(cls, entity_type: str) -> str:
        """
        Get the display name for an entity type.
        
        Args:
            entity_type: Internal entity type identifier
            
        Returns:
            Human-readable display name
        """
        return cls.ALL_TYPES.get(entity_type, entity_type.title())
    
    @classmethod
    def get_css_class(cls, entity_type: str) -> str:
        """
        Get the CSS class for styling an entity type.
        
        Args:
            entity_type: Internal entity type identifier
            
        Returns:
            CSS class name
        """
        # Map entity types to CSS classes for styling
        css_mapping = {
            'class': 'entity-class',
            'property': 'entity-property',
            'individual': 'entity-individual',
            'role': 'entity-role',
            'condition': 'entity-condition',
            'resource': 'entity-resource', 
            'action': 'entity-action',
            'event': 'entity-event',
            'capability': 'entity-capability'
        }
        return css_mapping.get(entity_type, 'entity-default')
    
    @classmethod
    def get_icon(cls, entity_type: str) -> str:
        """
        Get the icon name for an entity type.
        
        Args:
            entity_type: Internal entity type identifier
            
        Returns:
            Icon class or unicode symbol
        """
        icon_mapping = {
            'class': '📋',
            'property': '🔗',
            'individual': '👤',
            'role': '🎭',
            'condition': '⚡',
            'resource': '📦',
            'action': '⚡',
            'event': '📅',
            'capability': '🎯'
        }
        return icon_mapping.get(entity_type, '❓')
    
    @classmethod
    def is_proethica_type(cls, entity_type: str) -> bool:
        """Check if an entity type is a ProEthica-specific type."""
        return entity_type in cls.PROETHICA_TYPES
    
    @classmethod
    def is_bfo_aligned(cls, uri: str) -> bool:
        """Check if a URI indicates BFO alignment."""
        if not uri:
            return False
        
        uri_lower = uri.lower()
        return (
            'purl.obolibrary.org/obo/bfo' in uri_lower or
            'proethica.org/ontology' in uri_lower
        )
    
    @classmethod
    def get_entity_color(cls, entity_type: str, uri: str = None) -> str:
        """
        Get a color code for visualizing an entity.
        
        Args:
            entity_type: Internal entity type identifier
            uri: Optional URI for additional context
            
        Returns:
            Hex color code
        """
        # Base colors for entity types
        type_colors = {
            'class': '#4A90E2',      # Blue
            'property': '#F5A623',   # Orange
            'individual': '#7ED321', # Green
            'role': '#9013FE',       # Purple
            'condition': '#FF6B6B',  # Red
            'resource': '#4ECDC4',   # Teal
            'action': '#FFD93D',     # Yellow
            'event': '#FF9500',      # Orange-red
            'capability': '#00C9FF'  # Cyan
        }
        
        base_color = type_colors.get(entity_type, '#95A5A6')  # Default gray
        
        # Modify shade based on BFO alignment
        if uri and cls.is_bfo_aligned(uri):
            # Slightly darker shade for BFO-aligned entities
            return cls._darken_color(base_color, 0.1)
        
        return base_color
    
    @classmethod
    def _darken_color(cls, hex_color: str, factor: float) -> str:
        """Darken a hex color by a given factor."""
        # Remove # if present
        hex_color = hex_color.lstrip('#')
        
        # Convert to RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        # Darken by factor
        r = int(r * (1 - factor))
        g = int(g * (1 - factor))
        b = int(b * (1 - factor))
        
        # Convert back to hex
        return f"#{r:02x}{g:02x}{b:02x}"


class HierarchyBuilder:
    """
    Builds hierarchical structures from flat entity lists.
    Replaces Neo4j graph traversal with in-memory hierarchy building.
    """
    
    def __init__(self):
        """Initialize the hierarchy builder."""
        self.entity_map = {}
        self.parent_map = defaultdict(list)
        self.root_entities = []
    
    def build_hierarchy(self, entities: List[OntologyEntity], ontology: Ontology) -> Dict[str, Any]:
        """
        Build a hierarchical structure from a flat list of entities.
        
        Args:
            entities: List of OntologyEntity objects
            ontology: The ontology these entities belong to
            
        Returns:
            Hierarchical structure as nested dictionaries
        """
        # Reset internal state
        self.entity_map = {}
        self.parent_map = defaultdict(list)
        self.root_entities = []
        
        # Build entity map and parent relationships
        for entity in entities:
            self.entity_map[entity.uri] = entity
            
            if entity.parent_uri:
                self.parent_map[entity.parent_uri].append(entity.uri)
            else:
                self.root_entities.append(entity.uri)
        
        # If no explicit roots found, look for common root patterns
        if not self.root_entities:
            self.root_entities = self._find_implicit_roots(entities)
        
        # Build the hierarchy tree
        hierarchy = {
            'name': ontology.name,
            'ontology_id': ontology.ontology_id,
            'type': 'root',
            'uri': f"ontology:{ontology.ontology_id}",
            'description': ontology.description or f"Hierarchy for {ontology.name}",
            'children': []
        }
        
        # Add root entities as children
        for root_uri in self.root_entities:
            if root_uri in self.entity_map:
                child_node = self._build_entity_node(root_uri)
                if child_node:
                    hierarchy['children'].append(child_node)
        
        # Add orphaned entities (entities with parent_uri that doesn't exist)
        orphaned = self._find_orphaned_entities()
        for orphan_uri in orphaned:
            child_node = self._build_entity_node(orphan_uri)
            if child_node:
                hierarchy['children'].append(child_node)
        
        return hierarchy
    
    def _find_implicit_roots(self, entities: List[OntologyEntity]) -> List[str]:
        """
        Find implicit root entities by looking for common patterns.
        
        Args:
            entities: List of entities to analyze
            
        Returns:
            List of URIs that should be considered roots
        """
        # Look for BFO root classes
        bfo_roots = []
        other_roots = []
        
        for entity in entities:
            uri_lower = entity.uri.lower()
            
            # BFO Entity is often a root
            if 'bfo_0000001' in uri_lower:  # BFO Entity
                bfo_roots.append(entity.uri)
            
            # Other potential roots based on naming patterns
            elif any(pattern in entity.label.lower() if entity.label else '' 
                    for pattern in ['entity', 'thing', 'object', 'continuant', 'occurrent']):
                other_roots.append(entity.uri)
        
        # Prefer BFO roots if available
        if bfo_roots:
            return bfo_roots
        elif other_roots:
            return other_roots[:3]  # Limit to prevent too many roots
        
        # If still no roots, just take entities without parents
        return [entity.uri for entity in entities if not entity.parent_uri][:5]
    
    def _find_orphaned_entities(self) -> List[str]:
        """Find entities whose parent_uri doesn't exist in the entity map."""
        orphaned = []
        
        for uri, entity in self.entity_map.items():
            if entity.parent_uri and entity.parent_uri not in self.entity_map:
                orphaned.append(uri)
        
        return orphaned
    
    def _build_entity_node(self, uri: str, visited: Optional[Set[str]] = None) -> Optional[Dict[str, Any]]:
        """
        Recursively build a hierarchy node for an entity and its children.
        
        Args:
            uri: URI of the entity to build node for
            visited: Set of already visited URIs to prevent infinite recursion
            
        Returns:
            Dictionary representing the entity node and its children
        """
        if visited is None:
            visited = set()
        
        # Prevent infinite recursion
        if uri in visited:
            return None
        
        visited.add(uri)
        
        entity = self.entity_map.get(uri)
        if not entity:
            return None
        
        # Build the node
        node = {
            'name': entity.label or self._extract_name_from_uri(uri),
            'uri': uri,
            'type': self._classify_entity_type(entity),
            'entity_type': entity.entity_type,
            'description': entity.comment,
            'properties': {}
        }
        
        # Add entity-specific properties
        if entity.domain:
            node['properties']['domain'] = entity.domain
        if entity.range:
            node['properties']['range'] = entity.range
        if entity.properties:
            node['properties'].update(entity.properties)
        
        # Add creation metadata
        if entity.created_at:
            node['properties']['created'] = entity.created_at.isoformat()
        
        # Recursively add children
        children = []
        child_uris = self.parent_map.get(uri, [])
        
        for child_uri in child_uris:
            child_node = self._build_entity_node(child_uri, visited.copy())
            if child_node:
                children.append(child_node)
        
        if children:
            node['children'] = children
        
        return node
    
    def _extract_name_from_uri(self, uri: str) -> str:
        """Extract a readable name from a URI."""
        # Try fragment first
        if '#' in uri:
            return uri.split('#')[-1]
        
        # Then try last path component
        if '/' in uri:
            return uri.split('/')[-1]
        
        # Fall back to the full URI
        return uri
    
    def _classify_entity_type(self, entity: OntologyEntity) -> str:
        """
        Classify entity type for visualization purposes.
        
        Args:
            entity: The entity to classify
            
        Returns:
            Classification string for styling/visualization
        """
        uri_lower = entity.uri.lower()
        
        # BFO classification
        if 'purl.obolibrary.org/obo/bfo' in uri_lower:
            return 'bfo'
        
        # PROV-O classification
        if 'w3.org/ns/prov' in uri_lower:
            return 'prov'
        
        # ProEthica classification
        if 'proethica.org/ontology' in uri_lower:
            return 'bfo-aligned'
        
        # Other external ontologies
        if any(domain in uri_lower for domain in ['w3.org', 'schema.org', 'dublincore.org']):
            return 'external'
        
        # Local/custom entities
        return 'custom'
    
    def get_flat_entity_list(self, hierarchy: Dict[str, Any], entity_type_filter: str = None) -> List[Dict[str, Any]]:
        """
        Extract a flat list of entities from a hierarchy.
        
        Args:
            hierarchy: Hierarchical structure
            entity_type_filter: Optional filter by entity type
            
        Returns:
            Flat list of entity dictionaries
        """
        entities = []
        
        def extract_entities(node):
            # Skip root node
            if node.get('type') != 'root' and 'uri' in node:
                if entity_type_filter is None or node.get('entity_type') == entity_type_filter:
                    entities.append(node)
            
            # Recursively process children
            for child in node.get('children', []):
                extract_entities(child)
        
        extract_entities(hierarchy)
        return entities
    
    def get_entity_paths(self, hierarchy: Dict[str, Any], target_uri: str) -> List[List[str]]:
        """
        Find all paths from root to a target entity.
        
        Args:
            hierarchy: Hierarchical structure
            target_uri: URI of the target entity
            
        Returns:
            List of paths, where each path is a list of entity names
        """
        paths = []
        
        def find_paths(node, current_path):
            current_path = current_path + [node.get('name', 'Unknown')]
            
            if node.get('uri') == target_uri:
                paths.append(current_path)
                return
            
            for child in node.get('children', []):
                find_paths(child, current_path)
        
        find_paths(hierarchy, [])
        return paths
    
    def calculate_hierarchy_stats(self, hierarchy: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate statistics about the hierarchy.
        
        Args:
            hierarchy: Hierarchical structure
            
        Returns:
            Dictionary with hierarchy statistics
        """
        stats = {
            'total_entities': 0,
            'max_depth': 0,
            'entity_type_counts': defaultdict(int),
            'classification_counts': defaultdict(int)
        }
        
        def analyze_node(node, depth=0):
            stats['max_depth'] = max(stats['max_depth'], depth)
            
            if node.get('type') != 'root':
                stats['total_entities'] += 1
                
                entity_type = node.get('entity_type', 'unknown')
                stats['entity_type_counts'][entity_type] += 1
                
                classification = node.get('type', 'unknown')
                stats['classification_counts'][classification] += 1
            
            for child in node.get('children', []):
                analyze_node(child, depth + 1)
        
        analyze_node(hierarchy)
        
        # Convert defaultdicts to regular dicts
        stats['entity_type_counts'] = dict(stats['entity_type_counts'])
        stats['classification_counts'] = dict(stats['classification_counts'])
        
        return stats


class SearchHelper:
    """
    Helper functions for entity search and filtering.
    """
    
    @staticmethod
    def filter_entities_by_text(entities: List[Dict[str, Any]], search_term: str) -> List[Dict[str, Any]]:
        """
        Filter entities by text search in name, description, and URI.
        
        Args:
            entities: List of entity dictionaries
            search_term: Search term to filter by
            
        Returns:
            Filtered list of entities
        """
        if not search_term:
            return entities
        
        search_lower = search_term.lower()
        filtered = []
        
        for entity in entities:
            # Search in name
            if search_lower in (entity.get('name', '')).lower():
                filtered.append(entity)
                continue
            
            # Search in description
            if search_lower in (entity.get('description', '') or '').lower():
                filtered.append(entity)
                continue
            
            # Search in URI
            if search_lower in (entity.get('uri', '')).lower():
                filtered.append(entity)
                continue
        
        return filtered
    
    @staticmethod
    def group_entities_by_type(entities: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group entities by their type.
        
        Args:
            entities: List of entity dictionaries
            
        Returns:
            Dictionary mapping entity types to lists of entities
        """
        groups = defaultdict(list)
        
        for entity in entities:
            entity_type = entity.get('entity_type', 'unknown')
            groups[entity_type].append(entity)
        
        return dict(groups)
    
    @staticmethod
    def sort_entities(entities: List[Dict[str, Any]], sort_by: str = 'name', reverse: bool = False) -> List[Dict[str, Any]]:
        """
        Sort entities by a specified field.
        
        Args:
            entities: List of entity dictionaries
            sort_by: Field to sort by ('name', 'type', 'uri')
            reverse: Whether to sort in reverse order
            
        Returns:
            Sorted list of entities
        """
        sort_key_map = {
            'name': lambda x: (x.get('name', '') or '').lower(),
            'type': lambda x: x.get('entity_type', ''),
            'uri': lambda x: x.get('uri', '')
        }
        
        sort_key = sort_key_map.get(sort_by, sort_key_map['name'])
        
        return sorted(entities, key=sort_key, reverse=reverse)
