#!/usr/bin/env python3
"""Check ontologies in the database."""

import os
import sys
from pathlib import Path

os.environ['ENVIRONMENT'] = 'development'
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from web.app import create_app
from web.models import db, Ontology, OntologyVersion
from sqlalchemy import select

def check_ontologies():
    app = create_app('development')

    with app.app_context():
        # Get all ontologies
        stmt = select(Ontology).order_by(Ontology.id)
        ontologies = db.session.execute(stmt).scalars().all()

        print(f"\nFound {len(ontologies)} ontologies in database:\n")
        print(f"{'ID':<5} {'Name':<40} {'Base URI':<50} {'Has Content':<12} {'Type':<10}")
        print("=" * 120)

        for ont in ontologies:
            has_content = "Yes" if ont.current_content else "No"
            print(f"{ont.id:<5} {ont.name:<40} {ont.base_uri:<50} {has_content:<12} {ont.ontology_type:<10}")

        # Check for BFO entries
        print("\n" + "=" * 120)
        print("\nBFO-related entries:")
        bfo_stmt = select(Ontology).where(
            (Ontology.name.ilike('%bfo%')) |
            (Ontology.name.ilike('%basic formal%'))
        )
        bfo_entries = db.session.execute(bfo_stmt).scalars().all()

        for ont in bfo_entries:
            print(f"\nID: {ont.id}")
            print(f"  Name: {ont.name}")
            print(f"  Base URI: {ont.base_uri}")
            print(f"  Description: {ont.description}")
            print(f"  Has content: {'Yes' if ont.current_content else 'No'}")
            print(f"  Type: {ont.ontology_type}")
            print(f"  Is base: {ont.is_base}")

if __name__ == "__main__":
    check_ontologies()
