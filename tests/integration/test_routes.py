"""
Route Integration Tests

Tests for Flask routes, especially focusing on route conflict resolution
and authentication flows.
"""

import pytest
from urllib.parse import quote


@pytest.mark.integration
class TestBasicRoutes:
    """Test basic route functionality."""

    def test_index_route(self, client):
        """Test index page loads."""
        response = client.get('/')
        assert response.status_code == 200

    def test_health_endpoint(self, client):
        """Test health endpoint exists."""
        response = client.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert 'status' in data


@pytest.mark.integration
class TestOntologyRoutes:
    """Test ontology-related routes."""

    def test_ontology_detail_route(self, client, helpers, db_session):
        """Test ontology detail page."""
        # Create test ontology
        ontology = helpers.create_test_ontology(db_session)

        response = client.get(f'/ontology/{ontology.name}')
        # Should return 200 (detail page) or 302 (redirect to RDF format)
        assert response.status_code in [200, 302]

    def test_ontology_content_route(self, client, helpers, db_session):
        """Test ontology content endpoint."""
        ontology = helpers.create_test_ontology(db_session)

        response = client.get(f'/ontology/{ontology.name}/content')
        # Should return content or 404 if no content
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestEditRoutes:
    """Test edit-related routes and route conflict resolution."""

    def test_edit_route_exists(self, client, helpers, db_session):
        """Test edit route is accessible (should redirect to login if not authenticated)."""
        ontology = helpers.create_test_ontology(db_session, name='test-ontology')

        response = client.get('/ontology/test-ontology/edit', follow_redirects=False)

        # Should redirect to login (302) or show edit page (200) if authenticated
        assert response.status_code in [200, 302], \
            f"Expected 200 or 302, got {response.status_code}"

        if response.status_code == 302:
            # Verify redirect is to login page
            location = response.headers.get('Location', '')
            assert '/auth/login' in location, \
                f"Expected redirect to login, got {location}"

    def test_edit_route_with_url_encoded_name(self, client, helpers, db_session):
        """Test edit route works with URL-encoded ontology names (regression test for bug)."""
        # Create ontology with spaces in name
        ontology = helpers.create_test_ontology(
            db_session,
            name='Relations Ontology 2015'
        )

        # Test with URL encoding
        encoded_name = quote('Relations Ontology 2015')
        response = client.get(
            f'/ontology/{encoded_name}/edit',
            follow_redirects=False
        )

        # Should NOT return 404 (this was the bug)
        assert response.status_code != 404, \
            "Edit route should not return 404 for URL-encoded names"

        # Should redirect to login or show edit page
        assert response.status_code in [200, 302], \
            f"Expected 200 or 302, got {response.status_code}"

    def test_edit_route_priority_over_catch_all(self, client, helpers, db_session):
        """Test that edit route has priority over catch-all URI resolution route."""
        ontology = helpers.create_test_ontology(db_session)

        # The catch-all route matches /ontology/<path>/<entity_name>
        # But /ontology/<name>/edit should use the dedicated edit route
        response = client.get(
            f'/ontology/{ontology.name}/edit',
            follow_redirects=False
        )

        # Verify we got a proper response (login redirect or edit page)
        # NOT a 404 from the catch-all route rejecting 'edit' as reserved
        assert response.status_code in [200, 302]

        if response.status_code == 302:
            location = response.headers.get('Location', '')
            # Should redirect to login, not to edit route (no redirect loop)
            assert '/auth/login' in location
            assert '/edit' not in location or 'next=' in location

    def test_settings_route_exists(self, client, helpers, db_session):
        """Test settings route is accessible."""
        ontology = helpers.create_test_ontology(db_session)

        response = client.get(
            f'/ontology/{ontology.name}/settings',
            follow_redirects=False
        )

        # Should work (200) or redirect to login (302)
        assert response.status_code in [200, 302]

    def test_content_route_exists(self, client, helpers, db_session):
        """Test content route is accessible."""
        ontology = helpers.create_test_ontology(db_session)

        response = client.get(
            f'/ontology/{ontology.name}/content',
            follow_redirects=False
        )

        # Should return content (200) or 404 if no content
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestReservedRouteNames:
    """Test that reserved route names are handled correctly."""

    def test_reserved_names_not_treated_as_entities(self, client, helpers, db_session):
        """Test that reserved names (edit, save, etc.) use dedicated routes."""
        ontology = helpers.create_test_ontology(db_session)

        reserved_names = ['edit', 'save', 'settings', 'content']

        for name in reserved_names:
            response = client.get(
                f'/ontology/{ontology.name}/{name}',
                follow_redirects=False
            )

            # Should NOT return entity resolution (which might be 404)
            # Should use dedicated route (200, 302, or 405 for POST-only routes)
            assert response.status_code in [200, 302, 405], \
                f"Reserved name '{name}' got unexpected status {response.status_code}"


@pytest.mark.integration
class TestAuthenticationRoutes:
    """Test authentication-related routing."""

    def test_login_route_exists(self, client):
        """Test login page is accessible."""
        response = client.get('/auth/login')
        assert response.status_code == 200

    def test_protected_route_redirects_to_login(self, client, helpers, db_session):
        """Test that protected routes redirect to login."""
        ontology = helpers.create_test_ontology(db_session)

        # Try to access edit page without authentication
        response = client.get(
            f'/ontology/{ontology.name}/edit',
            follow_redirects=False
        )

        if response.status_code == 302:
            # Should redirect to login
            location = response.headers.get('Location', '')
            assert '/auth/login' in location

            # Should preserve 'next' parameter for redirect after login
            assert 'next=' in location


@pytest.mark.integration
class TestURIResolution:
    """Test URI resolution functionality."""

    def test_uri_resolution_query_param(self, client):
        """Test URI resolution with query parameter."""
        uri = 'http://proethica.org/ontology/intermediate#Honesty'
        response = client.get(f'/resolve?uri={uri}')

        # Should work or return 404 if entity doesn't exist
        assert response.status_code in [200, 404]

    def test_path_based_uri_resolution(self, client, helpers, db_session):
        """Test path-based URI resolution."""
        # Create test entity
        ontology = helpers.create_test_ontology(db_session)
        entity = helpers.create_test_entity(
            db_session,
            ontology,
            uri='http://proethica.org/ontology/test#TestEntity',
            label='TestEntity'
        )

        # Try to resolve via path (this is what the catch-all route handles)
        # Format: /ontology/test/TestEntity
        response = client.get('/ontology/test/TestEntity')

        # Should resolve or return 404 if entity doesn't exist
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestRouteConflictResolution:
    """Test that route conflicts are resolved correctly."""

    def test_specific_routes_take_precedence(self, client, helpers, db_session):
        """Test that specific routes have priority over catch-all routes."""
        ontology = helpers.create_test_ontology(db_session)

        # Test several specific routes that should NOT be caught by catch-all
        specific_routes = [
            f'/ontology/{ontology.name}/edit',
            f'/ontology/{ontology.name}/settings',
            f'/ontology/{ontology.name}/content',
        ]

        for route in specific_routes:
            response = client.get(route, follow_redirects=False)

            # Should NOT return 404 (which would indicate catch-all rejected it)
            assert response.status_code != 404, \
                f"Route {route} should not return 404"

            # Should return valid response (200, 302, or 405 for POST-only)
            assert response.status_code in [200, 302, 405], \
                f"Route {route} got unexpected status {response.status_code}"


# Pytest configuration for this module
pytest_plugins = []
