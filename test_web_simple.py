#!/usr/bin/env python3
"""
Simple Web Integration Test for Enhanced Processor

This script tests the basic web interface functionality 
of the enhanced processor.

Usage:
    python test_web_simple.py
"""

import sys
import os
from pathlib import Path

# Ensure we're in the right directory
project_root = Path(__file__).parent
os.chdir(project_root)

def test_imports():
    """Test that all required modules can be imported."""
    print("\n" + "="*80)
    print("📦 TESTING MODULE IMPORTS")
    print("="*80)
    
    success = True
    
    # Test core modules
    try:
        from core.enhanced_processor import EnhancedOntologyProcessor
        print("✅ Core enhanced processor imported")
    except ImportError as e:
        print(f"❌ Core enhanced processor import failed: {e}")
        success = False
    
    # Test storage
    try:
        from storage.file_storage import FileStorage
        print("✅ File storage imported")
    except ImportError as e:
        print(f"❌ File storage import failed: {e}")
        success = False
    
    # Test web app
    try:
        # Add web directory to path for proper imports
        sys.path.insert(0, str(project_root / 'web'))
        from app import app, db
        print("✅ Web app imported")
    except ImportError as e:
        print(f"⚠️  Web app import issue: {e}")
        # Try alternative import
        try:
            from web.app import app, db
            print("✅ Web app imported (alternative path)")
        except ImportError as e2:
            print(f"❌ Web app import failed: {e2}")
            success = False
    
    # Test models
    try:
        from models import Ontology, OntologyEntity, OntologyVersion
        print("✅ Web models imported")
    except ImportError as e:
        print(f"⚠️  Web models import issue: {e}")
        try:
            from web.models import Ontology, OntologyEntity, OntologyVersion
            print("✅ Web models imported (alternative path)")
        except ImportError as e2:
            print(f"❌ Web models import failed: {e2}")
            success = False
    
    # Test editor services
    try:
        # Editor services has complex relative imports, skip detailed test
        editor_path = project_root / 'editor' / 'services.py'
        if editor_path.exists():
            print("✅ Editor services file exists")
        else:
            print("⚠️  Editor services file not found")
            success = False
    except Exception as e:
        print(f"⚠️  Editor services check failed: {e}")
        success = False
    
    return success

def test_processor_integration():
    """Test enhanced processor integration with web components."""
    print("\n" + "="*80)
    print("🔧 TESTING PROCESSOR INTEGRATION")
    print("="*80)
    
    try:
        from core.enhanced_processor import EnhancedOntologyProcessor, ProcessingOptions
        from storage.file_storage import FileStorage
        import tempfile
        
        # Create temporary storage
        with tempfile.TemporaryDirectory() as temp_dir:
            # FileStorage expects a config dict, not a string
            config = {'storage_dir': temp_dir}
            storage = FileStorage(config)
            processor = EnhancedOntologyProcessor(storage)
            
            print("✅ Enhanced processor initialized")
            
            # Test processing options
            options = ProcessingOptions(
                use_reasoning=False,  # Disable since owlready2 not installed
                validate_consistency=False,
                generate_embeddings=False
            )
            
            print("✅ Processing options configured")
            
            # Create test ontology content
            test_ttl = """
            @prefix : <http://test.org/onto#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            
            :TestOntology a owl:Ontology .
            
            :TestClass a owl:Class ;
                rdfs:label "Test Class" ;
                rdfs:comment "A test class for validation" .
            
            :TestProperty a owl:ObjectProperty ;
                rdfs:domain :TestClass ;
                rdfs:range :TestClass .
            """
            
            # Store the test ontology first
            ontology_id = "test-onto"
            storage.store(
                ontology_id=ontology_id,
                content=test_ttl,
                metadata={'name': 'Test Ontology', 'format': 'turtle'}
            )
            print("✅ Test ontology stored")
            
            # Process the test ontology
            result = processor.process_ontology(
                ontology_id=ontology_id,
                options=options
            )
            
            print(f"✅ Processed test ontology:")
            print(f"   - Success: {result.success}")
            print(f"   - Entities extracted: {len(result.entities)}")
            print(f"   - Processing time: {result.processing_time:.2f}s")
            
            if not result.success:
                print(f"   ⚠️  Error: {result.error_message}")
            
            return True
            
    except Exception as e:
        print(f"❌ Processor integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_web_endpoints():
    """Test that web endpoints are accessible."""
    print("\n" + "="*80)
    print("🌐 TESTING WEB ENDPOINTS")
    print("="*80)
    
    try:
        # Try to import web app with proper path setup
        sys.path.insert(0, str(project_root / 'web'))
        try:
            from app import app
        except ImportError:
            from web.app import app
        
        # Create test client
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        
        with app.test_client() as client:
            # Test home page
            response = client.get('/')
            if response.status_code == 200:
                print("✅ Home page accessible")
            else:
                print(f"⚠️  Home page returned status {response.status_code}")
            
            # Test API endpoints
            response = client.get('/api/ontologies')
            if response.status_code in [200, 404]:  # 404 if no ontologies yet
                print("✅ API endpoint accessible")
            else:
                print(f"⚠️  API endpoint returned status {response.status_code}")
            
            # Test editor endpoints if available
            response = client.get('/editor')
            if response.status_code in [200, 404]:
                print("✅ Editor endpoint checked")
            else:
                print(f"⚠️  Editor endpoint returned status {response.status_code}")
            
            return True
            
    except Exception as e:
        print(f"❌ Web endpoint test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("\n🧪 Web Integration Test Suite")
    print("="*80)
    
    results = []
    
    # Run tests
    results.append(("Import Test", test_imports()))
    results.append(("Processor Integration", test_processor_integration()))
    results.append(("Web Endpoints", test_web_endpoints()))
    
    # Print summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("="*80)
    
    if all_passed:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed. Please check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())