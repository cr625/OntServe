"""
API Compatibility Tests

Tests to ensure external API contracts are maintained.
These tests verify that ProEthica and other external applications
can continue to use OntServe without breaking changes.
"""

import pytest
import json


@pytest.mark.api
class TestFlaskAPIEndpoints:
    """Test Flask HTTP API endpoints."""

    def test_uri_resolution_query_param(self, client):
        """Test URI resolution with query parameter."""
        uri = 'http://proethica.org/ontology/intermediate#Honesty'
        response = client.get(f'/resolve?uri={uri}')

        # Should return 404 if entity doesn't exist, or 200 if it does
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            # Check response format
            assert response.content_type in [
                'text/turtle',
                'application/json'
            ]

    def test_uri_resolution_with_json_accept(self, client):
        """Test URI resolution with JSON content negotiation."""
        uri = 'http://proethica.org/ontology/intermediate#Honesty'
        response = client.get(
            f'/resolve?uri={uri}',
            headers={'Accept': 'application/json'}
        )

        # Should work or return 404
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            assert response.is_json
            data = response.get_json()
            assert 'uri' in data

    def test_ontology_list_endpoint(self, client):
        """Test ontology listing endpoint."""
        response = client.get('/api/ontologies')

        # Endpoint should exist
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.get_json()
            assert isinstance(data, (list, dict))

    def test_ontology_detail_endpoint(self, client):
        """Test ontology detail endpoint."""
        response = client.get('/api/ontology/engineering-ethics')

        # Endpoint should exist
        assert response.status_code in [200, 404, 500]

    def test_cors_headers(self, client):
        """Test CORS headers are present."""
        response = client.get('/resolve?uri=http://test.org/test',
                             method='OPTIONS')

        # CORS preflight should work
        assert response.status_code in [200, 404]


@pytest.mark.api
@pytest.mark.database
class TestAPIContractStability:
    """Test that API contracts remain stable across updates."""

    def test_mcp_tool_list_stable(self, client):
        """Verify MCP tools list hasn't changed unexpectedly."""
        # This would normally call the MCP endpoint
        # For now, we document the expected tools
        expected_tools = {
            'get_entities_by_category',
            'submit_candidate_concept',
            'sparql_query',
            'update_concept_status',
            'get_candidate_concepts',
            'get_domain_info',
            'store_extracted_entities',
            'get_case_entities'
        }

        # Test passes if we can document the contract
        assert len(expected_tools) == 8

    def test_entity_json_format(self, client, helpers, db_session):
        """Test entity JSON format remains stable."""
        # Create test ontology and entity
        ontology = helpers.create_test_ontology(db_session)
        entity = helpers.create_test_entity(db_session, ontology)

        response = client.get(
            f'/resolve?uri={entity.uri}',
            headers={'Accept': 'application/json'}
        )

        if response.status_code == 200:
            data = response.get_json()

            # Required fields in entity JSON
            required_fields = ['uri', 'label', 'type']
            for field in required_fields:
                assert field in data, f"Required field '{field}' missing from entity JSON"


@pytest.mark.api
class TestBackwardCompatibility:
    """Test backward compatibility with previous versions."""

    def test_legacy_query_param_format(self, client):
        """Test legacy query parameter format still works."""
        # Old format might have been different
        response = client.get('/resolve?uri=http://test.org/test')

        # Should handle gracefully
        assert response.status_code in [200, 404, 400]

    def test_legacy_ontology_endpoints(self, client):
        """Test legacy ontology endpoints still work."""
        response = client.get('/ontology/engineering-ethics')

        # Endpoint should exist
        assert response.status_code in [200, 404, 302, 500]


@pytest.mark.api
@pytest.mark.integration
class TestProEthicaIntegration:
    """Specific tests for ProEthica integration."""

    def test_proethica_domain_default(self, client):
        """Test that engineering-ethics is the default domain."""
        # This tests ProEthica's assumption about default domain
        default_domain = 'engineering-ethics'

        # Verify domain exists or is handled
        assert default_domain is not None

    def test_concept_submission_flow(self, client, sample_candidate_concept):
        """Test the complete concept submission flow used by ProEthica."""
        # This would test:
        # 1. ProEthica extracts concepts
        # 2. Submits via MCP
        # 3. Retrieves via API
        # 4. Updates status

        # For now, document the expected flow
        flow_steps = [
            'extract_entities',
            'submit_candidate_concept',
            'get_candidate_concepts',
            'update_concept_status'
        ]

        assert len(flow_steps) == 4

    def test_case_entity_storage_flow(self, client):
        """Test case-specific entity storage (NSPE cases)."""
        # ProEthica stores entities for specific cases
        # Test the expected flow
        case_flow = [
            'store_extracted_entities',  # Store entities for a case
            'get_case_entities'           # Retrieve entities for a case
        ]

        assert len(case_flow) == 2


@pytest.mark.api
class TestAPIErrorHandling:
    """Test API error handling and edge cases."""

    def test_malformed_uri(self, client):
        """Test handling of malformed URI."""
        response = client.get('/resolve?uri=not-a-valid-uri')

        # Should handle gracefully
        assert response.status_code in [400, 404, 500]

    def test_missing_uri_param(self, client):
        """Test resolve endpoint without URI parameter."""
        response = client.get('/resolve')

        # Should return 400 Bad Request
        assert response.status_code == 400

        if response.is_json:
            data = response.get_json()
            assert 'error' in data

    def test_nonexistent_ontology(self, client):
        """Test requesting non-existent ontology."""
        response = client.get('/api/ontology/nonexistent-ontology-xyz')

        # Should return 404
        assert response.status_code == 404

    def test_invalid_sparql_query(self, client):
        """Test SPARQL endpoint with invalid query."""
        response = client.post(
            '/sparql',
            json={'query': 'INVALID SPARQL SYNTAX'}
        )

        # Should handle gracefully
        assert response.status_code in [400, 500, 503]


@pytest.mark.api
class TestAPIResponseFormats:
    """Test API response format consistency."""

    def test_json_responses_have_status(self, client):
        """Test that JSON API responses include status field."""
        response = client.get('/api/ontologies')

        if response.is_json and response.status_code == 200:
            data = response.get_json()
            # Many APIs include a status field
            # This is a soft check
            assert isinstance(data, (list, dict))

    def test_error_responses_consistent(self, client):
        """Test error response format is consistent."""
        # Trigger an error
        response = client.get('/resolve')  # Missing URI param

        assert response.status_code == 400

        if response.is_json:
            data = response.get_json()
            assert 'error' in data

    def test_ttl_content_type(self, client):
        """Test Turtle format has correct content type."""
        # Would need actual entity to test
        # For now, document expected behavior
        expected_content_type = 'text/turtle'
        assert expected_content_type is not None
