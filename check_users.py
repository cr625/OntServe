#!/usr/bin/env python3
"""Check users in the database."""

import os
import sys
from pathlib import Path

os.environ['ENVIRONMENT'] = 'development'
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from web.app import create_app
from web.models import db, User
from sqlalchemy import select

def check_users():
    app = create_app('development')

    with app.app_context():
        stmt = select(User).order_by(User.id)
        users = db.session.execute(stmt).scalars().all()

        if not users:
            print("No users found in the database!")
            print("\nYou need to create a user account to access login-protected features.")
            print("Would you like to create an admin user? (This needs to be done separately)")
            return

        print(f"\nFound {len(users)} user(s):\n")

        for user in users:
            print(f"\n{'='*80}")
            print(f"User ID: {user.id}")
            print(f"Username: {user.username}")
            print(f"Email: {user.email}")
            print(f"Admin: {'Yes' if user.is_admin else 'No'}")
            print(f"Active: {'Yes' if user.is_active else 'No'}")
            print(f"\nPermissions:")
            print(f"  Can import ontologies: {'Yes' if user.can_import_ontologies else 'No'}")
            print(f"  Can edit ontologies: {'Yes' if user.can_edit_ontologies else 'No'}")
            print(f"  Can delete ontologies: {'Yes' if user.can_delete_ontologies else 'No'}")
            print(f"  Can publish versions: {'Yes' if user.can_publish_versions else 'No'}")
            print(f"  Can access API: {'Yes' if user.can_access_api else 'No'}")
            print(f"\ncan_perform_action('edit'): {user.can_perform_action('edit')}")

        print(f"\n{'='*80}")

if __name__ == "__main__":
    check_users()
