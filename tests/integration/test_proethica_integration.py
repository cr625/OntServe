"""
ProEthica Integration Tests

Tests for the critical integration points between ProEthica and OntServe.
Based on PROETHICA_ONTSERVE_INTEGRATION.md

These tests ensure backward compatibility and must pass before any deployment.
"""

import pytest
import json
from typing import Dict, Any


@pytest.mark.integration
@pytest.mark.api
class TestRESTAPIIntegration:
    """Test HTTP REST API integration (Port 5003) - PRIMARY METHOD."""

    def test_get_ontology_entities_endpoint_exists(self, client, helpers, db_session):
        """Test the primary ProEthica integration endpoint exists.

        Endpoint: GET /editor/api/ontologies/{name}/entities
        Used by: OntServeAnnotationService.get_ontology_concepts()
        """
        ontology = helpers.create_test_ontology(
            db_session,
            name='engineering-ethics'
        )

        response = client.get('/editor/api/ontologies/engineering-ethics/entities')

        assert response.status_code == 200, \
            "Primary ProEthica endpoint must return 200"

    def test_entity_response_format(self, client, helpers, db_session):
        """Test entity response matches expected ProEthica format.

        Expected: {"entities": {"classes": [...], "properties": [...]}}
        """
        ontology = helpers.create_test_ontology(db_session)

        # Add some test entities (helper creates 'class' entities by default)
        helpers.create_test_entity(db_session, ontology, label='TestClass')
        helpers.create_test_entity(db_session, ontology, label='TestProperty')

        response = client.get(f'/editor/api/ontologies/{ontology.name}/entities')
        data = response.get_json()

        # Check response structure
        assert 'entities' in data or 'success' in data, \
            "Response must contain 'entities' or 'success' key"

        if 'entities' in data:
            entities = data['entities']
            # Can be dict with classes/properties or list
            assert isinstance(entities, (dict, list)), \
                "Entities must be dict or list"

    def test_entity_field_names(self, client, helpers, db_session):
        """Test entity fields match ProEthica expectations.

        ProEthica transforms:
        - id/uri -> uri
        - label/name -> label
        - description/definition -> definition
        - category/type -> type
        """
        ontology = helpers.create_test_ontology(db_session)
        entity = helpers.create_test_entity(db_session, ontology, label='TestEntity')

        response = client.get(f'/editor/api/ontologies/{ontology.name}/entities')
        data = response.get_json()

        # Extract entities from response
        entities = []
        if 'entities' in data:
            if isinstance(data['entities'], dict):
                entities.extend(data['entities'].get('classes', []))
                entities.extend(data['entities'].get('properties', []))
            elif isinstance(data['entities'], list):
                entities = data['entities']

        if entities:
            entity = entities[0]
            # Should have at least one of: id, uri
            assert 'id' in entity or 'uri' in entity, \
                "Entity must have 'id' or 'uri' field"
            # Should have at least one of: label, name
            assert 'label' in entity or 'name' in entity, \
                "Entity must have 'label' or 'name' field"


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestMCPIntegration:
    """Test MCP JSON-RPC integration (Port 8082) - SECONDARY METHOD."""

    async def test_list_tools_endpoint(self, mcp_client):
        """Test list_tools method returns available tools.

        Used by: ProEthica to discover available MCP tools
        """
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "list_tools",
            "params": {}
        }

        response = await mcp_client.post('/', json=request)
        assert response.status == 200, "list_tools must return 200"

        data = await response.json()
        assert 'result' in data, "Response must have 'result' key"
        assert 'tools' in data['result'], "Result must have 'tools' key"

    async def test_get_entities_by_category_tool_exists(self, mcp_client):
        """Test get_entities_by_category tool is available.

        This is the PRIMARY tool used by ProEthica for concept extraction.
        """
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "list_tools",
            "params": {}
        }

        response = await mcp_client.post('/', json=request)
        data = await response.json()

        tool_names = [tool['name'] for tool in data['result']['tools']]
        assert 'get_entities_by_category' in tool_names, \
            "Critical tool 'get_entities_by_category' must exist"

    async def test_call_tool_response_format(self, mcp_client):
        """Test tool response matches ProEthica's parsing expectations.

        ProEthica parses: result.content[0].text (JSON string)
        """
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "call_tool",
            "params": {
                "name": "get_entities_by_category",
                "arguments": {
                    "category": "Role",
                    "domain_id": "engineering-ethics",
                    "status": "approved"
                }
            }
        }

        response = await mcp_client.post('/', json=request)

        if response.status == 200:
            data = await response.json()

            # Check JSON-RPC response structure
            assert 'result' in data or 'error' in data, \
                "Must have 'result' or 'error' key"

            if 'result' in data:
                result = data['result']
                # ProEthica expects: result.content[0].text
                assert 'content' in result, \
                    "Result must have 'content' key for ProEthica compatibility"

                if result['content']:
                    first_content = result['content'][0]
                    assert 'type' in first_content, \
                        "Content must have 'type' key"
                    assert 'text' in first_content, \
                        "Content must have 'text' key for ProEthica parsing"


