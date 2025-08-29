"""
Concept Management Tools Module for OntServe MCP Server.

Provides tools for managing candidate concepts, approval workflows,
and concept status updates for the ProEthica integration.
"""

from typing import Dict, List, Any
import logging

from .base_tool import DatabaseRequiredTool

logger = logging.getLogger(__name__)


class SubmitCandidateConcept(DatabaseRequiredTool):
    """Submit a candidate concept extracted by ProEthica."""
    
    name = "submit_candidate_concept"
    description = "Submit a candidate concept extracted by ProEthica"
    schema = {
        "type": "object",
        "properties": {
            "concept": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string", 
                        "description": "Concept label with type suffix"
                    },
                    "category": {
                        "type": "string", 
                        "description": "Concept category"
                    },
                    "description": {
                        "type": "string", 
                        "description": "Concept description"
                    },
                    "uri": {
                        "type": "string", 
                        "description": "Concept URI"
                    },
                    "confidence_score": {
                        "type": "number", 
                        "description": "Extraction confidence (0.0-1.0)",
                        "minimum": 0.0,
                        "maximum": 1.0
                    },
                    "source_document": {
                        "type": "string", 
                        "description": "Source document identifier"
                    },
                    "extraction_method": {
                        "type": "string", 
                        "description": "Extraction method used"
                    },
                    "llm_reasoning": {
                        "type": "string", 
                        "description": "LLM reasoning for extraction"
                    }
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
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute candidate concept submission."""
        concept = arguments.get("concept")
        domain_id = arguments.get("domain_id", "engineering-ethics")
        submitted_by = arguments.get("submitted_by", "proethica-extractor")
        
        concept_label = concept.get("label", "Unknown")
        logger.info(f"Submitting candidate concept: {concept_label} in domain {domain_id}")
        
        try:
            # Use concept manager to submit candidate
            result = self.concept_manager.submit_candidate_concept(concept, domain_id, submitted_by)
            
            # Add submission metadata
            result["submission_info"] = {
                "domain_id": domain_id,
                "submitted_by": submitted_by,
                "concept_label": concept_label,
                "concept_category": concept.get("category"),
                "confidence_score": concept.get("confidence_score")
            }
            
            return self.format_success_response(result)
            
        except Exception as e:
            return self.format_error_response(
                f"Failed to submit candidate concept '{concept_label}': {str(e)}",
                error_code="CONCEPT_SUBMISSION_FAILED"
            )


class UpdateConceptStatus(DatabaseRequiredTool):
    """Update the status of a candidate concept (approve/reject)."""
    
    name = "update_concept_status"
    description = "Update the status of a candidate concept (approve/reject)"
    schema = {
        "type": "object",
        "properties": {
            "concept_id": {
                "type": "string",
                "description": "Concept identifier (UUID or database ID)"
            },
            "status": {
                "type": "string",
                "description": "New status for the concept",
                "enum": ["approved", "rejected", "deprecated"]
            },
            "user": {
                "type": "string",
                "description": "User making the status change"
            },
            "reason": {
                "type": "string",
                "description": "Reason for status change"
            },
            "reviewer_notes": {
                "type": "string",
                "description": "Additional reviewer notes",
                "default": ""
            }
        },
        "required": ["concept_id", "status", "user"]
    }
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute concept status update."""
        concept_id = arguments.get("concept_id")
        status = arguments.get("status")
        user = arguments.get("user")
        reason = arguments.get("reason", "")
        reviewer_notes = arguments.get("reviewer_notes", "")
        
        logger.info(f"Updating concept {concept_id} status to {status} by {user}")
        
        try:
            # Use concept manager to update status
            result = self.concept_manager.update_concept_status(
                concept_id, status, user, reason
            )
            
            # Add update metadata
            result["update_info"] = {
                "concept_id": concept_id,
                "new_status": status,
                "updated_by": user,
                "reason": reason,
                "reviewer_notes": reviewer_notes
            }
            
            return self.format_success_response(result)
            
        except Exception as e:
            return self.format_error_response(
                f"Failed to update concept status for {concept_id}: {str(e)}",
                error_code="STATUS_UPDATE_FAILED"
            )


class GetCandidateConcepts(DatabaseRequiredTool):
    """Retrieve candidate concepts for review."""
    
    name = "get_candidate_concepts"
    description = "Retrieve candidate concepts for review"
    schema = {
        "type": "object",
        "properties": {
            "domain_id": {
                "type": "string",
                "description": "Professional domain identifier",
                "default": "engineering-ethics"
            },
            "category": {
                "type": "string",
                "description": "Filter by concept category (optional)",
                "enum": ["Role", "Principle", "Obligation", "State", "Resource", 
                        "Action", "Event", "Capability", "Constraint"]
            },
            "status": {
                "type": "string", 
                "description": "Filter by concept status",
                "enum": ["candidate", "approved", "rejected", "deprecated"],
                "default": "candidate"
            },
            "submitted_by": {
                "type": "string",
                "description": "Filter by submitter (optional)"
            },
            "min_confidence": {
                "type": "number",
                "description": "Minimum confidence score (0.0-1.0)",
                "minimum": 0.0,
                "maximum": 1.0
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 100,
                "maximum": 1000
            },
            "order_by": {
                "type": "string",
                "description": "Sort order for results",
                "enum": ["created_at", "confidence_score", "label", "category"],
                "default": "created_at"
            },
            "order_direction": {
                "type": "string",
                "enum": ["asc", "desc"],
                "default": "desc"
            }
        },
        "required": ["domain_id"]
    }
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute candidate concepts retrieval."""
        domain_id = arguments.get("domain_id", "engineering-ethics")
        category = arguments.get("category")
        status = arguments.get("status", "candidate")
        submitted_by = arguments.get("submitted_by")
        min_confidence = arguments.get("min_confidence")
        max_results = arguments.get("max_results", 100)
        order_by = arguments.get("order_by", "created_at")
        order_direction = arguments.get("order_direction", "desc")
        
        logger.debug(f"Getting candidate concepts from domain {domain_id}, "
                    f"category: {category}, status: {status}")
        
        try:
            # Use concept manager with enhanced filtering
            result = await self._get_candidate_concepts_with_filters(
                domain_id=domain_id,
                category=category,
                status=status,
                submitted_by=submitted_by,
                min_confidence=min_confidence,
                max_results=max_results,
                order_by=order_by,
                order_direction=order_direction
            )
            
            # Add query metadata
            result["query_info"] = {
                "domain_id": domain_id,
                "filters": {
                    "category": category,
                    "status": status,
                    "submitted_by": submitted_by,
                    "min_confidence": min_confidence
                },
                "pagination": {
                    "max_results": max_results,
                    "order_by": order_by,
                    "order_direction": order_direction
                }
            }
            
            return self.format_success_response(result)
            
        except Exception as e:
            return self.format_error_response(
                f"Failed to retrieve candidate concepts: {str(e)}",
                error_code="CANDIDATE_RETRIEVAL_FAILED"
            )
    
    async def _get_candidate_concepts_with_filters(self, domain_id: str, category: str = None,
                                                  status: str = "candidate", submitted_by: str = None,
                                                  min_confidence: float = None, max_results: int = 100,
                                                  order_by: str = "created_at", 
                                                  order_direction: str = "desc") -> Dict[str, Any]:
        """Get candidate concepts with advanced filtering."""
        try:
            # If concept manager has enhanced filtering, use it
            if hasattr(self.concept_manager, 'get_candidate_concepts_filtered'):
                return self.concept_manager.get_candidate_concepts_filtered(
                    domain_id=domain_id,
                    category=category,
                    status=status,
                    submitted_by=submitted_by,
                    min_confidence=min_confidence,
                    max_results=max_results,
                    order_by=order_by,
                    order_direction=order_direction
                )
            else:
                # Fallback to basic method
                return self.concept_manager.get_candidate_concepts(domain_id, category, status)
                
        except Exception as e:
            logger.error(f"Error getting candidate concepts with filters: {e}")
            raise


class BatchUpdateConcepts(DatabaseRequiredTool):
    """Batch update multiple concepts for efficiency."""
    
    name = "batch_update_concepts"
    description = "Update status of multiple candidate concepts in a single operation"
    schema = {
        "type": "object",
        "properties": {
            "updates": {
                "type": "array",
                "description": "Array of concept updates",
                "items": {
                    "type": "object",
                    "properties": {
                        "concept_id": {"type": "string"},
                        "status": {"type": "string", "enum": ["approved", "rejected", "deprecated"]},
                        "reason": {"type": "string", "default": ""}
                    },
                    "required": ["concept_id", "status"]
                },
                "minItems": 1,
                "maxItems": 100
            },
            "user": {
                "type": "string",
                "description": "User making the batch update"
            },
            "domain_id": {
                "type": "string",
                "default": "engineering-ethics"
            }
        },
        "required": ["updates", "user"]
    }
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute batch concept status updates."""
        updates = arguments.get("updates", [])
        user = arguments.get("user")
        domain_id = arguments.get("domain_id", "engineering-ethics")
        
        logger.info(f"Batch updating {len(updates)} concepts by {user}")
        
        try:
            results = {
                "successful_updates": [],
                "failed_updates": [],
                "total_requested": len(updates),
                "total_successful": 0,
                "total_failed": 0
            }
            
            # Process each update
            for update in updates:
                concept_id = update.get("concept_id")
                status = update.get("status")
                reason = update.get("reason", "")
                
                try:
                    # Use concept manager for individual update
                    result = self.concept_manager.update_concept_status(
                        concept_id, status, user, reason
                    )
                    
                    results["successful_updates"].append({
                        "concept_id": concept_id,
                        "status": status,
                        "result": result
                    })
                    results["total_successful"] += 1
                    
                except Exception as e:
                    logger.error(f"Failed to update concept {concept_id}: {e}")
                    results["failed_updates"].append({
                        "concept_id": concept_id,
                        "status": status,
                        "error": str(e)
                    })
                    results["total_failed"] += 1
            
            # Add batch operation metadata
            results["batch_info"] = {
                "domain_id": domain_id,
                "updated_by": user,
                "success_rate": results["total_successful"] / len(updates) * 100
            }
            
            return self.format_success_response(results)
            
        except Exception as e:
            return self.format_error_response(
                f"Batch update operation failed: {str(e)}",
                error_code="BATCH_UPDATE_FAILED"
            )