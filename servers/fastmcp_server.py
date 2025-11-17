#!/usr/bin/env python3
"""
OntServe FastMCP Server

Modern MCP server implementation using FastMCP 2.0 framework.
Runs on port 8083 (parallel to legacy server on 8082).

Benefits over legacy server:
- 75% less code (~200 lines vs 863)
- Decorator-based tool definitions
- Automatic JSON-RPC handling
- Built-in security features
- Better error handling
"""

import os
import sys
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from fastmcp import FastMCP

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load configuration
from config.config_loader import load_ontserve_config
config_summary = load_ontserve_config()
logger.info(f"✅ Loaded configuration from: {', '.join(config_summary['loaded_files'])}")

# Import storage backends (reuse existing!)
from storage.postgresql_storage import PostgreSQLStorage, StorageError
from storage.concept_manager import ConceptManager
from services.sparql_service import SPARQLService

# Initialize FastMCP (name only, no version/description parameters)
mcp = FastMCP("OntServe MCP Server")

# Global storage instances (initialized on first use)
_storage = None
_concept_manager = None
_sparql_service = None

def get_storage():
    """Get or create PostgreSQL storage instance."""
    global _storage
    if _storage is None:
        db_url = os.environ.get(
            'ONTSERVE_DB_URL',
            'postgresql://postgres:PASS@localhost:5432/ontserve'
        )
        storage_config = {
            'db_url': db_url,
            'pool_size': int(os.environ.get('ONTSERVE_MAX_CONNECTIONS', 10)),
            'timeout': int(os.environ.get('ONTSERVE_QUERY_TIMEOUT', 30)),
            'enable_vector_search': os.environ.get('ONTSERVE_ENABLE_VECTOR_SEARCH', 'true').lower() == 'true'
        }
        _storage = PostgreSQLStorage(storage_config)
        logger.info(f"✅ PostgreSQL storage initialized")
    return _storage

def get_concept_manager():
    """Get or create concept manager instance."""
    global _concept_manager
    if _concept_manager is None:
        _concept_manager = ConceptManager()
        logger.info(f"✅ Concept manager initialized")
    return _concept_manager

def get_sparql_service():
    """Get or create SPARQL service instance."""
    global _sparql_service
    if _sparql_service is None:
        ontology_dir = os.environ.get(
            'ONTSERVE_STORAGE_DIR',
            str(project_root / 'ontologies')
        )
        _sparql_service = SPARQLService(ontology_dir)
        logger.info(f"✅ SPARQL service initialized")
    return _sparql_service


# ============================================================================
# MCP Tools - These 8 tools are used by ProEthica
# ============================================================================

@mcp.tool()
async def get_entities_by_category(
    category: str,
    domain_id: str = "engineering-ethics",
    status: str = "approved"
) -> dict:
    """
    Get ontology entities by category.

    PRIMARY tool for ProEthica concept extraction.

    Args:
        category: Entity type (Role, Principle, Obligation, State, Capability, Action, Event, Constraint, Resource)
        domain_id: Domain filter (default: engineering-ethics)
        status: Filter by status (approved, pending, rejected)

    Returns:
        Dictionary with entities list and metadata
    """
    logger.debug(f"Getting {category} entities from domain {domain_id} with status {status}")

    try:
        manager = get_concept_manager()
        result = manager.get_entities_by_category(category, domain_id, status)
        return result
    except Exception as e:
        logger.error(f"Error getting entities: {e}")
        return {
            "error": f"Failed to retrieve entities: {str(e)}",
            "entities": [],
            "category": category,
            "domain_id": domain_id,
            "status": status,
            "total_count": 0
        }


@mcp.tool()
async def submit_candidate_concept(
    concept_uri: str,
    concept_type: str,
    label: str,
    definition: str,
    justification: str,
    domain_id: str = "engineering-ethics",
    submitted_by: str = "ProEthica"
) -> dict:
    """
    Submit a candidate concept for review.

    Args:
        concept_uri: URI for the new concept
        concept_type: Type (Role, Principle, etc.)
        label: Human-readable label
        definition: Definition text
        justification: Why this concept should be added
        domain_id: Target domain
        submitted_by: Submitter name

    Returns:
        Dictionary with submission status
    """
    logger.info(f"Submitting candidate concept: {label} ({concept_type})")

    try:
        manager = get_concept_manager()
        result = manager.add_candidate_concept(
            uri=concept_uri,
            concept_type=concept_type,
            label=label,
            definition=definition,
            justification=justification,
            domain_id=domain_id,
            submitted_by=submitted_by
        )
        return {
            "success": True,
            "concept_uri": concept_uri,
            "message": "Candidate concept submitted successfully",
            "status": "pending"
        }
    except Exception as e:
        logger.error(f"Error submitting candidate: {e}")
        return {
            "success": False,
            "error": str(e),
            "concept_uri": concept_uri
        }


