"""Case page sections (case 24-1 review, lessons L3 and L6).

L3: the three Agent individuals of a case (core:Agent, cases:DeliberativeBody),
the actors the whole graph hangs on, have their own Agents section ahead of the
nine component sections instead of landing in the collapsed Other catch-all.
The lean per-case class redeclarations (rdf:type owl:Class + rdfs:subClassOf a
core category, no definition) are listed as a "types used" chip row linking to
the class pages instead of as cards at the tail of each component section.

L6: class names on the page render from rdfs:label when the route's label
index knows one, falling back to the split IRI fragment only otherwise.

Section assignment is tested on plain row objects. The chip row is rendered
through the real macro in a bare Jinja environment (the app factory needs a
database), with the app's globals stubbed.
"""
from pathlib import Path
from types import SimpleNamespace

import jinja2

from web.case_display import (
    PAGE_BLOCK_ORDER,
    agent_kind,
    build_ordered_blocks,
    build_type_label_index,
    is_bare_class_declaration,
    organize_entities_for_case,
    type_display_label,
    type_uris_used,
)

CORE = "http://proethica.org/ontology/core#"
CASES = "http://proethica.org/ontology/cases#"
PROETH = "http://proethica.org/ontology/intermediate#"
CASE = "http://proethica.org/ontology/case/8#"


def _ind(frag, parent, types=None, label=None):
    return SimpleNamespace(entity_type="individual", uri=CASE + frag, label=label or frag,
                           comment=None, parent_uri=parent,
                           properties={"rdf_types": types} if types else None)


def _cls(frag, parent, comment=None, props=None):
    return SimpleNamespace(entity_type="class", uri=PROETH + frag, label=frag,
                           comment=comment, parent_uri=parent, properties=props)


ENTITIES = [
    _ind("Engineer_L_Agent", CORE + "Agent", label="Engineer L"),
    _ind("NSPE_Board", CASES + "DeliberativeBody",
         types=[CASES + "DeliberativeBody", CORE + "Agent"], label="NSPE Board of Ethical Review"),
    _ind("Safety_Withdrawal_Duty", PROETH + "SafetyWithdrawalandNotificationObligation",
         types=[CORE + "Obligation", PROETH + "SafetyWithdrawalandNotificationObligation"],
         label="Safety withdrawal duty"),
    _ind("Public_Risk_State", PROETH + "PublicSafetyRiskState",
         types=[CORE + "State", PROETH + "PublicSafetyRiskState"], label="Public risk"),
    _cls("PublicSafetyRiskState", CORE + "State"),       # bare redeclaration
    _cls("SafetyObligation", CORE + "Obligation"),        # bare redeclaration of a base class
    _cls("DefinedState", CORE + "State", comment="A state the case file defines."),
]


def test_agents_section_precedes_the_nine_concepts():
    result = organize_entities_for_case(ENTITIES, "engineering")
    ids = [s["id"] for s in result["sections"]]
    assert ids[:2] == ["agents", "nine_concepts"]
    agents = result["sections"][0]
    assert sorted(e.label for e in agents["entities"]) == ["Engineer L", "NSPE Board of Ethical Review"]
    assert agents["types_used"] == []
    # the actors no longer fall into the catch-all
    assert "other" not in ids
    assert result["stats"]["by_section"]["agents"] == 2
    assert result["stats"]["individuals"] == 4


def test_case_documents_have_their_own_section():
    """A proeth:CaseDocument (2026-10-23) is a document of the case events, not a Resource: it
    has its own section after the nine components instead of the Other catch-all."""
    doc = _ind("Groundwater_Monitoring_Data", PROETH + "CaseDocument",
               types=[PROETH + "CaseDocument"], label="Groundwater Monitoring Data")
    result = organize_entities_for_case(ENTITIES + [doc], "engineering")
    ids = [s["id"] for s in result["sections"]]
    assert ids.index("nine_concepts") < ids.index("case_documents")
    section = next(s for s in result["sections"] if s["id"] == "case_documents")
    assert [e.label for e in section["entities"]] == ["Groundwater Monitoring Data"]
    assert "other" not in ids
    nine = next(s for s in result["sections"] if s["id"] == "nine_concepts")
    resources = next(s for s in nine["subsections"] if s["id"] == "resources")
    assert resources["entities"] == []
    # the page lists the section right after the nine components
    block_ids = [b["id"] for b in build_ordered_blocks(result["sections"])]
    assert block_ids.index("case_documents") == block_ids.index("nine_concepts") + 1


