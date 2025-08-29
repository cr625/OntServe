"""
Query Tools Module for OntServe MCP Server.

Provides SPARQL query execution and semantic search capabilities
with caching, reasoning support, and multiple output formats.
"""

from typing import Dict, List, Any, Optional
import logging
import json
import time

from .base_tool import CachedTool

logger = logging.getLogger(__name__)


class SPARQLQuery(CachedTool):
    """Execute SPARQL queries with optional reasoning and multiple output formats."""
    
    name = "sparql_query"
    description = "Execute SPARQL queries with optional reasoning and multiple output formats"
    schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "SPARQL SELECT, CONSTRUCT, ASK, or DESCRIBE query"
            },
            "domain_id": {
                "type": "string",
                "default": "engineering-ethics",
                "description": "Professional domain to query"
            },
            "reasoning": {
                "type": "boolean", 
                "default": False,
                "description": "Enable OWL reasoning and inference"
            },
            "format": {
                "type": "string",
                "enum": ["json", "csv", "xml", "turtle", "n3"],
                "default": "json",
                "description": "Output format for results"
            },
            "limit": {
                "type": "integer",
                "default": 100,
                "minimum": 1,
                "maximum": 10000,
                "description": "Maximum number of results to return"
            },
            "timeout": {
                "type": "integer",
                "default": 30,
                "minimum": 1,
                "maximum": 300,
                "description": "Query execution timeout in seconds"
            }
        },
        "required": ["query"]
    }
    
    def __init__(self, storage_backend=None, concept_manager=None):
        super().__init__(storage_backend, concept_manager, cache_ttl=300)  # 5-minute cache
        self._sparql_engine = None
    
    def _get_sparql_engine(self):
        """Lazy load SPARQL engine."""
        if not self._sparql_engine:
            try:
                from ..engines.sparql_engine import SPARQLEngine
                self._sparql_engine = SPARQLEngine(self.storage)
            except ImportError:
                # Fallback to basic implementation for now
                logger.warning("SPARQLEngine not available, using fallback implementation")
                self._sparql_engine = self._create_fallback_engine()
        return self._sparql_engine
    
    def _create_fallback_engine(self):
        """Create a basic fallback SPARQL engine."""
        class FallbackSPARQLEngine:
            def __init__(self, storage):
                self.storage = storage
            
            async def execute_query(self, query: str, domain_id: str, 
                                  reasoning: bool = False, format_type: str = "json",
                                  limit: int = 100, timeout: int = 30) -> Dict[str, Any]:
                """Fallback SPARQL implementation - will be replaced with real engine."""
                logger.warning("Using fallback SPARQL implementation")
                
                # For now, return structured mock data that indicates the query was received
                return {
                    "bindings": [],
                    "query": query,
                    "domain_id": domain_id,
                    "reasoning_enabled": reasoning,
                    "format": format_type,
                    "limit": limit,
                    "execution_time_ms": 45,
                    "result_count": 0,
                    "status": "fallback_implementation",
                    "message": "SPARQL engine not yet implemented - this is a structured placeholder response"
                }
        
        return FallbackSPARQLEngine(self.storage)
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute SPARQL query with caching and validation."""
        query = arguments.get("query")
        domain_id = arguments.get("domain_id", "engineering-ethics")
        reasoning = arguments.get("reasoning", False)
        format_type = arguments.get("format", "json")
        limit = arguments.get("limit", 100)
        timeout = arguments.get("timeout", 30)
        
        logger.debug(f"Executing SPARQL query on domain {domain_id}: {query[:100]}...")
        
        try:
            # Basic query validation
            validation_result = self._validate_sparql_query(query)
            if not validation_result["valid"]:
                return self.format_error_response(
                    f"Invalid SPARQL query: {validation_result['error']}",
                    error_code="INVALID_SPARQL"
                )
            
            # Get SPARQL engine
            engine = self._get_sparql_engine()
            
            # Execute query with timing
            start_time = time.time()
            result = await engine.execute_query(
                query=query,
                domain_id=domain_id,
                reasoning=reasoning,
                format_type=format_type,
                limit=limit,
                timeout=timeout
            )
            execution_time = (time.time() - start_time) * 1000  # Convert to ms
            
            # Add execution metadata
            result["execution_metadata"] = {
                "execution_time_ms": round(execution_time, 2),
                "query_length": len(query),
                "reasoning_enabled": reasoning,
                "format": format_type,
                "domain_id": domain_id,
                "cache_hit": False  # Will be set by CachedTool if from cache
            }
            
            return self.format_success_response(result)
            
        except Exception as e:
            return self.format_error_response(
                f"SPARQL query execution failed: {str(e)}",
                error_code="SPARQL_EXECUTION_FAILED"
            )
    
    def _validate_sparql_query(self, query: str) -> Dict[str, Any]:
        """Basic SPARQL query validation."""
        try:
            query_upper = query.upper().strip()
            
            # Check for basic SPARQL keywords
            valid_starts = ["SELECT", "CONSTRUCT", "ASK", "DESCRIBE", "INSERT", "DELETE"]
            if not any(query_upper.startswith(keyword) for keyword in valid_starts):
                return {
                    "valid": False,
                    "error": "Query must start with a valid SPARQL keyword (SELECT, CONSTRUCT, ASK, DESCRIBE, INSERT, DELETE)"
                }
            
            # Check for obvious injection attempts (basic security)
            suspicious_patterns = ["DROP", "CREATE", "ALTER", "TRUNCATE", "DELETE FROM"]
            for pattern in suspicious_patterns:
                if pattern in query_upper:
                    return {
                        "valid": False,
                        "error": f"Query contains potentially dangerous keyword: {pattern}"
                    }
            
            # Basic bracket matching
            if query.count("{") != query.count("}"):
                return {
                    "valid": False,
                    "error": "Mismatched curly braces in query"
                }
            
            return {"valid": True, "error": None}
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"Query validation error: {str(e)}"
            }


class FindRelatedEntities(CachedTool):
    """Find semantically related entities using vector similarity search."""
    
    name = "find_related_entities"
    description = "Find semantically related entities using vector similarity search"
    schema = {
        "type": "object",
        "properties": {
            "query_text": {
                "type": "string",
                "description": "Text description to find similar entities for"
            },
            "entity_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by entity types (optional)",
                "default": []
            },
            "similarity_threshold": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.7,
                "description": "Minimum cosine similarity score"
            },
            "max_results": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
                "description": "Maximum number of results to return"
            },
            "domain_id": {
                "type": "string",
                "default": "engineering-ethics",
                "description": "Professional domain to search within"
            },
            "include_scores": {
                "type": "boolean",
                "default": True,
                "description": "Include similarity scores in results"
            }
        },
        "required": ["query_text"]
    }
    
    def __init__(self, storage_backend=None, concept_manager=None):
        super().__init__(storage_backend, concept_manager, cache_ttl=600)  # 10-minute cache
        self._vector_engine = None
    
    def _get_vector_engine(self):
        """Lazy load vector search engine."""
        if not self._vector_engine:
            try:
                from ..engines.vector_engine import VectorSearchEngine
                self._vector_engine = VectorSearchEngine(self.storage)
            except ImportError:
                logger.warning("VectorSearchEngine not available, using fallback")
                self._vector_engine = self._create_fallback_vector_engine()
        return self._vector_engine
    
    def _create_fallback_vector_engine(self):
        """Create fallback vector search engine."""
        class FallbackVectorEngine:
            def __init__(self, storage):
                self.storage = storage
            
            async def find_similar_entities(self, query_text: str, **kwargs) -> Dict[str, Any]:
                """Fallback vector search - returns empty results for now."""
                return {
                    "similar_entities": [],
                    "query_text": query_text,
                    "total_found": 0,
                    "search_parameters": kwargs,
                    "status": "fallback_implementation",
                    "message": "Vector search engine not yet implemented"
                }
        
        return FallbackVectorEngine(self.storage)
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute vector similarity search."""
        query_text = arguments.get("query_text")
        entity_types = arguments.get("entity_types", [])
        similarity_threshold = arguments.get("similarity_threshold", 0.7)
        max_results = arguments.get("max_results", 10)
        domain_id = arguments.get("domain_id", "engineering-ethics")
        include_scores = arguments.get("include_scores", True)
        
        logger.debug(f"Finding entities similar to: '{query_text}' in domain {domain_id}")
        
        try:
            # Get vector search engine
            engine = self._get_vector_engine()
            
            # Execute similarity search
            result = await engine.find_similar_entities(
                query_text=query_text,
                entity_types=entity_types,
                similarity_threshold=similarity_threshold,
                max_results=max_results,
                domain_id=domain_id,
                include_scores=include_scores
            )
            
            # Add search metadata
            result["search_metadata"] = {
                "query_text": query_text,
                "domain_id": domain_id,
                "similarity_threshold": similarity_threshold,
                "max_results": max_results,
                "entity_types_filter": entity_types,
                "include_scores": include_scores
            }
            
            return self.format_success_response(result)
            
        except Exception as e:
            return self.format_error_response(
                f"Vector similarity search failed: {str(e)}",
                error_code="VECTOR_SEARCH_FAILED"
            )


