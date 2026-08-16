"""Unit tests for OntologySyncService._extract_dcterms_title.

Locks the durable case-title contract: ProEthica emits the human case title as
dcterms:title in the TTL header, and the sync service reads it into
display_name when first creating a case ontology.
"""
import tempfile
from pathlib import Path

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


def test_extracts_title_when_present():
    svc = OntologySyncService.__new__(OntologySyncService)
    p = _write('    dcterms:title "Misrepresentation of Qualifications" ;\n')
    assert svc._extract_dcterms_title(p) == "Misrepresentation of Qualifications"


def test_returns_none_when_absent():
    svc = OntologySyncService.__new__(OntologySyncService)
    p = _write('')
    assert svc._extract_dcterms_title(p) is None


def test_extract_ontology_meta_reads_case_number_and_decade():
    """ProEthica's case header carries dcterms:identifier (NSPE case number) and
    dcterms:temporal (decade); the sync maps them to metadata.case_number and
    metadata.subcategory (index grouping)."""
    svc = OntologySyncService.__new__(OntologySyncService)
    p = _write('    dcterms:title "Misrepresentation of Qualifications" ;\n'
               '    dcterms:identifier "24-2" ;\n'
               '    dcterms:temporal "2020s" ;\n')
    meta = svc._extract_ontology_meta(p)
    assert meta['title'] == "Misrepresentation of Qualifications"
    assert meta['identifier'] == "24-2"
    assert meta['temporal'] == "2020s"


def test_extract_ontology_meta_without_case_fields():
    svc = OntologySyncService.__new__(OntologySyncService)
    meta = svc._extract_ontology_meta(_write(''))
    assert 'identifier' not in meta and 'temporal' not in meta
