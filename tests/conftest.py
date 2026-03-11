"""
Pytest Configuration and Fixtures for OntServe Tests

This module provides shared fixtures and configuration for all tests.
"""

import os
import pytest
import pytest_asyncio
import asyncio
from pathlib import Path
from typing import Generator
from datetime import datetime

project_root = Path(__file__).parent.parent

# Set test environment before importing app
os.environ['ENVIRONMENT'] = 'test'
os.environ['FLASK_ENV'] = 'testing'
os.environ['TESTING'] = 'true'

# Import after environment is set
from config.config_loader import load_ontserve_config

# Load test configuration
load_ontserve_config('test')


# =============================================================================
# Session-scoped Fixtures
# =============================================================================

@pytest.fixture(scope='session')
def test_config():
    """Provide test configuration."""
    return {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': os.environ.get(
            'ONTSERVE_DB_URL',
            'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        ),
        'SECRET_KEY': 'test-secret-key',
        'WTF_CSRF_ENABLED': False,
    }


@pytest.fixture(scope='session')
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Shared Storage Fixtures (session-scoped for reuse across tests)
# =============================================================================

@pytest.fixture(scope='session')
def pg_storage():
    """Session-scoped PostgreSQLStorage connected to the test database."""
    from storage.postgresql_storage import PostgreSQLStorage

    config = {
        'db_url': os.environ.get(
            'ONTSERVE_DB_URL',
            'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        ),
    }
    storage = PostgreSQLStorage(config)
    yield storage


@pytest.fixture(scope='session')
def concept_manager(pg_storage):
    """Session-scoped ConceptManager backed by pg_storage."""
    from storage.concept_manager import ConceptManager
    return ConceptManager(pg_storage)


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture(scope='session')
def database_engine(test_config):
    """Create database engine for tests."""
    from sqlalchemy import create_engine

    engine = create_engine(
        test_config['SQLALCHEMY_DATABASE_URI'],
        echo=False,
        pool_pre_ping=True
    )

    yield engine

    engine.dispose()


@pytest.fixture(scope='session')
def _db_tables(app):
    """Create all tables once for the test session (DDL is expensive)."""
    from web.models import db

    with app.app_context():
        db.create_all()
        yield
        db.drop_all()


@pytest.fixture(scope='function')
def db_session(app, _db_tables):
    """Provide a clean Flask-SQLAlchemy session for each test.

    Uses DELETE (DML) instead of DROP/CREATE (DDL) for per-test isolation.
    This avoids the ~17s overhead of full schema recreation per test.
    """
    from web.models import db

    with app.app_context():
        # Clean data from previous test (respects FK ordering)
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()

        yield db.session

        db.session.remove()


@pytest.fixture(scope='function')
def clean_database(database_engine):
    """Provide a clean database for each test."""
    from web.models import Base

    # Drop all tables
    Base.metadata.drop_all(database_engine)

    # Create all tables
    Base.metadata.create_all(database_engine)

    yield database_engine

    # Clean up after test
    Base.metadata.drop_all(database_engine)


# =============================================================================
# Flask App Fixtures
# =============================================================================

@pytest.fixture(scope='session')
def app(test_config):
    """Create Flask app once for the test session."""
    from web.app import create_app

    app = create_app('testing')
    app.config.update(test_config)
    return app


@pytest.fixture(scope='function')
def client(app):
    """Create Flask test client."""
    return app.test_client()


@pytest.fixture(scope='function')
def runner(app):
    """Create Flask CLI test runner."""
    return app.test_cli_runner()


# =============================================================================
# MCP Server Fixtures (FastMCP in-process client)
# =============================================================================

@pytest.fixture(scope='session')
def mcp_server():
    """Import the FastMCP server instance (runs lifespan on first Client use)."""
    from servers.mcp_server import mcp
    return mcp


@pytest_asyncio.fixture(scope='function')
async def mcp_client(mcp_server):
    """In-process FastMCP Client -- no HTTP server needed."""
    from fastmcp import Client

    async with Client(mcp_server) as client:
        yield client


# =============================================================================
# SPARQL Service Fixtures
# =============================================================================

@pytest.fixture(scope='function')
def sparql_service():
    """Create SPARQL service instance for testing."""
    from services.sparql_service import SPARQLService

    # Create test ontology directory
    test_ontology_path = project_root / 'tests' / 'fixtures' / 'ontologies'
    test_ontology_path.mkdir(parents=True, exist_ok=True)

    service = SPARQLService(str(test_ontology_path))

    yield service


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def sample_ontology_ttl():
    """Provide sample ontology in Turtle format."""
    return """
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix test: <http://test.org/ontology#> .

test:Honesty a owl:Class ;
    rdfs:label "Honesty" ;
    rdfs:comment "The principle of honesty in engineering ethics" .

test:Engineer a owl:Class ;
    rdfs:label "Engineer" ;
    rdfs:comment "A professional engineer" .
"""


@pytest.fixture
def sample_candidate_concept():
    """Provide sample candidate concept data."""
    return {
        'label': 'Transparency',
        'category': 'Principle',
        'description': 'The principle of transparency in professional conduct',
        'uri': 'http://proethica.org/ontology/engineering-ethics#Transparency',
        'confidence_score': 0.92,
        'source_document': 'NSPE Code of Ethics',
        'extraction_method': 'llm-extraction',
        'llm_reasoning': 'Identified as a core ethical principle'
    }


@pytest.fixture
def sample_sparql_query():
    """Provide sample SPARQL query."""
    return """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>

SELECT ?class ?label
WHERE {
    ?class a owl:Class .
    ?class rdfs:label ?label .
}
"""


# =============================================================================
# Utility Fixtures
# =============================================================================

@pytest.fixture
def temp_directory(tmp_path):
    """Provide temporary directory for test files."""
    test_dir = tmp_path / "ontserve_test"
    test_dir.mkdir()
    return test_dir


@pytest.fixture
def mock_time(monkeypatch):
    """Provide consistent time for tests."""
    class MockDateTime:
        @staticmethod
        def now():
            return datetime(2025, 11, 16, 12, 0, 0)

    monkeypatch.setattr('datetime.datetime', MockDateTime)
    return MockDateTime


# =============================================================================
# Authentication Fixtures
# =============================================================================

@pytest.fixture
def authenticated_client(client, db_session):
    """Provide authenticated test client."""
    from web.models import User

    # Create test user
    user = User(
        username='testuser',
        email='test@example.com'
    )
    user.set_password('testpass123')

    db_session.add(user)
    db_session.commit()

    # Log in
    client.post('/login', data={
        'username': 'testuser',
        'password': 'testpass123'
    })

    yield client

    # Logout
    client.get('/logout')


# =============================================================================
# Markers for Test Organization
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "api: marks tests as API compatibility tests"
    )
    config.addinivalue_line(
        "markers", "mcp: marks tests as MCP server tests"
    )
    config.addinivalue_line(
        "markers", "database: marks tests that require database"
    )


# =============================================================================
# Test Helpers
# =============================================================================

class TestHelpers:
    """Helper methods for tests."""

    @staticmethod
    def create_test_ontology(db_session, name='test-ontology'):
        """Create a test ontology in database."""
        from web.models import Ontology

        ontology = Ontology(
            name=name,
            base_uri=f'http://test.org/{name}#',
            description=f'Test ontology: {name}'
        )

        db_session.add(ontology)
        db_session.commit()

        return ontology

    @staticmethod
    def create_test_entity(db_session, ontology, label='TestEntity', uri=None):
        """Create a test ontology entity."""
        from web.models import OntologyEntity

        entity = OntologyEntity(
            ontology_id=ontology.id,
            uri=uri or f'{ontology.base_uri}{label}',
            label=label,
            entity_type='class',
            comment=f'Test entity: {label}'
        )

        db_session.add(entity)
        db_session.commit()

        return entity


@pytest.fixture
def helpers():
    """Provide test helper methods."""
    return TestHelpers()
