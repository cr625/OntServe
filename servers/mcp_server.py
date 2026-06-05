#!/usr/bin/env python3
"""
OntServe MCP Server (FastMCP 3.x)

Ontology storage and serving for the ProEthica ecosystem.
Tools are auto-registered with schemas generated from type hints.
"""

import os
import sys
import json
import asyncio
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
# Put OntServe root on sys.path so the namespace package `validation` (no __init__.py) is
# importable by the conformance tools regardless of how the server is launched (the prior
# tools relied on the launcher's PYTHONPATH; a plain `python servers/mcp_server.py` did not
# have it, so `from validation import ...` raised ModuleNotFoundError).
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


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
            sparql_service = SPARQLService(db_storage=storage)
            status = sparql_service.get_service_status()
            logger.info(
                "SPARQL service: %d ontologies loaded from %s, %d triples",
                status.get("ontology_count", 0),
                status.get("load_source", "unknown"),
                status.get("total_triples", 0),
            )
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


async def _extract_sparql_query(request: Request) -> Optional[str]:
    """Pull a SPARQL query string from a request via GET, POST form, or POST JSON.

    Implements enough of the SPARQL 1.1 Protocol for standard clients
    to hit GET /sparql?query=... or POST with application/x-www-form-urlencoded
    or application/sparql-query bodies, in addition to the legacy
    JSON {"query": ...} body shape.
    """
    if request.method == "GET":
        return request.query_params.get("query")

    content_type = (request.headers.get("content-type") or "").lower()
    if "application/sparql-query" in content_type:
        body_bytes = await request.body()
        return body_bytes.decode("utf-8") if body_bytes else None

    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        return form.get("query")

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return None
    if isinstance(body, dict):
        return body.get("query")
    return None


@mcp.custom_route("/sparql", methods=["GET", "POST"])
async def sparql_endpoint(request: Request) -> JSONResponse:
    try:
        query = await _extract_sparql_query(request)
        if not query:
            return JSONResponse({"error": "No SPARQL query provided"}, status_code=400)

        sparql_service = request.app.state.lifespan_context.get("sparql_service")
        if not sparql_service:
            return JSONResponse(
                {"error": "SPARQL service not available"}, status_code=503
            )

        results = sparql_service.execute_query(query)
        return JSONResponse(results)
    except ValueError as e:
        # Raised by SPARQLService.execute_query on query syntax errors.
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        logger.error(f"SPARQL endpoint error: {e}")
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@mcp.custom_route("/sparql/status", methods=["GET"])
async def sparql_status(request: Request) -> JSONResponse:
    """Diagnostics: report how many ontologies are loaded in the SPARQL graph."""
    sparql_service = request.app.state.lifespan_context.get("sparql_service")
    if not sparql_service:
        return JSONResponse({"error": "SPARQL service not available"}, status_code=503)
    return JSONResponse(sparql_service.get_service_status())


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
# MCP Tools (17 tools: 12 base + 5 reasoning/BFO; schemas auto-generated from type hints)
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
# Reasoning tools (Pellet over merged core+intermediate+case; BFO compliance).
# Backed by servers/reasoning_tools.py -> validation/pellet_validate.py (the
# 119/119-consistent harness) + editor/services.OntologyValidationService.
# Pellet runs a blocking Java subprocess, so each call is offloaded to a thread.
# (sparql_query already exists above.)
# ---------------------------------------------------------------------------

@mcp.tool
async def reason_ontology(ontology_name: str, ctx: Context) -> str:
    """Run the Pellet reasoner over a stored ontology (merged with proethica-core
    + proethica-intermediate) and return consistency plus inferred-assertion counts
    and timing. Use the ontology name, e.g. 'proethica-case-86' or 'engineering-ethics'."""
    from servers import reasoning_tools as rt
    result = await asyncio.to_thread(rt.reason_ontology, ontology_name)
    return json.dumps(result)


@mcp.tool
async def check_consistency(ontology_name: str, ctx: Context) -> str:
    """Check whether a stored ontology is logically consistent under OWL-DL reasoning
    (Pellet, merged with core+intermediate). Returns a consistent flag, disjointness
    violation count, and any inconsistency explanation."""
    from servers import reasoning_tools as rt
    result = await asyncio.to_thread(rt.check_consistency, ontology_name)
    return json.dumps(result)


