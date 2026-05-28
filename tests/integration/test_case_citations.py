"""Unit tests for the NSPE citation-chain view model (web/case_citations.py).

Pure rdflib parse of inline fixtures -- no DB, no reasoner.
"""
from web.case_citations import build_citation_chain, build_conclusions

CASE_TTL = """
@prefix proeth-core: <http://proethica.org/ontology/core#> .
@prefix proeth: <http://proethica.org/ontology/intermediate#> .
@prefix cases: <http://proethica.org/ontology/cases#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix c: <http://proethica.org/ontology/case/99#> .
@prefix nspe: <http://proethica.org/ontology/nspe#> .

c:Conclusion_1 a owl:NamedIndividual, cases:EthicalConclusion ; rdfs:label "Conclusion_1" ;
    proeth:conclusionType "analytical_extension" ; proeth:conclusionNumber 101 ;
    proeth:conclusionText "Engineer must hold safety paramount." ;
    proeth-core:citesProvision nspe:II_1_f , nspe:I_1 .
c:Conclusion_2 a owl:NamedIndividual, cases:EthicalConclusion ; rdfs:label "Conclusion_2" ;
    proeth:conclusionType "analytical_extension" ; proeth:conclusionNumber 102 ;
    proeth:conclusionText "Disclosure duty applies." ;
    proeth-core:citesProvision nspe:I_1 .
"""

NSPE_TTL = """
@prefix proeth-core: <http://proethica.org/ontology/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix nspe: <http://proethica.org/ontology/nspe#> .
@prefix p: <http://proethica.org/ontology/principles#> .
@prefix o: <http://proethica.org/ontology/obligations#> .

nspe:I_1 a proeth-core:CodeProvision ; rdfs:label "Fundamental Canon I.1" ;
    dct:identifier "I.1" ; skos:definition "Hold paramount the safety of the public." ;
    proeth-core:establishes p:Public_Safety , o:Duty_of_Care .
nspe:II_1_f a proeth-core:CodeProvision ; rdfs:label "Rules of Practice II.1.f" ;
    dct:identifier "II.1.f" ; proeth-core:establishes o:Duty_to_Report .

p:Public_Safety a proeth-core:Principle ; rdfs:label "Public Safety" .
o:Duty_of_Care a proeth-core:Obligation ; rdfs:label "Duty of Care" .
o:Duty_to_Report a proeth-core:Obligation ; rdfs:label "Duty to Report" .
"""


def test_empty_when_no_citations():
    vm = build_citation_chain("@prefix x: <http://e#> . x:a x:b x:c .", NSPE_TTL)
    assert vm["has_citations"] is False
    assert vm["provisions"] == []


def test_chain_shape_and_sorting():
    vm = build_citation_chain(CASE_TTL, NSPE_TTL)
    assert vm["has_citations"] is True
    assert vm["provision_count"] == 2
    assert vm["citation_count"] == 3  # I.1 cited twice + II.1.f once
    # sorted by code: I.1 before II.1.f
    assert [p["code"] for p in vm["provisions"]] == ["I.1", "II.1.f"]


def test_established_concepts_typed_and_sorted():
    vm = build_citation_chain(CASE_TTL, NSPE_TTL)
    i1 = next(p for p in vm["provisions"] if p["code"] == "I.1")
    # sorted by (type, label): Obligation 'Duty of Care' before Principle 'Public Safety'
    assert [(c["label"], c["type"]) for c in i1["establishes"]] == [
        ("Duty of Care", "Obligation"), ("Public Safety", "Principle")]
    assert i1["text"] == "Hold paramount the safety of the public."


def test_cited_by_lists_conclusions():
    vm = build_citation_chain(CASE_TTL, NSPE_TTL)
    i1 = next(p for p in vm["provisions"] if p["code"] == "I.1")
    # human-readable derived labels, IRI localnames preserved as anchors
    assert sorted(e["label"] for e in i1["cited_by"]) == ["Analytical Extension 1", "Analytical Extension 2"]
    assert sorted(e["anchor"] for e in i1["cited_by"]) == ["Conclusion_1", "Conclusion_2"]


def test_build_conclusions_human_labels_and_anchors():
    vm = build_conclusions(CASE_TTL)
    assert vm["has_conclusions"] is True
    assert vm["count"] == 2
    by_anchor = {c["anchor"]: c for c in vm["conclusions"]}
    assert by_anchor["Conclusion_1"]["label"] == "Analytical Extension 1"
    assert by_anchor["Conclusion_1"]["type_label"] == "Analytical Extension"
    assert by_anchor["Conclusion_1"]["cited_provisions"] == ["I.1", "II.1.f"]


def test_build_conclusions_empty_without_data():
    assert build_conclusions(None)["has_conclusions"] is False
    assert build_conclusions("@prefix x: <http://x#> .")["has_conclusions"] is False


def test_missing_nspe_degrades_gracefully():
    vm = build_citation_chain(CASE_TTL, None)
    assert vm["has_citations"] is True
    assert vm["provision_count"] == 2
    # no NSPE graph -> no established concepts, code falls back from the IRI fragment
    assert all(p["establishes"] == [] for p in vm["provisions"])
    assert {p["code"] for p in vm["provisions"]} == {"I.1", "II.1.f"}
