#!/usr/bin/env python3
"""
Import ProEthica Intermediate ontology into OntServe.

This script imports the ProEthica intermediate ontology which contains
engineering ethics concepts and relationships.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.ontology_manager import OntologyManager
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    """Import ProEthica intermediate ontology."""
    
    # Configuration
    config = {
        'storage_type': 'file',
        'storage_config': {
            'storage_dir': '../storage'
        },
        'cache_dir': '../storage/cache/downloads',
        'log_level': 'INFO'
    }
    
    # Initialize OntologyManager
    logger.info("Initializing OntologyManager...")
    manager = OntologyManager(config)
    
    # Path to the ProEthica intermediate ontology
    proethica_path = "/home/chris/onto/proethica/ontologies/proethica-intermediate.ttl"
    
    # Check if file exists
    if not os.path.exists(proethica_path):
        logger.error(f"ProEthica intermediate ontology not found at {proethica_path}")
        return 1
    
    # Import the ontology
    logger.info(f"Importing ProEthica intermediate ontology from {proethica_path}...")
    
    try:
        result = manager.import_ontology(
            source=proethica_path,
            importer_type='prov',  # Use PROV importer as it handles TTL files well
            ontology_id='proethica-intermediate',
            name='ProEthica Intermediate Ontology',
            description='Engineering ethics ontology with BFO-aligned concepts for ethical decision-making',
            format='turtle'
        )
        
        if result.get('success'):
            logger.info(f"Successfully imported ProEthica: {result['ontology_id']}")
            
            # Display metadata
            metadata = result['metadata']
            logger.info(f"  Name: {metadata.get('name', 'ProEthica Intermediate Ontology')}")
            logger.info(f"  Description: {metadata.get('description', 'N/A')[:100]}...")
            logger.info(f"  Triple count: {metadata.get('triple_count', 0)}")
            logger.info(f"  Class count: {metadata.get('class_count', 0)}")
            logger.info(f"  Property count: {metadata.get('property_count', 0)}")
            
            # Store the ontology
            logger.info("\nStoring ProEthica in OntologyManager...")
            manager.store_ontology('proethica-intermediate', result.get('content', ''), metadata)
            logger.info("ProEthica intermediate ontology stored successfully!")
            
            # Now load it into the web database
            logger.info("\n=== Loading into Web Database ===")
            import_to_database()
            
        else:
            logger.error(f"Failed to import ProEthica: {result.get('message', 'Unknown error')}")
            return 1
            
    except Exception as e:
        logger.error(f"Error importing ProEthica: {e}")
        return 1
    
    return 0


def import_to_database():
    """Import ProEthica intermediate ontology into the web database."""
    
    # Import database dependencies
    sys.path.insert(0, str(Path(__file__).parent / 'web'))
    
    from flask import Flask
    from sqlalchemy import text
    import rdflib
    from rdflib import RDF, RDFS, OWL
    from datetime import datetime
    
    from config import config
    from models import db, Ontology, OntologyVersion, OntologyEntity
    from core.ontology_manager import OntologyManager
    
    # Create Flask app
    app = Flask(__name__)
    
    # Load configuration
    config_name = os.environ.get('FLASK_CONFIG', 'development')
    app.config.from_object(config[config_name])
    
    # Initialize database
    db.init_app(app)
    
    with app.app_context():
        # Initialize OntologyManager
        ontology_config = {
            'storage_type': 'file',
            'storage_config': {
                'storage_dir': '../storage'
            },
            'cache_dir': app.config['ONTSERVE_CACHE_DIR'],
            'log_level': 'INFO'
        }
        manager = OntologyManager(ontology_config)
        
        # Check if already in database
        existing = Ontology.query.filter_by(ontology_id='proethica-intermediate').first()
        if existing:
            logger.info("✓ ProEthica intermediate already exists in database")
            return
        
        # Get from file storage
        try:
            ont_data = manager.get_ontology('proethica-intermediate')
            if not ont_data:
                logger.warning("✗ ProEthica intermediate not found in file storage")
                return
            
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
                ontology_id='proethica-intermediate',
                name='ProEthica Intermediate Ontology',
                description='Engineering ethics ontology with BFO-aligned concepts for ethical decision-making',
                content=content,
                format='turtle',
                source_file=metadata.get('source_file') or metadata.get('source'),
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
                commit_message='Initial import of ProEthica intermediate ontology',
                created_at=datetime.now()
            )
            db.session.add(version)
            
            # Extract and store some entities (limited for performance)
            # Extract classes
            class_entities = []
            for s in list(g.subjects(RDF.type, OWL.Class))[:100]:  # Limit to 100 for performance
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
                for s in list(g.subjects(RDF.type, prop_type))[:50]:  # Limit to 50 for performance
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
            
            logger.info(f"✓ ProEthica intermediate imported to database:")
            logger.info(f"  - Triples: {triple_count}")
            logger.info(f"  - Classes: {class_count} (stored {len(class_entities)})")
            logger.info(f"  - Properties: {property_count} (stored {len(prop_entities)})")
            
        except Exception as e:
            logger.error(f"✗ Failed to import ProEthica intermediate: {e}")
            db.session.rollback()


if __name__ == "__main__":
    sys.exit(main())
