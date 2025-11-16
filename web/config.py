"""
Configuration for OntServe Web Application
"""

import os
import sys
from pathlib import Path

basedir = Path(__file__).parent.absolute()
project_root = basedir.parent

# Add project root to path for config imports
sys.path.insert(0, str(project_root))

# Load environment configuration using new standalone config system
from config.config_loader import load_ontserve_config
config_summary = load_ontserve_config()
print(f"✅ Loaded configuration from: {', '.join(config_summary['loaded_files'])}")


class Config:
    """Base configuration"""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database settings - using local PostgreSQL on port 5432
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://postgres:PASS@localhost:5432/ontserve'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
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
    
    # Ontology URI settings
    ONTOLOGY_BASE_URI = os.environ.get('ONTOLOGY_BASE_URI') or 'https://ontserve.ontorealm.net/'
    ONTOLOGY_NAMESPACE_TEMPLATE = os.environ.get('ONTOLOGY_NAMESPACE_TEMPLATE') or '{base_uri}ontology/{name}#'


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    
    # Use environment variables in production
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'prod-secret-key-must-be-set'


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
