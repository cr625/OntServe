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

The catalog (``CATEGORIES``) carries the display order, label and description
of each category. The home page places the ProEthica levels and the cases
itself (``services.proethica_stack``) and groups the remaining ontologies by
category; the flat list of ``/?category=`` filters by it.

Adding a category: append a ``Category`` to ``CATEGORIES`` and, if it should be
inferred, a rule to ``DEFAULT_RULES``. Ontologies that match no rule fall into
``UNCATEGORIZED``.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

CATEGORY_KEY = 'category'
SUBCATEGORY_KEY = 'subcategory'
EXPLICIT_KEYS = (CATEGORY_KEY, SUBCATEGORY_KEY)   # the settable classification keys
# Other metadata keys the sync fills from ProEthica case headers (see ontology_sync_service)
CASE_NUMBER_KEY = 'case_number'
DISPLAY_NAME_KEY = 'display_name'

@dataclass(frozen=True)
class Category:
    key: str
    label: str           # heading and filter-banner text
    description: str = ''
    listing: str = 'table'   # the flat list of /?category=: 'table', or 'cases' (the case index)


UNCATEGORIZED = Category(
    key='Uncategorized', label='Uncategorized',
    description='Ontologies with no explicit category and no matching default rule.')

CATEGORIES: Tuple[Category, ...] = (
    Category('Foundation', 'Foundation',
             'Upper-level ontologies the framework builds on (BFO, IAO, RO, PROV-O) and the ProEthica foundation layer.'),
    Category('ProEthica Framework', 'ProEthica Framework',
             'The layers that define the ProEthica vocabulary: core (the nine components), intermediate, '
             'proethica-cases (the case-analysis vocabulary the case ontologies are written in), '
             'provenance, the SHACL shapes, and the extracted extension.'),
    Category('Cases', 'ProEthica Cases',
             'One ontology per NSPE case analysed in ProEthica: the individuals (roles, principles, '
             'obligations, states, actions, events, ...) extracted from that case, typed with the '
             'framework vocabulary -- each case ontology imports proethica-cases and '
             'proethica-intermediate. Grouped by the decade of the Board of Ethical Review decision.',
             listing='cases'),
    Category('Domain', 'Domain',
             'Professional-domain ontologies that specialise the framework.'),
    Category('Professional Codes', 'Professional Codes',
             'Codes of ethics of professional societies, imported as vocabularies.'),
    Category('External Vocabularies', 'External Vocabularies',
             'Other external vocabularies and curated subsets.'),
    UNCATEGORIZED,
)

CATEGORY_BY_KEY: Dict[str, Category] = {c.key: c for c in CATEGORIES}
CATEGORY_ORDER: Dict[str, int] = {c.key: i for i, c in enumerate(CATEGORIES)}


# ---------------------------------------------------------------------------
# Default rules: first match wins. Each rule is (predicate, category, subcategory).
# ---------------------------------------------------------------------------

# One home for the proethica-case-<id> naming convention shared by the sync
# service (auto-create typing), the case page (ProEthica back-link) and links.
CASE_NAME_RE = re.compile(r'^proethica-case-(\d+)$')
_CODE_NAME = re.compile(r'code of ethics', re.IGNORECASE)


def case_id_from_name(name: Any) -> Optional[str]:
    """'proethica-case-102' -> '102'; None for anything else."""
    m = CASE_NAME_RE.match(str(name or ''))
    return m.group(1) if m else None


_NSPE_CASE_NUMBER = re.compile(r'^\s*(\d{2})-(\d+)\s*$')


def nspe_case_order(case_number: Any) -> Optional[Tuple[int, int]]:
    """(year, sequence) of an NSPE Board of Ethical Review case number YY-N,
    with the two-digit-year pivot of ProEthica (app/utils/nspe_case_number.py):
    YY >= 50 is 19YY, otherwise 20YY. '58-1' -> (1958, 1), '24-2' -> (2024, 2);
    None when the value is not of that form."""
    m = _NSPE_CASE_NUMBER.match(str(case_number or ''))
    if not m:
        return None
    yy = int(m.group(1))
    return (1900 + yy if yy >= 50 else 2000 + yy, int(m.group(2)))


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
    rule_category: Optional[str] = None   # what the rules alone would give (the settings-page default)


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
    return Classification(category=category, subcategory=subcategory, explicit=bool(explicit_cat),
                          rule_category=rule_cat or UNCATEGORIZED.key)


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def set_explicit(md: Dict[str, Any], key: str, value: Any) -> None:
    """Store an explicit metadata value in place; blank/None clears the key so
    the rule default applies again. Shared by the metadata API and the CLI tool
    so both have identical blank semantics."""
    value = _clean(value)
    if value:
        md[key] = value
    else:
        md.pop(key, None)


def category_info(key: str) -> Category:
    """Catalog entry for a category key; unknown (user-typed) keys get a plain entry."""
    return CATEGORY_BY_KEY.get(key) or Category(key=key, label=key)


def known_category_keys() -> List[str]:
    return [c.key for c in CATEGORIES if c is not UNCATEGORIZED]


# ---------------------------------------------------------------------------
# Grouping for the home page
# ---------------------------------------------------------------------------

@dataclass
class Group:
    category: Category
    ontologies: List[Any] = field(default_factory=list)
    subgroups: List[Tuple[Optional[str], int]] = field(default_factory=list)  # (subcategory, count) in display order

    @property
    def count(self) -> int:
        return len(self.ontologies)

    @property
    def key(self) -> str:
        return self.category.key


def group_ontologies(ontologies: Iterable[Any],
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
        groups.append(grp)
    return groups


def matches(ontology: Any, category: Optional[str], subcategory: Optional[str],
            rules: Sequence[Rule] = DEFAULT_RULES) -> bool:
    """Filter predicate used by the flat list when a category filter is active."""
    cls = resolve(ontology, rules)
    if category and cls.category != category:
        return False
    if subcategory and (cls.subcategory or '') != subcategory:
        return False
    return True
