"""The collections index at / (and /collections), the landing pages of
/collections/<key>, the redirect of ProEthica links to its landing page and
the navigation of the pages of each collection (services.collections,
web/main_routes.py, config/collections.yaml)."""

import re
from pathlib import Path
from urllib.parse import quote

import pytest
import yaml
from sqlalchemy import select

from services import collections as coll
from services import proethica_stack as stack
from services.ontology_credit import normalize_credit

HTML = {'Accept': 'text/html', 'User-Agent': 'Mozilla/5.0'}
STACK_URL = '/collections/proethica'

STACK_ROWS = [(lvl.ontology, 'base', 'proethica', {}) for lvl in stack.LEVELS] + [
    (stack.CASES_VOCABULARY, 'base', 'proethica', {}),
    (stack.CASES_CODE, 'base', 'external', {}),
    ('proethica-case-9801', 'case', 'proethica', {'subcategory': '1990s'}),
    ('bfo', 'upper', 'external', {}),
]


def _credit(title, creators, redistribution='hosted', license_id='MIT'):
    return normalize_credit({'title': title, 'creators': creators, 'license': license_id,
                             'source': {'repository': f'https://example.org/{title.lower()}'},
                             'retrieved': '2026-11-07', 'redistribution': redistribution})


ROBOTICS = 'Robotics and Automation'
TEST_ROWS = [
    ('ext-soma-test', {'collection': 'robotics', 'category': ROBOTICS, 'subcategory': 'Activities and manipulation',
                       'display_name': 'SOMA (test)',
                       'credit': _credit('Soma', ['Ada Lovelace', 'Charles Babbage', 'Grace Hopper', 'Alan Turing'])}),
    ('ext-pmk-test', {'collection': 'robotics', 'category': ROBOTICS, 'subcategory': 'Activities and manipulation',
                      'credit': _credit('Pmk', ['Mohammed Diab'], 'reference-only', 'none stated')}),
    ('ext-adas-test', {'collection': 'robotics', 'category': ROBOTICS, 'subcategory': 'Automated driving',
                       'credit': _credit('Adas', ['Lihua Zhao'], license_id='CC-BY-NC-SA-4.0')}),
    ('ext-nosub-test', {'collection': 'robotics', 'category': ROBOTICS}),
    ('ext-ps-test', {'collection': 'physical-systems'}),
    ('ext-mystery-test', {}),
]


@pytest.fixture(scope='module')
def rows(app):
    from web.models import db, Ontology
    with app.app_context():
        existing = set(db.session.execute(select(Ontology.name)).scalars().all())
        for name, otype, source, md in STACK_ROWS:
            if name not in existing:
                db.session.add(Ontology(name=name, base_uri=f'http://example.org/{quote(name)}#',
                                        ontology_type=otype, source_system=source, meta_data=md))
        for name, md in TEST_ROWS:
            if name not in existing:
                db.session.add(Ontology(name=name, base_uri=f'http://example.org/{name}#', ontology_type='base',
                                        source_system='external', meta_data=md))
        db.session.commit()
    yield
    with app.app_context():
        for o in db.session.execute(select(Ontology).where(
                Ontology.name.in_([n for n, _ in TEST_ROWS]))).scalars().all():
            db.session.delete(o)
        db.session.commit()


def _get(client, path):
    r = client.get(path, headers=HTML)
    return r, r.get_data(as_text=True)


def _main(html):
    return html[html.index('<main'):html.index('</main>')]


def _nav(html):
    return html[html.index('<nav'):html.index('</nav>')]


