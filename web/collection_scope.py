"""
Collection scope of the entity queries of one request.

A page of an ontology activates the scope of that ontology
(services.collections.scope_of). From then on, every ORM query of
OntologyEntity in the request leaves out the rows of the ontologies outside
that scope: the entity found by a fragment, the children and parents of a
class, the properties whose domain is one of its ancestors, the labels of
linked IRIs. A page of the ProEthica scope therefore reads the rows it read
before other collections existed, whatever IRIs, fragments, labels or parent
links the ontologies of another collection declare.

The limit names the ontologies to leave out, so a database whose ontologies
all lie in the scope runs every query unchanged, and elsewhere the queries
keep their access path and the order of their rows. A query that has to see
every collection passes the execution option ``all_collections=True``.
"""

from flask import g, has_request_context
from sqlalchemy import event, select
from sqlalchemy.orm import with_loader_criteria

from services import collections as coll

_G_KEY = 'entity_scope_excluded'
ALL_COLLECTIONS = 'all_collections'


def excluded_ids(ontology) -> tuple:
    """Ids of the ontologies outside the scope of the pages of ``ontology``.
    None stands for a page without an ontology row, which sees the ProEthica
    scope."""
    from web.models import db, Ontology
    rows = db.session.execute(select(Ontology)).scalars().all()
    keys = coll.scope_of(ontology)
    inside = set(coll.ids_in_scope(rows, keys))
    return tuple(sorted(o.id for o in rows if o.id not in inside))


def activate(ontology) -> None:
    """Limit the entity queries of the current request to the scope of ``ontology``."""
    setattr(g, _G_KEY, excluded_ids(ontology))


def active_exclusions():
    """The ids the active scope leaves out, or None when no scope is active."""
    return g.get(_G_KEY) if has_request_context() else None


def _limit_entities(state) -> None:
    excluded = active_exclusions()
    if (not excluded or not state.is_select or state.is_column_load or state.is_relationship_load
            or state.execution_options.get(ALL_COLLECTIONS)):
        return
    from web.models import OntologyEntity
    state.statement = state.statement.options(
        with_loader_criteria(OntologyEntity, lambda cls: cls.ontology_id.not_in(excluded), include_aliases=True))


def install(session_class) -> None:
    """Register the limit on the session class of the app (once)."""
    if not event.contains(session_class, 'do_orm_execute', _limit_entities):
        event.listen(session_class, 'do_orm_execute', _limit_entities)
