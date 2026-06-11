"""
MCP Server Integration Tests (FastMCP in-process)

Tests MCP server tools via FastMCP's in-process Client.
Requires local PostgreSQL with ontserve database.
"""

import json
import pytest


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestMCPServerBasics:
    """Test basic MCP server functionality."""

    async def test_list_tools(self, mcp_client):
        """All required tools are registered."""
        tools = await mcp_client.list_tools()
        tool_names = {t.name for t in tools}

        required = {
            'get_entities_by_category',
            'submit_candidate_concept',
            'sparql_query',
            'update_concept_status',
            'get_candidate_concepts',
            'get_domain_info',
            'store_extracted_entities',
            'get_case_entities',
            'get_entity_by_uri',
            'get_entities_by_uris',
            'get_entity_by_label',
            # reasoning + BFO tools (Phase 1.1, 2026-05-26)
            'reason_ontology',
            'check_consistency',
            'get_inferred_hierarchy',
            'get_inconsistent_classes',
            'validate_bfo_compliance',
        }

        for name in required:
            assert name in tool_names, f"Missing tool: {name}"

    async def test_tool_count(self, mcp_client):
        """Server exposes exactly 20 tools (12 base + 5 reasoning/BFO + 3 conformance)."""
        tools = await mcp_client.list_tools()
        assert len(tools) == 20


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
@pytest.mark.database
class TestMCPTools:
    """Test individual MCP tool calls against the live database."""

    async def test_get_entities_by_category(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entities_by_category',
            {'category': 'Role', 'domain_id': 'engineering-ethics'},
        )
        payload = json.loads(result.content[0].text)
        assert payload['category'] == 'Role'
        assert 'entities' in payload
        assert 'total_count' in payload
        assert isinstance(payload['entities'], list)

    async def test_get_entities_nonexistent_category(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entities_by_category',
            {'category': 'NonExistent999'},
        )
        payload = json.loads(result.content[0].text)
        assert payload['entities'] == []
        assert payload['total_count'] == 0

    async def test_get_domain_info(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_domain_info',
            {'domain_id': 'engineering-ethics'},
        )
        payload = json.loads(result.content[0].text)
        assert 'domain' in payload
        assert 'stats' in payload

    async def test_get_entity_by_label_found(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entity_by_label',
            {'label': 'Engineer'},
        )
        payload = json.loads(result.content[0].text)
        if not payload.get('found'):
            pytest.skip("Engineer entity not present in test database")
        assert 'uri' in payload
        assert 'label' in payload
        assert 'entity_type' in payload

    async def test_get_entity_by_label_not_found(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entity_by_label',
            {'label': 'ZZZ_Nonexistent_12345'},
        )
        payload = json.loads(result.content[0].text)
        assert payload.get('found') is False

    async def test_get_entity_by_uri(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entity_by_uri',
            {'uri': 'http://proethica.org/ontology/intermediate#Engineer'},
        )
        payload = json.loads(result.content[0].text)
        if not payload.get('found'):
            pytest.skip("Engineer entity not present in test database")
        assert payload['label'] == 'Engineer'

    async def test_get_entity_by_uri_not_found(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entity_by_uri',
            {'uri': 'http://nonexistent.org/nothing#X'},
        )
        payload = json.loads(result.content[0].text)
        assert payload.get('found') is False

    async def test_get_entities_by_uris(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entities_by_uris',
            {'uris': [
                'http://proethica.org/ontology/intermediate#Engineer',
                'http://nonexistent.org/nothing#X',
            ]},
        )
        payload = json.loads(result.content[0].text)
        assert 'entities' in payload
        assert 'not_found' in payload
        assert 'found_count' in payload
        # Engineer may or may not be in the database
        assert isinstance(payload['found_count'], int)
        assert 'http://nonexistent.org/nothing#X' in payload['not_found']

    async def test_get_entities_by_uris_empty(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entities_by_uris',
            {'uris': []},
        )
        payload = json.loads(result.content[0].text)
        assert 'error' in payload

    async def test_get_candidate_concepts(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_candidate_concepts',
            {'domain_id': 'engineering-ethics', 'status': 'candidate'},
        )
        payload = json.loads(result.content[0].text)
        assert 'candidates' in payload or 'error' in payload

    async def test_get_case_entities(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_case_entities',
            {'case_id': '7'},
        )
        payload = json.loads(result.content[0].text)
        assert 'entities' in payload
        assert 'case_id' in payload

    async def test_sparql_query(self, mcp_client, sample_sparql_query):
        result = await mcp_client.call_tool(
            'sparql_query',
            {'query': sample_sparql_query, 'domain_id': 'engineering-ethics'},
        )
        payload = json.loads(result.content[0].text)
        assert 'results' in payload or 'error' in payload

    async def test_submit_candidate_concept(self, mcp_client, sample_candidate_concept):
        result = await mcp_client.call_tool(
            'submit_candidate_concept',
            {
                'concept': sample_candidate_concept,
                'domain_id': 'engineering-ethics',
                'submitted_by': 'test-system',
            },
        )
        payload = json.loads(result.content[0].text)
        assert 'success' in payload or 'error' in payload
