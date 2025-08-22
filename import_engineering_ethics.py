#!/usr/bin/env python3
"""
Import script for ProEthica Engineering Ethics ontology.

This script imports the engineering-ethics.ttl ontology from the proethica repository
and processes it with enhanced reasoning to connect it to the proethica-intermediate
hierarchy.
"""

import os
import sys

# Change to web directory and import from there
web_dir = '/home/chris/onto/OntServe/web'
os.chdir(web_dir)
sys.path.insert(0, web_dir)
sys.path.insert(0, '/home/chris/onto/OntServe')

from app import create_app, db
from core.enhanced_processor import EnhancedOntologyProcessor, ProcessingOptions
from storage.file_storage import FileStorage
from web.models import Ontology


def main():
    """Import the engineering ethics ontology."""
    # Path to the engineering-ethics.ttl file
    ontology_path = "/home/chris/onto/proethica/ontologies/engineering-ethics.ttl"
    
    if not os.path.exists(ontology_path):
        print(f"❌ Error: File not found: {ontology_path}")
        return False
    
    # Read the ontology content
    try:
        with open(ontology_path, 'r', encoding='utf-8') as f:
            ontology_content = f.read()
        print(f"✅ Read ontology file: {len(ontology_content)} characters")
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False
    
    # Create Flask app context
    app = create_app()
    with app.app_context():
        # Configure storage
        storage_config = {
            'storage_dir': '/home/chris/onto/OntServe/storage',
            'metadata_dir': '/home/chris/onto/OntServe/storage/metadata',
            'versions_dir': '/home/chris/onto/OntServe/storage/versions'
        }
        storage = FileStorage(storage_config)
        
        # Check if ontology already exists
        existing = db.session.query(Ontology).filter_by(ontology_id='engineering-ethics').first()
        if existing:
            print(f"⚠️  Ontology 'engineering-ethics' already exists. Removing old version...")
            db.session.delete(existing)
            db.session.commit()
        
        # Create ontology record
        ontology_record = Ontology(
            ontology_id='engineering-ethics',
            name='Engineering Ethics Ontology',
            description='Domain-specific ontology for engineering ethics based on NSPE Code of Ethics and ISO standards',
            content=ontology_content,
            format='turtle',
            source_url=None,
            source_file=ontology_path,
            meta_data={
                'creator': 'ProEthica AI',
                'contributor': 'Claude 3 Opus - Anthropic',
                'date': '2025-01-15',
                'source': 'NSPE Code of Ethics, ISO/IEC 21838-2:2021 (BFO), ISO 15926, IFC/ISO 16739-1:2018',
                'imports': ['http://proethica.org/ontology/intermediate', 'bfo:bfo.owl']
            }
        )
        
        db.session.add(ontology_record)
        db.session.commit()
        print(f"✅ Created ontology record in database")
        
        # Process with enhanced reasoning
        processor = EnhancedOntologyProcessor(storage, db.session)
        
        # Enhanced processing options to capture hierarchy connections
        options = ProcessingOptions(
            use_reasoning=True,
            reasoner_type='hermit',
            include_inferred=True,
            force_refresh=True,
            generate_embeddings=True
        )
        
        print(f"🔄 Processing engineering-ethics with enhanced reasoning...")
        result = processor.process_ontology('engineering-ethics', options)
        
        if result.success:
            print(f"✅ Successfully processed engineering-ethics ontology!")
            print(f"   📊 Entity count: {len(result.entities)}")
            print(f"   🔗 Reasoning applied: {result.reasoning_applied}")
            print(f"   ⚡ Processing time: {result.processing_time:.2f}s")
            
            # Analyze the hierarchy connections
            print(f"\n🔍 Analyzing hierarchy connections...")
            
            # Check role connections
            role_entities = [e for e in result.entities if 'role' in (e.label or '').lower()]
            print(f"\n📋 Role entities ({len(role_entities)}):")
            for entity in role_entities:
                parent_info = f" -> {entity.parent_uri}" if entity.parent_uri else " (NO PARENT)"
                print(f"   {entity.label or entity.uri}{parent_info}")
            
            # Check resource connections
            resource_entities = [e for e in result.entities if any(term in (e.label or '').lower() 
                                                                 for term in ['document', 'drawing', 'specification'])]
            print(f"\n📄 Resource entities ({len(resource_entities)}):")
            for entity in resource_entities:
                parent_info = f" -> {entity.parent_uri}" if entity.parent_uri else " (NO PARENT)"
                print(f"   {entity.label or entity.uri}{parent_info}")
            
            # Check connections to proethica-intermediate
            intermediate_connections = [e for e in result.entities 
                                      if e.parent_uri and 'proethica.org/ontology/intermediate' in e.parent_uri]
            print(f"\n🔗 Connections to proethica-intermediate ({len(intermediate_connections)}):")
            for entity in intermediate_connections:
                print(f"   {entity.label or entity.uri} -> {entity.parent_uri}")
            
            return True
            
        else:
            print(f"❌ Failed to process engineering-ethics ontology: {result.error_message}")
            return False


if __name__ == "__main__":
    print("🚀 ProEthica Engineering Ethics Ontology Import")
    print("=" * 50)
    
    success = main()
    
    if success:
        print("\n🎉 Import completed successfully!")
        print("💡 You can now visualize the ontology at:")
        print("   http://localhost:8000/editor/ontology/engineering-ethics/visualize")
    else:
        print("\n💥 Import failed!")
        sys.exit(1)