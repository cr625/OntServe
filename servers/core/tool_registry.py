"""
Tool Registry for OntServe MCP Server.

Handles automatic tool discovery, registration, and request routing
with support for multiple tool modules and dynamic loading.
"""

from typing import Dict, List, Any, Type, Optional
import json
import logging
import inspect
import importlib
from pathlib import Path

from ..tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for MCP tools with automatic discovery and routing."""
    
    def __init__(self, storage_backend=None, concept_manager=None):
        """
        Initialize tool registry.
        
        Args:
            storage_backend: PostgreSQL storage backend for database tools
            concept_manager: Concept manager for entity operations
        """
        self.storage = storage_backend
        self.concept_manager = concept_manager
        self.tools: Dict[str, BaseTool] = {}
        self.tool_definitions: List[Dict[str, Any]] = []
        self._stats = {
            "registered_tools": 0,
            "successful_calls": 0,
            "failed_calls": 0
        }
        
        logger.info("Tool registry initialized")
    
    def register_tool(self, tool_class: Type[BaseTool]) -> bool:
        """
        Register a single tool class.
        
        Args:
            tool_class: Tool class inheriting from BaseTool
            
        Returns:
            True if registration successful, False otherwise
        """
        try:
            # Instantiate tool with dependencies
            tool_instance = tool_class(
                storage_backend=self.storage,
                concept_manager=self.concept_manager
            )
            
            # Check for name conflicts
            if tool_instance.name in self.tools:
                logger.warning(f"Tool '{tool_instance.name}' already registered, skipping")
                return False
            
            # Register tool
            self.tools[tool_instance.name] = tool_instance
            self.tool_definitions.append(tool_instance.get_tool_definition())
            self._stats["registered_tools"] += 1
            
            logger.info(f"Registered tool: {tool_instance.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register tool {tool_class.__name__}: {e}")
            return False
    
    def register_module(self, tool_module) -> int:
        """
        Auto-register all tool classes from a module.
        
        Args:
            tool_module: Python module containing tool classes
            
        Returns:
            Number of tools successfully registered
        """
        registered_count = 0
        module_name = getattr(tool_module, '__name__', str(tool_module))
        
        logger.info(f"Scanning module '{module_name}' for tools")
        
        # Find all tool classes in the module
        for name, obj in inspect.getmembers(tool_module, inspect.isclass):
            if (issubclass(obj, BaseTool) and 
                obj != BaseTool and
                hasattr(obj, 'name') and
                obj.name is not None):
                
                if self.register_tool(obj):
                    registered_count += 1
        
        logger.info(f"Registered {registered_count} tools from module '{module_name}'")
        return registered_count
    
    def auto_discover_tools(self) -> int:
        """
        Automatically discover and register all tools from the tools package.
        
        Returns:
            Total number of tools registered
        """
        total_registered = 0
        tools_package_path = Path(__file__).parent.parent / "tools"
        
        if not tools_package_path.exists():
            logger.warning("Tools package directory not found")
            return 0
        
        # Find all Python files in tools directory
        for tool_file in tools_package_path.glob("*.py"):
            if tool_file.name.startswith("__") or tool_file.name == "base_tool.py":
                continue
            
            module_name = f"servers.tools.{tool_file.stem}"
            
            try:
                # Import the module
                tool_module = importlib.import_module(module_name)
                
                # Register tools from module
                registered = self.register_module(tool_module)
                total_registered += registered
                
            except Exception as e:
                logger.error(f"Failed to import tool module '{module_name}': {e}")
        
        logger.info(f"Auto-discovery complete: {total_registered} tools registered")
        return total_registered
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """Get tool instance by name."""
        return self.tools.get(tool_name)
    
    def list_tool_names(self) -> List[str]:
        """Get list of registered tool names."""
        return list(self.tools.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            **self._stats,
            "available_tools": list(self.tools.keys())
        }
    
    # MCP Protocol Handlers
    
    async def handle_list_tools(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Handle MCP list_tools request.
        
        Args:
            params: Optional parameters (unused currently)
            
        Returns:
            MCP list_tools response
        """
        logger.debug(f"Listing {len(self.tool_definitions)} available tools")
        return {"tools": self.tool_definitions}
    
    async def handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle MCP call_tool request.
        
        Args:
            params: MCP call_tool parameters containing name and arguments
            
        Returns:
            MCP call_tool response with tool result
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        logger.debug(f"Calling tool '{tool_name}' with arguments: {arguments}")
        
        # Check if tool exists
        if tool_name not in self.tools:
            error_result = {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "available_tools": list(self.tools.keys())
            }
            self._stats["failed_calls"] += 1
            return {
                "content": [{"type": "text", "text": json.dumps(error_result)}]
            }
        
        try:
            # Execute tool
            tool = self.tools[tool_name]
            result = await tool.handle_request(arguments)
            
            # Update stats
            if result.get("success", True):
                self._stats["successful_calls"] += 1
            else:
                self._stats["failed_calls"] += 1
            
            # Format as MCP response
            return {
                "content": [{"type": "text", "text": json.dumps(result)}]
            }
            
        except Exception as e:
            error_msg = f"Tool execution error: {str(e)}"
            logger.error(f"Error calling tool '{tool_name}': {error_msg}", exc_info=True)
            
            error_result = {
                "success": False,
                "error": error_msg,
                "tool": tool_name
            }
            self._stats["failed_calls"] += 1
            
            return {
                "content": [{"type": "text", "text": json.dumps(error_result)}]
            }
    
    # Main Request Router
    
    async def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main request handler for JSON-RPC MCP requests.
        
        Args:
            request_data: JSON-RPC request data
            
        Returns:
            JSON-RPC response
        """
        method = request_data.get("method")
        params = request_data.get("params", {})
        request_id = request_data.get("id")
        
        logger.debug(f"Handling MCP request: {method}")
        
        try:
            # Route based on method
            if method == "list_tools":
                result = await self.handle_list_tools(params)
                
            elif method == "call_tool":
                result = await self.handle_call_tool(params)
                
            else:
                # Method not handled by tool registry
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601, 
                        "message": f"Method not found: {method}",
                        "data": {"supported_methods": ["list_tools", "call_tool"]}
                    },
                    "id": request_id
                }
            
            # Success response
            return {
                "jsonrpc": "2.0",
                "result": result,
                "id": request_id
            }
            
        except Exception as e:
            error_msg = f"Request handling error: {str(e)}"
            logger.error(f"Error handling request '{method}': {error_msg}", exc_info=True)
            
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": error_msg,
                    "data": {"method": method, "request_id": request_id}
                },
                "id": request_id
            }


class ToolLoadError(Exception):
    """Exception raised when tool loading fails."""
    pass


def create_tool_registry(storage_backend=None, concept_manager=None, 
                        auto_discover=True) -> ToolRegistry:
    """
    Create and initialize tool registry with optional auto-discovery.
    
    Args:
        storage_backend: PostgreSQL storage backend
        concept_manager: Concept manager instance
        auto_discover: Whether to auto-discover tools from modules
        
    Returns:
        Configured tool registry
    """
    registry = ToolRegistry(
        storage_backend=storage_backend,
        concept_manager=concept_manager
    )
    
    if auto_discover:
        registry.auto_discover_tools()
    
    return registry