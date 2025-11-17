#!/usr/bin/env python3
"""Test the edit route directly."""

import os
import sys
from pathlib import Path

os.environ['ENVIRONMENT'] = 'development'
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from web.app import create_app
from web.models import db, User
from sqlalchemy import select

def test_edit_route():
    app = create_app('development')

    with app.app_context():
        # Test with the test client
        client = app.test_client()

        # Get the user
        stmt = select(User).where(User.username == 'chris')
        user = db.session.execute(stmt).scalar_one_or_none()

        if not user:
            print("User 'chris' not found!")
            return

        # Log in
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        # Test the edit route
        ontology_name = "IFC Integration for Engineering Ethics"
        print(f"\nTesting GET /ontology/{ontology_name}/edit")
        print("=" * 80)

        response = client.get(f'/ontology/{ontology_name}/edit')

        print(f"\nResponse status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")

        if response.status_code == 200:
            print("\n✓ SUCCESS! Edit route works correctly.")
            print(f"Response length: {len(response.data)} bytes")
        elif response.status_code == 404:
            print("\n✗ 404 NOT FOUND")
            print(f"\nResponse body:\n{response.data.decode('utf-8')[:500]}")
        elif response.status_code == 302:
            print(f"\n→ REDIRECT to: {response.headers.get('Location')}")
        else:
            print(f"\n? Unexpected status code: {response.status_code}")
            print(f"\nResponse body:\n{response.data.decode('utf-8')[:500]}")

if __name__ == "__main__":
    try:
        test_edit_route()
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
