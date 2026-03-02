"""
ProEthica MCP Contract Tests

Validates that the MCP server's JSON-RPC interface matches the contract
expected by ProEthica's ExternalMCPClient. Tests tool names, parameter
names, and response shapes -- not data correctness.

These tests use the aiohttp test client fixture from conftest.py, which
spins up the MCP server in-process against the real database.
"""

import json
import pytest


def _parse_tool_result(data):
    """Extract the parsed JSON payload from an MCP tool call response."""
    assert "result" in data, f"Expected 'result' in response, got: {list(data.keys())}"
    assert "content" in data["result"]
    content_list = data["result"]["content"]
    assert len(content_list) >= 1
    assert content_list[0]["type"] == "text"
    return json.loads(content_list[0]["text"])


def _make_call_tool_request(tool_name, arguments, request_id=1):
    """Build a JSON-RPC call_tool request."""
    return {
        "jsonrpc": "2.0",
        "method": "call_tool",
        "params": {"name": tool_name, "arguments": arguments},
        "id": request_id,
    }


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

    async def test_list_tools_returns_all_expected(self, mcp_client):
        """list_tools must return every tool ProEthica references."""
        request = {
            "jsonrpc": "2.0",
            "method": "list_tools",
            "params": {},
            "id": 1,
        }
        resp = await mcp_client.post("/jsonrpc", json=request)
        assert resp.status == 200

        data = await resp.json()
        tool_names = {t["name"] for t in data["result"]["tools"]}
        for name in self.ALL_TOOLS:
            assert name in tool_names, f"Missing tool: {name}"

    async def test_tool_schemas_have_input_schema(self, mcp_client):
        """Every tool must expose an inputSchema with type=object."""
        request = {
            "jsonrpc": "2.0",
            "method": "list_tools",
            "params": {},
            "id": 2,
        }
        resp = await mcp_client.post("/jsonrpc", json=request)
        data = await resp.json()

        for tool in data["result"]["tools"]:
            schema = tool.get("inputSchema")
            assert schema is not None, f"Tool {tool['name']} missing inputSchema"
            assert schema["type"] == "object", (
                f"Tool {tool['name']} schema type is {schema['type']}, expected 'object'"
            )
            assert "properties" in schema, f"Tool {tool['name']} schema missing 'properties'"

    async def test_get_entities_by_category_schema(self, mcp_client):
        """Verify parameter names for get_entities_by_category."""
        request = {
            "jsonrpc": "2.0",
            "method": "list_tools",
            "params": {},
            "id": 3,
        }
        resp = await mcp_client.post("/jsonrpc", json=request)
        data = await resp.json()

        tools = {t["name"]: t for t in data["result"]["tools"]}
        schema = tools["get_entities_by_category"]["inputSchema"]
        assert "category" in schema["properties"]
        assert "domain_id" in schema["properties"]
        assert "category" in schema.get("required", [])

    async def test_get_entity_by_uri_schema(self, mcp_client):
        """Verify parameter names for get_entity_by_uri."""
        request = {
            "jsonrpc": "2.0",
            "method": "list_tools",
            "params": {},
            "id": 4,
        }
        resp = await mcp_client.post("/jsonrpc", json=request)
        data = await resp.json()

        tools = {t["name"]: t for t in data["result"]["tools"]}
        schema = tools["get_entity_by_uri"]["inputSchema"]
        assert "uri" in schema["properties"]
        assert "uri" in schema.get("required", [])

    async def test_get_entities_by_uris_schema(self, mcp_client):
        """Verify parameter names for get_entities_by_uris."""
        request = {
            "jsonrpc": "2.0",
            "method": "list_tools",
            "params": {},
            "id": 5,
        }
        resp = await mcp_client.post("/jsonrpc", json=request)
        data = await resp.json()

        tools = {t["name"]: t for t in data["result"]["tools"]}
        schema = tools["get_entities_by_uris"]["inputSchema"]
        assert "uris" in schema["properties"]
        assert "uris" in schema.get("required", [])

    async def test_get_entity_by_label_schema(self, mcp_client):
        """Verify parameter names for get_entity_by_label."""
        request = {
            "jsonrpc": "2.0",
            "method": "list_tools",
            "params": {},
            "id": 6,
        }
        resp = await mcp_client.post("/jsonrpc", json=request)
        data = await resp.json()

        tools = {t["name"]: t for t in data["result"]["tools"]}
        schema = tools["get_entity_by_label"]["inputSchema"]
        assert "label" in schema["properties"]
        assert "label" in schema.get("required", [])

    async def test_submit_candidate_concept_schema(self, mcp_client):
        """Verify parameter names for submit_candidate_concept."""
        request = {
            "jsonrpc": "2.0",
            "method": "list_tools",
            "params": {},
            "id": 7,
        }
        resp = await mcp_client.post("/jsonrpc", json=request)
        data = await resp.json()

        tools = {t["name"]: t for t in data["result"]["tools"]}
        schema = tools["submit_candidate_concept"]["inputSchema"]
        assert "concept" in schema["properties"]
        assert "concept" in schema.get("required", [])


