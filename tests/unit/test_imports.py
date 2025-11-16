"""
Basic Import Tests

Verifies that all major modules can be imported without errors.
"""

import pytest


@pytest.mark.unit
class TestCoreImports:
    """Test core module imports."""

    def test_import_config_loader(self):
        """Test config loader import."""
        from config.config_loader import ConfigLoader
        assert ConfigLoader is not None

    def test_import_mcp_server(self):
        """Test MCP server import."""
        from servers.mcp_server import OntServeMCPServer
        assert OntServeMCPServer is not None

    def test_import_sparql_service(self):
        """Test SPARQL service import."""
        from services.sparql_service import SPARQLService
        assert SPARQLService is not None

    def test_import_postgresql_storage(self):
        """Test PostgreSQL storage import."""
        from storage.postgresql_storage import PostgreSQLStorage
        assert PostgreSQLStorage is not None

    def test_import_concept_manager(self):
        """Test concept manager import."""
        from storage.concept_manager import ConceptManager
        assert ConceptManager is not None


@pytest.mark.unit
class TestWebImports:
    """Test web application imports."""

    def test_import_web_config(self):
        """Test web config import."""
        from web.config import Config
        assert Config is not None

    @pytest.mark.skip(reason="Requires database connection")
    def test_import_web_models(self):
        """Test web models import."""
        # This might fail without database setup
        try:
            from web.models import Ontology, OntologyEntity
            assert Ontology is not None
            assert OntologyEntity is not None
        except Exception:
            pytest.skip("Database not available for model import")


@pytest.mark.unit
class TestDependencyVersions:
    """Test that required dependencies are installed."""

    def test_flask_installed(self):
        """Test Flask is installed."""
        import flask
        assert flask is not None

    def test_sqlalchemy_installed(self):
        """Test SQLAlchemy is installed."""
        import sqlalchemy
        assert sqlalchemy is not None

    def test_rdflib_installed(self):
        """Test rdflib is installed."""
        import rdflib
        assert rdflib is not None

    def test_aiohttp_installed(self):
        """Test aiohttp is installed."""
        import aiohttp
        assert aiohttp is not None

    def test_pytest_installed(self):
        """Test pytest is installed."""
        import pytest
        assert pytest is not None

    def test_dotenv_installed(self):
        """Test python-dotenv is installed."""
        import dotenv
        assert dotenv is not None
