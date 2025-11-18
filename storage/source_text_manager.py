"""
Source Text Manager for OntServe

Handles storage and retrieval of source text provenance for ontology entities.
Implements W3C PROV-O patterns and ProEthica custom annotation properties.

Architecture:
- Classes (ontology_entities): source_reference for definitional citations
- Individuals (concepts): source_text in candidate_metadata + RDF triples
- RDF Triples (concept_triples): Full PROV-O provenance chains

Author: OntServe Team
Date: 2025-11-17
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from psycopg2.extras import Json

logger = logging.getLogger(__name__)

# PROV-O and ProEthica namespaces
PROV_NS = "http://www.w3.org/ns/prov#"
PROETH_PROV_NS = "http://proethica.org/ontology/provenance/"
XSD_NS = "http://www.w3.org/2001/XMLSchema#"

# Common predicates
PROV_DERIVED_FROM = f"{PROV_NS}wasDerivedFrom"
PROV_QUOTED_FROM = f"{PROV_NS}wasQuotedFrom"
PROV_GENERATED_AT = f"{PROV_NS}generatedAtTime"
PROV_ATTRIBUTED_TO = f"{PROV_NS}wasAttributedTo"
PROV_GENERATED_BY = f"{PROV_NS}wasGeneratedBy"
PROV_VALUE = f"{PROV_NS}value"

PROETH_SOURCE_TEXT = f"{PROETH_PROV_NS}sourceText"
PROETH_EXTRACTED_FROM = f"{PROETH_PROV_NS}extractedFrom"
PROETH_EXTRACTION_CONFIDENCE = f"{PROETH_PROV_NS}extractionConfidence"


class SourceTextManager:
    """
    Manager for source text provenance storage and retrieval.

    Handles both annotation properties (for display) and PROV-O object
    properties (for reasoning) following W3C best practices.
    """

    def __init__(self, storage):
        """
        Initialize source text manager.

        Args:
            storage: PostgreSQLStorage instance
        """
        self.storage = storage
        logger.info("Source text manager initialized")

    def store_individual_with_source_text(
        self,
        concept_id: int,
        entity_uri: str,
        source_text: str,
        extraction_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Store source text for an individual entity.

        Implements hybrid approach:
        1. Stores in candidate_metadata.source_text (database)
        2. Stores as annotation property triple (proeth-prov:sourceText)
        3. Optionally stores PROV-O object property triples

        Args:
            concept_id: Database ID of the concept
            entity_uri: URI of the entity
            source_text: Verbatim text snippet from source
            extraction_metadata: Optional metadata about extraction
                - extracted_from_section: Section identifier
                - extraction_timestamp: When extracted
                - extractor_name: Who/what extracted it
                - confidence: Extraction confidence score
                - case_id: Case number (for ProEthica)

        Returns:
            Dictionary with storage results
        """
        try:
            metadata = extraction_metadata or {}
            stored_triples = []

            # 1. Store annotation property: proeth-prov:sourceText
            triple_id = self._store_annotation_triple(
                subject=entity_uri,
                predicate=PROETH_SOURCE_TEXT,
                object_literal=source_text,
                concept_id=concept_id
            )
            stored_triples.append({
                'id': triple_id,
                'predicate': 'sourceText',
                'type': 'annotation'
            })

            # 2. Store extracted_from annotation if provided
            if 'extracted_from_section' in metadata:
                triple_id = self._store_annotation_triple(
                    subject=entity_uri,
                    predicate=PROETH_EXTRACTED_FROM,
                    object_literal=metadata['extracted_from_section'],
                    concept_id=concept_id
                )
                stored_triples.append({
                    'id': triple_id,
                    'predicate': 'extractedFrom',
                    'type': 'annotation'
                })

            # 3. Store extraction confidence if provided
            if 'confidence' in metadata:
                triple_id = self._store_annotation_triple(
                    subject=entity_uri,
                    predicate=PROETH_EXTRACTION_CONFIDENCE,
                    object_literal=str(metadata['confidence']),
                    concept_id=concept_id,
                    datatype=f"{XSD_NS}decimal"
                )
                stored_triples.append({
                    'id': triple_id,
                    'predicate': 'extractionConfidence',
                    'type': 'annotation'
                })

            # 4. Store PROV-O derivation: prov:wasDerivedFrom
            if 'extracted_from_section' in metadata and 'case_id' in metadata:
                section_uri = self._construct_section_uri(
                    metadata['case_id'],
                    metadata['extracted_from_section']
                )
                triple_id = self._store_object_property_triple(
                    subject=entity_uri,
                    predicate=PROV_DERIVED_FROM,
                    object_uri=section_uri,
                    concept_id=concept_id
                )
                stored_triples.append({
                    'id': triple_id,
                    'predicate': 'wasDerivedFrom',
                    'type': 'prov_o'
                })

            # 5. Store PROV-O temporal: prov:generatedAtTime
            if 'extraction_timestamp' in metadata:
                timestamp = metadata['extraction_timestamp']
                if isinstance(timestamp, datetime):
                    timestamp = timestamp.isoformat()

                triple_id = self._store_annotation_triple(
                    subject=entity_uri,
                    predicate=PROV_GENERATED_AT,
                    object_literal=timestamp,
                    concept_id=concept_id,
                    datatype=f"{XSD_NS}dateTime"
                )
                stored_triples.append({
                    'id': triple_id,
                    'predicate': 'generatedAtTime',
                    'type': 'prov_o'
                })

            # 6. Store PROV-O attribution: prov:wasAttributedTo
            if 'extractor_name' in metadata:
                extractor_uri = self._construct_extractor_uri(metadata['extractor_name'])
                triple_id = self._store_object_property_triple(
                    subject=entity_uri,
                    predicate=PROV_ATTRIBUTED_TO,
                    object_uri=extractor_uri,
                    concept_id=concept_id
                )
                stored_triples.append({
                    'id': triple_id,
                    'predicate': 'wasAttributedTo',
                    'type': 'prov_o'
                })

            logger.info(
                f"Stored source text for {entity_uri}: "
                f"{len(stored_triples)} triples, {len(source_text)} chars"
            )

            return {
                'success': True,
                'entity_uri': entity_uri,
                'source_text_length': len(source_text),
                'triples_stored': len(stored_triples),
                'triple_details': stored_triples
            }

        except Exception as e:
            logger.error(f"Failed to store source text for {entity_uri}: {e}")
            raise

    def store_class_with_source_reference(
        self,
        ontology_id: int,
        entity_uri: str,
        source_reference: str
    ) -> Dict[str, Any]:
        """
        Store definitional source reference for a class.

        This is for general concept definitions (e.g., "NSPE Code Section I.1"),
        not case-specific snippets. Stores in ontology_entities.source_reference.

        Args:
            ontology_id: Database ID of the ontology
            entity_uri: URI of the class
            source_reference: Citation for the definition

        Returns:
            Dictionary with update results
        """
        try:
            query = """
                UPDATE ontology_entities
                SET source_reference = %s
                WHERE ontology_id = %s AND uri = %s
                RETURNING id
            """

            result = self.storage._execute_query(
                query,
                (source_reference, ontology_id, entity_uri),
                fetch_one=True
            )

            if result:
                logger.info(f"Stored source reference for class {entity_uri}: {source_reference}")
                return {
                    'success': True,
                    'entity_uri': entity_uri,
                    'entity_id': result['id'],
                    'source_reference': source_reference
                }
            else:
                logger.warning(f"Class not found: {entity_uri}")
                return {
                    'success': False,
                    'error': 'Class not found in ontology_entities'
                }

        except Exception as e:
            logger.error(f"Failed to store source reference for {entity_uri}: {e}")
            raise

    def get_entity_source_text(self, entity_uri: str) -> Optional[Dict[str, Any]]:
        """
        Get source text for an entity (class or individual).

        Checks both ontology_entities.source_reference and
        candidate_metadata.source_text.

        Args:
            entity_uri: URI of the entity

        Returns:
            Dictionary with source text and metadata, or None
        """
        try:
            # Use the database function we created in migration
            query = "SELECT * FROM get_entity_source_text(%s)"
            result = self.storage._execute_query(query, (entity_uri,), fetch_one=True)

            if result:
                return {
                    'entity_uri': entity_uri,
                    'source_text': result['source_text'],
                    'source_type': result['source_type'],
                    'extraction_timestamp': result['extraction_timestamp']
                }

            # Fallback: Try to find in concept_triples
            triple_query = """
                SELECT object_literal, created_at
                FROM concept_triples
                WHERE subject = %s AND predicate = %s
                LIMIT 1
            """

            triple_result = self.storage._execute_query(
                triple_query,
                (entity_uri, PROETH_SOURCE_TEXT),
                fetch_one=True
            )

            if triple_result:
                return {
                    'entity_uri': entity_uri,
                    'source_text': triple_result['object_literal'],
                    'source_type': 'rdf_triple',
                    'extraction_timestamp': triple_result['created_at']
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get source text for {entity_uri}: {e}")
            return None

    def get_entity_provenance_chain(self, entity_uri: str) -> Dict[str, Any]:
        """
        Get full PROV-O provenance chain for an entity.

        Returns all provenance-related triples (wasDerivedFrom,
        generatedAtTime, wasAttributedTo, etc.)

        Args:
            entity_uri: URI of the entity

        Returns:
            Dictionary with provenance information
        """
        try:
            # Query all PROV-O triples for this entity
            query = """
                SELECT
                    predicate,
                    object_literal,
                    object_uri,
                    is_literal,
                    created_at
                FROM concept_triples
                WHERE subject = %s
                AND (
                    predicate LIKE 'http://www.w3.org/ns/prov#%%'
                    OR predicate LIKE 'http://proethica.org/ontology/provenance/%%'
                )
                ORDER BY created_at
            """

            results = self.storage._execute_query(query, (entity_uri,), fetch_all=True)

            provenance = {
                'entity_uri': entity_uri,
                'source_text': None,
                'extracted_from': None,
                'derived_from': None,
                'generated_at': None,
                'attributed_to': None,
                'confidence': None,
                'all_triples': []
            }

            for row in results:
                pred = row['predicate']
                value = row['object_literal'] if row['is_literal'] else row['object_uri']

                # Map to provenance fields
                if pred == PROETH_SOURCE_TEXT:
                    provenance['source_text'] = value
                elif pred == PROETH_EXTRACTED_FROM:
                    provenance['extracted_from'] = value
                elif pred == PROV_DERIVED_FROM:
                    provenance['derived_from'] = value
                elif pred == PROV_GENERATED_AT:
                    provenance['generated_at'] = value
                elif pred == PROV_ATTRIBUTED_TO:
                    provenance['attributed_to'] = value
                elif pred == PROETH_EXTRACTION_CONFIDENCE:
                    provenance['confidence'] = float(value) if value else None

                provenance['all_triples'].append({
                    'predicate': pred,
                    'value': value,
                    'is_literal': row['is_literal'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None
                })

            return provenance

        except Exception as e:
            logger.error(f"Failed to get provenance chain for {entity_uri}: {e}")
            return {'entity_uri': entity_uri, 'error': str(e)}

    # Helper methods

    def _store_annotation_triple(
        self,
        subject: str,
        predicate: str,
        object_literal: str,
        concept_id: int,
        datatype: Optional[str] = None
    ) -> int:
        """Store annotation property triple in concept_triples."""
        query = """
            INSERT INTO concept_triples (
                concept_id, subject, predicate, object_literal,
                is_literal, triple_metadata
            )
            VALUES (%s, %s, %s, %s, true, %s)
            RETURNING id
        """

        metadata = {'annotation_type': 'provenance'}
        if datatype:
            metadata['datatype'] = datatype

        result = self.storage._execute_query(
            query,
            (concept_id, subject, predicate, object_literal, Json(metadata)),
            fetch_one=True
        )

        return result['id'] if result else None

    def _store_object_property_triple(
        self,
        subject: str,
        predicate: str,
        object_uri: str,
        concept_id: int
    ) -> int:
        """Store object property triple in concept_triples."""
        query = """
            INSERT INTO concept_triples (
                concept_id, subject, predicate, object_uri,
                is_literal, triple_metadata
            )
            VALUES (%s, %s, %s, %s, false, %s)
            RETURNING id
        """

        metadata = {'property_type': 'prov_o_object_property'}

        result = self.storage._execute_query(
            query,
            (concept_id, subject, predicate, object_uri, Json(metadata)),
            fetch_one=True
        )

        return result['id'] if result else None

    def _construct_section_uri(self, case_id: int, section_name: str) -> str:
        """Construct URI for a case section."""
        # Normalize section name
        section_safe = section_name.lower().replace(' ', '_').replace('-', '_')
        return f"http://proethica.org/ontology/case/{case_id}#{section_safe}"

    def _construct_extractor_uri(self, extractor_name: str) -> str:
        """Construct URI for an extractor agent."""
        # Normalize extractor name
        extractor_safe = extractor_name.lower().replace(' ', '_').replace('-', '_')
        return f"http://proethica.org/extractors/{extractor_safe}"


def create_source_text_manager(storage) -> SourceTextManager:
    """
    Factory function to create SourceTextManager instance.

    Args:
        storage: PostgreSQLStorage instance

    Returns:
        SourceTextManager instance
    """
    return SourceTextManager(storage)
