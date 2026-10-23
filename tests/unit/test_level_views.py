"""Unit tests for the level-page builders of web.level_views, without a database.

The taxonomy tests run on rows that the sync's own extractor
(web.entity_extraction.build_entity_rows) builds from ontologies/proethica-core.ttl
and ontologies/proethica-intermediate.ttl, so primary parents are chosen as in
production. The catalog and standards tests run on stub rows.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
import rdflib

from services import proethica_stack as stack
from web.entity_extraction import build_entity_rows
from web.level_views import (catalog_from_rows, case_numbers, component_gloss, framework_grid,
                             standards_from_rows, taxonomy_from_rows)

ONTOLOGIES = Path(__file__).resolve().parents[2] / 'ontologies'
CORE = 'http://proethica.org/ontology/core#'
INT = 'http://proethica.org/ontology/intermediate#'
CASES = 'http://proethica.org/ontology/cases#'


def _rows(name):
    g = rdflib.Graph()
    g.parse(ONTOLOGIES / f'{name}.ttl', format='turtle')
    rows, _ = build_entity_rows(0, g)
    return [SimpleNamespace(uri=r.uri, label=r.label, comment=r.comment, parent_uri=r.parent_uri,
                            properties=r.properties, ontology=name)
            for r in rows if r.entity_type == 'class']


@pytest.fixture(scope='module')
def stack_rows():
    return _rows('proethica-core') + _rows('proethica-intermediate')


@pytest.fixture(scope='module')
def taxonomy(stack_rows):
    return taxonomy_from_rows(stack_rows)


def _group(taxonomy, label):
    return next(g for g in taxonomy['groups'] if g['label'] == label)


def _path_to(nodes, label, path=()):
    for node in nodes:
        here = path + (node['label'],)
        if node['label'] == label:
            return here, node
        found = _path_to(node['children'], label, here)
        if found:
            return found
    return None


def _all_labels(nodes):
    for node in nodes:
        yield node['label']
        yield from _all_labels(node['children'])


@pytest.mark.unit
class TestTaxonomy:

    def test_groups_in_tuple_order_then_other(self, taxonomy):
        labels = [g['label'] for g in taxonomy['groups']]
        assert labels[:9] == [stack.COMPONENT_LABELS[ltr] for ltr in stack.DTUPLE_ORDER]
        assert labels[9:] == ['Other']

    def test_engineer_disciplines_under_professional_role(self, taxonomy):
        path, _ = _path_to(_group(taxonomy, 'Roles')['nodes'], 'Civil Engineer Role')
        assert path == ('Professional Role', 'Engineer Role', 'Civil Engineer Role')

    def test_virtue_principles(self, taxonomy):
        path, _ = _path_to(_group(taxonomy, 'Principles')['nodes'], 'Honesty Principle')
        assert path[-2:] == ('Professional Virtue Principle', 'Honesty Principle')

    def test_multi_parent_class_listed_once_with_also_under(self, taxonomy):
        everywhere = [lab for g in taxonomy['groups'] for lab in _all_labels(g['nodes'])]
        assert everywhere.count('Public Responsibility Role') == 1
        _, node = _path_to(_group(taxonomy, 'Roles')['nodes'], 'Public Responsibility Role')
        assert 'Relational Role' in [a['label'] for a in node['also_under']]

    def test_deprecated_classes_left_out(self, stack_rows, taxonomy):
        deprecated = {r.label for r in stack_rows if r.ontology == 'proethica-intermediate'
                      and str((r.properties or {}).get('deprecated', '')).lower() == 'true'}
        assert deprecated
        everywhere = {lab for g in taxonomy['groups'] for lab in _all_labels(g['nodes'])}
        assert not deprecated & everywhere

    def test_action_and_event_point_to_core(self, taxonomy):
        action, event = _group(taxonomy, 'Actions'), _group(taxonomy, 'Events')
        assert action['nodes'] == [] and action['component']['uri'] == CORE + 'Action'
        assert event['nodes'] == []
        assert {k['uri'] for k in event['core_kinds']} >= {CORE + 'ExogenousEvent', CORE + 'AutomaticEvent'}

    def test_other_holds_the_classes_outside_the_components(self, taxonomy):
        other = {n['label'] for n in _group(taxonomy, 'Other')['nodes']}
        assert {'Causal Chain', 'Temporal Relation'} <= other

    def test_counts_cover_every_live_class(self, stack_rows, taxonomy):
        live = [r for r in stack_rows if r.ontology == 'proethica-intermediate'
                and str((r.properties or {}).get('deprecated', '')).lower() != 'true']
        assert taxonomy['total'] == len(live) == sum(g['count'] for g in taxonomy['groups'])


def test_primary_parent_cycle_keeps_its_classes():
    rows = [
        SimpleNamespace(uri=CORE + 'Role', label='Role', comment=None, parent_uri=None,
                        properties={'dtupleComponent': 'R'}, ontology='proethica-core'),
        SimpleNamespace(uri=INT + 'A', label='A', comment=None, parent_uri=INT + 'B',
                        properties={}, ontology='proethica-intermediate'),
        SimpleNamespace(uri=INT + 'B', label='B', comment=None, parent_uri=INT + 'A',
                        properties={}, ontology='proethica-intermediate'),
    ]
    view = taxonomy_from_rows(rows)
    labels = {lab for g in view['groups'] for lab in _all_labels(g['nodes'])}
    assert labels == {'A', 'B'}
    assert view['total'] == 2 == sum(g['count'] for g in view['groups'])


@pytest.mark.unit
class TestFrameworkGrid:

    def test_nine_components_in_order_with_grounding(self, stack_rows):
        grid = framework_grid([r for r in stack_rows if r.ontology == 'proethica-core'])
        assert [c['letter'] for c in grid] == list(stack.DTUPLE_ORDER)
        role = grid[0]
        assert role['fragment'] == 'Role' and role['grounding_label'] == 'BFO role'

    def test_grid_shows_the_gloss_without_the_component_phrase(self, stack_rows):
        grid = framework_grid([r for r in stack_rows if r.ontology == 'proethica-core'])
        assert grid[0]['gloss'].startswith('A position or standing borne by an agent')
        for c in grid:
            assert 'component of' not in c['gloss'] and c['gloss'].endswith('.'), c['letter']
            assert not c['gloss'].endswith('...'), c['letter']   # a whole gloss, not a cut definition

    def test_gloss_falls_back_to_the_cut_definition(self):
        row = SimpleNamespace(comment='x' * 200, properties={})
        assert component_gloss(row) == 'x' * 150 + '...'
        row = SimpleNamespace(comment='Long definition.', properties={
            'comment': 'A short gloss; the R component of D=(R,P,O,S,Rs,A,E,Ca,Cs).'})
        assert component_gloss(row) == 'A short gloss.'


def _cls(uri, parent, ontology, **props):
    return SimpleNamespace(uri=uri, label=uri.rsplit('#', 1)[-1], comment=None, parent_uri=parent,
                           properties=props, ontology=ontology)


CORE_ROWS = [
    _cls(CORE + 'Role', 'http://purl.obolibrary.org/obo/BFO_0000023', 'proethica-core', dtupleComponent='R'),
    _cls(CORE + 'State', 'http://purl.obolibrary.org/obo/BFO_0000020', 'proethica-core', dtupleComponent='S'),
    _cls(CORE + 'Capability', 'http://purl.obolibrary.org/obo/BFO_0000016', 'proethica-core', dtupleComponent='Ca'),
    _cls(CORE + 'Resource', 'http://purl.obolibrary.org/obo/IAO_0000030', 'proethica-core', dtupleComponent='Rs'),
    _cls(INT + 'EpistemicState', CORE + 'State', 'proethica-intermediate'),
    _cls(INT + 'RegulatoryState', CORE + 'State', 'proethica-intermediate'),
    _cls(INT + 'TechnicalStandard', CORE + 'Resource', 'proethica-intermediate'),
    _cls(INT + 'LegalResource', CORE + 'Resource', 'proethica-intermediate'),
]


@pytest.mark.unit
class TestCatalog:

    ROWS = CORE_ROWS + [
        _cls(INT + 'DoubtState', INT + 'EpistemicState', 'proethica-intermediate-extended',
             discoveredInCase=7, firstDiscoveredInCase=7, sourceText='unsure'),
        _cls(INT + 'LicensingState', INT + 'RegulatoryState', 'proethica-intermediate-extended',
             rdf_superclasses=[INT + 'RegulatoryState', INT + 'EpistemicState'],
             discoveredInCase=[7, 8], firstDiscoveredInCase=8),
        _cls(INT + 'EstimatingCapability', CORE + 'Capability', 'proethica-intermediate-extended',
             discoveredInCase=72, firstDiscoveredInCase=72),
        _cls(INT + 'OldState', INT + 'EpistemicState', 'proethica-intermediate-extended',
             deprecated=True, discoveredInCase=7),
    ]

    def test_groups_by_component_then_primary_parent(self):
        catalog = catalog_from_rows(self.ROWS, titles={7: 'Case seven'})
        groups = {g['label']: g for g in catalog['groups']}
        assert list(groups) == ['States', 'Capabilities']
        families = {f['parent']['label']: [e['label'] for e in f['entries']] for f in groups['States']['families']}
        assert families == {'EpistemicState': ['DoubtState'], 'RegulatoryState': ['LicensingState']}
        licensing = groups['States']['families'][1]['entries'][0]
        assert [a['label'] for a in licensing['also_under']] == ['EpistemicState']
        assert licensing['first']['num'] == 8 and licensing['further'] == 1
        doubt = groups['States']['families'][0]['entries'][0]
        assert doubt['first'] == {'num': 7, 'title': 'Case seven', 'name': 'proethica-case-7'}
        assert catalog['total'] == 3 and catalog['case_count'] == 3

    def test_class_on_a_core_component_joins_its_group(self):
        groups = {g['label']: g for g in catalog_from_rows(self.ROWS)['groups']}
        family = groups['Capabilities']['families'][0]
        assert family['parent']['uri'] == CORE + 'Capability'
        assert [e['label'] for e in family['entries']] == ['EstimatingCapability']

    def test_case_filter_matches_integer_and_list(self):
        assert catalog_from_rows(self.ROWS, case=7)['total'] == 2
        assert catalog_from_rows(self.ROWS, case=8)['total'] == 1
        assert catalog_from_rows(self.ROWS, case=99)['groups'] == []

    def test_case_numbers(self):
        assert case_numbers({'discoveredInCase': [13, 91, 162], 'firstDiscoveredInCase': 162}) == (162, [162, 13, 91])
        assert case_numbers({'discoveredincase': '7'}) == (None, [7])
        assert case_numbers({}) == (None, [])


@pytest.mark.unit
class TestStandards:

    def test_standards_vocabulary_and_case_structure(self):
        classes = CORE_ROWS + [
            _cls('http://proethica.org/ontology/engineering_ethics#ComplyWithSafetyStandards',
                 CORE + 'State', 'engineering-ethics'),
            _cls('http://proethica.org/ontology/engineering_ethics#DissentingSection',
                 CASES + 'SectionType', 'engineering-ethics'),
        ]
        individuals = [
            SimpleNamespace(uri='urn:x#ISO26262', label='ISO 26262', comment=None,
                            parent_uri=INT + 'TechnicalStandard',
                            properties={'identifier': 'ISO 26262:2018', 'source': 'https://www.iso.org/standard/68383.html',
                                        'applicableDomains': ['automotive_engineering']}),
            SimpleNamespace(uri='urn:x#Section508', label='Section 508', comment=None,
                            parent_uri=INT + 'LegalResource', properties={}),
            SimpleNamespace(uri='urn:x#NSPEFacts', label='Facts', comment=None,
                            parent_uri=CASES + 'CaseSection', properties={'sectionOrder': 1}),
        ]
        individuals[1].properties = {'source': 'javascript:alert(1)'}
        view = standards_from_rows(classes, individuals)
        assert [s['label'] for s in view['standards']] == ['ISO 26262', 'Section 508']
        iso, section508 = view['standards']
        assert iso['source_host'] == 'iso.org' and iso['domains'] == ['automotive engineering']
        assert iso['source_url'] == 'https://www.iso.org/standard/68383.html'
        assert section508['source_url'] is None   # only http(s) sources become links
        assert [i['label'] for i in view['structure_individuals']] == ['Facts']
        assert [c['label'] for c in view['structure_classes']] == ['DissentingSection']
        assert [(g['label'], len(g['classes'])) for g in view['vocabulary']] == [('States', 1)]
