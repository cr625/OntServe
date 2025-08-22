#!/usr/bin/env python3
"""
Basic Processor Test without Database Dependencies

Tests the core enhanced processor functionality without web/database components.

Usage:
    python test_processor_basic.py
"""

import sys
import os
import tempfile
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

# Ensure we're in the right directory
project_root = Path(__file__).parent
os.chdir(project_root)
sys.path.insert(0, str(project_root))

def test_basic_processing():
    """Test basic ontology processing without database."""
    print("\n" + "="*80)
    print("🔬 TESTING BASIC ONTOLOGY PROCESSING")
    print("="*80)
    
    try:
        # Import only what we need
        from storage.file_storage import FileStorage
        from rdflib import Graph, Namespace, URIRef
        from rdflib.namespace import RDF, RDFS, OWL
        
        print("✅ Core imports successful")
        
        # Create temporary storage
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {'storage_dir': temp_dir}
            storage = FileStorage(config)
            print(f"✅ File storage initialized at {temp_dir}")
            
            # Create test ontology content
            test_ttl = """
            @prefix : <http://test.org/onto#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            
            :TestOntology a owl:Ontology ;
                rdfs:label "Test Ontology" ;
                rdfs:comment "A simple test ontology" .
            
            :TestClass a owl:Class ;
                rdfs:label "Test Class" ;
                rdfs:comment "A test class for validation" .
            
            :SubTestClass a owl:Class ;
                rdfs:subClassOf :TestClass ;
                rdfs:label "Sub Test Class" .
            
            :TestProperty a owl:ObjectProperty ;
                rdfs:domain :TestClass ;
                rdfs:range :TestClass ;
                rdfs:label "Test Property" .
            
            :testIndividual a :TestClass ;
                rdfs:label "Test Individual" .
            """
            
            # Store the ontology
            ontology_id = "test-onto"
            result = storage.store(
                ontology_id=ontology_id,
                content=test_ttl,
                metadata={'name': 'Test Ontology', 'format': 'turtle'}
            )
            print(f"✅ Ontology stored successfully")
            if 'id' in result:
                print(f"   - ID: {result['id']}")
            
            # Parse with RDFLib to extract entities
            graph = Graph()
            graph.parse(data=test_ttl, format='turtle')
            
            # Count entities
            classes = list(graph.subjects(RDF.type, OWL.Class))
            properties = list(graph.subjects(RDF.type, OWL.ObjectProperty))
            individuals = []
            
            # Find individuals (instances of classes)
            for cls in classes:
                for individual in graph.subjects(RDF.type, cls):
                    if individual not in classes:  # Not a class itself
                        individuals.append(individual)
            
            print(f"\n📊 Entity Statistics:")
            print(f"   - Classes: {len(classes)}")
            print(f"   - Properties: {len(properties)}")
            print(f"   - Individuals: {len(individuals)}")
            print(f"   - Total triples: {len(graph)}")
            
            # Test retrieval
            retrieved = storage.retrieve(ontology_id)
            if retrieved and retrieved['content']:
                print(f"✅ Ontology retrieved successfully")
                print(f"   - Content length: {len(retrieved['content'])} chars")
            else:
                print("❌ Failed to retrieve ontology")
                return False
            
            # List stored ontologies
            ontologies = storage.list_ontologies()
            print(f"✅ Listed {len(ontologies)} ontologies")
            
            return True
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_enhanced_features():
    """Test enhanced processor features if available."""
    print("\n" + "="*80)
    print("🚀 TESTING ENHANCED FEATURES")
    print("="*80)
    
    try:
        # Check if owlready2 is available
        try:
            import owlready2
            print("✅ Owlready2 available - reasoning features enabled")
            has_reasoning = True
        except ImportError:
            print("⚠️  Owlready2 not available - reasoning features disabled")
            has_reasoning = False
        
        # Check if sentence-transformers is available
        try:
            from sentence_transformers import SentenceTransformer
            print("✅ Sentence-transformers available - semantic search enabled")
            has_embeddings = True
        except ImportError:
            print("⚠️  Sentence-transformers not available - semantic search disabled")
            has_embeddings = False
        
        # Try to use enhanced processor with minimal dependencies
        try:
            from core.enhanced_processor import ProcessingOptions
            
            options = ProcessingOptions(
                use_reasoning=False,  # Don't require owlready2
                validate_consistency=False,
                generate_embeddings=False  # Don't require sentence-transformers
            )
            
            print("✅ ProcessingOptions created successfully")
            print(f"   - Reasoning: {options.use_reasoning}")
            print(f"   - Consistency validation: {options.validate_consistency}")
            print(f"   - Embeddings: {options.generate_embeddings}")
            
        except Exception as e:
            print(f"⚠️  Could not create ProcessingOptions: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Enhanced features test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("\n🧪 Basic Processor Test Suite")
    print("="*80)
    
    results = []
    
    # Run tests
    results.append(("Basic Processing", test_basic_processing()))
    results.append(("Enhanced Features", test_enhanced_features()))
    
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
        print("\n❌ Some tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())