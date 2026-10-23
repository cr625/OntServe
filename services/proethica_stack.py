"""
The ProEthica stack: the ontology levels OntServe serves for ProEthica.

``LEVELS`` lists the four levels in stack order. The navbar, the home page,
the trail of the level and case pages and the dispatcher of
``/ontology/<name>`` read this table, so no template names a level ontology.
Nothing here touches Flask or the database: ``partition`` accepts any objects
exposing ``name``, ``ontology_type``, ``source_system`` and ``meta_data``,
the same contract as ``services.ontology_categories``.

Every ontology belongs to exactly one home-page region: a level, the cases,
the case vocabulary or code, or Reference. Reference holds the ontologies
behind the levels (``Level.support``) and then everything else, grouped by
the category resolution of ``services.ontology_categories``.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services import ontology_categories as categories

# The level pages: the D-tuple grid, the subclass tree, the case-discovered
# catalog and the standards view.
VIEWS = ('framework', 'taxonomy', 'catalog', 'standards')

# The nine components of D = (R, P, O, S, Rs, A, E, Ca, Cs), in tuple order,
# as the proeth-core:dtupleComponent annotation spells them.
DTUPLE_ORDER: Tuple[str, ...] = ('R', 'P', 'O', 'S', 'Rs', 'A', 'E', 'Ca', 'Cs')


@dataclass(frozen=True)
class Level:
    key: str
    ontology: str                  # ontology row name and /ontology/<name> slug
    label: str                     # heading, card and trail text
    nav_label: str                 # navbar text
    role: str                      # one sentence, on the home card and in the page header
    view: str                      # one of VIEWS
    count_noun: Tuple[str, str]    # (singular, plural) of the headline count
    support: Tuple[str, ...] = ()  # ontologies shown behind the level


LEVELS: Tuple[Level, ...] = (
    Level('core', 'proethica-core', 'Core', 'Core',
          'The nine components of a professional ethics case, D = (R, P, O, S, Rs, A, E, Ca, Cs), '
          'grounded in BFO and IAO.',
          'framework', ('component', 'components'),
          support=('proethica-foundation', 'proethica-shapes')),
    Level('intermediate', 'proethica-intermediate', 'Intermediate', 'Intermediate',
          'Curated kinds that specialize the nine components, such as professional roles, '
          'principle families, obligations and states.',
          'taxonomy', ('class', 'classes')),
    Level('extended', 'proethica-intermediate-extended', 'Intermediate-extended', 'Extended',
          'Classes minted from analysed cases, each placed under an intermediate or core kind '
          'and traced to the case passage it came from.',
          'catalog', ('class', 'classes'),
          support=('proethica-provenance',)),
    Level('engineering-ethics', 'engineering-ethics', 'Engineering ethics', 'Engineering ethics',
          'Named technical standards cited in engineering cases, with a short vocabulary for '
          'standards compliance.',
          'standards', ('standard', 'standards')),
)

LEVEL_BY_ONTOLOGY: Dict[str, Level] = {lvl.ontology: lvl for lvl in LEVELS}
LEVEL_BY_KEY: Dict[str, Level] = {lvl.key: lvl for lvl in LEVELS}
SUPPORT_NAMES: Tuple[str, ...] = tuple(name for lvl in LEVELS for name in lvl.support)

# The case ontologies: their category, the vocabulary their analysis records
# are typed with, and the code their conclusions cite.
CASES_CATEGORY = 'Cases'
CASES_VOCABULARY = 'proethica-cases'
CASES_CODE = 'NSPE Code of Ethics'

SUPPORT_GROUP_LABEL = 'ProEthica support'


def level_for(name: Any) -> Optional[Level]:
    """The level an ontology name stands for, or None."""
    return LEVEL_BY_ONTOLOGY.get(str(name or ''))


def _name(ontology: Any) -> str:
    value = ontology.get('name') if isinstance(ontology, dict) else getattr(ontology, 'name', None)
    return str(value or '')


@dataclass
class ReferenceGroup:
    label: str
    ontologies: List[Any] = field(default_factory=list)


@dataclass
class StackPartition:
    levels: List[Tuple[Level, Optional[Any]]]   # every level in stack order, with its row if loaded
    cases: List[Any]
    vocabulary: Optional[Any]
    code: Optional[Any]
    reference: List[ReferenceGroup]

    @property
    def reference_count(self) -> int:
        return sum(len(g.ontologies) for g in self.reference)


def partition(ontologies: Any) -> StackPartition:
    """Assign every ontology to exactly one home-page region.

    Within a region, ontologies keep the order they arrived in, except the
    support group, which follows the stack order of ``SUPPORT_NAMES``.
    """
    level_rows: Dict[str, Any] = {}
    support: Dict[str, Any] = {}
    cases: List[Any] = []
    rest: List[Any] = []
    vocabulary = code = None
    for ont in ontologies:
        name = _name(ont)
        if name in LEVEL_BY_ONTOLOGY:
            level_rows[name] = ont
        elif name == CASES_VOCABULARY:
            vocabulary = ont
        elif name == CASES_CODE:
            code = ont
        elif name in SUPPORT_NAMES:
            support[name] = ont
        elif categories.resolve(ont).category == CASES_CATEGORY:
            cases.append(ont)
        else:
            rest.append(ont)

    reference: List[ReferenceGroup] = []
    if support:
        reference.append(ReferenceGroup(SUPPORT_GROUP_LABEL,
                                        [support[n] for n in SUPPORT_NAMES if n in support]))
    for grp in categories.group_ontologies(rest):
        reference.append(ReferenceGroup(grp.category.label, list(grp.ontologies)))

    return StackPartition(levels=[(lvl, level_rows.get(lvl.ontology)) for lvl in LEVELS],
                          cases=cases, vocabulary=vocabulary, code=code, reference=reference)
