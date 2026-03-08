"""
Abstract base class for ontology importers.

Defines the interface that all importer implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
import logging


class ImportError(Exception):
    """Base exception for import-related errors."""
    pass


class BaseImporter(ABC):
    """
    Abstract base class for ontology importers.
    
    All importer implementations must inherit from this class and
    implement the required methods.
    """
    
    def __init__(self, storage_backend=None, cache_dir: str = None):
        """
        Initialize the importer.
        
        Args:
            storage_backend: Optional storage backend to use
            cache_dir: Optional directory for caching imports
        """
        self.storage_backend = storage_backend
        self.cache_dir = cache_dir
        self.logger = logging.getLogger(self.__class__.__name__)
        self.imported_ontologies = {}
        self._initialize()
    
    @abstractmethod
    def _initialize(self):
        """
        Initialize the importer.
        
        This method should set up any necessary resources,
        namespaces, etc.
        """
        pass
    
    @abstractmethod
    def import_from_url(self, url: str, ontology_id: Optional[str] = None,
                       name: Optional[str] = None, description: Optional[str] = None,
                       format: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Import an ontology from a URL.
        
        Args:
            url: URL of the ontology to import
            ontology_id: Optional unique identifier for the ontology
            name: Optional human-readable name
            description: Optional description
            format: Optional RDF format (turtle, xml, n3, etc.)
            force_refresh: Force re-download even if cached
            
        Returns:
            Dictionary containing import results:
                - success: Whether import was successful
                - ontology_id: ID of imported ontology
                - metadata: Metadata about the ontology
                - graph: RDF graph object (optional)
                - message: Status message
                
        Raises:
            ImportError: If import fails
        """
        pass
    
    @abstractmethod
    def import_from_file(self, file_path: str, ontology_id: Optional[str] = None,
                        name: Optional[str] = None, description: Optional[str] = None,
                        format: str = 'turtle') -> Dict[str, Any]:
        """
        Import an ontology from a local file.
        
        Args:
            file_path: Path to the ontology file
            ontology_id: Optional unique identifier for the ontology
            name: Optional human-readable name
            description: Optional description
            format: RDF format (turtle, xml, n3, etc.)
            
        Returns:
            Dictionary containing import results
            
        Raises:
            ImportError: If import fails
        """
        pass
    
    @abstractmethod
    def extract_classes(self, ontology_id: str) -> List[Dict[str, Any]]:
        """
        Extract all classes from an imported ontology.
        
        Args:
            ontology_id: ID of the ontology
            
        Returns:
            List of class definitions with URIs, labels, and comments
        """
        pass
    
    @abstractmethod
    def extract_properties(self, ontology_id: str) -> List[Dict[str, Any]]:
        """
        Extract all properties from an imported ontology.
        
        Args:
            ontology_id: ID of the ontology
            
        Returns:
            List of property definitions with types, domains, and ranges
        """
        pass
    
    @abstractmethod
    def extract_individuals(self, ontology_id: str) -> List[Dict[str, Any]]:
        """
        Extract all individuals (instances) from an imported ontology.
        
        Args:
            ontology_id: ID of the ontology
            
        Returns:
            List of individual definitions with types and properties
        """
        pass
    
    def get_imported_ontology(self, ontology_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an imported ontology by ID.
        
        Args:
            ontology_id: ID of the ontology to retrieve
            
        Returns:
            Dictionary containing ontology data or None if not found
        """
        return self.imported_ontologies.get(ontology_id)
    
    def list_imported_ontologies(self) -> List[Dict[str, Any]]:
        """
        List all imported ontologies.
        
        Returns:
            List of ontology metadata dictionaries
        """
        return [ont['metadata'] for ont in self.imported_ontologies.values()]
    
    def clear_cache(self):
        """Clear the import cache."""
        self.imported_ontologies = {}
        self.logger.info("Import cache cleared")
    
    def validate_format(self, content: str, format: str) -> bool:
        """
        Validate that content matches the expected format.
        
        Args:
            content: Content to validate
            format: Expected format
            
        Returns:
            True if content is valid for the format
        """
        # Basic validation - can be overridden by subclasses
        if format == 'turtle':
            return '@prefix' in content or '@base' in content
        elif format == 'xml':
            return '<?xml' in content or '<rdf:RDF' in content
        elif format == 'n3':
            return '@prefix' in content
        elif format == 'json-ld':
            try:
                import json
                json.loads(content)
                return True
            except (json.JSONDecodeError, ValueError):
                return False
        return True
    
    def detect_format(self, content: str, url: str = None) -> str:
        """
        Detect the RDF format of content.
        
        Args:
            content: Content to analyze
            url: Optional URL for extension-based detection
            
        Returns:
            Detected format string
        """
        # Check URL extension if provided
        if url:
            if url.endswith('.ttl'):
                return 'turtle'
            elif url.endswith('.rdf') or url.endswith('.xml'):
                return 'xml'
            elif url.endswith('.n3'):
                return 'n3'
            elif url.endswith('.jsonld') or url.endswith('.json'):
                return 'json-ld'
        
        # Check content patterns
        if '@prefix' in content or '@base' in content:
            return 'turtle'
        elif '<?xml' in content or '<rdf:RDF' in content:
            return 'xml'
        elif content.strip().startswith('{'):
            return 'json-ld'
        
        # Default to turtle
        return 'turtle'
    
    def generate_ontology_id(self, source: str) -> str:
        """
        Generate a unique ID for an ontology based on its source.
        
        Args:
            source: Source URL or file path
            
        Returns:
            Generated ontology ID
        """
        import hashlib
        from urllib.parse import urlparse
        import os
        
        # Try to create meaningful ID from source
        if source.startswith('http'):
            parsed = urlparse(source)
            # Use domain and path
            id_parts = []
            if parsed.netloc:
                id_parts.append(parsed.netloc.replace('.', '-'))
            if parsed.path:
                path = parsed.path.strip('/').replace('/', '-').replace('.', '-')
                if path:
                    id_parts.append(path)
            
            if id_parts:
                return '-'.join(id_parts)
        else:
            # File path - use filename without extension
            return os.path.splitext(os.path.basename(source))[0]
        
        # Fallback to hash
        return hashlib.md5(source.encode()).hexdigest()[:8]
