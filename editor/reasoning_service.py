"""Read-only reasoning for the visualization page.

Delegates to the shared Pellet harness (`servers/reasoning_tools.reason_detailed`
over the merged graph of `validation/pellet_validate`: foundation stub + core +
intermediate + cases base + NSPE + the target ontology), so the Run Inference
button reports the same inferences as the MCP reasoning tools instead of the
former isolated owlready run (which stripped imports and therefore reasoned
without the axioms that make inference meaningful here).

This endpoint never writes. The former save-as-version / auto-promote path
could replace the current ontology version from an unauthenticated public page
and diverge the database from the on-disk TTL; it was removed 2026-07-18.
Version minting belongs to the deliberate sync/commit workflows.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy import select

logger = logging.getLogger(__name__)


@dataclass
class ReasoningRequest:
    ontology_name: str
    reasoner_type: str = 'pellet'
    explain: bool = False


@dataclass
class ReasoningResult:
    success: bool
    message: str
    consistent: bool = False
    inferred_subclasses: List[dict] = field(default_factory=list)
    inferred_types: List[dict] = field(default_factory=list)
    nothing_entities: List[str] = field(default_factory=list)
    inferred_subclass_count: int = 0
    inferred_type_count: int = 0
    truncated: bool = False
    error: Optional[str] = None
    error_explanation: Optional[str] = None
    explanations: List[dict] = field(default_factory=list)
    inconsistency_explanation: Optional[dict] = None

    def to_response_dict(self) -> dict:
        return {
            'success': self.success,
            'message': self.message,
            'consistent': self.consistent,
            'inferred_subclasses': self.inferred_subclasses,
            'inferred_types': self.inferred_types,
            'nothing_entities': self.nothing_entities,
            'inferred_subclass_count': self.inferred_subclass_count,
            'inferred_type_count': self.inferred_type_count,
            'truncated': self.truncated,
            'error': self.error,
            'error_explanation': self.error_explanation,
            'explanations': self.explanations,
            'inconsistency_explanation': self.inconsistency_explanation,
        }


def _current_content(ontology_name: str) -> str:
    """Current-version content via the caller's app context (no re-bootstrap)."""
    from web.models import db, Ontology, OntologyVersion

    ontology = db.session.execute(
        select(Ontology).where(Ontology.name == ontology_name)
    ).scalar_one_or_none()
    if ontology is None:
        raise LookupError(f'Ontology {ontology_name} not found')
    version = db.session.execute(
        select(OntologyVersion).where(
            OntologyVersion.ontology_id == ontology.id,
            OntologyVersion.is_current.is_(True),
        )
    ).scalars().first()
    if version is None or not version.content:
        raise LookupError(f'No current content for {ontology_name}')
    return version.content


def execute_reasoning(req: ReasoningRequest, _content_loader=None) -> ReasoningResult:
    """Run the shared merged-graph Pellet pipeline, read-only."""
    loader = _content_loader or _current_content
    try:
        content = loader(req.ontology_name)
    except LookupError as exc:
        return ReasoningResult(success=False, message=str(exc), error='not-found')

    from servers.reasoning_tools import reason_detailed
    detail = reason_detailed(req.ontology_name, content=content, explain=req.explain)

    error = detail.get('error')
    # An inconsistent ontology is a successful reasoning RUN with a negative
    # verdict; only infrastructure failures are unsuccessful.
    if error and error != 'OwlReadyInconsistentOntologyError':
        logger.error(f"Reasoning failed for {req.ontology_name}: {error}")
        return ReasoningResult(
            success=False,
            message=f'Reasoning failed: {error}',
            error=error,
        )

    consistent = bool(detail.get('consistent'))
    message = (
        'Reasoning completed over the merged proethica graph '
        '(foundation + core + intermediate + this ontology). '
        + ('The ontology is consistent.' if consistent
           else 'THE MERGED ONTOLOGY IS INCONSISTENT.')
    )
    return ReasoningResult(
        success=True,
        message=message,
        consistent=consistent,
        inferred_subclasses=detail.get('inferred_subclasses', []),
        inferred_types=detail.get('inferred_types', []),
        nothing_entities=detail.get('nothing_entities', []),
        inferred_subclass_count=detail.get('inferred_subclass_count', 0),
        inferred_type_count=detail.get('inferred_type_count', 0),
        truncated=bool(detail.get('truncated')),
        error=detail.get('error'),
        error_explanation=detail.get('error_explanation'),
        explanations=detail.get('explanations', []),
        inconsistency_explanation=detail.get('inconsistency_explanation'),
    )
