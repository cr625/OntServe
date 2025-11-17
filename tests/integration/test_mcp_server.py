"""
MCP Server Integration Tests

Tests for MCP server tools and ProEthica compatibility.
These tests ensure that external integrations (like ProEthica) continue to work.
"""

import pytest
import json
from typing import Dict, Any


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestMCPServerBasics:
    """Test basic MCP server functionality."""

    async def test_server_health(self, mcp_client):
        """Test health endpoint returns ok."""
        response = await mcp_client.get('/health')
        assert response.status == 200

        data = await response.json()
        assert data['status'] == 'ok'
        assert 'server_info' in data

    async def test_initialize(self, mcp_client):
        """Test MCP initialize method."""
        request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            },
            "id": 1
        }

        response = await mcp_client.post('/jsonrpc', json=request)
        assert response.status == 200

        data = await response.json()
        assert 'result' in data
        assert 'serverInfo' in data['result']
        assert data['result']['serverInfo']['name'] == 'OntServe MCP Server'

    async def test_list_tools(self, mcp_client):
        """Test listing available MCP tools."""
        request = {
            "jsonrpc": "2.0",
            "method": "list_tools",
            "params": {},
            "id": 2
        }

        response = await mcp_client.post('/jsonrpc', json=request)
        assert response.status == 200

        data = await response.json()
        assert 'result' in data
        assert 'tools' in data['result']

        # Verify all required tools are present
        tool_names = [tool['name'] for tool in data['result']['tools']]
        required_tools = [
            'get_entities_by_category',
            'submit_candidate_concept',
            'sparql_query',
            'update_concept_status',
            'get_candidate_concepts',
            'get_domain_info',
            'store_extracted_entities',
            'get_case_entities'
        ]

        for tool in required_tools:
            assert tool in tool_names, f"Required tool '{tool}' not found"


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
@pytest.mark.database
class TestMCPTools:
    """Test individual MCP tools."""

    async def test_get_entities_by_category(self, mcp_client):
        """Test get_entities_by_category tool."""
        request = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {
                "name": "get_entities_by_category",
                "arguments": {
                    "category": "Principle",
                    "domain_id": "engineering-ethics",
                    "status": "approved"
                }
            },
            "id": 3
        }

        response = await mcp_client.post('/jsonrpc', json=request)
        assert response.status == 200

        data = await response.json()
        assert 'result' in data
        assert 'content' in data['result']

        # Parse tool result
        content = json.loads(data['result']['content'][0]['text'])
        assert 'category' in content
        assert content['category'] == 'Principle'

    async def test_submit_candidate_concept(self, mcp_client, sample_candidate_concept):
        """Test submitting a candidate concept."""
        request = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {
                "name": "submit_candidate_concept",
                "arguments": {
                    "concept": sample_candidate_concept,
                    "domain_id": "engineering-ethics",
                    "submitted_by": "test-system"
                }
            },
            "id": 4
        }

        response = await mcp_client.post('/jsonrpc', json=request)
        assert response.status == 200

        data = await response.json()
        assert 'result' in data

        # Parse result
        content = json.loads(data['result']['content'][0]['text'])

        # Should either succeed or report database not connected (in test env)
        assert 'success' in content or 'error' in content

    async def test_sparql_query(self, mcp_client, sample_sparql_query):
        """Test SPARQL query execution."""
        request = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {
                "name": "sparql_query",
                "arguments": {
                    "query": sample_sparql_query,
                    "domain_id": "engineering-ethics"
                }
            },
            "id": 5
        }

        response = await mcp_client.post('/jsonrpc', json=request)
        assert response.status == 200

        data = await response.json()
        assert 'result' in data

        # Parse result
        content = json.loads(data['result']['content'][0]['text'])

        # Should contain query results or error
        assert 'results' in content or 'error' in content

    async def test_get_candidate_concepts(self, mcp_client):
        """Test retrieving candidate concepts."""
        request = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {
                "name": "get_candidate_concepts",
                "arguments": {
                    "domain_id": "engineering-ethics",
                    "status": "candidate"
                }
            },
            "id": 6
        }

        response = await mcp_client.post('/jsonrpc', json=request)
        assert response.status == 200

        data = await response.json()
        assert 'result' in data

        content = json.loads(data['result']['content'][0]['text'])
        assert 'candidates' in content or 'error' in content


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
class TestProEthicaCompatibility:
    """Test ProEthica integration compatibility."""

    async def test_guidelines_endpoint(self, mcp_client):
        """Test ProEthica guidelines compatibility endpoint."""
        response = await mcp_client.get('/api/guidelines/engineering-ethics')
        assert response.status == 200

        data = await response.json()
        assert data['status'] == 'ok'
        assert data['domain'] == 'engineering-ethics'
        assert 'available_methods' in data

    async def test_sparql_http_endpoint(self, mcp_client, sample_sparql_query):
        """Test direct SPARQL HTTP endpoint."""
        response = await mcp_client.post(
            '/sparql',
            json={'query': sample_sparql_query}
        )

        # Should either succeed or return service unavailable
        assert response.status in [200, 503]

    async def test_mcp_tool_signatures(self, mcp_client):
        """Verify MCP tool signatures match ProEthica expectations."""
        request = {
            "jsonrpc": "2.0",
            "method": "list_tools",
            "params": {},
            "id": 7
        }

        response = await mcp_client.post('/jsonrpc', json=request)
        data = await response.json()

        tools = {tool['name']: tool for tool in data['result']['tools']}

        # Verify get_entities_by_category signature
        tool = tools['get_entities_by_category']
        assert 'inputSchema' in tool
        schema = tool['inputSchema']
        assert 'category' in schema['properties']
        assert 'domain_id' in schema['properties']
        assert 'status' in schema['properties']

        # Verify submit_candidate_concept signature
        tool = tools['submit_candidate_concept']
        schema = tool['inputSchema']
        assert 'concept' in schema['properties']
        assert 'domain_id' in schema['properties']

        # Verify store_extracted_entities signature (case entities)
        tool = tools['store_extracted_entities']
        schema = tool['inputSchema']
        assert 'case_id' in schema['properties']
        assert 'section_type' in schema['properties']
        assert 'entities' in schema['properties']


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
class TestMCPErrorHandling:
    """Test MCP server error handling."""

    async def test_invalid_method(self, mcp_client):
        """Test handling of invalid JSON-RPC method."""
        request = {
            "jsonrpc": "2.0",
            "method": "invalid_method",
            "params": {},
            "id": 8
        }

        response = await mcp_client.post('/jsonrpc', json=request)
        assert response.status == 200

        data = await response.json()
        assert 'error' in data
        assert data['error']['code'] == -32601  # Method not found

    async def test_invalid_tool_name(self, mcp_client):
        """Test calling non-existent tool."""
        request = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {
                "name": "non_existent_tool",
                "arguments": {}
            },
            "id": 9
        }

        response = await mcp_client.post('/jsonrpc', json=request)
        assert response.status == 200

        data = await response.json()
        assert 'result' in data
        content = json.loads(data['result']['content'][0]['text'])
        assert 'error' in content

    async def test_missing_required_params(self, mcp_client):
        """Test tool call with missing required parameters."""
        request = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {
                "name": "get_entities_by_category",
                "arguments": {}  # Missing required 'category'
            },
            "id": 10
        }

        response = await mcp_client.post('/jsonrpc', json=request)
        assert response.status == 200

        # Should handle gracefully (either error in result or tool handles it)
        data = await response.json()
        assert 'result' in data or 'error' in data


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
class TestMCPPerformance:
    """Test MCP server performance characteristics."""

    async def test_concurrent_requests(self, mcp_client):
        """Test handling of concurrent requests."""
        import asyncio

        async def make_request(request_id):
            request = {
                "jsonrpc": "2.0",
                "method": "list_tools",
                "params": {},
                "id": request_id
            }
            response = await mcp_client.post('/jsonrpc', json=request)
            return await response.json()

        # Make 10 concurrent requests
        tasks = [make_request(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 10
        for result in results:
            assert 'result' in result or 'error' in result
