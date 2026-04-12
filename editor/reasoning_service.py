"""
OWL reasoning service for the ontology editor.

Handles owlready2-based reasoning: content parsing, import stripping,
format conversion, reasoner execution, hierarchy diffing, and version creation.
Extracted from editor/routes.py simple_reasoning().

Note: This reasoner powers the editor's "reason" button for in-UI preview.
It operates on a single ontology's current_content and does NOT merge
core+intermediate or preserve external owl:imports. For paper-grade
validation (merged graphs, corpus runs, mutation tests) see
validation/pellet_validate.py.
"""

import hashlib
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import rdflib
from rdflib import OWL
from sqlalchemy import select

from web.models import db, Ontology, OntologyVersion

logger = logging.getLogger(__name__)


@dataclass
class ReasoningRequest:
    """Parameters for a reasoning operation."""
    ontology_name: str
    reasoner_type: str = 'pellet'
    save_as_version: bool = False
    auto_promote_significant: bool = False


@dataclass
class ReasoningResult:
    """Outcome of a reasoning operation."""
    success: bool
    message: str
    classes_before: int = 0
    classes_after: int = 0
    properties_before: int = 0
    properties_after: int = 0
    hierarchical_relationships: int = 0
    inferred_relationships: list = field(default_factory=list)
    sample_hierarchy: list = field(default_factory=list)
    version_info: Optional[dict] = None
    error: Optional[str] = None

    def to_response_dict(self) -> dict:
        """Build the JSON response payload."""
        if not self.success:
            return {'success': False, 'error': self.error or self.message}

        data = {
            'success': True,
            'message': self.message,
            'results': {
                'classes_before': self.classes_before,
                'classes_after': self.classes_after,
                'properties_before': self.properties_before,
                'properties_after': self.properties_after,
                'classes_inferred': self.classes_after - self.classes_before,
                'properties_inferred': self.properties_after - self.properties_before,
                'hierarchical_relationships': self.hierarchical_relationships,
                'new_inferred_relationships': len(self.inferred_relationships),
                'sample_hierarchy': self.sample_hierarchy,
                'inferred_relationships': self.inferred_relationships[:5],
            },
        }
        if self.version_info:
            data['version'] = self.version_info
        return data


def execute_reasoning(req: ReasoningRequest) -> ReasoningResult:
    """Run OWL reasoning on an ontology and optionally save the result as a new version.

    Must be called inside a Flask app context (uses db.session).
    """
    # Look up ontology
    stmt = select(Ontology).where(Ontology.name == req.ontology_name)
    ontology = db.session.execute(stmt).scalar_one_or_none()
    if not ontology:
        return ReasoningResult(
            success=False, message=f'Ontology {req.ontology_name} not found',
            error=f'Ontology {req.ontology_name} not found',
        )

    if not ontology.current_content:
        return ReasoningResult(
            success=False, message='No content found for ontology',
            error='No content found for ontology',
        )

    try:
        import owlready2
    except ImportError:
        return ReasoningResult(
            success=False, message='owlready2 not available',
            error='owlready2 not available',
        )

    try:
        return _run_reasoning_pipeline(ontology, req)
    except Exception as exc:
        logger.error("Reasoning failed for %s: %s", req.ontology_name, exc)
        return ReasoningResult(
            success=False, message=f'Reasoning failed: {exc}',
            error=f'Reasoning failed: {exc}',
        )


# ---------------------------------------------------------------------------
# Internal pipeline
# ---------------------------------------------------------------------------