# ---------------------------------------------------------------------------
# Tool response shape contracts
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestGetEntitiesByCategoryContract:
    """Validate get_entities_by_category response shape."""

    async def test_response_has_entities_and_count(self, mcp_client):
        req = _make_call_tool_request("get_entities_by_category", {
            "category": "Role",
            "domain_id": "engineering-ethics",
        })
        resp = await mcp_client.post("/jsonrpc", json=req)
        payload = _parse_tool_result(await resp.json())

        assert "entities" in payload
        assert "total_count" in payload
        assert "category" in payload
        assert "domain_id" in payload
        assert isinstance(payload["entities"], list)
        assert payload["category"] == "Role"

    async def test_nonexistent_category_returns_empty(self, mcp_client):
        req = _make_call_tool_request("get_entities_by_category", {
            "category": "NonExistent999",
            "domain_id": "engineering-ethics",
        })
        resp = await mcp_client.post("/jsonrpc", json=req)
        payload = _parse_tool_result(await resp.json())

        assert payload["entities"] == []
        assert payload["total_count"] == 0


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestGetEntityByLabelContract:
    """Validate get_entity_by_label response shape."""

    async def test_not_found_response(self, mcp_client):
        """Label that doesn't exist returns found=False."""
        req = _make_call_tool_request("get_entity_by_label", {
            "label": "ZZZ_Nonexistent_Entity_12345",
        })
        resp = await mcp_client.post("/jsonrpc", json=req)
        payload = _parse_tool_result(await resp.json())

        assert payload.get("found") is False or "error" in payload

    async def test_found_response_shape(self, mcp_client):
        """If an entity is found, response must have uri, label, definition, entity_type."""
        # Use a label likely to exist in the engineering-ethics ontology
        req = _make_call_tool_request("get_entity_by_label", {
            "label": "Role",
        })
        resp = await mcp_client.post("/jsonrpc", json=req)
        payload = _parse_tool_result(await resp.json())

        if payload.get("found"):
            assert "uri" in payload
            assert "label" in payload
            assert "definition" in payload
            assert "entity_type" in payload
            assert "source_ontology" in payload
        # If not found, that's OK -- just validating shape when found


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestGetEntityByUriContract:
    """Validate get_entity_by_uri response shape."""

    async def test_not_found_response(self, mcp_client):
        req = _make_call_tool_request("get_entity_by_uri", {
            "uri": "http://nonexistent.org/does-not-exist#Nothing",
        })
        resp = await mcp_client.post("/jsonrpc", json=req)
        payload = _parse_tool_result(await resp.json())

        assert payload.get("found") is False or "error" in payload

    async def test_found_response_shape(self, mcp_client):
        """If entity is found, validate the shape matches ExternalMCPClient expectations."""
        # Use the proethica-core Role class URI
        req = _make_call_tool_request("get_entity_by_uri", {
            "uri": "http://proethica.org/ontology/core#Role",
        })
        resp = await mcp_client.post("/jsonrpc", json=req)
        payload = _parse_tool_result(await resp.json())

        if payload.get("found"):
            assert "uri" in payload
            assert "label" in payload
            assert "definition" in payload
            assert "entity_type" in payload
            assert "source_ontology" in payload


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestGetEntitiesByUrisContract:
    """Validate get_entities_by_uris response shape."""

    async def test_empty_list(self, mcp_client):
        req = _make_call_tool_request("get_entities_by_uris", {"uris": []})
        resp = await mcp_client.post("/jsonrpc", json=req)
        payload = _parse_tool_result(await resp.json())

        # Empty input -> error or empty entities list
        assert "error" in payload or payload.get("entities") == []

    async def test_response_shape(self, mcp_client):
        req = _make_call_tool_request("get_entities_by_uris", {
            "uris": [
                "http://proethica.org/ontology/core#Role",
                "http://nonexistent.org/nothing#X",
            ],
        })
        resp = await mcp_client.post("/jsonrpc", json=req)
        payload = _parse_tool_result(await resp.json())

        assert "entities" in payload
        assert "not_found" in payload
        assert "found_count" in payload
        assert "not_found_count" in payload
        assert isinstance(payload["entities"], list)
        assert isinstance(payload["not_found"], list)


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestGetDomainInfoContract:
    """Validate get_domain_info response shape."""

    async def test_response_shape(self, mcp_client):
        req = _make_call_tool_request("get_domain_info", {
            "domain_id": "engineering-ethics",
        })
        resp = await mcp_client.post("/jsonrpc", json=req)
        payload = _parse_tool_result(await resp.json())

        # Either returns domain info or error (domain may not be in test DB)
        if "error" not in payload:
            assert "domain" in payload
            assert "stats" in payload


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestSparqlQueryContract:
    """Validate sparql_query response shape."""

    async def test_response_shape(self, mcp_client):
        req = _make_call_tool_request("sparql_query", {
            "query": "SELECT ?s WHERE { ?s a <http://www.w3.org/2002/07/owl#Class> } LIMIT 1",
            "domain_id": "engineering-ethics",
        })
        resp = await mcp_client.post("/jsonrpc", json=req)
        payload = _parse_tool_result(await resp.json())

        # Either results or error (SPARQL service may not be available)
        if "error" not in payload:
            assert "results" in payload
            assert "query" in payload
            assert "execution_time_ms" in payload


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestSubmitCandidateConceptContract:
    """Validate submit_candidate_concept response shape."""

    async def test_response_shape(self, mcp_client):
        req = _make_call_tool_request("submit_candidate_concept", {
            "concept": {
                "label": "ContractTestConcept",
                "category": "Principle",
                "uri": "http://proethica.org/ontology/test#ContractTestConcept",
                "description": "Test concept for contract validation",
            },
            "domain_id": "engineering-ethics",
            "submitted_by": "contract-test",
        })
        resp = await mcp_client.post("/jsonrpc", json=req)
        payload = _parse_tool_result(await resp.json())

        # Either success or error
        assert "success" in payload or "error" in payload


