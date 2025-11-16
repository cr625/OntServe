#!/usr/bin/env python3
"""
Clean up duplicate ontologies in the database.

Removes:
- Legacy "Basic Formal Ontology 2.0" (ID 21) - keeping newer "bfo" (ID 64)
- Duplicate test-ontology entries with no content (IDs 62, 63)
"""

import os
import sys
from pathlib import Path

os.environ['ENVIRONMENT'] = 'development'
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from web.app import create_app
from web.models import db, Ontology, OntologyVersion
from sqlalchemy import select, delete

def cleanup_duplicates():
    app = create_app('development')

    with app.app_context():
        print("=" * 80)
        print("CLEANING UP DUPLICATE ONTOLOGIES")
        print("=" * 80)

        # 1. Remove legacy BFO entry (ID 21)
        print("\n1. Removing legacy BFO entry...")
        legacy_bfo = db.session.get(Ontology, 21)
        if legacy_bfo:
            print(f"   Found: ID {legacy_bfo.id} - '{legacy_bfo.name}'")

            # Delete associated versions first
            version_stmt = delete(OntologyVersion).where(OntologyVersion.ontology_id == 21)
            result = db.session.execute(version_stmt)
            print(f"   Deleted {result.rowcount} version(s)")

            # Delete the ontology
            db.session.delete(legacy_bfo)
            print(f"   ✓ Deleted legacy BFO entry")
        else:
            print(f"   - Legacy BFO (ID 21) not found - may already be deleted")

        # 2. Remove duplicate test-ontology entries (no content)
        print("\n2. Removing duplicate test-ontology entries...")
        for test_id in [62, 63]:
            test_ont = db.session.get(Ontology, test_id)
            if test_ont:
                print(f"   Found: ID {test_ont.id} - '{test_ont.name}' (no content)")

                # Delete associated versions
                version_stmt = delete(OntologyVersion).where(OntologyVersion.ontology_id == test_id)
                result = db.session.execute(version_stmt)
                print(f"   Deleted {result.rowcount} version(s)")

                # Delete the ontology
                db.session.delete(test_ont)
                print(f"   ✓ Deleted test-ontology (ID {test_id})")
            else:
                print(f"   - test-ontology (ID {test_id}) not found - may already be deleted")

        # Commit all deletions
        db.session.commit()

        print("\n" + "=" * 80)
        print("CLEANUP COMPLETE")
        print("=" * 80)

        # Show remaining ontologies
        print("\nRemaining ontologies:")
        stmt = select(Ontology).order_by(Ontology.id)
        ontologies = db.session.execute(stmt).scalars().all()

        print(f"\n{'ID':<5} {'Name':<40} {'Type':<10}")
        print("-" * 80)
        for ont in ontologies:
            print(f"{ont.id:<5} {ont.name:<40} {ont.ontology_type:<10}")

        print(f"\nTotal ontologies: {len(ontologies)}")

if __name__ == "__main__":
    try:
        cleanup_duplicates()
        print("\n✅ Successfully cleaned up duplicate ontologies")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
