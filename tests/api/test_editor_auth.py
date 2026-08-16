"""Tests for the app-level /editor auth guard (_guard_editor_space).

The guard must cover routes registered under /editor by ANY blueprint (the
pre-fix hole was ontology.extract_entities_editor, an unauthenticated write
from a foreign blueprint), while keeping the read-only visualization surface
and the ProEthica entities contract public.
"""

import pytest


@pytest.fixture()
def client(app):
    return app.test_client()


class TestAnonymousBlocked:

    def test_editor_index_redirects_to_login(self, client):
        r = client.get('/editor/')
        assert r.status_code == 302
        assert '/auth/login' in r.headers['Location']

    def test_editor_page_redirect_carries_next(self, client):
        r = client.get('/editor/ontology/proethica-core')
        assert r.status_code == 302
        assert 'next=' in r.headers['Location']

    def test_foreign_blueprint_write_under_editor_is_blocked(self, client):
        # THE regression case: this route belongs to the `ontology` blueprint,
        # not ontology_editor, and used to execute an entity re-extraction
        # anonymously.
        r = client.post('/editor/api/extract-entities/proethica-core')
        assert r.status_code == 401
        assert r.get_json()['error'] == 'Authentication required'

    def test_draft_write_is_blocked(self, client):
        r = client.post('/editor/api/ontologies/x/draft', json={})
        assert r.status_code == 401

    def test_editor_entity_api_is_blocked(self, client):
        r = client.get('/editor/api/entity/1')
        assert r.status_code == 401


class TestPublicSurface:
    """Public endpoints must reach their handlers (a data-driven 404/500 is
    fine; a 302/401 would mean the guard wrongly blocked them)."""

    def _assert_not_auth_blocked(self, r):
        assert r.status_code not in (302, 401)

    def test_visualize_page(self, client):
        self._assert_not_auth_blocked(client.get('/editor/ontology/nope/visualize'))

    def test_visualization_data_api(self, client):
        self._assert_not_auth_blocked(client.get('/editor/api/enhanced/visualization/nope'))

    def test_hierarchy_data_api(self, client):
        self._assert_not_auth_blocked(client.get('/editor/api/hierarchy/visualization/nope'))

    def test_reasoning_read_only(self, client):
        self._assert_not_auth_blocked(client.post('/editor/api/simple/reasoning/nope', json={}))

    def test_proethica_entities_contract(self, client):
        # Documented ProEthica integration endpoint; must stay server-to-server
        # accessible without a session.
        self._assert_not_auth_blocked(client.get('/editor/api/ontologies/nope/entities'))


class TestAuthenticatedAccess:

    def test_logged_in_user_reaches_editor_index(self, logged_in_client):
        r = logged_in_client.get('/editor/')
        assert r.status_code == 200

    def test_login_disabled_bypasses_guard(self, app, client):
        app.config['LOGIN_DISABLED'] = True
        try:
            r = client.get('/editor/')
            assert r.status_code == 200
        finally:
            app.config['LOGIN_DISABLED'] = False