# ---------------------------------------------------------------------------
# JSON-RPC protocol contract
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestJsonRpcProtocolContract:
    """Verify JSON-RPC 2.0 protocol compliance."""

    async def test_response_has_jsonrpc_field(self, mcp_client):
        request = {
            "jsonrpc": "2.0",
            "method": "list_tools",
            "params": {},
            "id": 100,
        }
        resp = await mcp_client.post("/jsonrpc", json=request)
        data = await resp.json()
        assert data.get("jsonrpc") == "2.0"
        assert data.get("id") == 100

    async def test_unknown_method_returns_error(self, mcp_client):
        request = {
            "jsonrpc": "2.0",
            "method": "nonexistent_method",
            "params": {},
            "id": 101,
        }
        resp = await mcp_client.post("/jsonrpc", json=request)
        data = await resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32601

    async def test_root_endpoint_also_accepts_jsonrpc(self, mcp_client):
        """ProEthica sends to root '/' -- must work the same as '/jsonrpc'."""
        request = {
            "jsonrpc": "2.0",
            "method": "list_tools",
            "params": {},
            "id": 102,
        }
        resp = await mcp_client.post("/", json=request)
        assert resp.status == 200
        data = await resp.json()
        assert "result" in data
        assert "tools" in data["result"]

    async def test_tool_result_wrapped_in_content_array(self, mcp_client):
        """All call_tool results wrap payload as content[0].text JSON string."""
        req = _make_call_tool_request("get_entities_by_category", {
            "category": "Role",
        })
        resp = await mcp_client.post("/jsonrpc", json=req)
        data = await resp.json()

        result = data["result"]
        assert "content" in result
        assert isinstance(result["content"], list)
        assert result["content"][0]["type"] == "text"
        # Must be valid JSON
        json.loads(result["content"][0]["text"])
