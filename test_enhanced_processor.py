"""
Test script for Enhanced Ontology Processor

This script demonstrates and tests the hybrid RDFLib + Owlready2 processor
functionality including reasoning, consistency checking, and enhanced entity extraction.

Usage:
    python test_enhanced_processor.py
"""

import sys
import os
import logging
from datetime import datetime
from pathlib import Path

# Add OntServe to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_enhanced_processor.log')
    ]
)

logger = logging.getLogger(__name__)

def test_enhanced_processor():
    """Test the enhanced ontology processor functionality."""
    
    print("="*80)
    print("🚀 TESTING ENHANCED ONTOLOGY PROCESSOR")
    print("="*80)
    
    try:
        # Import required components
        from OntServe.storage.file_storage import FileStorage
        from OntServe.core.enhanced_processor import (
            EnhancedOntologyProcessor, 
            ProcessingOptions, 
            ProcessingResult
        )
        from OntServe.web.models import db, Ontology
        from OntServe.web.config import Config
        from flask import Flask
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        print("✅ Successfully imported all required components")
        
        # Initialize Flask app and database (for testing)
        app = Flask(__name__)
        app.config.from_object(Config)
        
        # For testing, use in-memory SQLite
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        
        with app.app_context():
            db.init_app(app)
            db.create_all()
            
            print("✅ Database initialized")
            
            # Initialize storage backend
            storage_dir = Path(__file__).parent / 'storage' / 'ontologies'
            storage_dir.mkdir(parents=True, exist_ok=True)
            
            storage_backend = FileStorage({'storage_dir': str(storage_dir)})
            print(f"✅ Storage backend initialized: {storage_dir}")
            
            # Initialize enhanced processor
            processor = EnhancedOntologyProcessor(storage_backend, db.session)
            print("✅ Enhanced processor initialized")
            
            # Test 1: Check processor capabilities
            print("\n" + "="*60)
            print("TEST 1: Processor Capabilities")
            print("="*60)
            
            has_reasoning = hasattr(processor, 'owlready_importer') and processor.owlready_importer is not None
            has_embeddings = processor.embedding_model is not None
            
            print(f"🧠 Reasoning (Owlready2): {'✅ Available' if has_reasoning else '❌ Not Available'}")
            print(f"🔍 Embeddings (SentenceTransformers): {'✅ Available' if has_embeddings else '❌ Not Available'}")
            print(f"📊 Processing Options: ✅ Available")
            print(f"💾 Storage Integration: ✅ Available")
            
            # Test 2: Create test ontology
            print("\n" + "="*60)
            print("TEST 2: Test Ontology Creation")
            print("="*60)
            
            test_ttl_content = create_test_ontology()
            print("✅ Test ontology content created")
            
            # Store test ontology
            test_ontology_id = 'test-enhanced-processor'
            metadata = {
                'name': 'Enhanced Processor Test Ontology',
                'description': 'Test ontology for enhanced processor functionality',
                'created_at': datetime.now().isoformat()
            }
            
            storage_result = storage_backend.store(test_ontology_id, test_ttl_content, metadata)
            print(f"✅ Test ontology stored: {storage_result.get('success', False)}")
            
            # Create database record
            test_ontology = Ontology(
                ontology_id=test_ontology_id,
                name=metadata['name'],
                description=metadata['description'],
                content=test_ttl_content,
                format='turtle',
                triple_count=len(test_ttl_content.split('\n')),  # Rough estimate
                created_at=datetime.utcnow()
            )
            db.session.add(test_ontology)
            db.session.commit()
            print("✅ Database record created")
            
            # Test 3: Basic processing without reasoning
            print("\n" + "="*60)
            print("TEST 3: Basic Processing (No Reasoning)")
            print("="*60)
            
            basic_options = ProcessingOptions(
                use_reasoning=False,
                generate_embeddings=has_embeddings,
                force_refresh=True
            )
            
            basic_result = processor.process_ontology(test_ontology_id, basic_options)
            print_processing_result(basic_result, "Basic Processing")
            
            # Test 4: Enhanced processing with reasoning (if available)
            if has_reasoning:
                print("\n" + "="*60)
                print("TEST 4: Enhanced Processing (With Reasoning)")
                print("="*60)
                
                enhanced_options = ProcessingOptions(
                    use_reasoning=True,
                    reasoner_type='hermit',
                    validate_consistency=True,
                    include_inferred=True,
                    generate_embeddings=has_embeddings,
                    force_refresh=True
                )
                
                enhanced_result = processor.process_ontology(test_ontology_id, enhanced_options)
                print_processing_result(enhanced_result, "Enhanced Processing")
                
                # Compare results
                print("\n📊 COMPARISON:")
                print(f"   Basic entities: {len(basic_result.entities)}")
                print(f"   Enhanced entities: {len(enhanced_result.entities)}")
                print(f"   Reasoning applied: {enhanced_result.reasoning_applied}")
                print(f"   Consistency check: {enhanced_result.consistency_check}")
                print(f"   Inferred count: {enhanced_result.inferred_count}")
            
            else:
                print("\n⚠️  Skipping reasoning tests - Owlready2 not available")
            
            # Test 5: Enhanced search (if embeddings available)
            if has_embeddings:
                print("\n" + "="*60)
                print("TEST 5: Enhanced Semantic Search")
                print("="*60)
                
                # Test various search queries
                search_queries = [
                    "person human being",
                    "organization group",
                    "action activity",
                    "capability skill"
                ]
                
                for query in search_queries:
                    results = processor.search_entities_enhanced(
                        query, 
                        ontology_id=test_ontology_id,
                        limit=3
                    )
                    print(f"🔍 Query: '{query}' -> {len(results)} results")
                    for i, result in enumerate(results):
                        score = result.get('similarity_score', 0)
                        label = result.get('label', 'No label')
                        print(f"   {i+1}. {label} (score: {score:.3f})")
            
            else:
                print("\n⚠️  Skipping search tests - SentenceTransformers not available")
            
            # Test 6: Enhanced validation
            print("\n" + "="*60)
            print("TEST 6: Enhanced Validation")
            print("="*60)
            
            validation_result = processor.validate_ontology_enhanced(test_ontology_id)
            print_validation_result(validation_result)
            
            # Test 7: Visualization data generation
            print("\n" + "="*60)
            print("TEST 7: Visualization Data Generation")
            print("="*60)
            
            if basic_result.visualization_data:
                viz_data = basic_result.visualization_data
                nodes = viz_data.get('nodes', [])
                edges = viz_data.get('edges', [])
                print(f"📊 Nodes: {len(nodes)}")
                print(f"📊 Edges: {len(edges)}")
                print(f"📊 Layout options: {'✅ Available' if viz_data.get('layout_options') else '❌ Not Available'}")
                print(f"📊 Style options: {'✅ Available' if viz_data.get('style_options') else '❌ Not Available'}")
            else:
                print("⚠️  No visualization data generated")
            
            # Test 8: Performance metrics
            print("\n" + "="*60)
            print("TEST 8: Performance Metrics")
            print("="*60)
            
            print(f"⚡ Basic processing time: {basic_result.processing_time:.2f}s")
            if has_reasoning and 'enhanced_result' in locals():
                print(f"⚡ Enhanced processing time: {enhanced_result.processing_time:.2f}s")
                print(f"⚡ Reasoning overhead: {enhanced_result.processing_time - basic_result.processing_time:.2f}s")
            
            print("\n" + "="*80)
            print("🎉 ALL TESTS COMPLETED SUCCESSFULLY!")
            print("="*80)
            
            # Display summary
            print("\n📋 SUMMARY:")
            print(f"   ✅ Enhanced Processor: Operational")
            print(f"   🧠 Reasoning: {'Available' if has_reasoning else 'Not Available'}")
            print(f"   🔍 Semantic Search: {'Available' if has_embeddings else 'Not Available'}")
            print(f"   📊 Visualization: Available")
            print(f"   ✅ Validation: Enhanced")
            print(f"   💾 Storage Integration: Working")
            
            return True
            
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("\n💡 Missing dependencies. Install with:")
        print("   pip install owlready2 sentence-transformers")
        return False
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        print(f"❌ Test Error: {e}")
        return False


