#!/usr/bin/env python3
"""
Migration script to add draft workflow fields to OntServe database.
Adds is_draft and workflow_status fields to ontology_versions table.
"""

import os
import sys
sys.path.insert(0, '/home/chris/onto/OntServe/web')

# Set up database connection
os.environ['DATABASE_URL'] = 'postgresql://postgres:PASS@localhost:5432/ontserve'

def migrate_database():
    """Add draft workflow fields to ontology_versions table."""
    from app import create_app, db
    from models import OntologyVersion
    from sqlalchemy import text
    
    app = create_app()
    with app.app_context():
        try:
            print("🔄 Adding draft workflow fields to ontology_versions table...")
            
            # Add the new columns using raw SQL since the model is already updated
            with db.engine.connect() as conn:
                conn.execute(text('''
                    ALTER TABLE ontology_versions 
                    ADD COLUMN IF NOT EXISTS is_draft BOOLEAN DEFAULT true,
                    ADD COLUMN IF NOT EXISTS workflow_status VARCHAR(20) DEFAULT 'draft';
                '''))
                conn.commit()
            
            print("✅ Successfully added is_draft and workflow_status columns")
            
            # Update existing records to be published (non-draft) by default
            with db.engine.connect() as conn:
                conn.execute(text('''
                    UPDATE ontology_versions 
                    SET is_draft = false, workflow_status = 'published' 
                    WHERE is_draft IS NULL OR workflow_status IS NULL;
                '''))
                conn.commit()
            
            print("✅ Updated existing versions as published")
            print("🎉 Database migration completed successfully!")
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            return False
            
        return True

if __name__ == "__main__":
    success = migrate_database()
    if success:
        print("\n🎉 Migration completed successfully!")
        print("   - Added is_draft BOOLEAN column (default: true)")
        print("   - Added workflow_status VARCHAR(20) column (default: 'draft')")
        print("   - Existing versions marked as published")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)