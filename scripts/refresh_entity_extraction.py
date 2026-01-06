#!/usr/bin/env python3
"""
Refresh entity extraction from ontology content.

This script re-extracts entities from the current ontology versions
and updates the ontology_entities table. Specifically designed to refresh
MCP server entity queries after ontology updates.
"""

import sys
import os
from pathlib import Path

# Set up paths BEFORE any other imports
# This needs careful ordering to avoid conflicts between config/ directory and config.py module
script_dir = Path(__file__).parent
ontserve_root = script_dir.parent
web_dir = ontserve_root / 'web'

# Add OntServe root first (for config/ package), then web dir (for models)
# The web/config.py module will handle its own imports from config/
if str(ontserve_root) not in sys.path:
    sys.path.insert(0, str(ontserve_root))
if str(web_dir) not in sys.path:
    sys.path.insert(0, str(web_dir))

import logging
import rdflib
from rdflib import RDF, RDFS, OWL
from rdflib.namespace import SKOS, DCTERMS
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def refresh_ontology_entities(ontology_name: str = "proethica-intermediate"):
    """Refresh entity extraction for specified ontology."""

    from flask import Flask
    # Import config module explicitly from web directory
    import importlib.util
    config_spec = importlib.util.spec_from_file_location("web_config", str(web_dir / "config.py"))
    web_config_module = importlib.util.module_from_spec(config_spec)
    config_spec.loader.exec_module(web_config_module)
    config = web_config_module.config

    from models import db, Ontology, OntologyVersion, OntologyEntity
    
    # Create Flask app
    app = Flask(__name__)
    
    # Load configuration
    config_name = os.environ.get('FLASK_CONFIG', 'development')
    app.config.from_object(config[config_name])
    
    # Initialize database
    db.init_app(app)
    
    with app.app_context():
        # Find the ontology
        ontology = Ontology.query.filter_by(name=ontology_name).first()
        if not ontology:
            logger.error(f"Ontology '{ontology_name}' not found in database")
            return False
        
        logger.info(f"Found ontology: {ontology.name} (ID: {ontology.id})")
        
        # Get the current version
        current_version = OntologyVersion.query.filter_by(
            ontology_id=ontology.id,
            is_current=True
        ).first()
        
        if not current_version:
            logger.error(f"No current version found for ontology '{ontology_name}'")
            return False
        
        logger.info(f"Using version {current_version.version_number} created at {current_version.created_at}")
        
        # Clear existing entities for this ontology
        deleted_count = OntologyEntity.query.filter_by(ontology_id=ontology.id).delete()
        logger.info(f"Cleared {deleted_count} existing entities")
        
        # Parse the ontology content - try file first, then database content
        g = rdflib.Graph()
        try:
            # First try parsing from original file if it exists
            ontology_file = f"/home/chris/onto/OntServe/ontologies/{ontology_name}.ttl"
            if os.path.exists(ontology_file):
                logger.info(f"Parsing from TTL file: {ontology_file}")
                g.parse(ontology_file, format='turtle')
                logger.info(f"Parsed ontology from file with {len(g)} triples")
            else:
                # Fallback to database content
                logger.info("Parsing from database content")
                g.parse(data=current_version.content, format='turtle')
                logger.info(f"Parsed ontology from database with {len(g)} triples")
        except Exception as e:
            logger.error(f"Failed to parse ontology content: {e}")
            # Try with less strict parsing
            try:
                logger.info("Attempting to parse with error recovery...")
                g = rdflib.Graph()
                # Create a temporary file with proper prefixes
                temp_content = """@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix iao: <http://purl.obolibrary.org/obo/IAO_> .
@prefix proeth: <http://www.semanticweb.org/ontologies/proethica#> .
@prefix bfo: <http://purl.obolibrary.org/obo/BFO_> .
@prefix obo: <http://purl.obolibrary.org/obo/> .

""" + current_version.content
                
                g.parse(data=temp_content, format='turtle')
                logger.info(f"Successfully parsed with prefix fixes: {len(g)} triples")
            except Exception as e2:
                logger.error(f"All parsing attempts failed: {e2}")
                return False
        
        # Extract entities
        entities_added = 0
        
        # Extract classes
        for class_uri in g.subjects(RDF.type, OWL.Class):
            label = next(g.objects(class_uri, RDFS.label), None)
            comment = next(g.objects(class_uri, RDFS.comment), None)
            definition = next(g.objects(class_uri, SKOS.definition), None)
            
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='class',
                uri=str(class_uri),
                label=str(label) if label else None,
                comment=str(comment) if comment else str(definition) if definition else None
            )
            db.session.add(entity)
            entities_added += 1
        
        logger.info(f"Extracted {entities_added} classes")
        
        # Extract object properties
        prop_count = 0
        for prop_uri in g.subjects(RDF.type, OWL.ObjectProperty):
            label = next(g.objects(prop_uri, RDFS.label), None)
            comment = next(g.objects(prop_uri, RDFS.comment), None)
            domain = next(g.objects(prop_uri, RDFS.domain), None)
            range_ = next(g.objects(prop_uri, RDFS.range), None)
            
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='property',
                uri=str(prop_uri),
                label=str(label) if label else None,
                comment=str(comment) if comment else None,
                domain=str(domain) if domain else None,
                range=str(range_) if range_ else None
            )
            db.session.add(entity)
            prop_count += 1
        
        # Extract datatype properties
        for prop_uri in g.subjects(RDF.type, OWL.DatatypeProperty):
            label = next(g.objects(prop_uri, RDFS.label), None)
            comment = next(g.objects(prop_uri, RDFS.comment), None)
            domain = next(g.objects(prop_uri, RDFS.domain), None)
            range_ = next(g.objects(prop_uri, RDFS.range), None)
            
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='property',
                uri=str(prop_uri),
                label=str(label) if label else None,
                comment=str(comment) if comment else None,
                domain=str(domain) if domain else None,
                range=str(range_) if range_ else None
            )
            db.session.add(entity)
            prop_count += 1
        
        logger.info(f"Extracted {prop_count} properties")
        entities_added += prop_count

        # Extract individuals (NamedIndividuals)
        individual_count = 0
        # Define standard predicates to skip when collecting properties
        standard_predicates = {
            RDF.type, RDFS.label, RDFS.comment, SKOS.definition,
            rdflib.URIRef('http://www.w3.org/ns/prov#generatedAtTime'),
            rdflib.URIRef('http://www.w3.org/ns/prov#wasGeneratedBy')
        }

        for individual_uri in g.subjects(RDF.type, OWL.NamedIndividual):
            label = next(g.objects(individual_uri, RDFS.label), None)
            comment = next(g.objects(individual_uri, RDFS.comment), None)

            # Get the types of this individual (excluding NamedIndividual itself)
            types = []
            for type_uri in g.objects(individual_uri, RDF.type):
                if type_uri != OWL.NamedIndividual:
                    types.append(str(type_uri))

            # Collect all other properties into a JSON structure
            properties = {}
            for predicate, obj in g.predicate_objects(individual_uri):
                if predicate not in standard_predicates:
                    pred_name = str(predicate).split('#')[-1].split('/')[-1]
                    obj_value = str(obj)
                    # Handle multiple values for same predicate
                    if pred_name in properties:
                        if isinstance(properties[pred_name], list):
                            properties[pred_name].append(obj_value)
                        else:
                            properties[pred_name] = [properties[pred_name], obj_value]
                    else:
                        properties[pred_name] = obj_value

            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='individual',
                uri=str(individual_uri),
                label=str(label) if label else None,
                comment=str(comment) if comment else None,
                parent_uri=types[0] if types else None,  # Use first type as parent
                properties=properties if properties else None
            )
            db.session.add(entity)
            individual_count += 1

        logger.info(f"Extracted {individual_count} individuals")
        entities_added += individual_count

        # Commit the changes
        try:
            db.session.commit()
            logger.info(f"Successfully updated {entities_added} entities for ontology '{ontology_name}'")
            
            # Update the MCP server cache timestamp
            ontology.updated_at = datetime.now()
            db.session.commit()
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to commit entity updates: {e}")
            db.session.rollback()
            return False


def main():
    """Main script entry point."""
    
    # Parse command line arguments
    ontology_name = "proethica-intermediate"
    if len(sys.argv) > 1:
        ontology_name = sys.argv[1]
    
    logger.info(f"Refreshing entity extraction for ontology: {ontology_name}")
    
    success = refresh_ontology_entities(ontology_name)
    
    if success:
        logger.info("Entity extraction refresh completed successfully")
        logger.info("MCP server will now serve updated entities on next query")
        return 0
    else:
        logger.error("Entity extraction refresh failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())