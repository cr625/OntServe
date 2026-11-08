"""services.ontology_credit: the credit schema, the header fallback and the
rows the fallback applies to."""

import datetime as dt
from types import SimpleNamespace

import pytest
from rdflib import Graph

from services import ontology_credit as oc

FULL = {
    'title': 'SOMA',
    'creators': ['Daniel Beßler', 'Robert Porzel'],
    'publisher': 'EASE CRC',
    'license': {'id': 'MIT', 'url': 'https://opensource.org/license/mit'},
    'source': {'repository': 'https://github.com/ease-crc/soma', 'commit': 'abc123',
               'paths': ['owl/SOMA.owl'], 'url': None},
    'homepage': 'https://ease-crc.github.io/soma/',
    'citation': {'text': 'Beßler et al. 2021', 'doi': 'https://doi.org/10.1234/x', 'url': None},
    'retrieved': dt.date(2026, 11, 7),
    'modifications': 'Converted from OWL functional syntax to Turtle.',
    'used_in': [{'text': 'A paper', 'reasoner': 'HermiT'}, 'Another paper'],
    'redistribution': 'hosted',
}

HEADER = '''
@prefix dc: <http://purl.org/dc/elements/1.1/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<http://example.org/onto> a owl:Ontology ;
    dcterms:title "Example ontology" ;
    dc:creator "B. Author", "A. Author" ;
    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ;
    dcterms:bibliographicCitation "Author, A. (2026). Example." ;
    owl:versionInfo "1.2" ;
    rdfs:seeAlso <https://example.org/docs> .

<http://example.org/other> a owl:Ontology ;
    dcterms:title "Another header" .
'''


def graph(text):
    g = Graph()
    g.parse(data=text, format='turtle')
    return g


@pytest.mark.unit
class TestNormalize:

    def test_full_block(self):
        c = oc.normalize_credit(FULL)
        assert c['creators'] == ['Daniel Beßler', 'Robert Porzel']
        assert c['license'] == {'id': 'MIT', 'url': 'https://opensource.org/license/mit'}
        assert c['source']['paths'] == ['owl/SOMA.owl'] and c['source']['url'] is None
        assert c['citation']['doi'] == '10.1234/x'
        assert c['retrieved'] == '2026-11-07'
        assert c['used_in'] == [{'text': 'A paper', 'reasoner': 'HermiT'},
                                {'text': 'Another paper', 'reasoner': None}]
        assert c['version'] is None and set(c) == set(oc._FIELDS)

    def test_shorthands_and_defaults(self):
        c = oc.normalize_credit({'title': 'T', 'license': 'none stated', 'creators': 'One Author',
                                 'citation': 'T. (2020)'}, retrieved='2026-11-01')
        assert c['license'] == {'id': 'none stated', 'url': None}
        assert c['creators'] == ['One Author'] and c['citation']['text'] == 'T. (2020)'
        assert c['redistribution'] == 'hosted' and c['retrieved'] == '2026-11-01'

    @pytest.mark.parametrize('block, message', [
        ({'title': 'T', 'license': 'MIT', 'licence': 'x'}, 'unknown credit keys: licence'),
        ({'title': 'T', 'license': {'id': 'MIT', 'link': 'x'}}, 'credit.license'),
        ({'license': 'MIT'}, 'title'),
        ({'title': 'T'}, 'license'),
        ({'title': 'T', 'license': 'MIT', 'redistribution': 'mirror'}, 'redistribution'),
        ({'title': 'T', 'license': 'none stated', 'redistribution': 'reference-only'}, 'reference-only'),
        ({'title': 'T', 'license': 'MIT', 'retrieved': 'last week'}, 'YYYY-MM-DD'),
    ])
    def test_strict_errors(self, block, message):
        with pytest.raises(oc.CreditError, match=message):
            oc.normalize_credit(block)

    def test_lenient_mode_coerces(self):
        c = oc.normalize_credit({'title': 'T', 'extra': 1, 'redistribution': 'mirror'}, strict=False)
        assert c['title'] == 'T' and c['redistribution'] == 'hosted' and 'extra' not in c

    def test_source_link(self):
        assert oc.source_link(oc.normalize_credit(FULL)) == 'https://github.com/ease-crc/soma'
        assert oc.source_link({'source': None, 'homepage': 'https://h'}) == 'https://h'
        assert oc.source_link(None) is None


@pytest.mark.unit
class TestHeaderFallback:

    def test_header_fields(self):
        c = oc.credit_from_graph(graph(HEADER), 'http://example.org/onto')
        assert c['title'] == 'Example ontology'
        assert c['creators'] == ['A. Author', 'B. Author']
        assert c['license'] == {'id': 'https://creativecommons.org/licenses/by/4.0/',
                                'url': 'https://creativecommons.org/licenses/by/4.0/'}
        assert c['citation']['text'] == 'Author, A. (2026). Example.'
        assert c['version'] == '1.2' and c['homepage'] == 'https://example.org/docs'

    def test_named_header_and_rights(self):
        text = HEADER + '<http://example.org/other> <http://purl.org/dc/elements/1.1/rights> "All rights reserved" .'
        c = oc.credit_from_graph(graph(text), 'http://example.org/other')
        assert c['title'] == 'Another header'
        assert c['license'] == {'id': 'All rights reserved', 'url': None}

    def test_header_without_fields(self):
        text = '<http://x> a <http://www.w3.org/2002/07/owl#Ontology> .'
        assert oc.credit_from_graph(graph(text), 'http://x') is None
        assert oc.credit_from_content('not turtle at all', None) is None


def row(meta, content, otype='base', source='external', name='x', vid=1):
    version = SimpleNamespace(id=vid, content=content, content_hash=f'h{vid}')
    return SimpleNamespace(name=name, ontology_type=otype, source_system=source, meta_data=meta,
                           base_uri='http://example.org/onto', current_version=version)


@pytest.mark.unit
class TestCreditFor:

    def test_stored_block_wins(self):
        r = row({'credit': {**FULL, 'retrieved': '2026-11-07'}}, HEADER)
        assert oc.credit_for(r)['title'] == 'SOMA'

    def test_header_fallback_in_collection_categories(self):
        for meta in ({'collection': 'robotics'}, {'category': 'Physical Systems'}):
            assert oc.credit_for(row(meta, HEADER, vid=id(meta)))['title'] == 'Example ontology'

    def test_no_fallback_for_proethica_rows(self):
        # ProEthica headers carry dc:creator and owl:versionInfo, and their pages show no panel
        assert oc.credit_for(row({}, HEADER, otype='base', source='proethica', name='proethica-core')) is None
        assert oc.credit_for(row({}, HEADER, otype='upper', source='external', name='bfo')) is None
        assert oc.credit_for(row({}, HEADER, otype='case', source='proethica', name='proethica-case-7')) is None
