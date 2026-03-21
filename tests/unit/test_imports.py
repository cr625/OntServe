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
        """Test MCP server import (FastMCP 3.x)."""
        from servers.mcp_server import mcp
        assert mcp is not None

    def test_import_mcp_tool_handlers(self):
        """Test MCP tool handlers import."""
        from servers.mcp_tool_handlers import MCPToolHandlers
        assert MCPToolHandlers is not None

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

    def test_no_dead_concept_managers(self):
        """Verify dead concept manager modules were removed."""
        import importlib
        for module_name in [
            'storage.concept_manager_database',
            'storage.concept_manager_enhanced',
        ]:
            try:
                importlib.import_module(module_name)
                assert False, f"{module_name} should have been removed"
            except ModuleNotFoundError:
                pass  # Expected


@pytest.mark.unit
class TestWebImports:
    """Test web application imports."""

    def test_import_web_config(self):
        """Test web config import."""
        from web.app_config import Config
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

    def test_fastmcp_installed(self):
        """Test FastMCP is installed."""
        import fastmcp
        assert fastmcp is not None

    def test_pytest_installed(self):
        """Test pytest is installed."""
        import pytest
        assert pytest is not None

    def test_dotenv_installed(self):
        """Test python-dotenv is installed."""
        import dotenv
        assert dotenv is not None
