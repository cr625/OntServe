#!/usr/bin/env python3
"""Check all registered Flask routes."""

import os
import sys
from pathlib import Path

os.environ['ENVIRONMENT'] = 'development'
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from web.app import create_app

def check_routes():
    app = create_app('development')

    print("\nRegistered Flask Routes:\n")
    print(f"{'Endpoint':<50} {'Methods':<20} {'URL Pattern':<60}")
    print("=" * 130)

    # Get all routes sorted by URL pattern
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append((str(rule), rule.endpoint, ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))))

    routes.sort()

    for url_pattern, endpoint, methods in routes:
        print(f"{endpoint:<50} {methods:<20} {url_pattern:<60}")

    # Check specifically for edit routes
    print("\n" + "=" * 130)
    print("\nEdit-related routes:")
    print("=" * 130)

    edit_routes = [r for r in routes if 'edit' in r[0].lower() or 'edit' in r[1].lower()]
    for url_pattern, endpoint, methods in edit_routes:
        print(f"{endpoint:<50} {methods:<20} {url_pattern:<60}")

    # Check for ontology routes
    print("\n" + "=" * 130)
    print("\nOntology-related routes:")
    print("=" * 130)

    ont_routes = [r for r in routes if 'ontology' in r[0].lower() or 'ontology' in r[1].lower()]
    for url_pattern, endpoint, methods in ont_routes:
        print(f"{endpoint:<50} {methods:<20} {url_pattern:<60}")

if __name__ == "__main__":
    check_routes()