@pytest.mark.integration
class TestIndex:

    def test_root_renders_the_index_with_proethica_first(self, client, rows):
        r, html = _get(client, '/')
        assert r.status_code == 200
        main = _main(html)
        positions = [main.index(f'id="collection-{key}"') for key in ('proethica', 'shared', 'robotics')]
        assert positions == sorted(positions)
        lead = main[positions[0]:positions[1]]
        assert '<h2 class="h3 card-title mb-2" id="collection-proethica-heading">' in lead
        assert 'href="/collections/proethica"' in lead and 'href="/?category=Cases"' in lead
        for lvl in stack.LEVELS:
            assert f'href="/ontology/{lvl.ontology}" class="chip">{lvl.label}</a>' in lead
        assert 'id="collection-physical-systems"' not in main and 'id="unassigned"' not in main
        assert '<title>OntServe, ontology server</title>' in html and '<footer' not in html
        assert 'rel="canonical"' not in html

    def test_collections_route_names_root_as_canonical(self, client, rows):
        _, html = _get(client, '/collections')
        assert '<link rel="canonical" href="/">' in html
        assert _main(html) == _main(_get(client, '/')[1])

    def test_signed_in_users_see_private_collections_and_unassigned_rows(self, logged_in_client, rows):
        main = _main(logged_in_client.get('/', headers=HTML).get_data(as_text=True))
        card = main[main.index('id="collection-physical-systems"'):]
        assert '>Private</span>' in card[:card.index('</div>')]
        unassigned = main[main.index('id="unassigned"'):]
        assert 'href="/ontology/ext-mystery-test"' in unassigned

    def test_proethica_links_land_on_its_page(self, client, rows):
        r = client.get('/?origin=proethica&filter=proethica')
        assert r.status_code == 302 and r.headers['Location'].endswith(STACK_URL)
        r = client.get('/?origin=robotics')
        assert r.status_code == 302 and r.headers['Location'].endswith('/collections/robotics')
        assert client.get('/?origin=nowhere').status_code == 200
        # With a filter the parameters keep their meaning
        r, html = _get(client, '/?origin=proethica&category=Cases')
        assert r.status_code == 200 and '<h1 class="h3 mb-1">ProEthica cases</h1>' in html

    def test_existing_parameters_keep_their_pages(self, client, rows):
        assert '<h1 class="h3 mb-1">ProEthica cases</h1>' in _get(client, '/?category=Cases')[1]
        main = _main(_get(client, '/?category=' + quote(ROBOTICS))[1])
        assert '<h1 class="h3 mb-3">Ontologies</h1>' in main and 'href="/ontology/ext-soma-test"' in main
        assert '<h1 class="h3 mb-3">Ontologies</h1>' in _main(_get(client, '/?source=external')[1])


@pytest.mark.integration
class TestLanding:

    def test_proethica_landing_is_the_stack(self, client, rows):
        r, html = _get(client, STACK_URL)
        assert r.status_code == 200
        main = _main(html)
        positions = [main.index(f'id="level-{lvl.key}"') for lvl in stack.LEVELS]
        assert positions == sorted(positions)
        assert '<title>OntServe, ontology server for ProEthica</title>' in html
        assert 'rel="canonical"' not in html and '<footer' not in html
        for name, _ in TEST_ROWS[:-1]:
            assert f'href="/ontology/{name}"' not in main, name
        # A row of no collection stays in the ProEthica scope
        assert 'href="/ontology/ext-mystery-test"' in main

    def test_robotics_landing_lists_members_with_credit(self, client, rows):
        r, html = _get(client, '/collections/robotics')
        assert r.status_code == 200
        main = _main(html)
        assert '<a href="/">Collections</a>' in main and '<h1 class="mb-1">Robotics and Automation</h1>' in main
        assert 'uses <a href="/collections/shared">Shared ontologies</a>' in main
        headings = re.findall(r'<h3 class="h6 text-body-secondary mt-3 mb-2">([^<]+)</h3>', main)
        assert headings == ['Activities and manipulation', 'Automated driving', 'Other']
        soma = main[main.index('id="member-ext-soma-test"'):]
        soma = soma[:soma.index('</li>')]
        assert '>SOMA (test)</a>' in soma
        assert 'Ada Lovelace, Charles Babbage, Grace Hopper and 1 other\n' in soma
        assert 'MIT' in soma and 'href="https://example.org/soma">source</a>' in soma
        pmk = main[main.index('id="member-ext-pmk-test"'):]
        pmk = pmk[:pmk.index('</li>')]
        assert '>Not hosted</span>' in pmk and 'no license stated' in pmk
        assert 'href="/ontology/ext-ps-test"' not in main and 'href="/ontology/bfo"' not in main

    def test_shared_landing_groups_by_category(self, client, rows):
        main = _main(_get(client, '/collections/shared')[1])
        assert '<h2 class="h4 mb-3">Foundation</h2>' in main and 'href="/ontology/bfo"' in main

    def test_private_and_unknown_collections(self, client, rows):
        assert client.get('/collections/physical-systems').status_code == 404
        assert client.get('/collections/nowhere').status_code == 404

    def test_private_collection_for_signed_in_users(self, logged_in_client, rows):
        # One client per test: the request context of the test keeps the first user it loads
        assert logged_in_client.get('/collections/physical-systems').status_code == 200


