"""Competition panel hover text (case 24-1 review, lesson L4).

The panel presented the prov:value of every defeasibility derivation node as a
verbatim grounding quote. For case 8 those values are passages of narrative
fields written by the extraction model on other individuals (the
tensionResolution of a principle, the caseContext of a duty), as the node's
"source_field=..." note records. The view model now labels such a passage
"derived from <field> of <individual>" and keeps the quote, and leaves a quote
from textReferences or sourceText (the two fields that quote the case text) as
it was.
"""
from web.case_competition import build_competition_clusters

CASE = "http://proethica.org/ontology/case/8#"

TTL = """
@prefix case: <http://proethica.org/ontology/case/8#> .
@prefix core: <http://proethica.org/ontology/core#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

case:Duty_A a core:Obligation ; rdfs:label "Duty A" ;
    core:prevailsOver case:Duty_B ;
    core:competesWith case:Duty_B .
case:Duty_B a core:Obligation ; rdfs:label "Duty B" ;
    core:competesWith case:Duty_A ;
    core:defeasibleUnder case:State_S .
case:State_S a core:State ; rdfs:label "State S" .
case:Principle_P a core:Principle ; rdfs:label "Public Safety Principle" .

case:defeasibility_edge_provenance_Duty_A_prevailsOver_Duty_B a prov:Derivation ;
    rdfs:comment "source_field=tensionresolution; confidence=0.9" ;
    prov:value "Safety was held to override the client duty." ;
    prov:wasDerivedFrom case:Duty_A, case:Duty_B, case:Principle_P .
case:defeasibility_edge_provenance_Duty_A_competesWith_Duty_B a prov:Derivation ;
    rdfs:comment "source_field=sourcetext; confidence=0.8" ;
    prov:value "Engineer L faced two duties." ;
    prov:wasDerivedFrom case:Duty_A, case:Duty_B .
case:defeasibility_edge_provenance_Duty_B_defeasibleUnder_State_S a prov:Derivation ;
    rdfs:comment "source_field=casecontext; confidence=0.7" ;
    prov:value "B yields when S obtains." ;
    prov:wasDerivedFrom case:Duty_B, case:State_S .
"""


def _clusters(ttl=TTL):
    model = build_competition_clusters(ttl)
    return {c["label"]: c for c in model["clusters"]}


def test_derived_passage_is_labelled_with_field_and_source_individual():
    prov = _clusters()["Duty A"]["prevails_over"][0]["prov"]
    assert prov["verbatim"] is False
    assert prov["source_field"] == "tensionresolution"
    assert prov["derived_from"] == {"iri": CASE + "Principle_P", "label": "Public Safety Principle",
                                    "field": "tensionresolution"}
    assert prov["hover"] == ("derived from tension resolution of Public Safety Principle: "
                             "Safety was held to override the client duty. "
                             "[source_field=tensionresolution; confidence=0.9]")
    # the quote itself is kept
    assert prov["quote"] == "Safety was held to override the client duty."
    # the loser's view of the same edge carries the same record
    assert _clusters()["Duty B"]["prevailed_over_by"][0]["prov"]["hover"] == prov["hover"]


def test_verbatim_field_keeps_the_plain_hover():
    prov = _clusters()["Duty B"]["competes_with"][0]["prov"]   # B->A falls back to the A->B node
    assert prov["verbatim"] is True
    assert prov["derived_from"] is None
    assert prov["hover"] == "Engineer L faced two duties. [source_field=sourcetext; confidence=0.8]"


def test_source_individual_falls_back_to_the_edge_subject():
    prov = _clusters()["Duty B"]["defeasible_under"][0]["prov"]
    assert prov["derived_from"]["label"] == "Duty B"
    assert prov["hover"].startswith("derived from case context of Duty B: B yields when S obtains.")


def test_note_without_a_source_field_is_treated_as_verbatim():
    ttl = TTL.replace('rdfs:comment "source_field=tensionresolution; confidence=0.9"',
                      'rdfs:comment "confidence=0.9"')
    prov = _clusters(ttl)["Duty A"]["prevails_over"][0]["prov"]
    assert prov["verbatim"] is True and prov["source_field"] is None
    assert prov["hover"] == "Safety was held to override the client duty. [confidence=0.9]"


def test_edge_without_a_derivation_node_has_no_provenance():
    ttl = TTL.split("case:defeasibility_edge_provenance_Duty_A_prevailsOver_Duty_B")[0]
    assert _clusters(ttl)["Duty A"]["prevails_over"][0]["prov"] is None
