#!/usr/bin/env python3
"""
Example usage of the OntServe unified ontology server.

This script demonstrates how to:
1. Import PROV-O ontology
2. Store and retrieve ontologies
3. Extract classes, properties, and individuals
4. Manage versions
"""

import json
import os
from pprint import pprint

# Import OntServe components
from OntServe import OntologyManager


def main():
    """Main example function."""
    
    # Configure the ontology manager
    config = {
        'storage_type': 'file',
        'storage_config': {
            'storage_dir': './ontology_storage'
        },
        'cache_dir': './ontology_cache',
        'log_level': 'INFO'
    }
    
    # Create ontology manager instance
    print("=== Creating OntologyManager ===")
    manager = OntologyManager(config)
    
    # Example 1: Import PROV-O ontology
    print("\n=== Example 1: Import PROV-O ===")
    result = manager.import_prov_o()
    if result['success']:
        print(f"✓ Successfully imported PROV-O")
        print(f"  Ontology ID: {result['ontology_id']}")
        print(f"  Triple count: {result['metadata'].get('triple_count', 'N/A')}")
    else:
        print(f"✗ Failed to import PROV-O: {result.get('message')}")
    
    # Example 2: List available ontologies
    print("\n=== Example 2: List Ontologies ===")
    ontologies = manager.list_ontologies()
    for ont in ontologies:
        print(f"- {ont.get('ontology_id')}: {ont.get('name', 'Unnamed')}")
    
    # Example 3: Extract classes from PROV-O
    print("\n=== Example 3: Extract Classes ===")
    if result['success']:
        classes = manager.extract_classes('prov-o')
        print(f"Found {len(classes)} classes in PROV-O")
        # Show first 5 classes
        for cls in classes[:5]:
            print(f"  - {cls.get('label', 'No label')}: {cls.get('uri')}")
    
    # Example 4: Extract properties
    print("\n=== Example 4: Extract Properties ===")
    if result['success']:
        properties = manager.extract_properties('prov-o')
        print(f"Found {len(properties)} properties in PROV-O")
        # Show first 5 properties
        for prop in properties[:5]:
            print(f"  - {prop.get('label', 'No label')} ({prop.get('type')})")
    
    # Example 5: Import a custom ontology from file
    print("\n=== Example 5: Import Custom Ontology ===")
    # Check if BFO file exists (example)
    bfo_file = "OntExtract/ontologies/bfo.ttl"
    if os.path.exists(bfo_file):
        custom_result = manager.import_ontology(
            source=bfo_file,
            importer_type='prov',  # Using PROV importer for now
            ontology_id='bfo',
            name='Basic Formal Ontology',
            description='BFO is a top-level ontology'
        )
        if custom_result['success']:
            print(f"✓ Successfully imported BFO")
            print(f"  Triple count: {custom_result['metadata'].get('triple_count', 'N/A')}")
    else:
        print(f"  BFO file not found at {bfo_file}")
    
    # Example 6: Retrieve ontology content
    print("\n=== Example 6: Retrieve Ontology ===")
    retrieved = manager.get_ontology('prov-o')
    print(f"Retrieved PROV-O ontology:")
    print(f"  Content size: {len(retrieved['content'])} bytes")
    print(f"  Version: {retrieved.get('version', 'latest')}")
    
    # Example 7: Update metadata
    print("\n=== Example 7: Update Metadata ===")
    success = manager.update_metadata('prov-o', {
        'tags': ['provenance', 'w3c', 'standard'],
        'usage_notes': 'Use for tracking provenance information'
    })
    if success:
        print("✓ Successfully updated metadata")
    
    # Example 8: Create a backup
    print("\n=== Example 8: Create Backup ===")
    backup_path = './backups/prov-o-backup.json'
    os.makedirs('./backups', exist_ok=True)
    if manager.backup_ontology('prov-o', backup_path):
        print(f"✓ Successfully backed up to {backup_path}")
    
    # Example 9: Get version information
    print("\n=== Example 9: Version Information ===")
    versions = manager.get_versions('prov-o')
    print(f"Found {len(versions)} versions of PROV-O")
    for ver in versions:
        print(f"  - Version: {ver.get('version')}, Size: {ver.get('size_bytes')} bytes")
    
    # Example 10: Get loaded ontologies info
    print("\n=== Example 10: Loaded Ontologies ===")
    loaded = manager.get_loaded_ontologies()
    for ont_id, info in loaded.items():
        print(f"- {ont_id}:")
        print(f"    Loaded at: {info.get('loaded_at')}")
        print(f"    Name: {info['metadata'].get('name', 'N/A')}")
    
    # Clean shutdown
    print("\n=== Shutting Down ===")
    manager.shutdown()
    print("✓ OntologyManager shutdown complete")


if __name__ == "__main__":
    main()
