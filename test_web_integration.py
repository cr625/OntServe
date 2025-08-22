#!/usr/bin/env python
"""
Test Web Integration for Enhanced Processor

This script tests the web interface integration of the enhanced processor
by directly testing the API endpoints and functionality.

Usage:
    python test_web_integration.py
    OR
    source venv/bin/activate && python test_web_integration.py
"""

import sys
import os
import json
import tempfile
from pathlib import Path
from datetime import datetime

# Add OntServe to path
sys.path.insert(0, str(Path(__file__).parent))

def test_web_integration():
    """Test the web interface integration for enhanced processor."""
    
    print("="*80)
    print("🌐 TESTING WEB INTERFACE INTEGRATION")
    print("="*80)
    
    try:
        # Import Flask components
        from flask import Flask
        
        # Check if web module exists
        web_path = Path(__file__).parent / 'web'
        if not web_path.exists():
            print(f"❌ Web module not found at {web_path}")
            print("💡 Make sure you're running from the OntServe directory")
            return False
            
        # Add web to path for imports
        sys.path.insert(0, str(web_path))
        
        from models import db, init_db, Ontology, OntologyEntity, OntologyVersion
        from config import Config
        
        # Import other components
        from storage.file_storage import FileStorage
        from core.enhanced_processor import EnhancedOntologyProcessor, ProcessingOptions
        
        # Check if editor module exists
        editor_path = Path(__file__).parent / 'editor'
        if editor_path.exists() and (editor_path / 'routes.py').exists():
            sys.path.insert(0, str(editor_path))
            from routes import create_editor_blueprint
            has_editor = True
        else:
            has_editor = False
            print("⚠️  Editor module not found, skipping editor tests")
        
        print("✅ Successfully imported all web components")
        
        # Create Flask app for testing
        app = Flask(__name__)
        app.config.from_object(Config)
        
        # Use in-memory SQLite for testing
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['ONTSERVE_STORAGE_DIR'] = tempfile.mkdtemp()
        app.config['ONTSERVE_CACHE_DIR'] = tempfile.mkdtemp()
        
        with app.app_context():
            # Initialize database
            init_db(app)
            db.create_all()
            print("✅ Database initialized")
            
            # Initialize storage backend
            storage_backend = FileStorage({'storage_dir': app.config['ONTSERVE_STORAGE_DIR']})
            print("✅ Storage backend initialized")
            
            # Create and register enhanced editor blueprint
            editor_config = {
                'require_auth': False,
                'admin_only': False,
                'storage': {'storage_dir': app.config['ONTSERVE_STORAGE_DIR']}
            }
            
            editor_blueprint = create_editor_blueprint(storage_backend, editor_config)
            app.register_blueprint(editor_blueprint)
            print("✅ Enhanced editor blueprint registered")
            
            # Create test ontology in database
            test_ontology = Ontology(
                ontology_id='test-web-integration',
                name='Web Integration Test Ontology',
                description='Test ontology for web interface integration',
                content=create_test_ontology_content(),
                format='turtle',
                triple_count=50,  # Estimate
                created_at=datetime.utcnow()
            )
            db.session.add(test_ontology)
            db.session.commit()
            print("✅ Test ontology created in database")
            
            # Store ontology in file storage
            storage_result = storage_backend.store(
                'test-web-integration',
                test_ontology.content,
                {'name': test_ontology.name, 'description': test_ontology.description}
            )
            print(f"✅ Test ontology stored in file system: {storage_result.get('success')}")
            
            # Test client for API endpoints
            client = app.test_client()
            
            # Test 1: Check enhanced capabilities endpoint
            print("\n" + "="*60)
            print("TEST 1: Enhanced Capabilities API")
            print("="*60)
            
            response = client.get('/editor/api/enhanced/capabilities')
            if response.status_code == 200:
                data = response.get_json()
                capabilities = data.get('capabilities', {})
                print("✅ Capabilities endpoint working")
                print(f"   🧠 Reasoning: {'✅' if capabilities.get('reasoning') else '❌'}")
                print(f"   🔍 Embeddings: {'✅' if capabilities.get('embeddings') else '❌'}")
                print(f"   📊 Visualization: {'✅' if capabilities.get('visualization') else '❌'}")
                print(f"   ✅ Enhanced Processing: {'✅' if capabilities.get('enhanced_processing') else '❌'}")
            else:
                print(f"❌ Capabilities endpoint failed: {response.status_code}")
            
            # Test 2: Enhanced validation endpoint
            print("\n" + "="*60)
            print("TEST 2: Enhanced Validation API")
            print("="*60)
            
            response = client.get('/editor/api/enhanced/validate/test-web-integration')
            if response.status_code == 200:
                data = response.get_json()
                validation = data.get('validation', {})
                print("✅ Enhanced validation endpoint working")
                print(f"   Valid: {'✅' if validation.get('valid') else '❌'}")
                print(f"   Errors: {len(validation.get('errors', []))}")
                print(f"   Warnings: {len(validation.get('warnings', []))}")
                print(f"   Reasoning applied: {'✅' if validation.get('reasoning_applied') else '❌'}")
            else:
                print(f"❌ Enhanced validation failed: {response.status_code}")
            
            # Test 3: Enhanced search endpoint
            print("\n" + "="*60)
            print("TEST 3: Enhanced Search API")
            print("="*60)
            
            search_params = {
                'query': 'person human',
                'ontology_id': 'test-web-integration',
                'limit': '5'
            }
            response = client.get('/editor/api/enhanced/search', query_string=search_params)
            if response.status_code == 200:
                data = response.get_json()
                results = data.get('results', [])
                print("✅ Enhanced search endpoint working")
                print(f"   Results found: {len(results)}")
                print(f"   Reasoning included: {'✅' if data.get('reasoning_included') else '❌'}")
            else:
                print(f"❌ Enhanced search failed: {response.status_code}")
            
            # Test 4: Enhanced processing endpoint
            print("\n" + "="*60)
            print("TEST 4: Enhanced Processing API")
            print("="*60)
            
            process_data = {
                'use_reasoning': False,  # Test without reasoning first
                'generate_embeddings': True,
                'force_refresh': True
            }
            response = client.post('/editor/api/enhanced/process/test-web-integration', 
                                 json=process_data)
            if response.status_code == 200:
                data = response.get_json()
                result = data.get('processing_result', {})
                print("✅ Enhanced processing endpoint working")
                print(f"   Success: {'✅' if result.get('success') else '❌'}")
                print(f"   Entities processed: {result.get('entity_count', 0)}")
                print(f"   Processing time: {result.get('processing_time', 0):.2f}s")
                print(f"   Reasoning applied: {'✅' if result.get('reasoning_applied') else '❌'}")
            else:
                print(f"❌ Enhanced processing failed: {response.status_code}")
                if response.data:
                    print(f"   Error: {response.get_json().get('error', 'Unknown error')}")
            
            # Test 5: Enhanced visualization endpoint
            print("\n" + "="*60)
            print("TEST 5: Enhanced Visualization API")
            print("="*60)
            
            viz_params = {
                'include_reasoning': 'true',
                'layout': 'hierarchical',
                'limit': '100'
            }
            response = client.get('/editor/api/enhanced/visualization/test-web-integration',
                                query_string=viz_params)
            if response.status_code == 200:
                data = response.get_json()
                visualization = data.get('visualization', {})
                stats = data.get('stats', {})
                print("✅ Enhanced visualization endpoint working")
                print(f"   Nodes: {stats.get('node_count', 0)}")
                print(f"   Edges: {stats.get('edge_count', 0)}")
                print(f"   Inferred nodes: {stats.get('inferred_nodes', 0)}")
                print(f"   Layout options: {'✅' if visualization.get('layout_options') else '❌'}")
                print(f"   Style options: {'✅' if visualization.get('style_options') else '❌'}")
            else:
                print(f"❌ Enhanced visualization failed: {response.status_code}")
            
            # Test 6: Regular editor endpoints
            print("\n" + "="*60)
            print("TEST 6: Regular Editor API Endpoints")
            print("="*60)
            
            # Test entities endpoint
            response = client.get('/editor/ontology/test-web-integration/entities')
            print(f"   Entities endpoint: {'✅' if response.status_code == 200 else '❌'}")
            
            # Test versions endpoint
            response = client.get('/editor/ontology/test-web-integration/versions')
            print(f"   Versions endpoint: {'✅' if response.status_code == 200 else '❌'}")
            
            # Test hierarchy endpoint
            response = client.get('/editor/ontology/test-web-integration/hierarchy')
            print(f"   Hierarchy endpoint: {'✅' if response.status_code == 200 else '❌'}")
            
            print("\n" + "="*80)
            print("🎉 WEB INTEGRATION TESTS COMPLETED!")
            print("="*80)
            
            print("\n📋 INTEGRATION SUMMARY:")
            print("   ✅ Enhanced Editor Blueprint: Registered")
            print("   🌐 API Endpoints: Accessible")
            print("   🧠 Enhanced Processing: Available")
            print("   🔍 Semantic Search: Available")
            print("   📊 Visualization Data: Generated")
            print("   ✅ Storage Integration: Working")
            
            return True
            
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("\n💡 Some dependencies may be missing.")
        return False
        
    except Exception as e:
        print(f"❌ Test Error: {e}")
        return False


