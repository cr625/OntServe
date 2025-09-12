#!/usr/bin/env python
"""
Reload proethica-intermediate ontology with new state classes
"""

import sys
import os
sys.path.append('/home/chris/onto/OntServe')

from web.app import create_app
from storage.models import db, Ontology, OntologyVersion
from storage.manager import OntologyManager

def reload_ontology():
    """Reload proethica-intermediate ontology with new state classes"""
    
    app = create_app()
    
    with app.app_context():
        # Read the updated TTL file
        ttl_path = '/home/chris/onto/OntServe/ontologies/proethica-intermediate.ttl'
        with open(ttl_path, 'r') as f:
            ttl_content = f.read()
        
        # Get the existing ontology
        ontology = Ontology.query.filter_by(name='proethica-intermediate').first()
        
        if not ontology:
            print("ERROR: proethica-intermediate ontology not found in database")
            print("Creating new ontology...")
            
            # Create new ontology
            manager = OntologyManager()
            result = manager.import_ontology(
                file_path=ttl_path,
                name='proethica-intermediate',
                description='ProEthica Intermediate Ontology with State Classes',
                format='turtle'
            )
            
            if result['success']:
                print(f"Successfully created ontology: {result['message']}")
                print(f"Entities extracted: {result.get('entity_counts', {})}")
            else:
                print(f"ERROR: {result['message']}")
            return
        
        print(f"Found ontology: {ontology.name} (ID: {ontology.id})")
        
        # Get current version
        current_version = OntologyVersion.query.filter_by(
            ontology_id=ontology.id, 
            is_current=True
        ).first()
        
        if current_version:
            print(f"Current version: {current_version.version_number} ({current_version.version_tag})")
            next_version_num = current_version.version_number + 1
        else:
            next_version_num = 1
        
        # Create new version
        new_version = OntologyVersion(
            ontology_id=ontology.id,
            version_number=next_version_num,
            version_tag=f"1.{next_version_num}.0",
            content=ttl_content,
            change_summary="Added state classes based on Chapter 2.2.4 literature review",
            created_by="system",
            is_current=True,
            is_draft=False,
            workflow_status='published'
        )
        
        # Set previous version to not current
        if current_version:
            current_version.is_current = False
        
        # Add and commit
        db.session.add(new_version)
        db.session.commit()
        
        print(f"Created new version: {new_version.version_number} ({new_version.version_tag})")
        
        # Re-extract entities
        from storage.entity_extractor import _extract_entities_from_content
        entity_counts = _extract_entities_from_content(ontology, ttl_content)
        
        print(f"Entities extracted: {entity_counts}")
        
        # Query for state entities
        from storage.models import OntologyEntity
        state_entities = OntologyEntity.query.filter(
            OntologyEntity.ontology_id == ontology.id,
            OntologyEntity.label.ilike('%state%')
        ).all()
        
        print(f"\nFound {len(state_entities)} state-related entities:")
        for entity in state_entities[:10]:
            print(f"  - {entity.label}: {entity.uri}")

if __name__ == "__main__":
    reload_ontology()