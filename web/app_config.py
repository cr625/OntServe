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
    # Pool resilience against server-side connection loss: pre_ping discards
    # a pooled connection the server has already closed instead of handing it
    # to the next request as a 500. Under gunicorn --preload --max-requests,
    # every replacement worker inherits the pooled connection the master
    # opened at startup, which the previous worker closed on exit. recycle
    # retires connections before typical server and network idle limits.
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # Application settings
    PORT = 5003
    HOST = '0.0.0.0'
    DEBUG = False
    
    # Pagination
    ONTOLOGIES_PER_PAGE = 20
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
    
    # ProEthica web app (case pages link back to it: {PROETHICA_BASE_URL}/cases/<id>)
    PROETHICA_BASE_URL = os.environ.get('PROETHICA_BASE_URL') or 'http://localhost:5000'

    # Double-blind anonymization, the counterpart of ANONYMOUS_MODE in ProEthica.
    # When true, the surfaces that name authors are withheld: the publications
    # list of the home page (config/publications.yaml). The default is true so
    # that a deploy without the setting stays anonymous; set ANONYMOUS_MODE=false
    # in the environment to show them.
    ANONYMOUS_MODE = os.environ.get('ANONYMOUS_MODE', 'true').lower() == 'true'

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
    PROETHICA_BASE_URL = os.environ.get('PROETHICA_BASE_URL') or 'https://proethica.org'

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
    # The in-memory database exists only inside its one pooled connection, so
    # a recycled connection would be an empty database.
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    WTF_CSRF_ENABLED = False
    # The suite exercises the full pages; tests of the withheld state set it.
    ANONYMOUS_MODE = False

    # Storage directories for testing
    ONTSERVE_STORAGE_DIR = '/tmp/ontserve_test_storage'
    ONTSERVE_CACHE_DIR = '/tmp/ontserve_test_cache'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