def _run_reasoning_pipeline(ontology: Ontology, req: ReasoningRequest) -> ReasoningResult:
    """Core reasoning pipeline: parse -> strip imports -> reason -> diff -> version."""
    import owlready2

    # Parse content and strip owl:imports
    content = ontology.current_content
    g = rdflib.Graph()
    fmt = 'xml' if content.strip().startswith('<?xml') else 'turtle'
    g.parse(data=content, format=fmt)

    for s, p, o in list(g.triples((None, OWL.imports, None))):
        g.remove((s, p, o))
        logger.info("Removed import: %s", o)

    # Convert to RDF/XML for owlready2
    rdfxml_content = g.serialize(format='xml')

    # Write temp file, load into owlready2
    with tempfile.NamedTemporaryFile(mode='w', suffix='.owl', delete=False) as f:
        f.write(rdfxml_content)
        temp_file = f.name

    try:
        world = owlready2.World()
        onto = world.get_ontology(f'file://{temp_file}').load()

        # Snapshot before reasoning
        classes_before = len(list(onto.classes()))
        properties_before = len(list(onto.properties()))
        hierarchy_before = _collect_hierarchy(onto)

        # Run reasoner
        with onto:
            owlready2.sync_reasoner_pellet(world)

        # Snapshot after reasoning
        classes_after = len(list(onto.classes()))
        properties_after = len(list(onto.properties()))

        base_uri = ontology.base_uri or f"http://ontserve.local/ontology/{req.ontology_name}#"
        hierarchy_after, inferred = _diff_hierarchy(
            onto, hierarchy_before, base_uri,
        )

        sample = _build_sample_hierarchy(hierarchy_after, limit=10)

        # Optionally save as version
        version_info = None
        if req.save_as_version:
            version_info = _save_reasoning_version(
                ontology, onto, temp_file, content,
                req, inferred, hierarchy_after,
                classes_before, classes_after,
                properties_before, properties_after,
            )

        return ReasoningResult(
            success=True,
            message=(
                f'Reasoning completed successfully. '
                f'Found {len(hierarchy_after)} hierarchical relationships.'
            ),
            classes_before=classes_before,
            classes_after=classes_after,
            properties_before=properties_before,
            properties_after=properties_after,
            hierarchical_relationships=len(hierarchy_after),
            inferred_relationships=inferred,
            sample_hierarchy=sample,
            version_info=version_info,
        )
    finally:
        os.unlink(temp_file)


# ---------------------------------------------------------------------------
# Hierarchy helpers
# ---------------------------------------------------------------------------

def _collect_hierarchy(onto) -> dict:
    """Collect class -> parent mappings from an owlready2 ontology."""
    hierarchy = {}
    for cls in onto.classes():
        parents = [str(p) for p in cls.is_a if hasattr(p, 'name')]
        if parents:
            hierarchy[str(cls)] = parents
    return hierarchy


def _clean_owlready_uri(uri_str: str, base_uri: str) -> str:
    """Convert owlready2 temp URIs (e.g. 'tmpXXX.ClassName') to proper ontology URIs."""
    if not uri_str:
        return uri_str
    if uri_str.startswith('http://'):
        return uri_str
    if '.' in uri_str:
        parts = uri_str.split('.')
        if len(parts) == 2 and parts[0].startswith('tmp'):
            return f"{base_uri}{parts[1]}"
    if '#' not in uri_str and '/' not in uri_str:
        return f"{base_uri}{uri_str}"
    return uri_str


def _diff_hierarchy(onto, hierarchy_before: dict, base_uri: str):
    """Collect post-reasoning hierarchy and identify newly inferred relationships.

    Returns (hierarchy_after, inferred_relationships).
    """
    hierarchy_after = {}
    inferred = []

    for cls in onto.classes():
        parents = [str(p) for p in cls.is_a if hasattr(p, 'name')]
        if not parents:
            continue

        clean_child = _clean_owlready_uri(str(cls), base_uri)
        clean_parents = [_clean_owlready_uri(p, base_uri) for p in parents]
        hierarchy_after[clean_child] = clean_parents

        old_parents = set(hierarchy_before.get(str(cls), []))
        for new_parent in set(parents) - old_parents:
            inferred.append({
                'child': clean_child,
                'parent': _clean_owlready_uri(new_parent, base_uri),
                'type': 'subClassOf',
            })

    return hierarchy_after, inferred


def _build_sample_hierarchy(hierarchy: dict, limit: int = 10) -> list:
    """Extract a sample of hierarchy entries for the UI response."""
    sample = []
    for cls_uri, parent_uris in list(hierarchy.items())[:limit]:
        if parent_uris:
            class_name = cls_uri.split('#')[-1] if '#' in cls_uri else cls_uri.split('/')[-1]
            parent_names = [
                p.split('#')[-1] if '#' in p else p.split('/')[-1]
                for p in parent_uris
            ]
            sample.append({'class': class_name, 'parents': parent_names})
    return sample


