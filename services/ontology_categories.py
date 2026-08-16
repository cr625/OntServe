"""
Ontology categorisation for the repository index.

Every ontology resolves to a (category, subcategory) pair. An explicit value
stored on the ontology row (``metadata.category`` / ``metadata.subcategory``,
settable from the settings page or the metadata API) always wins; otherwise
an ordered rule list derives a default from ``ontology_type``,
``source_system`` and the name. Nothing here touches Flask or the database:
the functions accept any object exposing ``name``, ``ontology_type``,
``source_system`` and ``meta_data`` (the ``Ontology`` model, a ``to_dict()``
result wrapped in ``SimpleNamespace``, or a test stub).

The catalog (``CATEGORIES``) carries display order, icon, colour and collapse
behaviour per category so the index template stays free of category-specific
branches. A category collapses to a single summary row when it holds more
than ``collapse_threshold`` ontologies unless the catalog pins it open or
closed.

Adding a category: append a ``Category`` to ``CATEGORIES`` and, if it should be
inferred, a rule to ``DEFAULT_RULES``. Ontologies that match no rule fall into
``UNCATEGORIZED``.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

CATEGORY_KEY = 'category'
SUBCATEGORY_KEY = 'subcategory'

DEFAULT_COLLAPSE_THRESHOLD = 12


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    icon: str            # bootstrap icon class
    color: str           # bootstrap contextual colour
    description: str = ''
    collapse: Optional[bool] = None   # None = threshold decides; True/False pins


UNCATEGORIZED = Category(
    key='Uncategorized', label='Uncategorized', icon='bi-question-circle', color='secondary',
    description='Ontologies with no explicit category and no matching default rule.')

CATEGORIES: Tuple[Category, ...] = (
    Category('Foundation', 'Foundation', 'bi-diagram-3', 'danger',
             'Upper-level ontologies the framework builds on (BFO, IAO, RO, PROV-O) and the ProEthica foundation layer.'),
    Category('ProEthica Framework', 'ProEthica Framework', 'bi-layers', 'primary',
             'The core, intermediate, cases and provenance layers of the ProEthica ontology, its SHACL shapes, and the extracted extension.'),
    Category('Domain', 'Domain', 'bi-globe', 'success',
             'Professional-domain ontologies that specialise the framework.'),
    Category('Professional Codes', 'Professional Codes', 'bi-journal-text', 'info',
             'Codes of ethics of professional societies, imported as vocabularies.'),
    Category('External Vocabularies', 'External Vocabularies', 'bi-cloud-download', 'info',
             'Other external vocabularies and curated subsets.'),
    Category('Cases', 'Cases', 'bi-folder2-open', 'warning',
             'Per-case ontologies committed by ProEthica, one per analysed case.'),
    UNCATEGORIZED,
)

CATEGORY_BY_KEY: Dict[str, Category] = {c.key: c for c in CATEGORIES}
CATEGORY_ORDER: Dict[str, int] = {c.key: i for i, c in enumerate(CATEGORIES)}


# ---------------------------------------------------------------------------
# Default rules: first match wins. Each rule is (predicate, category, subcategory).
# ---------------------------------------------------------------------------

_CASE_NAME = re.compile(r'^proethica-case-\d+$')
_CODE_NAME = re.compile(r'code of ethics', re.IGNORECASE)


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _meta(obj: Any) -> Dict[str, Any]:
    md = _attr(obj, 'meta_data')
    if md is None:
        md = _attr(obj, 'metadata')
    return md if isinstance(md, dict) else {}


Rule = Tuple[Callable[[Any], bool], str, Optional[str]]

DEFAULT_RULES: Sequence[Rule] = (
    (lambda o: _attr(o, 'ontology_type') == 'case', 'Cases', None),
    (lambda o: _attr(o, 'ontology_type') == 'upper', 'Foundation', None),
    (lambda o: _attr(o, 'ontology_type') == 'domain', 'Domain', None),
    (lambda o: _attr(o, 'source_system') == 'proethica'
        and str(_attr(o, 'name', '')).startswith('proethica-'), 'ProEthica Framework', None),
    (lambda o: _attr(o, 'source_system') == 'external'
        and bool(_CODE_NAME.search(str(_attr(o, 'name', '')))), 'Professional Codes', None),
    (lambda o: _attr(o, 'source_system') == 'external', 'External Vocabularies', None),
)


@dataclass(frozen=True)
class Classification:
    category: str
    subcategory: Optional[str]
    explicit: bool          # True when metadata.category supplied the category


def resolve(ontology: Any, rules: Sequence[Rule] = DEFAULT_RULES) -> Classification:
    """Return the (category, subcategory) for one ontology.

    Explicit metadata wins field by field: an explicit subcategory is kept
    even when the category comes from a rule, so a case can carry its decade
    without repeating "Cases" on every row.
    """
    md = _meta(ontology)
    explicit_cat = _clean(md.get(CATEGORY_KEY))
    explicit_sub = _clean(md.get(SUBCATEGORY_KEY))

    rule_cat, rule_sub = None, None
    for predicate, cat, sub in rules:
        try:
            if predicate(ontology):
                rule_cat, rule_sub = cat, sub
                break
        except Exception:
            continue

    category = explicit_cat or rule_cat or UNCATEGORIZED.key
    subcategory = explicit_sub or (rule_sub if not explicit_cat or explicit_cat == rule_cat else None)
    return Classification(category=category, subcategory=subcategory, explicit=bool(explicit_cat))


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def category_info(key: str) -> Category:
    """Catalog entry for a category key; unknown (user-typed) keys get a neutral entry."""
    return CATEGORY_BY_KEY.get(key) or Category(key=key, label=key, icon='bi-tag', color='secondary')


def known_category_keys() -> List[str]:
    return [c.key for c in CATEGORIES if c is not UNCATEGORIZED]


# ---------------------------------------------------------------------------
# Grouping for the index page
# ---------------------------------------------------------------------------

@dataclass
class Group:
    category: Category
    ontologies: List[Any] = field(default_factory=list)
    subgroups: List[Tuple[Optional[str], int]] = field(default_factory=list)  # (subcategory, count) in display order
    collapsed: bool = False

    @property
    def count(self) -> int:
        return len(self.ontologies)

    @property
    def key(self) -> str:
        return self.category.key


def group_ontologies(ontologies: Iterable[Any],
                     collapse_threshold: int = DEFAULT_COLLAPSE_THRESHOLD,
                     rules: Sequence[Rule] = DEFAULT_RULES) -> List[Group]:
    """Partition ontologies into ordered groups.

    Order: catalog order, then any user-defined categories alphabetically,
    with Uncategorized last. Within a group, ontologies keep the order they
    arrived in (the caller sorts). Subgroups are ordered by subcategory
    label with the unlabelled remainder (None) last.
    """
    buckets: Dict[str, Group] = {}
    sub_counts: Dict[str, Dict[Optional[str], int]] = {}
    for ont in ontologies:
        cls = resolve(ont, rules)
        grp = buckets.get(cls.category)
        if grp is None:
            grp = buckets[cls.category] = Group(category=category_info(cls.category))
            sub_counts[cls.category] = {}
        grp.ontologies.append(ont)
        sub_counts[cls.category][cls.subcategory] = sub_counts[cls.category].get(cls.subcategory, 0) + 1

    def order_key(k: str):
        if k == UNCATEGORIZED.key:
            return (2, '')
        if k in CATEGORY_ORDER:
            return (0, CATEGORY_ORDER[k])
        return (1, k.lower())

    groups: List[Group] = []
    for key in sorted(buckets, key=order_key):
        grp = buckets[key]
        subs = sub_counts[key]
        labelled = sorted((s, n) for s, n in subs.items() if s is not None)
        grp.subgroups = labelled + ([(None, subs[None])] if None in subs else [])
        pin = grp.category.collapse
        grp.collapsed = pin if pin is not None else grp.count > collapse_threshold
        groups.append(grp)
    return groups


def matches(ontology: Any, category: Optional[str], subcategory: Optional[str],
            rules: Sequence[Rule] = DEFAULT_RULES) -> bool:
    """Filter predicate used by the index when a category filter is active."""
    cls = resolve(ontology, rules)
    if category and cls.category != category:
        return False
    if subcategory and (cls.subcategory or '') != subcategory:
        return False
    return True
