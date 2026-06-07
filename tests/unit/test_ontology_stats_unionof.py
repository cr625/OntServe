"""Regression tests for owl:unionOf rendering in the ontology stats/axioms views.

Locks the fix for blank-node leakage in the web ontology views: an
owl:unionOf class expression is itself typed owl:Class and is an anonymous
node, so it must NOT be listed as a class, and a property/axiom that points at
one must render a readable label ("Action or Event") rather than the raw
rdflib blank-node id. See OntServe commit 5e2e8e9.
"""
from rdflib import Graph, RDFS, URIRef

from web.ontology_stats import (
    compute_stats_from_ttl,
    compute_axioms,
    humanize_domain_range,
)

NS = "http://ex.org/o#"

TTL = """@prefix : <http://ex.org/o#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

:Action a owl:Class .
:Event a owl:Class .
:State a owl:Class .

:initiates a owl:ObjectProperty ;
    rdfs:domain [ a owl:Class ; owl:unionOf ( :Action :Event ) ] ;
    rdfs:range :State .

:Weird a owl:Class ;
    owl:equivalentClass [ a owl:Class ; owl:unionOf ( :Action :Event ) ] .
"""


def test_class_list_excludes_anonymous_union_nodes():
    stats = compute_stats_from_ttl(TTL)
    labels = {c["label"] for c in stats["classes"]}
    assert labels == {"Action", "Event", "State", "Weird"}
    # no class entry should carry a bare blank-node id as uri
    assert all(c["uri"].startswith("http") for c in stats["classes"])


def test_object_property_union_domain_renders_readable():
    stats = compute_stats_from_ttl(TTL)
    initiates = next(p for p in stats["object_properties"]
                     if p["uri"] == NS + "initiates")
    assert initiates["domain"] == "Action or Event"
    # named class renders as its local name here (template applies extract_name);
    # the link-bearing cached-column path uses full_uri=True separately.
    assert initiates["range"] == "State"


def test_axioms_skip_anonymous_endpoints():
    axioms = compute_axioms(TTL)
    # Weird equivalentClass [union] -> object is anonymous -> not listed
    assert axioms["equivalent"] == []
    # property constraint resolves the union domain
    initiates = next(c for c in axioms["property_constraints"]
                     if c["property"] == "initiates")
    assert initiates["domain"] == "Action or Event"


def test_humanize_domain_range_directly():
    g = Graph()
    g.parse(data=TTL, format="turtle")
    initiates = URIRef(NS + "initiates")
    dom = g.value(initiates, RDFS.domain)   # blank node (union)
    rng = g.value(initiates, RDFS.range)    # named class
    assert humanize_domain_range(g, dom) == "Action or Event"
    assert humanize_domain_range(g, rng, full_uri=True) == NS + "State"
    assert humanize_domain_range(g, rng) == "State"
    assert humanize_domain_range(g, None) is None
