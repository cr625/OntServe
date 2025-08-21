#!/usr/bin/env python3
"""
Fix the proethica-intermediate ontology database content field.

This script updates the database to match the corrected file storage.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / 'web'))

from flask import Flask
import rdflib
from rdflib import RDF, RDFS, OWL
from datetime import datetime

from web.config import config
from web.models import db, Ontology

def main():
    """Fix the proethica-intermediate database content."""
    
    # Create Flask app
    app = Flask(__name__)
    
    # Load configuration
    config_name = os.environ.get('FLASK_CONFIG', 'development')
    app.config.from_object(config[config_name])
    
    # Initialize database
    db.init_app(app)
    
    with app.app_context():
        # Find the proethica-intermediate ontology
        ontology = Ontology.query.filter_by(ontology_id='proethica-intermediate').first()
        
        if not ontology:
            print("❌ ProEthica intermediate ontology not found in database")
            return 1
        
        # Read the corrected content from file storage
        storage_file = Path(__file__).parent / 'storage' / 'ontologies' / 'proethica-intermediate.ttl'
        
        if not storage_file.exists():
            print(f"❌ Storage file not found: {storage_file}")
            return 1
        
        print(f"📂 Reading content from: {storage_file}")
        content = storage_file.read_text(encoding='utf-8')
        
        if not content.strip():
            print("❌ Storage file is empty")
            return 1
        
        print(f"✅ Found content: {len(content)} characters")
        
        # Parse to get updated statistics
        try:
            g = rdflib.Graph()
            g.parse(data=content, format='turtle')
            
            triple_count = len(g)
            class_count = len(list(g.subjects(RDF.type, OWL.Class)))
            property_count = (
                len(list(g.subjects(RDF.type, OWL.ObjectProperty))) +
                len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))
            )
            
            print(f"📊 Parsed ontology statistics:")
            print(f"   - Triples: {triple_count}")
            print(f"   - Classes: {class_count}")
            print(f"   - Properties: {property_count}")
            
        except Exception as e:
            print(f"❌ Error parsing TTL content: {e}")
            return 1
        
        # Update the database record
        print("💾 Updating database record...")
        
        ontology.content = content
        ontology.triple_count = triple_count
        ontology.class_count = class_count
        ontology.property_count = property_count
        ontology.updated_at = datetime.now()
        
        # Update metadata if it exists
        if hasattr(ontology, 'meta_data') and ontology.meta_data:
            meta_data = ontology.meta_data or {}
            meta_data.update({
                'triple_count': triple_count,
                'class_count': class_count,
                'property_count': property_count,
                'last_synced': datetime.now().isoformat(),
                'synced_from': 'file_storage'
            })
            ontology.meta_data = meta_data
        
        try:
            db.session.commit()
            print("✅ Database updated successfully!")
            
            print(f"\n🎉 ProEthica intermediate ontology fixed:")
            print(f"   - Database content field: {len(content)} characters")
            print(f"   - File storage: {storage_file}")
            print(f"   - Triples: {triple_count}")
            print(f"   - Classes: {class_count}")
            print(f"   - Properties: {property_count}")
            
            return 0
            
        except Exception as e:
            print(f"❌ Error updating database: {e}")
            db.session.rollback()
            return 1

if __name__ == "__main__":
    sys.exit(main())
