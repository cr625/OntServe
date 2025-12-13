#!/usr/bin/env python3
"""
OntServe FastMCP Server (Phase 2)

Side-by-side FastMCP 2.0 implementation running on port 8083.
Maintains EXACT compatibility with ProEthica by matching legacy server signatures.

This server runs in parallel with mcp_server.py (port 8082) for testing.
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment configuration using standalone config system
from config.config_loader import load_ontserve_config
config_summary = load_ontserve_config()
logger.info(f"Loaded configuration from: {', '.join(config_summary['loaded_files'])}")

# Import storage backends (reusing existing code from legacy server)
from storage.postgresql_storage import PostgreSQLStorage, StorageError
from storage.concept_manager import ConceptManager
from storage.source_text_manager import SourceTextManager
from services.sparql_service import SPARQLService
from servers.mcp_source_text_integration import enhance_entity_submission_with_source_text


# Module-level storage singletons (initialized once)
_storage = None
_concept_manager = None
_source_text_manager = None
_sparql_service = None
_db_connected = False


def _init_database():
    """Initialize database connection and storage backends."""
    global _storage, _concept_manager, _source_text_manager, _sparql_service, _db_connected

    try:
        db_url = os.environ.get(
            'ONTSERVE_DB_URL',
            'postgresql://postgres:PASS@localhost:5432/ontserve'
        )

        logger.info(f"Initializing PostgreSQL storage: {db_url}")

        storage_config = {
            'db_url': db_url,
            'pool_size': int(os.environ.get('ONTSERVE_MAX_CONNECTIONS', 10)),
            'timeout': int(os.environ.get('ONTSERVE_QUERY_TIMEOUT', 30)),
            'enable_vector_search': os.environ.get('ONTSERVE_ENABLE_VECTOR_SEARCH', 'true').lower() == 'true'
        }

        _storage = PostgreSQLStorage(storage_config)
        _concept_manager = ConceptManager(_storage)
        _source_text_manager = SourceTextManager(_storage)

        try:
            _sparql_service = SPARQLService()
            logger.info("SPARQL service initialized successfully")
        except Exception as sparql_error:
            logger.warning(f"SPARQL service initialization failed: {sparql_error}")
            _sparql_service = None

        _db_connected = True
        logger.info("Database connection initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        _storage = None
        _concept_manager = None
        _source_text_manager = None
        _sparql_service = None
        _db_connected = False
        logger.warning("Server will start with limited functionality (no database)")


# Initialize database on module load
_init_database()

# Create FastMCP server instance
mcp = FastMCP("OntServe MCP Server")


# ============================================================================
# Tool implementations (bare async functions for both FastMCP and legacy)
# ============================================================================

async def impl_get_entities_by_category(
    category: str,
    domain_id: str = "engineering-ethics",
    status: str = "approved"
) -> dict:
    """Retrieve ontology entities by category from a professional domain."""
    logger.debug(f"Getting {category} entities from domain {domain_id} with status {status}")

    if not _db_connected or not _concept_manager:
        return {
            "error": "Database not connected",
            "entities": [],
            "category": category,
            "domain_id": domain_id,
            "status": status,
            "total_count": 0
        }

    try:
        result = _concept_manager.get_entities_by_category(category, domain_id, status)
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


async def impl_sparql_query(
    query: str,
    domain_id: str = "engineering-ethics"
) -> dict:
    """Execute SPARQL query on professional domain ontology."""
    logger.debug(f"Executing SPARQL query on domain {domain_id}: {query[:100]}...")

    if not _sparql_service:
        return {
            "error": "SPARQL service not available",
            "query": query,
            "domain_id": domain_id
        }

    try:
        import time
        start_time = time.time()
        results = _sparql_service.execute_query(query)
        execution_time_ms = int((time.time() - start_time) * 1000)

        return {
            "results": results.get("results", {}),
            "query": query,
            "domain_id": domain_id,
            "execution_time_ms": execution_time_ms,
            "message": "SPARQL query executed successfully"
        }
    except Exception as e:
        logger.error(f"SPARQL query execution failed: {e}")
        return {"error": str(e), "query": query, "domain_id": domain_id}


async def impl_submit_candidate_concept(
    concept: dict,
    domain_id: str = "engineering-ethics",
    submitted_by: str = "proethica-extractor"
) -> dict:
    """Submit a candidate concept extracted by ProEthica."""
    logger.info(f"Submitting candidate concept: {concept.get('label', 'unknown')} in domain {domain_id}")

    if not _db_connected or not _concept_manager:
        return {"error": "Database not connected"}

    try:
        result = _concept_manager.submit_candidate_concept(concept, domain_id, submitted_by)
        return result
    except StorageError as e:
        logger.error(f"Storage error submitting concept: {e}")
        return {"error": f"Failed to submit concept: {str(e)}"}


async def impl_update_concept_status(
    concept_id: str,
    status: str,
    user: str,
    reason: str = ""
) -> dict:
    """Update the status of a candidate concept (approve/reject)."""
    logger.info(f"Updating concept {concept_id} status to {status} by {user}")

    if not _db_connected or not _concept_manager:
        return {"error": "Database not connected"}

    try:
        result = _concept_manager.update_concept_status(concept_id, status, user, reason)
        return result
    except StorageError as e:
        logger.error(f"Storage error updating concept status: {e}")
        return {"error": f"Failed to update concept status: {str(e)}"}


async def impl_get_candidate_concepts(
    domain_id: str = "engineering-ethics",
    category: Optional[str] = None,
    status: str = "candidate"
) -> dict:
    """Retrieve candidate concepts for review."""
    logger.debug(f"Getting candidate concepts from domain {domain_id}, category: {category}, status: {status}")

    if not _db_connected or not _concept_manager:
        return {
            "error": "Database not connected",
            "candidates": [],
            "domain_id": domain_id,
            "filters": {"category": category, "status": status},
            "total_count": 0
        }

    try:
        result = _concept_manager.get_candidate_concepts(domain_id, category, status)
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


async def impl_get_domain_info(domain_id: str = "engineering-ethics") -> dict:
    """Get information about a professional domain."""
    if not _db_connected or not _concept_manager:
        return {"error": "Database not connected"}

    try:
        result = _concept_manager.get_domain_info(domain_id)
        return result
    except StorageError as e:
        logger.error(f"Storage error getting domain info: {e}")
        return {"error": f"Failed to retrieve domain info: {str(e)}"}


async def impl_store_extracted_entities(
    case_id: str,
    section_type: str,
    entities: List[dict],
    extraction_session: Optional[dict] = None
) -> dict:
    """Store extracted entities from LLM in case-specific ontology with PROV-O provenance."""
    if extraction_session is None:
        extraction_session = {}

    if not _db_connected or not _concept_manager:
        return {"error": "Database not connected"}

    try:
        stored_entities = []
        domain_id = "engineering-ethics"
        submitted_by = f"proethica-case-{case_id}-{section_type}"

        for entity in entities:
            label = entity.get('label', '')
            safe_label = label.replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '')
            entity_uri = f"http://proethica.org/ontology/case/{case_id}#{section_type}_{safe_label}"

            entity_data = {
                'label': entity.get('label', ''),
                'description': entity.get('description', ''),
                'category': entity.get('category', 'Entity'),
                'uri': entity_uri,
                'confidence': entity.get('confidence', 0.8),
                'source_text': entity.get('source_text', ''),
                'extracted_from_section': section_type,
                'extraction_timestamp': datetime.now(),
                'extractor_name': submitted_by,
                'extraction_method': 'case_entity_extraction',
                'domain_id': domain_id,
                'submitted_by': submitted_by,
                'case_id': case_id,
                'metadata': {
                    'extraction_session': extraction_session,
                    'extraction_metadata': entity.get('extraction_metadata', {}),
                    'nspe_case_entity': True
                }
            }

            result = enhance_entity_submission_with_source_text(
                _concept_manager, _source_text_manager, entity_data, case_id
            )

            if result.get('success'):
                stored_entities.append({
                    'label': entity.get('label', ''),
                    'category': entity.get('category', 'Entity'),
                    'section_type': section_type,
                    'concept_id': result.get('concept_id'),
                    'status': 'candidate',
                    'source_text_stored': result.get('source_text_stored', False),
                    'triples_count': result.get('triples_count', 0)
                })
            else:
                logger.warning(f"Failed to store entity {entity.get('label', '')}: {result.get('error', 'Unknown error')}")

        logger.info(f"Stored {len(stored_entities)} entities with provenance for case {case_id}, section {section_type}")

        return {
            "success": True,
            "case_id": case_id,
            "section_type": section_type,
            "stored_count": len(stored_entities),
            "entities": stored_entities,
            "method": "candidate_concepts_with_provenance"
        }
    except Exception as e:
        logger.error(f"Error storing extracted entities: {e}")
        return {"error": f"Failed to store entities: {str(e)}"}


async def impl_get_case_entities(
    case_id: str,
    section_type: Optional[str] = None,
    category: Optional[str] = None
) -> dict:
    """Retrieve stored entities for a specific case."""
    if not _db_connected or not _concept_manager:
        return {"error": "Database not connected"}

    try:
        submitted_by_pattern = f"proethica-case-{case_id}"
        if section_type:
            submitted_by_pattern += f"-{section_type}"

        result = _concept_manager.get_candidate_concepts(
            domain_id="engineering-ethics",
            status="candidate",
            filters={'submitted_by_like': submitted_by_pattern}
        )

        entities = result.get('candidates', [])

        if category:
            entities = [e for e in entities if e.get('category', '') == category]
        if section_type:
            entities = [e for e in entities if e.get('metadata', {}).get('section_type') == section_type]

        return {
            "case_id": case_id,
            "entities": entities,
            "total_count": len(entities),
            "filters": {'section_type': section_type, 'category': category},
            "method": "candidate_concepts"
        }
    except Exception as e:
        logger.error(f"Error retrieving case entities: {e}")
        return {"error": f"Failed to retrieve entities: {str(e)}"}


# ============================================================================
# Register tools with FastMCP (these wrap the impl_ functions)
# ============================================================================

@mcp.tool()
async def get_entities_by_category(category: str, domain_id: str = "engineering-ethics", status: str = "approved") -> dict:
    """Retrieve ontology entities by category from a professional domain."""
    return await impl_get_entities_by_category(category, domain_id, status)

@mcp.tool()
async def sparql_query(query: str, domain_id: str = "engineering-ethics") -> dict:
    """Execute SPARQL query on professional domain ontology."""
    return await impl_sparql_query(query, domain_id)

@mcp.tool()
async def submit_candidate_concept(concept: dict, domain_id: str = "engineering-ethics", submitted_by: str = "proethica-extractor") -> dict:
    """Submit a candidate concept extracted by ProEthica."""
    return await impl_submit_candidate_concept(concept, domain_id, submitted_by)

@mcp.tool()
async def update_concept_status(concept_id: str, status: str, user: str, reason: str = "") -> dict:
    """Update the status of a candidate concept (approve/reject)."""
    return await impl_update_concept_status(concept_id, status, user, reason)

@mcp.tool()
async def get_candidate_concepts(domain_id: str = "engineering-ethics", category: Optional[str] = None, status: str = "candidate") -> dict:
    """Retrieve candidate concepts for review."""
    return await impl_get_candidate_concepts(domain_id, category, status)

@mcp.tool()
async def get_domain_info(domain_id: str = "engineering-ethics") -> dict:
    """Get information about a professional domain."""
    return await impl_get_domain_info(domain_id)

@mcp.tool()
async def store_extracted_entities(case_id: str, section_type: str, entities: List[dict], extraction_session: Optional[dict] = None) -> dict:
    """Store extracted entities from LLM in case-specific ontology with PROV-O provenance."""
    return await impl_store_extracted_entities(case_id, section_type, entities, extraction_session)

@mcp.tool()
async def get_case_entities(case_id: str, section_type: Optional[str] = None, category: Optional[str] = None) -> dict:
    """Retrieve stored entities for a specific case."""
    return await impl_get_case_entities(case_id, section_type, category)


# ============================================================================
# Legacy JSON-RPC compatibility layer for ProEthica
# ============================================================================

TOOL_HANDLERS = {
    "get_entities_by_category": impl_get_entities_by_category,
    "sparql_query": impl_sparql_query,
    "submit_candidate_concept": impl_submit_candidate_concept,
    "update_concept_status": impl_update_concept_status,
    "get_candidate_concepts": impl_get_candidate_concepts,
    "get_domain_info": impl_get_domain_info,
    "store_extracted_entities": impl_store_extracted_entities,
    "get_case_entities": impl_get_case_entities,
}


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Legacy health check endpoint for monitoring."""
    domain_count = 0
    if _db_connected and _storage:
        try:
            query = "SELECT COUNT(*) FROM domains WHERE is_active = true"
            result = _storage._execute_query(query, fetch_one=True)
            domain_count = result[0] if result else 0
        except Exception:
            pass

    return JSONResponse({
        "status": "ok",
        "message": "OntServe FastMCP server is running",
        "server_version": "2.0.0-fastmcp",
        "database_connected": _db_connected,
        "domains_loaded": domain_count,
        "sparql_service": "available" if _sparql_service else "unavailable"
    })


