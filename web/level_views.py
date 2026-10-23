"""
View builders for the ProEthica level pages and the headline counts of the
home page.

The builders read the entity rows the sync stores, never the TTL, so a page
costs a few queries and no graph parse. JSON properties are read in Python
rather than with PostgreSQL operators, because the test app runs on SQLite.

``ClassIndex`` holds the asserted parents of every class of the stack
ontologies a page loads (``parent_uri`` plus ``properties.rdf_superclasses``)
and answers, per class, the nearest of the nine core components. The same
index serves the intermediate taxonomy, the intermediate-extended catalog,
the engineering-ethics standards view, the core grid and the headline counts.
"""

from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import func, select

from services import proethica_stack as stack
from web.models import Ontology, OntologyEntity

CORE_NS = 'http://proethica.org/ontology/core#'
CASES_NS = 'http://proethica.org/ontology/cases#'
RESOURCE_URI = CORE_NS + 'Resource'
OTHER = 'Other'

# Readable labels for the BFO and IAO classes the core components ground in.
GROUNDING_LABELS = {
    'BFO_0000023': 'BFO role',
    'BFO_0000020': 'BFO specifically dependent continuant',
    'BFO_0000015': 'BFO process',
    'BFO_0000016': 'BFO disposition',
    'BFO_0000040': 'BFO material entity',
    'IAO_0000033': 'IAO directive information entity',
    'IAO_0000030': 'IAO information content entity',
}


def _props(row: Any) -> Dict[str, Any]:
    props = getattr(row, 'properties', None)
    return props if isinstance(props, dict) else {}


def fragment(uri: str) -> str:
    return str(uri).rsplit('#', 1)[-1].rsplit('/', 1)[-1]


def is_deprecated(row: Any) -> bool:
    return str(_props(row).get('deprecated', '')).lower() == 'true'


def extra_parents(row: Any) -> List[str]:
    """The asserted parents of a class other than its primary ``parent_uri``."""
    out = []
    for parent in _props(row).get('rdf_superclasses') or []:
        if parent and parent != row.parent_uri and parent != row.uri and parent not in out:
            out.append(parent)
    return out


def _label_key(row: Any) -> str:
    return (row.label or fragment(row.uri)).lower()


class ClassIndex:
    """Asserted parents and component letters over a set of class rows.

    ``rows`` are objects with ``uri``, ``parent_uri`` and ``properties`` (and
    ``label`` and ``ontology`` when loaded by ``load_class_rows``). A core class
    carrying ``dtupleComponent`` is a component; ``component(uri)`` returns the
    URI of the component reached in the fewest steps over all asserted
    parents, ties going to the earlier letter of the tuple. Rows that share a
    URI (a class declared again in another ontology) pool their parents, and
    the row of the earliest stack level supplies the label and the link.
    """

    def __init__(self, rows: Iterable[Any]):
        rank = {lvl.ontology: i for i, lvl in enumerate(stack.LEVELS)}
        self.parents: Dict[str, List[str]] = {}
        self.letters: Dict[str, str] = {}
        self._home: Dict[str, Tuple[int, Optional[str], Optional[str]]] = {}
        for row in rows:
            parents = self.parents.setdefault(row.uri, [])
            for parent in [row.parent_uri] + list(_props(row).get('rdf_superclasses') or []):
                if parent and parent != row.uri and parent not in parents:
                    parents.append(parent)
            letter = _props(row).get('dtupleComponent')
            if letter and row.uri.startswith(CORE_NS):
                self.letters[row.uri] = str(letter)
            ontology = getattr(row, 'ontology', None)
            entry = (rank.get(ontology, len(rank)), getattr(row, 'label', None), ontology)
            if row.uri not in self._home or entry[0] < self._home[row.uri][0]:
                self._home[row.uri] = entry
        self.component_by_letter = {ltr: uri for uri, ltr in self.letters.items()}
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

    def ref(self, uri: Optional[str]) -> Optional[Dict[str, Any]]:
        """Label and link target of a class: ``ontology`` is None when the class
        is not among the loaded rows (a BFO or IAO parent), so no link."""
        if not uri:
            return None
        _, label, ontology = self._home.get(uri, (None, None, None))
        frag = fragment(uri)
        return {'uri': uri, 'label': label or GROUNDING_LABELS.get(frag) or frag, 'fragment': frag,
                'ontology': ontology}


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


