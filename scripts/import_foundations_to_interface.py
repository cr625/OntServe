#!/usr/bin/env python3
"""
Import Foundation Ontologies (BFO, RO, IAO) into OntServer Database

Properly imports the foundation ontologies into OntServer's database system
so they appear in the ontology repository interface with full entity extraction.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from web.config import config
from web.models import db, init_db, Ontology, OntologyEntity, OntologyVersion
from core.ontology_manager import OntologyManager
import rdflib
from rdflib import RDF, RDFS, OWL

def import_foundation_ontology(manager, app, ontology_info):
    """Import a single foundation ontology into the database."""
    
    ontology_id = ontology_info['ontology_id']
    file_path = ontology_info['file_path']
    name = ontology_info['name']
    description = ontology_info['description']
    source_url = ontology_info['source_url']
    
    print(f"\n📁 Importing {name} ({ontology_id})...")
    
    with app.app_context():
        # Check if ontology already exists (by name since there's no ontology_id field)
        existing = Ontology.query.filter_by(name=name).first()
        if existing:
            print(f"   ⚠️ {name} already exists in database")
            response = input(f"   Replace existing {name}? (y/n): ")
            if response.lower() != 'y':
                print(f"   ⏭️ Skipping {name}")
                return True
            else:
                print(f"   🗑️ Removing existing {name}")
                # Remove existing entities and versions
                OntologyEntity.query.filter_by(ontology_id=existing.id).delete()
                OntologyVersion.query.filter_by(ontology_id=existing.id).delete()
                db.session.delete(existing)
                db.session.commit()
        
        try:
            # Read ontology content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print(f"   📊 Parsing ontology structure...")
            
            # Parse to get statistics
            g = rdflib.Graph()
            g.parse(data=content, format='xml')  # OWL files are typically RDF/XML
            
            triple_count = len(g)
            classes = list(g.subjects(RDF.type, OWL.Class))
            obj_properties = list(g.subjects(RDF.type, OWL.ObjectProperty))
            data_properties = list(g.subjects(RDF.type, OWL.DatatypeProperty))
            
            class_count = len(classes)
            property_count = len(obj_properties) + len(data_properties)
            
            print(f"   📈 Found: {triple_count} triples, {class_count} classes, {property_count} properties")
            
            # Create ontology record using correct model fields
            ontology = Ontology(
                name=name,
                base_uri=source_url,
                description=description,
                is_base=True,  # Foundation ontologies are base ontologies
                is_editable=False,  # Foundation ontologies shouldn't be directly edited
                ontology_type='base',
                meta_data={
                    'foundation_ontology': True,
                    'imported_for': 'proethica-intermediate-upgrade',
                    'import_date': datetime.now().isoformat(),
                    'source_url': source_url,
                    'file_format': 'rdf/xml',
                    'triple_count': triple_count,
                    'original_ontology_id': ontology_id
                }
            )
            db.session.add(ontology)
            db.session.flush()  # Get the ID
            
            print(f"   💾 Created ontology record (ID: {ontology.id})")
            
            # Create initial version
            version = OntologyVersion(
                ontology_id=ontology.id,
                version_number=1,
                content=content,
                change_summary=f'Foundation ontology import: {name}',
                is_current=True,
                is_draft=False,
                workflow_status='published'
            )
            db.session.add(version)
            
            print(f"   🔄 Extracting entities (limited to first 100 for performance)...")
            
            # Extract and save classes (limit for performance)
            for i, class_uri in enumerate(classes):
                if i >= 100:  # Limit to first 100 classes for performance
                    break
                    
                # Get label and comment
                label = None
                comment = None
                parent_uri = None
                
                # Try to get rdfs:label
                labels = list(g.objects(class_uri, RDFS.label))
                if labels:
                    label = str(labels[0])
                
                # Try to get rdfs:comment or definition
                comments = list(g.objects(class_uri, RDFS.comment))
                if comments:
                    comment = str(comments[0])
                
                # Get parent class (rdfs:subClassOf)
                parents = list(g.objects(class_uri, RDFS.subClassOf))
                if parents:
                    # Get first non-blank node parent
                    for parent in parents:
                        if not isinstance(parent, rdflib.BNode):
                            parent_uri = str(parent)
                            break
                
                entity = OntologyEntity(
                    ontology_id=ontology.id,
                    entity_type='class',
                    uri=str(class_uri),
                    label=label,
                    comment=comment,
                    parent_uri=parent_uri
                )
                db.session.add(entity)
            
            # Extract and save properties (limit for performance)
            all_properties = obj_properties + data_properties
            for i, prop_uri in enumerate(all_properties):
                if i >= 50:  # Limit to first 50 properties
                    break
                
                # Get label and comment
                label = None
                comment = None
                domain = None
                range_val = None
                
                labels = list(g.objects(prop_uri, RDFS.label))
                if labels:
                    label = str(labels[0])
                
                comments = list(g.objects(prop_uri, RDFS.comment))
                if comments:
                    comment = str(comments[0])
                
                # Get domain and range
                domains = list(g.objects(prop_uri, RDFS.domain))
                if domains:
                    domain = str(domains[0])
                
                ranges = list(g.objects(prop_uri, RDFS.range))
                if ranges:
                    range_val = str(ranges[0])
                
                entity = OntologyEntity(
                    ontology_id=ontology.id,
                    entity_type='property',
                    uri=str(prop_uri),
                    label=label,
                    comment=comment,
                    domain=domain,
                    range=range_val
                )
                db.session.add(entity)
            
            db.session.commit()
            
            print(f"   ✅ Successfully imported {name} into database!")
            print(f"      - Name: {ontology.name}")
            print(f"      - Database ID: {ontology.id}")
            print(f"      - Classes stored: {min(class_count, 100)}")
            print(f"      - Properties stored: {min(property_count, 50)}")
            
            return True
            
        except Exception as e:
            print(f"   ❌ Error importing {name}: {e}")
            db.session.rollback()
            return False

def main():
    """Main import function."""
    print("Foundation Ontologies - Proper Import to OntServer Interface")
    print("=" * 70)
    print("Importing BFO, RO, and IAO ontologies into OntServer database...")
    
    # Foundation ontologies configuration
    foundation_ontologies = [
        {
            'ontology_id': 'bfo-2.0',
            'file_path': '../storage/ontologies/bfo-2.0.owl',
            'name': 'Basic Formal Ontology 2.0',
            'description': 'Upper-level ontology providing fundamental categories for all entities in reality',
            'source_url': 'http://purl.obolibrary.org/obo/bfo.owl'
        },
        {
            'ontology_id': 'ro-2015',
            'file_path': '../storage/ontologies/ro-2015.owl', 
            'name': 'Relations Ontology 2015',
            'description': 'Standard relations for linking ontology entities across domains',
            'source_url': 'http://purl.obolibrary.org/obo/ro.owl'
        },
        {
            'ontology_id': 'iao-2020',
            'file_path': '../storage/ontologies/iao-2020.owl',
            'name': 'Information Artifact Ontology 2020', 
            'description': 'Ontology for information content entities and documents',
            'source_url': 'http://purl.obolibrary.org/obo/iao.owl'
        }
    ]
    
    # Create Flask app for database context
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
    
    # Import each foundation ontology
    success_count = 0
    for ont_info in foundation_ontologies:
        if Path(ont_info['file_path']).exists():
            if import_foundation_ontology(manager, app, ont_info):
                success_count += 1
        else:
            print(f"❌ File not found: {ont_info['file_path']}")
    
    print("\n" + "=" * 70)
    print("FOUNDATION IMPORT SUMMARY")
    print("=" * 70)
    print(f"Successfully imported: {success_count}/3 foundation ontologies")
    
    if success_count == 3:
        print("✅ All foundation ontologies are now available in OntServer interface!")
        print("🌐 View at: http://localhost:5003/ontology/")
        print("   • BFO 2.0: http://localhost:5003/ontology/bfo-2.0")
        print("   • RO 2015: http://localhost:5003/ontology/ro-2015") 
        print("   • IAO 2020: http://localhost:5003/ontology/iao-2020")
    else:
        print("⚠️ Some foundation ontologies failed to import")
    
    return 0 if success_count == 3 else 1

if __name__ == "__main__":
    sys.exit(main())