def test_bare_class_redeclarations_become_types_used_not_cards():
    result = organize_entities_for_case(ENTITIES, "engineering")
    nine = next(s for s in result["sections"] if s["id"] == "nine_concepts")
    subs = {s["id"]: s for s in nine["subsections"]}
    # individuals first, the defined class still a card at the tail
    assert [e.label for e in subs["states"]["entities"]] == ["Public risk", "DefinedState"]
    assert [t.label for t in subs["states"]["types_used"]] == ["PublicSafetyRiskState"]
    assert [e.label for e in subs["obligations"]["entities"]] == ["Safety withdrawal duty"]
    assert [t.label for t in subs["obligations"]["types_used"]] == ["SafetyObligation"]
    # chips are not counted as section content
    assert result["stats"]["by_section"]["nine_concepts"] == 3
    assert result["stats"]["types_used"] == 2


def test_unmatched_bare_class_goes_to_other_types_used():
    stray = _cls("Mystery", "http://example.org/Unrelated")
    result = organize_entities_for_case([ENTITIES[0], stray], "engineering")
    by_id = {s["id"]: s for s in result["sections"]}
    # a section with chips only is not rendered (no entities), the chip is still filed
    assert "other" not in by_id
    assert result["stats"]["types_used"] == 1


def test_page_block_order_starts_with_agents():
    assert PAGE_BLOCK_ORDER[0] == "agents"
    sections = [
        {"id": "nine_concepts", "title": "9-Concept Formalism", "icon": None,
         "entities": [object()], "subsections": None},
        {"id": "agents", "title": "Agents", "icon": "bi-people",
         "entities": [object(), object()], "subsections": None},
    ]
    blocks = build_ordered_blocks(sections)
    assert [b["id"] for b in blocks] == ["agents", "nine_concepts"]
    assert blocks[0]["count"] == 2


def test_agent_kind_and_bare_declaration_predicates():
    assert agent_kind(ENTITIES[0]) == "Agent"
    assert agent_kind(ENTITIES[1]) == "DeliberativeBody"
    assert agent_kind(ENTITIES[2]) is None
    assert is_bare_class_declaration(_cls("X", CORE + "State"))
    assert is_bare_class_declaration(_cls("X", CORE + "State",
                                          props={"rdf_superclasses": [CORE + "State", PROETH + "Y"]}))
    assert not is_bare_class_declaration(_cls("X", CORE + "State", comment="defined"))
    assert not is_bare_class_declaration(_cls("X", CORE + "State", props={"discoveredInCase": 8}))
    assert not is_bare_class_declaration(ENTITIES[0])


# --- L6: declared label over split fragment -----------------------------------

DUTY = PROETH + "DutytoReportObligation"


def test_type_display_label_prefers_the_declared_label():
    # the splitter cannot place the word break the label has
    assert type_display_label(DUTY) == "Dutyto Report Obligation"
    assert type_display_label(DUTY, {DUTY: "Duty to Report Obligation"}) == "Duty to Report Obligation"
    assert type_display_label(DUTY, {DUTY: {"label": "Duty to Report Obligation",
                                            "ontology": "proethica-intermediate-extended"}}) \
        == "Duty to Report Obligation"
    # an index without the class falls back to the split fragment
    assert type_display_label(DUTY, {PROETH + "Other": "Other"}) == "Dutyto Report Obligation"
    assert type_display_label(None) == ""
    assert type_display_label(CASE + "Engineer_L_Agent") == "Engineer L Agent"


