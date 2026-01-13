"""
Ontology Sync Service

Automatically synchronizes ontology entities from TTL files to the database.
Uses hash-based change detection to only re-extract when files change.
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

from rdflib import Graph, RDF, RDFS, OWL, SKOS, Namespace
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Namespaces for parsing
PROETH = Namespace("http://proethica.org/ontology/intermediate#")


class OntologySyncService:
    """
    Service to sync ontology TTL files with the database.

    On startup, compares file hashes with stored hashes and re-extracts
    entities only when content has changed.
    """

    def __init__(self, db_session: Session, ontologies_dir: Path):
        """
        Initialize the sync service.

        Args:
            db_session: SQLAlchemy session for database operations
            ontologies_dir: Path to the ontologies directory containing TTL files
        """
        self.db_session = db_session
        self.ontologies_dir = ontologies_dir

    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def sync_all_ontologies(self, force: bool = False) -> Dict[str, any]:
        """
        Sync all TTL files in the ontologies directory.

        Args:
            force: If True, re-extract even if hash matches

        Returns:
            Summary of sync operations performed
        """
        # Import models here to avoid circular imports
        from web.models import Ontology, OntologyVersion, OntologyEntity, db

        results = {
            'checked': 0,
            'updated': 0,
            'skipped': 0,
            'errors': [],
            'details': []
        }

        ttl_files = list(self.ontologies_dir.glob('*.ttl'))
        logger.info(f"Found {len(ttl_files)} TTL files to check")

        for ttl_path in ttl_files:
            try:
                result = self._sync_single_ontology(ttl_path, force)
                results['checked'] += 1

                if result['action'] == 'updated':
                    results['updated'] += 1
                elif result['action'] == 'skipped':
                    results['skipped'] += 1

                results['details'].append(result)

            except Exception as e:
                logger.error(f"Error syncing {ttl_path.name}: {e}")
                results['errors'].append({
                    'file': ttl_path.name,
                    'error': str(e)
                })

        logger.info(f"Sync complete: {results['updated']} updated, {results['skipped']} skipped, {len(results['errors'])} errors")
        return results

    def _sync_single_ontology(self, ttl_path: Path, force: bool = False) -> Dict:
        """
        Sync a single TTL file.

        Args:
            ttl_path: Path to the TTL file
            force: Force re-extraction even if hash matches

        Returns:
            Dict with sync result details
        """
        from web.models import Ontology, OntologyVersion, OntologyEntity

        ontology_name = ttl_path.stem  # e.g., 'proethica-intermediate'
        file_hash = self.calculate_file_hash(ttl_path)

        # Find or create ontology record
        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = self.db_session.execute(stmt).scalar_one_or_none()

        if not ontology:
            # Create new ontology record
            logger.info(f"Creating new ontology record for {ontology_name}")
            ontology = Ontology(
                name=ontology_name,
                base_uri=f"http://proethica.org/ontology/{ontology_name}#",
                description=f"Auto-imported from {ttl_path.name}",
                is_editable=True
            )
            self.db_session.add(ontology)
            self.db_session.flush()

        # Get latest version to check hash
        stmt = select(OntologyVersion).where(
            OntologyVersion.ontology_id == ontology.id
        ).order_by(OntologyVersion.created_at.desc())
        latest_version = self.db_session.execute(stmt).scalars().first()

        # Check if we need to update
        needs_update = force or not latest_version or latest_version.content_hash != file_hash

        if not needs_update:
            logger.debug(f"Skipping {ontology_name} - hash unchanged")
            return {
                'file': ttl_path.name,
                'action': 'skipped',
                'reason': 'hash_unchanged',
                'hash': file_hash
            }

        logger.info(f"Updating {ontology_name} - {'forced' if force else 'hash changed'}")

        # Read TTL content
        with open(ttl_path, 'r', encoding='utf-8') as f:
            ttl_content = f.read()

        # Create new version
        new_version_number = (latest_version.version_number + 1) if latest_version else 1

        # Mark old version as not current
        if latest_version:
            latest_version.is_current = False

        new_version = OntologyVersion(
            ontology_id=ontology.id,
            version_number=new_version_number,
            content=ttl_content,
            content_hash=file_hash,
            change_summary=f"Auto-synced from {ttl_path.name}",
            created_by='ontology_sync_service',
            is_current=True,
            is_draft=False,
            workflow_status='published'
        )
        self.db_session.add(new_version)
        self.db_session.flush()

        # Extract and store entities
        entity_count = self._extract_and_store_entities(ontology, ttl_content)

        self.db_session.commit()

        return {
            'file': ttl_path.name,
            'action': 'updated',
            'version': new_version_number,
            'hash': file_hash,
            'entities_extracted': entity_count
        }

    def _extract_and_store_entities(self, ontology, ttl_content: str) -> int:
        """
        Extract entities from TTL content and store in database.

        Args:
            ontology: Ontology model instance
            ttl_content: TTL file content as string

        Returns:
            Number of entities extracted
        """
        from web.models import OntologyEntity

        # Delete existing entities for this ontology
        stmt = select(OntologyEntity).where(OntologyEntity.ontology_id == ontology.id)
        existing = self.db_session.execute(stmt).scalars().all()
        for entity in existing:
            self.db_session.delete(entity)
        self.db_session.flush()

        # Parse TTL
        graph = Graph()
        graph.parse(data=ttl_content, format='turtle')

        entities = []

        # Extract classes
        for s in graph.subjects(RDF.type, OWL.Class):
            entity = self._create_entity_from_subject(graph, s, 'Class', ontology.id)
            if entity:
                entities.append(entity)

        # Extract object properties
        for s in graph.subjects(RDF.type, OWL.ObjectProperty):
            entity = self._create_entity_from_subject(graph, s, 'ObjectProperty', ontology.id)
            if entity:
                entities.append(entity)

        # Extract datatype properties
        for s in graph.subjects(RDF.type, OWL.DatatypeProperty):
            entity = self._create_entity_from_subject(graph, s, 'DatatypeProperty', ontology.id)
            if entity:
                entities.append(entity)

        # Extract named individuals
        for s in graph.subjects(RDF.type, OWL.NamedIndividual):
            entity = self._create_entity_from_subject(graph, s, 'Individual', ontology.id)
            if entity:
                entities.append(entity)

        # Bulk insert
        for entity in entities:
            self.db_session.add(entity)

        logger.info(f"Extracted {len(entities)} entities from {ontology.name}")
        return len(entities)

    def _create_entity_from_subject(self, graph: Graph, subject, entity_type: str, ontology_id: int):
        """Create an OntologyEntity from an RDF subject."""
        from web.models import OntologyEntity

        uri = str(subject)

        # Skip blank nodes
        if uri.startswith('_:'):
            return None

        # Get label
        label = None
        for obj in graph.objects(subject, RDFS.label):
            label = str(obj)
            break

        # If no label, extract from URI
        if not label:
            label = uri.split('#')[-1].split('/')[-1]

        # Get description (comment or definition)
        description = None
        for obj in graph.objects(subject, RDFS.comment):
            description = str(obj)
            break
        if not description:
            for obj in graph.objects(subject, SKOS.definition):
                description = str(obj)
                break

        # Get domain and range for properties
        domain = None
        range_ = None
        if entity_type in ('ObjectProperty', 'DatatypeProperty'):
            for obj in graph.objects(subject, RDFS.domain):
                domain = str(obj)
                break
            for obj in graph.objects(subject, RDFS.range):
                range_ = str(obj)
                break

        return OntologyEntity(
            ontology_id=ontology_id,
            uri=uri,
            label=label,
            entity_type=entity_type,
            comment=description,
            domain=[domain] if domain else None,
            range=[range_] if range_ else None
        )


def sync_ontologies_on_startup(db_session: Session, ontologies_dir: Optional[Path] = None) -> Dict:
    """
    Convenience function to sync ontologies on application startup.

    Args:
        db_session: SQLAlchemy session
        ontologies_dir: Path to ontologies directory (defaults to OntServe/ontologies)

    Returns:
        Sync results summary
    """
    if ontologies_dir is None:
        # Default to OntServe/ontologies
        ontologies_dir = Path(__file__).parent.parent / 'ontologies'

    if not ontologies_dir.exists():
        logger.warning(f"Ontologies directory not found: {ontologies_dir}")
        return {'error': 'ontologies_dir_not_found'}

    logger.info(f"Starting ontology sync from {ontologies_dir}")

    service = OntologySyncService(db_session, ontologies_dir)
    return service.sync_all_ontologies()
