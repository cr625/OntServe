"""
Integration test for the KI2026 Figure 1 worked example (NSPE BER Case 72).

Loads the abbreviated Case 72 fixture together with the core and
intermediate ontologies, runs Pellet via owlready2 (imports stripped,
following the pipeline in editor/reasoning_service.py), and verifies:

1. The combined graph is consistent.
2. The three defeasibility edges from Figure 1 are present and
   queryable via SPARQL exactly as drawn in the paper.
3. The three typed individuals have the correct most-specific types.

These assertions are the reviewer-facing evidence that the core
ontology's competesWith / prevailsOver / defeasibleUnder object
properties, the intermediate ontology's NSPE-derived obligation and
state subclasses, and the fixture together reproduce the pattern the
paper illustrates in Figure 1.
"""

import os
import tempfile
from pathlib import Path

import pytest
import rdflib
from rdflib import Namespace, OWL, RDF


PROJECT_ROOT = Path(__file__).parent.parent.parent
ONTOLOGIES_DIR = PROJECT_ROOT / 'ontologies'
FIXTURE_DIR = PROJECT_ROOT / 'fixtures' / 'cases'

PROETH_CORE = Namespace('http://proethica.org/ontology/core#')
PROETH = Namespace('http://proethica.org/ontology/intermediate#')
CASE72 = Namespace('http://proethica.org/ontology/case/72#')


def _load_combined_graph() -> rdflib.Graph:
    """Load core + intermediate + Case 72 fixture into a single rdflib graph.

    We strip owl:imports so that the graph loads without network access to
    BFO/IAO/OWL-Time -- the Figure 1 pattern only depends on the proethica
    core object properties and the intermediate subclasses.
    """
    g = rdflib.Graph()
    g.parse(ONTOLOGIES_DIR / 'proethica-core.ttl', format='turtle')
    g.parse(ONTOLOGIES_DIR / 'proethica-intermediate.ttl', format='turtle')
    g.parse(FIXTURE_DIR / 'case_072.ttl', format='turtle')

    for s, p, o in list(g.triples((None, OWL.imports, None))):
        g.remove((s, p, o))

    return g


@pytest.mark.integration
def test_fixture_parses_and_has_three_typed_individuals():
    """The fixture must expose exactly the three typed individuals Figure 1 shows."""
    g = _load_combined_graph()

    named_individuals = set(g.subjects(RDF.type, OWL.NamedIndividual))
    case72_individuals = {i for i in named_individuals if str(i).startswith(str(CASE72))}

    assert case72_individuals == {
        CASE72.State_ConfirmedDischargeRisk,
        CASE72.Obl_FaithfulAgent,
        CASE72.Obl_PublicSafetyReport,
    }, f"Figure 1 fixture should declare exactly three named individuals, got: {case72_individuals}"


@pytest.mark.integration
def test_figure_1_types_match_intermediate_subclasses():
    """Each individual must be typed by the intermediate subclass the paper names."""
    g = _load_combined_graph()

    state_types = set(g.objects(CASE72.State_ConfirmedDischargeRisk, RDF.type))
    obl_faithful_types = set(g.objects(CASE72.Obl_FaithfulAgent, RDF.type))
    obl_public_types = set(g.objects(CASE72.Obl_PublicSafetyReport, RDF.type))

    assert PROETH.ConfirmedRiskWithoutAdequateSafeguardsState in state_types
    assert PROETH.FaithfulAgentObligation in obl_faithful_types
    assert PROETH.PostTermEnvRiskReportingObligation in obl_public_types


@pytest.mark.integration
def test_figure_1_defeasibility_edges_are_queryable():
    """The three defeasibility triples from Figure 1 must be SPARQL-queryable."""
    g = _load_combined_graph()

    # competesWith is symmetric in the core ontology, so we look for the
    # directed edge the fixture actually writes.
    competes = list(g.query(
        """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT ?a ?b WHERE { ?a core:competesWith ?b }
        """
    ))
    assert (CASE72.Obl_FaithfulAgent, CASE72.Obl_PublicSafetyReport) in competes

    prevails = list(g.query(
        """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT ?winner ?loser WHERE { ?winner core:prevailsOver ?loser }
        """
    ))
    assert (CASE72.Obl_PublicSafetyReport, CASE72.Obl_FaithfulAgent) in prevails

    defeasible = list(g.query(
        """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT ?obl ?state WHERE { ?obl core:defeasibleUnder ?state }
        """
    ))
    assert (CASE72.Obl_FaithfulAgent, CASE72.State_ConfirmedDischargeRisk) in defeasible


@pytest.mark.integration
@pytest.mark.requires_java
def test_figure_1_fixture_is_pellet_consistent():
    """Running Pellet on the combined graph must report consistency.

    Mirrors editor/reasoning_service.execute_reasoning: parse, strip imports,
    serialize to RDF/XML, load into owlready2, invoke sync_reasoner_pellet.
    """
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

        # Sanity: classes we expect to exist are still in the world after
        # reasoning.
        class_iris = {str(c.iri) for c in onto.classes()}
        assert 'http://proethica.org/ontology/intermediate#FaithfulAgentObligation' in class_iris
        assert 'http://proethica.org/ontology/intermediate#PostTermEnvRiskReportingObligation' in class_iris
        assert 'http://proethica.org/ontology/intermediate#ConfirmedRiskWithoutAdequateSafeguardsState' in class_iris
    finally:
        os.unlink(path)
