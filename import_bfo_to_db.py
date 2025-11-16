#!/usr/bin/env python3
"""
Import BFO (Basic Formal Ontology) into the OntServe database.
"""

import os
import sys
from pathlib import Path

# Set environment
os.environ['ENVIRONMENT'] = 'development'

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from web.app import create_app
from web.models import db, Ontology, OntologyVersion
from datetime import datetime, timezone

def import_bfo():
    """Import BFO from the storage file into the database."""

    # Path to BFO file
    bfo_file = project_root / 'storage' / 'ontologies' / 'purl-obolibrary-org-obo-bfo-owl.ttl'

    if not bfo_file.exists():
        print(f"ERROR: BFO file not found at {bfo_file}")
        return 1

    # Read BFO content
    print(f"Reading BFO from {bfo_file}")
    with open(bfo_file, 'r', encoding='utf-8') as f:
        bfo_content = f.read()

    print(f"BFO content size: {len(bfo_content)} bytes")

    # Create Flask app
    app = create_app('development')

    with app.app_context():
        # Check if BFO already exists
        existing_bfo = db.session.query(Ontology).filter_by(name='bfo').first()

        if existing_bfo:
            print(f"BFO already exists in database (ID: {existing_bfo.id})")
            print("Updating existing BFO...")
            ontology = existing_bfo
        else:
            print("Creating new BFO ontology entry...")
            ontology = Ontology(
                name='bfo',
                base_uri='http://purl.obolibrary.org/obo/bfo.owl',
                description='Basic Formal Ontology - A top-level ontology designed to support scientific research',
                is_base=True,
                is_editable=False,
                ontology_type='base'
            )
            db.session.add(ontology)
            db.session.flush()  # Get the ID

        # Create or update version
        print("Creating ontology version...")
        version = OntologyVersion(
            ontology_id=ontology.id,
            version_number=1,
            version_tag='2.0',
            content=bfo_content,
            change_summary='BFO 2.0 imported from purl.obolibrary.org',
            created_by='system',
            is_current=True,
            is_draft=False,
            workflow_status='published'
        )
        db.session.add(version)

        # Commit
        db.session.commit()

        print(f"✅ Successfully imported BFO (Ontology ID: {ontology.id})")
        print(f"   Name: {ontology.name}")
        print(f"   Base URI: {ontology.base_uri}")
        print(f"   Description: {ontology.description}")

    return 0

if __name__ == "__main__":
    try:
        sys.exit(import_bfo())
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
