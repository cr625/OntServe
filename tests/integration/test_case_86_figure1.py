"""
Integration test for the KI2026 Figure 1 worked example (NSPE BER Case 04-8).

Replaces the earlier Case 76-4 (internal "case 72") figure test. The camera-ready
figure was switched to BER 04-8 (2004) so the worked example uses the current
NSPE Code numbering rather than the retired pre-1979 sections.

Loads the abbreviated case_086 fixture together with the core and intermediate
ontologies, runs Pellet via owlready2 (imports stripped), and verifies:

1. The combined graph is consistent.
2. The three defeasibility edges from Figure 1 are present and queryable via
   SPARQL exactly as drawn in the paper.
3. The three typed individuals chain to the core categories the paper names.
"""

import os
import tempfile
from pathlib import Path

import pytest
import rdflib
from rdflib import Namespace, OWL, RDF, RDFS


PROJECT_ROOT = Path(__file__).parent.parent.parent
ONTOLOGIES_DIR = PROJECT_ROOT / 'ontologies'
FIXTURE_DIR = PROJECT_ROOT / 'fixtures' / 'cases'

PROETH_CORE = Namespace('http://proethica.org/ontology/core#')
PROETH = Namespace('http://proethica.org/ontology/intermediate#')
CASE86 = Namespace('http://proethica.org/ontology/case/86#')


def _load_combined_graph() -> rdflib.Graph:
    """Load core + intermediate + the case_086 fixture into one graph.

    owl:imports is stripped so the graph loads without network access to
    BFO/IAO/OWL-Time; the Figure 1 pattern depends only on the proethica core
    object properties and the fixture's own subclass-to-core declarations.
    """
    g = rdflib.Graph()
    g.parse(ONTOLOGIES_DIR / 'proethica-core.ttl', format='turtle')
    g.parse(ONTOLOGIES_DIR / 'proethica-intermediate.ttl', format='turtle')
    g.parse(FIXTURE_DIR / 'case_086.ttl', format='turtle')

    for s, p, o in list(g.triples((None, OWL.imports, None))):
        g.remove((s, p, o))

    return g


def _chains_to_core(g: rdflib.Graph, individual, core_class) -> bool:
    """True if the individual has an rdf:type whose subClassOf* reaches core_class."""
    for t in g.objects(individual, RDF.type):
        if t == OWL.NamedIndividual:
            continue
        if core_class in g.transitive_objects(t, RDFS.subClassOf):
            return True
    return False


@pytest.mark.integration
def test_fixture_parses_and_has_three_typed_individuals():
    g = _load_combined_graph()

    named = set(g.subjects(RDF.type, OWL.NamedIndividual))
    case86_individuals = {i for i in named if str(i).startswith(str(CASE86))}

    assert case86_individuals == {
        CASE86.State_WetlandViolation,
        CASE86.Obl_Confidentiality,
        CASE86.Obl_PublicWelfare,
    }, f"Figure 1 fixture should declare exactly three named individuals, got: {case86_individuals}"


@pytest.mark.integration
def test_figure_1_individuals_chain_to_core_categories():
    """Each individual must resolve to the core category the paper names."""
    g = _load_combined_graph()

    assert _chains_to_core(g, CASE86.State_WetlandViolation, PROETH_CORE.State)
    assert _chains_to_core(g, CASE86.Obl_Confidentiality, PROETH_CORE.Obligation)
    assert _chains_to_core(g, CASE86.Obl_PublicWelfare, PROETH_CORE.Obligation)


@pytest.mark.integration
def test_figure_1_defeasibility_edges_are_queryable():
    """The three defeasibility triples from Figure 1 must be SPARQL-queryable."""
    g = _load_combined_graph()

    competes = list(g.query(
        """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT ?a ?b WHERE { ?a core:competesWith ?b }
        """
    ))
    assert (CASE86.Obl_Confidentiality, CASE86.Obl_PublicWelfare) in competes

    prevails = list(g.query(
        """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT ?winner ?loser WHERE { ?winner core:prevailsOver ?loser }
        """
    ))
    assert (CASE86.Obl_PublicWelfare, CASE86.Obl_Confidentiality) in prevails

    defeasible = list(g.query(
        """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT ?obl ?state WHERE { ?obl core:defeasibleUnder ?state }
        """
    ))
    assert (CASE86.Obl_Confidentiality, CASE86.State_WetlandViolation) in defeasible


@pytest.mark.integration
@pytest.mark.requires_java
def test_figure_1_fixture_is_pellet_consistent():
    """Running Pellet on the combined graph must report consistency."""
    owlready2 = pytest.importorskip('owlready2')

    g = _load_combined_graph()
    rdfxml = g.serialize(format='xml')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.owl', delete=False) as f:
        f.write(rdfxml)
        path = f.name

    try:
        world = owlready2.World()
        onto = world.get_ontology(f'file://{path}').load()

        with onto:
            try:
                owlready2.sync_reasoner_pellet(world)
            except owlready2.OwlReadyInconsistentOntologyError as exc:
                pytest.fail(
                    "Figure 1 fixture should be consistent; Pellet reported "
                    f"inconsistency: {exc}"
                )
    finally:
        os.unlink(path)


@pytest.mark.integration
@pytest.mark.requires_java
def test_prevailsover_asymmetry_is_enforced():
    """prevailsOver is declared owl:AsymmetricProperty (added for KI2026 so the
    consistency claim is a statement about the edge layer, not only the type
    layer). A bidirectional prevailsOver pair must therefore be inconsistent.

    The fixture already asserts Obl_PublicWelfare prevailsOver Obl_Confidentiality;
    adding the contradictory inverse should make Pellet report inconsistency.
    """
    owlready2 = pytest.importorskip('owlready2')

    g = _load_combined_graph()
    g.add((CASE86.Obl_Confidentiality, PROETH_CORE.prevailsOver,
           CASE86.Obl_PublicWelfare))
    rdfxml = g.serialize(format='xml')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.owl', delete=False) as f:
        f.write(rdfxml)
        path = f.name

    try:
        world = owlready2.World()
        onto = world.get_ontology(f'file://{path}').load()
        with onto:
            with pytest.raises(owlready2.OwlReadyInconsistentOntologyError):
                owlready2.sync_reasoner_pellet(world)
    finally:
        os.unlink(path)
