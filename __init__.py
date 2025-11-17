"""
OntServe - Unified Ontology Server

A modular, extensible ontology management system that provides:
- Multiple ontology format support (PROV-O, BFO, custom)
- Unified API access (REST, MCP, library)
- Hybrid storage (file and database)
- Version control and history
- Intelligent caching

Version: 0.1.0
"""

__version__ = "0.1.0"
__author__ = "OntServe Team"

# Public API exports
# Note: These imports are commented out to avoid conflicts when running locally.
# Uncomment when installing OntServe as a package (pip install -e .)
# from .core.ontology_manager import OntologyManager
# from .storage.base import StorageBackend
# from .importers.base import BaseImporter

__all__ = [
    # 'OntologyManager',
    # 'StorageBackend',
    # 'BaseImporter',
    '__version__'
]
