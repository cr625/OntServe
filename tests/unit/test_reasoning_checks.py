"""Reasoning panel checks as data (case 24-1 review, lesson L5).

The panel's popover stated as fixed text that no individual violates the
nine-component disjointness, no property is used against its domain or range
and no prevailsOver pair violates asymmetry, while reason_detailed returned only
the verdict and the entailments. reasoning_checks now reports the constraints
present for a run (disjointness axioms, characteristic-bearing property pairs,
domain- and range-constrained properties used), reason_detailed carries it as
``checks`` and the adapter passes it to the panel.

No Java: the data assembly is pure rdflib, and the reason_detailed run mocks
the merged-graph builder and the Pellet call.
"""
import rdflib

import servers.reasoning_tools as rt
from editor.reasoning_service import ReasoningRequest, execute_reasoning

CORE = "http://proethica.org/ontology/core#"
CASE = "http://proethica.org/ontology/case/8#"
XSD = "http://www.w3.org/2001/XMLSchema#"

BASE = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix core: <http://proethica.org/ontology/core#> .

core:Role a owl:Class . core:Obligation a owl:Class . core:State a owl:Class .
[] a owl:AllDisjointClasses ; owl:members ( core:Role core:Obligation core:State ) .
core:Agent a owl:Class ; owl:disjointWith core:Role .
core:Role owl:disjointWith core:Agent .
core:prevailsOver a owl:ObjectProperty, owl:AsymmetricProperty, owl:IrreflexiveProperty ;
    rdfs:domain core:Obligation ; rdfs:range core:Obligation .
core:competesWith a owl:ObjectProperty, owl:SymmetricProperty .
core:hasObligation a owl:ObjectProperty ; rdfs:domain core:Role ; rdfs:range core:Obligation .
core:confidence a owl:DatatypeProperty ; rdfs:range xsd:decimal .
core:note a owl:AnnotationProperty .
"""

TARGET = """
@prefix core: <http://proethica.org/ontology/core#> .
@prefix case: <http://proethica.org/ontology/case/8#> .

