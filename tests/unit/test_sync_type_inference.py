"""Unit tests for OntologySyncService._infer_type_and_source.

Locks the auto-registration metadata contract: the sync service is the live
registrar for ProEthica case commits, so per-case ontologies must be created
as ontology_type='case' / source_system='proethica' instead of falling
through to the column defaults 'base'/'manual' (which hides them from the
Type=case filter and mislabels them as hand-authored).
"""
from services.ontology_sync_service import OntologySyncService


def test_case_ontology_names_infer_case_proethica():
    assert OntologySyncService._infer_type_and_source('proethica-case-7') == ('case', 'proethica')
    assert OntologySyncService._infer_type_and_source('proethica-case-121') == ('case', 'proethica')


def test_other_proethica_stack_names_infer_proethica_source():
    assert OntologySyncService._infer_type_and_source('proethica-foundation') == ('base', 'proethica')
    assert OntologySyncService._infer_type_and_source('proethica-cases') == ('base', 'proethica')


def test_non_proethica_names_keep_defaults():
    assert OntologySyncService._infer_type_and_source('iao') == ('base', 'manual')
    assert OntologySyncService._infer_type_and_source('ifc-roles') == ('base', 'manual')


def test_case_pattern_requires_numeric_suffix():
    assert OntologySyncService._infer_type_and_source('proethica-case-abc') == ('base', 'proethica')
    assert OntologySyncService._infer_type_and_source('proethica-case-7x') == ('base', 'proethica')
