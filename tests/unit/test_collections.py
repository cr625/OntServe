"""services.collections: the collections file, the resolution of an ontology
to its collection, the scopes and the grouping of the landing pages."""

from types import SimpleNamespace

import pytest

from services import collections as coll

# The rows of the development database before phase 1 (names, types and
# sources of the ontology listing of 2 July 2026 and the rows added up to
# October 2026), which must all stay in the ProEthica scope.
PRE_PHASE1_ROWS = [
    ('engineering-ethics', 'base', 'external'), ('proethica-intermediate', 'base', 'proethica'),
    ('Relations Ontology 2015', 'base', 'external'), ('Information Artifact Ontology 2020', 'base', 'external'),
    ('w3c-prov-o', 'upper', 'external'), ('proethica-core', 'core', 'proethica'),
    ('ASCE Code of Ethics', 'base', 'external'), ('IEEE Code of Ethics', 'base', 'external'),
    ('ASME Code of Ethics', 'base', 'external'), ('Terminological Foundations', 'base', 'external'),
    ('IFC Integration for Engineering Ethics', 'base', 'external'), ('proethica-cases', 'domain', 'proethica'),
    ('proethica-intermediate-extended', 'extracted', 'proethica'), ('bfo', 'upper', 'external'),
    ('semantic-change-ontology', 'base', 'external'), ('proethica-provenance', 'base', 'proethica'),
    ('NSPE Code of Ethics', 'base', 'external'), ('ifc-roles', 'base', 'manual'),
    ('proethica-foundation', 'base', 'manual'), ('iao', 'base', 'manual'),
    ('proethica-shapes', 'base', 'proethica'), ('proethica-case-72', 'case', 'proethica'),
]


def ont(name, otype='base', source='manual', meta=None, oid=None):
    return SimpleNamespace(name=name, ontology_type=otype, source_system=source, meta_data=meta or {}, id=oid)


@pytest.fixture(scope='module')
def config():
    return coll.get_config()


@pytest.mark.unit
class TestShippedConfig:

    def test_keys_order_and_home(self, config):
        assert [c.key for c in config.collections] == ['proethica', 'shared', 'robotics', 'physical-systems']
        assert (config.home, config.default_collection) == ('index', 'proethica')
        assert config.get('proethica').landing == 'proethica_stack'

    def test_policies(self, config):
        proethica, robotics = config.get('proethica'), config.get('robotics')
        assert proethica.case_view and proethica.embeddings and proethica.reasoning == 'proethica_merged'
        assert not robotics.case_view and not robotics.embeddings and robotics.reasoning == 'none'
        assert config.get('physical-systems').default_visibility == 'private'


@pytest.mark.unit
class TestResolve:

    @pytest.mark.parametrize('row', PRE_PHASE1_ROWS, ids=lambda r: r[0])
    def test_rows_before_phase1_stay_in_the_proethica_scope(self, config, row):
        assert coll.resolve(ont(*row), config) in coll.proethica_scope(config)

    @pytest.mark.parametrize('name, otype, expected', [
        ('proethica-case-7', 'case', 'proethica'), ('proethica-core', 'core', 'proethica'),
        ('engineering-ethics', 'base', 'proethica'), ('NSPE Code of Ethics', 'base', 'proethica'),
        ('ASCE Code of Ethics', 'base', 'proethica'), ('ifc-roles', 'base', 'proethica'),
        ('bfo', 'upper', 'shared'), ('semantic-change-ontology', 'base', 'shared'),
        ('some-upper', 'upper', 'shared'), ('mystery', 'base', None),
    ])
    def test_members_and_rules(self, config, name, otype, expected):
        assert coll.resolve(ont(name, otype), config) == expected

    def test_category_lists(self, config):
        assert coll.resolve(ont('soma', meta={'category': 'Robotics and Automation'}), config) == 'robotics'
        assert coll.resolve(ont('ps-arm', meta={'category': 'Physical Systems'}), config) == 'physical-systems'

    def test_explicit_value_wins_and_unknown_values_are_ignored(self, config):
        assert coll.resolve(ont('bfo', 'upper', meta={'collection': 'robotics'}), config) == 'robotics'
        # The phase 1 value of the robotics rows: unknown, so the category decides
        legacy = ont('dul', meta={'collection': 'robotics-and-automation', 'category': 'Robotics and Automation'})
        assert coll.resolve(legacy, config) == 'robotics'
        assert coll.resolve(ont('mystery', meta={'collection': 'nowhere'}), config) is None

    def test_default_ignores_the_explicit_value(self, config):
        row = ont('bfo', 'upper', meta={'collection': 'robotics'})
        assert coll.resolve(row, config, explicit=False) == 'shared'

    def test_row_dicts(self, config):
        row = {'id': 1, 'name': 'soma', 'ontology_type': 'base', 'source_system': 'external',
               'metadata': {'collection': 'robotics'}}
        assert coll.resolve(row, config) == 'robotics'

    def test_collection_for_category(self, config):
        assert coll.collection_for_category('Robotics and Automation', config) == 'robotics'
        assert coll.collection_for_category('Foundation', config) is None


