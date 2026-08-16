"""
Configuration for OntServe Web Application
"""

import os
from pathlib import Path

from config.config_loader import get_database_url

basedir = Path(__file__).parent.absolute()
project_root = basedir.parent

# Config loading deferred to create_app() — see web/app.py


class Config:
    """Base configuration"""

    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Database settings
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Application settings
    PORT = 5003
    HOST = '0.0.0.0'
    DEBUG = False
    
    # Pagination
    ONTOLOGIES_PER_PAGE = 20
    # Index page: a category with more ontologies than this collapses to one summary row
    INDEX_COLLAPSE_THRESHOLD = 12
    ENTITIES_PER_PAGE = 50
    
    # File upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'ttl', 'rdf', 'owl', 'n3', 'nt', 'json'}
    
    # Cache settings
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300
    
    # pgvector settings
    EMBEDDING_DIMENSION = 384  # Using sentence-transformers/all-MiniLM-L6-v2
    
    # OntServe integration
    ONTSERVE_STORAGE_DIR = os.environ.get('ONTSERVE_STORAGE_DIR') or str(basedir.parent / 'storage')
    ONTSERVE_CACHE_DIR = os.environ.get('ONTSERVE_CACHE_DIR') or str(basedir.parent / 'storage' / 'cache' / 'downloads')
    
    # Ontology URI settings
    ONTOLOGY_BASE_URI = os.environ.get('ONTOLOGY_BASE_URI') or 'https://ontserve.ontorealm.net/'
    ONTOLOGY_NAMESPACE_TEMPLATE = os.environ.get('ONTOLOGY_NAMESPACE_TEMPLATE') or '{base_uri}ontology/{name}#'


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    # Set to True to see all SQL queries (very verbose)
    # Set to 'debug' for just query strings
    SQLALCHEMY_ECHO = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

    @classmethod
    def init_app(cls, app):
        """Validate production-required settings after app creation."""
        if not app.config.get('SECRET_KEY') or \
                app.config['SECRET_KEY'] == 'dev-secret-key-change-in-production':
            raise ValueError("SECRET_KEY environment variable must be set in production")


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    
    # Storage directories for testing
    ONTSERVE_STORAGE_DIR = '/tmp/ontserve_test_storage'
    ONTSERVE_CACHE_DIR = '/tmp/ontserve_test_cache'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
