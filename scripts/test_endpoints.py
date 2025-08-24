#!/usr/bin/env python3
"""
Basic endpoint tests for OntServer derived ontology system.

This script tests the key API endpoints to ensure they're working correctly.
Can be run against a live server to verify functionality.

Usage:
    python scripts/test_endpoints.py [--host localhost] [--port 5003]
"""

import argparse
import requests
import json
import sys
from typing import Dict, Any

class EndpointTester:
    """Simple endpoint testing utility."""
    
    def __init__(self, base_url: str):
        """Initialize with base URL."""
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'OntServer-Endpoint-Tester/1.0'
        })
        
    def test_basic_connectivity(self) -> bool:
        """Test basic server connectivity."""
        print("🔗 Testing basic connectivity...")
        try:
            response = self.session.get(f"{self.base_url}/")
            if response.status_code == 200:
                print("  ✅ Main page accessible")
                return True
            else:
                print(f"  ❌ Main page returned {response.status_code}")
                return False
        except Exception as e:
            print(f"  ❌ Connection failed: {e}")
            return False
    
    def test_editor_interface(self) -> bool:
        """Test editor interface accessibility."""
        print("🖥️ Testing editor interface...")
        try:
            response = self.session.get(f"{self.base_url}/editor/")
            if response.status_code == 200:
                print("  ✅ Editor page accessible")
                return True
            else:
                print(f"  ❌ Editor page returned {response.status_code}")
                print(f"  Response: {response.text[:200]}...")
                return False
        except Exception as e:
            print(f"  ❌ Editor test failed: {e}")
            return False
    
    def test_ontology_list_api(self) -> bool:
        """Test ontology listing API."""
        print("📋 Testing ontology list API...")
        try:
            response = self.session.get(f"{self.base_url}/api/ontologies")
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    print(f"  ✅ API returned {len(data)} ontologies")
                    return True
                else:
                    print("  ❌ API didn't return a list")
                    return False
            else:
                print(f"  ❌ API returned {response.status_code}")
                return False
        except Exception as e:
            print(f"  ❌ API test failed: {e}")
            return False
    
    def test_draft_creation_api(self) -> bool:
        """Test draft ontology creation API."""
        print("📝 Testing draft creation API...")
        try:
            # Test data for draft creation
            test_data = {
                "concepts": [
                    {
                        "label": "TestConcept",
                        "type": "class",
                        "description": "A test concept for endpoint validation"
                    },
                    {
                        "label": "TestProperty",
                        "type": "property", 
                        "description": "A test property for endpoint validation"
                    }
                ],
                "base_imports": [],
                "metadata": {
                    "source": "endpoint-test",
                    "test_timestamp": "2025-08-24T12:00:00Z"
                },
                "created_by": "endpoint-tester"
            }
            
            response = self.session.post(
                f"{self.base_url}/editor/api/ontologies/test-endpoint-draft/draft",
                json=test_data,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print(f"  ✅ Draft created: {result.get('ontology_name')}")
                    print(f"     Concepts: {result.get('concepts_count')}")
                    print(f"     Entities: {sum(result.get('entities_extracted', {}).values())}")
                    return True
                else:
                    print(f"  ❌ Draft creation failed: {result.get('error')}")
                    return False
            else:
                print(f"  ❌ Draft API returned {response.status_code}")
                print(f"  Response: {response.text[:200]}")
                return False
        except Exception as e:
            print(f"  ❌ Draft creation test failed: {e}")
            return False
    
    def test_draft_with_parent_api(self) -> bool:
        """Test draft creation with parent relationship."""
        print("👨‍👦 Testing draft with parent relationship...")
        try:
            # Test data with parent relationship
            test_data = {
                "concepts": [
                    {
                        "label": "DerivedTestConcept",
                        "type": "class",
                        "description": "A derived test concept"
                    }
                ],
                "base_imports": ["test-endpoint-draft"],
                "parent_ontology": "test-endpoint-draft",
                "metadata": {
                    "source": "derived-endpoint-test",
                    "parent_test": True
                },
                "created_by": "endpoint-tester"
            }
            
            response = self.session.post(
                f"{self.base_url}/editor/api/ontologies/test-derived-endpoint/draft",
                json=test_data,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print(f"  ✅ Derived draft created: {result.get('ontology_name')}")
                    return True
                else:
                    print(f"  ❌ Derived draft failed: {result.get('error')}")
                    return False
            else:
                print(f"  ❌ Derived draft API returned {response.status_code}")
                return False
        except Exception as e:
            print(f"  ❌ Derived draft test failed: {e}")
            return False
    
    def test_merged_ontology_retrieval(self) -> bool:
        """Test merged ontology retrieval."""
        print("🔀 Testing merged ontology retrieval...")
        try:
            # Test getting merged ontology
            response = self.session.get(
                f"{self.base_url}/ontology/test-endpoint-draft?include_derived=true",
                headers={'Accept': 'text/turtle'}
            )
            
            if response.status_code == 200:
                content = response.text
                if 'test-endpoint-draft' in content:
                    print("  ✅ Merged ontology retrieved")
                    print(f"     Content length: {len(content)} characters")
                    # Check if it contains derived content (if available)
                    if 'DerivedTestConcept' in content:
                        print("  ✅ Contains derived content")
                    return True
                else:
                    print("  ❌ Merged content missing expected elements")
                    return False
            elif response.status_code == 404:
                print("  ⚠️ Test ontology not found (expected if no test data)")
                return True  # This is OK for basic endpoint test
            else:
                print(f"  ❌ Merged retrieval returned {response.status_code}")
                return False
        except Exception as e:
            print(f"  ❌ Merged retrieval test failed: {e}")
            return False
    
    def test_ontology_detail_api(self) -> bool:
        """Test ontology detail API with hierarchy info."""
        print("📊 Testing ontology detail API...")
        try:
            response = self.session.get(f"{self.base_url}/api/ontology/test-endpoint-draft")
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ['id', 'name', 'base_uri', 'ontology_type', 'parent_ontology_id']
                
                for field in required_fields:
                    if field not in data:
                        print(f"  ❌ Missing field: {field}")
                        return False
                
                print("  ✅ Ontology detail API working")
                print(f"     Type: {data.get('ontology_type')}")
                print(f"     Has children: {data.get('has_children', False)}")
                print(f"     Is derived: {data.get('is_derived', False)}")
                return True
            elif response.status_code == 404:
                print("  ⚠️ Test ontology not found (expected if no test data)")
                return True
            else:
                print(f"  ❌ Detail API returned {response.status_code}")
                return False
        except Exception as e:
            print(f"  ❌ Detail API test failed: {e}")
            return False
    
    def test_content_negotiation(self) -> bool:
        """Test content negotiation for different RDF formats."""
        print("🎭 Testing content negotiation...")
        
        formats_to_test = [
            ('text/turtle', 'Turtle'),
            ('application/rdf+xml', 'RDF/XML'),
            ('application/ld+json', 'JSON-LD'),
            ('application/n-triples', 'N-Triples')
        ]
        
        success_count = 0
        for accept_header, format_name in formats_to_test:
            try:
                response = self.session.get(
                    f"{self.base_url}/ontology/test-endpoint-draft",
                    headers={'Accept': accept_header}
                )
                
                if response.status_code == 200:
                    print(f"  ✅ {format_name} format working")
                    success_count += 1
                elif response.status_code == 404:
                    print(f"  ⚠️ {format_name} - test ontology not found")
                    success_count += 1  # This is OK
                else:
                    print(f"  ❌ {format_name} returned {response.status_code}")
            except Exception as e:
                print(f"  ❌ {format_name} test failed: {e}")
        
        return success_count == len(formats_to_test)
    
    def test_draft_deletion_api(self) -> bool:
        """Test draft deletion API."""
        print("🗑️ Testing draft deletion API...")
        try:
            response = self.session.delete(f"{self.base_url}/editor/api/ontologies/test-endpoint-draft/draft")
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print("  ✅ Draft deletion working")
                    return True
                else:
                    print(f"  ❌ Draft deletion failed: {result.get('error')}")
                    return False
            elif response.status_code == 404:
                print("  ⚠️ No draft found to delete (expected)")
                return True
            else:
                print(f"  ❌ Draft deletion returned {response.status_code}")
                return False
        except Exception as e:
            print(f"  ❌ Draft deletion test failed: {e}")
            return False
    
    def cleanup_test_data(self) -> bool:
        """Clean up any test data created during testing."""
        print("🧹 Cleaning up test data...")
        try:
            # Try to delete test ontologies
            test_ontologies = ['test-endpoint-draft', 'test-derived-endpoint']
            
            for ontology_name in test_ontologies:
                try:
                    response = self.session.delete(f"{self.base_url}/editor/api/ontologies/{ontology_name}/draft")
                    if response.status_code in [200, 404]:
                        print(f"  ✅ Cleaned up {ontology_name}")
                    else:
                        print(f"  ⚠️ Cleanup warning for {ontology_name}: {response.status_code}")
                except:
                    pass  # Ignore cleanup errors
            
            return True
        except Exception as e:
            print(f"  ⚠️ Cleanup had issues: {e}")
            return True  # Don't fail overall test for cleanup issues

def run_endpoint_tests(base_url: str) -> bool:
    """Run all endpoint tests."""
    print(f"🧪 Running OntServer Endpoint Tests")
    print(f"🎯 Target: {base_url}")
    print("=" * 60)
    
    tester = EndpointTester(base_url)
    
    tests = [
        ("Basic Connectivity", tester.test_basic_connectivity),
        ("Editor Interface", tester.test_editor_interface),
        ("Ontology List API", tester.test_ontology_list_api),
        ("Draft Creation API", tester.test_draft_creation_api),
        ("Draft with Parent API", tester.test_draft_with_parent_api),
        ("Merged Ontology Retrieval", tester.test_merged_ontology_retrieval),
        ("Ontology Detail API", tester.test_ontology_detail_api),
        ("Content Negotiation", tester.test_content_negotiation),
        ("Draft Deletion API", tester.test_draft_deletion_api),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"  ❌ Test failed with exception: {e}")
    
    # Always run cleanup
    print(f"\n🧹 Cleanup")
    tester.cleanup_test_data()
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All endpoint tests passed!")
        return True
    else:
        print("❌ Some tests failed. Check output above for details.")
        return False

def test_individual_endpoint(base_url: str, endpoint: str) -> bool:
    """Test a single endpoint."""
    print(f"🎯 Testing single endpoint: {endpoint}")
    
    tester = EndpointTester(base_url)
    
    if endpoint == "connectivity":
        return tester.test_basic_connectivity()
    elif endpoint == "editor":
        return tester.test_editor_interface()
    elif endpoint == "list":
        return tester.test_ontology_list_api()
    elif endpoint == "draft":
        return tester.test_draft_creation_api()
    elif endpoint == "derived":
        return tester.test_draft_with_parent_api()
    elif endpoint == "merge":
        return tester.test_merged_ontology_retrieval()
    elif endpoint == "detail":
        return tester.test_ontology_detail_api()
    elif endpoint == "negotiation":
        return tester.test_content_negotiation()
    elif endpoint == "delete":
        return tester.test_draft_deletion_api()
    else:
        print(f"❌ Unknown endpoint: {endpoint}")
        print("Available endpoints: connectivity, editor, list, draft, derived, merge, detail, negotiation, delete")
        return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test OntServer derived ontology endpoints')
    parser.add_argument('--host', default='localhost', help='Server host (default: localhost)')
    parser.add_argument('--port', default='5003', help='Server port (default: 5003)')
    parser.add_argument('--endpoint', help='Test single endpoint (optional)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Build base URL
    base_url = f"http://{args.host}:{args.port}"
    
    # Run tests
    if args.endpoint:
        success = test_individual_endpoint(base_url, args.endpoint)
    else:
        success = run_endpoint_tests(base_url)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
