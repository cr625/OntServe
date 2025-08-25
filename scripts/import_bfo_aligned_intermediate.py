#!/usr/bin/env python
"""
Import the BFO-aligned ProEthica Intermediate Ontology as a new version.
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.app import create_app
from web.models import db, Ontology, OntologyVersion, OntologyEntity
from datetime import datetime
import rdflib
from rdflib import Graph, Namespace, RDF, RDFS, OWL

def extract_entities_from_turtle(content):
    """Extract entities from Turtle content."""
    g = Graph()
    g.parse(data=content, format='turtle')
    
    # Define namespaces
    PROETH = Namespace("http://proethica.org/ontology/intermediate#")
    BFO = Namespace("http://purl.obolibrary.org/obo/BFO_")
    IAO = Namespace("http://purl.obolibrary.org/obo/IAO_")
    RO = Namespace("http://purl.obolibrary.org/obo/RO_")
    
    entities = []
    
    # Extract classes
    for cls in g.subjects(RDF.type, OWL.Class):
        if isinstance(cls, rdflib.term.URIRef):
            cls_str = str(cls)
            if cls_str.startswith(str(PROETH)):
                # Get label
                label = None
                for lbl in g.objects(cls, RDFS.label):
                    label = str(lbl)
                    break
                
                # Get parent class (subClassOf)
                parent_uri = None
                for parent in g.objects(cls, RDFS.subClassOf):
                    if isinstance(parent, rdflib.term.URIRef):
                        parent_str = str(parent)
                        # Skip restrictions and owl:Thing
                        if not parent_str.startswith('_:') and parent_str != str(OWL.Thing):
                            parent_uri = parent_str
                            break
                
                # Get definition
                definition = None
                for defn in g.objects(cls, IAO['0000115']):
                    definition = str(defn)
                    break
                
                entities.append({
                    'uri': cls_str,
                    'label': label or cls_str.split('#')[-1],
                    'entity_type': 'class',
                    'parent_uri': parent_uri,
                    'properties': {'definition': definition} if definition else {}
                })
    
    # Extract object properties
    for prop in g.subjects(RDF.type, OWL.ObjectProperty):
        if isinstance(prop, rdflib.term.URIRef):
            prop_str = str(prop)
            if prop_str.startswith(str(PROETH)):
                # Get label
                label = None
                for lbl in g.objects(prop, RDFS.label):
                    label = str(lbl)
                    break
                
                # Get domain and range
                domain = None
                range_val = None
                for d in g.objects(prop, RDFS.domain):
                    if isinstance(d, rdflib.term.URIRef):
                        domain = str(d)
                        break
                for r in g.objects(prop, RDFS.range):
                    if isinstance(r, rdflib.term.URIRef):
                        range_val = str(r)
                        break
                
                # Get definition
                definition = None
                for defn in g.objects(prop, IAO['0000115']):
                    definition = str(defn)
                    break
                
                entities.append({
                    'uri': prop_str,
                    'label': label or prop_str.split('#')[-1],
                    'entity_type': 'property',
                    'domain': domain,
                    'range': range_val,
                    'properties': {'definition': definition} if definition else {}
                })
    
    return entities

def main():
    """Main import function."""
    app = create_app()
    
    with app.app_context():
        # Read the new ontology file
        ontology_path = '/home/chris/onto/OntServe/ontologies/proethica-intermediate-v5-bfo-aligned.ttl'
        with open(ontology_path, 'r') as f:
            content = f.read()
        
        print(f"Read {len(content)} characters from ontology file")
        
        # Find the existing proethica-intermediate ontology
        ontology = Ontology.query.filter_by(name='proethica-intermediate').first()
        if not ontology:
            print("Error: proethica-intermediate ontology not found in database")
            return
        
        print(f"Found ontology: {ontology.name} (ID: {ontology.id})")
        
        # Create new version
        new_version = OntologyVersion(
            ontology_id=ontology.id,
            version_number=5,
            version_tag='5.0.0-bfo-aligned',
            content=content,
            change_summary='Complete BFO alignment with proper hierarchical structure. Fixed temporary node parent URIs and added missing intermediate classes.',
            workflow_status='published',
            is_current=False,  # Will set to current after entity extraction
            is_draft=False,
            created_by='admin',
            created_at=datetime.utcnow(),
            metadata={
                'bfo_aligned': True,
                'imports': ['BFO 2.0', 'IAO 2020', 'RO 2015'],
                'profile': 'OWL 2 EL',
                'alignment_date': '2025-08-25'
            }
        )
        
        db.session.add(new_version)
        db.session.commit()
        print(f"Created version {new_version.version_number}: {new_version.version_tag}")
        
        # Extract and store entities
        print("Extracting entities from ontology...")
        entities = extract_entities_from_turtle(content)
        print(f"Extracted {len(entities)} entities")
        
        # Delete existing entities for this ontology
        OntologyEntity.query.filter_by(ontology_id=ontology.id).delete()
        
        # Add new entities
        class_count = 0
        property_count = 0
        hierarchical_count = 0
        
        for entity_data in entities:
            entity = OntologyEntity(
                ontology_id=ontology.id,
                uri=entity_data['uri'],
                label=entity_data.get('label'),
                entity_type=entity_data['entity_type'],
                parent_uri=entity_data.get('parent_uri'),
                domain=entity_data.get('domain'),
                range=entity_data.get('range'),
                properties=entity_data.get('properties', {})
            )
            db.session.add(entity)
            
            if entity_data['entity_type'] == 'class':
                class_count += 1
                if entity_data.get('parent_uri'):
                    hierarchical_count += 1
            elif entity_data['entity_type'] == 'property':
                property_count += 1
        
        # Update version metadata with statistics
        new_version.metadata['entity_statistics'] = {
            'total_entities': len(entities),
            'classes': class_count,
            'properties': property_count,
            'hierarchical_relationships': hierarchical_count
        }
        
        # Make this version current
        OntologyVersion.query.filter_by(
            ontology_id=ontology.id
        ).update({'is_current': False})
        new_version.is_current = True
        
        # Update ontology statistics
        ontology.triple_count = len(entities)
        ontology.class_count = class_count
        ontology.property_count = property_count
        
        db.session.commit()
        
        print(f"\n✅ Successfully imported BFO-aligned ontology:")
        print(f"  Version: {new_version.version_tag}")
        print(f"  Classes: {class_count}")
        print(f"  Properties: {property_count}")
        print(f"  Hierarchical relationships: {hierarchical_count}")
        print(f"\n🎯 Version {new_version.version_number} is now the current version")
        print(f"\n📊 View at: http://localhost:5003/ontology/proethica-intermediate")

if __name__ == '__main__':
    main()