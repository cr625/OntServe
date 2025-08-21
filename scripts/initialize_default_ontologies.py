#!/usr/bin/env python3
"""
Initialize OntServe with default ontologies (PROV-O and BFO).

This script imports PROV-O and BFO as default ontologies that will
always be available in the OntServe system.
"""

import os
import sys
from pathlib import Path
import shutil
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.ontology_manager import OntologyManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def initialize_default_ontologies():
    """Initialize PROV-O and BFO as default ontologies."""
    
    # Initialize OntologyManager
    config = {
        'storage_type': 'file',
        'storage_config': {
            'storage_dir': 'OntServe/storage/ontologies'
        },
        'cache_dir': 'OntServe/cache',
        'log_level': 'INFO'
    }
    
    manager = OntologyManager(config)
    
    # 1. Import PROV-O
    logger.info("Importing PROV-O...")
    try:
        result = manager.import_prov_o(force_refresh=False)
        if result['success']:
            logger.info(f"✓ PROV-O imported successfully: {result['ontology_id']}")
            logger.info(f"  - Triples: {result['metadata'].get('triple_count', 0)}")
            logger.info(f"  - Classes: {result['metadata'].get('class_count', 0)}")
            logger.info(f"  - Properties: {result['metadata'].get('property_count', 0)}")
        else:
            logger.error(f"Failed to import PROV-O: {result.get('message')}")
    except Exception as e:
        logger.error(f"Error importing PROV-O: {e}")
    
    # 2. Import BFO
    logger.info("\nImporting BFO...")
    try:
        result = manager.import_bfo(version="latest", force_refresh=False)
        if result['success']:
            logger.info(f"✓ BFO imported successfully: {result['ontology_id']}")
            logger.info(f"  - Triples: {result['metadata'].get('triple_count', 0)}")
            logger.info(f"  - Classes: {result['metadata'].get('class_count', 0)}")
            logger.info(f"  - Properties: {result['metadata'].get('property_count', 0)}")
            
            # Log upper-level concepts if available
            if 'upper_level_concepts' in result:
                concepts = result['upper_level_concepts']
                logger.info(f"  - Top-level concepts: {len(concepts.get('top_level', []))}")
                logger.info(f"  - Continuants: {len(concepts.get('continuants', []))}")
                logger.info(f"  - Occurrents: {len(concepts.get('occurrents', []))}")
                logger.info(f"  - Relations: {len(concepts.get('relations', []))}")
        else:
            logger.error(f"Failed to import BFO: {result.get('message')}")
    except Exception as e:
        logger.error(f"Error importing BFO: {e}")
        
        # Try from local file as fallback
        logger.info("Attempting to import BFO from local file...")
        bfo_path = Path(__file__).parent.parent / "OntExtract" / "ontologies" / "bfo.ttl"
        
        if bfo_path.exists():
            try:
                result = manager.import_ontology(
                    source=str(bfo_path),
                    importer_type='bfo',
                    ontology_id='bfo',
                    name='Basic Formal Ontology (BFO)',
                    description='BFO is a top-level ontology designed to support scientific research',
                    format='turtle'
                )
                
                if result['success']:
                    logger.info(f"✓ BFO imported from local file successfully")
                    logger.info(f"  - Triples: {result['metadata'].get('triple_count', 0)}")
                    logger.info(f"  - Classes: {result['metadata'].get('class_count', 0)}")
                    logger.info(f"  - Properties: {result['metadata'].get('property_count', 0)}")
                else:
                    logger.error(f"Failed to import BFO from local file: {result.get('message')}")
            except Exception as e:
                logger.error(f"Error importing BFO from local file: {e}")
        else:
            logger.warning(f"BFO file not found at {bfo_path}")
    
    # 3. Verify both ontologies are available
    logger.info("\n=== Verifying Default Ontologies ===")
    
    # Check PROV-O
    prov_o = manager.get_ontology('prov-o')
    if prov_o:
        logger.info("✓ PROV-O is available")
    else:
        logger.warning("✗ PROV-O is not available")
    
    # Check BFO
    bfo = manager.get_ontology('bfo')
    if bfo:
        logger.info("✓ BFO is available")
    else:
        logger.warning("✗ BFO is not available")
    
    # List all available ontologies
    available = manager.list_ontologies()
    logger.info(f"\nTotal ontologies available: {len(available)}")
    for ont_id in available:
        logger.info(f"  - {ont_id}")
    
    return {
        'prov_o': prov_o is not None,
        'bfo': bfo is not None,
        'total': len(available)
    }


if __name__ == '__main__':
    print("=== OntServe Default Ontologies Initialization ===\n")
    result = initialize_default_ontologies()
    
    print("\n=== Summary ===")
    print(f"PROV-O: {'✓ Imported' if result['prov_o'] else '✗ Failed'}")
    print(f"BFO: {'✓ Imported' if result['bfo'] else '✗ Failed'}")
    print(f"Total ontologies available: {result['total']}")
    
    if result['prov_o'] and result['bfo']:
        print("\n✓ All default ontologies successfully initialized!")
        sys.exit(0)
    else:
        print("\n✗ Some ontologies failed to initialize. Check the logs above.")
        sys.exit(1)
