"""services.external_collection without a database: the manifest, the merge
of the files with drop_imports, the reference-only stub and the file steps."""

import hashlib
import shutil
from pathlib import Path

import pytest
from rdflib import Graph, Literal, OWL, RDF, URIRef
from rdflib.namespace import DCTERMS

from services import external_collection as ec
from services.ontology_credit import credit_from_graph

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'external'
NS = 'https://ontserve.example/ontology/'
CREDIT = {'title': 'Gripper Ontology', 'creators': ['Ada Lovelace'], 'license': 'MIT',
          'source': {'repository': 'https://github.com/example/gripper', 'commit': 'abc'}}


def manifest(*entries, **top):
    return {'category': 'Robotics and Automation', 'retrieved': '2026-11-07',
            'ontologies': list(entries), **top}


def entry(**kw):
    base = {'name': 'gripper', 'display_name': 'Gripper', 'subcategory': 'Grasping',
            'files': [{'path': 'gripper.ofn', 'format': 'ofn'}, {'path': 'device.ttl'}],
            'drop_imports': ['http://example.org/device'], 'credit': dict(CREDIT)}
    base.update(kw)
    return base


def turtle(text):
    g = Graph()
    g.parse(data=text, format='turtle')
    return g


@pytest.mark.unit
class TestManifest:

    def test_defaults(self):
        m = ec.parse_manifest(manifest(entry(display_name=None)))
        assert m.collection == 'robotics' and m.folder == 'robotics-and-automation'
        assert m.retrieved == '2026-11-07'
        e = m.entries[0]
        assert e.display_name == 'Gripper Ontology'          # the credit title
        assert e.credit['retrieved'] == '2026-11-07'          # the manifest date
        assert e.files[1] == ec.SourceFile(path='device.ttl', url=None, format=None)

    @pytest.mark.parametrize('bad, message', [
        (manifest(entry(colour='red')), 'unknown keys colour'),
        (manifest(entry(name='Gripper')), 'name must be'),
        (manifest(entry(name='proethica-gripper')), 'proethica-'),
        (manifest(entry(), entry()), 'occurs twice'),
        (manifest(entry(files=[])), 'at least one file'),
        (manifest(entry(files=[{'path': 'a.owl', 'format': 'manchester'}])), 'Unknown serialization'),
        (manifest(entry(credit={'license': 'MIT'})), 'title'),
        ({'ontologies': [entry()]}, 'category is required'),
        (manifest(entry(), extra=1), 'unknown keys extra'),
    ])
    def test_errors(self, bad, message):
        with pytest.raises(ec.ManifestError, match=message):
            ec.parse_manifest(bad)

    def test_reference_only_needs_no_files(self):
        credit = {**CREDIT, 'redistribution': 'reference-only'}
        m = ec.parse_manifest(manifest(entry(files=[], credit=credit)))
        assert m.entries[0].reference_only


@pytest.mark.unit
class TestBuild:

    def build(self, **kw):
        m = ec.parse_manifest(manifest(entry(**kw)))
        return ec.build_entry(m.entries[0], FIXTURES, NS)

    def test_merge_and_drop_imports(self):
        built = self.build()
        g = turtle(built.turtle)
        assert built.iri == 'http://example.org/gripper'      # the first file names the ontology
        assert (URIRef('http://example.org/gripper#Gripper'), RDF.type, OWL.Class) in g
        assert (URIRef('http://example.org/device#Device'), RDF.type, OWL.Class) in g
        imports = set(g.objects(None, OWL.imports))
        assert URIRef('http://example.org/device') not in imports
        assert imports == {URIRef('http://example.org/upper')}  # imported by both files, not dropped
        assert built.description == 'A gripper module in OWL functional syntax.'
        assert built.triples == len(g) and not built.warnings

    def test_unmatched_drop_import_is_reported(self):
        built = self.build(drop_imports=['http://example.org/nowhere'])
        assert built.warnings == ['drop_imports: no merged file imports http://example.org/nowhere']

    def test_same_input_same_turtle(self):
        assert self.build().turtle == self.build().turtle

    def test_reference_only_stub(self):
        credit = {**CREDIT, 'redistribution': 'reference-only', 'homepage': 'https://example.org/gripper',
                  'citation': 'Lovelace (2026)'}
        built = self.build(credit=credit, description='Listed by reference.')
        g = turtle(built.turtle)
        subject = URIRef('http://example.org/gripper')            # read from the source
        assert set(g.subjects()) == {subject}                       # the header only
        assert (subject, RDF.type, OWL.Ontology) in g
        assert (subject, DCTERMS.title, Literal('Gripper Ontology')) in g
        assert (subject, DCTERMS.creator, Literal('Ada Lovelace')) in g
        assert (subject, DCTERMS.source, URIRef('https://github.com/example/gripper')) in g
        assert not list(g.triples((None, OWL.imports, None)))
        header = credit_from_graph(g, str(subject))
        assert header['title'] == 'Gripper Ontology' and header['homepage'] == 'https://example.org/gripper'

    def test_reference_only_without_files_uses_the_namespace(self):
        credit = {**CREDIT, 'redistribution': 'reference-only'}
        built = self.build(files=[], credit=credit)
        assert built.iri == NS + 'gripper'


@pytest.mark.unit
class TestFiles:

    def test_local_copy_then_url(self, tmp_path):
        spec = ec.SourceFile(path='missing.ttl', url='https://example.org/device.ttl', format=None)
        fetched = []

        def fetch(url):
            fetched.append(url)
            return (FIXTURES / 'device.ttl').read_bytes()

        data, origin = ec.read_file(spec, tmp_path, fetch)
        assert fetched == [spec.url] and origin == spec.url
        shutil.copy(FIXTURES / 'device.ttl', tmp_path / 'missing.ttl')
        data2, origin2 = ec.read_file(spec, tmp_path, fetch)
        assert data2 == data and origin2 == str((tmp_path / 'missing.ttl').resolve()) and len(fetched) == 1

    def test_sha256_and_path_checks(self, tmp_path):
        shutil.copy(FIXTURES / 'device.ttl', tmp_path / 'device.ttl')
        good = hashlib.sha256((FIXTURES / 'device.ttl').read_bytes()).hexdigest()
        ec.read_file(ec.SourceFile('device.ttl', None, None, good), tmp_path)
        with pytest.raises(ec.ManifestError, match='SHA-256'):
            ec.read_file(ec.SourceFile('device.ttl', None, None, '0' * 64), tmp_path)
        with pytest.raises(ec.ManifestError, match='leaves the source directory'):
            ec.read_file(ec.SourceFile('../device.ttl', None, None), tmp_path / 'sub')
        with pytest.raises(ec.ManifestError, match='no url'):
            ec.read_file(ec.SourceFile('absent.ttl', None, None), tmp_path)

    def test_write_if_changed(self, tmp_path):
        path = tmp_path / 'external' / 'robotics-and-automation' / 'gripper.ttl'
        assert ec.write_if_changed(path, 'a\n') is True
        mtime = path.stat().st_mtime_ns
        assert ec.write_if_changed(path, 'a\n') is False and path.stat().st_mtime_ns == mtime
        assert ec.write_if_changed(path, 'b\n') is True and path.read_text() == 'b\n'
