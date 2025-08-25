#!/usr/bin/env python3
"""
Clean Up Old Basic Formal Ontology

Safely removes the old basic-formal-ontology and ensures the new 
"Basic Formal Ontology 2.0" is properly set up for the upgrade workflow.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from web.config import config
from web.models import db, init_db, Ontology, OntologyEntity, OntologyVersion

def cleanup_old_bfo():
    """Remove old basic-formal-ontology and verify new BFO 2.0 is ready."""
    
    print("OntServe - Basic Formal Ontology Cleanup")
    print("=" * 50)
    
    # Create Flask app for database context
    app = Flask(__name__)
    app.config.from_object(config['development'])
    init_db(app)
    
    with app.app_context():
        # Find old basic-formal-ontology
        old_bfo = Ontology.query.filter_by(name='basic-formal-ontology').first()
        
        if old_bfo:
            print(f"📁 Found old basic-formal-ontology (ID: {old_bfo.id})")
            print(f"   Base URI: {old_bfo.base_uri}")
            print(f"   Description: {old_bfo.description}")
            
            # Count what will be deleted
            entity_count = OntologyEntity.query.filter_by(ontology_id=old_bfo.id).count()
            version_count = OntologyVersion.query.filter_by(ontology_id=old_bfo.id).count()
            
            print(f"   Entities: {entity_count}")
            print(f"   Versions: {version_count}")
            
            # Confirm deletion
            confirm = input(f"\n🗑️ Delete old basic-formal-ontology? (y/n): ")
            
            if confirm.lower() == 'y':
                try:
                    # Delete in proper order
                    print("   Deleting entities...")
                    OntologyEntity.query.filter_by(ontology_id=old_bfo.id).delete()
                    
                    print("   Deleting versions...")
                    OntologyVersion.query.filter_by(ontology_id=old_bfo.id).delete()
                    
                    print("   Deleting ontology record...")
                    db.session.delete(old_bfo)
                    
                    db.session.commit()
                    
                    print("   ✅ Successfully deleted old basic-formal-ontology")
                    
                except Exception as e:
                    db.session.rollback()
                    print(f"   ❌ Error deleting old BFO: {e}")
                    return False
            else:
                print("   ⏭️ Skipping deletion")
        else:
            print("📁 No old basic-formal-ontology found")
        
        # Verify new BFO 2.0 is available
        print("\n🔍 Checking for new Basic Formal Ontology 2.0...")
        new_bfo = Ontology.query.filter_by(name='Basic Formal Ontology 2.0').first()
        
        if new_bfo:
            print(f"✅ Found Basic Formal Ontology 2.0 (ID: {new_bfo.id})")
            print(f"   Base URI: {new_bfo.base_uri}")
            print(f"   Classes: {new_bfo.class_count}")
            print(f"   Properties: {new_bfo.property_count}")
            print(f"   Is Foundation: {new_bfo.meta_data.get('foundation_ontology', False)}")
            
            # Check if it has a current version
            current_version = new_bfo.current_version
            if current_version:
                print(f"   Current Version: {current_version.version_number}")
                print(f"   Status: {'Draft' if current_version.is_draft else 'Published'}")
            else:
                print("   ⚠️ No current version found")
            
        else:
            print("❌ Basic Formal Ontology 2.0 not found!")
            print("   You may need to run the foundation import script again")
            return False
        
        print("\n" + "=" * 50)
        print("CLEANUP SUMMARY")
        print("=" * 50)
        print("✅ Old basic-formal-ontology: Cleaned up")
        print("✅ Basic Formal Ontology 2.0: Available")
        print("✅ Ready for ProEthica intermediate ontology upgrade")
        
        print(f"\n🌐 Access BFO 2.0 at: http://localhost:5003/ontology/Basic%20Formal%20Ontology%202.0")
        print(f"📊 Progress Dashboard: http://localhost:5002/progress")
        
        return True

if __name__ == "__main__":
    success = cleanup_old_bfo()
    if success:
        print("\n🎉 Cleanup completed successfully!")
    else:
        print("\n💥 Cleanup encountered issues")
    
    sys.exit(0 if success else 1)