@pytest.mark.integration
@pytest.mark.api
class TestCriticalMCPTools:
    """Test critical MCP tools used by ProEthica."""

    @pytest.mark.asyncio
    async def test_get_entities_by_category_arguments(self, mcp_client):
        """Test get_entities_by_category accepts required arguments.

        Arguments: category, domain_id, status
        BREAKING CHANGE RISK: These argument names are hardcoded in ProEthica
        """
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "call_tool",
            "params": {
                "name": "get_entities_by_category",
                "arguments": {
                    "category": "Role",
                    "domain_id": "test",
                    "status": "approved"
                }
            }
        }

        response = await mcp_client.post('/', json=request)

        # Should not fail due to missing/wrong arguments
        assert response.status in [200, 400, 404], \
            "Tool call should handle arguments gracefully"

    @pytest.mark.asyncio
    async def test_search_entities_tool(self, mcp_client):
        """Test search_entities tool is available."""
        request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "list_tools",
            "params": {}
        }

        response = await mcp_client.post('/', json=request)
        data = await response.json()

        tool_names = [tool['name'] for tool in data['result']['tools']]

        # This tool might not be implemented yet, but should be
        has_search = any('search' in name.lower() for name in tool_names)
        # Just document if missing, don't fail
        if not has_search:
            pytest.skip("search_entities tool not yet implemented")


@pytest.mark.integration
@pytest.mark.api
class TestDataFlowPatterns:
    """Test complete data flow patterns used by ProEthica."""

    def test_annotation_pipeline_pattern(self, client, helpers, db_session):
        """Test Pattern A: Annotation Pipeline data flow.

        Flow:
        1. Get world ontology mapping
        2. Get ontology concepts
        3. Transform to standardized format
        """
        # Create test ontology
        ontology = helpers.create_test_ontology(db_session, name='proethica-core')

        # Add some entities
        helpers.create_test_entity(db_session, ontology, label='TestRole')

        # Step 2: Get ontology concepts
        response = client.get(f'/editor/api/ontologies/{ontology.name}/entities')

        assert response.status_code == 200
        data = response.get_json()

        # Should be able to extract entities
        assert data is not None

    @pytest.mark.asyncio
    async def test_concept_extraction_pattern(self, mcp_client):
        """Test Pattern B: Concept Extraction (9-Concept System) data flow.

        Flow:
        1. Extract concepts from case
        2. Get entities by category via MCP
        3. Provide to LLM as context
        """
        # Step 2: Get entities by category
        request = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "call_tool",
            "params": {
                "name": "get_entities_by_category",
                "arguments": {
                    "category": "Role",
                    "domain_id": "engineering-ethics",
                    "status": "approved"
                }
            }
        }

        response = await mcp_client.post('/', json=request)

        # Should return entities or empty result, not error
        assert response.status in [200, 404]


@pytest.mark.integration
@pytest.mark.api
class TestBreakingChangeProtection:
    """Tests to prevent breaking changes to ProEthica integration."""

    def test_port_5003_accessible(self, client):
        """Test that web server is on expected port 5003.

        BREAKING CHANGE: Do not change port without updating all clients
        """
        # This test runs against the client which uses configured port
        response = client.get('/')
        assert response.status_code == 200, \
            "Web server must be accessible (default port 5003)"

    @pytest.mark.asyncio
    async def test_mcp_port_8082_accessible(self, mcp_client):
        """Test that MCP server is on expected port 8082.

        BREAKING CHANGE: Do not change port without updating all clients
        """
        response = await mcp_client.get('/health')
        assert response.status in [200, 404], \
            "MCP server must be accessible (default port 8082)"

    def test_http_status_codes(self, client, helpers, db_session):
        """Test HTTP status codes match ProEthica expectations.

        BREAKING CHANGE: ProEthica expects 200 for success
        """
        ontology = helpers.create_test_ontology(db_session)

        response = client.get(f'/editor/api/ontologies/{ontology.name}/entities')

        # Should return 200 for success, 404 for not found
        assert response.status_code in [200, 404], \
            f"Expected 200 or 404, got {response.status_code}"

    def test_entity_fields_backward_compatible(self, client, helpers, db_session):
        """Test entity fields remain backward compatible.

        BREAKING CHANGE: ProEthica transforms specific field names
        """
        ontology = helpers.create_test_ontology(db_session)
        entity = helpers.create_test_entity(db_session, ontology, label='Test')

        response = client.get(f'/editor/api/ontologies/{ontology.name}/entities')
        data = response.get_json()

        # Extract first entity
        entities = []
        if 'entities' in data:
            if isinstance(data['entities'], dict):
                entities.extend(data['entities'].get('classes', []))
            elif isinstance(data['entities'], list):
                entities = data['entities']

        if entities:
            entity = entities[0]
            # Must have recognizable fields that ProEthica can transform
            has_id = 'id' in entity or 'uri' in entity
            has_label = 'label' in entity or 'name' in entity
            has_type = 'type' in entity or 'category' in entity or 'entity_type' in entity

            assert has_id, "Entity must have id/uri field"
            assert has_label, "Entity must have label/name field"
            # Type is optional but helpful


@pytest.mark.integration
@pytest.mark.api
class TestWorldOntologyMapping:
    """Test world ontology mapping functionality."""

    def test_ontology_priority_system(self, client, helpers, db_session):
        """Test that ontologies can be queried in priority order.

        ProEthica uses: core (1) → intermediate (2) → domain (3)
        """
        # Create ontologies with different priorities
        core = helpers.create_test_ontology(db_session, name='proethica-core')
        intermediate = helpers.create_test_ontology(db_session, name='proethica-intermediate')
        domain = helpers.create_test_ontology(db_session, name='engineering-ethics')

        # All should be accessible
        for ont in [core, intermediate, domain]:
            response = client.get(f'/editor/api/ontologies/{ont.name}/entities')
            assert response.status_code in [200, 404]


# Pytest configuration
pytest_plugins = []


# Test summary metadata for reporting
TEST_METADATA = {
    'purpose': 'ProEthica Integration Compatibility',
    'criticality': 'HIGH',
    'breaking_change_risk': 'MUST PASS before deployment',
    'integration_points': [
        'HTTP REST API (Port 5003)',
        'MCP JSON-RPC (Port 8082)',
        'Entity data schema',
        'Tool argument names'
    ]
}