def _ontology(key: str) -> str:
    return stack.LEVEL_BY_KEY[key].ontology


# ---------------------------------------------------------------------------
# Case provenance of the classes minted from cases
# ---------------------------------------------------------------------------

def _case_ints(value: Any) -> List[int]:
    values = value if isinstance(value, list) else [value]
    out = []
    for v in values:
        try:
            out.append(int(str(v)))
        except (TypeError, ValueError):
            continue
    return out


def case_numbers(props: Dict[str, Any]) -> Tuple[Optional[int], List[int]]:
    """(first case, every case with the first leading) from the commit-time
    proeth-prov:firstDiscoveredInCase and discoveredInCase markers, which hold
    an integer or a list. Keys are matched without regard to case."""
    first = None
    numbers: List[int] = []
    for key, value in (props or {}).items():
        lowered = key.lower()
        if lowered == 'firstdiscoveredincase':
            got = _case_ints(value)
            first = got[0] if got else None
        elif lowered == 'discoveredincase':
            numbers.extend(_case_ints(value))
    ordered: List[int] = []
    for n in ([first] if first is not None else []) + numbers:
        if n not in ordered:
            ordered.append(n)
    return first, ordered


def case_titles(session, numbers: Iterable[int]) -> Dict[int, str]:
    """Display titles of the case ontologies proethica-case-<n>, in one query.
    Numbers without a loaded case ontology are absent from the result."""
    names = {f'proethica-case-{n}': n for n in set(numbers)}
    if not names:
        return {}
    rows = session.execute(select(Ontology.name, Ontology.meta_data)
                           .where(Ontology.name.in_(list(names)))).all()
    return {names[name]: ((meta if isinstance(meta, dict) else {}).get('display_name') or name)
            for name, meta in rows}


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------

def headline_counts(session) -> Dict[str, int]:
    """One count per level for the home page cards, keyed by ``Level.key``:
    core components, intermediate classes that are not deprecated,
    intermediate-extended classes, and engineering-ethics standards."""
    core, intermediate = _ontology('core'), _ontology('intermediate')
    extended, standards = _ontology('extended'), _ontology('engineering-ethics')

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


# ---------------------------------------------------------------------------
# Core: the D-tuple grid
# ---------------------------------------------------------------------------

def framework_grid(classes: Iterable[Any]) -> List[Dict[str, Any]]:
    """The nine components in tuple order, from the core class rows: letter,
    name, fragment, definition (the stored ``comment``, which the extractor
    fills from iao:0000115 first) and the BFO or IAO class it grounds in."""
    order = {ltr: i for i, ltr in enumerate(stack.DTUPLE_ORDER)}
    out = []
    for row in classes:
        letter = _props(row).get('dtupleComponent')
        if not letter:
            continue
        grounding = next((fragment(p) for p in [row.parent_uri] + extra_parents(row)
                          if p and fragment(p) in GROUNDING_LABELS), None)
        text = (row.comment or '').strip()
        out.append({
            'letter': str(letter),
            'name': row.label or fragment(row.uri),
            'fragment': fragment(row.uri),
            'definition': (text[:150].rstrip() + '...') if len(text) > 150 else text,
            'grounding_frag': grounding,
            'grounding_label': GROUNDING_LABELS.get(grounding),
        })
    out.sort(key=lambda c: order.get(c['letter'], len(order)))
    return out


# ---------------------------------------------------------------------------
# Intermediate: the asserted subclass tree under each component
# ---------------------------------------------------------------------------

def build_taxonomy(session) -> Dict[str, Any]:
    return taxonomy_from_rows(load_class_rows(session, [_ontology('core'), _ontology('intermediate')]))


