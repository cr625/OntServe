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
    # Ind1 is typed to a class that chains to Principle, AND carries
    # derivedFromPrinciple (an OBJECT property, rdfs:domain core:Obligation in the
    # real intermediate). OWL-RL infers both Principle and Obligation -> the
    # disjoint-core-category shape must flag it.
    # (The fixture formerly used the DATATYPE property obligatedparty; its domain
    # was removed by ee0fab8 under the leak-safe datatype-property convention, so
    # the property-domain channel now exists only for curated object properties.)
    content = _HDR + """
    case:FooObligation a owl:Class ; rdfs:subClassOf core:Principle .
    case:Ind1 a owl:NamedIndividual ; a case:FooObligation ;
        int:derivedFromPrinciple case:P1 .
    """
    r = validate_conformance_content("synthetic-cross-category", content)
    assert r.error is None, r.error
    assert r.conforms is False
    assert any(v.source_shape == "DisjointCoreCategoryShape"
               and "Ind1" in v.focus_node for v in r.violations), \
        [(v.source_shape, v.focus_node) for v in r.violations]


def test_clean_single_category_conforms():
    # Ind2 is an Obligation by chain; obligatedparty (datatype, domain-free since
    # ee0fab8) is carried verbatim and implies nothing -> agreement, no clash.
    content = _HDR + """
    case:BarObligation a owl:Class ; rdfs:subClassOf core:Obligation .
    case:Ind2 a owl:NamedIndividual ; a case:BarObligation ;
        int:obligatedparty "Engineer Y" .
    """
    r = validate_conformance_content("synthetic-clean", content)
    assert r.error is None, r.error
    assert r.conforms is True, [(v.source_shape, v.focus_node, v.message) for v in r.violations]


def test_datatype_property_does_not_retype_leak_safety():
    # Regression guard for ee0fab8 (2026-06-06): a datatype property landing on an
    # individual of ANY category must not re-type it. Before ee0fab8,
    # obligatedparty carried rdfs:domain core:Obligation, so this exact fixture
    # went OWL-inconsistent from one string property on a mis-resolved subject.
    # Under the domain-free datatype-property convention it must CONFORM.
    content = _HDR + """
    case:FooPrinciple a owl:Class ; rdfs:subClassOf core:Principle .
    case:Ind3 a owl:NamedIndividual ; a case:FooPrinciple ;
        int:obligatedparty "Engineer X" .
    """
    r = validate_conformance_content("synthetic-leak-safety", content)
    assert r.error is None, r.error
    assert r.conforms is True, [(v.source_shape, v.focus_node, v.message) for v in r.violations]


def test_no_datatype_property_carries_core_category_domain():
    # Locks the ee0fab8 invariant at the ontology layer: no owl:DatatypeProperty in
    # core or intermediate may declare rdfs:domain on one of the nine disjoint core
    # categories. A reintroduced domain would silently restore the leak (one
    # mis-resolved subject flips a whole case OWL-inconsistent).
    from rdflib import Graph, RDF, RDFS, OWL, URIRef
    g = Graph()
    g.parse(ONTSERVE_ROOT / "ontologies" / "proethica-core.ttl", format="turtle")
    g.parse(ONTSERVE_ROOT / "ontologies" / "proethica-intermediate.ttl", format="turtle")
    nine = {URIRef(CORE + c) for c in (
        "Role", "Principle", "Obligation", "State", "Resource",
        "Action", "Event", "Capability", "Constraint")}
    offenders = [
        str(p)
        for p in g.subjects(RDF.type, OWL.DatatypeProperty)
        for d in g.objects(p, RDFS.domain)
        if d in nine
    ]
    assert offenders == [], offenders


# --- engineering-shapes.ttl: RoleArchetypeShape -----------------------------

def test_role_archetype_shape_flags_unmapped_tail():
    """A role typed straight to core:Role (no occupational archetype) is flagged
    as a WARNING by the engineering RoleArchetypeShape; it does not fail the gate."""
    content = _HDR + """
    case:FreshRole a owl:Class ; rdfs:subClassOf core:Role .
    case:UnmappedTailRole a owl:NamedIndividual, case:FreshRole ;
        int:conceptCategory "Role" .
    """
    r = validate_conformance_content("synthetic-role-tail", content, domain="engineering")
    assert r.error is None, r.error
    warns = [v for v in r.violations if v.source_shape == "RoleArchetypeShape"]
    assert any("UnmappedTailRole" in v.focus_node for v in warns), \
        [(v.source_shape, v.severity, v.focus_node) for v in r.violations]
    assert all(v.severity == "Warning" for v in warns), warns
    # A Warning must not flip conformance to False.
    assert r.conforms is True, [(v.source_shape, v.severity, v.focus_node) for v in r.violations]


def test_role_archetype_shape_passes_archetyped_role():
    """A role facet typed through an occupational archetype (EngineerRole) and an
    Agent (core:Agent, not core:Role) are both left unflagged."""
    content = _HDR + """
    case:EngineerADesignEngineer a owl:NamedIndividual, int:EngineerRole ;
        int:conceptCategory "Role" .
    case:Agent_EngineerA a owl:NamedIndividual, core:Agent ;
        core:hasRole case:EngineerADesignEngineer .
    """
    r = validate_conformance_content("synthetic-role-archetyped", content, domain="engineering")
    assert r.error is None, r.error
    bad = [v for v in r.violations
           if v.source_shape == "RoleArchetypeShape"
           and ("EngineerADesignEngineer" in v.focus_node or "Agent_EngineerA" in v.focus_node)]
    assert not bad, [(v.severity, v.focus_node) for v in bad]
