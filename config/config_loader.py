"""
OntServe Configuration Loader

Centralized configuration loading for OntServe applications.
Replaces the old shared/.env dependency with standalone configuration.
"""

import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Configuration loader for OntServe.

    Priority order (highest to lowest):
    1. Environment variables (already set)
    2. .env file in project root
    3. config/{environment}.env file
    4. Default values
    """

    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize configuration loader.

        Args:
            project_root: Project root directory (auto-detected if not provided)
        """
        self.project_root = project_root or self._detect_project_root()
        self.config_dir = self.project_root / "config"
        self.loaded_files = []

    def _detect_project_root(self) -> Path:
        """
        Detect project root directory.

        Looks for directory containing 'config' folder or DEPLOYMENT.md.
        """
        # Start from current file's parent
        current = Path(__file__).parent.parent

        # Check if we're already in the project root
        if (current / "config").exists() or (current / "DEPLOYMENT.md").exists():
            return current

        # Otherwise, assume we're in a subdirectory
        # Try going up one more level
        parent = current.parent
        if (parent / "config").exists() or (parent / "DEPLOYMENT.md").exists():
            return parent

        # Default to current directory's parent
        logger.warning(f"Could not definitively detect project root, using: {current}")
        return current

    def load_config(self, environment: Optional[str] = None) -> dict:
        """
        Load configuration from appropriate sources.

        Args:
            environment: Environment name (development/production/test)
                        Auto-detected from ENVIRONMENT or FLASK_ENV if not provided

        Returns:
            Dictionary of loaded configuration (for verification purposes)
        """
        # Detect environment if not provided
        if environment is None:
            environment = os.environ.get(
                'ENVIRONMENT',
                os.environ.get('FLASK_ENV', 'development')
            )

        logger.info(f"Loading configuration for environment: {environment}")
        logger.info(f"Project root: {self.project_root}")

        # Load in priority order (lowest to highest priority)

        # 1. Load environment-specific config file
        env_file = self.config_dir / f"{environment}.env"
        if env_file.exists():
            load_dotenv(env_file, override=False)
            self.loaded_files.append(str(env_file))
            logger.info(f"✅ Loaded config file: {env_file}")
        else:
            logger.warning(f"⚠️  Config file not found: {env_file}")

        # 2. Load .env from project root (if exists)
        root_env = self.project_root / ".env"
        if root_env.exists():
            load_dotenv(root_env, override=True)  # Override with project-specific settings
            self.loaded_files.append(str(root_env))
            logger.info(f"✅ Loaded root .env file: {root_env}")

        # 3. Environment variables are already loaded (highest priority)

        # Build config summary
        config_summary = {
            'project_root': str(self.project_root),
            'config_dir': str(self.config_dir),
            'environment': environment,
            'loaded_files': self.loaded_files,
            'key_settings': {
                'FLASK_ENV': os.environ.get('FLASK_ENV'),
                'ENVIRONMENT': os.environ.get('ENVIRONMENT'),
                'ONTSERVE_DB_URL': self._mask_password(os.environ.get('ONTSERVE_DB_URL', '')),
                'ONTSERVE_MCP_PORT': os.environ.get('ONTSERVE_MCP_PORT'),
                'ONTSERVE_WEB_PORT': os.environ.get('ONTSERVE_WEB_PORT'),
            }
        }

        logger.info("Configuration loaded successfully")
        return config_summary

    def _mask_password(self, db_url: str) -> str:
        """Mask password in database URL for logging."""
        if not db_url or ':' not in db_url:
            return db_url

        try:
            # Format: postgresql://user:password@host:port/database
            if '@' in db_url:
                before_at, after_at = db_url.rsplit('@', 1)
                if ':' in before_at:
                    protocol_user, _ = before_at.rsplit(':', 1)
                    return f"{protocol_user}:****@{after_at}"
        except Exception:
            pass

        return db_url

    def verify_required_settings(self, required: list = None) -> bool:
        """
        Verify that required settings are present.

        Args:
            required: List of required environment variable names

        Returns:
            True if all required settings are present

        Raises:
            ValueError: If required settings are missing
        """
        if required is None:
            required = ['ONTSERVE_DB_URL']

        missing = [key for key in required if not os.environ.get(key)]

        if missing:
            error_msg = f"Missing required configuration: {', '.join(missing)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info("✅ All required settings verified")
        return True

    def get_database_url(self) -> str:
        """Get database URL with fallback to default."""
        return os.environ.get(
            'ONTSERVE_DB_URL',
            'postgresql://postgres:PASS@localhost:5432/ontserve'
        )

    def get_mcp_port(self) -> int:
        """Get MCP server port."""
        return int(os.environ.get('ONTSERVE_MCP_PORT', 8082))

    def get_web_port(self) -> int:
        """Get web server port."""
        return int(os.environ.get('ONTSERVE_WEB_PORT', 5003))

    def is_debug_mode(self) -> bool:
        """Check if debug mode is enabled."""
        flask_debug = os.environ.get('FLASK_DEBUG', '0')
        ontserve_debug = os.environ.get('ONTSERVE_DEBUG', 'false').lower()

        return flask_debug in ('1', 'true', 'True') or ontserve_debug == 'true'

    def is_production(self) -> bool:
        """Check if running in production environment."""
        env = os.environ.get('ENVIRONMENT', os.environ.get('FLASK_ENV', 'development'))
        return env == 'production'


# Global configuration loader instance
_config_loader = None


def get_config_loader(project_root: Optional[Path] = None) -> ConfigLoader:
    """
    Get or create global configuration loader instance.

    Args:
        project_root: Project root directory (only used on first call)

    Returns:
        ConfigLoader instance
    """
    global _config_loader

    if _config_loader is None:
        _config_loader = ConfigLoader(project_root)

    return _config_loader


def load_ontserve_config(environment: Optional[str] = None) -> dict:
    """
    Convenience function to load OntServe configuration.

    Args:
        environment: Environment name (auto-detected if not provided)

    Returns:
        Configuration summary dictionary
    """
    loader = get_config_loader()
    return loader.load_config(environment)


# Example usage
if __name__ == "__main__":
    # Configure logging for testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load configuration
    config = load_ontserve_config()

    # Print summary
    print("\n" + "="*60)
    print("OntServe Configuration Summary")
    print("="*60)
    print(f"Environment: {config['environment']}")
    print(f"Project Root: {config['project_root']}")
    print(f"\nLoaded Files:")
    for file in config['loaded_files']:
        print(f"  - {file}")
    print(f"\nKey Settings:")
    for key, value in config['key_settings'].items():
        print(f"  {key}: {value}")
    print("="*60)
