"""
Base tool interface for OntServe MCP tools.

Provides common interface and utilities for all MCP tools with validation,
error handling, and consistent response formatting.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import json
import logging
import jsonschema

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """Base class for all MCP tools."""
    
    # Subclasses must define these
    name: str = None
    description: str = None
    schema: Dict[str, Any] = None
    
    def __init__(self, storage_backend=None, concept_manager=None):
        """
        Initialize base tool.
        
        Args:
            storage_backend: PostgreSQL storage backend
            concept_manager: Concept management instance
        """
        self.storage = storage_backend
        self.concept_manager = concept_manager
        
        # Validate required attributes
        if not self.name:
            raise ValueError(f"Tool {self.__class__.__name__} must define 'name'")
        if not self.description:
            raise ValueError(f"Tool {self.__class__.__name__} must define 'description'")
        if not self.schema:
            raise ValueError(f"Tool {self.__class__.__name__} must define 'schema'")
        
        logger.debug(f"Initialized tool: {self.name}")
    
    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the tool with given arguments.
        
        Args:
            arguments: Tool arguments validated against schema
            
        Returns:
            Tool execution result dictionary
        """
        pass
    
    def validate_arguments(self, arguments: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate arguments against tool schema.
        
        Args:
            arguments: Arguments to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            jsonschema.validate(arguments, self.schema)
            return True, None
        except jsonschema.ValidationError as e:
            return False, f"Schema validation failed: {e.message}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    async def handle_request(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle MCP tool request with validation and error handling.
        
        Args:
            arguments: Tool arguments from MCP request
            
        Returns:
            Tool execution result with error handling
        """
        try:
            # Validate arguments
            is_valid, error_msg = self.validate_arguments(arguments)
            if not is_valid:
                logger.warning(f"Tool '{self.name}' validation failed: {error_msg}")
                return {
                    "success": False,
                    "error": f"Invalid arguments: {error_msg}",
                    "tool": self.name
                }
            
            # Execute tool
            logger.debug(f"Executing tool '{self.name}' with args: {arguments}")
            result = await self.execute(arguments)
            
            # Ensure result has success indicator
            if "success" not in result:
                result["success"] = True
            
            logger.debug(f"Tool '{self.name}' executed successfully")
            return result
            
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(f"Error in tool '{self.name}': {error_msg}", exc_info=True)
            return {
                "success": False,
                "error": error_msg,
                "tool": self.name
            }
    
    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get MCP tool definition for list_tools response.
        
        Returns:
            Tool definition dictionary for MCP protocol
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.schema
        }
    
    def format_success_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format a successful response with consistent structure."""
        return {
            "success": True,
            "tool": self.name,
            **data
        }
    
    def format_error_response(self, error_message: str, 
                            error_code: Optional[str] = None) -> Dict[str, Any]:
        """Format an error response with consistent structure."""
        response = {
            "success": False,
            "error": error_message,
            "tool": self.name
        }
        if error_code:
            response["error_code"] = error_code
        return response


class DatabaseRequiredTool(BaseTool):
    """Base tool that requires database connectivity."""
    
    def __init__(self, storage_backend=None, concept_manager=None):
        super().__init__(storage_backend, concept_manager)
        
        if not self.storage:
            raise ValueError(f"Tool {self.name} requires storage backend")
        if not self.concept_manager:
            raise ValueError(f"Tool {self.name} requires concept manager")
    
    async def check_database_connectivity(self) -> tuple[bool, Optional[str]]:
        """
        Check if database is connected and accessible.
        
        Returns:
            Tuple of (is_connected, error_message)
        """
        if not self.storage:
            return False, "Storage backend not initialized"
        if not self.concept_manager:
            return False, "Concept manager not initialized"
        
        try:
            # Simple connectivity check
            test_query = "SELECT 1"
            self.storage._execute_query(test_query, fetch_one=True)
            return True, None
        except Exception as e:
            return False, f"Database connectivity check failed: {str(e)}"
    
    async def handle_request(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request with database connectivity check."""
        # Check database connectivity first
        is_connected, error_msg = await self.check_database_connectivity()
        if not is_connected:
            return self.format_error_response(
                f"Database not connected: {error_msg}",
                error_code="DATABASE_UNAVAILABLE"
            )
        
        # Proceed with normal request handling
        return await super().handle_request(arguments)


class CachedTool(DatabaseRequiredTool):
    """Base tool with caching capabilities."""
    
    def __init__(self, storage_backend=None, concept_manager=None, cache_ttl=300):
        super().__init__(storage_backend, concept_manager)
        self.cache_ttl = cache_ttl
        self._cache = {}  # Simple in-memory cache for now
    
    def _generate_cache_key(self, arguments: Dict[str, Any]) -> str:
        """Generate cache key from arguments."""
        # Sort arguments for consistent keys
        sorted_args = json.dumps(arguments, sort_keys=True)
        return f"{self.name}:{hash(sorted_args)}"
    
    def _cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get item from cache."""
        if key in self._cache:
            cached_item = self._cache[key]
            # Simple TTL check
            import time
            if time.time() - cached_item["timestamp"] < self.cache_ttl:
                return cached_item["data"]
            else:
                # Expired, remove from cache
                del self._cache[key]
        return None
    
    def _cache_set(self, key: str, data: Dict[str, Any]):
        """Set item in cache."""
        import time
        self._cache[key] = {
            "data": data,
            "timestamp": time.time()
        }
    
    async def execute_with_cache(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute with caching support."""
        cache_key = self._generate_cache_key(arguments)
        
        # Check cache first
        cached_result = self._cache_get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for tool '{self.name}'")
            cached_result["cache_hit"] = True
            return cached_result
        
        # Execute and cache
        result = await self.execute(arguments)
        if result.get("success", True):  # Only cache successful results
            self._cache_set(cache_key, result)
            logger.debug(f"Cached result for tool '{self.name}'")
        
        result["cache_hit"] = False
        return result
    
    async def handle_request(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request with caching."""
        try:
            # Validate arguments first
            is_valid, error_msg = self.validate_arguments(arguments)
            if not is_valid:
                return self.format_error_response(f"Invalid arguments: {error_msg}")
            
            # Check database connectivity
            is_connected, db_error = await self.check_database_connectivity()
            if not is_connected:
                return self.format_error_response(f"Database not connected: {db_error}")
            
            # Execute with caching
            return await self.execute_with_cache(arguments)
            
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(f"Error in cached tool '{self.name}': {error_msg}", exc_info=True)
            return self.format_error_response(error_msg)