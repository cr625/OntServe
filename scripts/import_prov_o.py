#!/usr/bin/env python3
"""
Script to import PROV-O ontology into OntServe.

This will download PROV-O and store it both as a .ttl file
and in the database for testing the dual storage approach.
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.ontology_manager import OntologyManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    """Import PROV-O ontology."""
    # Configuration for OntologyManager
    config = {
        'storage_type': 'file',
        'storage_config': {
            'storage_dir': '../storage'
        },
        'cache_dir': '../storage/cache/downloads',
        'log_level': 'INFO'
    }
    
    # Create OntologyManager
    manager = OntologyManager(config)
    
    print("Importing PROV-O ontology...")
    
    # Import PROV-O
    result = manager.import_prov_o(force_refresh=False)
    
    if result.get('success'):
        print(f"✓ Successfully imported PROV-O")
        print(f"  Ontology ID: {result['ontology_id']}")
        print(f"  Triple count: {result['metadata'].get('triple_count', 0)}")
        print(f"  Class count: {result['metadata'].get('class_count', 0)}")
        print(f"  Property count: {result['metadata'].get('property_count', 0)}")
        
        # Extract and display some classes
        print("\nExtracting PROV-O classes...")
        classes = manager.extract_classes('prov-o')
        print(f"  Found {len(classes)} classes")
        
        # Show first 5 classes
        for cls in classes[:5]:
            label = cls.get('label', 'No label')
            uri = cls['uri']
            print(f"  - {label}: {uri}")
        
        # Extract and display some properties
        print("\nExtracting PROV-O properties...")
        properties = manager.extract_properties('prov-o')
        print(f"  Found {len(properties)} properties")
        
        # Show first 5 properties
        for prop in properties[:5]:
            label = prop.get('label', 'No label')
            uri = prop['uri']
            prop_type = prop.get('type', 'unknown')
            print(f"  - {label} ({prop_type}): {uri}")
            
        # List stored ontologies
        print("\nStored ontologies:")
        ontologies = manager.list_ontologies()
        for ont in ontologies:
            print(f"  - {ont.get('ontology_id')}: {ont.get('name', 'Unnamed')}")
            
        print("\n✓ PROV-O import complete!")
        
    else:
        print(f"✗ Failed to import PROV-O: {result.get('message', 'Unknown error')}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
