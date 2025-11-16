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
        print(f"{'ID':<5} {'Username':<20} {'Email':<30} {'Role':<10} {'Active':<10}")
        print("=" * 80)

        for user in users:
            print(f"{user.id:<5} {user.username:<20} {user.email:<30} {user.role:<10} {'Yes' if user.is_active else 'No':<10}")

if __name__ == "__main__":
    check_users()
