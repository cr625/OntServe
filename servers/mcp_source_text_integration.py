"""
MCP Server Integration for Source Text Provenance

Provides helper functions to integrate SourceTextManager with the MCP server.
Used by mcp_server.py to handle source text storage in entity submissions.

Author: OntServe Team
Date: 2025-11-17
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Import will happen at runtime to avoid circular imports
# from storage.source_text_manager import SourceTextManager


def enhance_entity_submission_with_source_text(
    concept_manager,
    source_text_manager,
    entity_data: Dict[str, Any],
    case_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enhanced entity submission that stores source text with provenance.

    This function wraps the standard concept submission to add source text
    storage as RDF triples with PROV-O metadata.

    Args:
        concept_manager: ConceptManager instance
        source_text_manager: SourceTextManager instance
        entity_data: Dictionary containing entity information
        case_id: Optional case identifier

    Returns:
        Enhanced submission result with provenance details
    """
    try:
        # 1. Submit concept using standard method
        domain_id = entity_data.get('domain_id', 'engineering-ethics')
        submitted_by = entity_data.get('submitted_by', 'proethica-extractor')

        # Build concept_data for submission
        concept_data = {
            'label': entity_data.get('label', ''),
            'category': entity_data.get('category', 'Entity'),
            'description': entity_data.get('description', ''),
            'uri': entity_data.get('uri', ''),
            'confidence_score': entity_data.get('confidence', 0.8),
            'source_document': entity_data.get('source_document'),
            'extraction_method': entity_data.get('extraction_method', 'llm_extraction'),
            'llm_reasoning': entity_data.get('llm_reasoning'),
            'metadata': entity_data.get('metadata', {})
        }

        result = concept_manager.submit_candidate_concept(
            concept_data,
            domain_id,
            submitted_by
        )

        if not result.get('success'):
            return result

        concept_db_id = result['concept_db_id']
        entity_uri = entity_data['uri']

        # 2. If source text provided, store with provenance
        if 'source_text' in entity_data and entity_data['source_text']:
            extraction_metadata = {
                'extracted_from_section': entity_data.get('extracted_from_section'),
                'extraction_timestamp': entity_data.get('extraction_timestamp', datetime.now()),
                'extractor_name': entity_data.get('extractor_name', submitted_by),
                'confidence': concept_data.get('confidence_score'),
                'case_id': case_id
            }

            # Filter out None values
            extraction_metadata = {
                k: v for k, v in extraction_metadata.items() if v is not None
            }

            provenance_result = source_text_manager.store_individual_with_source_text(
                concept_id=concept_db_id,
                entity_uri=entity_uri,
                source_text=entity_data['source_text'],
                extraction_metadata=extraction_metadata
            )

            # Add provenance info to result
            result['provenance'] = provenance_result
            result['source_text_stored'] = True
            result['triples_count'] = provenance_result.get('triples_stored', 0)

            logger.info(
                f"Entity submitted with source text provenance: "
                f"{entity_data['label']} ({result['triples_count']} triples)"
            )
        else:
            result['source_text_stored'] = False
            result['triples_count'] = 0

        return result

    except Exception as e:
        logger.error(f"Failed to submit entity with source text: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def get_entity_with_provenance(
    source_text_manager,
    entity_uri: str
) -> Optional[Dict[str, Any]]:
    """
    Get entity with full provenance chain.

    Args:
        source_text_manager: SourceTextManager instance
        entity_uri: URI of the entity

    Returns:
        Dictionary with entity and provenance information
    """
    try:
        provenance = source_text_manager.get_entity_provenance_chain(entity_uri)
        return provenance

    except Exception as e:
        logger.error(f"Failed to get entity provenance: {e}")
        return None


def enhance_entity_query_results(
    source_text_manager,
    entities: List[Dict[str, Any]],
    include_source_text: bool = True
) -> List[Dict[str, Any]]:
    """
    Enhance entity query results with source text provenance.

    Args:
        source_text_manager: SourceTextManager instance
        entities: List of entity dictionaries
        include_source_text: Whether to include source text

    Returns:
        Enhanced entity list with provenance
    """
    if not include_source_text:
        return entities

    enhanced_entities = []

    for entity in entities:
        entity_uri = entity.get('uri')
        if entity_uri:
            # Get source text
            source_text_info = source_text_manager.get_entity_source_text(entity_uri)
            if source_text_info:
                entity['source_text'] = source_text_info.get('source_text')
                entity['source_type'] = source_text_info.get('source_type')
                entity['extraction_timestamp'] = source_text_info.get('extraction_timestamp')

        enhanced_entities.append(entity)

    return enhanced_entities


def store_batch_entities_with_source_text(
    concept_manager,
    source_text_manager,
    entities: List[Dict[str, Any]],
    case_id: Optional[str] = None,
    section_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Store multiple entities with source text in batch.

    Args:
        concept_manager: ConceptManager instance
        source_text_manager: SourceTextManager instance
        entities: List of entity dictionaries
        case_id: Optional case identifier
        section_type: Optional section type

    Returns:
        Batch storage results
    """
    try:
        stored_entities = []
        failed_entities = []

        for entity in entities:
            # Add case_id and section_type to entity data
            entity['case_id'] = case_id
            entity['extracted_from_section'] = section_type

            # Submit entity with source text
            result = enhance_entity_submission_with_source_text(
                concept_manager,
                source_text_manager,
                entity,
                case_id
            )

            if result.get('success'):
                stored_entities.append({
                    'label': entity.get('label', ''),
                    'category': entity.get('category', 'Entity'),
                    'concept_id': result.get('concept_id'),
                    'source_text_stored': result.get('source_text_stored', False),
                    'triples_count': result.get('triples_count', 0)
                })
            else:
                failed_entities.append({
                    'label': entity.get('label', ''),
                    'error': result.get('error', 'Unknown error')
                })

        logger.info(
            f"Batch storage complete: {len(stored_entities)} succeeded, "
            f"{len(failed_entities)} failed"
        )

        return {
            'success': True,
            'stored_count': len(stored_entities),
            'failed_count': len(failed_entities),
            'stored_entities': stored_entities,
            'failed_entities': failed_entities
        }

    except Exception as e:
        logger.error(f"Batch storage failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
