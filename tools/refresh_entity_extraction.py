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
# (script lives at OntServe/tools/, so the OntServe root is one level up -- matching
# populate_entity_embeddings.py. The prior `.parent.parent` resolved to /home/chris/onto,
# which made run_cleanup's extended-refresh a silent no-op behind subprocess.run.)
script_dir = Path(__file__).parent
ontserve_root = script_dir.parent
web_dir = ontserve_root / 'web'

# Add OntServe root first (for config/ package), then web dir (for models)
# The web/config.py module will handle its own imports from config/
if str(ontserve_root) not in sys.path:
    sys.path.insert(0, str(ontserve_root))
if str(web_dir) not in sys.path:
    sys.path.insert(0, str(web_dir))

import hashlib
import logging
import rdflib
from rdflib import RDF, RDFS, OWL
from rdflib.namespace import SKOS, DCTERMS
from datetime import datetime, timezone

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROETHICA_NS = 'http://proethica.org/ontology/'


PROETHICA_INTERMEDIATE_NS = 'http://proethica.org/ontology/intermediate#'
PROETHICA_CORE_NS = 'http://proethica.org/ontology/core#'


def refresh_ontology_entities(ontology_name: str = "proethica-intermediate"):
    """Refresh entity extraction for specified ontology."""

    from flask import Flask
    # Import config module explicitly from web directory
    import importlib.util
    config_spec = importlib.util.spec_from_file_location("web_config", str(web_dir / "app_config.py"))
    web_config_module = importlib.util.module_from_spec(config_spec)
    config_spec.loader.exec_module(web_config_module)
    config = web_config_module.config

    # Import via the web.models PACKAGE path (not bare `models`) so it is the SAME module object -- and the
    # SAME SQLAlchemy db instance -- that web/entity_extraction.py (the canonical extractor we delegate to)
    # uses. Importing the same file under two names creates two db instances, which fails init_app binding.
    from web.models import db, Ontology, OntologyVersion, OntologyEntity
    
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
        
        # Re-extract via the single canonical extractor (web/entity_extraction.extract_entities_from_content):
        # it clears this ontology's existing entities, captures + RESTORES embeddings for unchanged
        # (uri, content_hash), and captures the full entity set (classes, all property types incl. annotation
        # properties, individuals, concepts, schemes, catch-all). Read the TTL from the file (preferred) or
        # the stored version content. This module no longer carries its own copy of the extraction passes.
        from web.entity_extraction import extract_entities_from_content
        _script_dir = os.path.dirname(os.path.abspath(__file__))
        ontology_file = os.path.join(os.path.dirname(_script_dir), 'ontologies', f"{ontology_name}.ttl")
        if os.path.exists(ontology_file):
            logger.info(f"Reading TTL file: {ontology_file}")
            content = open(ontology_file).read()
        else:
            logger.info("Reading from stored version content")
            content = current_version.content
        counts = extract_entities_from_content(ontology, content)
        entities_added = sum(counts.values())
        logger.info(f"Extracted {entities_added} entities {counts} via the canonical extractor")

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