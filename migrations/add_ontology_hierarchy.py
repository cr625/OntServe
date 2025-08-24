"""
Database migration to add parent-child relationships to ontologies.

Adds parent_ontology_id and ontology_type fields to support derived ontologies.
"""

import sys
from pathlib import Path

# Add parent directory to path to import models
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from web.models import db
from web.config import config
from sqlalchemy import text


def create_migration_app():
    """Create a Flask app for running migrations."""
    app = Flask(__name__)
    app.config.from_object(config['development'])  # Use development config by default
    db.init_app(app)
    return app


def upgrade():
    """Apply the migration - add parent-child relationship fields."""
    app = create_migration_app()
    
    with app.app_context():
        try:
            print("Adding parent_ontology_id and ontology_type columns to ontologies table...")
            
            # Add parent_ontology_id column
            db.session.execute(text("""
                ALTER TABLE ontologies 
                ADD COLUMN IF NOT EXISTS parent_ontology_id INTEGER;
            """))
            
            # Add ontology_type column with default value
            db.session.execute(text("""
                ALTER TABLE ontologies 
                ADD COLUMN IF NOT EXISTS ontology_type VARCHAR(20) DEFAULT 'base';
            """))
            
            # Add foreign key constraint for parent_ontology_id
            db.session.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints 
                        WHERE constraint_name = 'fk_ontology_parent'
                    ) THEN
                        ALTER TABLE ontologies 
                        ADD CONSTRAINT fk_ontology_parent 
                        FOREIGN KEY (parent_ontology_id) REFERENCES ontologies(id);
                    END IF;
                END $$;
            """))
            
            # Create index on parent_ontology_id for better query performance
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ontology_parent 
                ON ontologies(parent_ontology_id);
            """))
            
            # Create index on ontology_type for filtering
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ontology_type 
                ON ontologies(ontology_type);
            """))
            
            db.session.commit()
            print("✓ Migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Migration failed: {e}")
            raise


def downgrade():
    """Rollback the migration - remove parent-child relationship fields."""
    app = create_migration_app()
    
    with app.app_context():
        try:
            print("Removing parent_ontology_id and ontology_type columns...")
            
            # Drop indexes first
            db.session.execute(text("DROP INDEX IF EXISTS idx_ontology_parent;"))
            db.session.execute(text("DROP INDEX IF EXISTS idx_ontology_type;"))
            
            # Drop foreign key constraint
            db.session.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.table_constraints 
                        WHERE constraint_name = 'fk_ontology_parent'
                    ) THEN
                        ALTER TABLE ontologies DROP CONSTRAINT fk_ontology_parent;
                    END IF;
                END $$;
            """))
            
            # Drop columns
            db.session.execute(text("ALTER TABLE ontologies DROP COLUMN IF EXISTS parent_ontology_id;"))
            db.session.execute(text("ALTER TABLE ontologies DROP COLUMN IF EXISTS ontology_type;"))
            
            db.session.commit()
            print("✓ Rollback completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Rollback failed: {e}")
            raise


def check_migration_needed():
    """Check if the migration needs to be applied."""
    app = create_migration_app()
    
    with app.app_context():
        try:
            # Check if the new columns exist
            result = db.session.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'ontologies' 
                AND column_name IN ('parent_ontology_id', 'ontology_type');
            """))
            existing_columns = [row[0] for row in result]
            
            if 'parent_ontology_id' not in existing_columns or 'ontology_type' not in existing_columns:
                return True
            else:
                return False
                
        except Exception as e:
            print(f"Error checking migration status: {e}")
            return True  # Assume migration is needed if we can't check


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Ontology hierarchy migration')
    parser.add_argument('action', choices=['upgrade', 'downgrade', 'check'], 
                       help='Migration action to perform')
    
    args = parser.parse_args()
    
    if args.action == 'upgrade':
        if check_migration_needed():
            upgrade()
        else:
            print("Migration already applied - no action needed")
    elif args.action == 'downgrade':
        downgrade()
    elif args.action == 'check':
        if check_migration_needed():
            print("Migration needed: parent_ontology_id and ontology_type columns missing")
        else:
            print("Migration not needed: columns already exist")