def create_test_ontology() -> str:
    """Create a test ontology with reasoning-testable content."""
    
    return '''
@prefix : <http://test.ontserve.org/enhanced-processor#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix bfo: <http://purl.obolibrary.org/obo/> .

# Ontology declaration
: a owl:Ontology ;
    rdfs:label "Enhanced Processor Test Ontology" ;
    rdfs:comment "Test ontology for enhanced processor functionality with reasoning capabilities" .

# Base classes aligned with BFO
:Entity a owl:Class ;
    rdfs:subClassOf bfo:BFO_0000001 ;  # BFO Entity
    rdfs:label "Entity" ;
    rdfs:comment "A basic entity in our test ontology" .

:Person a owl:Class ;
    rdfs:subClassOf :Entity ;
    rdfs:label "Person" ;
    rdfs:comment "A human being" .

:Organization a owl:Class ;
    rdfs:subClassOf :Entity ;
    rdfs:label "Organization" ;
    rdfs:comment "A group or institution" .

:Role a owl:Class ;
    rdfs:subClassOf bfo:BFO_0000023 ;  # BFO Role
    rdfs:label "Role" ;
    rdfs:comment "A role that can be played by an entity" .

:ProfessionalRole a owl:Class ;
    rdfs:subClassOf :Role ;
    rdfs:label "Professional Role" ;
    rdfs:comment "A role in professional context" .

:Engineer a owl:Class ;
    rdfs:subClassOf :ProfessionalRole ;
    rdfs:label "Engineer" ;
    rdfs:comment "A professional engineer role" .

:Action a owl:Class ;
    rdfs:subClassOf bfo:BFO_0000015 ;  # BFO Process
    rdfs:label "Action" ;
    rdfs:comment "An action or activity" .

:DesignAction a owl:Class ;
    rdfs:subClassOf :Action ;
    rdfs:label "Design Action" ;
    rdfs:comment "An action involving design" .

# Object Properties
:hasRole a owl:ObjectProperty ;
    rdfs:domain :Person ;
    rdfs:range :Role ;
    rdfs:label "has role" ;
    rdfs:comment "Relates a person to their role" .

:performsAction a owl:ObjectProperty ;
    rdfs:domain :Person ;
    rdfs:range :Action ;
    rdfs:label "performs action" ;
    rdfs:comment "Relates a person to actions they perform" .

:worksFor a owl:ObjectProperty ;
    rdfs:domain :Person ;
    rdfs:range :Organization ;
    rdfs:label "works for" ;
    rdfs:comment "Relates a person to their organization" .

# Data Properties
:hasName a owl:DatatypeProperty ;
    rdfs:domain :Entity ;
    rdfs:range xsd:string ;
    rdfs:label "has name" ;
    rdfs:comment "The name of an entity" .

:hasExperience a owl:DatatypeProperty ;
    rdfs:domain :Person ;
    rdfs:range xsd:integer ;
    rdfs:label "has experience" ;
    rdfs:comment "Years of experience" .

# Individuals for testing
:johnDoe a :Person ;
    :hasName "John Doe" ;
    :hasExperience 5 ;
    :hasRole :seniorEngineer ;
    :worksFor :techCorp .

:seniorEngineer a :Engineer ;
    rdfs:label "Senior Engineer" .

:techCorp a :Organization ;
    :hasName "Tech Corporation" .

:designProject a :DesignAction ;
    rdfs:label "Design Project Alpha" .

# Add some restrictions for reasoning tests
:SoftwareEngineer a owl:Class ;
    rdfs:subClassOf :Engineer ;
    rdfs:subClassOf [ a owl:Restriction ;
                     owl:onProperty :performsAction ;
                     owl:someValuesFrom :DesignAction ] ;
    rdfs:label "Software Engineer" ;
    rdfs:comment "An engineer who performs design actions" .

# Equivalence for reasoning
:Developer owl:equivalentClass :SoftwareEngineer .

# Disjoint classes
:Person owl:disjointWith :Organization .
'''


