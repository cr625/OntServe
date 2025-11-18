"""
Test Source Text Integration

Tests the complete source text provenance pipeline:
1. Store entities with source text via MCP
2. Retrieve entities with provenance
3. Query RDF triples
4. Test ProEthica → OntServe integration

Run with: python tests/test_source_text_integration.py

Author: OntServe Team
Date: 2025-11-17
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import after path is set
from storage.postgresql_storage import PostgreSQLStorage
from storage.concept_manager import ConceptManager
from storage.source_text_manager import SourceTextManager
from servers.mcp_source_text_integration import (
    enhance_entity_submission_with_source_text,
    get_entity_with_provenance,
    enhance_entity_query_results
)


def test_basic_source_text_storage():
    """Test basic source text storage and retrieval."""
    print("\n" + "="*70)
    print("TEST 1: Basic Source Text Storage")
    print("="*70)

    try:
        # Initialize storage
        db_url = os.environ.get(
            'ONTSERVE_DB_URL',
            'postgresql://postgres:PASS@localhost:5432/ontserve'
        )

        storage_config = {'db_url': db_url}
        storage = PostgreSQLStorage(storage_config)
        concept_manager = ConceptManager(storage)
        source_text_manager = SourceTextManager(storage)

        # Test data - simulating ProEthica extraction
        entity_data = {
            'label': 'Engineer L (Test)',
            'category': 'Role',
            'description': 'Licensed professional engineer',
            'uri': 'http://proethica.org/ontology/test/case1#EngineerL',
            'confidence': 0.95,
            'source_text': 'Engineer L, a licensed professional engineer employed by XYZ Consulting, has many years of experience in stormwater control design.',
            'extracted_from_section': 'facts',
            'extraction_timestamp': datetime.now(),
            'extractor_name': 'Pass1RoleExtractor',
            'extraction_method': 'llm_extraction',
            'domain_id': 'engineering-ethics',
            'submitted_by': 'test_suite'
        }

        # Submit entity with source text
        print("\n1. Submitting entity with source text...")
        result = enhance_entity_submission_with_source_text(
            concept_manager,
            source_text_manager,
            entity_data,
            case_id='test-case-1'
        )

        print(f"   Submission success: {result.get('success')}")
        print(f"   Concept ID: {result.get('concept_id')}")
        print(f"   Source text stored: {result.get('source_text_stored')}")
        print(f"   Triples stored: {result.get('triples_count')}")

        if result.get('provenance'):
            print(f"   Provenance triples:")
            for triple in result['provenance'].get('triple_details', []):
                print(f"      - {triple['predicate']} ({triple['type']})")

        # Retrieve entity with provenance
        print("\n2. Retrieving entity provenance...")
        provenance = get_entity_with_provenance(
            source_text_manager,
            entity_data['uri']
        )

        if provenance:
            print(f"   Source text: {provenance.get('source_text', 'N/A')[:50]}...")
            print(f"   Extracted from: {provenance.get('extracted_from')}")
            print(f"   Generated at: {provenance.get('generated_at')}")
            print(f"   Derived from: {provenance.get('derived_from')}")
            print(f"   Total triples: {len(provenance.get('all_triples', []))}")

        print("\n✓ Test 1 PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Test 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_class_source_reference():
    """Test storing definitional source references on classes."""
    print("\n" + "="*70)
    print("TEST 2: Class Source Reference")
    print("="*70)

    try:
        # Initialize storage
        db_url = os.environ.get(
            'ONTSERVE_DB_URL',
            'postgresql://postgres:PASS@localhost:5432/ontserve'
        )

        storage_config = {'db_url': db_url}
        storage = PostgreSQLStorage(storage_config)
        source_text_manager = SourceTextManager(storage)

        # Get an ontology ID (engineering-ethics domain)
        query = """
            SELECT o.id, o.name
            FROM ontologies o
            JOIN domains d ON o.domain_id = d.id
            WHERE d.name = 'engineering-ethics'
            LIMIT 1
        """
        result = storage._execute_query(query, fetch_one=True)

        if not result:
            print("   No ontologies found, skipping class test")
            return True

        ontology_id = result['id']
        ontology_name = result['name']

        print(f"\n1. Using ontology: {ontology_name} (ID: {ontology_id})")

        # Store source reference for a test class
        class_uri = 'http://proethica.org/ontology/intermediate/TestProfessionalRole'
        source_ref = 'NSPE Code of Ethics, Section II.1'

        # First, insert a test class if it doesn't exist
        insert_query = """
            INSERT INTO ontology_entities (
                ontology_id, entity_type, uri, label, comment
            )
            VALUES (%s, 'class', %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING id
        """

        storage._execute_query(
            insert_query,
            (ontology_id, class_uri, 'Test Professional Role', 'Test class for source reference'),
            fetch_one=True
        )

        # Now store source reference
        print("\n2. Storing source reference on class...")
        result = source_text_manager.store_class_with_source_reference(
            ontology_id=ontology_id,
            entity_uri=class_uri,
            source_reference=source_ref
        )

        print(f"   Success: {result.get('success')}")
        print(f"   Entity URI: {result.get('entity_uri')}")
        print(f"   Source reference: {result.get('source_reference')}")

        # Retrieve source text
        print("\n3. Retrieving class source reference...")
        source_info = source_text_manager.get_entity_source_text(class_uri)

        if source_info:
            print(f"   Source text: {source_info.get('source_text')}")
            print(f"   Source type: {source_info.get('source_type')}")

        print("\n✓ Test 2 PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Test 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_batch_entity_storage():
    """Test batch storage of entities with source text."""
    print("\n" + "="*70)
    print("TEST 3: Batch Entity Storage")
    print("="*70)

    try:
        # Initialize storage
        db_url = os.environ.get(
            'ONTSERVE_DB_URL',
            'postgresql://postgres:PASS@localhost:5432/ontserve'
        )

        storage_config = {'db_url': db_url}
        storage = PostgreSQLStorage(storage_config)
        concept_manager = ConceptManager(storage)
        source_text_manager = SourceTextManager(storage)

        # Batch of entities from a case
        entities = [
            {
                'label': 'Engineer M (Test Batch)',
                'category': 'Role',
                'description': 'Senior engineer',
                'uri': 'http://proethica.org/ontology/test/case2#EngineerM',
                'confidence': 0.92,
                'source_text': 'Engineer M is a senior engineer with expertise in structural design.',
                'extraction_method': 'llm_extraction'
            },
            {
                'label': 'Client X (Test Batch)',
                'category': 'Role',
                'description': 'Client organization',
                'uri': 'http://proethica.org/ontology/test/case2#ClientX',
                'confidence': 0.89,
                'source_text': 'Client X contracted Engineer M to design a commercial building.',
                'extraction_method': 'llm_extraction'
            },
            {
                'label': 'Public Safety Principle (Test Batch)',
                'category': 'Principle',
                'description': 'Hold paramount public safety',
                'uri': 'http://proethica.org/ontology/test/case2#PublicSafetyPrinciple',
                'confidence': 0.98,
                'source_text': 'Engineers shall hold paramount the safety, health, and welfare of the public.',
                'extraction_method': 'llm_extraction'
            }
        ]

        print(f"\n1. Submitting batch of {len(entities)} entities...")

        from servers.mcp_source_text_integration import store_batch_entities_with_source_text

        result = store_batch_entities_with_source_text(
            concept_manager,
            source_text_manager,
            entities,
            case_id='test-case-2',
            section_type='facts'
        )

        print(f"   Success: {result.get('success')}")
        print(f"   Stored: {result.get('stored_count')}")
        print(f"   Failed: {result.get('failed_count')}")

        if result.get('stored_entities'):
            print(f"\n   Stored entities:")
            for entity in result['stored_entities']:
                print(f"      - {entity['label']} ({entity['category']}): "
                      f"{entity['triples_count']} triples")

        print("\n✓ Test 3 PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Test 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_query_rdf_triples():
    """Test querying RDF triples directly."""
    print("\n" + "="*70)
    print("TEST 4: RDF Triple Queries")
    print("="*70)

    try:
        # Initialize storage
        db_url = os.environ.get(
            'ONTSERVE_DB_URL',
            'postgresql://postgres:PASS@localhost:5432/ontserve'
        )

        storage_config = {'db_url': db_url}
        storage = PostgreSQLStorage(storage_config)

        # Query sourceText triples
        print("\n1. Querying sourceText triples...")
        query = """
            SELECT subject, object_literal, created_at
            FROM concept_triples
            WHERE predicate = 'http://proethica.org/ontology/provenance/sourceText'
            ORDER BY created_at DESC
            LIMIT 5
        """

        results = storage._execute_query(query, (), fetch_all=True)

        print(f"   Found {len(results)} sourceText triples")
        for row in results:
            subject = row['subject'].split('#')[-1] if '#' in row['subject'] else row['subject']
            source_text_preview = row['object_literal'][:50] + "..." if len(row['object_literal']) > 50 else row['object_literal']
            print(f"      - {subject}: {source_text_preview}")

        # Query PROV-O triples
        print("\n2. Querying PROV-O triples...")
        query = """
            SELECT predicate, COUNT(*) as count
            FROM concept_triples
            WHERE predicate LIKE 'http://www.w3.org/ns/prov#%%'
            GROUP BY predicate
        """

        results = storage._execute_query(query, (), fetch_all=True)

        print(f"   Found {len(results)} different PROV-O predicates")
        for row in results:
            pred_name = row['predicate'].split('#')[-1]
            print(f"      - {pred_name}: {row['count']} triples")

        # Use the view
        print("\n3. Querying entities_with_source_text view...")
        query = """
            SELECT entity_storage_type, entity_type, label, source_text_type
            FROM entities_with_source_text
            LIMIT 5
        """

        results = storage._execute_query(query, (), fetch_all=True)

        print(f"   Found {len(results)} entities with source text")
        for row in results:
            print(f"      - {row['label']} ({row['entity_type']}, {row['source_text_type']})")

        print("\n✓ Test 4 PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Test 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all source text integration tests."""
    print("\n" + "#"*70)
    print("# OntServe Source Text Integration Test Suite")
    print("#"*70)

    tests = [
        ("Basic Source Text Storage", test_basic_source_text_storage),
        ("Class Source Reference", test_class_source_reference),
        ("Batch Entity Storage", test_batch_entity_storage),
        ("RDF Triple Queries", test_query_rdf_triples)
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = test_func()
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
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
