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

    with app.app_context(), app.test_request_context():
        html = render_template(
            "ontology_case.html",
            ontology=ont, case_sections=[], stats={"total": 0}, competition=model,
        )
        assert "Obligation Competition" in html
        assert "prevails over" in html
        assert "defeasible under" in html
        assert html.count("bi-asterisk") == model["obligation_count"]

        empty = build_competition_clusters(None)
        html2 = render_template(
            "ontology_case.html",
            ontology=ont, case_sections=[], stats={"total": 0}, competition=empty,
        )
        assert "Obligation Competition" not in html2  # graceful: no panel, no error