def taxonomy_from_rows(rows: List[Any]) -> Dict[str, Any]:
    """The intermediate classes as one tree per core component, from the class
    rows of core and intermediate.

    A class sits under its primary parent; its other parents are listed as
    "also under". The roots of a component are the classes whose primary
    parent lies outside intermediate. Deprecated classes are left out, and a
    component without intermediate kinds lists the kinds core defines for it.
    """
    core, intermediate = _ontology('core'), _ontology('intermediate')
    index = ClassIndex(rows)
    own = [r for r in rows if r.ontology == intermediate and not is_deprecated(r)]
    own_uris = {r.uri for r in own}

    children: Dict[str, List[Any]] = defaultdict(list)
    roots: List[Any] = []
    for r in own:
        if r.parent_uri in own_uris and r.parent_uri != r.uri:
            children[r.parent_uri].append(r)
        else:
            roots.append(r)

    def node(row: Any, seen: frozenset) -> Dict[str, Any]:
        seen = seen | {row.uri}
        kids = [k for k in sorted(children.get(row.uri, []), key=_label_key) if k.uri not in seen]
        return {
            'label': row.label or fragment(row.uri),
            'fragment': fragment(row.uri),
            'ontology': intermediate,
            'definition': (row.comment or '').strip(),
            'also_under': [index.ref(p) for p in extra_parents(row)],
            'children': [node(k, seen) for k in kids],
        }

    def size(n: Dict[str, Any]) -> int:
        return 1 + sum(size(c) for c in n['children'])

    by_letter: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in sorted(roots, key=_label_key):
        letter = index.letter(r.uri) or OTHER
        item = node(r, frozenset())
        comp = index.component(r.uri)
        # A root hanging off a core class other than its component, such as
        # EthicalCode under core:Guideline, names that parent.
        item['under'] = index.ref(r.parent_uri) if r.parent_uri and r.parent_uri != comp else None
        by_letter[letter].append(item)

    groups = []
    for letter in stack.DTUPLE_ORDER + (OTHER,):
        nodes = by_letter.get(letter, [])
        comp_uri = index.component_by_letter.get(letter)
        if letter == OTHER and not nodes:
            continue
        core_kinds = []
        if not nodes and comp_uri:
            core_kinds = [index.ref(r.uri) for r in sorted(rows, key=_label_key)
                          if r.ontology == core and r.uri != comp_uri and index.component(r.uri) == comp_uri]
        groups.append({
            'letter': letter if letter != OTHER else None,
            'label': stack.COMPONENT_LABELS.get(letter, OTHER),
            'component': index.ref(comp_uri),
            'nodes': nodes,
            'count': sum(size(n) for n in nodes),
            'core_kinds': core_kinds,
        })
    return {'groups': groups, 'total': len(own)}


# ---------------------------------------------------------------------------
# Intermediate-extended: the case-discovered catalog
# ---------------------------------------------------------------------------

def build_catalog(session, case: Optional[int] = None) -> Dict[str, Any]:
    rows = load_class_rows(session, [_ontology('core'), _ontology('intermediate'), _ontology('extended')])
    numbers = {n for r in rows if r.ontology == _ontology('extended')
               for n in case_numbers(_props(r))[1]}
    return catalog_from_rows(rows, case=case, titles=case_titles(session, numbers))


