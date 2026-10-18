"""Named-individual count of the case page (case 24-1 review, lessons L1 and L6).

The extractor stores the reified prov:Derivation edge-provenance nodes and the
OWL-Time anchors of a case graph as entity_type 'individual' beside the
owl:NamedIndividual declarations, so case 8 printed 595 "Named Individuals" for
176 declarations. The extraction now records the declaration itself in
properties['named_individual'] (web/entity_extraction.py) and the case page
counts that flag (web/case_display.is_named_individual), falling back to the
prov/time namespace rule for rows extracted before the flag existed.

Pure rdflib: build_entity_rows runs the extraction passes without a database.
"""
from types import SimpleNamespace

import rdflib

from web.case_display import is_named_individual, is_support_node, organize_entities_for_case
from web.entity_extraction import build_entity_rows

TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix time: <http://www.w3.org/2006/time#> .
@prefix core: <http://proethica.org/ontology/core#> .
@prefix case8: <http://proethica.org/ontology/case/8#> .

case8:Engineer_L_Agent a owl:NamedIndividual, core:Agent ;
    rdfs:label "Engineer L" .

case8:defeasibility_edge_provenance_Duty_A_prevailsOver_Duty_B a prov:Derivation ;
    rdfs:label "Defeasibility edge from tensionresolution" ;
    prov:value "A passage." ;
    rdfs:comment "source_field=tensionresolution; confidence=0.9" ;
    prov:wasDerivedFrom case8:Engineer_L_Agent .

case8:Instant_1 a time:Instant ;
    rdfs:label "Instant 1" ;
    time:inXSDDateTimeStamp "2024-01-01T00:00:00Z"^^xsd:dateTimeStamp .
"""

CORE = "http://proethica.org/ontology/core#"
PROV = "http://www.w3.org/ns/prov#"
TIME = "http://www.w3.org/2006/time#"


def _rows():
    g = rdflib.Graph()
    g.parse(data=TTL, format="turtle")
    return build_entity_rows(ontology_id=1, g=g)


def test_all_three_rows_are_stored_as_individuals():
    """entity_type alone is the overstated figure the header used to print."""
    _, counts = _rows()
    assert counts["individual"] == 3


def test_flag_marks_the_declaration_only():
    rows, _ = _rows()
    by_label = {r.label: r for r in rows}
    assert by_label["Engineer L"].properties["named_individual"] is True
    assert by_label["Defeasibility edge from tensionresolution"].properties["named_individual"] is False
    assert by_label["Instant 1"].properties["named_individual"] is False
    assert [is_named_individual(r) for r in rows].count(True) == 1


def test_case_page_counts_one_named_individual_and_two_support_nodes():
    rows, _ = _rows()
    result = organize_entities_for_case(rows, "engineering")
    assert result["stats"]["individuals"] == 1
    assert result["stats"]["support"] == 2
    by_id = {s["id"]: s for s in result["sections"]}
    assert sorted(e.label for e in by_id["support"]["entities"]) == [
        "Defeasibility edge from tensionresolution", "Instant 1"]
    assert [e.label for e in by_id["agents"]["entities"]] == ["Engineer L"]
    assert "other" not in by_id


def test_rows_without_the_flag_fall_back_to_the_namespace_rule():
    """Rows extracted before the flag carry no 'named_individual' key."""
    named = SimpleNamespace(entity_type="individual", parent_uri=CORE + "Agent",
                            properties=None, label="agent")
    prov_node = SimpleNamespace(entity_type="individual", parent_uri=PROV + "Derivation",
                                properties=None, label="derivation")
    time_node = SimpleNamespace(entity_type="individual", parent_uri="http://example.org/Anchor",
                                properties={"rdf_types": [TIME + "Instant", "http://example.org/Anchor"]},
                                label="anchor")
    class_row = SimpleNamespace(entity_type="class", parent_uri=CORE + "State",
                                properties=None, label="a class")
    assert is_named_individual(named)
    assert not is_named_individual(prov_node)
    assert not is_named_individual(time_node)
    assert is_support_node(time_node) and not is_support_node(named)
    assert not is_named_individual(class_row)


def test_explicit_flag_wins_over_the_namespace_rule():
    flagged_false = SimpleNamespace(entity_type="individual", parent_uri=CORE + "Obligation",
                                    properties={"named_individual": False}, label="catch-all row")
    flagged_true = SimpleNamespace(entity_type="individual", parent_uri=PROV + "Entity",
                                   properties={"named_individual": True}, label="declared prov entity")
    assert not is_named_individual(flagged_false)
    assert is_named_individual(flagged_true)
