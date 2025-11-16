#!/usr/bin/env python3
"""
Initialize default ontologies in the web database.

This script imports PROV-O and BFO from file storage into the database
so they're available through the web interface.
"""

import os
import sys
from pathlib import Path
import logging
from datetime import datetime

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
from sqlalchemy import text, select
import rdflib
from rdflib import RDF, RDFS, OWL

from config import config
from models import db, Ontology, OntologyVersion, OntologyEntity
from core.ontology_manager import OntologyManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_database_ontologies(app):
    """Initialize PROV-O and BFO in the database."""
    
    with app.app_context():
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
        
        # List of default ontologies to import
        default_ontologies = [
            {
                'ontology_id': 'prov-o',
                'name': 'W3C Provenance Ontology (PROV-O)',
                'description': 'The PROV Ontology provides classes, properties, and restrictions for representing provenance information'
            },
            {
                'ontology_id': 'bfo',
                'name': 'Basic Formal Ontology (BFO)',
                'description': 'BFO is a top-level ontology designed to support scientific research'
            }
        ]
        
        for ont_info in default_ontologies:
            ont_id = ont_info['ontology_id']
            
            # Check if already in database
            stmt = select(Ontology).where(Ontology.ontology_id == ont_id)
            existing = db.session.execute(stmt).scalar_one_or_none()
            if existing:
                logger.info(f"✓ {ont_id} already exists in database")
                continue
            
            # Get from file storage
            try:
                ont_data = manager.get_ontology(ont_id)
                if not ont_data:
                    logger.warning(f"✗ {ont_id} not found in file storage")
                    continue
                
                content = ont_data.get('content', '')
                metadata = ont_data.get('metadata', {})
                
                # Parse to get statistics
                g = rdflib.Graph()
                g.parse(data=content, format='turtle')
                
                triple_count = len(g)
                class_count = len(list(g.subjects(RDF.type, OWL.Class)))
                property_count = (
                    len(list(g.subjects(RDF.type, OWL.ObjectProperty))) +
                    len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))
                )
                
                # Create ontology record
                ontology = Ontology(
                    ontology_id=ont_id,
                    name=ont_info['name'],
                    description=ont_info['description'],
                    content=content,
                    format='turtle',
                    source_url=metadata.get('source_url') or metadata.get('source'),
                    triple_count=triple_count,
                    class_count=class_count,
                    property_count=property_count,
                    meta_data=metadata
                )
                db.session.add(ontology)
                db.session.flush()  # Get the ID
                
                # Create initial version
                version = OntologyVersion(
                    ontology_id=ontology.id,
                    version=1,
                    content=content,
                    commit_message=f'Initial import of {ont_id}',
                    created_at=datetime.now()
                )
                db.session.add(version)
                
                # Extract and store entities (limited for performance)
                # Extract classes
                class_entities = []
                for s in list(g.subjects(RDF.type, OWL.Class))[:50]:
                    label = next(g.objects(s, RDFS.label), None)
                    comment = next(g.objects(s, RDFS.comment), None)
                    
                    entity = OntologyEntity(
                        ontology_id=ontology.id,
                        entity_type='class',
                        uri=str(s),
                        label=str(label) if label else None,
                        comment=str(comment) if comment else None
                    )
                    class_entities.append(entity)
                    db.session.add(entity)
                
                # Extract properties
                prop_entities = []
                for prop_type in [OWL.ObjectProperty, OWL.DatatypeProperty]:
                    for s in list(g.subjects(RDF.type, prop_type))[:25]:
                        label = next(g.objects(s, RDFS.label), None)
                        comment = next(g.objects(s, RDFS.comment), None)
                        domain = next(g.objects(s, RDFS.domain), None)
                        range_ = next(g.objects(s, RDFS.range), None)
                        
                        entity = OntologyEntity(
                            ontology_id=ontology.id,
                            entity_type='property',
                            uri=str(s),
                            label=str(label) if label else None,
                            comment=str(comment) if comment else None,
                            domain=str(domain) if domain else None,
                            range=str(range_) if range_ else None
                        )
                        prop_entities.append(entity)
                        db.session.add(entity)
                
                db.session.commit()
                
                logger.info(f"✓ {ont_id} imported to database:")
                logger.info(f"  - Triples: {triple_count}")
                logger.info(f"  - Classes: {class_count} (stored {len(class_entities)})")
                logger.info(f"  - Properties: {property_count} (stored {len(prop_entities)})")
                
            except Exception as e:
                logger.error(f"✗ Failed to import {ont_id}: {e}")
                db.session.rollback()
                continue
        
        # List all ontologies in database
        stmt = select(Ontology)
        all_onts = db.session.execute(stmt).scalars().all()
        logger.info(f"\n=== Total ontologies in database: {len(all_onts)} ===")
        for ont in all_onts:
            logger.info(f"  - {ont.ontology_id}: {ont.name}")


if __name__ == '__main__':
    # Create Flask app
    app = Flask(__name__)
    
    # Load configuration
    config_name = os.environ.get('FLASK_CONFIG', 'development')
    app.config.from_object(config[config_name])
    
    # Initialize database
    db.init_app(app)
    
    # Create tables if they don't exist
    with app.app_context():
        db.create_all()
        
        # Initialize default ontologies
        print("=== Initializing Default Ontologies in Database ===\n")
        init_database_ontologies(app)
        print("\n✓ Done!")
