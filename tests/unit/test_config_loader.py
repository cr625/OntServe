"""
Unit Tests for Configuration Loader

Tests the new standalone configuration system.
"""

import pytest
import os
from pathlib import Path


@pytest.mark.unit
class TestConfigLoader:
    """Test configuration loading functionality."""

    def test_config_loader_import(self):
        """Test that config loader can be imported."""
        from config.config_loader import ConfigLoader

        assert ConfigLoader is not None

    def test_config_loader_initialization(self):
        """Test ConfigLoader initialization."""
        from config.config_loader import ConfigLoader

        loader = ConfigLoader()

        assert loader.project_root is not None
        assert loader.config_dir.exists()

    def test_load_config_returns_summary(self):
        """Test that load_config returns a summary dictionary."""
        from config.config_loader import ConfigLoader

        loader = ConfigLoader()
        summary = loader.load_config('test')

        assert isinstance(summary, dict)
        assert 'project_root' in summary
        assert 'environment' in summary
        assert 'loaded_files' in summary

    def test_get_database_url(self):
        """Test database URL retrieval."""
        from config.config_loader import ConfigLoader

        loader = ConfigLoader()
        db_url = loader.get_database_url()

        assert db_url is not None
        assert 'postgresql' in db_url

    def test_get_mcp_port(self):
        """Test MCP port retrieval."""
        from config.config_loader import ConfigLoader

        loader = ConfigLoader()
        port = loader.get_mcp_port()

        assert isinstance(port, int)
        assert 1024 <= port <= 65535

    def test_get_web_port(self):
        """Test web port retrieval."""
        from config.config_loader import ConfigLoader

        loader = ConfigLoader()
        port = loader.get_web_port()

        assert isinstance(port, int)
        assert 1024 <= port <= 65535

    def test_is_debug_mode(self):
        """Test debug mode detection."""
        from config.config_loader import ConfigLoader

        loader = ConfigLoader()
        is_debug = loader.is_debug_mode()

        assert isinstance(is_debug, bool)

    def test_is_production(self):
        """Test production environment detection."""
        from config.config_loader import ConfigLoader

        # Set test environment
        os.environ['ENVIRONMENT'] = 'test'

        loader = ConfigLoader()
        is_prod = loader.is_production()

        assert is_prod is False

    def test_password_masking(self):
        """Test that passwords are masked in logs."""
        from config.config_loader import ConfigLoader

        loader = ConfigLoader()
        db_url = 'postgresql://user:secretpassword@localhost/db'
        masked = loader._mask_password(db_url)

        assert 'secretpassword' not in masked
        assert '****' in masked


@pytest.mark.unit
class TestConfigEnvironments:
    """Test environment-specific configuration."""

    def test_test_environment_config_exists(self):
        """Test that test environment config file exists."""
        from pathlib import Path

        config_file = Path(__file__).parent.parent.parent / 'config' / 'test.env'
        assert config_file.exists()

    def test_development_environment_config_exists(self):
        """Test that development environment config file exists."""
        from pathlib import Path

        config_file = Path(__file__).parent.parent.parent / 'config' / 'development.env'
        assert config_file.exists()

    def test_production_template_exists(self):
        """Test that production template exists."""
        from pathlib import Path

        config_file = Path(__file__).parent.parent.parent / 'config' / 'production.env.template'
        assert config_file.exists()


@pytest.mark.unit
class TestConfigPriority:
    """Test configuration priority order."""

    def test_environment_variables_take_precedence(self, monkeypatch):
        """Test that environment variables override config files."""
        from config.config_loader import ConfigLoader

        # Set environment variable
        monkeypatch.setenv('ONTSERVE_MCP_PORT', '9999')

        loader = ConfigLoader()
        port = loader.get_mcp_port()

        assert port == 9999