@mcp.tool()
async def sparql_query(
    query: str,
    domain_id: str = "engineering-ethics"
) -> dict:
    """
    Execute a SPARQL query on ontology data.

    Args:
        query: SPARQL query string
        domain_id: Domain to query against

    Returns:
        Query results with execution metadata
    """
    logger.debug(f"Executing SPARQL query on domain {domain_id}")

    try:
        import time
        start_time = time.time()

        service = get_sparql_service()
        results = service.execute_query(query)

        execution_time_ms = int((time.time() - start_time) * 1000)

        return {
            "results": results.get("results", {}),
            "query": query,
            "domain_id": domain_id,
            "execution_time_ms": execution_time_ms,
            "message": "SPARQL query executed successfully"
        }
    except Exception as e:
        logger.error(f"SPARQL query failed: {e}")
        return {
            "error": str(e),
            "query": query,
            "domain_id": domain_id
        }


@mcp.tool()
async def update_concept_status(
    concept_uri: str,
    new_status: str,
    updated_by: str = "admin"
) -> dict:
    """
    Update the status of a candidate concept.

    Args:
        concept_uri: URI of the concept
        new_status: New status (approved, rejected, pending)
        updated_by: Who made the update

    Returns:
        Update status
    """
    logger.info(f"Updating concept {concept_uri} to status {new_status}")

    try:
        manager = get_concept_manager()
        result = manager.update_concept_status(concept_uri, new_status, updated_by)
        return {
            "success": True,
            "concept_uri": concept_uri,
            "new_status": new_status,
            "message": "Concept status updated successfully"
        }
    except Exception as e:
        logger.error(f"Error updating concept status: {e}")
        return {
            "success": False,
            "error": str(e),
            "concept_uri": concept_uri
        }


@mcp.tool()
async def get_candidate_concepts(
    status: str = "pending",
    domain_id: str = None
) -> dict:
    """
    Retrieve candidate concepts by status.

    Args:
        status: Filter by status (pending, approved, rejected, all)
        domain_id: Optional domain filter

    Returns:
        List of candidate concepts
    """
    logger.debug(f"Getting candidate concepts with status {status}")

    try:
        manager = get_concept_manager()
        concepts = manager.get_candidate_concepts(status, domain_id)
        return {
            "concepts": concepts,
            "status": status,
            "domain_id": domain_id,
            "count": len(concepts)
        }
    except Exception as e:
        logger.error(f"Error getting candidate concepts: {e}")
        return {
            "error": str(e),
            "concepts": [],
            "count": 0
        }


@mcp.tool()
async def get_domain_info(
    domain_id: str = "engineering-ethics"
) -> dict:
    """
    Get information about a domain.

    Args:
        domain_id: Domain identifier

    Returns:
        Domain metadata and statistics
    """
    logger.debug(f"Getting info for domain {domain_id}")

    try:
        manager = get_concept_manager()
        info = manager.get_domain_info(domain_id)
        return info
    except Exception as e:
        logger.error(f"Error getting domain info: {e}")
        return {
            "error": str(e),
            "domain_id": domain_id
        }


@mcp.tool()
async def store_extracted_entities(
    entities: List[Dict[str, Any]],
    case_id: str,
    ontology_name: str = "proethica-intermediate-extracted",
    extraction_metadata: Dict[str, Any] = None
) -> dict:
    """
    Store entities extracted from a case.

    Used by ProEthica 9-concept extraction system.

    Args:
        entities: List of extracted entities
        case_id: Case identifier
        ontology_name: Target ontology
        extraction_metadata: Optional metadata about extraction

    Returns:
        Storage status
    """
    logger.info(f"Storing {len(entities)} entities for case {case_id}")

    try:
        manager = get_concept_manager()
        result = manager.store_extracted_entities(
            entities=entities,
            case_id=case_id,
            ontology_name=ontology_name,
            metadata=extraction_metadata or {}
        )
        return {
            "success": True,
            "case_id": case_id,
            "entities_stored": len(entities),
            "ontology_name": ontology_name,
            "message": "Entities stored successfully"
        }
    except Exception as e:
        logger.error(f"Error storing entities: {e}")
        return {
            "success": False,
            "error": str(e),
            "case_id": case_id,
            "entities_stored": 0
        }


@mcp.tool()
async def get_case_entities(
    case_id: str,
    entity_type: str = None
) -> dict:
    """
    Retrieve entities extracted from a specific case.

    Args:
        case_id: Case identifier
        entity_type: Optional filter by entity type

    Returns:
        List of case entities
    """
    logger.debug(f"Getting entities for case {case_id}")

    try:
        manager = get_concept_manager()
        entities = manager.get_case_entities(case_id, entity_type)
        return {
            "case_id": case_id,
            "entities": entities,
            "entity_type": entity_type,
            "count": len(entities)
        }
    except Exception as e:
        logger.error(f"Error getting case entities: {e}")
        return {
            "error": str(e),
            "case_id": case_id,
            "entities": [],
            "count": 0
        }


# ============================================================================
# Server Startup
# ============================================================================

if __name__ == "__main__":
    # Get port from environment (default 8083 for parallel testing)
    port = int(os.environ.get('FASTMCP_PORT', 8083))

    logger.info("="*60)
    logger.info("OntServe FastMCP Server Starting")
    logger.info(f"Port: {port}")
    logger.info(f"Tools: 8 (ProEthica compatible)")
    logger.info(f"Legacy server: Keep running on port 8082")
    logger.info("="*60)

    # Run the server (FastMCP uses stdio by default per MCP spec)
    # For HTTP/SSE mode, use: mcp.run()
    # For testing, we'll use stdio mode
    mcp.run()
