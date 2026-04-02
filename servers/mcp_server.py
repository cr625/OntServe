#!/usr/bin/env python3
"""
OntServe MCP Server (FastMCP 3.x)

Ontology storage and serving for the ProEthica ecosystem.
Tools are auto-registered with schemas generated from type hints.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from fastmcp import FastMCP, Context
from fastmcp.server.lifespan import lifespan
from starlette.requests import Request
from starlette.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

project_root = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Pydantic models for complex tool inputs
# ---------------------------------------------------------------------------

class ConceptInput(BaseModel):
    label: str = Field(description="Concept label with type suffix")
    category: str = Field(description="Concept category")
    uri: str = Field(description="Concept URI")
    description: str = Field(default="", description="Concept description")
    confidence_score: Optional[float] = Field(default=None, description="Extraction confidence")
    source_document: Optional[str] = Field(default=None, description="Source document")
    extraction_method: Optional[str] = Field(default=None, description="Extraction method used")
    llm_reasoning: Optional[str] = Field(default=None, description="LLM reasoning for extraction")


class EntityInput(BaseModel):
    label: str
    category: str = "Entity"
    description: str = ""
    confidence: float = 0.8
    source_text: Optional[str] = None
    extraction_metadata: Optional[dict] = None


class ExtractionSession(BaseModel):
    extraction_session: Optional[dict] = None


# ---------------------------------------------------------------------------
# Lifespan: database and service initialization
# ---------------------------------------------------------------------------

@lifespan
async def app_lifespan(server):
    from config.config_loader import load_ontserve_config
    config_summary = load_ontserve_config()
    logger.info(f"Loaded config from: {', '.join(config_summary['loaded_files'])}")

    from storage.postgresql_storage import PostgreSQLStorage
    from storage.concept_manager import ConceptManager
    from storage.source_text_manager import SourceTextManager
    from services.sparql_service import SPARQLService
    from services.wolfram_service import WolframService
    from services.ontology_sync_service import sync_ontologies_on_startup
    from servers.mcp_tool_handlers import MCPToolHandlers

    from config.config_loader import get_database_url
    db_url = get_database_url()

    try:
        storage = PostgreSQLStorage({
            'db_url': db_url,
            'pool_size': int(os.environ.get('ONTSERVE_MAX_CONNECTIONS', 10)),
            'timeout': int(os.environ.get('ONTSERVE_QUERY_TIMEOUT', 30)),
            'enable_vector_search': os.environ.get(
                'ONTSERVE_ENABLE_VECTOR_SEARCH', 'true'
            ).lower() == 'true'
        })
        concept_manager = ConceptManager(storage)
        source_text_manager = SourceTextManager(storage)

        try:
            sparql_service = SPARQLService()
        except Exception as e:
            logger.warning(f"SPARQL service init failed: {e}")
            sparql_service = None

        try:
            wolfram_service = WolframService()
            if wolfram_service.is_configured:
                logger.info("Wolfram AgentOne service initialized")
            else:
                logger.warning("Wolfram service created but API key not configured")
        except Exception as e:
            logger.warning(f"Wolfram service init failed: {e}")
            wolfram_service = None

        # Auto-sync ontology entities from TTL files
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            engine = create_engine(db_url)
            Session = sessionmaker(bind=engine)
            session = Session()
            sync_result = sync_ontologies_on_startup(
                session, project_root / 'ontologies'
            )
            if sync_result.get('updated', 0) > 0:
                logger.info(
                    f"Ontology sync: {sync_result['updated']} ontologies updated"
                )
            session.close()
        except Exception as e:
            logger.warning(f"Ontology sync failed (non-fatal): {e}")

        handlers = MCPToolHandlers(
            concept_manager=concept_manager,
            storage=storage,
            sparql_service=sparql_service,
            wolfram_service=wolfram_service,
            source_text_manager=source_text_manager,
            db_connected=True,
        )
        logger.info("OntServe MCP Server initialized (database connected)")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        handlers = MCPToolHandlers(
            concept_manager=None,
            storage=None,
            sparql_service=None,
            wolfram_service=None,
            source_text_manager=None,
            db_connected=False,
        )
        sparql_service = None
        wolfram_service = None
        logger.warning("Server starting with limited functionality (no database)")

    yield {
        "handlers": handlers,
        "sparql_service": sparql_service,
        "wolfram_service": wolfram_service,
    }


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "OntServe",
    instructions="Ontology storage and serving for the ProEthica ecosystem",
    lifespan=app_lifespan,
)


# ---------------------------------------------------------------------------
# Custom HTTP endpoints
# ---------------------------------------------------------------------------

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "message": "OntServe MCP server is running",
        "server": "FastMCP 3.x",
    })


@mcp.custom_route("/sparql", methods=["POST"])
async def sparql_endpoint(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        query = body.get('query')
        if not query:
            return JSONResponse({"error": "No SPARQL query provided"}, status_code=400)

        # Access sparql_service from app state
        sparql_service = request.app.state.lifespan_context.get("sparql_service")
        if not sparql_service:
            return JSONResponse(
                {"error": "SPARQL service not available"}, status_code=503
            )

        results = sparql_service.execute_query(query)
        return JSONResponse(results)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    except Exception as e:
        logger.error(f"SPARQL endpoint error: {e}")
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@mcp.custom_route("/api/guidelines/{domain}", methods=["GET"])
async def guidelines_compat(request: Request) -> JSONResponse:
    domain = request.path_params.get("domain", "engineering-ethics")
    return JSONResponse({
        "status": "ok",
        "domain": domain,
        "message": "Guidelines endpoint for ProEthica compatibility",
        "available_tools": [
            "get_entities_by_category", "submit_candidate_concept",
            "update_concept_status", "get_candidate_concepts", "sparql_query",
            "wolfram_lookup", "store_extracted_entities", "get_case_entities",
            "get_entity_by_uri", "get_entities_by_uris", "get_entity_by_label",
        ]
    })


# ---------------------------------------------------------------------------
# MCP Tools (12 tools, schemas auto-generated from type hints)
# ---------------------------------------------------------------------------

def _get_handlers(ctx: Context):
    """Get the MCPToolHandlers instance from lifespan context."""
    return ctx.lifespan_context["handlers"]


@mcp.tool
async def get_entities_by_category(
    category: str,
    ctx: Context,
    domain_id: str = "engineering-ethics",
    status: str = "approved",
) -> str:
    """Retrieve ontology entities by category from a professional domain."""
    result = await _get_handlers(ctx).handle_get_entities_by_category({
        "category": category, "domain_id": domain_id, "status": status,
    })
    return json.dumps(result)


@mcp.tool
async def sparql_query(
    query: str,
    ctx: Context,
    domain_id: str = "engineering-ethics",
) -> str:
    """Execute SPARQL query on professional domain ontology."""
    result = await _get_handlers(ctx).handle_sparql_query({
        "query": query, "domain_id": domain_id,
    })
    return json.dumps(result)


@mcp.tool
async def wolfram_lookup(
    query: str,
    ctx: Context,
    context: str = "",
) -> str:
    """Look up a concept, definition, or factual information via Wolfram AgentOne.
    Useful for verifying definitions, finding related concepts, and grounding
    ontology terms in authoritative knowledge during ontology construction."""
    result = await _get_handlers(ctx).handle_wolfram_lookup({
        "query": query, "context": context,
    })
    return json.dumps(result)


@mcp.tool
async def submit_candidate_concept(
    concept: ConceptInput,
    ctx: Context,
    domain_id: str = "engineering-ethics",
    submitted_by: str = "proethica-extractor",
) -> str:
    """Submit a candidate concept extracted by ProEthica."""
    result = await _get_handlers(ctx).handle_submit_candidate_concept({
        "concept": concept.model_dump(exclude_none=True),
        "domain_id": domain_id,
        "submitted_by": submitted_by,
    })
    return json.dumps(result)


@mcp.tool
async def update_concept_status(
    concept_id: str,
    status: str,
    user: str,
    ctx: Context,
    reason: str = "",
) -> str:
    """Update the status of a candidate concept (approve/reject)."""
    result = await _get_handlers(ctx).handle_update_concept_status({
        "concept_id": concept_id, "status": status,
        "user": user, "reason": reason,
    })
    return json.dumps(result)


@mcp.tool
async def get_candidate_concepts(
    domain_id: str,
    ctx: Context,
    category: Optional[str] = None,
    status: str = "candidate",
) -> str:
    """Retrieve candidate concepts for review."""
    result = await _get_handlers(ctx).handle_get_candidate_concepts({
        "domain_id": domain_id, "category": category, "status": status,
    })
    return json.dumps(result)


@mcp.tool
async def get_domain_info(
    domain_id: str,
    ctx: Context,
) -> str:
    """Get information about a professional domain."""
    result = await _get_handlers(ctx).handle_get_domain_info({
        "domain_id": domain_id,
    })
    return json.dumps(result)


@mcp.tool
async def store_extracted_entities(
    case_id: str,
    section_type: str,
    entities: list[EntityInput],
    ctx: Context,
    extraction_session: Optional[dict] = None,
) -> str:
    """Store extracted entities from LLM in case-specific ontology."""
    result = await _get_handlers(ctx).handle_store_extracted_entities({
        "case_id": case_id,
        "section_type": section_type,
        "entities": [e.model_dump(exclude_none=True) for e in entities],
        "extraction_session": extraction_session or {},
    })
    return json.dumps(result)


@mcp.tool
async def get_case_entities(
    case_id: str,
    ctx: Context,
    section_type: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    """Retrieve stored entities for a specific case."""
    result = await _get_handlers(ctx).handle_get_case_entities({
        "case_id": case_id, "section_type": section_type, "category": category,
    })
    return json.dumps(result)


@mcp.tool
async def get_entity_by_uri(
    uri: str,
    ctx: Context,
    include_properties: bool = False,
) -> str:
    """Retrieve an entity's definition and metadata by its URI.
    Use this to resolve ProEthica entity IRIs during reasoning."""
    result = await _get_handlers(ctx).handle_get_entity_by_uri({
        "uri": uri, "include_properties": include_properties,
    })
    return json.dumps(result)


@mcp.tool
async def get_entities_by_uris(
    uris: list[str],
    ctx: Context,
) -> str:
    """Retrieve definitions for multiple entities at once (max 20)."""
    result = await _get_handlers(ctx).handle_get_entities_by_uris({
        "uris": uris,
    })
    return json.dumps(result)


@mcp.tool
async def get_entity_by_label(
    label: str,
    ctx: Context,
) -> str:
    """Retrieve an entity's definition, URI, and metadata by its label.
    Use for disambiguation when matching extracted concepts against existing
    ontology classes."""
    result = await _get_handlers(ctx).handle_get_entity_by_label({
        "label": label,
    })
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("ONTSERVE_MCP_PORT", 8082))
    host = os.environ.get("ONTSERVE_HOST", "0.0.0.0")

    debug = os.environ.get("ONTSERVE_DEBUG", "false").lower() == "true"
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    mcp.run(transport="http", host=host, port=port)
