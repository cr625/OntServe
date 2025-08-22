#!/usr/bin/env python3
"""
Combine engineering-ethics with proethica-intermediate entities for complete visualization.

This script creates a combined view by copying the main category entities from 
proethica-intermediate into the engineering-ethics ontology so we can see the 
complete hierarchy in one visualization.
"""

import os
import sys

# Change to web directory and import from there
web_dir = '/home/chris/onto/OntServe/web'
os.chdir(web_dir)
sys.path.insert(0, web_dir)
sys.path.insert(0, '/home/chris/onto/OntServe')

from app import create_app, db
from web.models import Ontology, OntologyEntity


def main():
    """Combine ontologies for complete visualization."""
    
    app = create_app()
    with app.app_context():
        # Get the engineering-ethics ontology
        engineering_ethics = db.session.query(Ontology).filter_by(ontology_id='engineering-ethics').first()
        if not engineering_ethics:
            print("❌ Error: engineering-ethics ontology not found. Run import_engineering_ethics.py first.")
            return False
        
        # Get the proethica-intermediate ontology  
        proethica_intermediate = db.session.query(Ontology).filter_by(ontology_id='proethica-intermediate').first()
        if not proethica_intermediate:
            print("❌ Error: proethica-intermediate ontology not found.")
            return False
        
        print(f"✅ Found engineering-ethics ontology (ID: {engineering_ethics.id})")
        print(f"✅ Found proethica-intermediate ontology (ID: {proethica_intermediate.id})")
        
        # Get the main category entities from proethica-intermediate
        main_categories = ['Role', 'Principle', 'Obligation', 'State', 'Resource', 'Action', 'Event', 'Capability', 'Constraint']
        
        intermediate_entities = db.session.query(OntologyEntity).filter_by(ontology_id=proethica_intermediate.id).all()
        print(f"📋 Found {len(intermediate_entities)} entities in proethica-intermediate")
        
        # Find the main category entities
        category_entities = []
        for category in main_categories:
            matching = [e for e in intermediate_entities if e.label and e.label.lower() == category.lower()]
            if matching:
                category_entities.extend(matching)
                print(f"   ✅ Found {category}: {matching[0].uri}")
            else:
                print(f"   ❌ Missing {category}")
        
        print(f"📊 Found {len(category_entities)} main category entities to copy")
        
        # Check if these entities already exist in engineering-ethics
        engineering_entities = db.session.query(OntologyEntity).filter_by(ontology_id=engineering_ethics.id).all()
        existing_uris = {e.uri for e in engineering_entities}
        
        # Copy the category entities to engineering-ethics ontology
        copied_count = 0
        for entity in category_entities:
            if entity.uri not in existing_uris:
                # Create a copy of the entity for the engineering-ethics ontology
                new_entity = OntologyEntity(
                    ontology_id=engineering_ethics.id,
                    entity_type=entity.entity_type,
                    uri=entity.uri,
                    label=entity.label,
                    comment=entity.comment,
                    parent_uri=entity.parent_uri,
                    domain=entity.domain,
                    range=entity.range,
                    properties=entity.properties,
                    embedding=entity.embedding
                )
                db.session.add(new_entity)
                copied_count += 1
                print(f"   ➕ Copied {entity.label}: {entity.uri}")
            else:
                print(f"   ⏭️  Skipped {entity.label}: already exists")
        
        # Also copy some key intermediate entities that are parents
        key_parents = ['EngineerRole', 'ProfessionalRole', 'ParticipantRole']
        for parent_name in key_parents:
            matching = [e for e in intermediate_entities if e.label and parent_name.lower() in e.label.lower()]
            for entity in matching:
                if entity.uri not in existing_uris:
                    new_entity = OntologyEntity(
                        ontology_id=engineering_ethics.id,
                        entity_type=entity.entity_type,
                        uri=entity.uri,
                        label=entity.label,
                        comment=entity.comment,
                        parent_uri=entity.parent_uri,
                        domain=entity.domain,
                        range=entity.range,
                        properties=entity.properties,
                        embedding=entity.embedding
                    )
                    db.session.add(new_entity)
                    copied_count += 1
                    print(f"   ➕ Copied parent {entity.label}: {entity.uri}")
        
        # Commit the changes
        if copied_count > 0:
            db.session.commit()
            print(f"✅ Successfully copied {copied_count} entities to engineering-ethics")
            
            # Verify the complete hierarchy
            print(f"\\n🔍 Verifying complete hierarchy...")
            updated_entities = db.session.query(OntologyEntity).filter_by(ontology_id=engineering_ethics.id).all()
            print(f"📊 Total entities in engineering-ethics: {len(updated_entities)}")
            
            # Show the hierarchy for roles
            print(f"\\n👥 Role hierarchy in combined ontology:")
            role_entities = [e for e in updated_entities if 'role' in (e.label or '').lower()]
            for entity in sorted(role_entities, key=lambda x: x.label or ''):
                parent_info = f" -> {entity.parent_uri}" if entity.parent_uri else " (NO PARENT)"
                print(f"   {entity.label}{parent_info}")
            
            # Show connections to main categories
            print(f"\\n🔗 Entities connecting to main categories:")
            for category in main_categories:
                category_uri = f"http://proethica.org/ontology/intermediate#{category}"
                connecting = [e for e in updated_entities if e.parent_uri == category_uri]
                if connecting:
                    print(f"   {category} ({len(connecting)} children):")
                    for child in connecting[:3]:  # Show first 3
                        print(f"     - {child.label}")
                    if len(connecting) > 3:
                        print(f"     - ... and {len(connecting) - 3} more")
            
            return True
        else:
            print("ℹ️  No new entities to copy - combination already complete")
            return True


if __name__ == "__main__":
    print("🔗 Combining Engineering Ethics with ProEthica Intermediate")
    print("=" * 60)
    
    success = main()
    
    if success:
        print("\\n🎉 Combination completed successfully!")
        print("💡 You can now visualize the complete hierarchy at:")
        print("   http://localhost:8000/editor/ontology/engineering-ethics/visualize")
        print("\\n🌟 The visualization should now show:")
        print("   • All 9 main categories (Role, Principle, etc.)")
        print("   • Engineering-specific entities as children")
        print("   • Complete hierarchical connections")
    else:
        print("\\n💥 Combination failed!")
        sys.exit(1)