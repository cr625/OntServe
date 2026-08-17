"""Header contract between ProEthica case TTLs and the OntServe sync.

ProEthica writes rdfs:label, dcterms:title (case title), dcterms:identifier
(NSPE case number) and dcterms:temporal (decade) into every case ontology
header (proethica app/services/commit/case_header.py). The sync reads them
with OntologySyncService._extract_ontology_meta and maps them to metadata
display_name / case_number / subcategory via HEADER_META (fill-if-absent, so
values set on the settings page or by tools/set_ontology_categories.py survive
later commits; source / version always refresh).
"""
import tempfile
from pathlib import Path

import pytest

from services.ontology_categories import CASE_NUMBER_KEY, DISPLAY_NAME_KEY, SUBCATEGORY_KEY
from services.ontology_sync_service import OntologySyncService

_HEADER = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<http://proethica.org/ontology/case/60> a owl:Ontology ;
    rdfs:label "ProEthica Case 60 Ontology" ;
{title_line}    owl:imports <http://proethica.org/ontology/intermediate> .
"""


def _write(title_line):
    p = Path(tempfile.mktemp(suffix='.ttl'))
    p.write_text(_HEADER.format(title_line=title_line))
    return p


def _svc():
    return OntologySyncService.__new__(OntologySyncService)


def test_extracts_title_when_present():
    p = _write('    dcterms:title "Misrepresentation of Qualifications" ;\n')
    assert _svc()._extract_ontology_meta(p).get('title') == "Misrepresentation of Qualifications"


def test_title_absent():
    assert 'title' not in _svc()._extract_ontology_meta(_write(''))


def test_extract_ontology_meta_reads_case_number_and_decade():
    p = _write('    dcterms:title "Misrepresentation of Qualifications" ;\n'
               '    dcterms:identifier "24-2" ;\n'
               '    dcterms:temporal "2020s" ;\n')
    meta = _svc()._extract_ontology_meta(p)
    assert meta['title'] == "Misrepresentation of Qualifications"
    assert meta['identifier'] == "24-2"
    assert meta['temporal'] == "2020s"


def test_extract_ontology_meta_without_case_fields():
    meta = _svc()._extract_ontology_meta(_write(''))
    assert 'identifier' not in meta and 'temporal' not in meta


def test_apply_header_meta_fill_and_refresh_policy():
    ometa = {'title': 'T', 'identifier': '24-2', 'temporal': '2020s', 'source': 's2', 'version': 'v2'}
    fresh = OntologySyncService._apply_header_meta({}, ometa)
    assert fresh == {DISPLAY_NAME_KEY: 'T', CASE_NUMBER_KEY: '24-2', SUBCATEGORY_KEY: '2020s',
                     'source': 's2', 'version': 'v2'}
    # existing display_name / case_number / subcategory are kept; source / version refresh
    kept = OntologySyncService._apply_header_meta(
        {DISPLAY_NAME_KEY: 'edited', CASE_NUMBER_KEY: '58-1', SUBCATEGORY_KEY: '1950s', 'source': 's1'}, ometa)
    assert kept[DISPLAY_NAME_KEY] == 'edited' and kept[CASE_NUMBER_KEY] == '58-1' and kept[SUBCATEGORY_KEY] == '1950s'
    assert kept['source'] == 's2' and kept['version'] == 'v2'
    # missing header fields leave metadata untouched
    assert OntologySyncService._apply_header_meta({'x': 1}, {}) == {'x': 1}


def test_proethica_golden_header_round_trips():
    """Pin the contract against ProEthica's own golden case TTL when the sibling
    repo is checked out next to this one (skipped elsewhere)."""
    fixture = Path(__file__).resolve().parents[3] / 'proethica' / 'tests' / 'fixtures' / 'commit_golden' / 'individuals_case_501.ttl'
    if not fixture.exists():
        pytest.skip(f'sibling ProEthica golden fixture not found: {fixture}')
    meta = _svc()._extract_ontology_meta(fixture)
    assert meta['title'] and meta['identifier'] and meta['temporal']
    md = OntologySyncService._apply_header_meta({}, meta)
    assert md[DISPLAY_NAME_KEY] == meta['title']
    assert md[CASE_NUMBER_KEY] == meta['identifier']
    assert md[SUBCATEGORY_KEY] == meta['temporal']
