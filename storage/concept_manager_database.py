"""
Database-aware Concept Manager for OntServe.

This version queries the actual ontology_entities table where ProEthica
ontology classes are stored in the populated database.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from .postgresql_storage import PostgreSQLStorage, StorageError

logger = logging.getLogger(__name__)


class DatabaseConceptManager:
    """
    Concept manager that queries ontology_entities table for ProEthica concepts.
    """
    
    def __init__(self, storage: PostgreSQLStorage):
        """Initialize database concept manager."""
        self.storage = storage
        logger.info("Database concept manager initialized")
    
    def get_entities_by_category(self, category: str, domain_id: str = "engineering-ethics", 
                                status: str = "approved") -> Dict[str, Any]:
        """
        Get ontology entities by category from the ontology_entities table.
        
        Args:
            category: Entity category (Role, Principle, Obligation, etc.)
            domain_id: Professional domain identifier (used to select ontology)
            status: Status filter (not used for ontology classes, kept for compatibility)
            
        Returns:
            Dictionary with entities and metadata
        """
        logger.info(f"Getting {category} entities from ontology_entities table")
        
        try:
            # Map domain to ontology names
            ontology_names = self._get_ontology_names_for_domain(domain_id)
            
            if not ontology_names:
                logger.warning(f"No ontologies found for domain: {domain_id}")
                return self._empty_response(category, domain_id, status)
            
            # Use proper ontological hierarchy via parent_uri relationships
            # This is semantically correct and uses actual subClassOf relationships
            if category in ['Principle', 'Role', 'State', 'Resource', 'Obligation', 
                          'Action', 'Event', 'Capability', 'Constraint']:
                
                # First, find the base class URI for this category
                base_uri_query = """
                    SELECT DISTINCT uri 
                    FROM ontology_entities 
                    WHERE label = %s 
                    AND entity_type = 'class'
                    AND ontology_id IN (
                        SELECT id FROM ontologies WHERE name = ANY(%s)
                    )
                    ORDER BY uri
                    LIMIT 1
                """
                
                base_uri_result = self.storage._execute_query(
                    base_uri_query,
                    (category, ontology_names),
                    fetch_one=True
                )
                
                if base_uri_result and base_uri_result['uri']:
                    base_uri = base_uri_result['uri']
                    
                    # Use recursive CTE to get all subclasses via parent_uri
                    query = """
                        WITH RECURSIVE category_hierarchy AS (
                            -- Base case: Get the category class itself
                            SELECT e.uri, e.label, e.comment, e.parent_uri, 
                                   o.name as ontology_name, o.id as ontology_id,
                                   0 as hierarchy_level
                            FROM ontology_entities e
                            JOIN ontologies o ON e.ontology_id = o.id
                            WHERE e.uri = %s
                            AND e.entity_type = 'class'
                            
                            UNION
                            
                            -- Recursive case: Get all subclasses
                            SELECT e.uri, e.label, e.comment, e.parent_uri,
                                   o.name as ontology_name, o.id as ontology_id,
                                   ch.hierarchy_level + 1
                            FROM ontology_entities e
                            JOIN ontologies o ON e.ontology_id = o.id
                            INNER JOIN category_hierarchy ch ON e.parent_uri = ch.uri
                            WHERE e.entity_type = 'class'
                            AND o.name = ANY(%s)
                        )
                        SELECT DISTINCT uri, label, comment, ontology_name, 
                               hierarchy_level as sort_order, ontology_id
                        FROM category_hierarchy
                        ORDER BY hierarchy_level, label
                    """
                    
                    results = self.storage._execute_query(
                        query,
                        (base_uri, ontology_names),
                        fetch_all=True
                    )
                else:
                    # Fallback to label matching if no base URI found
                    logger.warning(f"No base URI found for category {category}, using label matching")
                    query = """
                        SELECT DISTINCT e.uri, e.label, e.comment, o.name as ontology_name,
                            0 as sort_order, o.id as ontology_id
                        FROM ontology_entities e
                        JOIN ontologies o ON e.ontology_id = o.id
                        WHERE o.name = ANY(%s)
                        AND e.entity_type = 'class'
                        AND e.label = %s
                        ORDER BY e.label
                    """
                    
                    results = self.storage._execute_query(
                        query,
                        (ontology_names, category),
                        fetch_all=True
                    )
            else:
                # Broader matching for other categories
                query = """
                    SELECT e.uri, e.label, e.comment, o.name as ontology_name,
                        CASE 
                            WHEN e.label = %s THEN 0  -- Exact match first
                            WHEN e.label ILIKE %s THEN 1  -- Contains category
                            ELSE 2
                        END as sort_order,
                        o.id as ontology_id
                    FROM ontology_entities e
                    JOIN ontologies o ON e.ontology_id = o.id
                    WHERE o.name = ANY(%s)
                    AND e.entity_type = 'class'
                    AND (
                        e.label ILIKE %s
                        OR e.uri ILIKE %s
                    )
                    ORDER BY sort_order, e.label
                """
                
                # Create search patterns
                exact_category = category
                category_pattern = f'%{category}%'
                category_uri_pattern = f'%#{category}%'
                
                results = self.storage._execute_query(
                    query,
                    (exact_category, category_pattern, ontology_names, 
                     category_pattern, category_uri_pattern),
                    fetch_all=True
                )
            
            if not results:
                # Try to get the core category definitions from proethica-core
                logger.info(f"No specific {category} classes found, checking proethica-core")
                results = self._get_core_category_class(category)
            
            # Format results and track URIs to avoid duplicates
            entities = []
            seen_uris = set()
            
            for row in results:
                if row['uri'] not in seen_uris:
                    seen_uris.add(row['uri'])
                    entity = {
                        'id': row['uri'],
                        'uri': row['uri'],
                        'label': row['label'],
                        'semantic_label': row['label'],
                        'description': row['comment'] or f"A {category} in the {domain_id} domain",
                        'category': category,
                        'confidence_score': 1.0,  # Ontology classes have full confidence
                        'entity_type': 'class',
                        'source': row.get('ontology_name', 'proethica-core'),
                        'metadata': {
                            'source': 'ontology',
                            'ontology': row.get('ontology_name', 'proethica-core'),
                            'from_database': True
                        }
                    }
                    entities.append(entity)
            
            # If we found the main category class, also get its subclasses
            # Pass seen_uris to avoid duplicates
            if entities and category in ['Role', 'Principle', 'Obligation', 'Resource', 'State']:
                subclasses = self._get_subclasses_for_category(category, ontology_names, seen_uris)
                entities.extend(subclasses)
            
            return {
                'entities': entities,
                'category': category,
                'domain_id': domain_id,
                'status': 'ontology_class',  # These are ontology classes, not instances
                'total_count': len(entities),
                'source': 'ontology_entities_table'
            }
            
        except Exception as e:
            logger.error(f"Database error getting entities: {e}")
            return self._empty_response(category, domain_id, status)
    
    def _get_ontology_names_for_domain(self, domain_id: str) -> List[str]:
        """
        Get relevant ontology names for a domain.
        
        Args:
            domain_id: Domain identifier
            
        Returns:
            List of ontology names
        """
        # For engineering-ethics, use these core ontologies
        if domain_id == "engineering-ethics":
            return ['proethica-core', 'proethica-intermediate', 'engineering-ethics']
        
        # For other domains, try to find matching ontologies
        try:
            query = """
                SELECT DISTINCT o.name
                FROM ontologies o
                LEFT JOIN domains d ON o.domain_id = d.id
                WHERE d.name = %s OR o.name ILIKE %s
            """
            
            results = self.storage._execute_query(
                query,
                (domain_id, f'%{domain_id}%'),
                fetch_all=True
            )
            
            if results:
                return [r['name'] for r in results]
            
            # Default to core ontologies
            return ['proethica-core', 'proethica-intermediate']
            
        except Exception as e:
            logger.error(f"Error getting ontology names: {e}")
            return ['proethica-core', 'proethica-intermediate']
    
    def _get_core_category_class(self, category: str) -> List[Dict[str, Any]]:
        """
        Get the core category class from proethica-core ontology.
        
        Args:
            category: Category name (Role, Principle, etc.)
            
        Returns:
            List with the core category class if found
        """
        try:
            query = """
                SELECT e.uri, e.label, e.comment, o.name as ontology_name
                FROM ontology_entities e
                JOIN ontologies o ON e.ontology_id = o.id
                WHERE o.name = 'proethica-core'
                AND e.entity_type = 'class'
                AND e.label = %s
            """
            
            result = self.storage._execute_query(
                query,
                (category,),
                fetch_one=True
            )
            
            if result:
                return [result]
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting core category class: {e}")
            return []
    
    def _get_subclasses_for_category(self, category: str, ontology_names: List[str], seen_uris: set = None) -> List[Dict[str, Any]]:
        """
        Get subclasses of a category (e.g., ProfessionalRole as subclass of Role).
        
        Args:
            category: Category name
            ontology_names: List of ontology names to search
            seen_uris: Set of URIs already seen (to avoid duplicates)
            
        Returns:
            List of subclass entities
        """
        subclasses = []
        if seen_uris is None:
            seen_uris = set()  # Track URIs to avoid duplicates
        
        try:
            # Query for all subclasses in one go to avoid duplicates
            query = """
                SELECT DISTINCT e.uri, e.label, e.comment, o.name as ontology_name
                FROM ontology_entities e
                JOIN ontologies o ON e.ontology_id = o.id
                WHERE o.name = ANY(%s)
                AND e.entity_type = 'class'
                AND e.label != %s  -- Exclude the main category itself
                AND (
                    e.label ILIKE %s  -- Match Role in label
                    OR e.uri ILIKE %s  -- Match Role in URI
                )
                ORDER BY e.label
            """
            
            # Create search patterns for the category
            category_pattern = f'%{category}%'
            
            results = self.storage._execute_query(
                query,
                (ontology_names, category, category_pattern, category_pattern),
                fetch_all=True
            )
            
            for result in results:
                # Skip if we've already seen this URI
                if result['uri'] in seen_uris:
                    continue
                    
                seen_uris.add(result['uri'])
                
                entity = {
                    'id': result['uri'],
                    'uri': result['uri'],
                    'label': result['label'],
                    'semantic_label': result['label'],
                    'description': result['comment'] or f"A subclass of {category}",
                    'category': category,
                    'confidence_score': 1.0,
                    'entity_type': 'class',
                    'source': result['ontology_name'],
                    'is_subclass': True,
                    'parent_class': category,
                    'metadata': {
                        'source': 'ontology',
                        'ontology': result['ontology_name'],
                        'from_database': True,
                        'is_subclass_of': category
                    }
                }
                subclasses.append(entity)
            
        except Exception as e:
            logger.error(f"Error getting subclasses: {e}")
        
        return subclasses
    
    def get_domain_info(self, domain_id: str) -> Dict[str, Any]:
        """
        Get information about a professional domain.
        
        Args:
            domain_id: Domain identifier
            
        Returns:
            Domain information dictionary
        """
        try:
            query = """
                SELECT name, display_name, namespace_uri, description, metadata
                FROM domains
                WHERE name = %s AND is_active = true
            """
            
            result = self.storage._execute_query(query, (domain_id,), fetch_one=True)
            
            if result:
                # Get ontology count for this domain
                onto_query = """
                    SELECT COUNT(*) as count
                    FROM ontologies o
                    JOIN domains d ON o.domain_id = d.id
                    WHERE d.name = %s
                """
                onto_result = self.storage._execute_query(onto_query, (domain_id,), fetch_one=True)
                
                # Get entity count
                entity_query = """
                    SELECT COUNT(*) as count
                    FROM ontology_entities e
                    JOIN ontologies o ON e.ontology_id = o.id
                    JOIN domains d ON o.domain_id = d.id
                    WHERE d.name = %s
                """
                entity_result = self.storage._execute_query(entity_query, (domain_id,), fetch_one=True)
                
                return {
                    'domain_id': result['name'],
                    'display_name': result['display_name'],
                    'namespace_uri': result['namespace_uri'],
                    'description': result['description'],
                    'metadata': result['metadata'] or {},
                    'ontology_count': onto_result['count'] if onto_result else 0,
                    'entity_count': entity_result['count'] if entity_result else 0,
                    'status': 'active'
                }
            
            return {
                'error': f'Domain not found: {domain_id}',
                'domain_id': domain_id,
                'status': 'not_found'
            }
            
        except Exception as e:
            logger.error(f"Error getting domain info: {e}")
            return {
                'error': f'Failed to get domain info: {str(e)}',
                'domain_id': domain_id,
                'status': 'error'
            }
    
    def _empty_response(self, category: str, domain_id: str, status: str) -> Dict[str, Any]:
        """
        Generate an empty response structure.
        
        Args:
            category: Category requested
            domain_id: Domain identifier
            status: Status filter
            
        Returns:
            Empty response dictionary
        """
        return {
            'entities': [],
            'category': category,
            'domain_id': domain_id,
            'status': status,
            'total_count': 0,
            'source': 'ontology_entities_table'
        }
    
    # Methods for compatibility with the concept manager interface
    
    def submit_candidate_concept(self, concept: Dict[str, Any], domain_id: str, submitted_by: str) -> Dict[str, Any]:
        """Stub for interface compatibility."""
        return {'error': 'This manager only handles ontology queries, not candidate submission'}
    
    def update_concept_status(self, concept_id: str, status: str, user: str, reason: str = "") -> Dict[str, Any]:
        """Stub for interface compatibility."""
        return {'error': 'This manager only handles ontology queries, not status updates'}
    
    def get_candidate_concepts(self, domain_id: str, category: Optional[str] = None, status: str = "candidate") -> Dict[str, Any]:
        """Stub for interface compatibility."""
        return {'error': 'This manager only handles ontology queries, not candidate concepts'}
