"""Unit tests for the attribute/relationship split shared by the case-page
cards and the entity detail page (web/ontology_routes._categorize_entity_properties).

IRI-valued triples are object properties (R->P->O / defeasibility edges) and must
be grouped as relationships; literal-valued triples stay as attributes; the
conceptCategory and <concept>class keys are dropped from display.
"""
from types import SimpleNamespace

from web.ontology_routes import _categorize_entity_properties, _iri_values


def test_iri_values_detects_single_and_list_and_literal():
    assert _iri_values('http://x/case/60#Foo') == ['http://x/case/60#Foo']
    assert _iri_values(['http://x#A', 'http://x#B']) == ['http://x#A', 'http://x#B']
    assert _iri_values('public_responsibility') is None
    assert _iri_values(['plain', 'text']) is None


def test_categorize_splits_relationships_from_attributes():
    entity = SimpleNamespace(properties={
        'rolecategory': 'public_responsibility',
        'caseinvolvement': 'The engineer did X.',
        'hasObligation': 'http://proethica.org/ontology/case/60#Some_Obligation',
        'adheresToPrinciple': ['http://proethica.org/ontology/case/60#P1',
                               'http://proethica.org/ontology/case/60#P2'],
        'conceptCategory': 'Role',
        'roleclass': 'Multi-State Licensed Engineer',
        'sourcetext': 'verbatim quote',
    })

    groups = _categorize_entity_properties(entity)

    rel_keys = [k for k, _ in groups['relationships']]
    assert set(rel_keys) == {'hasObligation', 'adheresToPrinciple'}
    # adheresToPrinciple keeps both target IRIs
    rel = dict(groups['relationships'])
    assert len(rel['adheresToPrinciple']) == 2

    core_labels = [label for label, _ in groups['core']]
    assert 'Role category' in core_labels        # literal attribute, humanised
    assert 'caseinvolvement' not in core_labels   # routed to description group

    # conceptCategory and <concept>class never displayed
    all_labels = ' '.join(
        label for grp in ('core', 'description', 'evidence', 'extraction_meta')
        for label, _ in groups[grp]
    )
    assert 'Concept' not in all_labels
    assert 'Role Class' not in all_labels
    # caseinvolvement is the description; sourcetext is evidence
    assert any('engineer did X' in str(v) for _, v in groups['description'])
    assert groups['evidence']
