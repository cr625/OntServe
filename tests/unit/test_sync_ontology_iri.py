"""ontologies.base_uri from the owl:Ontology IRI (case 24-1 review, lesson L2).

The sync used to set base_uri to the file-name pattern
http://proethica.org/ontology/<name>#, a namespace that occurs nowhere in a case
graph (the case namespace is http://proethica.org/ontology/case/<n>#, the
ontology IRI .../case/<n>). The case page header, the canonical Link header and
the generated @prefix line all printed it. The sync now reads the declared IRI,
falls back to the pattern only when a file declares none, repairs a
pattern-valued row on re-sync, and tools/backfill_base_uri.py repairs existing
rows through declared_base_uri.

The sync paths run against a fake session (no database): the Ontology and
OntologyVersion rows are plain model instances.
"""
import tempfile
from pathlib import Path

import pytest

from services.ontology_sync_service import (
    OntologySyncService, declared_base_uri, ontology_iri_from_content)
from web.rdf_helpers import namespace_from_base_uri

CASE_IRI = "http://proethica.org/ontology/case/8"
PATTERN = "http://proethica.org/ontology/proethica-case-8#"

CASE_HEADER = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix case8: <http://proethica.org/ontology/case/8#> .
<http://proethica.org/ontology/case/8> a owl:Ontology ;
    rdfs:label "ProEthica Case 8 Ontology" ;
    dcterms:title "Public Safety and Client Confidentiality" ;
    dcterms:identifier "24-1" ;
    owl:imports <http://proethica.org/ontology/intermediate> .
case8:Engineer_L a owl:NamedIndividual ; rdfs:label "Engineer L" .
"""

NO_HEADER = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix case8: <http://proethica.org/ontology/case/8#> .
case8:Engineer_L a owl:NamedIndividual ; rdfs:label "Engineer L" .
"""


def test_iri_extraction_from_content():
    assert ontology_iri_from_content(CASE_HEADER) == CASE_IRI


def test_iri_extraction_without_declaration():
    assert ontology_iri_from_content(NO_HEADER) is None
    assert ontology_iri_from_content("") is None
    assert ontology_iri_from_content(None) is None
    assert ontology_iri_from_content("not turtle {{{") is None


def test_anonymous_ontology_declaration_yields_no_iri():
    ttl = NO_HEADER + "[] a owl:Ontology ; rdfs:label \"anonymous\" .\n"
    assert ontology_iri_from_content(ttl) is None


def test_extract_ontology_meta_carries_the_iri_beside_the_header_fields():
    p = Path(tempfile.mktemp(suffix=".ttl"))
    p.write_text(CASE_HEADER)
    meta = OntologySyncService.__new__(OntologySyncService)._extract_ontology_meta(p)
    assert meta["iri"] == CASE_IRI
    assert meta["title"] == "Public Safety and Client Confidentiality"
    assert meta["identifier"] == "24-1"


def test_declared_base_uri_decisions():
    assert declared_base_uri("proethica-case-8", PATTERN, CASE_HEADER) == (CASE_IRI, "declared IRI")
    assert declared_base_uri("proethica-case-8", CASE_IRI, CASE_HEADER) == (None, "unchanged")
    assert declared_base_uri("proethica-case-8", PATTERN, NO_HEADER) == (None, "no owl:Ontology declaration")
    assert declared_base_uri("proethica-case-8", PATTERN, None) == (None, "no content")


def test_declared_base_uri_keeps_a_hand_set_value():
    """Review fix: the backfill rewrites only a pattern-valued row, as the sync
    does on re-sync. A base_uri set on the settings page (or by a migration)
    differs from the declared IRI as well and used to be listed for a change."""
    assert declared_base_uri("proethica-case-8", "http://example.org/custom#", CASE_HEADER) \
        == (None, "hand-set base_uri kept")
    # the draft form of the pattern (no '#') is not the pattern either
    assert declared_base_uri("proethica-case-8", "http://proethica.org/ontology/proethica-case-8", CASE_HEADER) \
        == (None, "hand-set base_uri kept")


TWO_DECLARATIONS = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
<http://proethica.org/ontology/engineering-ethics> a owl:Ontology ;
    rdfs:comment "NSPE engineering ethics ontology" ;
    owl:versionInfo "3.1" .
<http://proethica.org/ontology/aaa-standards> a owl:Ontology ;
    dcterms:title "Technical Standards" ;
    owl:versionInfo "1.0" .
