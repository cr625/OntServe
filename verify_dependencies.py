#!/usr/bin/env python3
"""
Dependency Verification Script

Tests that all updated dependencies are installed and working correctly.
Run this after installing requirements.txt to verify the upgrade.
"""

import sys
import importlib.metadata
from typing import Dict, List, Tuple

# Expected minimum versions
EXPECTED_VERSIONS = {
    'Flask': '3.1.0',
    'SQLAlchemy': '2.0.44',
    'rdflib': '7.4.0',
    'aiohttp': '3.13.0',
    'sentence-transformers': '3.3.0',
    'pytest': '8.3.0',
    'psycopg2-binary': '2.9.11',
    'numpy': '1.26.0',
    'python-dotenv': '1.0.0',
}

def parse_version(version_str: str) -> Tuple[int, ...]:
    """Parse version string into tuple of integers."""
    return tuple(int(x) for x in version_str.split('.')[:3])

def check_package_version(package: str, min_version: str) -> Tuple[bool, str, str]:
    """
    Check if package is installed and meets minimum version.

    Returns:
        (success, installed_version, message)
    """
    try:
        installed = importlib.metadata.version(package)
        installed_tuple = parse_version(installed)
        required_tuple = parse_version(min_version)

        if installed_tuple >= required_tuple:
            return True, installed, f"✅ {package}: {installed} (required >= {min_version})"
        else:
            return False, installed, f"❌ {package}: {installed} < {min_version} (UPGRADE NEEDED)"
    except importlib.metadata.PackageNotFoundError:
        return False, "NOT INSTALLED", f"❌ {package}: NOT INSTALLED"

def test_imports() -> List[Tuple[bool, str]]:
    """Test that critical modules can be imported."""
    tests = []

    # Flask
    try:
        import flask
        from flask_sqlalchemy import SQLAlchemy
        from flask_migrate import Migrate
        tests.append((True, "✅ Flask and extensions import successfully"))
    except Exception as e:
        tests.append((False, f"❌ Flask import failed: {e}"))

    # SQLAlchemy 2.0
    try:
        from sqlalchemy import select, func, or_
        from sqlalchemy.orm import Session
        tests.append((True, "✅ SQLAlchemy 2.0 imports successfully"))
    except Exception as e:
        tests.append((False, f"❌ SQLAlchemy import failed: {e}"))

    # rdflib
    try:
        import rdflib
        from rdflib import Graph, Namespace, RDF, RDFS, OWL
        tests.append((True, "✅ rdflib imports successfully"))
    except Exception as e:
        tests.append((False, f"❌ rdflib import failed: {e}"))

    # aiohttp
    try:
        import aiohttp
        from aiohttp import web
        tests.append((True, "✅ aiohttp imports successfully"))
    except Exception as e:
        tests.append((False, f"❌ aiohttp import failed: {e}"))

    # sentence-transformers
    try:
        from sentence_transformers import SentenceTransformer
        tests.append((True, "✅ sentence-transformers imports successfully"))
    except Exception as e:
        tests.append((False, f"❌ sentence-transformers import failed: {e}"))

    # pytest
    try:
        import pytest
        tests.append((True, "✅ pytest imports successfully"))
    except Exception as e:
        tests.append((False, f"❌ pytest import failed: {e}"))

    return tests

def test_sqlalchemy_2_features():
    """Test SQLAlchemy 2.0 specific features."""
    tests = []

    try:
        from sqlalchemy import create_engine, select, MetaData, Table, Column, Integer, String
        from sqlalchemy.orm import Session

        # Test in-memory database with SQLAlchemy 2.0 API
        engine = create_engine("sqlite:///:memory:")
        metadata = MetaData()

        # Create test table
        test_table = Table(
            'test',
            metadata,
            Column('id', Integer, primary_key=True),
            Column('name', String(50))
        )
        metadata.create_all(engine)

        # Test select() syntax
        with Session(engine) as session:
            # Insert test data
            session.execute(test_table.insert().values(id=1, name='test'))
            session.commit()

            # Query with 2.0 syntax
            stmt = select(test_table)
            result = session.execute(stmt)
            rows = result.all()

            if len(rows) == 1:
                tests.append((True, "✅ SQLAlchemy 2.0 select() API works correctly"))
            else:
                tests.append((False, f"❌ SQLAlchemy 2.0 query returned unexpected results"))
    except Exception as e:
        tests.append((False, f"❌ SQLAlchemy 2.0 feature test failed: {e}"))

    return tests

def test_rdflib_features():
    """Test rdflib 7.4 features."""
    tests = []

    try:
        from rdflib import Graph, Namespace, Literal, URIRef
        from rdflib.namespace import RDF, RDFS

        # Create a simple graph
        g = Graph()
        ex = Namespace("http://example.org/")

        # Add triples
        g.add((ex.subject, RDF.type, ex.Class))
        g.add((ex.subject, RDFS.label, Literal("Test Subject")))

        # Query the graph
        results = list(g.triples((None, RDF.type, None)))

        if len(results) == 1:
            tests.append((True, "✅ rdflib 7.4 graph operations work correctly"))
        else:
            tests.append((False, f"❌ rdflib graph query returned unexpected results"))
    except Exception as e:
        tests.append((False, f"❌ rdflib feature test failed: {e}"))

    return tests

def main():
    """Run all verification tests."""
    print("=" * 70)
    print("OntServe Dependency Verification")
    print("=" * 70)
    print()

    # Check Python version
    python_version = sys.version_info
    print(f"Python Version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    if python_version >= (3, 11):
        print("✅ Python version is 3.11+")
    else:
        print("⚠️  Python 3.11+ recommended (you have {}.{})".format(
            python_version.major, python_version.minor))
    print()

    # Check package versions
    print("-" * 70)
    print("Package Version Check")
    print("-" * 70)

    all_ok = True
    for package, min_version in EXPECTED_VERSIONS.items():
        success, installed, message = check_package_version(package, min_version)
        print(message)
        if not success:
            all_ok = False
    print()

    # Test imports
    print("-" * 70)
    print("Import Tests")
    print("-" * 70)

    import_tests = test_imports()
    for success, message in import_tests:
        print(message)
        if not success:
            all_ok = False
    print()

    # Test SQLAlchemy 2.0 features
    print("-" * 70)
    print("SQLAlchemy 2.0 Feature Tests")
    print("-" * 70)

    sqlalchemy_tests = test_sqlalchemy_2_features()
    for success, message in sqlalchemy_tests:
        print(message)
        if not success:
            all_ok = False
    print()

    # Test rdflib features
    print("-" * 70)
    print("rdflib 7.4 Feature Tests")
    print("-" * 70)

    rdflib_tests = test_rdflib_features()
    for success, message in rdflib_tests:
        print(message)
        if not success:
            all_ok = False
    print()

    # Final verdict
    print("=" * 70)
    if all_ok:
        print("✅ ALL TESTS PASSED - Dependencies are correctly installed!")
        print()
        print("Next steps:")
        print("1. Run the test suite: pytest")
        print("2. Start the web app: cd web && python app.py")
        print("3. Start the MCP server: cd servers && python mcp_server.py")
        return 0
    else:
        print("❌ SOME TESTS FAILED - Please review errors above")
        print()
        print("To fix:")
        print("1. pip install --upgrade -r requirements.txt")
        print("2. Run this script again to verify")
        return 1

if __name__ == '__main__':
    sys.exit(main())
