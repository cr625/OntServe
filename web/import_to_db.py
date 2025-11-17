#!/usr/bin/env python3
"""
Import PROV-O ontology into the database for testing the web interface.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from sqlalchemy import select
from web.config import config
from web.models import db, init_db, Ontology, OntologyEntity, OntologyVersion
from core.ontology_manager import OntologyManager
import rdflib
from rdflib import RDF, RDFS, OWL

def main():
    """Import PROV-O into the database."""
    # Create Flask app
    app = Flask(__name__)
    app.config.from_object(config['development'])
    
    # Initialize database
    init_db(app)
    
    # Initialize OntologyManager
    ontology_config = {
        'storage_type': 'file',
        'storage_config': {
            'storage_dir': app.config['ONTSERVE_STORAGE_DIR']
        },
        'cache_dir': app.config['ONTSERVE_CACHE_DIR'],
        'log_level': 'INFO'
    }
    manager = OntologyManager(ontology_config)
    
    with app.app_context():
        # Check if PROV-O already exists
        stmt = select(Ontology).where(Ontology.ontology_id == 'prov-o')
        existing = db.session.execute(stmt).scalar_one_or_none()
        if existing:
            print("PROV-O already exists in database, skipping...")
            return
        
        # Get the PROV-O content from storage
        try:
            ont_data = manager.get_ontology('prov-o')
            content = ont_data.get('content', '')
            metadata = ont_data.get('metadata', {})
            
            # Parse to get stats
            g = rdflib.Graph()
            g.parse(data=content, format='turtle')
            
            # Create ontology record
            ontology = Ontology(
                ontology_id='prov-o',
                name='W3C Provenance Ontology (PROV-O)',
                description='The PROV Ontology provides classes, properties, and restrictions for representing provenance information',
                content=content,
                format='turtle',
                source_url='https://www.w3.org/ns/prov.ttl',
                triple_count=len(g),
                class_count=len(list(g.subjects(RDF.type, OWL.Class))),
                property_count=(
                    len(list(g.subjects(RDF.type, OWL.ObjectProperty))) +
                    len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))
                ),
                meta_data=metadata,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.session.add(ontology)
            db.session.flush()  # Get the ID
            
            # Create initial version
            version = OntologyVersion(
                ontology_id=ontology.id,
                version=1,
                content=content,
                commit_message='Initial import of PROV-O',
                created_at=datetime.now()
            )
            db.session.add(version)
            
            # Extract and save entities
            print("Extracting entities...")
            
            # Extract classes
            classes = manager.extract_classes('prov-o')
            for cls in classes[:50]:  # Limit to first 50 for testing
                entity = OntologyEntity(
                    ontology_id=ontology.id,
                    entity_type='class',
                    uri=cls['uri'],
                    label=cls.get('label'),
                    comment=cls.get('comment'),
                    parent_uri=cls.get('subclass_of', [None])[0] if cls.get('subclass_of') else None
                )
                db.session.add(entity)
            
            # Extract properties
            properties = manager.extract_properties('prov-o')
            for prop in properties[:50]:  # Limit to first 50 for testing
                entity = OntologyEntity(
                    ontology_id=ontology.id,
                    entity_type='property',
                    uri=prop['uri'],
                    label=prop.get('label'),
                    comment=prop.get('comment'),
                    domain=prop.get('domain'),
                    range=prop.get('range')
                )
                db.session.add(entity)
            
            db.session.commit()
            
            print(f"✓ Successfully imported PROV-O into database")
            print(f"  - ID: {ontology.ontology_id}")
            print(f"  - Triples: {ontology.triple_count}")
            print(f"  - Classes: {len(classes)} (stored first 50)")
            print(f"  - Properties: {len(properties)} (stored first 50)")
            
        except Exception as e:
            print(f"✗ Error importing PROV-O: {e}")
            db.session.rollback()
            return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
