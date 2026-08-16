"""Index page grouping by category (services.ontology_categories)."""

import re

import pytest
from sqlalchemy import select


@pytest.fixture()
def case_names(app):
    """Names of case ontologies, seeding enough to exceed the collapse threshold.

    Other test modules' db_session fixture wipes every table, so this test
    cannot rely on the startup TTL sync having populated the shared test DB.
    """
    from web.models import db, Ontology
    threshold = app.config.get('INDEX_COLLAPSE_THRESHOLD', 12)
    with app.app_context():
        names = db.session.execute(
            select(Ontology.name).where(Ontology.ontology_type == 'case')).scalars().all()
        for i in range(len(names), threshold + 2):
            name = f'proethica-case-{9000 + i}'
            db.session.add(Ontology(name=name, base_uri=f'http://proethica.org/ontology/case/{9000 + i}#',
                                    ontology_type='case', source_system='proethica', meta_data={}))
            names.append(name)
        core = db.session.execute(select(Ontology).where(Ontology.name == 'proethica-core')).scalar_one_or_none()
        if core is None:
            db.session.add(Ontology(name='proethica-core', base_uri='http://proethica.org/ontology/core#',
                                    ontology_type='core', source_system='proethica', meta_data={}))
        elif (core.meta_data or {}).get('category') or (core.meta_data or {}).get('subcategory'):
            # A failed settings test may leave an explicit category behind; the rule default is assumed below
            core.meta_data = {k: v for k, v in (core.meta_data or {}).items() if k not in ('category', 'subcategory')}
        db.session.commit()
    return names


def _section_span(html, section_id):
    """[start, end) of the <section id=...> element, honouring nested <section>s."""
    m = re.search(r'<section[^>]*\bid="%s"' % re.escape(section_id), html)
    if not m:
        return None
    depth = 0
    for tok in re.finditer(r'<section\b|</section>', html[m.start():]):
        depth += 1 if tok.group() == '<section' else -1
        if depth == 0:
            return (m.start(), m.start() + tok.end())
    return None


@pytest.mark.integration
class TestIndexGrouping:

    def test_unfiltered_index_is_grouped(self, client, case_names):
        r = client.get('/')
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert 'id="category-cases"' in html
        assert 'Browse all' in html
        # Cases sit INSIDE the ProEthica family section, after the framework layers
        fam = _section_span(html, 'family-proethica')
        assert fam is not None
        inner = html[fam[0]:fam[1]]
        assert 'id="category-proethica-framework"' in inner and 'id="category-cases"' in inner
        assert inner.index('id="category-proethica-framework"') < inner.index('id="category-cases"')
        assert '>Framework</a>' in inner and '>Cases</a>' in inner
        # Individual case rows are collapsed away when the group exceeds the threshold
        threshold = client.application.config.get('INDEX_COLLAPSE_THRESHOLD', 12)
        if len(case_names) > threshold:
            assert not re.search(r'<strong>proethica-case-\d+</strong>', html)

    def test_category_filter_lists_cases_flat(self, client, case_names):
        r = client.get('/?category=Cases')
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert re.search(r'<strong>proethica-case-\d+</strong>', html)
        assert 'Clear category' in html
        # Flat view: no family sections, banner uses the full standalone label
        assert 'id="family-proethica"' not in html and 'family-section' not in html
        assert 'ProEthica Cases' in html

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
            # The grouped index advertises the subcategory as a chip when the group is collapsed
            r = client.get('/')
            if len(case_names) > client.application.config.get('INDEX_COLLAPSE_THRESHOLD', 12):
                assert 'subcategory=Test+Decade' in r.get_data(as_text=True)
        finally:
            with app.app_context():
                o = db.session.execute(select(Ontology).where(Ontology.name == name)).scalar_one()
                o.meta_data = saved
                db.session.commit()

    def test_unknown_category_yields_no_match_alert(self, client):
        r = client.get('/?category=NoSuchCategory')
        assert r.status_code == 200
        assert 'No matching ontologies' in r.get_data(as_text=True)

    def test_source_and_type_filters_still_work(self, client, case_names):
        r = client.get('/?type=case')
        assert r.status_code == 200
        assert re.search(r'<strong>proethica-case-\d+</strong>', r.get_data(as_text=True))

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
