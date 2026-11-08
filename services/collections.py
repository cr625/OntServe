"""
Collections: the bodies of work whose ontologies OntServe hosts.

A collection groups the ontologies of one project or source and carries their
policy (config/collections.yaml): the landing page, the collections it uses,
whether it is listed, whether its classes receive embeddings, its reasoning
recipe and whether its case ontologies render with the case page. Categories
(services.ontology_categories) classify ontologies within a collection.

Every ontology resolves to one collection key or to None, in this order:
``metadata.collection`` when it names a configured collection, the
``members`` list of a collection, the ``categories`` list of a collection
(matched against the category resolution), then the rules of
``DEFAULT_RULES``. Nothing here touches Flask or the database: the functions
accept the objects that services.ontology_categories accepts (the
``Ontology`` model, a row dict with a ``metadata`` key, a test stub).

The ProEthica scope is the ProEthica collection, the collections it uses
(transitively) and the ontologies of no collection. The lookups ProEthica
depends on consider the rows of this scope only, so an ontology of another
collection that declares the same IRI, fragment or label does not answer
them. An ontology of no collection stays in the scope, as every ontology was
before collections existed.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

import yaml

from services import ontology_categories as categories
from services import proethica_stack as stack

CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config' / 'collections.yaml'

COLLECTION_KEY = categories.COLLECTION_KEY   # metadata key of an explicit collection
PROETHICA = 'proethica'
SHARED = 'shared'

HOME_INDEX = 'index'
HOME_DEFAULT = 'default_collection'
LANDINGS = ('proethica_stack', 'generic')
REASONING = ('proethica_merged', 'none')
VISIBILITY = ('public', 'private')


class CollectionsConfigError(ValueError):
    """A collections file that does not follow the schema."""


@dataclass(frozen=True)
class Collection:
    key: str
    title: str
    description: str = ''
    landing: str = 'generic'
    uses: Tuple[str, ...] = ()
    default_visibility: str = 'public'
    embeddings: bool = False
    reasoning: str = 'none'
    case_view: bool = False
    categories: Tuple[str, ...] = ()
    members: Tuple[str, ...] = ()

    @property
    def public(self) -> bool:
        return self.default_visibility == 'public'


@dataclass(frozen=True)
class CollectionsConfig:
    home: str
    default_collection: str
    collections: Tuple[Collection, ...]

    @property
    def by_key(self) -> Dict[str, Collection]:
        return {c.key: c for c in self.collections}

    def get(self, key: Optional[str]) -> Optional[Collection]:
        return self.by_key.get(key) if key else None


_FIELDS = {'title', 'description', 'landing', 'uses', 'default_visibility', 'embeddings',
           'reasoning', 'case_view', 'categories', 'members'}


def _names(value: Any, where: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CollectionsConfigError(f'{where} must be a list')
    return tuple(str(v).strip() for v in value if str(v).strip())


def parse_config(data: Any) -> CollectionsConfig:
    """Check a loaded collections file and return it."""
    if not isinstance(data, dict):
        raise CollectionsConfigError('the collections file is not a mapping')
    raw = data.get('collections')
    if not isinstance(raw, dict) or not raw:
        raise CollectionsConfigError('collections must be a non-empty mapping')
    items = []
    for key, spec in raw.items():
        key = str(key)
        if categories.slugify(key) != key:
            raise CollectionsConfigError(f'collection key {key} is not a slug')
        spec = spec or {}
        extra = sorted(set(spec) - _FIELDS)
        if extra:
            raise CollectionsConfigError(f"{key}: unknown keys {', '.join(extra)}")
        title = str(spec.get('title') or '').strip()
        if not title:
            raise CollectionsConfigError(f'{key}: title is required')
        item = Collection(
            key=key, title=title, description=' '.join(str(spec.get('description') or '').split()),
            landing=str(spec.get('landing') or 'generic'),
            uses=_names(spec.get('uses'), f'{key}.uses'),
            default_visibility=str(spec.get('default_visibility') or 'public'),
            embeddings=bool(spec.get('embeddings', False)),
            reasoning=str(spec.get('reasoning') or 'none'),
            case_view=bool(spec.get('case_view', False)),
            categories=_names(spec.get('categories'), f'{key}.categories'),
            members=_names(spec.get('members'), f'{key}.members'),
        )
        for field, value, allowed in (('landing', item.landing, LANDINGS), ('reasoning', item.reasoning, REASONING),
                                      ('default_visibility', item.default_visibility, VISIBILITY)):
            if value not in allowed:
                raise CollectionsConfigError(f"{key}.{field} must be one of {', '.join(allowed)}: {value}")
        items.append(item)
    keys = {c.key for c in items}
    if PROETHICA not in keys:
        raise CollectionsConfigError(f'the collection {PROETHICA} is required')
    seen_members: Dict[str, str] = {}
    seen_categories: Dict[str, str] = {}
    for c in items:
        unknown = sorted(set(c.uses) - keys)
        if unknown:
            raise CollectionsConfigError(f"{c.key}.uses names unknown collections: {', '.join(unknown)}")
        for name, seen, what in [(m, seen_members, 'member') for m in c.members] + \
                                [(k, seen_categories, 'category') for k in c.categories]:
            if name in seen:
                raise CollectionsConfigError(f'{what} {name} is listed by {seen[name]} and {c.key}')
            seen[name] = c.key
    home = str(data.get('home') or HOME_INDEX)
    if home not in (HOME_INDEX, HOME_DEFAULT):
        raise CollectionsConfigError(f'home must be {HOME_INDEX} or {HOME_DEFAULT}: {home}')
    default = str(data.get('default_collection') or PROETHICA)
    if default not in keys:
        raise CollectionsConfigError(f'default_collection names an unknown collection: {default}')
    return CollectionsConfig(home=home, default_collection=default, collections=tuple(items))


_CACHE: Dict[str, Tuple[Optional[float], CollectionsConfig]] = {}


def get_config(path: Optional[Path] = None) -> CollectionsConfig:
    """The collections file, read again when its modification time changes."""
    path = Path(path or CONFIG_PATH)
    mtime = path.stat().st_mtime if path.exists() else None
    cached = _CACHE.get(str(path))
    if cached is None or cached[0] != mtime:
        if mtime is None:
            raise CollectionsConfigError(f'collections file not found: {path}')
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        _CACHE[str(path)] = (mtime, parse_config(data))
    return _CACHE[str(path)][1]


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _is_proethica(ontology: Any) -> bool:
    """The case ontologies, the proethica- names and the ontologies of the stack."""
    name = str(_attr(ontology, 'name', '') or '')
    return (_attr(ontology, 'ontology_type') == 'case'
            or bool(categories.case_id_from_name(name))
            or name.startswith('proethica-')
            or stack.level_for(name) is not None
            or name in stack.SUPPORT_NAMES
            or name in (stack.CASES_VOCABULARY, stack.CASES_CODE))


Rule = Tuple[Callable[[Any], bool], str]

DEFAULT_RULES: Sequence[Rule] = (
    (_is_proethica, PROETHICA),
    (lambda o: _attr(o, 'ontology_type') == 'upper', SHARED),
)


def resolve(ontology: Any, config: Optional[CollectionsConfig] = None,
            rules: Sequence[Rule] = DEFAULT_RULES, explicit: bool = True) -> Optional[str]:
    """The collection key of one ontology, or None when nothing assigns it.
    With ``explicit=False`` the metadata value is ignored, which gives the
    default the settings page shows."""
    config = config or get_config()
    keys = config.by_key
    value = categories.collection_of(ontology) if explicit else None
    if value in keys:
        return value
    name = str(_attr(ontology, 'name', '') or '')
    for c in config.collections:
        if name in c.members:
            return c.key
    category = categories.resolve(ontology).category
    for c in config.collections:
        if category in c.categories:
            return c.key
    for predicate, key in rules:
        try:
            if predicate(ontology) and key in keys:
                return key
        except Exception:
            continue
    return None


def collection_for_category(category: str, config: Optional[CollectionsConfig] = None) -> Optional[str]:
    """The collection whose ``categories`` list names this category, or None."""
    config = config or get_config()
    return next((c.key for c in config.collections if category in c.categories), None)


def uses_closure(key: str, config: Optional[CollectionsConfig] = None) -> FrozenSet[str]:
    """The collection and every collection it uses, directly or through another."""
    config = config or get_config()
    seen, todo = set(), [key]
    while todo:
        current = todo.pop()
        if current in seen or config.get(current) is None:
            continue
        seen.add(current)
        todo.extend(config.get(current).uses)
    return frozenset(seen)


def proethica_scope(config: Optional[CollectionsConfig] = None) -> FrozenSet[Optional[str]]:
    """The collection keys of the ProEthica scope, None (no collection) included."""
    return uses_closure(PROETHICA, config) | {None}


def scope_keys(key: Optional[str], config: Optional[CollectionsConfig] = None) -> FrozenSet[Optional[str]]:
    """The keys whose ontologies the pages of collection ``key`` see: the
    ProEthica scope for a key inside it, else the collection and those it uses."""
    config = config or get_config()
    base = proethica_scope(config)
    return base if key in base else uses_closure(key, config)


def scope_of(ontology: Any, config: Optional[CollectionsConfig] = None) -> FrozenSet[Optional[str]]:
    """scope_keys of the collection of an ontology, the ProEthica scope for None."""
    config = config or get_config()
    return scope_keys(resolve(ontology, config) if ontology is not None else None, config)


def ids_in_scope(ontologies: Iterable[Any], keys: FrozenSet[Optional[str]],
                 config: Optional[CollectionsConfig] = None) -> List[int]:
    config = config or get_config()
    return [_attr(o, 'id') for o in ontologies if resolve(o, config) in keys]


def policy_for(ontology: Any, config: Optional[CollectionsConfig] = None) -> Collection:
    """The collection whose policy applies to an ontology: the ProEthica
    collection for every ontology of the ProEthica scope, so its shared and
    unassigned ontologies keep the ProEthica behaviour, else its own collection."""
    config = config or get_config()
    key = resolve(ontology, config)
    if key in proethica_scope(config):
        return config.get(PROETHICA)
    return config.get(key)


def embeddings_allowed(ontology: Any, config: Optional[CollectionsConfig] = None) -> bool:
    """True when the class rows of an ontology receive embeddings: the setting
    of its own collection, and True for an ontology of no collection."""
    config = config or get_config()
    key = resolve(ontology, config)
    return True if key is None else config.get(key).embeddings


# ---------------------------------------------------------------------------
# Index and landing pages
# ---------------------------------------------------------------------------

@dataclass
class IndexEntry:
    collection: Collection
    ontologies: List[Any]

    @property
    def count(self) -> int:
        return len(self.ontologies)


def index_entries(ontologies: Iterable[Any], include_private: bool = False,
                  config: Optional[CollectionsConfig] = None) -> List[IndexEntry]:
    """The collections in file order with their ontologies. A collection that
    is not public is included only with ``include_private``."""
    config = config or get_config()
    members: Dict[Optional[str], List[Any]] = {}
    for o in ontologies:
        members.setdefault(resolve(o, config), []).append(o)
    return [IndexEntry(c, members.get(c.key, [])) for c in config.collections
            if c.public or include_private]


def unassigned(ontologies: Iterable[Any], config: Optional[CollectionsConfig] = None) -> List[Any]:
    """The ontologies of no collection."""
    config = config or get_config()
    return [o for o in ontologies if resolve(o, config) is None]


@dataclass
class MemberGroup:
    label: Optional[str]            # category label, None when the collection has one category
    subgroups: List[Tuple[Optional[str], List[Any]]]

    @property
    def labelled(self) -> bool:
        """True when a subgroup carries a subcategory."""
        return any(sub for sub, _ in self.subgroups)


def landing_groups(key: str, ontologies: Iterable[Any],
                   config: Optional[CollectionsConfig] = None) -> List[MemberGroup]:
    """The ontologies of one collection by category (catalog order) and
    subcategory (alphabetical, the unlabelled ones last), names sorted."""
    config = config or get_config()
    rows = sorted((o for o in ontologies if resolve(o, config) == key),
                  key=lambda o: (str(_attr(o, 'name', '') or '').lower()))
    groups = []
    for grp in categories.group_ontologies(rows):
        subs: Dict[Optional[str], List[Any]] = {}
        for o in grp.ontologies:
            subs.setdefault(categories.resolve(o).subcategory, []).append(o)
        groups.append(MemberGroup(grp.category.label, [(s, subs[s]) for s, _ in grp.subgroups]))
    if len(groups) == 1:
        groups[0].label = None
    return groups
