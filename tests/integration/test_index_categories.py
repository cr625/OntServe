"""The home page (the ProEthica stack), the flat list of the category filters,
the category settings and the navbar."""

import re
from urllib.parse import quote

import pytest
from sqlalchemy import select

from services import proethica_stack as stack

# Rows the home page needs beyond the levels: the case vocabulary and code,
# one support ontology, one reference ontology.
STACK_ROWS = [(lvl.ontology, 'base', 'proethica') for lvl in stack.LEVELS] + [
    (stack.CASES_VOCABULARY, 'base', 'proethica'),
    (stack.CASES_CODE, 'base', 'external'),
    ('proethica-foundation', 'upper', 'proethica'),
    ('bfo', 'upper', 'external'),
]


@pytest.fixture()
def case_names(app):
    """Names of case ontologies, with the stack rows the home page needs.

    Other test modules' db_session fixture wipes every table, so these tests
    cannot rely on the startup TTL sync having populated the shared test DB.
    """
    from web.models import db, Ontology
    with app.app_context():
        existing = set(db.session.execute(select(Ontology.name)).scalars().all())
        for name, otype, source in STACK_ROWS:
            if name not in existing:
                db.session.add(Ontology(name=name, base_uri=f'http://example.org/{quote(name)}#',
                                        ontology_type=otype, source_system=source, meta_data={}))
        names = db.session.execute(
            select(Ontology.name).where(Ontology.ontology_type == 'case')).scalars().all()
        for i in range(len(names), 3):
            name = f'proethica-case-{9000 + i}'
            db.session.add(Ontology(name=name, base_uri=f'http://proethica.org/ontology/case/{9000 + i}',
                                    ontology_type='case', source_system='proethica',
                                    meta_data={'subcategory': '1990s'}))
            names.append(name)
        core = db.session.execute(select(Ontology).where(Ontology.name == 'proethica-core')).scalar_one()
        if (core.meta_data or {}).get('category') or (core.meta_data or {}).get('subcategory'):
            # A failed settings test may leave an explicit category behind; the rule default is assumed below
            core.meta_data = {k: v for k, v in (core.meta_data or {}).items() if k not in ('category', 'subcategory')}
        db.session.commit()
    return names


def _main(html):
    return html[html.index('<main'):html.index('</main>')]


def _nav(html):
    return html[html.index('<nav'):html.index('</nav>')]


def _element(html, tag, element_id):
    """The <tag id=...> element, honouring nested elements of the same tag."""
    m = re.search(r'<%s[^>]*\bid="%s"' % (tag, re.escape(element_id)), html)
    if not m:
        return None
    depth = 0
    for tok in re.finditer(r'<%s\b|</%s>' % (tag, tag), html[m.start():]):
        depth += -1 if tok.group().startswith('</') else 1
        if depth == 0:
            return html[m.start():m.start() + tok.end()]
    return None


def _href(name):
    return f'href="/ontology/{quote(name)}"'


