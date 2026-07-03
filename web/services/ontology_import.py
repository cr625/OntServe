"""
Ontology import service.

Handles content acquisition (URL/file), format detection, vocabulary
conversion, reasoning-based import, and database persistence. Extracted
from web/ontology_routes.py import_ontology().
"""

import os
import re
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests as http_requests
from flask import current_app
from sqlalchemy import select

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from web.entity_extraction import extract_entities_from_content
from utils.vocabulary_converter import VocabularyConverter, is_vocabulary_convertible

logger = logging.getLogger(__name__)


@dataclass
class ImportRequest:
    """Parsed import parameters from the route handler."""
    source_type: str
    name: Optional[str]
    description: Optional[str]
    format_hint: str
    use_reasoning: bool
    reasoner_type: str
    source_url: Optional[str] = None
    file_content: Optional[str] = None
    filename: Optional[str] = None


@dataclass
class ImportResult:
    """Outcome of an import operation."""
    success: bool
    message: str
    ontology_name: Optional[str] = None
    redirect_name: Optional[str] = None
    reasoning_summary: Optional[str] = None


def execute_import(req: ImportRequest) -> ImportResult:
    """Execute an ontology import from URL or uploaded content.

    Runs inside a Flask request context (requires current_app and db.session).
    """
    # --- Acquire content ---
    source, content, filename = _acquire_content(req)

    # --- Detect format ---
    format_hint = _detect_format(req.format_hint, filename, content)
    logger.info("Detected format: %s", format_hint)

    # --- Vocabulary conversion (optional) ---
    content = _maybe_convert_vocabulary(content, format_hint, req.name)

    # --- Run import ---
    if req.use_reasoning:
        result = _import_with_reasoning(
            source, content, req.source_type, req.name,
            req.description, format_hint, req.reasoner_type,
        )
    else:
        result = _import_basic(
            source, content, req.source_type, req.name,
            req.description, format_hint,
        )

    if not result['success']:
        return ImportResult(
            success=False,
            message=f"Import failed: {result.get('message', 'Unknown error')}",
        )

    # --- Persist to database ---
    return _persist_import(
        result, req, source, content, format_hint,
    )


# ---------------------------------------------------------------------------
# Content acquisition
# ---------------------------------------------------------------------------

def _acquire_content(req: ImportRequest) -> tuple[str, str, str]:
    """Fetch content from URL or use uploaded file content.

    Returns (source, content, filename).
    Raises ValueError on bad input.
    """
    if req.source_type == 'url':
        if not req.source_url:
            raise ValueError("Please provide a URL")
        logger.info("Fetching ontology from URL: %s", req.source_url)
        headers = {
            'Accept': 'text/turtle, application/rdf+xml, application/n-triples, '
                      'application/ld+json, text/n3, */*',
            'User-Agent': 'OntServe/1.0 (ontology importer)',
        }
        response = http_requests.get(req.source_url, headers=headers, timeout=30)
        response.raise_for_status()
        filename = req.source_url.split('/')[-1] or 'ontology'
        return req.source_url, response.text, filename

    if req.source_type == 'upload':
        if not req.file_content or not req.filename:
            raise ValueError("Please select a file to upload")
        logger.info("Processing uploaded file: %s", req.filename)
        return f"uploaded://{req.filename}", req.file_content, req.filename

    raise ValueError("Invalid source type")


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

_EXTENSION_MAP = {
    '.ttl': 'turtle',
    '.rdf': 'xml',
    '.xml': 'xml',
    '.owl': 'xml',
    '.n3': 'n3',
    '.jsonld': 'json-ld',
    '.json': 'json-ld',
    '.nt': 'nt',
}


def _detect_format(hint: str, filename: str, content: str) -> str:
    """Auto-detect serialization format from hint, filename, or content."""
    if hint:
        return hint

    if filename:
        for ext, fmt in _EXTENSION_MAP.items():
            if filename.endswith(ext):
                return fmt

    if '@prefix' in content or '@base' in content:
        return 'turtle'
    if '<?xml' in content or '<rdf:RDF' in content or 'xmlns:rdf' in content:
        return 'xml'
    if content.strip().startswith('{'):
        return 'json-ld'

    return 'turtle'