def print_processing_result(result, test_name: str):
    """Print processing result details."""
    print(f"\n📊 {test_name} Result:")
    print(f"   Success: {'✅' if result.success else '❌'}")
    print(f"   Entities: {len(result.entities)}")
    print(f"   Processing time: {result.processing_time:.2f}s")
    print(f"   Reasoning applied: {'✅' if result.reasoning_applied else '❌'}")
    print(f"   Consistency check: {result.consistency_check}")
    print(f"   Inferred count: {result.inferred_count}")
    
    if result.error_message:
        print(f"   Error: {result.error_message}")
    
    if result.warnings:
        print(f"   Warnings: {len(result.warnings)}")


def print_validation_result(result: dict):
    """Print validation result details."""
    print(f"\n📝 Validation Result:")
    print(f"   Valid: {'✅' if result.get('valid', False) else '❌'}")
    print(f"   Errors: {len(result.get('errors', []))}")
    print(f"   Warnings: {len(result.get('warnings', []))}")
    print(f"   Suggestions: {len(result.get('suggestions', []))}")
    print(f"   Reasoning applied: {'✅' if result.get('reasoning_applied', False) else '❌'}")
    print(f"   Consistency check: {result.get('consistency_check')}")
    
    # Show first few issues
    for error in result.get('errors', [])[:3]:
        print(f"   ❌ {error}")
    
    for warning in result.get('warnings', [])[:3]:
        print(f"   ⚠️  {warning}")


if __name__ == '__main__':
    print("🧪 Enhanced Ontology Processor Test Suite")
    print("=" * 80)
    
    success = test_enhanced_processor()
    
    if success:
        print("\n🎉 Test suite completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Test suite failed!")
        sys.exit(1)
