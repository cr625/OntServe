"""
Entity Tools Module for OntServe MCP Server.

Provides tools for retrieving, managing, and querying ontology entities
with support for categories, domains, and comprehensive entity definitions.
"""

from typing import Dict, List, Any
import logging

from .base_tool import DatabaseRequiredTool, CachedTool

logger = logging.getLogger(__name__)


class GetEntitiesByCategory(DatabaseRequiredTool):
    """Retrieve ontology entities by category from a professional domain."""
    
    name = "get_entities_by_category"
    description = "Retrieve ontology entities by category from a professional domain"
    schema = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Entity category (Role, Principle, Obligation, etc.)",
                "enum": ["Role", "Principle", "Obligation", "State", "Resource", 
                        "Action", "Event", "Capability", "Constraint"]
            },
            "domain_id": {
                "type": "string", 
                "description": "Professional domain identifier",
                "default": "engineering-ethics"
            },
            "status": {
                "type": "string",
                "description": "Concept status filter",
                "enum": ["candidate", "approved", "deprecated"],
                "default": "approved"
            }
        },
        "required": ["category"]
    }
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute entity retrieval by category."""
        category = arguments.get("category")
        domain_id = arguments.get("domain_id", "engineering-ethics")
        status = arguments.get("status", "approved")
        
        logger.debug(f"Getting {category} entities from domain {domain_id} with status {status}")
        
        try:
            # Use concept manager to get entities
            result = self.concept_manager.get_entities_by_category(category, domain_id, status)
            
            # Add execution metadata
            result["query_parameters"] = {
                "category": category,
                "domain_id": domain_id,
                "status": status
            }
            
            return self.format_success_response(result)
            
        except Exception as e:
            return self.format_error_response(
                f"Failed to retrieve {category} entities: {str(e)}",
                error_code="ENTITY_RETRIEVAL_FAILED"
            )


class GetEntityDefinition(CachedTool):
    """Get comprehensive entity definition with relationships and semantic context."""
    
    name = "get_entity_definition"
    description = "Get comprehensive entity definition with relationships, hierarchy, and semantic context"
    schema = {
        "type": "object",
        "properties": {
            "entity_uri": {
                "type": "string",
                "description": "Full URI of the entity to describe"
            },
            "include_relationships": {
                "type": "boolean",
                "default": True,
                "description": "Include incoming and outgoing relationships"
            },
            "include_hierarchy": {
                "type": "boolean", 
                "default": True,
                "description": "Include superclass/subclass hierarchy"
            },
            "include_properties": {
                "type": "boolean",
                "default": True, 
                "description": "Include property definitions and constraints"
            },
            "reasoning_depth": {
                "type": "integer",
                "default": 2,
                "minimum": 1,
                "maximum": 5,
                "description": "Levels of relationship traversal (1-5)"
            },
            "include_examples": {
                "type": "boolean",
                "default": False,
                "description": "Include usage examples if available"
            },
            "domain_id": {
                "type": "string",
                "default": "engineering-ethics",
                "description": "Professional domain context"
            }
        },
        "required": ["entity_uri"]
    }
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute comprehensive entity definition lookup."""
        entity_uri = arguments.get("entity_uri")
        include_relationships = arguments.get("include_relationships", True)
        include_hierarchy = arguments.get("include_hierarchy", True)
        include_properties = arguments.get("include_properties", True)
        reasoning_depth = arguments.get("reasoning_depth", 2)
        include_examples = arguments.get("include_examples", False)
        domain_id = arguments.get("domain_id", "engineering-ethics")
        
        logger.debug(f"Getting definition for entity: {entity_uri}")
        
        try:
            # Get basic entity information
            entity_data = await self._get_basic_entity_info(entity_uri, domain_id)
            if not entity_data:
                return self.format_error_response(
                    f"Entity not found: {entity_uri}",
                    error_code="ENTITY_NOT_FOUND"
                )
            
            # Build comprehensive definition
            definition = {
                "entity": entity_data,
                "query_parameters": {
                    "entity_uri": entity_uri,
                    "domain_id": domain_id,
                    "reasoning_depth": reasoning_depth
                }
            }
            
            # Add optional components
            if include_hierarchy:
                definition["hierarchy"] = await self._get_entity_hierarchy(
                    entity_uri, domain_id, reasoning_depth
                )
            
            if include_relationships:
                definition["relationships"] = await self._get_entity_relationships(
                    entity_uri, domain_id, reasoning_depth
                )
            
            if include_properties:
                definition["properties"] = await self._get_entity_properties(
                    entity_uri, domain_id
                )
            
            if include_examples:
                definition["examples"] = await self._get_entity_examples(
                    entity_uri, domain_id
                )
            
            return self.format_success_response(definition)
            
        except Exception as e:
            return self.format_error_response(
                f"Failed to get entity definition: {str(e)}",
                error_code="DEFINITION_LOOKUP_FAILED"
            )
    
    async def _get_basic_entity_info(self, entity_uri: str, domain_id: str) -> Dict[str, Any]:
        """Get basic entity information from database."""
        try:
            # Query entity from database
            query = """
                SELECT e.uri, e.label, e.entity_type, e.definition, e.properties,
                       o.name as ontology_name, o.base_uri as ontology_namespace
                FROM ontology_entities e
                JOIN ontologies o ON e.ontology_id = o.id
                WHERE e.uri = %s
                LIMIT 1
            """
            
            result = self.storage._execute_query(query, (entity_uri,), fetch_one=True)
            
            if not result:
                return None
            
            return {
                "uri": result[0],
                "label": result[1],
                "type": result[2],
                "definition": result[3],
                "properties": result[4] or {},
                "ontology_name": result[5],
                "namespace": result[6]
            }
            
        except Exception as e:
            logger.error(f"Error getting basic entity info for {entity_uri}: {e}")
            return None
    
    async def _get_entity_hierarchy(self, entity_uri: str, domain_id: str, depth: int) -> Dict[str, Any]:
        """Get entity hierarchy information."""
        try:
            # Get superclasses (parents)
            superclass_query = """
                SELECT e.uri, e.label, e.entity_type
                FROM ontology_entities e
                WHERE e.uri IN (
                    SELECT parent_uri FROM ontology_entities 
                    WHERE uri = %s AND parent_uri IS NOT NULL
                )
                ORDER BY e.label
            """
            
            superclasses = self.storage._execute_query(superclass_query, (entity_uri,), fetch_all=True)
            
            # Get subclasses (children)
            subclass_query = """
                SELECT e.uri, e.label, e.entity_type
                FROM ontology_entities e
                WHERE e.parent_uri = %s
                ORDER BY e.label
            """
            
            subclasses = self.storage._execute_query(subclass_query, (entity_uri,), fetch_all=True)
            
            return {
                "superClasses": [
                    {"uri": row[0], "label": row[1], "type": row[2]}
                    for row in (superclasses or [])
                ],
                "subClasses": [
                    {"uri": row[0], "label": row[1], "type": row[2]}
                    for row in (subclasses or [])
                ],
                "depth": depth
            }
            
        except Exception as e:
            logger.error(f"Error getting hierarchy for {entity_uri}: {e}")
            return {"superClasses": [], "subClasses": [], "depth": depth}
    
    async def _get_entity_relationships(self, entity_uri: str, domain_id: str, depth: int) -> Dict[str, Any]:
        """Get entity relationships."""
        try:
            # This would be implemented with proper relationship queries
            # For now, return basic structure
            return {
                "incoming": [],
                "outgoing": [],
                "depth": depth
            }
            
        except Exception as e:
            logger.error(f"Error getting relationships for {entity_uri}: {e}")
            return {"incoming": [], "outgoing": [], "depth": depth}
    
    async def _get_entity_properties(self, entity_uri: str, domain_id: str) -> Dict[str, Any]:
        """Get entity property information."""
        try:
            # Basic property structure
            return {
                "dataProperties": [],
                "objectProperties": []
            }
            
        except Exception as e:
            logger.error(f"Error getting properties for {entity_uri}: {e}")
            return {"dataProperties": [], "objectProperties": []}
    
    async def _get_entity_examples(self, entity_uri: str, domain_id: str) -> List[str]:
        """Get usage examples for entity."""
        try:
            # This would query examples from the database
            return []
            
        except Exception as e:
            logger.error(f"Error getting examples for {entity_uri}: {e}")
            return []


class GetDomainInfo(DatabaseRequiredTool):
    """Get information about a professional domain."""
    
    name = "get_domain_info"
    description = "Get information about a professional domain"
    schema = {
        "type": "object",
        "properties": {
            "domain_id": {
                "type": "string",
                "description": "Professional domain identifier",
                "default": "engineering-ethics"
            }
        },
        "required": ["domain_id"]
    }
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute domain info retrieval."""
        domain_id = arguments.get("domain_id", "engineering-ethics")
        
        logger.debug(f"Getting domain info for: {domain_id}")
        
        try:
            # Use concept manager to get domain info
            result = self.concept_manager.get_domain_info(domain_id)
            return self.format_success_response(result)
            
        except Exception as e:
            return self.format_error_response(
                f"Failed to get domain info for {domain_id}: {str(e)}",
                error_code="DOMAIN_INFO_FAILED"
            )