@pytest.mark.unit
class TestScopes:

    def test_proethica_scope(self, config):
        assert coll.proethica_scope(config) == {'proethica', 'shared', None}

    def test_scope_keys(self, config):
        assert coll.scope_keys('robotics', config) == {'robotics', 'shared'}
        assert coll.scope_keys('physical-systems', config) == {'physical-systems', 'robotics', 'shared'}
        for key in ('proethica', 'shared', None):
            assert coll.scope_keys(key, config) == coll.proethica_scope(config)

    def test_ids_in_scope(self, config):
        rows = [ont('proethica-core', 'core', oid=1), ont('soma', meta={'collection': 'robotics'}, oid=2),
                ont('mystery', oid=3), ont('bfo', 'upper', oid=4)]
        assert coll.ids_in_scope(rows, coll.proethica_scope(config), config) == [1, 3, 4]
        assert coll.ids_in_scope(rows, coll.scope_keys('robotics', config), config) == [2, 4]

    def test_policy_and_embeddings(self, config):
        shared, robotics = ont('bfo', 'upper'), ont('soma', meta={'collection': 'robotics'})
        assert coll.policy_for(shared, config).key == 'proethica'
        assert coll.policy_for(ont('mystery'), config).key == 'proethica'
        assert coll.policy_for(robotics, config).key == 'robotics'
        assert coll.embeddings_allowed(shared, config) and coll.embeddings_allowed(ont('mystery'), config)
        assert not coll.embeddings_allowed(robotics, config)


@pytest.mark.unit
class TestIndexAndLanding:

    def rows(self):
        return [ont('soma', meta={'collection': 'robotics', 'subcategory': 'Activities'}),
                ont('dul', meta={'collection': 'robotics', 'subcategory': 'Upper ontologies'}),
                ont('adas-car', meta={'collection': 'robotics', 'subcategory': 'Automated driving'}),
                ont('knowrob', meta={'collection': 'robotics', 'subcategory': 'Activities'}),
                ont('pmk', meta={'collection': 'robotics'}),
                ont('bfo', 'upper', 'external'), ont('ifc-roles', 'base', 'manual'),
                ont('semantic-change-ontology', 'base', 'external'), ont('mystery')]

    def test_index_entries(self, config):
        entries = coll.index_entries(self.rows(), config=config)
        assert [(e.collection.key, e.count) for e in entries] == [('proethica', 1), ('shared', 2), ('robotics', 5)]
        assert [e.collection.key for e in coll.index_entries([], include_private=True, config=config)][-1] \
            == 'physical-systems'
        assert [o.name for o in coll.unassigned(self.rows(), config)] == ['mystery']

    def test_landing_of_one_category(self, config):
        [group] = coll.landing_groups('robotics', self.rows(), config)
        assert group.label is None
        assert [(sub, [o.name for o in rows]) for sub, rows in group.subgroups] == [
            ('Activities', ['knowrob', 'soma']), ('Automated driving', ['adas-car']),
            ('Upper ontologies', ['dul']), (None, ['pmk'])]

    def test_landing_by_category(self, config):
        groups = coll.landing_groups('shared', self.rows(), config)
        assert [g.label for g in groups] == ['Foundation', 'External Vocabularies']


@pytest.mark.unit
class TestParseConfig:

    BASE = {'collections': {'proethica': {'title': 'ProEthica'}, 'robotics': {'title': 'Robotics'}}}

    def test_minimal(self):
        cfg = coll.parse_config(self.BASE)
        assert cfg.home == 'index' and cfg.default_collection == 'proethica'
        assert cfg.get('robotics').landing == 'generic' and not cfg.get('robotics').embeddings

    @pytest.mark.parametrize('change, message', [
        ({'collections': {'robotics': {'title': 'R'}}}, 'proethica is required'),
        ({'collections': {'proethica': {'title': 'P', 'uses': ['nowhere']}}}, 'unknown collections'),
        ({'collections': {'proethica': {'title': 'P', 'members': ['bfo']}, 'shared': {'title': 'S', 'members': ['bfo']}}},
         'listed by'),
        ({'collections': {'proethica': {'title': 'P', 'landing': 'custom'}}}, 'landing'),
        ({'collections': {'proethica': {'title': 'P', 'colour': 'red'}}}, 'unknown keys'),
        ({'collections': {'Pro Ethica': {'title': 'P'}}}, 'not a slug'),
        ({'collections': {'proethica': {}}}, 'title is required'),
        ({'home': 'stack'}, 'home must be'),
        ({'default_collection': 'nowhere'}, 'default_collection'),
    ])
    def test_errors(self, change, message):
        data = {**self.BASE, **change}
        with pytest.raises(coll.CollectionsConfigError, match=message):
            coll.parse_config(data)
