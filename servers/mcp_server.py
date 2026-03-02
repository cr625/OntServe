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
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment configuration using new standalone config system
from config.config_loader import load_ontserve_config
config_summary = load_ontserve_config()
logger.info(f"Loaded configuration from: {', '.join(config_summary['loaded_files'])}")

from storage.postgresql_storage import PostgreSQLStorage, StorageError
from storage.concept_manager import ConceptManager
from storage.source_text_manager import SourceTextManager
from services.sparql_service import SPARQLService
from services.ontology_sync_service import sync_ontologies_on_startup
from servers.mcp_tool_schemas import TOOL_DEFINITIONS
from servers.mcp_tool_handlers import MCPToolHandlers


class OntServeMCPServer:
    """
    OntServe MCP Server

    Provides ontology storage, versioning, and serving capabilities via MCP protocol.
    Handles candidate concepts from ProEthica extraction workflows.
    """

    def __init__(self):
        """Initialize the OntServe MCP server."""
        self.jsonrpc_id = 0

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

        self.debug_mode = os.environ.get("ONTSERVE_DEBUG", "false").lower() == "true"
        if self.debug_mode:
            logger.info("Debug mode enabled")
            logging.getLogger().setLevel(logging.DEBUG)

        logger.info("OntServe MCP Server initialized")

        # Initialize database connection and storage
        self._init_database()

        # Build tool handler instances
        self.tool_handlers = MCPToolHandlers(
            concept_manager=self.concept_manager,
            storage=self.storage,
            sparql_service=self.sparql_service,
            source_text_manager=self.source_text_manager,
            db_connected=self.db_connected,
        )

        # Map tool names to handler methods
        self._tool_dispatch = {
            "get_entities_by_category": self.tool_handlers.handle_get_entities_by_category,
            "sparql_query": self.tool_handlers.handle_sparql_query,
            "submit_candidate_concept": self.tool_handlers.handle_submit_candidate_concept,
            "update_concept_status": self.tool_handlers.handle_update_concept_status,
            "get_candidate_concepts": self.tool_handlers.handle_get_candidate_concepts,
            "get_domain_info": self.tool_handlers.handle_get_domain_info,
            "store_extracted_entities": self.tool_handlers.handle_store_extracted_entities,
            "get_case_entities": self.tool_handlers.handle_get_case_entities,
            "get_entity_by_uri": self.tool_handlers.handle_get_entity_by_uri,
            "get_entities_by_uris": self.tool_handlers.handle_get_entities_by_uris,
            "get_entity_by_label": self.tool_handlers.handle_get_entity_by_label,
        }

    def _init_database(self):
        """Initialize database connection and storage backends."""
        try:
            self.db_url = os.environ.get(
                'ONTSERVE_DB_URL',
                'postgresql://postgres:PASS@localhost:5432/ontserve'
            )

            logger.info(f"Initializing PostgreSQL storage: {self.db_url}")

            storage_config = {
                'db_url': self.db_url,
                'pool_size': int(os.environ.get('ONTSERVE_MAX_CONNECTIONS', 10)),
                'timeout': int(os.environ.get('ONTSERVE_QUERY_TIMEOUT', 30)),
                'enable_vector_search': os.environ.get('ONTSERVE_ENABLE_VECTOR_SEARCH', 'true').lower() == 'true'
            }

            self.storage = PostgreSQLStorage(storage_config)
            self.concept_manager = ConceptManager(self.storage)
            self.source_text_manager = SourceTextManager(self.storage)

            try:
                self.sparql_service = SPARQLService()
                logger.info("SPARQL service initialized successfully")
            except Exception as sparql_error:
                logger.warning(f"SPARQL service initialization failed: {sparql_error}")
                self.sparql_service = None

            self.db_connected = True
            logger.info("Database connection initialized successfully")

            # Auto-sync ontology entities from TTL files
            try:
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker
                engine = create_engine(self.db_url)
                Session = sessionmaker(bind=engine)
                session = Session()
                ontologies_dir = project_root / 'ontologies'
                sync_result = sync_ontologies_on_startup(session, ontologies_dir)
                if sync_result.get('updated', 0) > 0:
                    logger.info(f"Ontology sync: {sync_result['updated']} ontologies updated")
                else:
                    logger.debug("Ontology sync: all ontologies up to date")
                session.close()
            except Exception as sync_error:
                logger.warning(f"Ontology sync failed (non-fatal): {sync_error}")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            self.storage = None
            self.concept_manager = None
            self.source_text_manager = None
            self.sparql_service = None
            self.db_connected = False
            logger.warning("Server will start with limited functionality (no database)")

    # ------------------------------------------------------------------
    # HTTP endpoints
    # ------------------------------------------------------------------

    async def handle_health(self, request):
        """Health check endpoint for the OntServe MCP server."""
        domain_count = 0
        if self.db_connected and self.storage:
            try:
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
            "domains_loaded": domain_count,
            "sparql_service": "available" if self.sparql_service else "unavailable"
        })

    async def handle_sparql(self, request):
        """SPARQL query endpoint."""
        if not self.sparql_service:
            return web.json_response({
                "error": "SPARQL service not available"
            }, status=503)

        try:
            body = await request.json()
            query = body.get('query')

            if not query:
                return web.json_response({
                    "error": "No SPARQL query provided"
                }, status=400)

            results = self.sparql_service.execute_query(query)
            return web.json_response(results)

        except json.JSONDecodeError:
            return web.json_response({
                "error": "Invalid JSON in request body"
            }, status=400)
        except ValueError as ve:
            return web.json_response({
                "error": str(ve)
            }, status=400)
        except Exception as e:
            logger.error(f"SPARQL endpoint error: {e}")
            return web.json_response({
                "error": "Internal server error"
            }, status=500)

    async def handle_get_guidelines_compat(self, request):
        """ProEthica compatibility endpoint for guidelines."""
        domain = request.match_info.get('domain', 'engineering-ethics')

        logger.info(f"ProEthica compatibility: guidelines request for domain '{domain}'")

        return web.json_response({
            "status": "ok",
            "domain": domain,
            "message": "Guidelines endpoint available for ProEthica compatibility",
            "note": "This is a compatibility endpoint - full guidelines functionality available via JSON-RPC",
            "available_methods": [
                "get_entities_by_category",
                "submit_candidate_concept",
                "update_concept_status",
                "get_candidate_concepts",
                "sparql_query"
            ]
        })

    # ------------------------------------------------------------------
    # JSON-RPC protocol
    # ------------------------------------------------------------------

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
        return {"tools": TOOL_DEFINITIONS}

    async def _handle_call_tool(self, params):
        """Handle tool calls."""
        name = params.get("name")
        arguments = params.get("arguments", {})

        logger.debug(f"Calling tool '{name}' with arguments: {arguments}")

        handler = self._tool_dispatch.get(name)
        if not handler:
            return {
                "content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {name}"})}]
            }

        try:
            result = await handler(arguments)
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
        except Exception as e:
            logger.error(f"Error in tool '{name}': {str(e)}")
            return {
                "content": [{"type": "text", "text": json.dumps({"error": f"Tool execution failed: {str(e)}"})}]
            }

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the MCP server."""
        self.app = web.Application()

        @web.middleware
        async def cors_middleware(request, handler):
            response = await handler(request)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            return response

        self.app.middlewares.append(cors_middleware)

        self.app.router.add_post('/', self.handle_jsonrpc)
        self.app.router.add_post('/jsonrpc', self.handle_jsonrpc)
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_post('/sparql', self.handle_sparql)
        self.app.router.add_get('/api/guidelines/{domain}', self.handle_get_guidelines_compat)

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
            await asyncio.sleep(3600)

    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except asyncio.CancelledError:
        logger.info("Server cancelled")
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