# ---------------------------------------------------------------------------
# Version persistence
# ---------------------------------------------------------------------------

def _save_reasoning_version(
    ontology, onto, temp_file, original_content,
    req, inferred, hierarchy_after,
    classes_before, classes_after,
    properties_before, properties_after,
) -> dict:
    """Save reasoning results as a new ontology version."""
    try:
        onto.save(temp_file, format='rdfxml')
        with open(temp_file, 'r', encoding='utf-8') as f:
            enriched_content = f.read()

        # Convert back to Turtle if the original was Turtle
        if not original_content.strip().startswith('<?xml'):
            g = rdflib.Graph()
            g.parse(data=enriched_content, format='xml')
            enriched_content = g.serialize(format='turtle')

        current_version = ontology.current_version
        next_version = (current_version.version_number + 1) if current_version else 1

        if inferred:
            change_summary = (
                f'Applied {req.reasoner_type} reasoning. '
                f'Added {len(inferred)} inferred relationships: '
                f'{classes_after - classes_before} new classes, '
                f'{properties_after - properties_before} new properties.'
            )
        else:
            change_summary = (
                f'Applied {req.reasoner_type} reasoning. '
                f'No new relationships inferred. '
                f'URI prefixes normalized and ontology structure validated. '
                f'Found {len(hierarchy_after)} existing hierarchical relationships.'
            )

        new_version = OntologyVersion(
            ontology_id=ontology.id,
            version_number=next_version,
            version_tag=f'v{next_version}.0-reasoned-{req.reasoner_type}',
            content=enriched_content,
            content_hash=hashlib.sha256(enriched_content.encode()).hexdigest(),
            change_summary=change_summary,
            created_by='reasoning-engine',
            created_at=datetime.now(timezone.utc),
            is_current=False,
            is_draft=True,
            workflow_status='review',
            meta_data={
                'reasoning': {
                    'reasoner_type': req.reasoner_type,
                    'classes_before': classes_before,
                    'classes_after': classes_after,
                    'properties_before': properties_before,
                    'properties_after': properties_after,
                    'inferred_relationships': inferred,
                    'hierarchical_relationships': len(hierarchy_after),
                }
            },
        )
        db.session.add(new_version)
        db.session.flush()

        auto_promoted = False
        if req.auto_promote_significant and inferred:
            auto_promoted = _auto_promote_version(
                ontology, new_version, enriched_content, next_version, inferred,
            )

        db.session.commit()

        if inferred:
            msg = f'Created version {next_version} with {len(inferred)} inferred relationships'
            if auto_promoted:
                msg += ' (Auto-promoted to current)'
        else:
            msg = f'Created version {next_version} with normalized URIs and validated structure'

        return {
            'version_created': True,
            'version_number': next_version,
            'version_tag': new_version.version_tag,
            'version_id': new_version.id,
            'is_draft': not auto_promoted,
            'is_current': auto_promoted,
            'auto_promoted': auto_promoted,
            'message': msg,
        }

    except Exception as exc:
        logger.error("Failed to create version: %s", exc)
        return {'version_created': False, 'error': str(exc)}


def _auto_promote_version(ontology, new_version, content, version_number, inferred):
    """Promote a reasoning version to current if it has significant inferences."""
    stmt = select(OntologyVersion).where(
        OntologyVersion.ontology_id == ontology.id
    )
    for v in db.session.execute(stmt).scalars().all():
        v.is_current = False

    new_version.is_current = True
    new_version.is_draft = False
    new_version.workflow_status = 'published'

    logger.info(
        "Auto-promoted version %d to current due to %d inferred relationships",
        version_number, len(inferred),
    )

    try:
        from web.entity_extraction import extract_entities_from_content
        entity_counts = extract_entities_from_content(ontology, content)
        logger.info(
            "Re-extracted %d entities for auto-promoted version %d",
            sum(entity_counts.values()), version_number,
        )
    except Exception as exc:
        logger.warning("Failed to re-extract entities during auto-promotion: %s", exc)

    return True
