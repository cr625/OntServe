#!/usr/bin/env python3
"""Test looking up a specific ontology by name."""

import os
import sys
from pathlib import Path

os.environ['ENVIRONMENT'] = 'development'
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from web.app import create_app
from web.models import db, Ontology
from sqlalchemy import select

def test_lookup():
    app = create_app('development')

    test_name = "IFC Integration for Engineering Ethics"

    with app.app_context():
        print(f"\nTesting lookup for ontology: '{test_name}'")
        print(f"Name length: {len(test_name)} characters")
        print(f"Name repr: {repr(test_name)}")
        print("\n" + "=" * 80)

        # Try exact match
        stmt = select(Ontology).where(Ontology.name == test_name)
        result = db.session.execute(stmt).scalar_one_or_none()

        if result:
            print(f"✓ FOUND exact match!")
            print(f"  ID: {result.id}")
            print(f"  Name: '{result.name}'")
            print(f"  Name length: {len(result.name)}")
            print(f"  Name repr: {repr(result.name)}")
            print(f"  Base URI: {result.base_uri}")
            print(f"  Has content: {'Yes' if result.current_content else 'No'}")
        else:
            print(f"✗ NOT FOUND with exact match")

            # Try partial match
            print("\nSearching for similar names...")
            stmt = select(Ontology).where(Ontology.name.ilike(f'%IFC%Integration%'))
            similar = db.session.execute(stmt).scalars().all()

            if similar:
                print(f"\nFound {len(similar)} similar ontolog(ies):")
                for ont in similar:
                    print(f"\n  ID: {ont.id}")
                    print(f"  Name: '{ont.name}'")
                    print(f"  Name length: {len(ont.name)}")
                    print(f"  Name repr: {repr(ont.name)}")
                    print(f"  Match: {ont.name == test_name}")
            else:
                print("No similar names found")

if __name__ == "__main__":
    test_lookup()
