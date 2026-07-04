"""
Ontology Sync Service

Automatically synchronizes ontology entities from TTL files to the database.
Uses hash-based change detection to only re-extract when files change.
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

from rdflib import Graph, RDF, RDFS, OWL, SKOS, Namespace, BNode
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

    def _extract_dcterms_title(self, ttl_path: Path) -> Optional[str]:
        """Return the dcterms:title of the owl:Ontology subject in a TTL file,
        or None if absent. Used to seed display_name for newly synced case
        ontologies (ProEthica emits the human case title in the header)."""
        from rdflib import Graph
        from rdflib.namespace import OWL, RDF, DCTERMS
        try:
            g = Graph()
            g.parse(str(ttl_path), format='turtle')
            for subj in g.subjects(RDF.type, OWL.Ontology):
                title = g.value(subj, DCTERMS.title)
                if title:
                    return str(title).strip() or None
        except Exception as e:
            logger.warning(f"Could not read dcterms:title from {ttl_path.name}: {e}")
        return None

    def _extract_ontology_meta(self, ttl_path: Path) -> Dict:
        """Read owl:Ontology-level provenance from a TTL: rdfs:comment (-> description),
        dcterms:source, owl:versionInfo, dcterms:title. Lets imported vocabularies (e.g. the
        ifc-roles crosswalk stub) carry their provenance into the OntServe ontology record
        instead of the generic 'Auto-imported from ...' default."""
        from rdflib import Graph
        from rdflib.namespace import OWL, RDF, RDFS, DCTERMS
        out: Dict = {}
        try:
            g = Graph()
            g.parse(str(ttl_path), format='turtle')
            for subj in g.subjects(RDF.type, OWL.Ontology):
                comment = g.value(subj, RDFS.comment)
                if comment:
                    out['description'] = str(comment).strip()
                source = g.value(subj, DCTERMS.source)
                if source:
                    out['source'] = str(source).strip()
                version = g.value(subj, OWL.versionInfo)
                if version:
                    out['version'] = str(version).strip()
                title = g.value(subj, DCTERMS.title)
                if title:
                    out['title'] = str(title).strip()
                break  # one owl:Ontology subject expected
        except Exception as e:
            logger.warning(f"Could not read owl:Ontology metadata from {ttl_path.name}: {e}")
        return out

    @staticmethod
    def _infer_type_and_source(ontology_name: str) -> Tuple[str, str]:
        """Infer (ontology_type, source_system) for a newly auto-created ontology
        record. The sync path is the live registrar for ProEthica case commits
        (ontserve_commit_service._sync_ontology_to_db relies on the auto-create),
        so per-case ontologies must not fall through to the column defaults
        'base'/'manual' -- that renders them unreachable via the Type=case filter
        and mislabels them as hand-authored. Mirrors
        scripts/active/register_case_ontologies.py."""
        if re.fullmatch(r'proethica-case-\d+', ontology_name):
            return 'case', 'proethica'
        if ontology_name.startswith('proethica-'):
            return 'base', 'proethica'
        return 'base', 'manual'

    def _sync_single_ontology(self, ttl_path: Path, force: bool = False,
                              change_summary: str = None) -> Dict:
        """
        Sync a single TTL file.

        Args:
            ttl_path: Path to the TTL file
            force: Force re-extraction even if hash matches
            change_summary: Recorded on the new ontology_versions row so the DB
                history carries its own why (the case TTLs are gitignored, so
                this row IS their audit trail). Defaults to the generic
                auto-sync message used by the startup importer.

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
            # ProEthica emits the human case title as dcterms:title in the TTL
            # header; carry it into display_name so the case view shows the real
            # title instead of the opaque "proethica-case-N" id. Set on create
            # only, so a manually edited display_name is never overwritten.
            ometa = self._extract_ontology_meta(ttl_path)
            meta_data = {}
            if ometa.get('title'):
                meta_data['display_name'] = ometa['title']
            if ometa.get('source'):
                meta_data['source'] = ometa['source']
            if ometa.get('version'):
                meta_data['version'] = ometa['version']
            inferred_type, inferred_source = self._infer_type_and_source(ontology_name)
            ontology = Ontology(
                name=ontology_name,
                base_uri=f"http://proethica.org/ontology/{ontology_name}#",
                description=ometa.get('description') or f"Auto-imported from {ttl_path.name}",
                is_editable=True,
                ontology_type=inferred_type,
                source_system=inferred_source,
                meta_data=meta_data
            )
            self.db_session.add(ontology)
            self.db_session.flush()

        # Get latest version to check hash
        stmt = select(OntologyVersion).where(
            OntologyVersion.ontology_id == ontology.id
        ).order_by(OntologyVersion.version_number.desc())
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

        # Refresh ontology-level provenance from the TTL on every (re)sync, preserving a
        # manually-set display_name. Lets a vocabulary's owl:Ontology comment/source/version
        # reach the OntServe record instead of the generic 'Auto-imported' default.
        ometa = self._extract_ontology_meta(ttl_path)
        if ometa.get('description'):
            ontology.description = ometa['description']
        md = dict(ontology.meta_data or {})
        if ometa.get('source'):
            md['source'] = ometa['source']
        if ometa.get('version'):
            md['version'] = ometa['version']
        if ometa.get('title') and not md.get('display_name'):
            md['display_name'] = ometa['title']
        ontology.meta_data = md

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
            change_summary=change_summary or f"Auto-synced from {ttl_path.name}",
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
        # Delegate to the single canonical extractor (web/entity_extraction.extract_entities_from_content)
        # so the startup sync, the web import, and the manual refresh tool all capture the SAME entity set
        # (classes, ALL property types incl. annotation properties, individuals, concepts, schemes, catch-all)
        # and preserve embeddings. It clears the ontology's existing entities and adds the new ones to the
        # shared db.session (== self.db_session); the caller commits.
        from web.entity_extraction import extract_entities_from_content
        counts = extract_entities_from_content(ontology, ttl_content)
        total = sum(counts.values())
        logger.info(f"Extracted {total} entities from {ontology.name} (canonical extractor)")
        return total

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
