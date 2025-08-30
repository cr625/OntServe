"""
Enhanced Concept Manager for OntServe with Ontology Class Support.

This enhanced version adds support for querying ontology class definitions
(like ProfessionalRole, ParticipantRole) in addition to instance management.
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from uuid import uuid4

from psycopg2.extras import Json
from .postgresql_storage import PostgreSQLStorage, StorageError
from .concept_manager import ConceptManager

logger = logging.getLogger(__name__)


class EnhancedConceptManager(ConceptManager):
    """
    Enhanced manager that supports both ontology class queries and instance management.
    
    Extends the base ConceptManager to add ontology class parsing capabilities
    while preserving all instance management functionality.
    """
    
    def __init__(self, storage: PostgreSQLStorage):
        """Initialize enhanced concept manager."""
        super().__init__(storage)
        self.ontology_cache = {}  # Cache parsed ontology classes
        logger.info("Enhanced concept manager initialized with ontology class support")
    
    def get_entities_by_category(self, category: str, domain_id: str = "engineering-ethics",
                                status: str = "approved", include_classes: bool = True) -> Dict[str, Any]:
        """
        Get entities by category - returns both ontology classes AND instances.
        
        This enhanced version first checks for ontology class definitions,
        then falls back to instance queries for populated data.
        
        Args:
            category: Entity category (Role, Principle, etc.)
            domain_id: Professional domain identifier
            status: Status filter for instances
            include_classes: Whether to include ontology class definitions
            
        Returns:
            Dictionary with entities (classes and/or instances) and metadata
        """
        entities = []
        
        # First, try to get ontology class definitions if requested
        if include_classes:
            class_entities = self._get_ontology_classes_by_category(category, domain_id)
            entities.extend(class_entities)
        
        # Then get instances from the database (for future case-based queries)
        # This preserves the original logic for when we have actual instances
        instance_result = super().get_entities_by_category(category, domain_id, status)
        
        # If we have instances, add them to the results
        if instance_result.get('entities'):
            # Mark instances to distinguish from classes
            for instance in instance_result['entities']:
                instance['entity_type'] = 'instance'
            entities.extend(instance_result['entities'])
        
        # If no classes or instances found, return the class definitions as guidance
        if not entities and include_classes:
            # Try to get the category definition itself
            category_def = self._get_category_definition(category, domain_id)
            if category_def:
                entities.append(category_def)
        
        return {
            'entities': entities,
            'category': category,
            'domain_id': domain_id,
            'status': status if not include_classes else 'mixed',
            'total_count': len(entities),
            'has_classes': any(e.get('entity_type') == 'class' for e in entities),
            'has_instances': any(e.get('entity_type') == 'instance' for e in entities)
        }
    
    def _get_ontology_classes_by_category(self, category: str, domain_id: str) -> List[Dict[str, Any]]:
        """
        Parse ontology to get class definitions for a category.
        
        Args:
            category: Category to query (e.g., "Role", "Principle")
            domain_id: Domain identifier
            
        Returns:
            List of class definition dictionaries
        """
        try:
            # Get the proethica-intermediate ontology content
            ontology_content = self._get_ontology_content("proethica-intermediate", domain_id)
            if not ontology_content:
                return []
            
            # Parse classes from the ontology
            classes = self._parse_ontology_classes(ontology_content, category)
            
            # Format as entity results
            entities = []
            for cls_uri, cls_data in classes.items():
                entity = {
                    'id': cls_uri,
                    'uri': cls_uri,
                    'label': cls_data.get('label', cls_uri.split('#')[-1]),
                    'semantic_label': cls_data.get('label', ''),
                    'description': cls_data.get('comment', ''),
                    'category': category,
                    'entity_type': 'class',  # Mark as ontology class, not instance
                    'is_subclass_of': cls_data.get('subclass_of', []),
                    'metadata': {
                        'source': 'ontology',
                        'ontology': 'proethica-intermediate',
                        'class_type': 'definition'
                    }
                }
                entities.append(entity)
            
            return entities
            
        except Exception as e:
            logger.error(f"Failed to get ontology classes: {e}")
            return []
    
    def _get_category_definition(self, category: str, domain_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the definition of the category itself from the ontology.
        
        Args:
            category: Category name (e.g., "Role")
            domain_id: Domain identifier
            
        Returns:
            Category definition dictionary or None
        """
        try:
            ontology_content = self._get_ontology_content("proethica-intermediate", domain_id)
            if not ontology_content:
                return None
            
            # Look for the category class definition
            category_pattern = rf':({category})\s+rdf:type\s+owl:Class\s*;(.*?)(?=\n\n|\n:[A-Z]|\Z)'
            match = re.search(category_pattern, ontology_content, re.DOTALL)
            
            if match:
                class_block = match.group(2)
                
                # Extract label and comment
                label_match = re.search(r'rdfs:label\s+"([^"]+)"', class_block)
                comment_match = re.search(r'rdfs:comment\s+"([^"]+)"', class_block)
                
                return {
                    'id': f'http://proethica.org/ontology/intermediate#{category}',
                    'uri': f'http://proethica.org/ontology/intermediate#{category}',
                    'label': label_match.group(1) if label_match else category,
                    'semantic_label': label_match.group(1) if label_match else category,
                    'description': comment_match.group(1) if comment_match else f"Category definition for {category}",
                    'category': 'CategoryDefinition',
                    'entity_type': 'class',
                    'metadata': {
                        'source': 'ontology',
                        'ontology': 'proethica-intermediate',
                        'is_category_root': True
                    }
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get category definition: {e}")
            return None
    
    def _get_ontology_content(self, ontology_name: str, domain_id: str) -> Optional[str]:
        """
        Retrieve ontology content from the database.
        
        Args:
            ontology_name: Name of the ontology
            domain_id: Domain identifier
            
        Returns:
            Ontology content as string or None
        """
        # Check cache first
        cache_key = f"{domain_id}:{ontology_name}"
        if cache_key in self.ontology_cache:
            return self.ontology_cache[cache_key]
        
        try:
            # Query for the ontology content
            query = """
                SELECT ov.content
                FROM ontology_versions ov
                JOIN ontologies o ON ov.ontology_id = o.id
                JOIN domains d ON o.domain_id = d.id
                WHERE o.name = %s AND d.name = %s AND ov.is_current = true
            """
            
            result = self.storage._execute_query(query, (ontology_name, domain_id), fetch_one=True)
            
            if result and result['content']:
                content = result['content']
                # Cache the content
                self.ontology_cache[cache_key] = content
                return content
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get ontology content: {e}")
            return None
    
    def _parse_ontology_classes(self, content: str, category: str) -> Dict[str, Dict[str, Any]]:
        """
        Parse ontology TTL content to extract class definitions.
        
        Args:
            content: TTL ontology content
            category: Category to filter (e.g., "Role")
            
        Returns:
            Dictionary of class URIs to class data
        """
        classes = {}
        
        try:
            # Pattern to find subclasses of the category
            # Looking for patterns like:
            # :ProfessionalRole rdf:type owl:Class ;
            #     rdfs:subClassOf :Role ;
            
            if category == "Role":
                # Special handling for Role - get its subclasses
                role_subclasses = [
                    ('ProfessionalRole', 'Professional Role', 
                     'A role within a profession that entails recognized ends/goals of practice and obligations'),
                    ('ParticipantRole', 'Participant Role',
                     'A role of an involved party or stakeholder that does not itself establish professional obligations'),
                    ('EngineerRole', 'Engineer Role',
                     'A professional role involving engineering practice and responsibilities'),
                    ('StakeholderRole', 'Stakeholder Role',
                     'A participant role borne by stakeholders such as Clients, Employers, and the Public')
                ]
                
                for class_name, label, description in role_subclasses:
                    # Check if this class exists in the ontology
                    if f':{class_name}' in content:
                        uri = f'http://proethica.org/ontology/intermediate#{class_name}'
                        
                        # Extract actual description from ontology if available
                        pattern = rf':{class_name}\s+.*?rdfs:comment\s+"([^"]+)"'
                        match = re.search(pattern, content, re.DOTALL)
                        if match:
                            description = match.group(1)
                        
                        classes[uri] = {
                            'label': label,
                            'comment': description,
                            'subclass_of': [f'http://proethica.org/ontology/intermediate#{category}']
                        }
            
            elif category == "Principle":
                # Get principle-related classes
                principle_classes = [
                    ('EthicalPrinciple', 'Ethical Principle', 'Legacy synonym for Principle'),
                    ('EthicalCode', 'Ethical Code', 'A standard that establishes ethical principles and professional conduct requirements')
                ]
                
                for class_name, label, description in principle_classes:
                    if f':{class_name}' in content:
                        uri = f'http://proethica.org/ontology/intermediate#{class_name}'
                        classes[uri] = {
                            'label': label,
                            'comment': description,
                            'subclass_of': [f'http://proethica.org/ontology/intermediate#{category}']
                        }
            
            elif category == "Obligation":
                # Get obligation-related classes
                obligation_classes = [
                    ('ProfessionalObligation', 'Professional Obligation', 
                     'A duty or responsibility arising from professional role or standards'),
                    ('Permission', 'Permission',
                     'A normative allowance indicating that an action or state is permitted'),
                    ('Prohibition', 'Prohibition',
                     'A normative restriction indicating that an action or state is disallowed')
                ]
                
                for class_name, label, description in obligation_classes:
                    if f':{class_name}' in content:
                        uri = f'http://proethica.org/ontology/intermediate#{class_name}'
                        classes[uri] = {
                            'label': label,
                            'comment': description,
                            'subclass_of': [f'http://proethica.org/ontology/intermediate#{category}']
                        }
            
            # Add more category-specific parsing as needed
            
        except Exception as e:
            logger.error(f"Failed to parse ontology classes: {e}")
        
        return classes
    
    def get_ontology_classes(self, domain_id: str = "engineering-ethics") -> Dict[str, Any]:
        """
        Get all available ontology classes grouped by category.
        
        Args:
            domain_id: Domain identifier
            
        Returns:
            Dictionary with all ontology classes grouped by category
        """
        categories = ['Role', 'Principle', 'Obligation', 'State', 'Resource', 
                     'Action', 'Event', 'Capability', 'Constraint']
        
        result = {
            'domain_id': domain_id,
            'categories': {}
        }
        
        for category in categories:
            classes = self._get_ontology_classes_by_category(category, domain_id)
            if classes:
                result['categories'][category] = classes
        
        return result


# Factory function to get the enhanced manager
def get_enhanced_concept_manager(storage: PostgreSQLStorage) -> EnhancedConceptManager:
    """
    Factory function to create an enhanced concept manager.
    
    Args:
        storage: PostgreSQL storage backend
        
    Returns:
        Enhanced concept manager instance
    """
    return EnhancedConceptManager(storage)
