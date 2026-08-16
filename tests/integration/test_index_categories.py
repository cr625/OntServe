"""Index page grouping by category (services.ontology_categories)."""

import re

import pytest
from sqlalchemy import select


@pytest.mark.integration
class TestIndexGrouping:

    @pytest.fixture()
    def case_names(self, app):
        from web.models import db, Ontology
        with app.app_context():
            names = db.session.execute(
                select(Ontology.name).where(Ontology.ontology_type == 'case')).scalars().all()
        if not names:
            pytest.skip('no case ontologies in the test database')
        return names

    def test_unfiltered_index_is_grouped(self, client, case_names):
        r = client.get('/')
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert 'id="category-cases"' in html
        assert 'Browse all' in html
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

    def test_api_exposes_category(self, client):
        r = client.get('/api/ontologies')
        assert r.status_code == 200
        data = r.get_json()
        assert data and all('category' in o and 'subcategory' in o for o in data)


@pytest.mark.integration
class TestCategorySettings:

    def test_settings_page_and_api_round_trip(self, logged_in_client):
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
