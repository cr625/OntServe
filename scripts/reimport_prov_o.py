#!/usr/bin/env python3
"""
Reimport W3C PROV-O with Canonical URI

Downloads and properly imports the W3C Provenance Ontology (PROV-O) 
using the canonical W3C URI and our standardized import process.
"""

import os
import sys
import requests
import shutil
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from web.config import config
from web.models import db, init_db, Ontology, OntologyEntity, OntologyVersion
import rdflib
from rdflib import RDF, RDFS, OWL

def reimport_prov_o():
    """Download and import PROV-O with canonical W3C URI."""
    
    print("OntServe - W3C PROV-O Reimport")
    print("=" * 50)
    
    # PROV-O configuration with canonical W3C URI
    prov_config = {
        'name': 'W3C Provenance Ontology (PROV-O)',
        'canonical_uri': 'https://www.w3.org/ns/prov.ttl',
        'base_uri': 'http://www.w3.org/ns/prov#',
        'description': 'The PROV Ontology provides classes, properties, and restrictions for representing provenance information',
        'download_path': 'storage/ontologies/prov-o.ttl'
    }
    
    # Create Flask app for database context
    app = Flask(__name__)
    app.config.from_object(config['development'])
    init_db(app)
    
    with app.app_context():
        # Check if PROV-O already exists
        existing_prov = Ontology.query.filter(
            db.or_(
                Ontology.name.ilike('%prov%'),
                Ontology.base_uri.like('%prov%')
            )
        ).first()
        
        if existing_prov:
            print(f"⚠️ Found existing PROV-O: {existing_prov.name} (ID: {existing_prov.id})")
            print(f"   Base URI: {existing_prov.base_uri}")
            confirm = input("   Delete and reimport? (y/n): ")
            
            if confirm.lower() != 'y':
                print("   ⏭️ Skipping reimport")
                return False
            
            # Delete existing PROV-O
            print("   🗑️ Removing existing PROV-O...")
            OntologyEntity.query.filter_by(ontology_id=existing_prov.id).delete()
            OntologyVersion.query.filter_by(ontology_id=existing_prov.id).delete()
            db.session.delete(existing_prov)
            db.session.commit()
            print("   ✅ Existing PROV-O removed")
        
        # Download PROV-O from canonical source
        print(f"\n📥 Downloading PROV-O from {prov_config['canonical_uri']}...")
        
        try:
            response = requests.get(prov_config['canonical_uri'], timeout=30)
            response.raise_for_status()
            content = response.text
            
            # Save to storage directory
            os.makedirs(os.path.dirname(prov_config['download_path']), exist_ok=True)
            with open(prov_config['download_path'], 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✅ Downloaded PROV-O ({len(content):,} characters)")
            
        except Exception as e:
            print(f"❌ Failed to download PROV-O: {e}")
            return False
        
        # Parse ontology to get statistics
        print("📊 Parsing ontology structure...")
        
        try:
            g = rdflib.Graph()
            g.parse(data=content, format='turtle')
            
            triple_count = len(g)
            classes = list(g.subjects(RDF.type, OWL.Class))
            obj_properties = list(g.subjects(RDF.type, OWL.ObjectProperty))
            data_properties = list(g.subjects(RDF.type, OWL.DatatypeProperty))
            
            class_count = len(classes)
            property_count = len(obj_properties) + len(data_properties)
            
            print(f"📈 Found: {triple_count} triples, {class_count} classes, {property_count} properties")
            
        except Exception as e:
            print(f"❌ Failed to parse PROV-O: {e}")
            return False
        
        # Create ontology record with proper canonical URI
        print("💾 Creating ontology record...")
        
        ontology = Ontology(
            name='w3c-prov-o',  # Use consistent naming
            base_uri=prov_config['base_uri'],  # Canonical W3C URI
            description=prov_config['description'],
            is_base=True,  # PROV-O is a foundational ontology
            is_editable=False,  # Standard ontologies shouldn't be edited
            ontology_type='base',
            meta_data={
                'canonical_source': prov_config['canonical_uri'],
                'w3c_standard': True,
                'reimported_date': datetime.now().isoformat(),
                'triple_count': triple_count,
                'import_method': 'standardized_reimport'
            }
        )
        db.session.add(ontology)
        db.session.flush()  # Get the ID
        
        print(f"✅ Created ontology record (ID: {ontology.id})")
        
        # Create initial version
        version = OntologyVersion(
            ontology_id=ontology.id,
            version_number=1,
            version_tag='1.0.0',
            content=content,
            change_summary='Reimport with canonical W3C URI and standardized fields',
            created_by='standardized-reimport',
            is_current=True,
            is_draft=False,
            workflow_status='published',
            meta_data={
                'source': prov_config['canonical_uri'],
                'import_method': 'standardized'
            }
        )
        db.session.add(version)
        
        # Extract entities (limit for performance)
        print("🔄 Extracting entities...")
        
        # Extract classes (first 100 for performance)
        for i, class_uri in enumerate(classes):
            if i >= 100:
                break
                
            # Get label and comment
            label = None
            comment = None
            parent_uri = None
            
            labels = list(g.objects(class_uri, RDFS.label))
            if labels:
                label = str(labels[0])
            
            comments = list(g.objects(class_uri, RDFS.comment))
            if comments:
                comment = str(comments[0])
            
            # Get parent class
            parents = list(g.objects(class_uri, RDFS.subClassOf))
            if parents:
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
        
        # Extract properties (first 50 for performance)
        all_properties = obj_properties + data_properties
        for i, prop_uri in enumerate(all_properties):
            if i >= 50:
                break
            
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
        
        print("\n" + "=" * 50)
        print("PROV-O REIMPORT SUMMARY")
        print("=" * 50)
        print(f"✅ Successfully reimported W3C PROV-O")
        print(f"   Name: {ontology.name}")
        print(f"   Canonical URI: {ontology.base_uri}")
        print(f"   Database ID: {ontology.id}")
        print(f"   Classes: {min(class_count, 100)} stored")
        print(f"   Properties: {min(property_count, 50)} stored")
        print(f"   Total triples: {triple_count}")
        
        print(f"\n🌐 Access at: http://localhost:5003/ontology/{ontology.name}")
        print(f"📁 File saved: {prov_config['download_path']}")
        
        return True

if __name__ == "__main__":
    success = reimport_prov_o()
    if success:
        print("\n🎉 PROV-O reimport completed successfully!")
        print("Repository now has consistent foundation ontologies with canonical URIs.")
    else:
        print("\n💥 PROV-O reimport failed")
    
    sys.exit(0 if success else 1)