@mcp.custom_route("/", methods=["POST"])
async def legacy_jsonrpc(request: Request) -> JSONResponse:
    """
    Legacy JSON-RPC endpoint for ProEthica compatibility.
    Handles requests in the format ProEthica expects.
    """
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
        })

    jsonrpc_id = body.get("id", 1)
    method = body.get("method", "")
    params = body.get("params", {})

    # Handle tools/list
    if method in ("tools/list", "list_tools"):
        tools = [{"name": name, "description": f"Tool: {name}"} for name in TOOL_HANDLERS.keys()]
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": jsonrpc_id,
            "result": {"tools": tools}
        })

    # Handle tool calls
    if method in ("tools/call", "call_tool"):
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in TOOL_HANDLERS:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            })

        try:
            handler = TOOL_HANDLERS[tool_name]
            result = await handler(**arguments)

            return JSONResponse({
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result)}]
                }
            })
        except Exception as e:
            logger.error(f"Error in tool '{tool_name}': {str(e)}")
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(e)})}]
                }
            })

    return JSONResponse({
        "jsonrpc": "2.0",
        "id": jsonrpc_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"}
    })


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OntServe FastMCP Server (Phase 2)")
    parser.add_argument("--port", type=int, default=8083, help="Port to run on (default: 8083)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--transport", default="http",
                       choices=["http", "streamable-http", "sse", "stdio"],
                       help="Transport mode (default: http for legacy compatibility)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("OntServe FastMCP Server (Phase 2)")
    logger.info(f"Port: {args.port}")
    logger.info(f"Transport: {args.transport}")
    logger.info(f"Tools: 8 (ProEthica compatible)")
    logger.info(f"Legacy JSON-RPC: http://localhost:{args.port}/")
    logger.info(f"Health check: http://localhost:{args.port}/health")
    logger.info(f"Database: {'connected' if _db_connected else 'NOT CONNECTED'}")
    logger.info(f"SPARQL: {'available' if _sparql_service else 'unavailable'}")
    logger.info("Legacy server: Keep running on port 8082")
    logger.info("=" * 60)

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)
