"""
ProEthica MCP Contract Tests (FastMCP in-process)

Validates that the MCP server's tool catalog and response shapes match
the contract expected by ProEthica's MCPTransport client. Tests tool
names, parameter schemas, and response shapes -- not data correctness.

Uses FastMCP's in-process Client (no HTTP server needed).
"""

import json
import pytest


def _payload(result) -> dict:
    """Extract parsed JSON from a CallToolResult."""
    return json.loads(result.content[0].text)


# ---------------------------------------------------------------------------
# Tool listing contract
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestToolListContract:
    """Verify the tool catalog matches ProEthica's expectations."""

    PROETHICA_TOOLS = [
        "get_entities_by_category",
        "get_entity_by_label",
        "get_entity_by_uri",
        "get_entities_by_uris",
        "get_domain_info",
        "sparql_query",
        "submit_candidate_concept",
    ]

    ALL_TOOLS = PROETHICA_TOOLS + [
        "update_concept_status",
        "get_candidate_concepts",
        "store_extracted_entities",
        "get_case_entities",
    ]

    async def test_all_expected_tools_present(self, mcp_client):
        tools = await mcp_client.list_tools()
        tool_names = {t.name for t in tools}
        for name in self.ALL_TOOLS:
            assert name in tool_names, f"Missing tool: {name}"

    async def test_tools_have_input_schema(self, mcp_client):
        tools = await mcp_client.list_tools()
        for tool in tools:
            schema = tool.inputSchema
            assert schema is not None, f"Tool {tool.name} missing inputSchema"
            assert schema.get("type") == "object", (
                f"Tool {tool.name} schema type is {schema.get('type')}"
            )
            assert "properties" in schema, f"Tool {tool.name} missing properties"

    async def test_get_entities_by_category_schema(self, mcp_client):
        tools = await mcp_client.list_tools()
        schema = {t.name: t.inputSchema for t in tools}["get_entities_by_category"]
        assert "category" in schema["properties"]
        assert "domain_id" in schema["properties"]
        assert "category" in schema.get("required", [])

    async def test_get_entity_by_uri_schema(self, mcp_client):
        tools = await mcp_client.list_tools()
        schema = {t.name: t.inputSchema for t in tools}["get_entity_by_uri"]
        assert "uri" in schema["properties"]
        assert "uri" in schema.get("required", [])

    async def test_get_entities_by_uris_schema(self, mcp_client):
        tools = await mcp_client.list_tools()
        schema = {t.name: t.inputSchema for t in tools}["get_entities_by_uris"]
        assert "uris" in schema["properties"]
        assert "uris" in schema.get("required", [])

    async def test_get_entity_by_label_schema(self, mcp_client):
        tools = await mcp_client.list_tools()
        schema = {t.name: t.inputSchema for t in tools}["get_entity_by_label"]
        assert "label" in schema["properties"]
        assert "label" in schema.get("required", [])

    async def test_submit_candidate_concept_schema(self, mcp_client):
        tools = await mcp_client.list_tools()
        schema = {t.name: t.inputSchema for t in tools}["submit_candidate_concept"]
        assert "concept" in schema["properties"]
        assert "concept" in schema.get("required", [])

    async def test_store_extracted_entities_schema(self, mcp_client):
        tools = await mcp_client.list_tools()
        schema = {t.name: t.inputSchema for t in tools}["store_extracted_entities"]
        assert "case_id" in schema["properties"]
        assert "section_type" in schema["properties"]
        assert "entities" in schema["properties"]


# ---------------------------------------------------------------------------
# Tool response shape contracts
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestGetEntitiesByCategoryContract:

    async def test_response_shape(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entities_by_category',
            {'category': 'Role', 'domain_id': 'engineering-ethics'},
        )
        payload = _payload(result)
        assert 'entities' in payload
        assert 'total_count' in payload
        assert 'category' in payload
        assert 'domain_id' in payload
        assert isinstance(payload['entities'], list)
        assert payload['category'] == 'Role'

    async def test_nonexistent_category_returns_empty(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entities_by_category',
            {'category': 'NonExistent999', 'domain_id': 'engineering-ethics'},
        )
        payload = _payload(result)
        assert payload['entities'] == []
        assert payload['total_count'] == 0


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestGetEntityByLabelContract:

    async def test_not_found(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entity_by_label',
            {'label': 'ZZZ_Nonexistent_Entity_12345'},
        )
        payload = _payload(result)
        assert payload.get('found') is False

    async def test_found_response_shape(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entity_by_label',
            {'label': 'Engineer'},
        )
        payload = _payload(result)
        if payload.get('found'):
            for key in ('uri', 'label', 'definition', 'entity_type', 'source_ontology'):
                assert key in payload, f"Missing key: {key}"


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestGetEntityByUriContract:

    async def test_not_found(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entity_by_uri',
            {'uri': 'http://nonexistent.org/does-not-exist#Nothing'},
        )
        payload = _payload(result)
        assert payload.get('found') is False

    async def test_found_response_shape(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entity_by_uri',
            {'uri': 'http://proethica.org/ontology/intermediate#Engineer'},
        )
        payload = _payload(result)
        if payload.get('found'):
            for key in ('uri', 'label', 'definition', 'entity_type', 'source_ontology'):
                assert key in payload, f"Missing key: {key}"


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestGetEntitiesByUrisContract:

    async def test_empty_list(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entities_by_uris',
            {'uris': []},
        )
        payload = _payload(result)
        assert 'error' in payload or payload.get('entities') == []

    async def test_response_shape(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_entities_by_uris',
            {'uris': [
                'http://proethica.org/ontology/intermediate#Engineer',
                'http://nonexistent.org/nothing#X',
            ]},
        )
        payload = _payload(result)
        assert 'entities' in payload
        assert 'not_found' in payload
        assert 'found_count' in payload
        assert 'not_found_count' in payload
        assert isinstance(payload['entities'], list)
        assert isinstance(payload['not_found'], list)


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestGetDomainInfoContract:

    async def test_response_shape(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_domain_info',
            {'domain_id': 'engineering-ethics'},
        )
        payload = _payload(result)
        if 'error' not in payload:
            assert 'domain' in payload
            assert 'stats' in payload


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestSparqlQueryContract:

    async def test_response_shape(self, mcp_client, sample_sparql_query):
        result = await mcp_client.call_tool(
            'sparql_query',
            {'query': sample_sparql_query, 'domain_id': 'engineering-ethics'},
        )
        payload = _payload(result)
        if 'error' not in payload:
            assert 'results' in payload
            assert 'query' in payload
            assert 'execution_time_ms' in payload


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestGetCaseEntitiesContract:

    async def test_response_shape(self, mcp_client):
        result = await mcp_client.call_tool(
            'get_case_entities',
            {'case_id': '7'},
        )
        payload = _payload(result)
        assert 'entities' in payload
        assert 'case_id' in payload
        assert 'total_count' in payload