@pytest.mark.integration
class TestStackHome:

    def test_levels_in_stack_order(self, client, case_names):
        r = client.get('/')
        assert r.status_code == 200
        main = _main(r.get_data(as_text=True))
        positions = [main.index(f'id="level-{lvl.key}"') for lvl in stack.LEVELS]
        assert positions == sorted(positions)
        for lvl in stack.LEVELS:
            assert lvl.role in main

    def test_no_repository_chrome(self, client, case_names):
        main = _main(client.get('/').get_data(as_text=True))
        assert 'aria-label="Source filter"' not in main and 'aria-label="Type filter"' not in main
        assert 'Total Ontologies' not in main and 'text-bg-' not in main
        assert 'Import Ontology' not in main

    def test_decade_chip_links_the_case_listing(self, client, app, case_names):
        from web.models import db, Ontology
        name = case_names[0]
        with app.app_context():
            o = db.session.execute(select(Ontology).where(Ontology.name == name)).scalar_one()
            saved = dict(o.meta_data or {})
            o.meta_data = {**saved, 'subcategory': '1990s'}
            db.session.commit()
        try:
            cases = _element(client.get('/').get_data(as_text=True), 'section', 'cases')
            assert 'href="/?category=Cases&amp;subcategory=1990s"' in cases
            assert 'href="/?category=Cases"' in cases
            assert _href(stack.CASES_VOCABULARY) in cases and _href(stack.CASES_CODE) in cases
        finally:
            with app.app_context():
                o = db.session.execute(select(Ontology).where(Ontology.name == name)).scalar_one()
                o.meta_data = saved
                db.session.commit()

    def test_bfo_only_in_the_closed_reference_list(self, client, case_names):
        main = _main(client.get('/').get_data(as_text=True))
        reference = _element(main, 'details', 'reference')
        assert reference is not None and not re.match(r'<details[^>]*\bopen\b', reference)
        assert _href('bfo') in reference
        assert main.count(_href('bfo')) == 1

    def test_each_ontology_once(self, client, app, case_names):
        from web.models import db, Ontology
        with app.app_context():
            names = db.session.execute(select(Ontology.name)).scalars().all()
        main = _main(client.get('/').get_data(as_text=True))
        for name in names:
            # Case ontologies are counted in the Cases region, not listed
            expected = 0 if name in case_names or name.startswith('proethica-case-') else 1
            assert main.count(_href(name)) == expected, name

    def test_publications_follow_anonymous_mode(self, client, app, case_names):
        app.config['ANONYMOUS_MODE'] = True
        try:
            assert 'id="publications"' not in client.get('/').get_data(as_text=True)
        finally:
            app.config['ANONYMOUS_MODE'] = False
        html = client.get('/').get_data(as_text=True)
        assert 'id="publications"' in html
        assert 'Metadata Terminology Standardization for AI-Assisted Materials Science Research' in html
        assert '(in press)' in html


@pytest.mark.integration
class TestNavbar:

    def test_navbar_reads_the_stack(self, client, case_names):
        nav = _nav(client.get('/').get_data(as_text=True))
        for lvl in stack.LEVELS:
            assert _href(lvl.ontology) in nav and f'>{lvl.nav_label}</a>' in nav
        assert '>Cases</a>' in nav and '>Search</a>' in nav
        assert '> Home' not in nav and 'bi-house' not in nav

    def test_anonymous_navbar_has_no_filled_badge(self, client, case_names):
        nav = _nav(client.get('/').get_data(as_text=True))
        assert 'text-bg-' not in nav and 'bg-info' not in nav and 'bg-warning' not in nav
        assert '>Import</a>' not in nav

    def test_active_item(self, client, case_names):
        nav = _nav(client.get('/?category=Cases').get_data(as_text=True))
        assert re.search(r'class="nav-link active" aria-current="page"\s+href="/\?category=Cases"', nav)
        nav = _nav(client.get('/search').get_data(as_text=True))
        assert re.search(r'class="nav-link active" aria-current="page"\s+href="/search"', nav)

    def test_title_and_footer(self, client, case_names):
        html = client.get('/').get_data(as_text=True)
        assert '<title>OntServe, ontology server for ProEthica</title>' in html
        assert 'Unified Ontology Server' not in html
        # The home page states the server once, in its heading; other pages keep the footer
        body = html[html.index('<body'):]
        assert body.lower().count('ontology server for proethica') == 1
        assert '<footer' not in body
        assert '<footer' in client.get('/search').get_data(as_text=True)