class NaturalLanguageQuery(CachedTool):
    """Convert natural language questions to SPARQL queries and execute them."""
    
    name = "natural_language_query"
    description = "Convert natural language questions to SPARQL queries and execute them"
    schema = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string", 
                "description": "Natural language question about the ontology"
            },
            "context_entities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Entity URIs to provide query context",
                "default": []
            },
            "domain_id": {
                "type": "string",
                "default": "engineering-ethics",
                "description": "Professional domain context"
            },
            "explain_query": {
                "type": "boolean",
                "default": True,
                "description": "Include generated SPARQL query in response"
            },
            "reasoning": {
                "type": "boolean",
                "default": False,
                "description": "Apply reasoning to query results"
            },
            "max_results": {
                "type": "integer",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
                "description": "Maximum results to return"
            }
        },
        "required": ["question"]
    }
    
    def __init__(self, storage_backend=None, concept_manager=None):
        super().__init__(storage_backend, concept_manager, cache_ttl=900)  # 15-minute cache
        self._nl_engine = None
    
    def _get_nl_engine(self):
        """Lazy load natural language processing engine."""
        if not self._nl_engine:
            try:
                from ..engines.nlp_engine import NLPEngine
                self._nl_engine = NLPEngine(self.storage)
            except ImportError:
                logger.warning("NLPEngine not available, using fallback")
                self._nl_engine = self._create_fallback_nl_engine()
        return self._nl_engine
    
    def _create_fallback_nl_engine(self):
        """Create fallback NL processing engine."""
        class FallbackNLEngine:
            def __init__(self, storage):
                self.storage = storage
            
            async def convert_to_sparql(self, question: str, **kwargs) -> Dict[str, Any]:
                """Fallback NL to SPARQL conversion."""
                return {
                    "sparql_query": "# Generated SPARQL query would appear here",
                    "question": question,
                    "confidence": 0.0,
                    "query_type": "unknown",
                    "generated_explanation": "Natural language to SPARQL conversion not yet implemented",
                    "status": "fallback_implementation"
                }
            
            async def execute_nl_query(self, question: str, **kwargs) -> Dict[str, Any]:
                """Fallback NL query execution."""
                conversion_result = await self.convert_to_sparql(question, **kwargs)
                
                return {
                    "question": question,
                    "sparql_query": conversion_result["sparql_query"],
                    "results": [],
                    "result_count": 0,
                    "confidence": conversion_result["confidence"],
                    "explanation": conversion_result["generated_explanation"],
                    "status": "fallback_implementation"
                }
        
        return FallbackNLEngine(self.storage)
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute natural language query conversion and execution."""
        question = arguments.get("question")
        context_entities = arguments.get("context_entities", [])
        domain_id = arguments.get("domain_id", "engineering-ethics")
        explain_query = arguments.get("explain_query", True)
        reasoning = arguments.get("reasoning", False)
        max_results = arguments.get("max_results", 20)
        
        logger.debug(f"Processing natural language query: '{question}' in domain {domain_id}")
        
        try:
            # Get NLP engine
            engine = self._get_nl_engine()
            
            # Execute natural language query
            result = await engine.execute_nl_query(
                question=question,
                context_entities=context_entities,
                domain_id=domain_id,
                reasoning=reasoning,
                max_results=max_results
            )
            
            # Add/remove SPARQL query based on explain_query setting
            if not explain_query and "sparql_query" in result:
                result["sparql_query_available"] = True
                del result["sparql_query"]
            
            # Add processing metadata
            result["processing_metadata"] = {
                "question": question,
                "domain_id": domain_id,
                "context_entities_count": len(context_entities),
                "explain_query": explain_query,
                "reasoning_enabled": reasoning,
                "max_results": max_results
            }
            
            return self.format_success_response(result)
            
        except Exception as e:
            return self.format_error_response(
                f"Natural language query processing failed: {str(e)}",
                error_code="NL_QUERY_FAILED"
            )