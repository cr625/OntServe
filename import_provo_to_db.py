#!/usr/bin/env python3
"""
Import PROV-O (PROV Ontology) into the OntServe database.
"""

import os
import sys
from pathlib import Path
import urllib.request

# Set environment
os.environ['ENVIRONMENT'] = 'development'

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from web.app import create_app
from web.models import db, Ontology, OntologyVersion
from datetime import datetime, timezone

def download_provo():
    """Download PROV-O from W3C."""
    prov_url = 'https://www.w3.org/ns/prov.ttl'
    storage_dir = project_root / 'storage' / 'ontologies'
    storage_dir.mkdir(parents=True, exist_ok=True)

    prov_file = storage_dir / 'prov-o.ttl'

    if prov_file.exists():
        print(f"PROV-O file already exists at {prov_file}")
        with open(prov_file, 'r', encoding='utf-8') as f:
            return f.read()

    print(f"Downloading PROV-O from {prov_url}...")
    try:
        with urllib.request.urlopen(prov_url) as response:
            content = response.read().decode('utf-8')

        # Save to storage
        with open(prov_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"✅ Downloaded PROV-O to {prov_file}")
        return content
    except Exception as e:
        print(f"ERROR downloading PROV-O: {e}")
        return None

def import_provo():
    """Import PROV-O into the database."""

    # Download PROV-O
    prov_content = download_provo()
    if not prov_content:
        return 1

    print(f"PROV-O content size: {len(prov_content)} bytes")

    # Create Flask app
    app = create_app('development')

    with app.app_context():
        # Check if PROV-O already exists
        existing_provo = db.session.query(Ontology).filter_by(name='prov-o').first()

        if existing_provo:
            print(f"PROV-O already exists in database (ID: {existing_provo.id})")
            print("Updating existing PROV-O...")
            ontology = existing_provo
        else:
            print("Creating new PROV-O ontology entry...")
            ontology = Ontology(
                name='prov-o',
                base_uri='http://www.w3.org/ns/prov#',
                description='PROV Ontology - W3C provenance ontology for representing and interchanging provenance information',
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
            version_tag='W3C Recommendation',
            content=prov_content,
            change_summary='PROV-O imported from w3.org',
            created_by='system',
            is_current=True,
            is_draft=False,
            workflow_status='published'
        )
        db.session.add(version)

        # Commit
        db.session.commit()

        print(f"✅ Successfully imported PROV-O (Ontology ID: {ontology.id})")
        print(f"   Name: {ontology.name}")
        print(f"   Base URI: {ontology.base_uri}")
        print(f"   Description: {ontology.description}")

    return 0

if __name__ == "__main__":
    try:
        sys.exit(import_provo())
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
