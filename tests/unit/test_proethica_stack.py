"""Unit tests for services.proethica_stack and the class index of web.level_views
(pure functions over stubs, no DB)."""

from types import SimpleNamespace

import pytest

from services import proethica_stack as stack
from web.level_views import ClassIndex, is_deprecated, is_standard

CORE = 'http://proethica.org/ontology/core#'
INT = 'http://proethica.org/ontology/intermediate#'
BFO_ROLE = 'http://purl.obolibrary.org/obo/BFO_0000023'


def ont(name, otype='base', source='manual', meta=None, description=''):
    return SimpleNamespace(name=name, ontology_type=otype, source_system=source,
                           meta_data=meta or {}, description=description)


def cls(uri, parent=None, **props):
    return SimpleNamespace(uri=uri, parent_uri=parent, properties=props)


# The non-case rows of the repository on 2026-10-23, with their stored types.
REPOSITORY = [
    ont('ASCE Code of Ethics', 'base', 'external'),
    ont('ASME Code of Ethics', 'base', 'external'),
    ont('bfo', 'upper', 'external'),
    ont('engineering-ethics', 'domain', 'proethica'),
    ont('iao', 'upper', 'external'),
    ont('IEEE Code of Ethics', 'base', 'external'),
    ont('ifc-roles', 'base', 'external'),
    ont('NSPE Code of Ethics', 'base', 'external'),
    ont('proethica-cases', 'base', 'proethica'),
    ont('proethica-core', 'core', 'proethica'),
    ont('proethica-foundation', 'upper', 'proethica'),
    ont('proethica-intermediate', 'base', 'proethica'),
    ont('proethica-intermediate-extended', 'extracted', 'proethica'),
    ont('proethica-provenance', 'base', 'proethica'),
    ont('proethica-shapes', 'base', 'proethica'),
    ont('Relations Ontology 2015', 'upper', 'external'),
    ont('semantic-change-ontology', 'base', 'external'),
    ont('w3c-prov-o', 'upper', 'external'),
]
CASES = [ont(f'proethica-case-{i}', 'case', 'proethica', {'subcategory': '2020s'}) for i in (7, 8, 72)]


@pytest.mark.unit
class TestStackTable:

    def test_levels_in_stack_order(self):
        assert [lvl.ontology for lvl in stack.LEVELS] == [
            'proethica-core', 'proethica-intermediate', 'proethica-intermediate-extended',
            'engineering-ethics']
        assert [lvl.view for lvl in stack.LEVELS] == list(stack.VIEWS)

    def test_no_ontology_named_twice(self):
        names = [lvl.ontology for lvl in stack.LEVELS] + list(stack.SUPPORT_NAMES)
        names += [stack.CASES_VOCABULARY, stack.CASES_CODE]
        assert len(names) == len(set(names))

    def test_level_for(self):
        assert stack.level_for('proethica-intermediate').key == 'intermediate'
        assert stack.level_for('proethica-cases') is None
        assert stack.level_for(None) is None

    def test_dtuple_order(self):
        assert stack.DTUPLE_ORDER == ('R', 'P', 'O', 'S', 'Rs', 'A', 'E', 'Ca', 'Cs')