@pytest.mark.integration
class TestFlatList:

    def test_category_filter_lists_cases_flat(self, client, case_names):
        r = client.get('/?category=Cases')
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert re.search(r'<strong>proethica-case-\d+</strong>', html)
        assert 'Clear category' in html
        assert 'ProEthica Cases' in html
        assert 'id="reference"' not in html

    def test_subcategory_filter(self, client, app, case_names):
        """An explicit metadata.subcategory routes the case into a chip and a filter."""
        from web.models import db, Ontology
        name = case_names[0]
        with app.app_context():
            o = db.session.execute(select(Ontology).where(Ontology.name == name)).scalar_one()
            saved = dict(o.meta_data or {})
            o.meta_data = {**saved, 'subcategory': 'Test Decade'}
            db.session.commit()
        try:
            r = client.get('/?category=Cases&subcategory=Test%20Decade')
            assert r.status_code == 200
            html = r.get_data(as_text=True)
            assert f'<strong>{name}</strong>' in html
            assert 'Test Decade' in html
            others = re.findall(r'<strong>(proethica-case-\d+)</strong>', html)
            assert others == [name]
            # The home page advertises the subcategory as a decade chip
            assert 'subcategory=Test+Decade' in client.get('/').get_data(as_text=True)
        finally:
            with app.app_context():
                o = db.session.execute(select(Ontology).where(Ontology.name == name)).scalar_one()
                o.meta_data = saved
                db.session.commit()

    def test_unknown_category_yields_no_match_alert(self, client, case_names):
        r = client.get('/?category=NoSuchCategory')
        assert r.status_code == 200
        assert 'No matching ontologies' in r.get_data(as_text=True)

    def test_source_and_type_filters_still_work(self, client, case_names):
        r = client.get('/?type=case')
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert re.search(r'<strong>proethica-case-\d+</strong>', html)
        assert 'text-bg-' not in _main(html)

    def test_api_exposes_category(self, client, case_names):
        r = client.get('/api/ontologies')
        assert r.status_code == 200
        data = r.get_json()
        assert data and all('category' in o and 'subcategory' in o for o in data)


@pytest.mark.integration
class TestCategorySettings:

    def test_settings_page_and_api_round_trip(self, logged_in_client, case_names):
        r = logged_in_client.get('/ontology/proethica-core/settings')
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert 'id="ontologyCategory"' in html and 'id="ontologySubcategory"' in html
        assert 'placeholder="default: ProEthica Framework"' in html

        r = logged_in_client.put('/api/ontology/proethica-core/metadata',
                                 json={'category': 'Sandbox', 'subcategory': 'x'})
        assert r.status_code == 200 and r.get_json()['success']
        data = logged_in_client.get('/api/ontology/proethica-core').get_json()
        assert (data['category'], data['subcategory']) == ('Sandbox', 'x')

        # Blank clears the explicit value; the rule default applies again
        logged_in_client.put('/api/ontology/proethica-core/metadata', json={'category': '', 'subcategory': ''})
        data = logged_in_client.get('/api/ontology/proethica-core').get_json()
        assert (data['category'], data['subcategory']) == ('ProEthica Framework', None)


@pytest.mark.integration
class TestWolframAccess:

    def test_wolfram_routes_require_login(self, client):
        for method, path in (('get', '/wolfram/'), ('post', '/wolfram/query'),
                             ('post', '/wolfram/clear'), ('get', '/wolfram/status')):
            r = getattr(client, method)(path, json={'message': 'x'} if method == 'post' else None)
            assert r.status_code in (302, 401), path
            if r.status_code == 302:
                assert '/auth/login' in r.headers['Location']


@pytest.mark.integration
class TestCaseHeaderBacklink:

    def test_case_page_links_to_proethica_case(self, client, app, case_names):
        name = case_names[0]
        case_id = name.rsplit('-', 1)[1]
        app.config['PROETHICA_BASE_URL'] = 'https://proethica.example/'
        try:
            r = client.get(f'/ontology/{name}', headers={'Accept': 'text/html'})
            assert r.status_code == 200
            html = r.get_data(as_text=True)
            assert f'href="https://proethica.example/cases/{case_id}"' in html
            assert 'View case in ProEthica' in html
        finally:
            app.config.pop('PROETHICA_BASE_URL', None)

    def test_case_number_and_decade_badges(self, client, app, case_names):
        from web.models import db, Ontology
        name = case_names[0]
        with app.app_context():
            o = db.session.execute(select(Ontology).where(Ontology.name == name)).scalar_one()
            saved = dict(o.meta_data or {})
            o.meta_data = {**saved, 'case_number': '99-7', 'subcategory': '1990s'}
            db.session.commit()
        try:
            html = client.get(f'/ontology/{name}', headers={'Accept': 'text/html'}).get_data(as_text=True)
            assert 'NSPE 99-7' in html
            assert 'subcategory=1990s' in html
        finally:
            with app.app_context():
                o = db.session.execute(select(Ontology).where(Ontology.name == name)).scalar_one()
                o.meta_data = saved
                db.session.commit()
