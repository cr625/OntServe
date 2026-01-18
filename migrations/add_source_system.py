"""
Database migration to add source_system column to ontologies table.

Adds a source_system column to identify where ontologies originated:
- proethica: Ontologies from ProEthica extraction pipeline
- external: Imported from external sources (BFO, PROV-O, etc.)
- manual: Manually created ontologies
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
    """Apply the migration - add source_system column."""
    app = create_migration_app()

    with app.app_context():
        try:
            print("Adding source_system column to ontologies table...")

            # Add source_system column
            db.session.execute(text("""
                ALTER TABLE ontologies
                ADD COLUMN IF NOT EXISTS source_system VARCHAR(50) DEFAULT 'manual';
            """))
            print("  - Added source_system column")

            # Create index for filtering
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ontologies_source_system
                ON ontologies(source_system);
            """))
            print("  - Created index")

            # Add comment
            db.session.execute(text("""
                COMMENT ON COLUMN ontologies.source_system IS
                'Source system: proethica, external, manual';
            """))

            db.session.commit()
            print("Migration completed successfully!")

            # Now populate existing data
            print("\nPopulating source_system for existing ontologies...")
            populate_source_systems()

        except Exception as e:
            db.session.rollback()
            print(f"Migration failed: {e}")
            raise


def populate_source_systems():
    """Populate source_system values for existing ontologies."""
    app = create_migration_app()

    with app.app_context():
        try:
            # ProEthica ontologies
            db.session.execute(text("""
                UPDATE ontologies
                SET source_system = 'proethica'
                WHERE name LIKE 'proethica-%';
            """))

            # External/imported ontologies
            db.session.execute(text("""
                UPDATE ontologies
                SET source_system = 'external'
                WHERE name IN (
                    'bfo', 'w3c-prov-o', 'engineering-ethics',
                    'Information Artifact Ontology 2020',
                    'Relations Ontology 2015',
                    'Terminological Foundations',
                    'IFC Integration for Engineering Ethics',
                    'semantic-change-ontology'
                );
            """))

            # Code of Ethics ontologies
            db.session.execute(text("""
                UPDATE ontologies
                SET source_system = 'external'
                WHERE name LIKE '%Code of Ethics%';
            """))

            db.session.commit()

            # Show results
            result = db.session.execute(text("""
                SELECT source_system, COUNT(*) as count
                FROM ontologies
                GROUP BY source_system
                ORDER BY source_system;
            """))
            print("\nSource system distribution:")
            for row in result:
                print(f"  {row[0]}: {row[1]} ontologies")

        except Exception as e:
            db.session.rollback()
            print(f"Population failed: {e}")
            raise


def downgrade():
    """Rollback the migration - remove source_system column."""
    app = create_migration_app()

    with app.app_context():
        try:
            print("Removing source_system column...")

            db.session.execute(text("DROP INDEX IF EXISTS idx_ontologies_source_system;"))
            db.session.execute(text("ALTER TABLE ontologies DROP COLUMN IF EXISTS source_system;"))

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
                WHERE table_name = 'ontologies'
                AND column_name = 'source_system';
            """))
            existing = [row[0] for row in result]
            return 'source_system' not in existing

        except Exception as e:
            print(f"Error checking migration status: {e}")
            return True


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Source system migration')
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
            print("Migration needed: source_system column missing")
        else:
            print("Migration not needed: column already exists")
