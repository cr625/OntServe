#!/usr/bin/env python3
"""
Import PROV-O (W3C Provenance Ontology) into OntServe as a base ontology.

This script imports PROV-O as a non-editable base ontology that can be used
by other systems like OntExtract for provenance tracking and document classification.
"""

import os
import sys
import json
import logging
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from storage.postgresql_storage import PostgreSQLStorage, StorageError
from storage.concept_manager import ConceptManager
import rdflib
from rdflib import Graph, Namespace, RDF, RDFS, OWL
from rdflib.namespace import PROV

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# PROV-O constants
PROV_O_URL = "https://www.w3.org/ns/prov.ttl"
PROV_O_DOMAIN = "prov-o"
PROV_O_NAMESPACE = "http://www.w3.org/ns/prov#"

class ProvOImporter:
    """Imports PROV-O ontology into OntServe."""
    
    def __init__(self):
        """Initialize the importer."""
        # Get database URL from environment
        self.db_url = os.environ.get(
            'ONTSERVE_DB_URL',
            'postgresql://ontserve_user:ontserve_development_password@localhost:5433/ontserve'
        )
        
        # Initialize storage backend
        storage_config = {
            'db_url': self.db_url,
            'pool_size': 5,
            'timeout': 30
        }
        
        try:
            self.storage = PostgreSQLStorage(storage_config)
            self.concept_manager = ConceptManager(self.storage)
            logger.info("Database connection established successfully")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def import_prov_o(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Import PROV-O ontology into OntServe.
        
        Args:
            force_refresh: Force re-import even if already exists
            
        Returns:
            Dictionary with import results
        """
        logger.info("Starting PROV-O import into OntServe...")
        
        try:
            # Check if PROV-O domain already exists
            if not force_refresh and self._domain_exists():
                logger.info("PROV-O domain already exists. Use force_refresh=True to re-import.")
                return {"success": False, "message": "Domain already exists"}
            
            # Download and parse PROV-O
            logger.info(f"Downloading PROV-O from {PROV_O_URL}")
            graph = self._download_prov_o()
            
            # Create PROV-O domain
            self._create_prov_domain()
            
            # Extract and import concepts
            concepts_imported = self._import_concepts(graph)
            
            # Store ontology content
            self._store_ontology_content(graph)
            
            logger.info(f"Successfully imported PROV-O with {concepts_imported} concepts")
            
            return {
                "success": True,
                "message": f"Successfully imported PROV-O with {concepts_imported} concepts",
                "domain": PROV_O_DOMAIN,
                "concepts_imported": concepts_imported
            }
            
        except Exception as e:
            logger.error(f"Failed to import PROV-O: {e}")
            return {"success": False, "error": str(e)}
    
    def _domain_exists(self) -> bool:
        """Check if PROV-O domain already exists."""
        try:
            result = self.concept_manager.get_domain_info(PROV_O_DOMAIN)
            return True
        except StorageError:
            return False
    
    def _download_prov_o(self) -> Graph:
        """Download and parse PROV-O ontology."""
        try:
            response = requests.get(
                PROV_O_URL,
                headers={'Accept': 'text/turtle, application/rdf+xml'},
                timeout=30
            )
            response.raise_for_status()
            
            # Parse the RDF content
            g = Graph()
            g.parse(data=response.text, format='turtle')
            
            logger.info(f"Successfully parsed PROV-O with {len(g)} triples")
            return g
            
        except requests.RequestException as e:
            logger.error(f"Failed to download PROV-O: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse PROV-O: {e}")
            raise
    
    def _create_prov_domain(self):
        """Create the PROV-O domain in OntServe."""
        logger.info("Creating PROV-O domain...")
        
        domain_id = self.storage._get_or_create_domain(PROV_O_DOMAIN)
        
        # Update domain metadata
        query = """
            UPDATE domains 
            SET display_name = %s, namespace_uri = %s, description = %s, metadata = %s
            WHERE name = %s
        """
        
        metadata = {
            "type": "base_ontology",
            "source": PROV_O_URL,
            "version": "2013-04-30",
            "standard": "W3C Recommendation",
            "imported_by": "OntServe PROV-O Importer",
            "imported_at": datetime.now().isoformat()
        }
        
        self.storage._execute_query(
            query,
            (
                "W3C Provenance Ontology (PROV-O)",
                PROV_O_NAMESPACE,
                "The PROV Ontology (PROV-O) provides a set of classes, properties, and restrictions for representing provenance information generated by applications",
                json.dumps(metadata),
                PROV_O_DOMAIN
            )
        )
        
        logger.info("PROV-O domain created successfully")
    
    def _import_concepts(self, graph: Graph) -> int:
        """Import PROV-O concepts as approved concepts."""
        logger.info("Extracting and importing PROV-O concepts...")
        
        concepts_imported = 0
        
        # Import classes
        classes = self._extract_classes(graph)
        for class_info in classes:
            try:
                concept_data = {
                    "label": f"{class_info['label']} (Class)",
                    "category": "Resource",  # PROV-O classes are conceptual resources
                    "uri": class_info['uri'],
                    "description": class_info['comment'] or f"PROV-O class: {class_info['label']}",
                    "confidence_score": 1.0,
                    "extraction_method": "ontology_import",
                    "source_document": "W3C PROV-O Specification",
                    "semantic_label": class_info['label']
                }
                
                result = self.concept_manager.submit_candidate_concept(
                    concept_data, 
                    PROV_O_DOMAIN, 
                    "prov-o-importer"
                )
                
                if result.get('success'):
                    # Immediately approve the concept
                    self.concept_manager.update_concept_status(
                        result['concept_id'],
                        'approved',
                        'prov-o-importer',
                        'Auto-approved base ontology concept'
                    )
                    concepts_imported += 1
                    
            except Exception as e:
                logger.warning(f"Failed to import class {class_info['label']}: {e}")
        
        # Import properties
        properties = self._extract_properties(graph)
        for prop_info in properties:
            try:
                # Determine concept category based on property type
                if prop_info['type'] == 'object_property':
                    category = "Action"  # Object properties represent relationships/actions
                else:
                    category = "State"   # Datatype properties represent attributes/states
                
                concept_data = {
                    "label": f"{prop_info['label']} (Property)",
                    "category": category,
                    "uri": prop_info['uri'],
                    "description": prop_info['comment'] or f"PROV-O {prop_info['type'].replace('_', ' ')}: {prop_info['label']}",
                    "confidence_score": 1.0,
                    "extraction_method": "ontology_import",
                    "source_document": "W3C PROV-O Specification",
                    "semantic_label": prop_info['label']
                }
                
                result = self.concept_manager.submit_candidate_concept(
                    concept_data,
                    PROV_O_DOMAIN,
                    "prov-o-importer"
                )
                
                if result.get('success'):
                    # Immediately approve the concept
                    self.concept_manager.update_concept_status(
                        result['concept_id'],
                        'approved',
                        'prov-o-importer',
                        'Auto-approved base ontology concept'
                    )
                    concepts_imported += 1
                    
            except Exception as e:
                logger.warning(f"Failed to import property {prop_info['label']}: {e}")
        
        return concepts_imported
    
    def _extract_classes(self, graph: Graph) -> List[Dict[str, Any]]:
        """Extract classes from PROV-O graph."""
        classes = []
        
        for s in graph.subjects(RDF.type, OWL.Class):
            # Only include classes in PROV namespace
            if str(s).startswith(PROV_O_NAMESPACE):
                class_info = {
                    'uri': str(s),
                    'label': self._get_label(graph, s) or str(s).split('#')[-1],
                    'comment': self._get_comment(graph, s),
                    'subclass_of': [str(o) for o in graph.objects(s, RDFS.subClassOf)]
                }
                classes.append(class_info)
        
        # Add core PROV classes that might not be explicitly declared as OWL.Class
        core_classes = [
            (PROV.Entity, "Entity"),
            (PROV.Activity, "Activity"), 
            (PROV.Agent, "Agent"),
            (PROV.Plan, "Plan"),
            (PROV.Collection, "Collection"),
            (PROV.Bundle, "Bundle"),
            (PROV.Person, "Person"),
            (PROV.Organization, "Organization"),
            (PROV.SoftwareAgent, "SoftwareAgent")
        ]
        
        existing_uris = {c['uri'] for c in classes}
        for class_uri, class_name in core_classes:
            if str(class_uri) not in existing_uris:
                classes.append({
                    'uri': str(class_uri),
                    'label': class_name,
                    'comment': self._get_comment(graph, class_uri) or f"PROV-O core class: {class_name}",
                    'subclass_of': []
                })
        
        logger.info(f"Extracted {len(classes)} classes from PROV-O")
        return classes
    
    def _extract_properties(self, graph: Graph) -> List[Dict[str, Any]]:
        """Extract properties from PROV-O graph."""
        properties = []
        
        # Object properties
        for s in graph.subjects(RDF.type, OWL.ObjectProperty):
            if str(s).startswith(PROV_O_NAMESPACE):
                prop_info = {
                    'uri': str(s),
                    'type': 'object_property',
                    'label': self._get_label(graph, s) or str(s).split('#')[-1],
                    'comment': self._get_comment(graph, s),
                    'domain': [str(o) for o in graph.objects(s, RDFS.domain)],
                    'range': [str(o) for o in graph.objects(s, RDFS.range)]
                }
                properties.append(prop_info)
        
        # Datatype properties
        for s in graph.subjects(RDF.type, OWL.DatatypeProperty):
            if str(s).startswith(PROV_O_NAMESPACE):
                prop_info = {
                    'uri': str(s),
                    'type': 'datatype_property',
                    'label': self._get_label(graph, s) or str(s).split('#')[-1],
                    'comment': self._get_comment(graph, s),
                    'domain': [str(o) for o in graph.objects(s, RDFS.domain)],
                    'range': [str(o) for o in graph.objects(s, RDFS.range)]
                }
                properties.append(prop_info)
        
        # Add core PROV properties
        core_properties = [
            (PROV.wasGeneratedBy, "wasGeneratedBy", "object_property"),
            (PROV.used, "used", "object_property"),
            (PROV.wasInformedBy, "wasInformedBy", "object_property"),
            (PROV.wasStartedBy, "wasStartedBy", "object_property"),
            (PROV.wasEndedBy, "wasEndedBy", "object_property"),
            (PROV.wasInvalidatedBy, "wasInvalidatedBy", "object_property"),
            (PROV.wasDerivedFrom, "wasDerivedFrom", "object_property"),
            (PROV.wasRevisionOf, "wasRevisionOf", "object_property"),
            (PROV.wasQuotedFrom, "wasQuotedFrom", "object_property"),
            (PROV.hadPrimarySource, "hadPrimarySource", "object_property"),
            (PROV.wasAttributedTo, "wasAttributedTo", "object_property"),
            (PROV.wasAssociatedWith, "wasAssociatedWith", "object_property"),
            (PROV.actedOnBehalfOf, "actedOnBehalfOf", "object_property"),
            (PROV.wasInfluencedBy, "wasInfluencedBy", "object_property"),
            (PROV.atTime, "atTime", "datatype_property"),
            (PROV.value, "value", "datatype_property")
        ]
        
        existing_uris = {p['uri'] for p in properties}
        for prop_uri, prop_name, prop_type in core_properties:
            if str(prop_uri) not in existing_uris:
                properties.append({
                    'uri': str(prop_uri),
                    'type': prop_type,
                    'label': prop_name,
                    'comment': self._get_comment(graph, prop_uri) or f"PROV-O core property: {prop_name}",
                    'domain': [],
                    'range': []
                })
        
        logger.info(f"Extracted {len(properties)} properties from PROV-O")
        return properties
    
    def _store_ontology_content(self, graph: Graph):
        """Store the full PROV-O ontology content."""
        logger.info("Storing PROV-O ontology content...")
        
        # Serialize the graph to TTL format
        ttl_content = graph.serialize(format='turtle')
        
        # Store using the storage backend
        metadata = {
            "name": "W3C Provenance Ontology (PROV-O)",
            "description": "The PROV Ontology (PROV-O) provides a set of classes, properties, and restrictions for representing provenance information",
            "version": "2013-04-30",
            "source": PROV_O_URL,
            "is_base": True,
            "is_editable": False,
            "base_uri": PROV_O_NAMESPACE,
            "created_by": "prov-o-importer",
            "change_summary": "Initial import of PROV-O base ontology"
        }
        
        try:
            result = self.storage.store(
                f"{PROV_O_DOMAIN}:prov-o-base",
                ttl_content,
                metadata
            )
            logger.info(f"Stored PROV-O ontology content: {result}")
        except Exception as e:
            logger.warning(f"Failed to store ontology content: {e}")
    
    def _get_label(self, graph: Graph, subject: Any) -> str:
        """Get rdfs:label for a subject."""
        label = next(graph.objects(subject, RDFS.label), None)
        return str(label) if label else None
    
    def _get_comment(self, graph: Graph, subject: Any) -> str:
        """Get rdfs:comment for a subject."""
        comment = next(graph.objects(subject, RDFS.comment), None)
        return str(comment) if comment else None
    
    def close(self):
        """Close database connections."""
        if self.storage:
            self.storage.close()


def main():
    """Main function to run PROV-O import."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Import PROV-O into OntServe")
    parser.add_argument(
        "--force", 
        action="store_true", 
        help="Force re-import even if PROV-O already exists"
    )
    
    args = parser.parse_args()
    
    importer = None
    try:
        importer = ProvOImporter()
        result = importer.import_prov_o(force_refresh=args.force)
        
        if result['success']:
            print(f"✓ {result['message']}")
            print(f"  Domain: {result['domain']}")
            print(f"  Concepts imported: {result['concepts_imported']}")
            return 0
        else:
            print(f"✗ Import failed: {result.get('message', result.get('error'))}")
            return 1
            
    except KeyboardInterrupt:
        print("\nImport cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"✗ Import failed with unexpected error: {e}")
        return 1
    finally:
        if importer:
            importer.close()


if __name__ == "__main__":
    exit(main())
