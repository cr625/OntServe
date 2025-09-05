#!/usr/bin/env python3
"""
OntServe MCP Server - Modular Version

A lightweight, modular MCP server orchestrator for the ProEthica ecosystem.
Handles automatic tool discovery, registration, and request routing.
"""

import os
import sys
import json
import logging
import asyncio
from aiohttp import web
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import storage backend and concept manager
from storage.postgresql_storage import PostgreSQLStorage, StorageError
from storage.concept_manager import ConceptManager

# Import modular components
from servers.core.tool_registry import create_tool_registry


class OntServeMCPServer:
    """
    Lightweight MCP server orchestrator with modular tool architecture.
    
    This version delegates all tool handling to the ToolRegistry and focuses
    on server lifecycle management, health monitoring, and request routing.
    """
    
    def __init__(self):
        """Initialize the modular OntServe MCP server."""
        self.jsonrpc_id = 0
        
        # Server information
        self.server_info = {
            "name": "OntServe MCP Server",
            "version": "2.0.0",  # Incremented for modular version
            "description": "Modular ontology storage and serving server for ProEthica ecosystem",
            "architecture": "modular",
            "capabilities": [
                "Ontology entity storage and retrieval",
                "Candidate concept management", 
                "Version control and audit trail",
                "SPARQL query execution",
                "Vector similarity search",
                "Natural language query processing",
                "Professional domain management",
                "Cross-ontology term referencing"
            ]
        }
        
        # Configuration
        self.debug_mode = os.environ.get("ONTSERVE_DEBUG", "false").lower() == "true"
        if self.debug_mode:
            logger.info("Debug mode enabled")
            logging.getLogger().setLevel(logging.DEBUG)
        
        # Initialize components
        self.tool_registry = None
        self.storage = None
        self.concept_manager = None
        self.db_connected = False
        
        logger.info("OntServe MCP Server (Modular) initialized")
        
        # Initialize database and tools
        self._init_database()
        self._init_tool_registry()
    
    def _init_database(self):
        """Initialize database connection and storage backends."""
        try:
            # Database URL from environment
            self.db_url = os.environ.get(
                'ONTSERVE_DB_URL', 
                'postgresql://postgres:PASS@localhost:5432/ontserve'
            )
            
            logger.info(f"Initializing PostgreSQL storage: {self.db_url}")
            
            # Initialize PostgreSQL storage backend
            storage_config = {
                'db_url': self.db_url,
                'pool_size': int(os.environ.get('ONTSERVE_MAX_CONNECTIONS', 10)),
                'timeout': int(os.environ.get('ONTSERVE_QUERY_TIMEOUT', 30)),
                'enable_vector_search': os.environ.get('ONTSERVE_ENABLE_VECTOR_SEARCH', 'true').lower() == 'true'
            }
            
            self.storage = PostgreSQLStorage(storage_config)
            self.concept_manager = ConceptManager(self.storage)
            
            self.db_connected = True
            logger.info("Database connection initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            self.storage = None
            self.concept_manager = None
            self.db_connected = False
            logger.warning("Server will start with limited functionality (no database)")
    
    def _init_tool_registry(self):
        """Initialize the tool registry with auto-discovery."""
        try:
            logger.info("Initializing modular tool registry...")
            
            # Create tool registry with database dependencies
            self.tool_registry = create_tool_registry(
                storage_backend=self.storage,
                concept_manager=self.concept_manager,
                auto_discover=True
            )
            
            # Get registry statistics
            stats = self.tool_registry.get_stats()
            logger.info(f"Tool registry initialized: {stats['registered_tools']} tools available")
            
            if self.debug_mode:
                logger.debug(f"Available tools: {stats['available_tools']}")
            
        except Exception as e:
            logger.error(f"Failed to initialize tool registry: {e}")
            self.tool_registry = None
            raise RuntimeError(f"Tool registry initialization failed: {e}")
    
    async def handle_health(self, request):
        """Health check endpoint for the OntServe MCP server."""
        # Get tool registry stats
        tool_stats = {}
        if self.tool_registry:
            tool_stats = self.tool_registry.get_stats()
        
        # Get domain count if database is available
        domain_count = 0
        if self.db_connected and self.storage:
            try:
                query = "SELECT COUNT(*) FROM domains WHERE is_active = true"
                result = self.storage._execute_query(query, fetch_one=True)
                domain_count = result[0] if result else 0
            except Exception as e:
                logger.warning(f"Failed to get domain count for health check: {e}")
        
        health_data = {
            "status": "ok", 
            "message": "OntServe MCP server is running",
            "server_info": self.server_info,
            "database_connected": self.db_connected,
            "domains_loaded": domain_count,
            "tool_registry": {
                "available_tools": tool_stats.get("registered_tools", 0),
                "successful_calls": tool_stats.get("successful_calls", 0),
                "failed_calls": tool_stats.get("failed_calls", 0)
            }
        }
        
        return web.json_response(health_data)
    
    async def handle_jsonrpc(self, request):
        """Handle JSON-RPC requests by delegating to tool registry."""
        try:
            request_data = await request.json()
            
            # Log request in debug mode
            if self.debug_mode:
                method = request_data.get("method", "unknown")
                logger.debug(f"Processing JSON-RPC request: {method}")
            
            # Delegate to tool registry
            if self.tool_registry:
                response = await self.tool_registry.handle_request(request_data)
            else:
                # Fallback error response if tool registry is not available
                response = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32000, 
                        "message": "Tool registry not available",
                        "data": {"server_status": "degraded"}
                    },
                    "id": request_data.get("id")
                }
            
            return web.json_response(response)
            
        except Exception as e:
            logger.error(f"Error processing JSON-RPC request: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32000, 
                    "message": f"Internal error: {str(e)}",
                    "data": {"error_type": "request_processing_error"}
                },
                "id": self.jsonrpc_id
            }
            return web.json_response(error_response)
    
    async def handle_legacy_methods(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Handle legacy MCP methods not managed by tool registry.
        
        This includes initialize, list_resources, etc.
        """
        method = request_data.get("method")
        params = request_data.get("params", {})
        request_id = request_data.get("id")
        
        if method == "initialize":
            client_info = params.get("clientInfo", {})
            logger.info(f"Initializing MCP connection with client: {client_info}")
            
            return {
                "jsonrpc": "2.0",
                "result": {
                    "serverInfo": self.server_info,
                    "capabilities": {
                        "resources": {},
                        "tools": {"listChanged": True}
                    }
                },
                "id": request_id
            }
        
        elif method in ["list_resources", "list_resource_templates", "read_resource"]:
            # These are not currently used but included for MCP compliance
            empty_results = {
                "list_resources": {"resources": []},
                "list_resource_templates": {"resourceTemplates": []}, 
                "read_resource": {"contents": []}
            }
            
            return {
                "jsonrpc": "2.0",
                "result": empty_results.get(method, {}),
                "id": request_id
            }
        
        return None  # Method not handled here
    
    async def start(self):
        """Start the MCP server with middleware and routing."""
        # Initialize web application
        self.app = web.Application()
        
        # Add CORS middleware
        @web.middleware
        async def cors_middleware(request, handler):
            response = await handler(request)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            return response
        
        # Add request logging middleware (debug mode only)
        if self.debug_mode:
            @web.middleware
            async def logging_middleware(request, handler):
                start_time = asyncio.get_event_loop().time()
                response = await handler(request)
                duration = asyncio.get_event_loop().time() - start_time
                
                logger.debug(f"{request.method} {request.path} -> {response.status} ({duration:.3f}s)")
                return response
            
            self.app.middlewares.append(logging_middleware)
        
        self.app.middlewares.append(cors_middleware)
        
        # Register routes
        self.app.router.add_post('/', self.handle_jsonrpc)          # Root for MCP
        self.app.router.add_post('/jsonrpc', self.handle_jsonrpc)   # Standard JSON-RPC
        self.app.router.add_get('/health', self.handle_health)      # Health check
        
        # Start the server
        port = int(os.environ.get("ONTSERVE_MCP_PORT", 8082))
        host = os.environ.get("ONTSERVE_HOST", "0.0.0.0")
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        
        logger.info(f"OntServe MCP Server (Modular) started at http://{host}:{port}")
        logger.info(f"Health check available at: http://{host}:{port}/health")
        
        # Log available tools in debug mode
        if self.debug_mode and self.tool_registry:
            stats = self.tool_registry.get_stats()
            logger.debug(f"Server ready with {stats['registered_tools']} tools: {stats['available_tools']}")
    
    async def stop(self):
        """Stop the server gracefully."""
        if hasattr(self, 'site'):
            await self.site.stop()
        if hasattr(self, 'runner'):
            await self.runner.cleanup()
        
        logger.info("OntServe MCP Server (Modular) stopped")
    
    def get_server_stats(self) -> Dict[str, Any]:
        """Get comprehensive server statistics."""
        stats = {
            "server_info": self.server_info,
            "database_connected": self.db_connected,
            "debug_mode": self.debug_mode,
            "uptime": "unknown",  # Could be tracked if needed
        }
        
        # Add tool registry stats
        if self.tool_registry:
            stats["tools"] = self.tool_registry.get_stats()
        
        return stats


async def main():
    """Run the modular OntServe MCP server."""
    server = OntServeMCPServer()
    
    try:
        await server.start()
        
        # Log startup completion
        stats = server.get_server_stats()
        logger.info(f"Server startup complete. Database: {stats['database_connected']}, "
                   f"Tools: {stats.get('tools', {}).get('registered_tools', 0)}")
        
        # Keep running until interrupted
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour
            
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except asyncio.CancelledError:
        logger.info("Server cancelled")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())