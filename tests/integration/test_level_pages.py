"""The ProEthica level pages (web/level_views.py, level_*.html) and the generic
page they leave in place.

The level ontologies are seeded through the sync service from the TTL files in
ontologies/, the intermediate-extended layer and BFO from the small fixtures in
tests/fixtures/level_pages/. Other modules wipe the tables, so the seeding runs
once per module and does not rely on the startup sync.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import select

from services import proethica_stack as stack

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'level_pages'
HTML = {'Accept': 'text/html', 'User-Agent': 'Mozilla/5.0'}


@pytest.fixture(scope='module')
def seeded(app):
    from services.ontology_sync_service import OntologySyncService
    from web.models import db, Ontology
    with app.app_context():
        service = OntologySyncService(db.session, ROOT / 'ontologies')
        for name in ('proethica-core', 'proethica-intermediate', 'engineering-ethics', 'proethica-cases'):
            service._sync_single_ontology(ROOT / 'ontologies' / f'{name}.ttl', force=True)
        for name in ('proethica-intermediate-extended', 'bfo'):
            service._sync_single_ontology(FIXTURES / f'{name}.ttl', force=True)
        case = db.session.execute(select(Ontology).where(Ontology.name == 'proethica-case-7')).scalar_one_or_none()
        if case is None:
            db.session.add(Ontology(name='proethica-case-7', base_uri='http://proethica.org/ontology/case/7',
                                    ontology_type='case', source_system='proethica',
                                    meta_data={'display_name': 'Use of Artificial Intelligence in Engineering Practice'}))
        db.session.commit()
    return True


def _page(client, path):
    r = client.get(path, headers=HTML)
    assert r.status_code == 200, path
    html = r.get_data(as_text=True)
    return html[html.index('<main'):html.index('</main>')]


def _section(html, section_id):
    """From the element with this id to the end of its <section> (the level
    pages do not nest sections)."""
    start = html.index(f'id="{section_id}"')
    return html[start:html.index('</section>', start)]


@pytest.mark.integration
class TestLevelHeader:

    @pytest.mark.parametrize('level', stack.LEVELS, ids=lambda lvl: lvl.key)
    def test_header_trail_and_actions(self, client, seeded, level):
        main = _page(client, f'/ontology/{level.ontology}')
        assert f'<h1 class="mb-1">{level.label}</h1>' in main
        assert level.role in main
        assert f'<strong aria-current="page">{level.label}</strong>' in main
        for other in stack.LEVELS:
            if other is not level:
                assert f'href="/ontology/{other.ontology}">{other.label}</a>' in main
        assert f'href="/ontology/{level.ontology}?view=standard"' in main and '>Schema view</a>' in main
        assert 'text-bg-' not in main and 'badge' not in main
        for name in level.support:
            assert f'href="/ontology/{name}">{name}</a>' in main


@pytest.mark.integration
class TestIntermediate:

    def test_taxonomy(self, client, seeded):
        main = _page(client, '/ontology/proethica-intermediate')
        roles = _section(main, 'component-r')
        professional = roles.index('>Professional Role</a>')
        assert professional < roles.index('>Engineer Role</a>') < roles.index('>Civil Engineer Role</a>')
        assert 'id="component-other"' in main and '>Causal Chain</a>' in main
        assert 'id="concepts-tab"' not in main and '> Concepts' not in main

    def test_stored_display_config_is_inert(self, client, app, seeded):
        """The intermediate row of the deployed database stores a display_config
        with the old banner; the level page no longer reads it."""
        from web.models import db, Ontology
        with app.app_context():
            o = db.session.execute(select(Ontology).where(Ontology.name == 'proethica-intermediate')).scalar_one()
            saved = dict(o.meta_data or {})
            o.meta_data = {**saved, 'display_config': {
                'banner': {'title': 'ProEthica Intermediate Layer'},
                'featured_categories': [{'label': 'Roles', 'prefix': 'Role'}]}}
            db.session.commit()
        try:
            for path in ('/ontology/proethica-intermediate', '/ontology/proethica-intermediate?view=standard'):
                main = _page(client, path)
                # The Metadata tab of the Schema view prints the stored JSON as data
                rendered = re.sub(r'<pre[^>]*>.*?</pre>', '', main, flags=re.S)
                assert 'ProEthica Intermediate Layer' not in rendered and 'id="concepts-tab"' not in main
        finally:
            with app.app_context():
                o = db.session.execute(select(Ontology).where(Ontology.name == 'proethica-intermediate')).scalar_one()
                o.meta_data = saved
                db.session.commit()

    def test_schema_view(self, client, seeded):
        main = _page(client, '/ontology/proethica-intermediate?view=standard')
        assert 'Schema view' in main and '>Intermediate view</a>' in main
        assert 'id="schema-tab"' in main and 'id="properties-tab"' in main
        assert 'id="reasoning"' not in main and 'id="enrichment"' not in main
        assert 'class="badge' not in main


@pytest.mark.integration
class TestExtended:

    def test_catalog(self, client, seeded):
        main = _page(client, '/ontology/proethica-intermediate-extended')
        states = _section(main, 'component-s')
        assert '>Fixture Doubt State</a>' in states and '>Fixture Licensing State</a>' in states
        assert 'also under' in states
        assert '>Fixture Estimating Capability</a>' in _section(main, 'component-ca')
        assert 'Case 7: Use of Artificial Intelligence in Engineering Practice' in states
        assert 'and in 1 further case' in states
        assert '<details class="catalog-family">' in main

    def test_case_filter(self, client, seeded):
        main = _page(client, '/ontology/proethica-intermediate-extended?case=7')
        assert re.search(r'2 classes discovered in\s+<a href="/ontology/proethica-case-7">Case 7: ', main)
        assert '>Fixture Doubt State</a>' in main and '>Fixture Licensing State</a>' in main
        assert 'Fixture Estimating Capability' not in main and 'Fixture Neighbor Role' not in main
        assert '<details class="catalog-family" open>' in main


@pytest.mark.integration
class TestEngineeringEthics:

    def test_standards_view(self, client, seeded):
        main = _page(client, '/ontology/engineering-ethics')
        standards = _section(main, 'standards')
        assert 'ISO 26262' in standards and 'Section 508' in standards
        assert 'International Organization for Standardization' in standards
        assert 'Facts' not in standards
        structure = _section(main, 'case-structure')
        assert '>Facts</a>' in structure and '>Dissenting Section</a>' in structure
        assert 'id="vocabulary"' in main


@pytest.mark.integration
class TestCore:

    def test_grid_and_schema(self, client, seeded):
        main = _page(client, '/ontology/proethica-core')
        grid = _section(main, 'components')
        assert len(re.findall(r'class="component-letter"', grid)) == 9
        assert 'Grounded in' in grid and 'style=' not in grid
        assert '<h2 class="h4 mt-4 mb-2" id="schema">Schema</h2>' in main
        assert 'class="tab-count"' in main and 'class="badge' not in main

    def test_turtle_by_content_negotiation(self, client, seeded):
        r = client.get('/ontology/proethica-core', headers={'Accept': 'text/turtle'})
        assert r.status_code == 200 and r.mimetype == 'text/turtle'
        assert '@prefix' in r.get_data(as_text=True)


@pytest.mark.integration
class TestReferencePages:

    def test_bfo_generic_page(self, client, seeded):
        main = _page(client, '/ontology/bfo')
        assert 'ProEthica stack:' not in main and 'Schema view' not in main
        assert 'id="schema-tab"' in main
