"""utils.rdf_conversion: format detection and conversion to Turtle, including
OWL functional syntax and OWL/XML through py-horned-owl."""

import builtins
from pathlib import Path

import pytest
from rdflib import Graph, Literal, OWL, RDF, RDFS, URIRef, XSD

from utils import rdf_conversion as rc

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'external'
GRIPPER = 'http://example.org/gripper#'


def fixture(name):
    return (FIXTURES / name).read_bytes()


def turtle_graph(text):
    g = Graph()
    g.parse(data=text, format='turtle')
    return g


@pytest.mark.unit
class TestDetectFormat:

    def test_extension_names_the_format(self):
        assert rc.detect_format('a.ttl') == rc.TURTLE
        assert rc.detect_format('a.rdf') == rc.RDFXML
        assert rc.detect_format('a.nt') == rc.NTRIPLES
        assert rc.detect_format('a.ofn') == rc.OFN
        assert rc.detect_format('a.owx') == rc.OWX
        assert rc.detect_format('https://example.org/x/a.jsonld') == rc.JSONLD

    def test_owl_extension_reads_the_content(self):
        assert rc.detect_format('soma.owl', fixture('gripper.ofn')) == rc.OFN
        assert rc.detect_format('arm.owl', fixture('arm.owx')) == rc.OWX
        assert rc.detect_format('sensor.owl', fixture('sensor.rdf')) == rc.RDFXML
        assert rc.detect_format('empty.owl', b'') == rc.RDFXML

    def test_content_without_a_name(self):
        assert rc.detect_format(None, fixture('device.ttl')) == rc.TURTLE
        assert rc.detect_format(None, '# comment\nPrefix(:=<http://x#>)\nOntology()') == rc.OFN
        assert rc.detect_format(None, '{"@id": "http://x"}') == rc.JSONLD

    def test_xml_root_after_doctype(self):
        text = ('<?xml version="1.0"?>\n<!DOCTYPE rdf:RDF [\n<!ENTITY owl "http://www.w3.org/2002/07/owl#" >\n]>\n'
                '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>')
        assert rc.sniff_format(text) == rc.RDFXML

    def test_hint_wins_and_aliases(self):
        assert rc.detect_format('a.ttl', hint='rdfxml') == rc.RDFXML
        assert rc.normalize_format('functional') == rc.OFN
        assert rc.normalize_format('') is None
        with pytest.raises(rc.ConversionError):
            rc.normalize_format('manchester')


@pytest.mark.unit
class TestConversion:

    def test_functional_syntax_sample(self):
        g = rc.graph_from_content(fixture('gripper.ofn'), 'ofn')
        gripper = URIRef(GRIPPER + 'Gripper')
        assert (gripper, RDF.type, OWL.Class) in g
        assert (gripper, RDFS.subClassOf, URIRef('http://example.org/device#Device')) in g
        restriction = next(o for o in g.objects(gripper, RDFS.subClassOf) if not isinstance(o, URIRef))
        assert g.value(restriction, OWL.someValuesFrom) == URIRef(GRIPPER + 'Finger')
        # plain literals stay plain, language tags stay
        assert (gripper, RDFS.label, Literal('Gripper')) in g
        assert (URIRef(GRIPPER + 'Finger'), RDFS.label, Literal('Finger', lang='en')) in g
        assert not any(isinstance(o, Literal) and o.datatype == XSD.string for o in g.objects())
        # the declared prefixes, the empty one under a name from its namespace
        bound = {p: str(n) for p, n in g.namespaces()}
        assert bound['gripper'] == GRIPPER and bound['dev'] == 'http://example.org/device#'

    def test_functional_syntax_to_turtle(self):
        text = rc.to_turtle(fixture('gripper.ofn'), 'ofn')
        assert '@prefix gripper: <http://example.org/gripper#>' in text
        assert 'gripper:Gripper' in text and '^^xsd:string' not in text
        assert len(turtle_graph(text)) == len(rc.graph_from_content(fixture('gripper.ofn'), 'ofn'))

    def test_owl_xml_sample(self):
        g = rc.graph_from_content(fixture('arm.owx'), 'owx')
        assert (URIRef('http://example.org/arm#Joint'), RDFS.subClassOf, URIRef('http://example.org/arm#Arm')) in g
        assert (URIRef('http://example.org/arm'), RDF.type, OWL.Ontology) in g

    def test_rdfxml_and_ntriples_to_turtle(self):
        text = rc.to_turtle(fixture('sensor.rdf'), 'xml')
        assert (URIRef('http://example.org/sensor#Sensor'), RDFS.label, Literal('Sensor')) in turtle_graph(text)
        nt = '<http://example.org/a> <http://www.w3.org/2000/01/rdf-schema#label> "A" .\n'
        assert len(turtle_graph(rc.to_turtle(nt, 'nt'))) == 1

    def test_turtle_is_kept_as_written(self):
        text = fixture('device.ttl').decode('utf-8')
        assert rc.to_turtle(text, 'turtle') == text

    def test_unparsable_content_raises(self):
        with pytest.raises(rc.ConversionError):
            rc.to_turtle('@prefix x: <http://x#> .\nx:a x:b', 'turtle')
        with pytest.raises(rc.ConversionError):
            rc.to_turtle('Ontology(<http://x> SubClassOf(', 'ofn')

    def test_canonical_turtle_is_stable(self):
        # Two parses give different blank node ids, and the canonical text is the same
        first = rc.graph_to_turtle(rc.graph_from_content(fixture('device.ttl'), 'turtle'), canonical=True)
        second = rc.graph_to_turtle(rc.graph_from_content(fixture('device.ttl'), 'turtle'), canonical=True)
        assert first == second
        assert len(turtle_graph(first)) == 13

    def test_missing_py_horned_owl(self, monkeypatch):
        real_import = builtins.__import__

        def no_horned(name, *args, **kwargs):
            if name == 'pyhornedowl':
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, '__import__', no_horned)
        with pytest.raises(rc.ConversionError, match='py-horned-owl'):
            rc.graph_from_content(fixture('gripper.ofn'), 'ofn')
