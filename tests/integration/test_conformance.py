"""Tests for the SHACL+OWL-RL conformance gate (Phase C).

Exercises the full mechanism end-to-end on tiny synthetic case content (merged with the
REAL core+intermediate from disk, then OWL-RL-expanded), so it is self-contained (no DB)
but still proves that the OWL-RL closure + the disjoint-core-category shape catch the
F2-class clash via BOTH a type chain AND a property-domain inference.

Needs pyshacl + owlrl (no Java/Pellet). See
proethica/docs-internal/reextraction/matcher-category-authority-design.md.
"""
import sys
from pathlib import Path

import pytest

ONTSERVE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ONTSERVE_ROOT))
sys.path.insert(0, str(ONTSERVE_ROOT / "web"))
sys.path.insert(0, str(ONTSERVE_ROOT / "validation"))

pytest.importorskip("pyshacl")

from conformance import validate_conformance_content  # noqa: E402

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


def test_flags_cross_category_via_chain_and_property_domain():
    # Ind1 is typed to a class that chains to Principle, AND carries obligatedparty
    # (rdfs:domain core:Obligation in the real intermediate). OWL-RL infers both
    # Principle and Obligation -> the disjoint-core-category shape must flag it.
    content = _HDR + """
    case:FooObligation a owl:Class ; rdfs:subClassOf core:Principle .
    case:Ind1 a owl:NamedIndividual ; a case:FooObligation ;
        int:obligatedparty "Engineer X" .
    """
    r = validate_conformance_content("synthetic-cross-category", content)
    assert r.error is None, r.error
    assert r.conforms is False
    assert any(v.source_shape == "DisjointCoreCategoryShape"
               and "Ind1" in v.focus_node for v in r.violations), \
        [(v.source_shape, v.focus_node) for v in r.violations]


def test_clean_single_category_conforms():
    # Ind2 is an Obligation by chain AND by obligatedparty domain -> agreement, no clash.
    content = _HDR + """
    case:BarObligation a owl:Class ; rdfs:subClassOf core:Obligation .
    case:Ind2 a owl:NamedIndividual ; a case:BarObligation ;
        int:obligatedparty "Engineer Y" .
    """
    r = validate_conformance_content("synthetic-clean", content)
    assert r.error is None, r.error
    assert r.conforms is True, [(v.source_shape, v.focus_node, v.message) for v in r.violations]
