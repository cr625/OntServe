#!/usr/bin/env python3
"""
Extract entities from engineering-ethics ontology directly into OntServe database.
This bypasses the ontology manager and works directly with the database.
"""

import os
import sys
import rdflib
from rdflib import RDF, RDFS, OWL

# Add OntServe web directory to path
sys.path.insert(0, '/home/chris/onto/OntServe/web')

# Set up database connection
os.environ['DATABASE_URL'] = 'postgresql://ontserve_user:ontserve_development_password@localhost:5435/ontserve'

def extract_entities():
    """Extract entities from engineering-ethics ontology and save to database."""
    
    # Import after setting up path
    from app import create_app, db
    from models import Ontology, OntologyEntity
    
    print("🔍 Starting entity extraction for engineering-ethics ontology...")
    
    # Create app context
    app = create_app()
    with app.app_context():
        # Find the engineering-ethics ontology
        ontology = Ontology.query.filter_by(name='engineering-ethics').first()
        if not ontology:
            print("❌ Engineering-ethics ontology not found in database!")
            return False
            
        print(f"✓ Found ontology: {ontology.name} (ID: {ontology.id})")
        
        # Get the current version content
        current_version = ontology.current_version
        if not current_version or not current_version.content:
            print("❌ No content found for engineering-ethics ontology!")
            return False
            
        content = current_version.content
        print(f"✓ Found content: {len(content)} characters")
        
        # Parse RDF content
        print("🔍 Parsing RDF content...")
        g = rdflib.Graph()
        try:
            g.parse(data=content, format='turtle')
            print(f"✓ Successfully parsed RDF graph with {len(g)} triples")
        except Exception as e:
            print(f"❌ Failed to parse RDF content: {e}")
            return False
        
        # Clear existing entities for this ontology
        print("🗑️  Clearing existing entities...")
        deleted_count = OntologyEntity.query.filter_by(ontology_id=ontology.id).delete()
        print(f"✓ Deleted {deleted_count} existing entities")
        
        entity_counts = {'class': 0, 'property': 0, 'individual': 0}
        
        # Extract classes
        print("📝 Extracting classes...")
        for cls in g.subjects(RDF.type, OWL.Class):
            label = next(g.objects(cls, RDFS.label), None)
            comment = next(g.objects(cls, RDFS.comment), None)
            subclass_of = list(g.objects(cls, RDFS.subClassOf))
            
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='class',
                uri=str(cls),
                label=str(label) if label else None,
                comment=str(comment) if comment else None,
                parent_uri=str(subclass_of[0]) if subclass_of else None
            )
            db.session.add(entity)
            entity_counts['class'] += 1
        
        # Extract object properties
        print("📝 Extracting object properties...")
        for prop in g.subjects(RDF.type, OWL.ObjectProperty):
            label = next(g.objects(prop, RDFS.label), None)
            comment = next(g.objects(prop, RDFS.comment), None)
            domain = next(g.objects(prop, RDFS.domain), None)
            range_val = next(g.objects(prop, RDFS.range), None)
            
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='property',
                uri=str(prop),
                label=str(label) if label else None,
                comment=str(comment) if comment else None,
                domain=str(domain) if domain else None,
                range=str(range_val) if range_val else None
            )
            db.session.add(entity)
            entity_counts['property'] += 1
        
        # Extract datatype properties
        print("📝 Extracting datatype properties...")
        for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
            label = next(g.objects(prop, RDFS.label), None)
            comment = next(g.objects(prop, RDFS.comment), None)
            domain = next(g.objects(prop, RDFS.domain), None)
            range_val = next(g.objects(prop, RDFS.range), None)
            
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='property',
                uri=str(prop),
                label=str(label) if label else None,
                comment=str(comment) if comment else None,
                domain=str(domain) if domain else None,
                range=str(range_val) if range_val else None
            )
            db.session.add(entity)
            entity_counts['property'] += 1
        
        # Extract individuals
        print("📝 Extracting individuals...")
        for ind in g.subjects(RDF.type, OWL.NamedIndividual):
            label = next(g.objects(ind, RDFS.label), None)
            comment = next(g.objects(ind, RDFS.comment), None)
            
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='individual',
                uri=str(ind),
                label=str(label) if label else None,
                comment=str(comment) if comment else None
            )
            db.session.add(entity)
            entity_counts['individual'] += 1
        
        # Commit all changes
        print("💾 Saving entities to database...")
        try:
            db.session.commit()
            print("✅ Successfully saved all entities!")
        except Exception as e:
            print(f"❌ Failed to save entities: {e}")
            db.session.rollback()
            return False
        
        # Print summary
        print(f"\n📊 Entity Extraction Summary:")
        print(f"   Classes: {entity_counts['class']}")
        print(f"   Properties: {entity_counts['property']}")
        print(f"   Individuals: {entity_counts['individual']}")
        print(f"   Total: {sum(entity_counts.values())}")
        
        return True

if __name__ == "__main__":
    success = extract_entities()
    if success:
        print("\n🎉 Entity extraction completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Entity extraction failed!")
        sys.exit(1)