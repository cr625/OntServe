"""Unit tests for build_ordered_blocks (web/case_display.py).

Guards the single-source-of-truth ordering that keeps the case-view sidebar nav
and body in lockstep, and the de-duplication of the YAML conclusions section
against the richer conclusions panel.
"""
from web.case_display import build_ordered_blocks


def _section(sid, n=1, title=None):
    return {'id': sid, 'title': title or sid.title(),
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

    assert ids == ['nine_concepts', 'competition', 'citations',
                   'decision_points', 'questions', 'conclusions', 'other']
    # Panel counts come from the panel models, section counts from entities.
    by_id = {b['id']: b for b in blocks}
    assert by_id['competition']['count'] == 2
    assert by_id['citations']['count'] == 3
    assert by_id['conclusions']['count'] == 4
    assert by_id['conclusions']['kind'] == 'panel'


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


def test_unlisted_sections_appended_before_other():
    sections = [_section('nine_concepts'), _section('mystery'), _section('other')]
    blocks = build_ordered_blocks(sections)
    ids = [b['id'] for b in blocks]

    assert ids == ['nine_concepts', 'mystery', 'other']
    assert ids.index('mystery') < ids.index('other')
