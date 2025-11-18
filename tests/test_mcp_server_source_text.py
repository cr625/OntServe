"""
Test MCP Server Source Text Integration

Tests the MCP server's source text handling via the store_extracted_entities endpoint.
Simulates what ProEthica would send when extracting entities with source text.

Run with: python tests/test_mcp_server_source_text.py

Author: OntServe Team
Date: 2025-11-17
"""

import sys
import os
import json
import asyncio
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import MCP server
from servers.mcp_server import OntServeMCPServer


async def test_mcp_store_entities_with_source_text():
    """Test MCP server's store_extracted_entities with source text."""
    print("\n" + "="*70)
    print("TEST: MCP Server Source Text Integration")
    print("="*70)

    try:
        # Initialize MCP server
        print("\n1. Initializing MCP server...")
        server = OntServeMCPServer()

        if not server.db_connected:
            print("   ✗ Database not connected, skipping test")
            return False

        print("   ✓ MCP server initialized")
        print(f"   Database: Connected")
        print(f"   Concept Manager: {server.concept_manager is not None}")
        print(f"   Source Text Manager: {server.source_text_manager is not None}")

        # Simulate ProEthica entity extraction
        print("\n2. Simulating ProEthica entity extraction...")

        # This is the format ProEthica sends when extracting entities
        mcp_payload = {
            "case_id": "mcp-test-1",
            "section_type": "facts",
            "entities": [
                {
                    "label": "Senior Engineer (MCP Test)",
                    "category": "Role",
                    "description": "Senior professional engineer with 15 years experience",
                    "confidence": 0.94,
                    "source_text": "Senior Engineer T has 15 years of experience in civil engineering and holds licenses in three states."
                },
                {
                    "label": "Public Safety Paramount (MCP Test)",
                    "category": "Principle",
                    "description": "Hold paramount the safety of the public",
                    "confidence": 0.98,
                    "source_text": "Engineers shall hold paramount the safety, health, and welfare of the public in the performance of their professional duties."
                },
                {
                    "label": "Design Review Obligation (MCP Test)",
                    "category": "Obligation",
                    "description": "Obligation to review designs for public safety",
                    "confidence": 0.91,
                    "source_text": "The engineer has an obligation to thoroughly review all designs to ensure they meet public safety standards."
                }
            ],
            "extraction_session": {
                "pass": "1",
                "timestamp": "2025-11-17T20:00:00",
                "llm_model": "claude-sonnet-4.5"
            }
        }

        print(f"   Entities to store: {len(mcp_payload['entities'])}")
        for entity in mcp_payload['entities']:
            print(f"      - {entity['label']} ({entity['category']})")
            print(f"        Source: '{entity['source_text'][:50]}...'")

        # Call MCP handler (simulating MCP tool call)
        print("\n3. Calling MCP store_extracted_entities handler...")
        result = await server._handle_store_extracted_entities(mcp_payload)

        if result.get("success"):
            print(f"   ✓ Success!")
            print(f"   Case ID: {result.get('case_id')}")
            print(f"   Section: {result.get('section_type')}")
            print(f"   Stored: {result.get('stored_count')} entities")
            print(f"   Method: {result.get('method')}")

            print("\n   Stored entities:")
            for entity in result.get('entities', []):
                print(f"      - {entity['label']} ({entity['category']})")
                print(f"        Concept ID: {entity['concept_id']}")
                print(f"        Source text stored: {entity.get('source_text_stored', 'N/A')}")
                print(f"        RDF triples: {entity.get('triples_count', 0)}")
        else:
            print(f"   ✗ Failed: {result.get('error')}")
            return False

        # Verify in database
        print("\n4. Verifying in database...")

        # Query concept_triples for source text
        query = """
            SELECT subject, object_literal
            FROM concept_triples
            WHERE predicate = 'http://proethica.org/ontology/provenance/sourceText'
            AND subject LIKE '%%mcp-test-1%%'
            LIMIT 5
        """

        results = server.storage._execute_query(query, (), fetch_all=True)

        print(f"   Found {len(results)} sourceText triples for MCP test entities")
        for row in results:
            subject_name = row['subject'].split('#')[-1]
            source_preview = row['object_literal'][:60] + "..."
            print(f"      - {subject_name}: {source_preview}")

        # Query PROV-O triples
        query = """
            SELECT COUNT(*) as count
            FROM concept_triples
            WHERE subject LIKE '%%mcp-test-1%%'
            AND (predicate LIKE 'http://www.w3.org/ns/prov#%%%%'
                 OR predicate LIKE 'http://proethica.org/ontology/provenance/%%%%')
        """

        result = server.storage._execute_query(query, (), fetch_one=True)
        total_triples = result['count'] if result else 0

        print(f"\n   Total provenance triples for MCP test: {total_triples}")
        print(f"   Expected: {3 * 6} (3 entities × 6 triples each)")

        if total_triples == 18:
            print("   ✓ Correct number of triples!")
        else:
            print(f"   ⚠ Triple count mismatch (expected 18, got {total_triples})")

        print("\n✓ Test PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_mcp_json_rpc_format():
    """Test full JSON-RPC formatted request (as Claude would send)."""
    print("\n" + "="*70)
    print("TEST: MCP JSON-RPC Request Format")
    print("="*70)

    try:
        # Initialize MCP server
        server = OntServeMCPServer()

        if not server.db_connected:
            print("   Database not connected, skipping test")
            return False

        # Simulate full JSON-RPC request
        print("\n1. Simulating JSON-RPC call_tool request...")

        json_rpc_request = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "call_tool",
            "params": {
                "name": "store_extracted_entities",
                "arguments": {
                    "case_id": "json-rpc-test",
                    "section_type": "discussion",
                    "entities": [
                        {
                            "label": "Consulting Engineer (JSON-RPC Test)",
                            "category": "Role",
                            "description": "Independent consulting engineer",
                            "confidence": 0.87,
                            "source_text": "The consulting engineer provides independent professional opinions on engineering matters."
                        }
                    ]
                }
            }
        }

        print(f"   Request method: {json_rpc_request['method']}")
        print(f"   Tool: {json_rpc_request['params']['name']}")
        print(f"   Arguments: {len(json_rpc_request['params']['arguments'])} fields")

        # Process through MCP server
        print("\n2. Processing request...")
        response = await server._process_request(json_rpc_request)

        print(f"   Response ID: {response.get('id')}")
        print(f"   JSON-RPC version: {response.get('jsonrpc')}")

        if "result" in response:
            result_json = json.loads(response['result']['content'][0]['text'])
            print(f"   ✓ Success!")
            print(f"   Stored: {result_json.get('stored_count')} entities")
        else:
            print(f"   ✗ Error: {response.get('error')}")
            return False

        print("\n✓ Test PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all MCP server integration tests."""
    print("\n" + "#"*70)
    print("# MCP Server Source Text Integration Tests")
    print("#"*70)

    tests = [
        ("MCP Store Entities", test_mcp_store_entities_with_source_text),
        ("JSON-RPC Format", test_mcp_json_rpc_format)
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = await test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\nTest {test_name} crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status:12} {test_name}")

    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n🎉 All MCP server tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