@pytest.mark.unit
class TestPartition:

    def test_every_ontology_once(self):
        part = stack.partition(REPOSITORY + CASES)
        placed = [o for _, o in part.levels if o] + part.cases + [part.vocabulary, part.code]
        placed += [o for g in part.reference for o in g.ontologies]
        assert sorted(o.name for o in placed) == sorted(o.name for o in REPOSITORY + CASES)
        assert part.reference_count == len(REPOSITORY) - 6

    def test_regions(self):
        part = stack.partition(REPOSITORY + CASES)
        assert [(lvl.key, o.name) for lvl, o in part.levels] == [
            ('core', 'proethica-core'), ('intermediate', 'proethica-intermediate'),
            ('extended', 'proethica-intermediate-extended'),
            ('engineering-ethics', 'engineering-ethics')]
        assert part.vocabulary.name == 'proethica-cases'
        assert part.code.name == 'NSPE Code of Ethics'
        assert [o.name for o in part.cases] == ['proethica-case-7', 'proethica-case-8', 'proethica-case-72']

    def test_reference_groups(self):
        part = stack.partition(REPOSITORY + CASES)
        groups = {g.label: [o.name for o in g.ontologies] for g in part.reference}
        # The support group comes first, in stack order, even though
        # proethica-foundation would otherwise resolve to Foundation.
        assert part.reference[0].label == stack.SUPPORT_GROUP_LABEL
        assert groups[stack.SUPPORT_GROUP_LABEL] == [
            'proethica-foundation', 'proethica-shapes', 'proethica-provenance']
        assert groups['Foundation'] == ['bfo', 'iao', 'Relations Ontology 2015', 'w3c-prov-o']
        assert groups['Professional Codes'] == [
            'ASCE Code of Ethics', 'ASME Code of Ethics', 'IEEE Code of Ethics']
        assert groups['External Vocabularies'] == ['ifc-roles', 'semantic-change-ontology']

    def test_missing_level_rows(self):
        part = stack.partition([ont('bfo', 'upper', 'external')])
        assert [o for _, o in part.levels] == [None] * len(stack.LEVELS)
        assert part.vocabulary is None and part.code is None and part.cases == []
        assert [g.label for g in part.reference] == ['Foundation']


@pytest.mark.unit
class TestClassIndex:

    def _index(self):
        return ClassIndex([
            cls(CORE + 'Role', BFO_ROLE, dtupleComponent='R'),
            cls(CORE + 'Resource', 'http://purl.obolibrary.org/obo/IAO_0000030', dtupleComponent='Rs'),
            cls(CORE + 'Guideline', CORE + 'Resource',
                rdf_superclasses=[CORE + 'Resource', 'http://purl.obolibrary.org/obo/IAO_0000310']),
            cls(CORE + 'Agent', 'http://purl.obolibrary.org/obo/BFO_0000040'),
            cls(INT + 'ProfessionalRole', CORE + 'Role'),
            cls(INT + 'EngineerRole', INT + 'ProfessionalRole'),
            cls(INT + 'TechnicalStandard', CORE + 'Resource'),
            cls(INT + 'EthicalCode', CORE + 'Guideline'),
            cls(INT + 'PublicInterest', CORE + 'Agent'),
            # A second declaration of core:Role elsewhere, without the annotation
            cls(CORE + 'Role', BFO_ROLE),
        ])

    def test_nearest_component(self):
        index = self._index()
        assert index.component(INT + 'EngineerRole') == CORE + 'Role'
        assert index.letter(INT + 'EngineerRole') == 'R'
        assert index.component(CORE + 'Role') == CORE + 'Role'
        assert index.letter(INT + 'EthicalCode') == 'Rs'

    def test_outside_the_components(self):
        index = self._index()
        assert index.component(INT + 'PublicInterest') is None
        assert index.component('http://example.org/unknown') is None

    def test_redeclared_class_keeps_its_letter(self):
        assert self._index().letters[CORE + 'Role'] == 'R'

    def test_standard_is_a_kind_of_resource(self):
        index = self._index()
        standard = SimpleNamespace(parent_uri=INT + 'TechnicalStandard', properties={})
        section = SimpleNamespace(parent_uri='http://proethica.org/ontology/cases#CaseSection', properties={})
        multi = SimpleNamespace(parent_uri=INT + 'PublicInterest',
                                properties={'rdf_types': [INT + 'PublicInterest', INT + 'TechnicalStandard']})
        assert is_standard(standard, index)
        assert not is_standard(section, index)
        assert is_standard(multi, index)

    def test_deprecated_flag(self):
        assert is_deprecated(cls('x', deprecated=True))
        assert is_deprecated(cls('x', deprecated='true'))
        assert not is_deprecated(cls('x'))
