"""Unit tests for the obligation-competition view model (web/case_competition.py).

Pure rdflib parse of the case_086 Figure-1 fixture — no DB, no Java reasoner.
"""
from pathlib import Path

import pytest

from web.case_competition import build_competition_clusters

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "cases" / "case_086.ttl"

CASE = "http://proethica.org/ontology/case/86#"


@pytest.fixture(scope="module")
def model():
    return build_competition_clusters(FIXTURE.read_text(encoding="utf-8"))


def _by_iri(clusters, frag):
    return next(c for c in clusters if c["iri"] == CASE + frag)


def test_fixture_has_competition_edges(model):
    assert model["has_edges"] is True
    assert model["edge_counts"]["competesWith"] == 1
    assert model["edge_counts"]["prevailsOver"] == 1
    assert model["edge_counts"]["defeasibleUnder"] == 1
    # the two obligations are clustered; the State is NOT itself an obligation cluster
    assert model["obligation_count"] == 2
    iris = {c["iri"] for c in model["clusters"]}
    assert iris == {CASE + "Obl_Confidentiality", CASE + "Obl_PublicWelfare"}


def test_confidentiality_cluster_shape(model):
    conf = _by_iri(model["clusters"], "Obl_Confidentiality")
    assert any(e["iri"] == CASE + "Obl_PublicWelfare" for e in conf["competes_with"])
    assert any(e["iri"] == CASE + "Obl_PublicWelfare" for e in conf["prevailed_over_by"])
    du = conf["defeasible_under"]
    assert any(e["iri"] == CASE + "State_WetlandViolation" for e in du)
    # the defeasibility State carries its grounding quote (proeth:sourcetext)
    state = next(e for e in du if e["iri"] == CASE + "State_WetlandViolation")
    assert state["source_text"] and "fill material" in state["source_text"].lower()
    # the obligation itself carries a verbatim grounding quote
    assert conf["source_text"] and "reveal" in conf["source_text"].lower()


def test_public_welfare_prevails(model):
    pw = _by_iri(model["clusters"], "Obl_PublicWelfare")
    assert any(e["iri"] == CASE + "Obl_Confidentiality" for e in pw["prevails_over"])


def test_zero_edge_ontology_degrades():
    ttl = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix ex: <http://example.org/c#> .
ex:Thing a owl:NamedIndividual ; <http://www.w3.org/2000/01/rdf-schema#label> "x" .
"""
    m = build_competition_clusters(ttl)
    assert m["has_edges"] is False
    assert m["clusters"] == []


def test_empty_and_malformed_input_degrade():
    assert build_competition_clusters(None)["has_edges"] is False
    assert build_competition_clusters("not valid ttl {{{")["has_edges"] is False


@pytest.mark.integration
def test_competition_panel_renders_in_case_template(model):
    """ontology_case.html renders the competition panel for an edge-carrying model,
    and omits it for an edge-free model (graceful degradation)."""
    from types import SimpleNamespace
    from flask import render_template
    from web.app import create_app

    app = create_app("testing")
    ont = SimpleNamespace(name="proethica-case-86", description=None, current_version=None)

    from web.case_display import build_ordered_blocks

    with app.app_context(), app.test_request_context():
        # The body and nav both render from page_blocks (built the same way the
        # route does), so the test must supply it for the panel to appear.
        blocks = build_ordered_blocks([], competition=model)
        html = render_template(
            "ontology_case.html",
            ontology=ont, case_sections=[], page_blocks=blocks,
            stats={"total": 0}, competition=model,
        )
        assert "Obligation Competition" in html
        assert "prevails over" in html
        assert "defeasible under" in html
        assert html.count("bi-asterisk") == model["obligation_count"]

        empty = build_competition_clusters(None)
        empty_blocks = build_ordered_blocks([], competition=empty)
        html2 = render_template(
            "ontology_case.html",
            ontology=ont, case_sections=[], page_blocks=empty_blocks,
            stats={"total": 0}, competition=empty,
        )
        assert "Obligation Competition" not in html2  # graceful: no panel, no error


# ---------------------------------------------------------------------------
# Per-edge provenance (2026-07-08): the commit pipeline reifies each
# defeasibility edge as a prov:Derivation node named
# defeasibility_edge_provenance_<S>_<pred>_<O>, with the verbatim quote in
# prov:value and "source_field=...; confidence=..." in rdfs:comment. The view
# model attaches it to each rendered edge; graphs without the nodes (the
# case_086 fixture, the legacy corpus) get prov=None and the template falls
# back to entity-level quotes.
# ---------------------------------------------------------------------------

EDGE_PROV_TTL = """
@prefix case: <http://proethica.org/ontology/case/99#> .
@prefix proeth-core: <http://proethica.org/ontology/core#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

