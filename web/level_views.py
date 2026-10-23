"""
View builders for the ProEthica level pages and the headline counts of the
home page.

The builders read the entity rows the sync stores, never the TTL, so a page
costs a few queries and no graph parse. JSON properties are read in Python
rather than with PostgreSQL operators, because the test app runs on SQLite.

``ClassIndex`` holds the asserted parents of every class of the stack
ontologies a page loads (``parent_uri`` plus ``properties.rdf_superclasses``)
and answers, per class, the nearest of the nine core components.
"""

from collections import deque
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, select

from services import proethica_stack as stack
from web.models import Ontology, OntologyEntity

CORE_NS = 'http://proethica.org/ontology/core#'
RESOURCE_URI = CORE_NS + 'Resource'


def _props(row: Any) -> Dict[str, Any]:
    props = getattr(row, 'properties', None)
    return props if isinstance(props, dict) else {}


def is_deprecated(row: Any) -> bool:
    return str(_props(row).get('deprecated', '')).lower() == 'true'


class ClassIndex:
    """Asserted parents and component letters over a set of class rows.

    ``rows`` are objects with ``uri``, ``parent_uri`` and ``properties``. A core
    class carrying ``dtupleComponent`` is a component; ``component(uri)``
    returns the URI of the component reached in the fewest steps over all
    asserted parents, ties going to the earlier letter of the tuple. Rows that
    share a URI (a class declared again in another ontology) pool their parents.
    """

    def __init__(self, rows: Iterable[Any]):
        self.parents: Dict[str, List[str]] = {}
        self.letters: Dict[str, str] = {}
        for row in rows:
            parents = self.parents.setdefault(row.uri, [])
            for parent in [row.parent_uri] + list(_props(row).get('rdf_superclasses') or []):
                if parent and parent != row.uri and parent not in parents:
                    parents.append(parent)
            letter = _props(row).get('dtupleComponent')
            if letter and row.uri.startswith(CORE_NS):
                self.letters[row.uri] = str(letter)
        self._component: Dict[str, Optional[str]] = {}

    def component(self, uri: str) -> Optional[str]:
        if uri in self._component:
            return self._component[uri]
        order = {ltr: i for i, ltr in enumerate(stack.DTUPLE_ORDER)}
        found: Optional[str] = None
        seen = {uri}
        frontier = deque([uri])
        while frontier and found is None:
            # One breadth-first layer at a time, so the nearest component wins
            hits = []
            for _ in range(len(frontier)):
                node = frontier.popleft()
                if node in self.letters:
                    hits.append(node)
                    continue
                for parent in self.parents.get(node, []):
                    if parent not in seen:
                        seen.add(parent)
                        frontier.append(parent)
            if hits:
                found = min(hits, key=lambda u: order.get(self.letters[u], len(order)))
        self._component[uri] = found
        return found

    def letter(self, uri: str) -> Optional[str]:
        comp = self.component(uri)
        return self.letters.get(comp) if comp else None


def load_class_rows(session, ontology_names: Iterable[str]) -> List[Any]:
    """Class rows of the named ontologies, with the ontology name, in one query."""
    names = list(ontology_names)
    if not names:
        return []
    stmt = (select(OntologyEntity.uri, OntologyEntity.label, OntologyEntity.comment,
                   OntologyEntity.parent_uri, OntologyEntity.properties,
                   Ontology.name.label('ontology'))
            .join(Ontology, Ontology.id == OntologyEntity.ontology_id)
            .where(OntologyEntity.entity_type == 'class', Ontology.name.in_(names)))
    return session.execute(stmt).all()


def _individual_rows(session, ontology_name: str) -> List[Any]:
    stmt = (select(OntologyEntity.uri, OntologyEntity.label, OntologyEntity.comment,
                   OntologyEntity.parent_uri, OntologyEntity.properties)
            .join(Ontology, Ontology.id == OntologyEntity.ontology_id)
            .where(OntologyEntity.entity_type == 'individual', Ontology.name == ontology_name))
    return session.execute(stmt).all()


def individual_types(row: Any) -> List[str]:
    """The asserted types of an individual: the materialized ``parent_uri``
    plus ``properties.rdf_types`` when it carries several."""
    types = [row.parent_uri] if row.parent_uri else []
    for extra in _props(row).get('rdf_types') or []:
        if extra and extra not in types:
            types.append(extra)
    return types


def is_standard(row: Any, index: ClassIndex) -> bool:
    """An individual typed with a kind of core:Resource."""
    return any(index.component(t) == RESOURCE_URI for t in individual_types(row))


def headline_counts(session) -> Dict[str, int]:
    """One count per level for the home page cards, keyed by ``Level.key``:
    core components, intermediate classes that are not deprecated,
    intermediate-extended classes, and engineering-ethics standards."""
    core = stack.LEVEL_BY_KEY['core'].ontology
    intermediate = stack.LEVEL_BY_KEY['intermediate'].ontology
    extended = stack.LEVEL_BY_KEY['extended'].ontology
    standards = stack.LEVEL_BY_KEY['engineering-ethics'].ontology

    rows = load_class_rows(session, [core, intermediate, standards])
    index = ClassIndex(rows)
    extended_count = session.execute(
        select(func.count(OntologyEntity.id))
        .join(Ontology, Ontology.id == OntologyEntity.ontology_id)
        .where(OntologyEntity.entity_type == 'class', Ontology.name == extended)
    ).scalar() or 0
    return {
        'core': len(index.letters),
        'intermediate': sum(1 for r in rows if r.ontology == intermediate and not is_deprecated(r)),
        'extended': extended_count,
        'engineering-ethics': sum(1 for r in _individual_rows(session, standards) if is_standard(r, index)),
    }