def catalog_from_rows(rows: List[Any], case: Optional[int] = None,
                      titles: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    """The intermediate-extended classes grouped by component and then by
    primary parent, each with its first case, the number of further cases and
    its source excerpt, from the class rows of core, intermediate and
    intermediate-extended. ``case`` keeps the classes discovered in that case;
    ``titles`` maps case numbers to the titles of their case ontologies."""
    extended = _ontology('extended')
    titles = titles or {}
    index = ClassIndex(rows)
    own = [r for r in rows if r.ontology == extended and not is_deprecated(r)]
    provenance = {r.uri: case_numbers(_props(r)) for r in own}
    if case is not None:
        own = [r for r in own if case in provenance[r.uri][1]]

    tree: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in sorted(own, key=_label_key):
        first, numbers = provenance[r.uri]
        first = first if first is not None else (numbers[0] if numbers else None)
        excerpt = str(_props(r).get('sourceText') or '').strip()
        tree[index.letter(r.uri) or OTHER][r.parent_uri or ''].append({
            'label': r.label or fragment(r.uri),
            'fragment': fragment(r.uri),
            'ontology': extended,
            'also_under': [index.ref(p) for p in extra_parents(r)],
            'first': ({'num': first, 'title': titles.get(first), 'name': f'proethica-case-{first}'}
                      if first is not None else None),
            'further': max(len(numbers) - 1, 0),
            'excerpt': (excerpt[:280].rstrip() + '...') if len(excerpt) > 280 else excerpt,
        })

    groups = []
    for letter in stack.DTUPLE_ORDER + (OTHER,):
        parents = tree.get(letter)
        if not parents:
            continue
        families = [{'parent': index.ref(uri), 'entries': entries, 'count': len(entries)}
                    for uri, entries in parents.items()]
        families.sort(key=lambda f: (-f['count'], (f['parent']['label'] if f['parent'] else '').lower()))
        groups.append({
            'letter': letter if letter != OTHER else None,
            'label': stack.COMPONENT_LABELS.get(letter, OTHER),
            'families': families,
            'count': sum(f['count'] for f in families),
        })
    cases = {n for r in own for n in provenance[r.uri][1]}
    return {'groups': groups, 'total': len(own), 'case_count': len(cases), 'case': case,
            'case_title': titles.get(case) if case is not None else None}


# ---------------------------------------------------------------------------
# Engineering ethics: the standards view
# ---------------------------------------------------------------------------

def _humanize(value: Any) -> str:
    return str(value).replace('_', ' ')


def build_standards(session) -> Dict[str, Any]:
    ee = _ontology('engineering-ethics')
    rows = load_class_rows(session, [_ontology('core'), _ontology('intermediate'), ee, stack.CASES_VOCABULARY])
    return standards_from_rows(rows, _individual_rows(session, ee))


def standards_from_rows(rows: List[Any], individuals: List[Any]) -> Dict[str, Any]:
    """The engineering-ethics individuals typed with a kind of core:Resource
    (the standards), its classes grouped by component (the compliance
    vocabulary), and the case-structure classes and individuals typed in the
    proethica-cases vocabulary. ``rows`` are the class rows of core,
    intermediate, engineering-ethics and proethica-cases; ``individuals`` are
    the individual rows of engineering-ethics."""
    ee = _ontology('engineering-ethics')
    index = ClassIndex(rows)

    standards, structure_individuals, other_individuals = [], [], []
    for r in sorted(individuals, key=_label_key):
        props = _props(r)
        if is_standard(r, index):
            domains = props.get('applicableDomains') or []
            standards.append({
                'label': r.label or fragment(r.uri),
                'fragment': fragment(r.uri),
                'ontology': ee,
                'identifier': props.get('identifier'),
                'publisher': props.get('publisher'),
                'source': props.get('source'),
                'source_host': urlparse(str(props.get('source') or '')).netloc.removeprefix('www.'),
                'domains': [_humanize(d) for d in (domains if isinstance(domains, list) else [domains])],
                'kind': index.ref(r.parent_uri),
            })
        else:
            item = {'label': r.label or fragment(r.uri), 'fragment': fragment(r.uri), 'ontology': ee,
                    'kind': index.ref(r.parent_uri), 'definition': (r.comment or '').strip()}
            if any(t.startswith(CASES_NS) for t in individual_types(r)):
                structure_individuals.append(item)
            else:
                other_individuals.append(item)

    by_letter: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    structure_classes = []
    for r in sorted((r for r in rows if r.ontology == ee and not is_deprecated(r)), key=_label_key):
        item = {'label': r.label or fragment(r.uri), 'fragment': fragment(r.uri), 'ontology': ee,
                'kind': index.ref(r.parent_uri), 'definition': (r.comment or '').strip()}
        if r.parent_uri and r.parent_uri.startswith(CASES_NS):
            structure_classes.append(item)
        else:
            by_letter[index.letter(r.uri) or OTHER].append(item)
    vocabulary = [{'letter': ltr if ltr != OTHER else None, 'label': stack.COMPONENT_LABELS.get(ltr, OTHER),
                   'classes': by_letter[ltr]}
                  for ltr in stack.DTUPLE_ORDER + (OTHER,) if by_letter.get(ltr)]
    return {
        'standards': standards,
        'vocabulary': vocabulary,
        'vocabulary_count': sum(len(g['classes']) for g in vocabulary),
        'structure_classes': structure_classes,
        'structure_individuals': sorted(structure_individuals, key=lambda i: i['label'].lower()),
        'other_individuals': other_individuals,
    }
