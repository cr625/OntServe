#!/usr/bin/env python3
"""
Test script for enhanced ontology visualization with Owlready2 and Cytoscape.js

This script tests:
1. Owlready2 importer functionality
2. Enhanced ontology processing with reasoning
3. Cytoscape.js data generation
4. Integration with existing ProEthica ontologies
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# Add OntServe to Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from importers.owlready_importer import OwlreadyImporter
    from storage.file_storage import FileStorage
    from web.models import db, Ontology
except ImportError as e:
    print(f"Error importing OntServe modules: {e}")
    print("Make sure you're running this from the OntServe directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_owlready_basic():
    """Test basic Owlready2 functionality."""
    logger.info("Testing basic Owlready2 functionality...")
    
    try:
        import owlready2
        logger.info("Owlready2 imported successfully")
        
        # Test basic ontology creation
        test_onto = owlready2.get_ontology("http://test.example.org/onto.owl")
        with test_onto:
            class TestClass(owlready2.Thing):
                pass
            
            class TestProperty(owlready2.ObjectProperty):
                pass
        
        logger.info("✓ Basic Owlready2 functionality works")
        return True
        
    except Exception as e:
        logger.error(f"✗ Basic Owlready2 test failed: {e}")
        return False


def test_enhanced_importer():
    """Test the enhanced Owlready2 importer."""
    logger.info("Testing enhanced Owlready2 importer...")
    
    try:
        # Create storage backend
        storage = FileStorage({'cache_dir': './test_cache'})
        
        # Create importer
        importer = OwlreadyImporter(storage_backend=storage)
        logger.info("✓ OwlreadyImporter created successfully")
        
        # Test with PROV-O (small, well-structured ontology)
        prov_url = "https://www.w3.org/ns/prov.ttl"
        logger.info(f"Testing import from: {prov_url}")
        
        result = importer.import_from_url(
            prov_url,
            ontology_id="prov-o-test",
            name="PROV-O Test Import",
            description="Test import of PROV-O using enhanced importer"
        )
        
        if result['success']:
            logger.info("✓ PROV-O import successful")
            logger.info(f"  - Classes: {result['metadata']['class_count']}")
            logger.info(f"  - Properties: {result['metadata']['property_count']}")
            logger.info(f"  - Reasoning applied: {result['metadata']['reasoning_applied']}")
            logger.info(f"  - Consistent: {result['metadata']['consistency_check']}")
            logger.info(f"  - Inferred relationships: {result['metadata']['inferred_relationships']}")
            
            # Test visualization data generation
            viz_data = importer.get_visualization_data("prov-o-test")
            logger.info(f"  - Visualization nodes: {len(viz_data['nodes'])}")
            logger.info(f"  - Visualization edges: {len(viz_data['edges'])}")
            
            return True
        else:
            logger.error(f"✗ PROV-O import failed: {result}")
            return False
            
    except Exception as e:
        logger.error(f"✗ Enhanced importer test failed: {e}")
        return False


def test_cytoscape_data_format():
    """Test that generated data is compatible with Cytoscape.js format."""
    logger.info("Testing Cytoscape.js data format...")
    
    try:
        storage = FileStorage({'cache_dir': './test_cache'})
        importer = OwlreadyImporter(storage_backend=storage)
        
        # Get visualization data from previous test
        viz_data = importer.get_visualization_data("prov-o-test")
        
        # Validate Cytoscape format
        assert 'nodes' in viz_data, "Missing 'nodes' in visualization data"
        assert 'edges' in viz_data, "Missing 'edges' in visualization data"
        assert 'layout_options' in viz_data, "Missing 'layout_options' in visualization data"
        assert 'style_options' in viz_data, "Missing 'style_options' in visualization data"
        
        # Validate node format
        if viz_data['nodes']:
            node = viz_data['nodes'][0]
            assert 'data' in node, "Node missing 'data' property"
            assert 'id' in node['data'], "Node data missing 'id'"
            assert 'label' in node['data'], "Node data missing 'label'"
            
        # Validate edge format  
        if viz_data['edges']:
            edge = viz_data['edges'][0]
            assert 'data' in edge, "Edge missing 'data' property"
            assert 'source' in edge['data'], "Edge data missing 'source'"
            assert 'target' in edge['data'], "Edge data missing 'target'"
        
        logger.info("✓ Cytoscape.js data format is valid")
        return True
        
    except Exception as e:
        logger.error(f"✗ Cytoscape data format test failed: {e}")
        return False


def test_visualization_template():
    """Test that the visualization template can be rendered."""
    logger.info("Testing visualization template rendering...")
    
    try:
        from flask import Flask, render_template_string
        
        # Read the template file
        template_path = Path(__file__).parent / 'web' / 'templates' / 'editor' / 'visualize.html'
        
        if not template_path.exists():
            logger.error(f"✗ Template file not found: {template_path}")
            return False
        
        with open(template_path, 'r') as f:
            template_content = f.read()
        
        # Check for key Cytoscape.js components
        required_components = [
            'cytoscape@3.21.0',
            'cytoscape-dagre',
            'cytoscape-cose-bilkent',
            'cytoscape-fcose',
            'initializeCytoscape',
            'convertHierarchyToCytoscape',
            'applyLayout'
        ]
        
        missing_components = []
        for component in required_components:
            if component not in template_content:
                missing_components.append(component)
        
        if missing_components:
            logger.error(f"✗ Template missing components: {missing_components}")
            return False
        
        logger.info("✓ Visualization template contains all required components")
        return True
        
    except Exception as e:
        logger.error(f"✗ Template rendering test failed: {e}")
        return False


def test_proethica_compatibility():
    """Test compatibility with ProEthica ontology structure."""
    logger.info("Testing ProEthica ontology compatibility...")
    
    try:
        storage = FileStorage({'cache_dir': './test_cache'})
        importer = OwlreadyImporter(storage_backend=storage)
        
        # Create a minimal ProEthica-like ontology for testing
        proethica_ttl = """
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix proethica: <http://proethica.org/ontology/> .
        @prefix bfo: <http://purl.obolibrary.org/obo/> .
        
        <http://proethica.org/ontology/> a owl:Ontology ;
            rdfs:label "ProEthica Test Ontology" ;
            rdfs:comment "Test ontology for ProEthica compatibility" .
        
        proethica:Role a owl:Class ;
            rdfs:label "Role" ;
            rdfs:comment "A role that can be played by an agent" .
        
        proethica:EthicalPrinciple a owl:Class ;
            rdfs:label "Ethical Principle" ;
            rdfs:comment "A principle that guides ethical decision-making" .
        
        proethica:Obligation a owl:Class ;
            rdfs:subClassOf proethica:EthicalPrinciple ;
            rdfs:label "Obligation" ;
            rdfs:comment "A duty or commitment to perform certain actions" .
        
        proethica:hasRole a owl:ObjectProperty ;
            rdfs:label "has role" ;
            rdfs:domain owl:Thing ;
            rdfs:range proethica:Role .
        
        proethica:appliesTo a owl:ObjectProperty ;
            rdfs:label "applies to" ;
            rdfs:domain proethica:EthicalPrinciple ;
            rdfs:range proethica:Role .
        """
        
        # Write to temporary file
        temp_file = Path('./test_proethica.ttl')
        with open(temp_file, 'w') as f:
            f.write(proethica_ttl)
        
        try:
            # Import the test ontology
            result = importer.import_from_file(
                str(temp_file),
                ontology_id="proethica-test",
                name="ProEthica Test",
                description="Test ProEthica-like ontology"
            )
            
            if result['success']:
                logger.info("✓ ProEthica-like ontology imported successfully")
                
                # Test visualization data generation
                viz_data = importer.get_visualization_data("proethica-test")
                
                # Check for ProEthica-specific elements
                nodes = viz_data['nodes']
                node_labels = [node['data']['label'] for node in nodes]
                
                expected_labels = ['Role', 'Ethical Principle', 'Obligation']
                found_labels = [label for label in expected_labels if label in node_labels]
                
                logger.info(f"  - Found ProEthica concepts: {found_labels}")
                
                if len(found_labels) == len(expected_labels):
                    logger.info("✓ All expected ProEthica concepts found in visualization")
                    return True
                else:
                    logger.error(f"✗ Missing ProEthica concepts: {set(expected_labels) - set(found_labels)}")
                    return False
            else:
                logger.error(f"✗ ProEthica ontology import failed: {result}")
                return False
                
        finally:
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()
                
    except Exception as e:
        logger.error(f"✗ ProEthica compatibility test failed: {e}")
        return False


def generate_test_report():
    """Generate a comprehensive test report."""
    logger.info("Generating enhanced visualization test report...")
    
    tests = [
        ("Basic Owlready2 Functionality", test_owlready_basic),
        ("Enhanced Importer", test_enhanced_importer), 
        ("Cytoscape Data Format", test_cytoscape_data_format),
        ("Visualization Template", test_visualization_template),
        ("ProEthica Compatibility", test_proethica_compatibility),
    ]
    
    results = {}
    
    print("\n" + "="*60)
    print("ENHANCED ONTOLOGY VISUALIZATION TEST REPORT")
    print("="*60)
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python Version: {sys.version}")
    print()
    
    for test_name, test_func in tests:
        print(f"Running: {test_name}...")
        try:
            result = test_func()
            results[test_name] = result
            status = "PASS" if result else "FAIL"
            print(f"  Result: {status}")
        except Exception as e:
            results[test_name] = False
            print(f"  Result: FAIL - {e}")
        print()
    
    # Summary
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    print("-"*60)
    print("SUMMARY")
    print("-"*60)
    print(f"Tests Passed: {passed}/{total}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("\n🎉 All tests passed! Enhanced visualization is ready.")
    else:
        print(f"\n❌ {total-passed} test(s) failed. Check the logs above for details.")
    
    print("\nNext Steps:")
    print("1. Install enhanced requirements: pip install -r requirements-enhanced.txt")
    print("2. Install Java JDK for Owlready2 reasoners: apt-get install openjdk-11-jdk")
    print("3. Start the web server: cd web && ./run.sh")
    print("4. Test visualization: http://localhost:5003/editor/ontology/<id>/visualize")
    
    return passed == total


def main():
    """Main test execution."""
    print("Enhanced Ontology Visualization Test Suite")
    print("=========================================")
    
    # Check if we're in the right directory
    if not Path('./importers/owlready_importer.py').exists():
        print("Error: This script must be run from the OntServe directory")
        sys.exit(1)
    
    # Create test cache directory
    os.makedirs('./test_cache', exist_ok=True)
    
    success = generate_test_report()
    
    # Cleanup
    try:
        import shutil
        if Path('./test_cache').exists():
            shutil.rmtree('./test_cache')
    except:
        pass
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