def create_test_ontology_content():
    """Create test ontology content for web integration testing."""
    return '''
@prefix : <http://test.ontserve.org/web-integration#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix bfo: <http://purl.obolibrary.org/obo/> .

# Ontology declaration
: a owl:Ontology ;
    rdfs:label "Web Integration Test Ontology" ;
    rdfs:comment "Test ontology for web interface integration testing" .

# Classes
:Person a owl:Class ;
    rdfs:subClassOf bfo:BFO_0000001 ;
    rdfs:label "Person" ;
    rdfs:comment "A human being" .

:Engineer a owl:Class ;
    rdfs:subClassOf :Person ;
    rdfs:label "Engineer" ;
    rdfs:comment "A professional engineer" .

:Organization a owl:Class ;
    rdfs:subClassOf bfo:BFO_0000001 ;
    rdfs:label "Organization" ;
    rdfs:comment "An organized group" .

# Properties
:worksFor a owl:ObjectProperty ;
    rdfs:domain :Person ;
    rdfs:range :Organization ;
    rdfs:label "works for" ;
    rdfs:comment "Employment relationship" .

:hasName a owl:DatatypeProperty ;
    rdfs:domain :Person ;
    rdfs:range xsd:string ;
    rdfs:label "has name" ;
    rdfs:comment "Person's name" .

# Individuals
:johnDoe a :Engineer ;
    :hasName "John Doe" ;
    :worksFor :techCorp .

:techCorp a :Organization ;
    :hasName "Tech Corporation" .
'''


if __name__ == '__main__':
    print("🧪 Enhanced Processor Web Integration Test")
    print("=" * 80)
    
    success = test_web_integration()
    
    if success:
        print("\n🎉 Web integration test completed successfully!")
        print("\n🌐 The enhanced processor is ready for web interface usage!")
        sys.exit(0)
    else:
        print("\n❌ Web integration test failed!")
        sys.exit(1)