@pytest.mark.integration
class TestNavigation:

    def test_proethica_pages_keep_the_navbar_and_gain_collections(self, client, rows):
        for path in (STACK_URL, '/search', '/?category=Cases'):
            nav = _nav(_get(client, path)[1])
            assert 'href="/">Collections</a>' in nav, path
            for lvl in stack.LEVELS:
                assert f'>{lvl.nav_label}</a>' in nav, path
            assert '>Cases</a>' in nav and '>Search</a>' in nav
        nav = _nav(_get(client, '/')[1])
        assert re.search(r'class="nav-link active" aria-current="page"\s+href="/">Collections</a>', nav)

    def test_pages_of_another_collection_show_it(self, client, rows):
        for path in ('/collections/robotics', '/ontology/ext-soma-test'):
            r, html = _get(client, path)
            assert r.status_code == 200, path
            nav = _nav(html)
            assert re.search(r'class="nav-link active" aria-current="page"\s+href="/collections/robotics">'
                             r'Robotics and Automation</a>', nav), path
            assert '>Core</a>' not in nav and '>Cases</a>' not in nav and '>Search</a>' in nav
            assert 'ontology server for ProEthica' not in html, path
        main = _main(_get(client, '/ontology/ext-soma-test')[1])
        assert '<nav class="small mb-1" aria-label="Collection"><a href="/collections/robotics">' in main


@pytest.fixture()
def option_a(tmp_path, monkeypatch):
    """The collections file with home: default_collection (option A)."""
    data = yaml.safe_load(coll.CONFIG_PATH.read_text(encoding='utf-8'))
    data['home'] = 'default_collection'
    path = tmp_path / 'collections.yaml'
    path.write_text(yaml.safe_dump(data), encoding='utf-8')
    monkeypatch.setattr(coll, 'CONFIG_PATH', path)
    return path


@pytest.mark.integration
class TestDefaultCollectionAtRoot:

    def test_root_renders_the_default_collection(self, client, rows, option_a):
        r, html = _get(client, '/')
        assert r.status_code == 200 and 'id="level-core"' in html and 'rel="canonical"' not in html
        _, landing = _get(client, STACK_URL)
        assert '<link rel="canonical" href="/">' in landing
        _, index = _get(client, '/collections')
        assert 'id="collection-proethica"' in index and 'rel="canonical"' not in index
        assert 'href="/collections">Collections</a>' in _nav(html)
        assert client.get('/?origin=proethica&filter=proethica').status_code == 200
        r = client.get('/?origin=robotics')
        assert r.status_code == 302 and r.headers['Location'].endswith('/collections/robotics')


@pytest.mark.integration
class TestCollectionSetting:

    def test_settings_page_and_api(self, logged_in_client, rows):
        html = logged_in_client.get('/ontology/ext-mystery-test/settings').get_data(as_text=True)
        assert 'id="ontologyCollection"' in html and '<option value="">Default: no collection</option>' in html
        r = logged_in_client.put('/api/ontology/ext-mystery-test/metadata', json={'collection': 'nowhere'})
        assert r.status_code == 400
        r = logged_in_client.put('/api/ontology/ext-mystery-test/metadata', json={'collection': 'shared'})
        assert r.status_code == 200 and r.get_json()['success']
        main = _main(logged_in_client.get('/collections/shared').get_data(as_text=True))
        assert 'href="/ontology/ext-mystery-test"' in main
        html = logged_in_client.get('/ontology/ext-mystery-test/settings').get_data(as_text=True)
        assert '<option value="shared" selected>Shared ontologies</option>' in html
        # Blank clears the explicit value
        logged_in_client.put('/api/ontology/ext-mystery-test/metadata', json={'collection': ''})
        main = _main(logged_in_client.get('/collections/shared').get_data(as_text=True))
        assert 'href="/ontology/ext-mystery-test"' not in main
