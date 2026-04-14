"""
Integration test that concretely validates Section 5 of the KI2026 paper:

    "A query checking for entities with two incompatible component
     types will return empty because the ontology makes such a
     classification incoherent at the schema level. The Pellet
     reasoner confirms consistency for each case ontology submitted
     to inference."

The fixture fixtures/cases/malformed_disjoint.ttl deliberately types a
single individual as both proeth-core:State (specifically dependent
continuant) and proeth-core:Action (a process). These are disjoint in
proethica-core.ttl via owl:AllDisjointClasses and, transitively, via
the BFO continuant/occurrent boundary. Pellet must report this as
inconsistent.

If this test fails, one of two things is wrong:

1. The AllDisjointClasses axiom on the nine D-tuple components has been
   removed or weakened.
2. The class hierarchy in proethica-core.ttl has drifted in a way that
   lets a single individual simultaneously be a continuant and an
   occurrent.

Either regression undermines the paper's consistency-by-construction
argument and this test exists to catch it.
"""

import os
import tempfile
from pathlib import Path

import pytest
import rdflib
from rdflib import OWL


PROJECT_ROOT = Path(__file__).parent.parent.parent
ONTOLOGIES_DIR = PROJECT_ROOT / 'ontologies'
FIXTURE_DIR = PROJECT_ROOT / 'fixtures' / 'cases'


def _load_graph(fixture_name: str) -> rdflib.Graph:
    """Load the core ontology plus a test fixture, stripping owl:imports."""
    g = rdflib.Graph()
    g.parse(ONTOLOGIES_DIR / 'proethica-core.ttl', format='turtle')
    g.parse(FIXTURE_DIR / fixture_name, format='turtle')

    for s, p, o in list(g.triples((None, OWL.imports, None))):
        g.remove((s, p, o))

    return g


def _run_pellet(graph: rdflib.Graph):
    """Serialize the graph to RDF/XML and invoke Pellet via owlready2.

    Returns (world, onto) on success. Raises owlready2.OwlReadyInconsistentOntologyError
    if the ontology is inconsistent.
    """
    owlready2 = pytest.importorskip('owlready2')

    rdfxml = graph.serialize(format='xml')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.owl', delete=False) as f:
        f.write(rdfxml)
        path = f.name

    try:
        world = owlready2.World()
        onto = world.get_ontology(f'file://{path}').load()
        with onto:
            owlready2.sync_reasoner_pellet(world)
        return world, onto
    finally:
        os.unlink(path)


@pytest.mark.integration
def test_core_ontology_declares_all_disjoint_components():
    """The nine D-tuple components must be asserted pairwise disjoint.

    Static check -- does not require Pellet. Guards against the simplest
    regression: the AllDisjointClasses axiom being deleted from the core
    ontology.
    """
    g = rdflib.Graph()
    g.parse(ONTOLOGIES_DIR / 'proethica-core.ttl', format='turtle')

    disjoint_members = set()
    for adc in g.subjects(rdflib.RDF.type, OWL.AllDisjointClasses):
        members_node = g.value(adc, OWL.members)
        if members_node is None:
            continue
        for member in rdflib.collection.Collection(g, members_node):
            disjoint_members.add(str(member))

    expected = {
        'http://proethica.org/ontology/core#Role',
        'http://proethica.org/ontology/core#Principle',
        'http://proethica.org/ontology/core#Obligation',
        'http://proethica.org/ontology/core#State',
        'http://proethica.org/ontology/core#Resource',
        'http://proethica.org/ontology/core#Action',
        'http://proethica.org/ontology/core#Event',
        'http://proethica.org/ontology/core#Capability',
        'http://proethica.org/ontology/core#Constraint',
    }
    missing = expected - disjoint_members
    assert not missing, (
        "proethica-core.ttl must assert all nine D-tuple components as "
        f"pairwise disjoint; missing: {missing}"
    )


@pytest.mark.integration
@pytest.mark.requires_java
def test_malformed_state_and_action_is_pellet_inconsistent():
    """A single individual typed as both State and Action must be rejected."""
    owlready2 = pytest.importorskip('owlready2')

    g = _load_graph('malformed_disjoint.ttl')

    with pytest.raises(owlready2.OwlReadyInconsistentOntologyError):
        _run_pellet(g)
