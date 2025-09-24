"""
Concept management for OntServe.

Handles candidate concept storage, approval workflows, and semantic search
for concepts extracted by Proethica and other systems.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from uuid import uuid4

from psycopg2.extras import Json
from .postgresql_storage import PostgreSQLStorage, StorageError

logger = logging.getLogger(__name__)


class ConceptManager:
    """
    Manager for concept storage and candidate workflow operations.
    
    Provides high-level operations for concept management, building on
    the PostgreSQL storage backend.
    """
    
    def __init__(self, storage: PostgreSQLStorage):
        """
        Initialize concept manager.
        
        Args:
            storage: PostgreSQL storage backend instance
        """
        self.storage = storage
        logger.info("Concept manager initialized")
    
    def submit_candidate_concept(self, concept_data: Dict[str, Any], 
                                domain_id: str = "engineering-ethics",
                                submitted_by: str = "proethica-extractor") -> Dict[str, Any]:
        """
        Submit a candidate concept for review and approval.
        
        Args:
            concept_data: Dictionary containing concept information:
                - label: Concept label with type suffix
                - category: Concept category (primary_type)
                - description: Concept description
                - uri: Concept URI
                - confidence_score: Extraction confidence (optional)
                - source_document: Source document (optional)
                - extraction_method: Method used for extraction (optional)
                - llm_reasoning: LLM reasoning for extraction (optional)
                - semantic_label: Human-readable semantic description (optional)
            domain_id: Professional domain identifier
            submitted_by: User/system submitting the concept
            
        Returns:
            Dictionary with submission result including concept_id
        """
        try:
            # Validate required fields
            required_fields = ['label', 'category', 'uri']
            for field in required_fields:
                if field not in concept_data:
                    raise StorageError(f"Missing required field: {field}")
            
            # Get domain ID
            domain_db_id = self.storage._get_or_create_domain(domain_id)
            
            # Prepare concept data
            concept_uuid = str(uuid4())
            
            # Extract semantic label from full label if not provided
            semantic_label = concept_data.get('semantic_label')
            if not semantic_label and ' (' in concept_data['label']:
                # Extract semantic part before type suffix
                semantic_label = concept_data['label'].split(' (')[0]
            
            # Insert concept
            query = """
                INSERT INTO concepts (
                    uuid, domain_id, uri, label, semantic_label, primary_type,
                    description, status, confidence_score, extraction_method,
                    source_document, llm_reasoning, created_by, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'candidate', %s, %s, %s, %s, %s, %s)
                RETURNING id, uuid
            """
            
            params = (
                concept_uuid,
                domain_db_id,
                concept_data['uri'],
                concept_data['label'],
                semantic_label,
                concept_data['category'],
                concept_data.get('description'),
                concept_data.get('confidence_score'),
                concept_data.get('extraction_method', 'llm_extraction'),
                concept_data.get('source_document'),
                concept_data.get('llm_reasoning'),
                submitted_by,
                Json(concept_data.get('metadata', {}))
            )
            
            result = self.storage._execute_query(query, params, fetch_one=True)
            concept_id = result['id']
            concept_uuid = result['uuid']
            
            # Insert candidate metadata if provided
            self._insert_candidate_metadata(concept_id, concept_data, submitted_by)
            
            # Create approval workflow
            self._create_approval_workflow(concept_id)
            
            logger.info(f"Candidate concept submitted: {concept_data['label']} ({concept_uuid})")
            
            return {
                'success': True,
                'concept_id': str(concept_uuid),
                'concept_db_id': concept_id,
                'status': 'candidate',
                'domain_id': domain_id,
                'submitted_by': submitted_by,
                'submitted_at': datetime.now().isoformat(),
                'label': concept_data['label'],
                'category': concept_data['category']
            }
            
        except Exception as e:
            logger.error(f"Failed to submit candidate concept: {e}")
            raise StorageError(f"Concept submission failed: {str(e)}")
    
    def update_concept_status(self, concept_id: str, status: str, 
                             user: str, reason: str = "") -> Dict[str, Any]:
        """
        Update the status of a concept (approve/reject/deprecate).
        
        Args:
            concept_id: Concept UUID or database ID
            status: New status (approved, rejected, deprecated)
            user: User making the change
            reason: Reason for status change
            
        Returns:
            Dictionary with update result
        """
        try:
            # Validate status
            valid_statuses = ['approved', 'rejected', 'deprecated']
            if status not in valid_statuses:
                raise StorageError(f"Invalid status: {status}. Must be one of: {valid_statuses}")
            
            # Get current concept
            concept = self._get_concept_by_id(concept_id)
            if not concept:
                raise StorageError(f"Concept not found: {concept_id}")
            
            old_status = concept['status']
            concept_db_id = concept['id']
            
            # Create version history entry
            self._create_concept_version(concept_db_id, concept, ['status'], reason, user)
            
            # Update concept status
            query = """
                UPDATE concepts 
                SET status = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP,
                    approved_by = CASE WHEN %s = 'approved' THEN %s ELSE approved_by END,
                    approved_at = CASE WHEN %s = 'approved' THEN CURRENT_TIMESTAMP ELSE approved_at END
                WHERE id = %s
            """
            
            self.storage._execute_query(
                query, 
                (status, user, status, user, status, concept_db_id)
            )
            
            # Update approval workflow
            self._update_approval_workflow(concept_db_id, status, user, reason)
            
            logger.info(f"Concept {concept_id} status updated from {old_status} to {status} by {user}")
            
            return {
                'success': True,
                'concept_id': concept_id,
                'old_status': old_status,
                'new_status': status,
                'updated_by': user,
                'updated_at': datetime.now().isoformat(),
                'reason': reason
            }
            
        except Exception as e:
            logger.error(f"Failed to update concept status: {e}")
            raise StorageError(f"Status update failed: {str(e)}")
    
    def get_candidate_concepts(self, domain_id: str = "engineering-ethics", 
                              category: Optional[str] = None,
                              status: str = "candidate",
                              limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        Retrieve candidate concepts for review.
        
        Args:
            domain_id: Professional domain identifier
            category: Filter by category (optional)
            status: Filter by status
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            Dictionary with candidate concepts and metadata
        """
        try:
            # Build query with filters
            where_clauses = ["d.name = %s", "c.status = %s"]
            params = [domain_id, status]
            
            if category:
                where_clauses.append("c.primary_type = %s")
                params.append(category)
            
            query = f"""
                SELECT 
                    c.uuid, c.label, c.semantic_label, c.primary_type, c.description,
                    c.uri, c.confidence_score, c.source_document, c.created_by,
                    c.created_at, c.needs_review, c.review_notes, c.metadata,
                    cm.source_text, cm.llm_confidence, cm.extraction_method,
                    cm.llm_reasoning, cm.source_document_title,
                    aw.current_state as workflow_state, aw.assigned_to, aw.priority
                FROM concepts c
                JOIN domains d ON c.domain_id = d.id
                LEFT JOIN candidate_metadata cm ON c.id = cm.concept_id
                LEFT JOIN approval_workflows aw ON c.id = aw.concept_id
                WHERE {' AND '.join(where_clauses)}
                ORDER BY c.created_at DESC
                LIMIT %s OFFSET %s
            """
            
            params.extend([limit, offset])
            results = self.storage._execute_query(query, tuple(params), fetch_all=True)
            
            # Get total count
            count_query = f"""
                SELECT COUNT(*)
                FROM concepts c
                JOIN domains d ON c.domain_id = d.id
                WHERE {' AND '.join(where_clauses[:-2])}
            """
            
            count_params = params[:-2]  # Remove limit and offset
            if category:
                count_params = params[:-3]  # Remove category, limit, offset
                count_query = f"""
                    SELECT COUNT(*)
                    FROM concepts c
                    JOIN domains d ON c.domain_id = d.id
                    WHERE {' AND '.join(where_clauses[:-2])}
                """
            else:
                count_query = f"""
                    SELECT COUNT(*)
                    FROM concepts c
                    JOIN domains d ON c.domain_id = d.id
                    WHERE {' AND '.join(where_clauses)}
                """
                count_params = params[:-2]
            
            total_count = self.storage._execute_query(count_query, tuple(count_params), fetch_one=True)[0]
            
            # Format results
            candidates = []
            for row in results:
                candidate = {
                    'id': str(row['uuid']),
                    'label': row['label'],
                    'semantic_label': row['semantic_label'],
                    'category': row['primary_type'],
                    'description': row['description'],
                    'uri': row['uri'],
                    'confidence_score': float(row['confidence_score']) if row['confidence_score'] else None,
                    'source_document': row['source_document'],
                    'source_text': row['source_text'],
                    'source_document_title': row['source_document_title'],
                    'extraction_method': row['extraction_method'],
                    'llm_confidence': float(row['llm_confidence']) if row['llm_confidence'] else None,
                    'llm_reasoning': row['llm_reasoning'],
                    'needs_review': row['needs_review'],
                    'review_notes': row['review_notes'],
                    'workflow_state': row['workflow_state'],
                    'assigned_to': row['assigned_to'],
                    'priority': row['priority'],
                    'created_by': row['created_by'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'metadata': row['metadata'] or {}
                }
                candidates.append(candidate)
            
            return {
                'candidates': candidates,
                'domain_id': domain_id,
                'filters': {
                    'category': category,
                    'status': status
                },
                'pagination': {
                    'total_count': total_count,
                    'limit': limit,
                    'offset': offset,
                    'has_more': offset + len(candidates) < total_count
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get candidate concepts: {e}")
            raise StorageError(f"Failed to retrieve candidates: {str(e)}")
    
    def get_entities_by_category(self, category: str, domain_id: str = "engineering-ethics",
                                status: str = "approved") -> Dict[str, Any]:
        """
        Get approved entities by category for MCP queries.
        
        Args:
            category: Entity category (Role, Principle, etc.)
            domain_id: Professional domain identifier
            status: Status filter
            
        Returns:
            Dictionary with entities and metadata
        """
        try:
            query = """
                SELECT 
                    c.uuid, c.uri, c.label, c.semantic_label, c.description,
                    c.primary_type, c.confidence_score, c.created_at,
                    c.approved_by, c.approved_at, c.metadata
                FROM concepts c
                JOIN domains d ON c.domain_id = d.id
                WHERE d.name = %s AND c.primary_type = %s AND c.status = %s
                ORDER BY c.label
            """
            
            results = self.storage._execute_query(
                query, 
                (domain_id, category, status), 
                fetch_all=True
            )
            
            entities = []
            for row in results:
                entity = {
                    'id': str(row['uuid']),
                    'uri': row['uri'],
                    'label': row['label'],
                    'semantic_label': row['semantic_label'],
                    'description': row['description'],
                    'category': row['primary_type'],
                    'confidence_score': float(row['confidence_score']) if row['confidence_score'] else None,
                    'status': status,
                    'approved_by': row['approved_by'],
                    'approved_at': row['approved_at'].isoformat() if row['approved_at'] else None,
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'metadata': row['metadata'] or {},
                    'source': 'concepts'
                }
                entities.append(entity)

            # Also get ontology entities for this category
            ontology_entities = self.get_ontology_entities_by_category(category)
            entities.extend(ontology_entities)

            return {
                'entities': entities,
                'category': category,
                'domain_id': domain_id,
                'status': status,
                'total_count': len(entities),
                'concept_count': len(results),
                'ontology_count': len(ontology_entities)
            }
            
        except Exception as e:
            logger.error(f"Failed to get entities by category: {e}")
            raise StorageError(f"Failed to retrieve entities: {str(e)}")
    
    def get_domain_info(self, domain_id: str) -> Dict[str, Any]:
        """
        Get information about a professional domain.
        
        Args:
            domain_id: Professional domain identifier
            
        Returns:
            Dictionary with domain information and statistics
        """
        try:
            # Get domain info
            domain_query = """
                SELECT id, name, display_name, namespace_uri, description, 
                       is_active, created_at, updated_at, metadata
                FROM domains WHERE name = %s
            """
            
            domain = self.storage._execute_query(domain_query, (domain_id,), fetch_one=True)
            if not domain:
                raise StorageError(f"Domain not found: {domain_id}")
            
            # Get concept statistics
            stats_query = """
                SELECT 
                    status,
                    primary_type,
                    COUNT(*) as count
                FROM concepts 
                WHERE domain_id = %s
                GROUP BY status, primary_type
                ORDER BY status, primary_type
            """
            
            stats_results = self.storage._execute_query(stats_query, (domain['id'],), fetch_all=True)
            
            # Aggregate statistics
            stats = {
                'total_concepts': 0,
                'approved_concepts': 0,
                'candidate_concepts': 0,
                'rejected_concepts': 0,
                'by_type': {}
            }
            
            for row in stats_results:
                status = row['status']
                concept_type = row['primary_type']
                count = row['count']
                
                stats['total_concepts'] += count
                
                if status == 'approved':
                    stats['approved_concepts'] += count
                elif status == 'candidate':
                    stats['candidate_concepts'] += count
                elif status == 'rejected':
                    stats['rejected_concepts'] += count
                
                if concept_type not in stats['by_type']:
                    stats['by_type'][concept_type] = {'approved': 0, 'candidate': 0, 'rejected': 0}
                
                stats['by_type'][concept_type][status] = count
            
            return {
                'domain': {
                    'id': domain['id'],
                    'name': domain['name'],
                    'display_name': domain['display_name'],
                    'namespace_uri': domain['namespace_uri'],
                    'description': domain['description'],
                    'is_active': domain['is_active'],
                    'created_at': domain['created_at'].isoformat(),
                    'updated_at': domain['updated_at'].isoformat(),
                    'metadata': domain['metadata'] or {}
                },
                'stats': stats
            }
            
        except Exception as e:
            logger.error(f"Failed to get domain info: {e}")
            raise StorageError(f"Failed to retrieve domain info: {str(e)}")
    
    # Helper methods
    
    def _get_concept_by_id(self, concept_id: str) -> Optional[Dict[str, Any]]:
        """Get concept by UUID or database ID."""
        try:
            # Try UUID first
            query = "SELECT * FROM concepts WHERE uuid = %s"
            result = self.storage._execute_query(query, (concept_id,), fetch_one=True)
            
            if not result:
                # Try database ID if it's numeric
                try:
                    db_id = int(concept_id)
                    query = "SELECT * FROM concepts WHERE id = %s"
                    result = self.storage._execute_query(query, (db_id,), fetch_one=True)
                except ValueError:
                    pass
            
            return dict(result) if result else None
            
        except Exception as e:
            logger.error(f"Error getting concept by ID: {e}")
            return None
    
    def _insert_candidate_metadata(self, concept_id: int, concept_data: Dict[str, Any], 
                                  submitted_by: str):
        """Insert candidate metadata."""
        try:
            query = """
                INSERT INTO candidate_metadata (
                    concept_id, extraction_method, llm_confidence,
                    source_text, llm_reasoning, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            params = (
                concept_id,
                concept_data.get('extraction_method'),
                concept_data.get('llm_confidence'),
                concept_data.get('source_text'),
                concept_data.get('llm_reasoning'),
                Json(concept_data.get('extraction_metadata', {}))
            )
            
            self.storage._execute_query(query, params)
            
        except Exception as e:
            logger.warning(f"Failed to insert candidate metadata: {e}")
    
    def _create_approval_workflow(self, concept_id: int):
        """Create approval workflow for concept."""
        try:
            query = """
                INSERT INTO approval_workflows (concept_id, workflow_type, current_state)
                VALUES (%s, 'standard', 'submitted')
            """
            
            self.storage._execute_query(query, (concept_id,))
            
        except Exception as e:
            logger.warning(f"Failed to create approval workflow: {e}")
    
    def _update_approval_workflow(self, concept_id: int, status: str, user: str, reason: str):
        """Update approval workflow."""
        try:
            # Map status to workflow state
            state_mapping = {
                'approved': 'approved',
                'rejected': 'rejected',
                'deprecated': 'deprecated'
            }
            
            new_state = state_mapping.get(status, 'under_review')
            
            query = """
                UPDATE approval_workflows 
                SET previous_state = current_state, current_state = %s,
                    decision = %s, decision_reason = %s, decided_by = %s,
                    decided_at = CURRENT_TIMESTAMP, actual_completion = CURRENT_TIMESTAMP
                WHERE concept_id = %s
            """
            
            self.storage._execute_query(
                query, 
                (new_state, status, reason, user, concept_id)
            )
            
        except Exception as e:
            logger.warning(f"Failed to update approval workflow: {e}")
    
    def _create_concept_version(self, concept_id: int, concept: Dict[str, Any], 
                               changed_fields: List[str], reason: str, user: str):
        """Create concept version history entry."""
        try:
            # Get next version number
            query = "SELECT COALESCE(MAX(version_number), 0) + 1 FROM concept_versions WHERE concept_id = %s"
            result = self.storage._execute_query(query, (concept_id,), fetch_one=True)
            version_number = result[0] if result else 1
            
            # Insert version
            query = """
                INSERT INTO concept_versions (
                    concept_id, version_number, uri, label, semantic_label,
                    primary_type, description, status, metadata,
                    changed_fields, change_reason, changed_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            params = (
                concept_id, version_number, concept['uri'], concept['label'],
                concept['semantic_label'], concept['primary_type'], concept['description'],
                concept['status'], Json(concept.get('metadata', {})),
                Json(changed_fields), reason, user
            )
            
            self.storage._execute_query(query, params)
            
        except Exception as e:
            logger.warning(f"Failed to create concept version: {e}")

    def get_ontology_entities_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Get ontology class entities by category from the ontology_entities table.

        Args:
            category: Entity category (Role, Principle, etc.)

        Returns:
            List of ontology entities matching the category
        """
        try:
            # Look for classes in the proethica intermediate ontology that match the category
            query = """
                SELECT
                    id, uri, label, comment as description, entity_type,
                    parent_uri, created_at
                FROM ontology_entities
                WHERE entity_type = 'class'
                AND (
                    uri LIKE %s
                    OR label ILIKE %s
                    OR uri LIKE %s
                )
                AND uri LIKE %s
                ORDER BY label
            """

            # Search patterns for the category
            category_pattern = f'%{category}%'
            label_pattern = f'%{category}%'
            uri_pattern = f'%{category}'
            ontology_pattern = '%proethica.org/ontology%'

            results = self.storage._execute_query(
                query,
                (category_pattern, label_pattern, uri_pattern, ontology_pattern),
                fetch_all=True
            )

            entities = []
            if results:
                for row in results:
                    try:
                        entity = {
                            'id': row['id'],
                            'uri': row['uri'],
                            'label': row['label'],
                            'description': row['description'] or f'Ontology class for {category}',
                            'category': category,
                            'entity_type': row['entity_type'],
                            'parent_uri': row['parent_uri'],
                            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                            'source': 'ontology'
                        }
                        entities.append(entity)
                    except Exception as row_error:
                        logger.error(f"Error processing row: {row_error}, row data: {row}")
                        continue
            else:
                logger.warning(f"No results returned for category {category} query")

            logger.info(f"Found {len(entities)} ontology entities for category {category}")
            return entities

        except Exception as e:
            logger.error(f"Error getting ontology entities by category {category}: {e}")
            return []
