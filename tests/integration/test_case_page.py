"""The redesigned case page (ontology_case.html) and the route that loads its
collapsed sections on demand (ontology.case_section).

The fixture case tests/fixtures/level_pages/proethica-case-9901.ttl is seeded
through the sync service, once per module, since other modules wipe the tables.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'level_pages' / 'proethica-case-9901.ttl'
HTML = {'Accept': 'text/html', 'User-Agent': 'Mozilla/5.0'}
CASE = 'proethica-case-9901'


@pytest.fixture(scope='module')
def case_page(app):
    from services.ontology_sync_service import OntologySyncService
    from web.models import db
    with app.app_context():
        OntologySyncService(db.session, FIXTURE.parent)._sync_single_ontology(FIXTURE, force=True)
    app.config['PROETHICA_BASE_URL'] = 'https://proethica.example'
    try:
        yield
    finally:
        app.config.pop('PROETHICA_BASE_URL', None)


def _get(client, path):
    r = client.get(path, headers=HTML)
    return r, r.get_data(as_text=True)


@pytest.mark.integration
class TestCaseHeader:

    def test_trail_title_and_actions(self, client, case_page):
        r, html = _get(client, f'/ontology/{CASE}')
        assert r.status_code == 200
        main = html[html.index('<main'):html.index('</main>')]
        assert 'href="/?category=Cases">ProEthica cases</a>' in main
        assert 'href="/?category=Cases&amp;subcategory=1990s">1990s</a>' in main
        assert '<span aria-current="page">Case 9901</span>' in main
        assert '<h1 class="mb-1">Fixture Case on Drainage Design</h1>' in main
        assert 'NSPE 99-1' in main
        assert 'href="https://proethica.example/cases/9901"' in main and 'Open in ProEthica' in main
        assert main.count('btn-outline-primary') == 1
        assert f'href="/ontology/{CASE}?view=standard"' in main
        assert 'linear-gradient' not in html and 'text-bg-' not in main

    def test_vocabulary_line(self, client, case_page):
        _, html = _get(client, f'/ontology/{CASE}')
        assert 'href="/ontology/proethica-intermediate">proethica-intermediate</a>' in html
        assert 'href="/ontology/proethica-intermediate-extended?case=9901"' in html
        assert 'href="/ontology/proethica-cases">proethica-cases</a>' in html
        assert 'href="/ontology/NSPE%20Code%20of%20Ethics">NSPE Code of Ethics</a>' in html


@pytest.mark.integration
class TestCaseBody:

    def test_parts_and_nine_components(self, client, case_page):
        _, html = _get(client, f'/ontology/{CASE}')
        assert 'id="part-entities"' in html and 'Case entities' in html
        assert 'id="part-provenance"' in html and 'id="part-reasoning"' in html
        nine = html[html.index('id="section-nine_concepts"'):]
        assert 'Nine components' in nine[:200]
        # The component letters carry the concept colours of the docs palette;
        # each group has a thin border in its colour
        assert 'style="background: #0d6efd; border-color: #0d6efd; color: #ffffff;">R</span>' in nine
        assert '--subsection-color: #0d6efd;' in nine
        assert 'Engineer A Design Engineer' in nine and 'Engineer A Public Safety Duty' in nine

    def test_support_section_loads_on_demand(self, client, case_page):
        _, html = _get(client, f'/ontology/{CASE}')
        support = html[html.index('id="section-support"'):]
        link = f'href="/ontology/{CASE}/case-section/support" rel="nofollow"'
        assert link in support
        assert f'data-fragment="/ontology/{CASE}/case-section/support?fragment=1"' in support
        assert 'Derivation 1' in support
        assert 'Fixture edge provenance' not in html

        r, fragment = _get(client, f'/ontology/{CASE}/case-section/support?fragment=1')
        assert r.status_code == 200 and r.headers['X-Robots-Tag'] == 'noindex'
        assert 'Fixture edge provenance' in fragment and '<html' not in fragment

        r, page = _get(client, f'/ontology/{CASE}/case-section/support')
        assert r.status_code == 200 and r.headers['X-Robots-Tag'] == 'noindex'
        assert '<html' in page and 'Fixture edge provenance' in page
        assert f'href="/ontology/{CASE}#section-support"' in page

    def test_unknown_section_and_non_case_ontology(self, client, case_page):
        assert client.get(f'/ontology/{CASE}/case-section/nope', headers=HTML).status_code == 404
        assert client.get('/ontology/proethica-cases/case-section/support', headers=HTML).status_code == 404

    def test_sidebar_lists_the_parts(self, client, case_page):
        _, html = _get(client, f'/ontology/{CASE}')
        nav = html[html.index('class="case-nav"'):]
        nav = nav[:nav.index('</nav>')]
        assert re.search(r'href="#part-entities">Case entities</a>', nav)
        assert 'href="#section-support">Support nodes <span class="nav-count">1</span>' in nav
        assert 'href="#part-reasoning">Reasoning</a>' in nav