# ---------------------------------------------------------------------------
# Vocabulary conversion
# ---------------------------------------------------------------------------

def _maybe_convert_vocabulary(content: str, format_hint: str, name: Optional[str]) -> str:
    """Convert non-OWL vocabularies (SKOS, Dublin Core) if needed."""
    original = content
    try:
        if is_vocabulary_convertible(content, format_hint):
            logger.info("Detected non-OWL vocabulary; converting")
            converter = VocabularyConverter()
            ontology_uri = (
                f"http://example.org/{name.lower().replace(' ', '-')}"
                if name else None
            )
            content = converter.convert_vocabulary_content(
                content, input_format=format_hint,
                output_format='turtle', ontology_uri=ontology_uri,
            )
            logger.info(
                "Converted vocabulary (%d -> %d chars)",
                len(original), len(content),
            )
    except Exception as exc:
        logger.warning("Vocabulary conversion failed: %s. Using original.", exc)
        content = original
    return content


# ---------------------------------------------------------------------------
# Import execution
# ---------------------------------------------------------------------------

def _import_with_reasoning(
    source, content, source_type, name, description, format_hint, reasoner_type,
):
    """Import with OWL reasoning via OwlreadyImporter."""
    from importers.owlready_importer import OwlreadyImporter

    importer = OwlreadyImporter()
    importer.use_reasoner = True
    importer.reasoner_type = reasoner_type
    importer.validate_consistency = True
    importer.include_inferred = True

    logger.info("Using OwlreadyImporter with %s reasoning", reasoner_type)

    if source_type == 'url':
        return importer.import_from_url(
            source, name=name, description=description, format=format_hint,
        )

    with tempfile.NamedTemporaryFile(
        mode='w', suffix=f'.{format_hint}', delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        return importer.import_from_file(
            tmp_path, name=name, description=description, format=format_hint,
        )
    finally:
        os.unlink(tmp_path)


def _import_basic(source, content, source_type, name, description, format_hint):
    """Import without reasoning via OntologyManager."""
    logger.info("Using basic OntologyManager (no reasoning)")
    manager = current_app.ontology_manager

    if source_type == 'upload':
        with tempfile.NamedTemporaryFile(
            mode='w', suffix=f'.{format_hint}', delete=False,
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            result = manager.import_ontology(
                source=tmp_path, importer_type='prov', name=name,
                description=description, format=format_hint, source_type='file',
            )
            if result.get('success'):
                result['content'] = content
            return result
        finally:
            os.unlink(tmp_path)

    result = manager.import_ontology(
        source=source, importer_type='prov', name=name,
        description=description, format=format_hint, source_type='url',
    )
    if result.get('success'):
        result['content'] = content
    return result


# ---------------------------------------------------------------------------
# Database persistence
# ---------------------------------------------------------------------------

def _persist_import(result, req, source, content, format_hint) -> ImportResult:
    """Create Ontology, OntologyVersion, and entity records in the database."""
    ontology_name = req.name or result['metadata'].get('name', 'Unnamed')

    uri_safe_name = ontology_name.lower().replace(' ', '-')
    uri_safe_name = uri_safe_name.replace('&', 'and').replace('/', '-').replace('\\', '-')
    uri_safe_name = re.sub(r'[^a-z0-9\-]', '', uri_safe_name)
    uri_safe_name = re.sub(r'-+', '-', uri_safe_name).strip('-')

    existing = db.session.execute(
        select(Ontology).where(Ontology.name == uri_safe_name)
    ).scalar_one_or_none()
    if existing:
        return ImportResult(
            success=False,
            message=f"Ontology '{uri_safe_name}' already exists",
            redirect_name=uri_safe_name,
        )

    default_base_uri = current_app.config['ONTOLOGY_NAMESPACE_TEMPLATE'].format(
        base_uri=current_app.config['ONTOLOGY_BASE_URI'],
        name=uri_safe_name,
    )

    ontology = Ontology(
        name=uri_safe_name,
        base_uri=result['metadata'].get('namespace', default_base_uri),
        description=req.description or result['metadata'].get('description', ''),
        # A URL import is an externally published vocabulary; an upload is
        # hand-supplied. Without this, every import lands on the column
        # defaults ('base'/'manual') regardless of origin.
        source_system='external' if req.source_type == 'url' else 'manual',
        meta_data={
            **result['metadata'],
            'original_name': ontology_name,
            'display_name': ontology_name,
        },
    )
    db.session.add(ontology)
    db.session.flush()

    # Build version metadata
    if req.use_reasoning and 'enhanced_data' in result:
        version_content = content or result.get('rdf_content', '')
        reasoning_metadata = {
            'reasoning_applied': True,
            'reasoner_type': req.reasoner_type,
            'inferred_relationships': result.get(
                'reasoning_result', {}
            ).get('inferred_count', 0),
            'consistency_check': result.get(
                'reasoning_result', {}
            ).get('is_consistent'),
        }
        change_summary = f"Initial import with {req.reasoner_type} reasoning"
    else:
        version_content = content or result.get('content', '')
        reasoning_metadata = {'reasoning_applied': False}
        change_summary = "Initial import"

    version = OntologyVersion(
        ontology_id=ontology.id,
        version_number=1,
        version_tag="1.0.0",
        content=version_content,
        change_summary=change_summary,
        created_by="web-import",
        is_current=True,
        is_draft=False,
        workflow_status='published',
        meta_data={
            'source': source,
            'source_type': req.source_type,
            'format': result['metadata'].get('format', format_hint),
            'import_date': datetime.now(timezone.utc).isoformat(),
            **reasoning_metadata,
        },
    )
    db.session.add(version)

    # Extract entities
    if req.use_reasoning and 'enhanced_data' in result:
        _store_enhanced_entities(ontology.id, result['enhanced_data'])
    else:
        counts = extract_entities_from_content(ontology, version_content, format_hint)
        logger.info("Extracted %d entities using basic parsing", sum(counts.values()))

    db.session.commit()

    # Build success message
    msg = f"Successfully imported ontology: {ontology_name}"
    reasoning_summary = None
    if req.use_reasoning:
        rr = result.get('reasoning_result', {})
        inferred = rr.get('inferred_count', 0)
        consistency = rr.get('is_consistent', 'unknown')
        reasoning_summary = (
            f"Reasoning: {inferred} inferred relationships, "
            f"consistency: {consistency}"
        )
        msg += f" ({reasoning_summary})"

    return ImportResult(
        success=True,
        message=msg,
        ontology_name=ontology_name,
        redirect_name=uri_safe_name,
        reasoning_summary=reasoning_summary,
    )


def _store_enhanced_entities(ontology_id: int, enhanced_data: dict):
    """Store entities from reasoning-enhanced import result."""
    for cls in enhanced_data.get('classes', []):
        db.session.add(OntologyEntity(
            ontology_id=ontology_id,
            entity_type='class',
            uri=cls['uri'],
            label=cls.get('label', [None])[0] if cls.get('label') else None,
            comment=cls.get('comment', [None])[0] if cls.get('comment') else None,
            parent_uri=cls.get('parents', [None])[0] if cls.get('parents') else None,
        ))

    for prop in enhanced_data.get('properties', []):
        db.session.add(OntologyEntity(
            ontology_id=ontology_id,
            entity_type='property',
            uri=prop['uri'],
            label=prop.get('label', [None])[0] if prop.get('label') else None,
            comment=prop.get('comment', [None])[0] if prop.get('comment') else None,
            domain=prop.get('domain', [None])[0] if prop.get('domain') else None,
            range=prop.get('range', [None])[0] if prop.get('range') else None,
        ))

    for ind in enhanced_data.get('individuals', []):
        db.session.add(OntologyEntity(
            ontology_id=ontology_id,
            entity_type='individual',
            uri=ind['uri'],
            label=ind.get('label', [None])[0] if ind.get('label') else None,
            comment=ind.get('comment', [None])[0] if ind.get('comment') else None,
        ))
