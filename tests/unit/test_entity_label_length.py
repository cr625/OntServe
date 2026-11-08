"""web.entity_extraction.build_entity_rows fits labels to the 255 characters
of ontology_entities.label (SOMA writes a 576-character rdfs:label)."""

import pytest
from rdflib import Graph

from web.entity_extraction import LABEL_MAX, build_entity_rows
from web.models import OntologyEntity

LONG = 'A relation between a description and the event type it defines. ' * 9


@pytest.mark.unit
def test_long_label_is_cut_and_hashed_as_stored():
    g = Graph()
    g.parse(data=f'''
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        <http://example.org/x#definesEventType> a owl:ObjectProperty ; rdfs:label "{LONG}" .
        <http://example.org/x#Short> a owl:Class ; rdfs:label "Short" .
    ''', format='turtle')
    rows = {r.uri.rsplit('#', 1)[-1]: r for r in build_entity_rows(1, g)[0]}
    cut = rows['definesEventType']
    assert len(LONG) > LABEL_MAX and len(cut.label) == LABEL_MAX
    assert cut.label == LONG[:LABEL_MAX - 1] + '…'
    assert cut.content_hash == OntologyEntity.compute_content_hash(cut.uri, cut.label, cut.comment)
    assert rows['Short'].label == 'Short'
