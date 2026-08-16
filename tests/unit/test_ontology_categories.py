"""Unit tests for services.ontology_categories (pure functions, no DB)."""

from types import SimpleNamespace

import pytest

from services import ontology_categories as cat


def ont(name, otype='base', source='manual', meta=None):
    return SimpleNamespace(name=name, ontology_type=otype, source_system=source, meta_data=meta or {})


@pytest.mark.unit
class TestResolve:

    def test_case_rule(self):
        r = cat.resolve(ont('proethica-case-7', 'case', 'proethica'))
        assert (r.category, r.subcategory, r.explicit) == ('Cases', None, False)

    def test_upper_is_foundation_regardless_of_source(self):
        assert cat.resolve(ont('bfo', 'upper', 'external')).category == 'Foundation'
        assert cat.resolve(ont('proethica-foundation', 'upper', 'proethica')).category == 'Foundation'

    def test_proethica_framework(self):
        for name in ('proethica-core', 'proethica-intermediate', 'proethica-shapes'):
            assert cat.resolve(ont(name, 'base', 'proethica')).category == 'ProEthica Framework'

    def test_domain(self):
        assert cat.resolve(ont('engineering-ethics', 'domain', 'proethica')).category == 'Domain'

    def test_professional_codes_by_name(self):
        assert cat.resolve(ont('NSPE Code of Ethics', 'base', 'external')).category == 'Professional Codes'
        assert cat.resolve(ont('ifc-roles', 'base', 'external')).category == 'External Vocabularies'

    def test_unmatched_is_uncategorized(self):
        assert cat.resolve(ont('something', 'base', 'manual')).category == cat.UNCATEGORIZED.key

    def test_explicit_category_wins(self):
        r = cat.resolve(ont('proethica-case-7', 'case', 'proethica', {'category': 'Teaching Set'}))
        assert r.category == 'Teaching Set' and r.explicit

    def test_explicit_subcategory_kept_with_rule_category(self):
        r = cat.resolve(ont('proethica-case-7', 'case', 'proethica', {'subcategory': '2020s'}))
        assert (r.category, r.subcategory) == ('Cases', '2020s')

    def test_blank_metadata_values_ignored(self):
        r = cat.resolve(ont('proethica-case-7', 'case', 'proethica', {'category': '  ', 'subcategory': ''}))
        assert (r.category, r.subcategory, r.explicit) == ('Cases', None, False)

    def test_accepts_dicts(self):
        r = cat.resolve({'name': 'bfo', 'ontology_type': 'upper', 'source_system': 'external', 'metadata': {}})
        assert r.category == 'Foundation'


@pytest.mark.unit
class TestGrouping:

    def _corpus(self, n_cases=15):
        base = [
            ont('bfo', 'upper', 'external'),
            ont('proethica-core', 'core', 'proethica'),
            ont('engineering-ethics', 'domain', 'proethica'),
            ont('NSPE Code of Ethics', 'base', 'external'),
            ont('mystery', 'base', 'manual'),
            ont('proethica-core-x', 'base', 'proethica', {'category': 'Sandbox'}),
        ]
        cases = [ont(f'proethica-case-{i}', 'case', 'proethica',
                     {'subcategory': '2020s' if i % 2 else '1990s'}) for i in range(n_cases)]
        cases.append(ont('proethica-case-999', 'case', 'proethica'))  # no subcategory
        return base + cases

    def test_catalog_order_then_custom_then_uncategorized(self):
        keys = [g.key for g in cat.group_ontologies(self._corpus())]
        assert keys == ['Foundation', 'ProEthica Framework', 'Domain', 'Professional Codes',
                        'Cases', 'Sandbox', cat.UNCATEGORIZED.key]

    def test_collapse_threshold(self):
        groups = {g.key: g for g in cat.group_ontologies(self._corpus(), collapse_threshold=12)}
        assert groups['Cases'].collapsed is True
        assert groups['Foundation'].collapsed is False
        groups = {g.key: g for g in cat.group_ontologies(self._corpus(), collapse_threshold=100)}
        assert groups['Cases'].collapsed is False

    def test_subgroups_sorted_with_unlabelled_last(self):
        groups = {g.key: g for g in cat.group_ontologies(self._corpus(16))}
        assert groups['Cases'].subgroups == [('1990s', 8), ('2020s', 8), (None, 1)]
        assert groups['Cases'].count == 17

    def test_matches_filter(self):
        o = ont('proethica-case-1', 'case', 'proethica', {'subcategory': '2020s'})
        assert cat.matches(o, 'Cases', None)
        assert cat.matches(o, 'Cases', '2020s')
        assert not cat.matches(o, 'Cases', '1990s')
        assert not cat.matches(o, 'Foundation', None)

    def test_category_info_for_unknown_key(self):
        info = cat.category_info('Sandbox')
        assert info.key == info.label == 'Sandbox' and info.icon
