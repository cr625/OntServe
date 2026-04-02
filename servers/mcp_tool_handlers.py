"""
MCP Tool Handler Implementations

Contains the business logic for each MCP tool. The OntServeMCPServer
delegates call_tool requests to this class.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional

from storage.postgresql_storage import StorageError
from servers.mcp_source_text_integration import enhance_entity_submission_with_source_text
from core.entity_patterns import infer_category_from_type, build_ontology_priority_sql

logger = logging.getLogger(__name__)


class MCPToolHandlers:
    """Handler implementations for all MCP tools.

    Each public async method corresponds to one MCP tool and accepts
    the ``arguments`` dict from the JSON-RPC call_tool request.
    """

    def __init__(self, concept_manager, storage, sparql_service,
                 wolfram_service, source_text_manager, db_connected: bool):
        self.concept_manager = concept_manager
        self.storage = storage
        self.sparql_service = sparql_service
        self.wolfram_service = wolfram_service
        self.source_text_manager = source_text_manager
        self.db_connected = db_connected

    # ------------------------------------------------------------------
    # get_entities_by_category
    # ------------------------------------------------------------------

    async def handle_get_entities_by_category(self, arguments: dict) -> dict:
        """Get ontology entities by category."""
        category = arguments.get("category")
        domain_id = arguments.get("domain_id", "engineering-ethics")
        status = arguments.get("status", "approved")

        logger.debug(
            "Getting %s entities from domain %s with status %s",
            category, domain_id, status,
        )

        if not self.db_connected or not self.concept_manager:
            return {
                "error": "Database not connected",
                "entities": [],
                "category": category,
                "domain_id": domain_id,
                "status": status,
                "total_count": 0,
            }

        try:
            return await asyncio.to_thread(
                self.concept_manager.get_entities_by_category,
                category, domain_id, status,
            )
        except StorageError as e:
            logger.error("Storage error getting entities: %s", e)
            return {
                "error": f"Failed to retrieve entities: {e}",
                "entities": [],
                "category": category,
                "domain_id": domain_id,
                "status": status,
                "total_count": 0,
            }

    # ------------------------------------------------------------------
    # sparql_query
    # ------------------------------------------------------------------

    async def handle_sparql_query(self, arguments: dict) -> dict:
        """Execute SPARQL query."""
        query = arguments.get("query")
        domain_id = arguments.get("domain_id", "engineering-ethics")

        logger.debug("Executing SPARQL query on domain %s: %s", domain_id, query)

        if not self.sparql_service:
            return {
                "error": "SPARQL service not available",
                "query": query,
                "domain_id": domain_id,
            }

        try:
            start_time = time.time()
            results = await asyncio.to_thread(self.sparql_service.execute_query, query)
            execution_time_ms = int((time.time() - start_time) * 1000)

            return {
                "results": results.get("results", {}),
                "query": query,
                "domain_id": domain_id,
                "execution_time_ms": execution_time_ms,
                "message": "SPARQL query executed successfully",
            }
        except Exception as e:
            logger.error("SPARQL query execution failed: %s", e)
            return {"error": str(e), "query": query, "domain_id": domain_id}

    # ------------------------------------------------------------------
    # wolfram_lookup
    # ------------------------------------------------------------------

    async def handle_wolfram_lookup(self, arguments: dict) -> dict:
        """Look up a concept or term via Wolfram AgentOne."""
        query = arguments.get("query", "")
        context = arguments.get("context", "")

        if not query:
            return {"error": "Query is required", "query": query}

        if not self.wolfram_service:
            return {
                "error": "Wolfram service not available",
                "query": query,
            }

        if not self.wolfram_service.is_configured:
            return {
                "error": "Wolfram API key not configured",
                "query": query,
            }

        if context:
            formatted_query = f"In the context of {context}: {query}"
        else:
            formatted_query = query

        logger.debug("Wolfram lookup: %s", formatted_query)

        try:
            start_time = time.time()
            result = await asyncio.to_thread(
                self.wolfram_service.query, formatted_query
            )
            execution_time_ms = int((time.time() - start_time) * 1000)

            if not result.get("success"):
                return {
                    "error": result.get("error", "Wolfram query failed"),
                    "query": query,
                    "execution_time_ms": execution_time_ms,
                }

            return {
                "content": result.get("content", ""),
                "query": query,
                "context": context,
                "model": result.get("model", "AgentOne"),
                "execution_time_ms": execution_time_ms,
                "message": "Wolfram lookup completed successfully",
            }
        except Exception as e:
            logger.error("Wolfram lookup failed: %s", e)
            return {"error": str(e), "query": query}

    # ------------------------------------------------------------------
    # submit_candidate_concept
    # ------------------------------------------------------------------

    async def handle_submit_candidate_concept(self, arguments: dict) -> dict:
        """Submit a candidate concept."""
        concept = arguments.get("concept")
        domain_id = arguments.get("domain_id", "engineering-ethics")
        submitted_by = arguments.get("submitted_by", "proethica-extractor")

        logger.info(
            "Submitting candidate concept: %s in domain %s",
            concept["label"], domain_id,
        )

        if not self.db_connected or not self.concept_manager:
            return {"error": "Database not connected"}

        try:
            return await asyncio.to_thread(
                self.concept_manager.submit_candidate_concept,
                concept, domain_id, submitted_by,
            )
        except StorageError as e:
            logger.error("Storage error submitting concept: %s", e)
            return {"error": f"Failed to submit concept: {e}"}

    # ------------------------------------------------------------------
    # update_concept_status
    # ------------------------------------------------------------------

    async def handle_update_concept_status(self, arguments: dict) -> dict:
        """Update concept status."""
        concept_id = arguments.get("concept_id")
        status = arguments.get("status")
        user = arguments.get("user")
        reason = arguments.get("reason", "")

        logger.info(
            "Updating concept %s status to %s by %s", concept_id, status, user,
        )

        if not self.db_connected or not self.concept_manager:
            return {"error": "Database not connected"}

        try:
            return await asyncio.to_thread(
                self.concept_manager.update_concept_status,
                concept_id, status, user, reason,
            )
        except StorageError as e:
            logger.error("Storage error updating concept status: %s", e)
            return {"error": f"Failed to update concept status: {e}"}

    # ------------------------------------------------------------------
    # get_candidate_concepts
    # ------------------------------------------------------------------

    async def handle_get_candidate_concepts(self, arguments: dict) -> dict:
        """Get candidate concepts for review."""
        domain_id = arguments.get("domain_id", "engineering-ethics")
        category = arguments.get("category")
        status = arguments.get("status", "candidate")

        logger.debug(
            "Getting candidate concepts from domain %s, category: %s, status: %s",
            domain_id, category, status,
        )

        if not self.db_connected or not self.concept_manager:
            return {
                "error": "Database not connected",
                "candidates": [],
                "domain_id": domain_id,
                "filters": {"category": category, "status": status},
                "total_count": 0,
            }

        try:
            return await asyncio.to_thread(
                self.concept_manager.get_candidate_concepts,
                domain_id, category, status,
            )
        except StorageError as e:
            logger.error("Storage error getting candidate concepts: %s", e)
            return {
                "error": f"Failed to retrieve candidate concepts: {e}",
                "candidates": [],
                "domain_id": domain_id,
                "filters": {"category": category, "status": status},
                "total_count": 0,
            }

    # ------------------------------------------------------------------
    # get_domain_info
    # ------------------------------------------------------------------

    async def handle_get_domain_info(self, arguments: dict) -> dict:
        """Get domain information."""
        domain_id = arguments.get("domain_id", "engineering-ethics")

        if not self.db_connected or not self.concept_manager:
            return {"error": "Database not connected"}

        try:
            return await asyncio.to_thread(
                self.concept_manager.get_domain_info, domain_id,
            )
        except StorageError as e:
            logger.error("Storage error getting domain info: %s", e)
            return {"error": f"Failed to retrieve domain info: {e}"}

    # ------------------------------------------------------------------
    # store_extracted_entities
    # ------------------------------------------------------------------

    async def handle_store_extracted_entities(self, arguments: dict) -> dict:
        """Store extracted entities with source text provenance in OntServe."""
        case_id = arguments.get("case_id")
        section_type = arguments.get("section_type")
        entities = arguments.get("entities", [])
        extraction_session = arguments.get("extraction_session", {})

        if not self.db_connected or not self.concept_manager:
            return {"error": "Database not connected"}

        try:
            stored_entities = []
            domain_id = "engineering-ethics"
            submitted_by = f"proethica-case-{case_id}-{section_type}"

            for entity in entities:
                label = entity.get("label", "")
                safe_label = (
                    label.replace(" ", "_")
                    .replace("-", "_")
                    .replace("(", "")
                    .replace(")", "")
                )
                entity_uri = (
                    f"http://proethica.org/ontology/case/{case_id}"
                    f"#{section_type}_{safe_label}"
                )

                entity_data = {
                    "label": entity.get("label", ""),
                    "description": entity.get("description", ""),
                    "category": entity.get("category", "Entity"),
                    "uri": entity_uri,
                    "confidence": entity.get("confidence", 0.8),
                    "source_text": entity.get("source_text", ""),
                    "extracted_from_section": section_type,
                    "extraction_timestamp": datetime.now(),
                    "extractor_name": submitted_by,
                    "extraction_method": "case_entity_extraction",
                    "domain_id": domain_id,
                    "submitted_by": submitted_by,
                    "case_id": case_id,
                    "metadata": {
                        "extraction_session": extraction_session,
                        "extraction_metadata": entity.get("extraction_metadata", {}),
                        "nspe_case_entity": True,
                    },
                }

                result = await asyncio.to_thread(
                    enhance_entity_submission_with_source_text,
                    self.concept_manager,
                    self.source_text_manager,
                    entity_data,
                    case_id,
                )

                if result.get("success"):
                    stored_entities.append({
                        "label": entity.get("label", ""),
                        "category": entity.get("category", "Entity"),
                        "section_type": section_type,
                        "concept_id": result.get("concept_id"),
                        "status": "candidate",
                        "source_text_stored": result.get("source_text_stored", False),
                        "triples_count": result.get("triples_count", 0),
                    })
                else:
                    logger.warning(
                        "Failed to store entity %s: %s",
                        entity.get("label", ""),
                        result.get("error", "Unknown error"),
                    )

            logger.info(
                "Stored %d entities with provenance for case %s, section %s",
                len(stored_entities), case_id, section_type,
            )

            return {
                "success": True,
                "case_id": case_id,
                "section_type": section_type,
                "stored_count": len(stored_entities),
                "entities": stored_entities,
                "method": "candidate_concepts_with_provenance",
            }

        except Exception as e:
            logger.error("Error storing extracted entities: %s", e)
            return {"error": f"Failed to store entities: {e}"}

    # ------------------------------------------------------------------
    # get_case_entities
    # ------------------------------------------------------------------

    async def handle_get_case_entities(self, arguments: dict) -> dict:
        """Retrieve stored entities for a specific case."""
        case_id = arguments.get("case_id")
        section_type = arguments.get("section_type")
        category = arguments.get("category")

        if not self.db_connected or not self.concept_manager:
            return {"error": "Database not connected"}

        try:
            submitted_by_pattern = f"proethica-case-{case_id}"
            if section_type:
                submitted_by_pattern += f"-{section_type}"

            result = await asyncio.to_thread(
                self.concept_manager.get_candidate_concepts,
                domain_id="engineering-ethics",
                status="candidate",
                submitted_by_like=submitted_by_pattern,
            )

            entities = result.get("candidates", [])

            if category:
                entities = [
                    e for e in entities if e.get("category", "") == category
                ]
            if section_type:
                entities = [
                    e for e in entities
                    if e.get("metadata", {}).get("section_type") == section_type
                ]

            return {
                "case_id": case_id,
                "entities": entities,
                "total_count": len(entities),
                "filters": {"section_type": section_type, "category": category},
                "method": "candidate_concepts",
            }

        except Exception as e:
            logger.error("Error retrieving case entities: %s", e)
            return {"error": f"Failed to retrieve entities: {e}"}

    # ------------------------------------------------------------------
    # get_entity_by_uri
    # ------------------------------------------------------------------

    async def handle_get_entity_by_uri(self, arguments: dict) -> dict:
        """Retrieve an entity's definition and metadata by its URI."""
        uri = arguments.get("uri")
        include_properties = arguments.get("include_properties", False)

        if not uri:
            return {"error": "URI is required"}

        if not self.db_connected or not self.storage:
            return {"error": "Database not connected"}

        logger.debug("Looking up entity by URI: %s", uri)

        try:
            query = """
                SELECT
                    e.uri,
                    e.label,
                    e.comment,
                    e.entity_type,
                    e.parent_uri,
                    e.properties,
                    o.name as source_ontology
                FROM ontology_entities e
                JOIN ontologies o ON e.ontology_id = o.id
                WHERE e.uri = %s
                LIMIT 1
            """
            result = await asyncio.to_thread(
                self.storage._execute_query, query, (uri,), fetch_one=True,
            )

            if not result and "#" in uri:
                fragment = uri.split("#")[-1]
                query_fragment = """
                    SELECT
                        e.uri,
                        e.label,
                        e.comment,
                        e.entity_type,
                        e.parent_uri,
                        e.properties,
                        o.name as source_ontology
                    FROM ontology_entities e
                    JOIN ontologies o ON e.ontology_id = o.id
                    WHERE e.uri LIKE %s
                    ORDER BY o.name
                    LIMIT 1
                """
                result = await asyncio.to_thread(
                    self.storage._execute_query,
                    query_fragment, (f"%#{fragment}",), fetch_one=True,
                )

            if not result:
                return {"error": "Entity not found", "uri": uri, "found": False}

            return self._format_entity_result(result, include_properties)

        except Exception as e:
            logger.error("Error looking up entity by URI: %s", e)
            return {"error": f"Failed to retrieve entity: {e}", "uri": uri}

    # ------------------------------------------------------------------
    # get_entities_by_uris
    # ------------------------------------------------------------------

    async def handle_get_entities_by_uris(self, arguments: dict) -> dict:
        """Retrieve definitions for multiple entities at once (max 20)."""
        uris = arguments.get("uris", [])

        if not uris:
            return {"error": "URIs list is required", "entities": [], "not_found": []}

        if len(uris) > 20:
            uris = uris[:20]
            logger.warning("Truncated URIs list to 20 items")

        if not self.db_connected or not self.storage:
            return {
                "error": "Database not connected",
                "entities": [],
                "not_found": uris,
            }

        logger.debug("Looking up %d entities by URI", len(uris))

        # Batch query: single round-trip for all URIs
        query = """
            SELECT
                e.uri,
                e.label,
                e.comment,
                e.entity_type,
                e.parent_uri,
                e.properties,
                o.name as source_ontology
            FROM ontology_entities e
            JOIN ontologies o ON e.ontology_id = o.id
            WHERE e.uri = ANY(%s)
        """
        rows = await asyncio.to_thread(
            self.storage._execute_query, query, (uris,), fetch_all=True,
        ) or []
        found_by_uri = {row["uri"]: row for row in rows}

        entities = []
        not_found = []

        for uri in uris:
            if uri in found_by_uri:
                formatted = self._format_entity_result(found_by_uri[uri])
                formatted.pop("found", None)
                entities.append(formatted)
            elif "#" in uri:
                # Fragment fallback for URIs with different base but same fragment
                result = await self.handle_get_entity_by_uri({"uri": uri})
                if result.get("found"):
                    result.pop("found", None)
                    entities.append(result)
                else:
                    not_found.append(uri)
            else:
                not_found.append(uri)

        return {
            "entities": entities,
            "found_count": len(entities),
            "not_found": not_found,
            "not_found_count": len(not_found),
        }

    # ------------------------------------------------------------------
    # get_entity_by_label
    # ------------------------------------------------------------------

    async def handle_get_entity_by_label(self, arguments: dict) -> dict:
        """Retrieve an entity's definition and metadata by its label."""
        label = arguments.get("label")

        if not label:
            return {"error": "Label is required"}

        if not self.db_connected or not self.storage:
            return {"error": "Database not connected"}

        logger.debug("Looking up entity by label: %s", label)

        try:
            priority_sql = build_ontology_priority_sql()
            query = f"""
                SELECT
                    e.uri,
                    e.label,
                    e.comment,
                    e.entity_type,
                    e.parent_uri,
                    e.properties,
                    o.name as source_ontology
                FROM ontology_entities e
                JOIN ontologies o ON e.ontology_id = o.id
                WHERE LOWER(e.label) = LOWER(%s)
                ORDER BY {priority_sql}
                LIMIT 1
            """
            result = await asyncio.to_thread(
                self.storage._execute_query, query, (label,), fetch_one=True,
            )

            if not result:
                return {"error": "Entity not found", "label": label, "found": False}

            return self._format_entity_result(result)

        except Exception as e:
            logger.error("Error looking up entity by label: %s", e)
            return {"error": f"Failed to retrieve entity: {e}", "label": label}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_entity_result(self, result: dict,
                              include_properties: bool = False) -> dict:
        """Format a raw DB entity row into the standard MCP response dict."""
        uri = result.get("uri", "")
        definition = result.get("comment") or ""
        properties = result.get("properties") or {}

        if not definition and properties:
            definition = self._extract_definition_from_properties(properties)

        entity_type = result.get("entity_type") or "individual"
        parent_uri = result.get("parent_uri") or ""
        category = infer_category_from_type(entity_type, parent_uri, uri)

        label = result.get("label")
        if not label:
            label = uri.split("#")[-1] if "#" in uri else uri.split("/")[-1]

        response = {
            "uri": uri,
            "label": label,
            "definition": definition,
            "entity_type": category,
            "parent_type": parent_uri,
            "source_ontology": result.get("source_ontology"),
            "found": True,
        }

        if include_properties and properties:
            response["properties"] = properties

        return response

    @staticmethod
    def _extract_definition_from_properties(properties: dict) -> str:
        """Extract a definition string from entity RDF properties."""
        definition_keys = [
            "obligationstatement", "proeth:obligationstatement",
            "sourcetext", "proeth:sourcetext",
            "casecontext", "proeth:casecontext",
            "ethicaltension", "proeth:ethicaltension",
            "comment", "rdfs:comment",
            "definition", "skos:definition",
            "description",
        ]
        for key in definition_keys:
            if key in properties and properties[key]:
                val = properties[key]
                if isinstance(val, list):
                    return val[0] if val else ""
                return str(val)
        return ""

