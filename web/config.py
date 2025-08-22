"""
Configuration for OntServe Web Application
"""

import os
from pathlib import Path

basedir = Path(__file__).parent.absolute()


class Config:
    """Base configuration"""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database settings - using OntServe's PostgreSQL on port 5435
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://ontserve_user:ontserve_development_password@localhost:5435/ontserve'
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
    ONTSERVE_STORAGE_DIR = str(basedir.parent / 'storage')
    ONTSERVE_CACHE_DIR = str(basedir.parent / 'storage' / 'cache' / 'downloads')


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


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