def test_build_type_label_index_prefers_definitional_rows():
    rows = [
        (DUTY, "Dutyto Report Obligation", "proethica-case-8"),
        (DUTY, "Duty to Report Obligation", "proethica-intermediate-extended"),
        (PROETH + "Unlabelled", None, "proethica-core"),
        (PROETH + "CaseOnly", "Case Only", "proethica-case-8"),
    ]
    index = build_type_label_index(rows)
    assert index[DUTY] == {"label": "Duty to Report Obligation", "ontology": "proethica-intermediate-extended"}
    assert PROETH + "Unlabelled" not in index
    assert index[PROETH + "CaseOnly"] == {"label": "Case Only", "ontology": "proethica-case-8"}
    # row order does not change the answer
    assert build_type_label_index(list(reversed(rows)))[DUTY]["ontology"] == "proethica-intermediate-extended"


def test_type_uris_used_collects_parents_types_and_class_rows():
    uris = type_uris_used(ENTITIES)
    assert {CORE + "Agent", CASES + "DeliberativeBody", CORE + "Obligation",
            PROETH + "SafetyWithdrawalandNotificationObligation",
            PROETH + "SafetyObligation", PROETH + "DefinedState"} <= uris


# --- the macro renders the chip row from the declared label -------------------

def _macro_environment():
    """The case_display macros with the app's filters and globals stubbed."""
    from web.property_labels import humanize_key, qualify_predicate, split_pascal_case
    from web.case_display import concept_type_meta, materialized_category
    templates = Path(__file__).resolve().parents[2] / "web" / "templates"
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(templates)), autoescape=True)
    env.filters["split_pascal"] = split_pascal_case
    env.filters["pretty_key"] = humanize_key
    env.filters["qualify_pred"] = qualify_predicate
    env.filters["extract_name"] = lambda uri: str(uri).split("#")[-1].split("/")[-1]
    env.globals["url_for"] = lambda endpoint, **kw: f"/entity/{kw['ontology_name']}/{kw['fragment']}"
    env.globals["type_label"] = type_display_label
    env.globals["concept_meta"] = concept_type_meta
    env.globals["materialized_category"] = materialized_category
    return env


def test_render_section_lists_types_used_as_labelled_chips():
    duty = _ind("Report_Duty", DUTY, types=[CORE + "Obligation", DUTY], label="Report duty")
    bare = _cls("DutytoReportObligation", CORE + "Obligation")
    result = organize_entities_for_case([duty, bare], "engineering")
    nine = next(s for s in result["sections"] if s["id"] == "nine_concepts")
    type_labels = {DUTY: {"label": "Duty to Report Obligation", "ontology": "proethica-intermediate-extended"}}

    env = _macro_environment()
    html = env.from_string(
        '{% from "macros/case_display.html" import render_section %}'
        "{{ render_section(section, ontology_name='proethica-case-8', type_labels=type_labels) }}"
    ).render(section=nine, type_labels=type_labels)

    assert "Types used" in html
    assert html.count("Duty to Report Obligation") == 2   # the chip and the card's "instance of"
    assert "Dutyto Report Obligation" not in html          # the split fragment is never shown as text
    # the chip links to the definitional copy, the card to the case copy
    assert '/entity/proethica-intermediate-extended/DutytoReportObligation' in html
    assert '/entity/proethica-case-8/DutytoReportObligation' in html
    # the bare redeclaration is not a card
    assert html.count('class="entity-card') == 1
    assert ">class<" not in html


def test_render_section_without_label_index_falls_back_to_the_split_fragment():
    duty = _ind("Report_Duty", DUTY, types=[CORE + "Obligation", DUTY], label="Report duty")
    bare = _cls("DutytoReportObligation", CORE + "Obligation")
    result = organize_entities_for_case([duty, bare], "engineering")
    nine = next(s for s in result["sections"] if s["id"] == "nine_concepts")
    html = _macro_environment().from_string(
        '{% from "macros/case_display.html" import render_section %}'
        "{{ render_section(section, ontology_name='proethica-case-8') }}"
    ).render(section=nine)
    assert "Dutyto Report Obligation" in html
    assert '/entity/proethica-case-8/DutytoReportObligation' in html
