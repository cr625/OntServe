"""
Central ontology management system.

Coordinates between storage backends, importers, and modules to provide
a unified interface for ontology management.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from storage.base import StorageBackend, StorageError
from storage.file_storage import FileStorage
from importers.base import BaseImporter, ImportError
from importers.prov_importer import PROVImporter
from importers.bfo_importer import BFOImporter


class OntologyManager:
    """
    Central manager for all ontology operations.
    
    This class coordinates between:
    - Storage backends (file, database, hybrid)
    - Importers (PROV-O, BFO, custom)
    - Modules (query, validation, etc.)
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the ontology manager.
        
        Args:
            config: Configuration dictionary with settings for:
                - storage_type: 'file', 'database', or 'hybrid'
                - storage_config: Configuration for storage backend
                - cache_dir: Directory for caching imports
                - log_level: Logging level
        """
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # Set up logging
        log_level = self.config.get('log_level', 'INFO')
        logging.basicConfig(level=getattr(logging, log_level))
        
        # Initialize storage backend
        self._initialize_storage()
        
        # Initialize importers
        self._initialize_importers()
        
        # Cache for loaded ontologies
        self.loaded_ontologies = {}
        
        self.logger.info("OntologyManager initialized")
    
    def _initialize_storage(self):
        """Initialize the storage backend based on configuration.

        OntologyManager uses file storage for the basic import/cache path.
        The database-backed ontology storage lives in ``storage.postgresql_storage``
        and is managed directly by the web app and MCP server.
        """
        storage_config = self.config.get('storage_config', {})
        self.storage = FileStorage(storage_config)
        self.logger.info("Using file storage backend")
    
    def _initialize_importers(self):
        """Initialize available importers."""
        cache_dir = self.config.get('cache_dir')
        
        self.importers = {
            'prov': PROVImporter(
                storage_backend=self.storage,
                cache_dir=cache_dir
            ),
            'bfo': BFOImporter(
                storage_backend=self.storage,
                cache_dir=cache_dir
            )
        }

        self.logger.info(f"Initialized {len(self.importers)} importers")
    
    def import_ontology(self, source: str, importer_type: str = 'prov',
                       ontology_id: Optional[str] = None,
                       name: Optional[str] = None,
                       description: Optional[str] = None,
                       format: Optional[str] = None,
                       source_type: Optional[str] = None,
                       force_refresh: bool = False) -> Dict[str, Any]:
        """
        Import an ontology from a URL or file.
        
        Args:
            source: URL or file path of the ontology
            importer_type: Type of importer to use ('prov', 'bfo', etc.)
            ontology_id: Optional unique identifier
            name: Optional human-readable name
            description: Optional description
            format: Optional RDF format
            source_type: Optional explicit source type ('url' or 'file')
            force_refresh: Force re-import even if cached
            
        Returns:
            Dictionary containing import results
        """
        # Get the appropriate importer
        importer = self.importers.get(importer_type)
        if not importer:
            raise ImportError(f"Unknown importer type: {importer_type}")
        
        # Determine if source is URL or file
        # Use explicit source_type if provided, otherwise auto-detect
        if source_type == 'url' or (source_type is None and (source.startswith('http://') or source.startswith('https://'))):
            result = importer.import_from_url(
                source, ontology_id, name, description, format, force_refresh
            )
        else:
            result = importer.import_from_file(
                source, ontology_id, name, description, format or 'turtle'
            )
        
        # Cache the loaded ontology
        if result.get('success'):
            ont_id = result['ontology_id']
            self.loaded_ontologies[ont_id] = {
                'importer': importer,
                'metadata': result.get('metadata', {}),
                'loaded_at': datetime.now().isoformat()
            }
        
        return result
    
    def import_prov_o(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Convenience method to import the standard PROV-O ontology.
        
        Args:
            force_refresh: Force re-download even if cached
            
        Returns:
            Dictionary containing import results
        """
        prov_importer = self.importers['prov']
        return prov_importer.import_prov_o(force_refresh)
    
    def import_bfo(self, version: str = "latest", force_refresh: bool = False) -> Dict[str, Any]:
        """
        Convenience method to import the BFO (Basic Formal Ontology).
        
        Args:
            version: BFO version to import ("latest", "2.0", "2020", etc.)
            force_refresh: Force re-download even if cached
            
        Returns:
            Dictionary containing import results
        """
        bfo_importer = self.importers['bfo']
        return bfo_importer.import_bfo(version, force_refresh)
    
    def get_ontology(self, ontology_id: str, version: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve an ontology from storage.
        
        Args:
            ontology_id: Unique identifier for the ontology
            version: Optional version to retrieve
            
        Returns:
            Dictionary containing ontology content and metadata
        """
        try:
            return self.storage.retrieve(ontology_id, version)
        except StorageError as e:
            self.logger.error(f"Error retrieving ontology {ontology_id}: {e}")
            raise
    
    def store_ontology(self, ontology_id: str, content: str,
                      metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Store an ontology in the configured storage backend.
        
        Args:
            ontology_id: Unique identifier for the ontology
            content: The ontology content (TTL format)
            metadata: Optional metadata about the ontology
            
        Returns:
            Dictionary containing storage result
        """
        try:
            return self.storage.store(ontology_id, content, metadata)
        except StorageError as e:
            self.logger.error(f"Error storing ontology {ontology_id}: {e}")
            raise
    
    def list_ontologies(self, filter_criteria: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        List available ontologies.
        
        Args:
            filter_criteria: Optional filtering criteria
            
        Returns:
            List of ontology metadata dictionaries
        """
        return self.storage.list_ontologies(filter_criteria)
    
    def delete_ontology(self, ontology_id: str, version: Optional[str] = None) -> bool:
        """
        Delete an ontology or specific version.
        
        Args:
            ontology_id: Unique identifier for the ontology
            version: Optional version to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            result = self.storage.delete(ontology_id, version)
            
            # Remove from cache if present
            if ontology_id in self.loaded_ontologies:
                del self.loaded_ontologies[ontology_id]
            
            return result
        except StorageError as e:
            self.logger.error(f"Error deleting ontology {ontology_id}: {e}")
            raise
    
    def extract_classes(self, ontology_id: str, importer_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extract all classes from an ontology.
        
        Args:
            ontology_id: Unique identifier for the ontology
            importer_type: Optional importer type to use
            
        Returns:
            List of class definitions
        """
        # Get the appropriate importer
        if importer_type:
            importer = self.importers.get(importer_type)
        elif ontology_id in self.loaded_ontologies:
            importer = self.loaded_ontologies[ontology_id]['importer']
        else:
            # Default to PROV importer
            importer = self.importers['prov']
        
        if not importer:
            raise ImportError(f"No importer available for ontology {ontology_id}")
        
        return importer.extract_classes(ontology_id)
    
    def extract_properties(self, ontology_id: str, importer_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extract all properties from an ontology.
        
        Args:
            ontology_id: Unique identifier for the ontology
            importer_type: Optional importer type to use
            
        Returns:
            List of property definitions
        """
        # Get the appropriate importer
        if importer_type:
            importer = self.importers.get(importer_type)
        elif ontology_id in self.loaded_ontologies:
            importer = self.loaded_ontologies[ontology_id]['importer']
        else:
            # Default to PROV importer
            importer = self.importers['prov']
        
        if not importer:
            raise ImportError(f"No importer available for ontology {ontology_id}")
        
        return importer.extract_properties(ontology_id)
    
    def extract_individuals(self, ontology_id: str, importer_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extract all individuals from an ontology.
        
        Args:
            ontology_id: Unique identifier for the ontology
            importer_type: Optional importer type to use
            
        Returns:
            List of individual definitions
        """
        # Get the appropriate importer
        if importer_type:
            importer = self.importers.get(importer_type)
        elif ontology_id in self.loaded_ontologies:
            importer = self.loaded_ontologies[ontology_id]['importer']
        else:
            # Default to PROV importer
            importer = self.importers['prov']
        
        if not importer:
            raise ImportError(f"No importer available for ontology {ontology_id}")
        
        return importer.extract_individuals(ontology_id)
    
    def create_version(self, ontology_id: str, content: str,
                      version_info: Dict[str, Any] = None) -> str:
        """
        Create a new version of an ontology.
        
        Args:
            ontology_id: Unique identifier for the ontology
            content: The new version content
            version_info: Optional version metadata
            
        Returns:
            Version identifier for the new version
        """
        return self.storage.create_version(ontology_id, content, version_info)
    
    def get_metadata(self, ontology_id: str, version: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metadata for an ontology.
        
        Args:
            ontology_id: Unique identifier for the ontology
            version: Optional version
            
        Returns:
            Metadata dictionary
        """
        return self.storage.get_metadata(ontology_id, version)
    
    def update_metadata(self, ontology_id: str, metadata: Dict[str, Any],
                       version: Optional[str] = None) -> bool:
        """
        Update metadata for an ontology.
        
        Args:
            ontology_id: Unique identifier for the ontology
            metadata: New metadata to merge with existing
            version: Optional version to update
            
        Returns:
            True if update was successful
        """
        return self.storage.update_metadata(ontology_id, metadata, version)
