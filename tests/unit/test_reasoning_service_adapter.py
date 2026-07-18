"""Unit tests for the read-only reasoning adapter (editor Run Inference)."""

import pytest

import servers.reasoning_tools as rt
from editor.reasoning_service import ReasoningRequest, execute_reasoning


def _loader(name):
    return '@prefix : <http://example.org/> .'


def _detail(**over):
    base = {
        'ontology_name': 'proethica-intermediate',
        'consistent': True,
        'inferred_subclasses': [{'child': 'http://x#A', 'parent': 'http://x#B'}],
        'inferred_types': [{'individual': 'http://x#i', 'type': 'http://x#A'}],
        'nothing_entities': [],
        'inferred_subclass_count': 1,
        'inferred_type_count': 1,
        'truncated': False,
        'error': None,
    }
    base.update(over)
    return base


class TestExecuteReasoning:

    def test_consistent_run_maps_fields(self, monkeypatch):
        monkeypatch.setattr(rt, 'reason_detailed', lambda name, content=None: _detail())
        r = execute_reasoning(ReasoningRequest('proethica-intermediate'), _content_loader=_loader)
        assert r.success and r.consistent
        assert r.inferred_subclass_count == 1
        assert r.inferred_subclasses[0]['child'] == 'http://x#A'
        assert 'consistent' in r.message

    def test_inconsistent_is_successful_run(self, monkeypatch):
        monkeypatch.setattr(rt, 'reason_detailed', lambda name, content=None: _detail(
            consistent=False, error='OwlReadyInconsistentOntologyError',
            error_explanation='clash', inferred_subclasses=[], inferred_types=[],
            inferred_subclass_count=0, inferred_type_count=0))
        r = execute_reasoning(ReasoningRequest('x'), _content_loader=_loader)
        assert r.success and not r.consistent
        assert 'INCONSISTENT' in r.message

    def test_infrastructure_error_fails(self, monkeypatch):
        monkeypatch.setattr(rt, 'reason_detailed', lambda name, content=None: _detail(
            consistent=False, error='reason-failed: OSError: java not found'))
        r = execute_reasoning(ReasoningRequest('x'), _content_loader=_loader)
        assert not r.success
        assert 'java' in r.error

    def test_missing_ontology(self):
        def loader(name):
            raise LookupError(f'Ontology {name} not found')
        r = execute_reasoning(ReasoningRequest('nope'), _content_loader=loader)
        assert not r.success and r.error == 'not-found'

    def test_response_dict_shape(self, monkeypatch):
        monkeypatch.setattr(rt, 'reason_detailed', lambda name, content=None: _detail())
        d = execute_reasoning(ReasoningRequest('x'), _content_loader=_loader).to_response_dict()
        for key in ('success', 'consistent', 'inferred_subclasses', 'inferred_types',
                    'nothing_entities', 'inferred_subclass_count', 'truncated'):
            assert key in d
