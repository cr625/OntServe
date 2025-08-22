#!/usr/bin/env python3
"""
OntServe MCP Server

A dedicated ontology storage and serving MCP server for the ProEthica ecosystem.
Handles ontology storage, versioning, candidate concept management, and SPARQL queries.
"""

import os
import sys
import json
import logging
import asyncio
from aiohttp import web
from typing import Dict, List, Any, Optional, Union
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

class OntServeMCPServer:
    """
    OntServe MCP Server
    
    Provides ontology storage, versioning, and serving capabilities via MCP protocol.
    Handles candidate concepts from ProEthica extraction workflows.
    """
    
    def __init__(self):
        """Initialize the OntServe MCP server."""
        self.jsonrpc_id = 0
        
        # Server information
        self.server_info = {
            "name": "OntServe MCP Server",
            "version": "1.0.0",
            "description": "Dedicated ontology storage and serving server for ProEthica ecosystem",
            "capabilities": [
                "Ontology entity storage and retrieval",
                "Candidate concept management", 
                "Version control and audit trail",
                "SPARQL query execution",
                "Professional domain management",
                "Cross-ontology term referencing"
            ]
        }
        
        # Check environment variable for debug mode
        self.debug_mode = os.environ.get("ONTSERVE_DEBUG", "false").lower() == "true"
        if self.debug_mode:
            logger.info("Debug mode enabled")
            logging.getLogger().setLevel(logging.DEBUG)
            
        logger.info("OntServe MCP Server initialized")
        
        # Initialize database connection and storage
        self._init_database()
    
    def _init_database(self):
        """Initialize database connection and storage backends."""
        try:
            # Database URL from environment
            self.db_url = os.environ.get(
                'ONTSERVE_DB_URL', 
                'postgresql://ontserve_user:ontserve_development_password@localhost:5433/ontserve'
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
            
            # In case of database failure, we can still start but with limited functionality
            logger.warning("Server will start with limited functionality (no database)")
    
    async def handle_health(self, request):
        """Health check endpoint for the OntServe MCP server."""
        domain_count = 0
        if self.db_connected and self.storage:
            try:
                # Get count of active domains from database
                query = "SELECT COUNT(*) FROM domains WHERE is_active = true"
                result = self.storage._execute_query(query, fetch_one=True)
                domain_count = result[0] if result else 0
            except Exception as e:
                logger.warning(f"Failed to get domain count for health check: {e}")
        
        return web.json_response({
            "status": "ok", 
            "message": "OntServe MCP server is running",
            "server_info": self.server_info,
            "database_connected": self.db_connected,
            "domains_loaded": domain_count
        })

    async def handle_jsonrpc(self, request):
        """Handle JSON-RPC requests."""
        try:
            request_data = await request.json()
            response = await self._process_request(request_data)
            return web.json_response(response)
        except Exception as e:
            logger.error(f"Error processing JSON-RPC request: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": f"Internal error: {str(e)}"},
                "id": self.jsonrpc_id
            }
            return web.json_response(error_response)

    async def _process_request(self, request):
        """Process a JSON-RPC request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        self.jsonrpc_id = request_id

        logger.debug(f"Processing method: {method} with params: {params}")

        # MCP standard methods
        handlers = {
            "initialize": self._handle_initialize,
            "list_resources": self._handle_list_resources,
            "list_resource_templates": self._handle_list_resource_templates,
            "read_resource": self._handle_read_resource,
            "list_tools": self._handle_list_tools,
            "call_tool": self._handle_call_tool
        }

        if method not in handlers:
            return {
                "jsonrpc": "2.0", 
                "error": {"code": -32601, "message": f"Method not found: {method}"}, 
                "id": request_id
            }

        try:
            result = await handlers[method](params)
            return {"jsonrpc": "2.0", "result": result, "id": request_id}
        except Exception as e:
            logger.error(f"Error in method {method}: {str(e)}")
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                "id": request_id
            }

    async def _handle_initialize(self, params):
        """Handle MCP initialize request."""
        client_info = params.get("clientInfo", {})
        logger.info(f"Initializing MCP connection with client: {client_info}")
        
        return {
            "serverInfo": self.server_info,
            "capabilities": {
                "resources": {},
                "tools": {
                    "listChanged": True
                }
            }
        }

    async def _handle_list_resources(self, params):
        """List available resources."""
        return {"resources": []}

    async def _handle_list_resource_templates(self, params):
        """List resource templates."""
        return {"resourceTemplates": []}

    async def _handle_read_resource(self, params):
        """Read a resource."""
        return {"contents": []}

    async def _handle_list_tools(self, params):
        """List available tools."""
        tools = [
            {
                "name": "get_entities_by_category",
                "description": "Retrieve ontology entities by category from a professional domain",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Entity category (Role, Principle, Obligation, etc.)",
                            "enum": ["Role", "Principle", "Obligation", "State", "Resource", "Action", "Event", "Capability", "Constraint"]
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
            },
            {
                "name": "sparql_query",
                "description": "Execute SPARQL query on professional domain ontology",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "SPARQL query string"
                        },
                        "domain_id": {
                            "type": "string",
                            "description": "Professional domain identifier",
                            "default": "engineering-ethics"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "submit_candidate_concept",
                "description": "Submit a candidate concept extracted by ProEthica",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "concept": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "Concept label with type suffix"},
                                "category": {"type": "string", "description": "Concept category"},
                                "description": {"type": "string", "description": "Concept description"},
                                "uri": {"type": "string", "description": "Concept URI"},
                                "confidence_score": {"type": "number", "description": "Extraction confidence"},
                                "source_document": {"type": "string", "description": "Source document"},
                                "extraction_method": {"type": "string", "description": "Extraction method used"},
                                "llm_reasoning": {"type": "string", "description": "LLM reasoning for extraction"}
                            },
                            "required": ["label", "category", "uri"]
                        },
                        "domain_id": {
                            "type": "string",
                            "description": "Professional domain identifier",
                            "default": "engineering-ethics"
                        },
                        "submitted_by": {
                            "type": "string",
                            "description": "User/system submitting the concept",
                            "default": "proethica-extractor"
                        }
                    },
                    "required": ["concept"]
                }
            },
            {
                "name": "update_concept_status",
                "description": "Update the status of a candidate concept (approve/reject)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "concept_id": {
                            "type": "string",
                            "description": "Concept identifier"
                        },
                        "status": {
                            "type": "string",
                            "description": "New status",
                            "enum": ["approved", "rejected", "deprecated"]
                        },
                        "user": {
                            "type": "string",
                            "description": "User making the change"
                        },
                        "reason": {
                            "type": "string",
                            "description": "Reason for status change"
                        }
                    },
                    "required": ["concept_id", "status", "user"]
                }
            },
            {
                "name": "get_candidate_concepts",
                "description": "Retrieve candidate concepts for review",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "domain_id": {
                            "type": "string",
                            "description": "Professional domain identifier",
                            "default": "engineering-ethics"
                        },
                        "category": {
                            "type": "string",
                            "description": "Filter by category (optional)"
                        },
                        "status": {
                            "type": "string", 
                            "description": "Filter by status",
                            "default": "candidate"
                        }
                    },
                    "required": ["domain_id"]
                }
            },
            {
                "name": "get_domain_info",
                "description": "Get information about a professional domain",
                "inputSchema": {
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
            }
        ]
        
        return {"tools": tools}

    async def _handle_call_tool(self, params):
        """Handle tool calls."""
        name = params.get("name")
        arguments = params.get("arguments", {})
        
        logger.debug(f"Calling tool '{name}' with arguments: {arguments}")

        # Tool handlers
        tool_handlers = {
            "get_entities_by_category": self._handle_get_entities_by_category,
            "sparql_query": self._handle_sparql_query,
            "submit_candidate_concept": self._handle_submit_candidate_concept,
            "update_concept_status": self._handle_update_concept_status,
            "get_candidate_concepts": self._handle_get_candidate_concepts,
            "get_domain_info": self._handle_get_domain_info
        }
        
        if name not in tool_handlers:
            return {
                "content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {name}"})}]
            }
        
        try:
            result = await tool_handlers[name](arguments)
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
        except Exception as e:
            logger.error(f"Error in tool '{name}': {str(e)}")
            return {
                "content": [{"type": "text", "text": json.dumps({"error": f"Tool execution failed: {str(e)}"})}]
            }

    async def _handle_get_entities_by_category(self, arguments):
        """Get ontology entities by category."""
        category = arguments.get("category")
        domain_id = arguments.get("domain_id", "engineering-ethics")
        status = arguments.get("status", "approved")
        
        logger.debug(f"Getting {category} entities from domain {domain_id} with status {status}")
        
        if not self.db_connected or not self.concept_manager:
            return {
                "error": "Database not connected",
                "entities": [],
                "category": category,
                "domain_id": domain_id,
                "status": status,
                "total_count": 0
            }
        
        try:
            result = self.concept_manager.get_entities_by_category(category, domain_id, status)
            return result
        except StorageError as e:
            logger.error(f"Storage error getting entities: {e}")
            return {
                "error": f"Failed to retrieve entities: {str(e)}",
                "entities": [],
                "category": category,
                "domain_id": domain_id,
                "status": status,
                "total_count": 0
            }

    async def _handle_sparql_query(self, arguments):
        """Execute SPARQL query."""
        query = arguments.get("query")
        domain_id = arguments.get("domain_id", "engineering-ethics")
        
        logger.debug(f"Executing SPARQL query on domain {domain_id}: {query}")
        
        # TODO: Replace with actual SPARQL execution
        # For now, return mock result
        return {
            "bindings": [],
            "query": query,
            "domain_id": domain_id,
            "execution_time_ms": 45,
            "message": "SPARQL execution not implemented yet - returning mock data"
        }

    async def _handle_submit_candidate_concept(self, arguments):
        """Submit a candidate concept."""
        concept = arguments.get("concept")
        domain_id = arguments.get("domain_id", "engineering-ethics")
        submitted_by = arguments.get("submitted_by", "proethica-extractor")
        
        logger.info(f"Submitting candidate concept: {concept['label']} in domain {domain_id}")
        
        if not self.db_connected or not self.concept_manager:
            return {"error": "Database not connected"}
        
        try:
            result = self.concept_manager.submit_candidate_concept(concept, domain_id, submitted_by)
            return result
        except StorageError as e:
            logger.error(f"Storage error submitting concept: {e}")
            return {"error": f"Failed to submit concept: {str(e)}"}

    async def _handle_update_concept_status(self, arguments):
        """Update concept status."""
        concept_id = arguments.get("concept_id")
        status = arguments.get("status")
        user = arguments.get("user")
        reason = arguments.get("reason", "")
        
        logger.info(f"Updating concept {concept_id} status to {status} by {user}")
        
        if not self.db_connected or not self.concept_manager:
            return {"error": "Database not connected"}
        
        try:
            result = self.concept_manager.update_concept_status(concept_id, status, user, reason)
            return result
        except StorageError as e:
            logger.error(f"Storage error updating concept status: {e}")
            return {"error": f"Failed to update concept status: {str(e)}"}

    async def _handle_get_candidate_concepts(self, arguments):
        """Get candidate concepts for review."""
        domain_id = arguments.get("domain_id", "engineering-ethics")
        category = arguments.get("category")
        status = arguments.get("status", "candidate")
        
        logger.debug(f"Getting candidate concepts from domain {domain_id}, category: {category}, status: {status}")
        
        if not self.db_connected or not self.concept_manager:
            return {
                "error": "Database not connected",
                "candidates": [],
                "domain_id": domain_id,
                "filters": {"category": category, "status": status},
                "total_count": 0
            }
        
        try:
            result = self.concept_manager.get_candidate_concepts(domain_id, category, status)
            return result
        except StorageError as e:
            logger.error(f"Storage error getting candidate concepts: {e}")
            return {
                "error": f"Failed to retrieve candidate concepts: {str(e)}",
                "candidates": [],
                "domain_id": domain_id,
                "filters": {"category": category, "status": status},
                "total_count": 0
            }

    async def _handle_get_domain_info(self, arguments):
        """Get domain information."""
        domain_id = arguments.get("domain_id", "engineering-ethics")
        
        if not self.db_connected or not self.concept_manager:
            return {"error": "Database not connected"}
        
        try:
            result = self.concept_manager.get_domain_info(domain_id)
            return result
        except StorageError as e:
            logger.error(f"Storage error getting domain info: {e}")
            return {"error": f"Failed to retrieve domain info: {str(e)}"}

    async def start(self):
        """Start the MCP server."""
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

        self.app.middlewares.append(cors_middleware)

        # Register routes
        self.app.router.add_post('/', self.handle_jsonrpc)  # Root for MCP
        self.app.router.add_post('/jsonrpc', self.handle_jsonrpc)  # Standard JSON-RPC
        self.app.router.add_get('/health', self.handle_health)  # Health check

        # Start the server
        port = int(os.environ.get("ONTSERVE_MCP_PORT", 8082))
        host = os.environ.get("ONTSERVE_HOST", "0.0.0.0")
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()

        logger.info(f"OntServe MCP Server started at http://{host}:{port}")
        logger.info(f"Health check available at: http://{host}:{port}/health")

    async def stop(self):
        """Stop the server."""
        if hasattr(self, 'site'):
            await self.site.stop()
        if hasattr(self, 'runner'):
            await self.runner.cleanup()
        logger.info("OntServe MCP Server stopped")


async def main():
    """Run the OntServe MCP server."""
    server = OntServeMCPServer()
    
    try:
        await server.start()
        
        # Keep running until interrupted
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour
            
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except asyncio.CancelledError:
        logger.info("Server cancelled")
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
