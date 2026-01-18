"""
Database migration to add case extraction versioning support.

Adds columns to concepts table:
- case_id: Which case this concept was extracted from
- extraction_run_version: Version number within a case (increments on re-extraction)
- is_current: Whether this is the current version for this case+URI combination
- superseded_at: When this version was superseded
- entity_class: 'class' or 'individual' (for TTL file routing)

This enables:
- Overwriting case TTL files on re-extraction
- Preserving historical versions in the database
- Individual class versioning across cases
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
    app.config.from_object(config['development'])
    db.init_app(app)
    return app


def upgrade():
    """Apply the migration - add case extraction versioning columns."""
    app = create_migration_app()

    with app.app_context():
        try:
            print("Adding case extraction versioning columns to concepts table...")

            # Add case_id column
            db.session.execute(text("""
                ALTER TABLE concepts
                ADD COLUMN IF NOT EXISTS case_id INTEGER;
            """))
            print("  - Added case_id column")

            # Add extraction_run_version column (version within a case)
            db.session.execute(text("""
                ALTER TABLE concepts
                ADD COLUMN IF NOT EXISTS extraction_run_version INTEGER DEFAULT 1;
            """))
            print("  - Added extraction_run_version column")

            # Add is_current column
            db.session.execute(text("""
                ALTER TABLE concepts
                ADD COLUMN IF NOT EXISTS is_current BOOLEAN DEFAULT true;
            """))
            print("  - Added is_current column")

            # Add superseded_at column
            db.session.execute(text("""
                ALTER TABLE concepts
                ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMP WITH TIME ZONE;
            """))
            print("  - Added superseded_at column")

            # Add entity_class column ('class' or 'individual')
            db.session.execute(text("""
                ALTER TABLE concepts
                ADD COLUMN IF NOT EXISTS entity_class VARCHAR(20) DEFAULT 'individual';
            """))
            print("  - Added entity_class column")

            # Create indexes for efficient queries
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_concepts_case_id
                ON concepts(case_id);
            """))

            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_concepts_case_current
                ON concepts(case_id, is_current)
                WHERE case_id IS NOT NULL;
            """))

            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_concepts_uri_current
                ON concepts(uri, is_current);
            """))

            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_concepts_entity_class
                ON concepts(entity_class);
            """))
            print("  - Created indexes")

            # Add comment to table
            db.session.execute(text("""
                COMMENT ON COLUMN concepts.case_id IS
                'Case ID this concept was extracted from (null for ontology-defined concepts)';
            """))
            db.session.execute(text("""
                COMMENT ON COLUMN concepts.extraction_run_version IS
                'Version number within a case - increments each time case is re-extracted';
            """))
            db.session.execute(text("""
                COMMENT ON COLUMN concepts.is_current IS
                'True if this is the current/active version, false for historical versions';
            """))
            db.session.execute(text("""
                COMMENT ON COLUMN concepts.entity_class IS
                'Whether this is a class (shared across cases) or individual (case-specific)';
            """))

            db.session.commit()
            print("Migration completed successfully!")

        except Exception as e:
            db.session.rollback()
            print(f"Migration failed: {e}")
            raise


def downgrade():
    """Rollback the migration - remove case extraction versioning columns."""
    app = create_migration_app()

    with app.app_context():
        try:
            print("Removing case extraction versioning columns...")

            # Drop indexes first
            db.session.execute(text("DROP INDEX IF EXISTS idx_concepts_case_id;"))
            db.session.execute(text("DROP INDEX IF EXISTS idx_concepts_case_current;"))
            db.session.execute(text("DROP INDEX IF EXISTS idx_concepts_uri_current;"))
            db.session.execute(text("DROP INDEX IF EXISTS idx_concepts_entity_class;"))

            # Drop columns
            db.session.execute(text("ALTER TABLE concepts DROP COLUMN IF EXISTS case_id;"))
            db.session.execute(text("ALTER TABLE concepts DROP COLUMN IF EXISTS extraction_run_version;"))
            db.session.execute(text("ALTER TABLE concepts DROP COLUMN IF EXISTS is_current;"))
            db.session.execute(text("ALTER TABLE concepts DROP COLUMN IF EXISTS superseded_at;"))
            db.session.execute(text("ALTER TABLE concepts DROP COLUMN IF EXISTS entity_class;"))

            db.session.commit()
            print("Rollback completed successfully!")

        except Exception as e:
            db.session.rollback()
            print(f"Rollback failed: {e}")
            raise


def check_migration_needed():
    """Check if the migration needs to be applied."""
    app = create_migration_app()

    with app.app_context():
        try:
            result = db.session.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'concepts'
                AND column_name IN ('case_id', 'extraction_run_version', 'is_current', 'entity_class');
            """))
            existing_columns = [row[0] for row in result]

            needed_columns = ['case_id', 'extraction_run_version', 'is_current', 'entity_class']
            missing = [col for col in needed_columns if col not in existing_columns]

            if missing:
                print(f"Missing columns: {missing}")
                return True
            return False

        except Exception as e:
            print(f"Error checking migration status: {e}")
            return True


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Case extraction versioning migration')
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
            print("Migration needed")
        else:
            print("Migration not needed: columns already exist")