case:Obl_A a proeth-core:Obligation ; rdfs:label "Duty A" ;
    proeth-core:competesWith case:Obl_B ;
    proeth-core:prevailsOver case:Obl_B .
case:Obl_B a proeth-core:Obligation ; rdfs:label "Duty B" ;
    proeth-core:competesWith case:Obl_A ;
    proeth-core:defeasibleUnder case:State_S .
case:State_S a proeth-core:State ; rdfs:label "State S" .

case:defeasibility_edge_provenance_Obl_A_prevailsOver_Obl_B a prov:Derivation ;
    rdfs:comment "source_field=tensionresolution; confidence=0.9" ;
    prov:value "A overrode B in the circumstances." ;
    prov:wasDerivedFrom case:Obl_A, case:Obl_B .
case:defeasibility_edge_provenance_Obl_A_competesWith_Obl_B a prov:Derivation ;
    rdfs:comment "source_field=balancingwith; confidence=0.8" ;
    prov:value "A and B stood in tension." ;
    prov:wasDerivedFrom case:Obl_A, case:Obl_B .
case:defeasibility_edge_provenance_Obl_B_defeasibleUnder_State_S a prov:Derivation ;
    rdfs:comment "source_field=tensionresolution; confidence=0.7" ;
    prov:value "B yields when S obtains." ;
    prov:wasDerivedFrom case:Obl_B, case:State_S .
"""

CASE99 = "http://proethica.org/ontology/case/99#"


@pytest.fixture(scope="module")
def prov_model():
    return build_competition_clusters(EDGE_PROV_TTL)


def test_per_edge_provenance_attached(prov_model):
    a = next(c for c in prov_model["clusters"] if c["iri"] == CASE99 + "Obl_A")
    b = next(c for c in prov_model["clusters"] if c["iri"] == CASE99 + "Obl_B")

    # Directed edge: the winner's prevails_over ref carries the edge's own quote.
    po = a["prevails_over"][0]
    assert po["prov"]["quote"] == "A overrode B in the circumstances."
    assert "confidence=0.9" in po["prov"]["note"]

    # The loser's yields-to view of the SAME edge resolves the same node.
    pob = b["prevailed_over_by"][0]
    assert pob["prov"]["quote"] == "A overrode B in the circumstances."

    # competesWith: only the A->B direction is reified here; the B->A ref
    # falls back to the reverse key (symmetric pair, one grounding quote).
    cw_b = b["competes_with"][0]
    assert cw_b["prov"]["quote"] == "A and B stood in tension."

    du = b["defeasible_under"][0]
    assert du["prov"]["quote"] == "B yields when S obtains."


def test_fixture_edges_have_no_prov(model):
    """The case_086 fixture predates edge reification: every ref degrades to
    prov=None (the template then falls back to entity-level quotes)."""
    for c in model["clusters"]:
        for key in ("competes_with", "prevails_over", "prevailed_over_by", "defeasible_under"):
            for e in c[key]:
                assert e["prov"] is None
