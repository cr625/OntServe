"""Unit tests for the editor visualization service (basic builder)."""

from types import SimpleNamespace

import pytest

from editor import visualization_service as vs


I = 'http://proethica.org/ontology/intermediate#'
CORE = 'http://proethica.org/ontology/core#'
XSD = 'http://www.w3.org/2001/XMLSchema#'


def _entity(uri, label, entity_type='class', parent_uri=None, domain=None,
            range=None, properties=None, comment=''):
    return SimpleNamespace(uri=uri, label=label, entity_type=entity_type,
                           parent_uri=parent_uri, domain=domain, range=range,
                           properties=properties, comment=comment)


def _build(monkeypatch, entities):
    monkeypatch.setattr(vs, '_load_ontology_entities',
                        lambda name: (SimpleNamespace(id=1, name=name), entities))
    return vs.build_basic_visualization('proethica-intermediate')


class TestHelpers:

    def test_uri_list_shapes(self):
        assert vs._uri_list(None) == []
        assert vs._uri_list(I + 'Role') == [I + 'Role']
        assert vs._uri_list([I + 'Role', I + 'State']) == [I + 'Role', I + 'State']

    def test_datatype_uri(self):
        assert vs._is_datatype_uri(XSD + 'string')
        assert vs._is_datatype_uri('http://www.w3.org/2000/01/rdf-schema#Literal')
        assert not vs._is_datatype_uri(I + 'EthicalCode')

    def test_deprecated_marker(self):
        assert vs._is_deprecated(_entity('u', 'x', properties={'deprecated': 'true'}))
        assert vs._is_deprecated(_entity('u', 'x', properties={'deprecated': True}))
        assert not vs._is_deprecated(_entity('u', 'x', properties=None))


class TestBasicVisualization:

    def test_object_property_becomes_labeled_edge_not_node(self, monkeypatch):
        entities = [
            _entity(I + 'ProfessionalRole', 'Professional Role', parent_uri=CORE + 'Role'),
            _entity(I + 'EthicalCode', 'Ethical Code', parent_uri=CORE + 'Resource'),
            _entity(I + 'governedByCode', 'governed by code', entity_type='property',
                    domain=I + 'ProfessionalRole', range=I + 'EthicalCode'),
        ]
        result = _build(monkeypatch, entities)
        nodes = result['visualization']['nodes']
        edges = result['visualization']['edges']
        assert not any(n['data']['type'] == 'property' for n in nodes)
        prop_edges = [e for e in edges if 'property-edge' in e['classes']]
        assert len(prop_edges) == 1
        assert prop_edges[0]['data']['source'] == I + 'ProfessionalRole'
        assert prop_edges[0]['data']['target'] == I + 'EthicalCode'
        assert prop_edges[0]['data']['label'] == 'governed by code'
        assert result['statistics']['object_property_edges'] == 1

    def test_datatype_property_omitted_and_counted(self, monkeypatch):
        entities = [
            _entity(I + 'CausalChain', 'Causal Chain'),
            _entity(I + 'causeText', 'cause text', entity_type='property',
                    domain=I + 'CausalChain', range=XSD + 'string'),
            _entity(I + 'archetypeAxis', 'archetype axis', entity_type='property',
                    domain=None, range=None),
        ]
        result = _build(monkeypatch, entities)
        assert result['statistics']['omitted_datatype_properties'] == 2
        assert not any('property-edge' in e['classes']
                       for e in result['visualization']['edges'])

    def test_deprecated_entities_excluded(self, monkeypatch):
        entities = [
            _entity(I + 'LiveClass', 'Live Class'),
            _entity(I + 'OldClass', 'Old Class', properties={'deprecated': 'true'}),
            _entity(I + 'oldProp', 'old prop', entity_type='property',
                    domain=I + 'LiveClass', range=I + 'LiveClass',
                    properties={'deprecated': 'true'}),
        ]
        result = _build(monkeypatch, entities)
        labels = [n['data']['label'] for n in result['visualization']['nodes']]
        assert 'Old Class' not in labels
        assert result['statistics']['deprecated_excluded'] == 2
        assert result['statistics']['object_property_edges'] == 0

    def test_no_fabricated_relatedto_edges(self, monkeypatch):
        entities = [
            _entity(I + 'A', 'A'),
            _entity(I + 'orphanProp', 'orphan prop', entity_type='property',
                    domain=None, range=None),
        ]
        result = _build(monkeypatch, entities)
        assert not any(e['data'].get('type') == 'relatedTo'
                       for e in result['visualization']['edges'])

    def test_external_domain_range_get_nodes(self, monkeypatch):
        entities = [
            _entity(I + 'LocalClass', 'Local Class'),
            _entity(I + 'crossProp', 'cross prop', entity_type='property',
                    domain=I + 'LocalClass', range=CORE + 'Obligation'),
        ]
        result = _build(monkeypatch, entities)
        node_ids = {n['data']['id'] for n in result['visualization']['nodes']}
        assert CORE + 'Obligation' in node_ids  # external endpoint materialized

    def test_multi_domain_list(self, monkeypatch):
        entities = [
            _entity(I + 'A', 'A'), _entity(I + 'B', 'B'), _entity(I + 'C', 'C'),
            _entity(I + 'p', 'p', entity_type='property',
                    domain=[I + 'A', I + 'B'], range=I + 'C'),
        ]
        result = _build(monkeypatch, entities)
        prop_edges = [e for e in result['visualization']['edges']
                      if 'property-edge' in e['classes']]
        assert {(e['data']['source'], e['data']['target']) for e in prop_edges} == {
            (I + 'A', I + 'C'), (I + 'B', I + 'C')}

    def test_missing_ontology(self, monkeypatch):
        monkeypatch.setattr(vs, '_load_ontology_entities', lambda name: (None, []))
        assert vs.build_basic_visualization('nope')['success'] is False