@mcp.tool
async def get_inferred_hierarchy(ontology_name: str, ctx: Context) -> str:
    """Return the class-subsumption and type assertions the reasoner INFERS for a
    stored ontology (the edges not asserted in the source TTL), capped to 300 each."""
    from servers import reasoning_tools as rt
    result = await asyncio.to_thread(rt.get_inferred_hierarchy, ontology_name)
    return json.dumps(result)


@mcp.tool
async def get_inconsistent_classes(ontology_name: str, ctx: Context) -> str:
    """List entities the reasoner forces to owl:Nothing (disjointness violations) in a
    stored ontology, plus a hard-inconsistency flag/explanation if the whole ontology
    is inconsistent."""
    from servers import reasoning_tools as rt
    result = await asyncio.to_thread(rt.get_inconsistent_classes, ontology_name)
    return json.dumps(result)


@mcp.tool
async def validate_bfo_compliance(ontology_name: str, ctx: Context) -> str:
    """Run BFO / PROV-O / proethica-intermediate compliance checks over a stored
    ontology's TTL and return errors + warnings."""
    from servers import reasoning_tools as rt
    result = await asyncio.to_thread(rt.validate_bfo_compliance, ontology_name)
    return json.dumps(result)


@mcp.tool
async def validate_conformance(ontology_name: str, ctx: Context) -> str:
    """SHACL + OWL-RL conformance check of a STORED case ontology against the core
    conformance shapes (merged with core+intermediate, OWL-RL closure applied). Returns
    a repair-oriented report: {conforms, n_violations, groups:[{shape, gloss, focus_nodes,
    count}]}. Each group is an equivalence class of violations with an NL repair gloss.
    Complements check_consistency (Pellet): this gives per-node, actionable violations."""
    from validation import conformance as cf
    result = await asyncio.to_thread(cf.conformance_report_case, ontology_name)
    return json.dumps(result)


@mcp.tool
async def validate_conformance_ttl(ttl_content: str, ctx: Context) -> str:
    """SHACL + OWL-RL conformance check of AD-HOC case TTL content (the extraction-time
    path: validate a candidate graph from temporary_rdf_storage BEFORE commit, so the
    extractor can repair in-loop). Same repair-oriented report as validate_conformance.
    Pass the candidate case TTL as a string; it is merged with core+intermediate and
    OWL-RL-expanded before the shapes run."""
    from validation import conformance as cf
    result = await asyncio.to_thread(cf.conformance_report_content, "candidate", ttl_content)
    return json.dumps(result)


@mcp.tool
async def repair_conformance_ttl(ttl_content: str, ctx: Context, domain: str = "engineering") -> str:
    """SHACL + OWL-RL conformance check WITH deterministic Tier-0 repair (no LLM) of ad-hoc
    case TTL. Runs the validate-repair loop with Tier-0 only (defer a disjoint-core clash to the
    property-domain category, etc.), and returns the repaired TTL, whether it now conforms, the
    number of repairs applied, and any residual violations the deterministic tier could not fix.
    The pre-commit gate path: ProEthica calls this after materialising edges and before persisting
    a case, writes the repaired TTL back, and (until the LLM repair tiers are wired) flags any
    residual for the pilot. The LLM tiers (Haiku->Sonnet->Opus) run caller-side, not here, because
    this server has no model key."""
    from validation import conformance_loop as cl
    from validation import conformance as cf

    def _run():
        r = cl.repair_loop(ttl_content, domain=domain, llm_repair=None)
        remaining = {"violations": []}
        if not r.conforms:
            rep = cf.conformance_report_content("repaired", r.case_content)
            remaining = {"violations": rep.get("violations", [])} if isinstance(rep, dict) else {"violations": []}
        return {
            "conforms": r.conforms,
            "repairs_applied": r.repairs_applied,
            "reason": r.reason,
            "repaired_ttl": r.case_content,
            "remaining": remaining,
        }

    result = await asyncio.to_thread(_run)
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
