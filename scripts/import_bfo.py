#!/usr/bin/env python3
"""
Import BFO (Basic Formal Ontology) into OntServe.

This script demonstrates importing the BFO ontology from its official source.
BFO is a top-level ontology designed to support scientific research.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.ontology_manager import OntologyManager
from importers.bfo_importer import BFOImporter
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    """Import BFO ontology."""
    
    # Configuration
    config = {
        'storage_type': 'file',
        'storage_config': {
            'storage_dir': '../storage'
        },
        'cache_dir': '../cache',
        'log_level': 'INFO'
    }
    
    # Initialize OntologyManager
    logger.info("Initializing OntologyManager...")
    manager = OntologyManager(config)
    
    # Import BFO using the manager's convenience method
    logger.info("Importing BFO ontology...")
    result = manager.import_bfo(version="latest", force_refresh=False)
    
    if result.get('success'):
        logger.info(f"Successfully imported BFO: {result['ontology_id']}")
        
        # Display metadata
        metadata = result['metadata']
        logger.info(f"  Name: {metadata.get('name', 'Basic Formal Ontology')}")
        logger.info(f"  Description: {metadata.get('description', 'N/A')[:100]}...")
        logger.info(f"  Triple count: {metadata.get('triple_count', 0)}")
        logger.info(f"  Class count: {metadata.get('class_count', 0)}")
        logger.info(f"  Property count: {metadata.get('property_count', 0)}")
        
        # Display upper-level concepts if extracted
        if 'upper_level_concepts' in result:
            concepts = result['upper_level_concepts']
            logger.info(f"\nBFO Upper-level concepts:")
            logger.info(f"  Top-level: {len(concepts.get('top_level', []))} concepts")
            logger.info(f"  Continuants: {len(concepts.get('continuants', []))} concepts")
            logger.info(f"  Occurrents: {len(concepts.get('occurrents', []))} concepts")
            logger.info(f"  Relations: {len(concepts.get('relations', []))} properties")
            
            # Show some examples
            if concepts.get('top_level'):
                logger.info("\n  Sample top-level concepts:")
                for concept in concepts['top_level'][:3]:
                    comment = concept.get('comment', 'No description')
                    if comment:
                        comment = comment[:80] + '...' if len(comment) > 80 else comment
                    else:
                        comment = 'No description'
                    logger.info(f"    - {concept['label']}: {comment}")
        
        # Store the ontology
        logger.info("\nStoring BFO in OntologyManager...")
        manager.store_ontology('bfo', result.get('content', ''), metadata)
        logger.info("BFO ontology stored successfully!")
        
    else:
        logger.error(f"Failed to import BFO: {result.get('message', 'Unknown error')}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
