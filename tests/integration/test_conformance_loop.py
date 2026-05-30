"""Tests for the Phase-D validate-repair loop spine (conformance_loop.py).

Self-contained (no DB, no fixture file): tiny synthetic case content merged with the REAL
core+intermediate. Proves the evaluator-optimizer loop drives an inconsistent candidate to
conformance with a deterministic Tier-0 repair (zero LLM), and leaves a clean candidate
untouched. See proethica/docs-internal/reextraction/extraction-conformance plan, Phase D.
"""
import sys
from pathlib import Path

import pytest

ONTSERVE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ONTSERVE_ROOT))
sys.path.insert(0, str(ONTSERVE_ROOT / "web"))
sys.path.insert(0, str(ONTSERVE_ROOT / "validation"))

pytest.importorskip("pyshacl")

from conformance_loop import repair_loop  # noqa: E402

CORE = "http://proethica.org/ontology/core#"
INT = "http://proethica.org/ontology/intermediate#"
CASE = "http://proethica.org/ontology/case/test#"

_HDR = f"""
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix core: <{CORE}> .
@prefix int:  <{INT}> .
@prefix case: <{CASE}> .
"""


def test_loop_repairs_cross_category_with_tier0():
    # Ind1: type chains to Principle, but obligatedparty (domain Obligation) is present.
    # Tier-0 defers to the property domain -> strips the Principle type, re-types Obligation.
    content = _HDR + """
    case:FooObligation a owl:Class ; rdfs:subClassOf core:Principle .
    case:Ind1 a owl:NamedIndividual ; a case:FooObligation ;
        int:obligatedparty "Engineer X" .
    """
    r = repair_loop(content, max_rounds=3)
    assert r.conforms is True, (r.reason, r.rounds)
    assert r.repairs_applied >= 1
    assert len(r.rounds) <= 3
    # the repaired graph must re-type Ind1 to core:Obligation and drop the Principle-chained type
    from rdflib import Graph, URIRef, RDF
    g = Graph(); g.parse(data=r.case_content, format="turtle")
    ind = URIRef(CASE + "Ind1")
    types = {str(t) for t in g.objects(ind, RDF.type)}
    assert CORE + "Obligation" in types, types
    assert CASE + "FooObligation" not in types, types


def test_clean_case_conforms_round0_no_repairs():
    content = _HDR + """
    case:BarObligation a owl:Class ; rdfs:subClassOf core:Obligation .
    case:Ind2 a owl:NamedIndividual ; a case:BarObligation ;
        int:obligatedparty "Engineer Y" .
    """
    r = repair_loop(content, max_rounds=3)
    assert r.conforms is True, (r.reason, r.rounds)
    assert r.repairs_applied == 0
    assert r.rounds[0]["n_violations"] == 0


def test_ambiguous_clash_defers_not_loops_forever():
    # Two conflicting TYPE chains (Role and State) and NO single property-domain signal:
    # Tier-0 cannot deterministically choose, so the loop must STOP (not spin), reporting
    # the residual for the LLM tier.
    content = _HDR + """
    case:Weird a owl:Class ; rdfs:subClassOf core:Role , core:State .
    case:Ind3 a owl:NamedIndividual ; a case:Weird .
    """
    r = repair_loop(content, max_rounds=3)
    assert r.conforms is False
    assert "no-fix-available" in r.reason or "no-progress" in r.reason
    assert len(r.rounds) <= 4  # terminated, did not spin


# --- Phase D3: LLM repair tier (mock model, no API) -------------------------

def test_llm_tier_repairs_pure_type_chain_clash():
    """A clash between TWO type chains with NO disjoint-domain property: Tier-0 has no
    authoritative signal (len(prop_cats) != 1) and defers; the LLM tier (here a mock that
    chooses 'Obligation') resolves it, and the symbolic gate confirms conformance."""
    from llm_repair import make_llm_repair

    content = _HDR + """
    case:FooPrinciple a owl:Class ; rdfs:subClassOf core:Principle .
    case:BarObligation a owl:Class ; rdfs:subClassOf core:Obligation .
    case:Ind2 a owl:NamedIndividual ; a case:FooPrinciple ; a case:BarObligation ;
        int:conceptCategory "Obligation" .
    """
    calls = []

    def fake_call_model(model, system, user):
        calls.append((model, user))
        return '{"category": "Obligation", "reason": "carries obligation semantics"}'

    # Tier-0 alone cannot fix it (no property-domain signal).
    r0 = repair_loop(content, max_rounds=3)
    assert r0.conforms is False, (r0.reason, r0.rounds)

    # With the LLM tier injected, it conforms.
    repair = make_llm_repair(call_model=fake_call_model)
    r1 = repair_loop(content, max_rounds=3, llm_repair=repair)
    assert r1.conforms is True, (r1.reason, r1.rounds)
    assert r1.repairs_applied >= 1
    assert calls and calls[0][0] == "claude-haiku-4-5"  # Tier 1 first


def test_llm_tier_escalates_model_when_unresolved():
    """If the model's first choice does not clear the clash, the next round escalates to
    the next model in the ladder (Haiku -> Sonnet)."""
    from llm_repair import make_llm_repair

    content = _HDR + """
    case:FooPrinciple a owl:Class ; rdfs:subClassOf core:Principle .
    case:BarObligation a owl:Class ; rdfs:subClassOf core:Obligation .
    case:Ind3 a owl:NamedIndividual ; a case:FooPrinciple ; a case:BarObligation .
    """
    models_used = []

    def fake_call_model(model, system, user):
        models_used.append(model)
        # First (Haiku) returns an INVALID category (no-op); escalate next round.
        if model == "claude-haiku-4-5":
            return '{"category": "NotACategory"}'
        return '{"category": "Principle"}'

    repair = make_llm_repair(call_model=fake_call_model)
    r = repair_loop(content, max_rounds=4, llm_repair=repair)
    assert r.conforms is True, (r.reason, r.rounds)
    assert "claude-haiku-4-5" in models_used and "claude-sonnet-4-6" in models_used, models_used
