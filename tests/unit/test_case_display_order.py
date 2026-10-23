"""Unit tests for build_ordered_blocks and the case-page view helpers
(web/case_display.py).

Guards the single-source-of-truth ordering that keeps the case-view sidebar nav
and body in lockstep, the three parts of the page, the sections loaded on
demand, and the de-duplication of the YAML conclusions section against the
richer conclusions panel.
"""
from types import SimpleNamespace

from web.case_display import (build_case_summary, build_ordered_blocks, group_blocks,
                              section_type_counts)


def _section(sid, n=1, title=None, collapsed=False):
    return {'id': sid, 'title': title or sid.title(), 'collapsed': collapsed,
            'icon': 'bi-x', 'entities': [object()] * n, 'subsections': None}


def test_panels_interleave_with_sections_in_canonical_order():
    sections = [_section('nine_concepts'), _section('decision_points'),
                _section('questions'), _section('other')]
    # count comes from competing_count (competing obligations), not
    # len(clusters): lineage-only clusters must not inflate the nav count.
    competition = {'has_edges': True, 'clusters': [1, 2, 3], 'competing_count': 2}
    citations = {'has_citations': True, 'provision_count': 3}
    conclusions = {'has_conclusions': True, 'count': 4}

    blocks = build_ordered_blocks(sections, competition, citations, conclusions)
    ids = [b['id'] for b in blocks]

    assert ids == ['nine_concepts', 'competition', 'other',
                   'decision_points', 'questions', 'conclusions', 'citations']
    # Panel counts come from the panel models, section counts from entities.
    by_id = {b['id']: b for b in blocks}
    assert by_id['competition']['count'] == 2
    assert by_id['citations']['count'] == 3
    assert by_id['conclusions']['count'] == 4
    assert by_id['conclusions']['kind'] == 'panel'


def test_parts_and_deferred_sections():
    sections = [_section('agents'), _section('nine_concepts'), _section('decision_points'),
                _section('analysis', collapsed=True), _section('support', collapsed=True),
                _section('other', collapsed=True)]
    blocks = build_ordered_blocks(sections)
    assert [(b['id'], b['part']) for b in blocks] == [
        ('agents', 'entities'), ('nine_concepts', 'entities'), ('other', 'entities'),
        ('decision_points', 'analysis'), ('analysis', 'analysis'), ('support', 'provenance')]
    assert {b['id'] for b in blocks if b['deferred']} == {'analysis', 'support', 'other'}
    parts = group_blocks(blocks)
    assert [(p['key'], p['title'], [b['id'] for b in p['blocks']]) for p in parts] == [
        ('entities', 'Case entities', ['agents', 'nine_concepts', 'other']),
        ('analysis', 'Analysis record', ['decision_points', 'analysis']),
        ('provenance', 'Provenance and support', ['support'])]


def test_yaml_conclusions_section_dropped_when_panel_present():
    # A YAML 'conclusions' section must not produce a second Conclusions block.
    sections = [_section('nine_concepts'), _section('conclusions', n=5)]
    conclusions = {'has_conclusions': True, 'count': 4}

    blocks = build_ordered_blocks(sections, conclusions=conclusions)
    conclusion_blocks = [b for b in blocks if b['id'] == 'conclusions']

    assert len(conclusion_blocks) == 1
    assert conclusion_blocks[0]['kind'] == 'panel'
    assert conclusion_blocks[0]['count'] == 4  # panel count, not the 5 entities


def test_empty_panels_and_sections_omitted():
    sections = [_section('nine_concepts'), _section('questions', n=0)]
    blocks = build_ordered_blocks(sections, competition={'has_edges': False, 'clusters': []})
    ids = [b['id'] for b in blocks]

    assert ids == ['nine_concepts']  # zero-count section and absent panels gone
    assert [p['key'] for p in group_blocks(blocks)] == ['entities']


def test_unlisted_sections_join_the_case_entities():
    sections = [_section('nine_concepts'), _section('mystery'), _section('other')]
    ids = [b['id'] for b in build_ordered_blocks(sections)]
    assert ids == ['nine_concepts', 'mystery', 'other']

    # Without an "other" block they follow the last entity block, not the analysis record
    blocks = build_ordered_blocks([_section('nine_concepts'), _section('mystery'), _section('questions')])
    assert [(b['id'], b['part']) for b in blocks] == [
        ('nine_concepts', 'entities'), ('mystery', 'entities'), ('questions', 'analysis')]


def test_case_summary_omits_zero_counts():
    blocks = build_ordered_blocks(
        [_section('decision_points', n=6), _section('questions', n=1)],
        competition={'has_edges': True, 'competing_count': 0},
        citations={'has_citations': True, 'provision_count': 9})
    summary = build_case_summary({'individuals': 203}, blocks)
    assert [(s['count'], s['label'], s['anchor']) for s in summary] == [
        (203, 'named individuals', 'part-entities'),
        (6, 'decision points', 'section-decision_points'),
        (1, 'question', 'section-questions'),
        (9, 'cited provisions', 'section-citations')]


def test_section_type_counts():
    def row(parent, etype='individual'):
        return SimpleNamespace(parent_uri=parent, entity_type=etype)
    prov = 'http://www.w3.org/ns/prov#Derivation'
    section = {'entities': [row(prov), row(prov), row('http://www.w3.org/2006/time#Instant'),
                            row(None, 'property')]}
    counts = section_type_counts(section, limit=2)
    assert counts[0] == {'label': 'Derivation', 'count': 2}
    assert counts[-1] == {'label': None, 'count': 1}
    assert sum(c['count'] for c in counts) == 4
