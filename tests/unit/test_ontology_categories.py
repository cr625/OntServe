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
        assert r.rule_category == 'Cases'   # what the settings page shows as the default

    def test_rule_category_for_unmatched(self):
        assert cat.resolve(ont('something', 'base', 'manual')).rule_category == cat.UNCATEGORIZED.key

    def test_case_id_from_name(self):
        assert cat.case_id_from_name('proethica-case-102') == '102'
        assert cat.case_id_from_name('proethica-cases') is None
        assert cat.case_id_from_name('proethica-case-7x') is None
        assert cat.case_id_from_name(None) is None

    def test_set_explicit_blank_clears(self):
        md = {'category': 'X', 'other': 1}
        cat.set_explicit(md, 'category', '   ')
        cat.set_explicit(md, 'subcategory', ' 1990s ')
        cat.set_explicit(md, 'case_number', None)
        assert md == {'other': 1, 'subcategory': '1990s'}

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
        assert keys == ['Foundation', 'ProEthica Framework', 'Cases', 'Domain', 'Professional Codes',
                        'Sandbox', cat.UNCATEGORIZED.key]

    def test_family_sections(self):
        """ProEthica Framework and Cases fold into one ProEthica section at the
        position of the first; everything else is a section of its own."""
        sections = cat.group_by_family(cat.group_ontologies(self._corpus()))
        keys = [(s.family.key if s.family else None, [g.key for g in s.groups]) for s in sections]
        assert keys == [
            (None, ['Foundation']),
            ('ProEthica', ['ProEthica Framework', 'Cases']),
            (None, ['Domain']),
            (None, ['Professional Codes']),
            (None, ['Sandbox']),
            (None, [cat.UNCATEGORIZED.key]),
        ]
        proethica = sections[1]
        assert proethica.count == 1 + 16 and proethica.key == 'ProEthica'
        assert [g.category.section_label for g in proethica.groups] == ['Framework', 'Cases']
        assert cat.category_info('Cases').label == 'ProEthica Cases'

    def test_family_section_appears_even_with_one_member(self):
        groups = cat.group_ontologies([ont('proethica-case-1', 'case', 'proethica')])
        sections = cat.group_by_family(groups)
        assert len(sections) == 1 and sections[0].family.key == 'ProEthica'
        assert [g.key for g in sections[0].groups] == ['Cases']

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


@pytest.mark.unit
class TestFamilyContract:
    """group_by_family on synthetic groups, independent of the real catalog."""

    @staticmethod
    def _g(key, family=None):
        return cat.Group(category=cat.Category(key, key, 'bi-x', 'secondary', family=family, short_label=key))

    def test_section_anchored_at_first_member_and_keeps_input_order(self):
        groups = [self._g('A', 'ProEthica'), self._g('B'), self._g('C', 'ProEthica'), self._g('D')]
        sections = cat.group_by_family(groups)
        assert [(s.family.key if s.family else None, [g.key for g in s.groups]) for s in sections] == [
            ('ProEthica', ['A', 'C']), (None, ['B']), (None, ['D'])]

    def test_unknown_family_key_falls_back_to_standalone(self):
        sections = cat.group_by_family([self._g('X', 'NoSuchFamily'), self._g('Y')])
        assert [s.family for s in sections] == [None, None]
        assert [s.key for s in sections] == ['X', 'Y']

    def test_empty_corpus_has_no_sections(self):
        assert cat.group_by_family([]) == []
        assert [(s.family, [g.key for g in s.groups])
                for s in cat.group_by_family(cat.group_ontologies([ont('bfo', 'upper', 'external')]))] == [(None, ['Foundation'])]

    def test_counts_and_labels(self):
        sections = cat.group_by_family([self._g('A', 'ProEthica'), self._g('C', 'ProEthica')])
        assert sections[0].count == 0 and sections[0].key == 'ProEthica'
        assert cat.category_info('Foundation').section_label == 'Foundation'
        assert cat.category_info('Sandbox').section_label == 'Sandbox'

    def test_catalog_invariants(self):
        """Every Category.family names a declared Family, every Family has members,
        and every family member carries a short_label for its nested heading."""
        assert {c.family for c in cat.CATEGORIES if c.family} <= set(cat.FAMILY_BY_KEY)
        for f in cat.FAMILIES:
            assert any(c.family == f.key for c in cat.CATEGORIES), f.key
        for c in cat.CATEGORIES:
            if c.family:
                assert c.short_label, c.key