"""


def test_several_declarations_prefer_the_one_named_like_the_file():
    """Review fix: ontologies/engineering-ethics.ttl declares two ontologies
    (.../engineering-ethics and .../engineering_standards); sorted order picks
    the file's own IRI there only because '-' sorts before '_'. The file stem
    (the ontology name) decides when it names one of the declarations."""
    assert ontology_iri_from_content(TWO_DECLARATIONS) == "http://proethica.org/ontology/aaa-standards"
    assert ontology_iri_from_content(TWO_DECLARATIONS, preferred_name="engineering-ethics") \
        == "http://proethica.org/ontology/engineering-ethics"
    # a name that matches no declaration falls back to the sorted order
    assert ontology_iri_from_content(TWO_DECLARATIONS, preferred_name="other") \
        == "http://proethica.org/ontology/aaa-standards"
    assert declared_base_uri("engineering-ethics", "http://proethica.org/ontology/engineering-ethics#",
                             TWO_DECLARATIONS) == ("http://proethica.org/ontology/engineering-ethics", "declared IRI")


def test_extract_ontology_meta_reads_the_header_of_the_preferred_declaration(tmp_path):
    p = tmp_path / "engineering-ethics.ttl"
    p.write_text(TWO_DECLARATIONS)
    meta = OntologySyncService.__new__(OntologySyncService)._extract_ontology_meta(p)
    assert meta["iri"] == "http://proethica.org/ontology/engineering-ethics"
    assert meta["description"] == "NSPE engineering ethics ontology"
    assert meta["version"] == "3.1"
    assert "title" not in meta   # the other declaration's title is not read


def test_default_base_uri_is_the_legacy_pattern():
    assert OntologySyncService.default_base_uri("proethica-case-8") == PATTERN


def test_namespace_from_base_uri():
    assert namespace_from_base_uri(CASE_IRI) == CASE_IRI + "#"
    assert namespace_from_base_uri(PATTERN) == PATTERN
    assert namespace_from_base_uri("http://purl.obolibrary.org/obo/") == "http://purl.obolibrary.org/obo/"
    assert namespace_from_base_uri(None) is None


# --- the sync paths against a fake session -----------------------------------

class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def first(self):
        return self._value


class _FakeSession:
    """Answers the sync's two selects in order (ontology row, latest version)."""

    def __init__(self, results):
        self._results = list(results)
        self.added = []
        self.committed = False

    def execute(self, stmt):
        return _FakeResult(self._results.pop(0))

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        self.committed = True


def _sync(tmp_path, content, monkeypatch, existing=None):
    ttl = tmp_path / "proethica-case-8.ttl"
    ttl.write_text(content)
    session = _FakeSession([existing, None])
    service = OntologySyncService(session, tmp_path)
    monkeypatch.setattr(service, "_extract_and_store_entities", lambda ontology, content: 0)
    result = service._sync_single_ontology(ttl)
    return session, result


def test_create_path_sets_base_uri_from_the_declared_iri(tmp_path, monkeypatch):
    session, result = _sync(tmp_path, CASE_HEADER, monkeypatch)
    ontology = next(o for o in session.added if type(o).__name__ == "Ontology")
    assert ontology.base_uri == CASE_IRI
    assert ontology.ontology_type == "case" and ontology.source_system == "proethica"
    assert ontology.meta_data["case_number"] == "24-1"
    assert result["action"] == "updated" and session.committed


def test_create_path_falls_back_to_the_pattern_without_a_declaration(tmp_path, monkeypatch):
    session, _ = _sync(tmp_path, NO_HEADER, monkeypatch)
    ontology = next(o for o in session.added if type(o).__name__ == "Ontology")
    assert ontology.base_uri == PATTERN


def test_resync_replaces_a_pattern_valued_base_uri(tmp_path, monkeypatch):
    from web.models import Ontology
    existing = Ontology(name="proethica-case-8", base_uri=PATTERN, meta_data={})
    _sync(tmp_path, CASE_HEADER, monkeypatch, existing=existing)
    assert existing.base_uri == CASE_IRI


def test_resync_keeps_a_hand_set_base_uri(tmp_path, monkeypatch):
    from web.models import Ontology
    existing = Ontology(name="proethica-case-8", base_uri="http://example.org/custom#", meta_data={})
    _sync(tmp_path, CASE_HEADER, monkeypatch, existing=existing)
    assert existing.base_uri == "http://example.org/custom#"


@pytest.mark.parametrize("content", [CASE_HEADER, NO_HEADER])
def test_sync_parses_the_header_once_per_run(tmp_path, monkeypatch, content):
    """The create path reads the IRI from the same parse that fills the header metadata."""
    ttl = tmp_path / "proethica-case-8.ttl"
    ttl.write_text(content)
    service = OntologySyncService(_FakeSession([None, None]), tmp_path)
    calls = []
    real = service._extract_ontology_meta

    def counting(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(service, "_extract_ontology_meta", counting)
    monkeypatch.setattr(service, "_extract_and_store_entities", lambda ontology, content: 0)
    service._sync_single_ontology(ttl)
    assert len(calls) == 1