case:Duty_A a core:Obligation ; core:prevailsOver case:Duty_B ; core:confidence 0.9 ; core:note "n" .
case:Duty_B a core:Obligation ; core:prevailsOver case:Duty_C .
case:Duty_C a core:Obligation .
case:Role_R a core:Role ; core:hasObligation case:Duty_A .
"""


def _graph(*parts):
    g = rdflib.Graph()
    for part in parts:
        g.parse(data=part, format="turtle")
    return g


def test_checks_report_axioms_pairs_and_constraints():
    merged, target = _graph(BASE, TARGET), _graph(TARGET)
    c = rt.reasoning_checks(merged, target)

    assert c["disjointness_axiom_count"] == 2
    assert c["disjointness_axioms"] == [
        {"kind": "AllDisjointClasses", "members": sorted([CORE + "Role", CORE + "Obligation", CORE + "State"])},
        {"kind": "disjointWith", "members": sorted([CORE + "Agent", CORE + "Role"])},  # one entry for both directions
    ]

    props = {p["property"]: p for p in c["characteristic_properties"]}
    assert set(props) == {CORE + "prevailsOver"}       # competesWith: declared, but no pair asserted
    assert props[CORE + "prevailsOver"]["characteristics"] == ["Asymmetric", "Irreflexive"]
    assert props[CORE + "prevailsOver"]["pairs_examined"] == 2
    assert props[CORE + "prevailsOver"]["pairs"] == [
        {"subject": CASE + "Duty_A", "object": CASE + "Duty_B"},
        {"subject": CASE + "Duty_B", "object": CASE + "Duty_C"},
    ]
    assert c["pairs_examined"] == 2

    dr = {p["property"]: p for p in c["domain_range_properties"]}
    assert set(dr) == {CORE + "prevailsOver", CORE + "hasObligation", CORE + "confidence"}
    assert dr[CORE + "hasObligation"] == {"property": CORE + "hasObligation", "domain": [CORE + "Role"],
                                          "range": [CORE + "Obligation"], "uses": 1}
    assert dr[CORE + "prevailsOver"]["uses"] == 2
    assert dr[CORE + "confidence"] == {"property": CORE + "confidence", "domain": [],
                                       "range": [XSD + "decimal"], "uses": 1}
    assert c["domain_range_property_count"] == 3


def test_checks_without_constraints_are_empty():
    g = _graph(TARGET)
    assert rt.reasoning_checks(g, g) == {
        "disjointness_axioms": [], "disjointness_axiom_count": 0,
        "characteristic_properties": [], "pairs_examined": 0,
        "domain_range_properties": [], "domain_range_property_count": 0,
    }


def test_reason_detailed_carries_checks_with_the_reasoner_mocked(monkeypatch):
    """The merge and the Pellet call are replaced, the data assembly runs for real."""
    import owlready2
    from validation import pellet_validate

    merged = _graph(BASE, TARGET)
    monkeypatch.setattr(pellet_validate, "_build_merged_graph", lambda content: merged)
    monkeypatch.setattr(owlready2, "sync_reasoner_pellet", lambda world, **kw: None)

    d = rt.reason_detailed("proethica-case-8", content=TARGET, scope="local")

    assert d["error"] is None and d["consistent"] is True
    assert d["checks"]["pairs_examined"] == 2
    assert d["checks"]["disjointness_axiom_count"] == 2
    assert [p["property"] for p in d["checks"]["characteristic_properties"]] == [CORE + "prevailsOver"]
    # the existing fields are still there
    for key in ("inferred_subclasses", "inferred_types", "nothing_entities",
                "inferred_subclass_count", "inferred_type_count", "truncated"):
        assert key in d


def test_reason_detailed_checks_key_present_when_the_merge_fails(monkeypatch):
    from validation import pellet_validate

    def boom(content):
        raise ValueError("bad merge")

    monkeypatch.setattr(pellet_validate, "_build_merged_graph", boom)
    d = rt.reason_detailed("proethica-case-8", content=TARGET)
    assert d["checks"] is None
    assert d["error"].startswith("merge/serialize-failed")


def test_adapter_passes_checks_to_the_panel_response(monkeypatch):
    checks = {"disjointness_axioms": [{"kind": "AllDisjointClasses", "members": [CORE + "Role"]}],
              "disjointness_axiom_count": 1, "characteristic_properties": [], "pairs_examined": 0,
              "domain_range_properties": [], "domain_range_property_count": 0}

    def fake_detail(name, content=None, explain=False, scope="merged"):
        return {"ontology_name": name, "consistent": True, "inferred_subclasses": [],
                "inferred_types": [], "nothing_entities": [], "inferred_subclass_count": 0,
                "inferred_type_count": 0, "truncated": False, "error": None, "checks": checks}

    monkeypatch.setattr(rt, "reason_detailed", fake_detail)
    r = execute_reasoning(ReasoningRequest("proethica-case-8"),
                          _content_loader=lambda n: "@prefix : <http://example.org/> .")
    assert r.success
    assert r.to_response_dict()["checks"] == checks


def test_adapter_without_checks_keeps_the_key_null(monkeypatch):
    monkeypatch.setattr(rt, "reason_detailed", lambda name, content=None, explain=False, scope="merged": {
        "ontology_name": name, "consistent": True, "inferred_subclasses": [], "inferred_types": [],
        "nothing_entities": [], "inferred_subclass_count": 0, "inferred_type_count": 0,
        "truncated": False, "error": None})
    d = execute_reasoning(ReasoningRequest("x"),
                          _content_loader=lambda n: "@prefix : <http://example.org/> .").to_response_dict()
    assert "checks" in d and d["checks"] is None


UNION_BASE = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix core: <http://proethica.org/ontology/core#> .

core:Action a owl:Class . core:Event a owl:Class . core:State a owl:Class . core:Role a owl:Class .
core:initiates a owl:ObjectProperty ;
    rdfs:domain [ a owl:Class ; owl:unionOf ( core:Action core:Event ) ] ;
    rdfs:range core:State .
core:boundBy a owl:ObjectProperty ;
    rdfs:domain [ a owl:Restriction ; owl:onProperty core:initiates ; owl:someValuesFrom core:State ] .
core:mentions a owl:ObjectProperty .
"""

UNION_TARGET = """
@prefix core: <http://proethica.org/ontology/core#> .
@prefix case: <http://proethica.org/ontology/case/8#> .

case:Act_1 a core:Action ; core:initiates case:State_1 ; core:boundBy case:Role_R ; core:mentions case:Role_R .
case:State_1 a core:State .
case:Role_R a core:Role .
"""


def test_checks_list_union_and_anonymous_domain_constraints():
    """Review fix: core:initiates, core:terminates, core:establishedBy and the
    intermediate temporal properties constrain their domain or range through an
    anonymous owl:unionOf class; the checks skipped them, so the panel under-
    reported the domain and range constraints Pellet verifies."""
    merged, target = _graph(UNION_BASE, UNION_TARGET), _graph(UNION_TARGET)
    dr = {p["property"]: p for p in rt.reasoning_checks(merged, target)["domain_range_properties"]}
    assert set(dr) == {CORE + "initiates", CORE + "boundBy"}   # mentions: unconstrained
    assert dr[CORE + "initiates"] == {"property": CORE + "initiates",
                                      "domain": [CORE + "Action", CORE + "Event"],
                                      "range": [CORE + "State"], "uses": 1}
    assert dr[CORE + "boundBy"]["domain"] == [rt._ANON_CLASS_EXPRESSION]
    assert dr[CORE + "boundBy"]["range"] == []
