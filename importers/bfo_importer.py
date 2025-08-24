"""
BFO (Basic Formal Ontology) importer.

Specialized importer for handling BFO ontologies with support for
upper-level ontology concepts and formal ontology patterns.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import requests

try:
    import rdflib
    from rdflib import Graph, Namespace, RDF, RDFS, OWL
    from rdflib.namespace import FOAF, DCTERMS, XSD
except ImportError:
    raise ImportError("rdflib is required for BFO import. Install with: pip install rdflib")

from importers.base import BaseImporter, ImportError


# BFO specific namespaces
BFO_NAMESPACES = {
    'bfo': Namespace("http://purl.obolibrary.org/obo/BFO_"),
    'obo': Namespace("http://purl.obolibrary.org/obo/"),
    'oboInOwl': Namespace("http://www.geneontology.org/formats/oboInOwl#"),
    'iao': Namespace("http://purl.obolibrary.org/obo/IAO_"),
}

# Standard namespaces
STANDARD_NAMESPACES = {
    'foaf': FOAF,
    'dcterms': DCTERMS,
    'xsd': XSD,
    'owl': OWL,
    'rdf': RDF,
    'rdfs': RDFS,
    'skos': Namespace("http://www.w3.org/2004/02/skos/core#"),
}


class BFOImporter(BaseImporter):
    """
    Specialized importer for BFO (Basic Formal Ontology).
    
    Provides enhanced support for:
    - BFO core concepts (Continuant, Occurrent, etc.)
    - Upper-level ontology patterns
    - Formal ontology relationships
    - Integration with domain ontologies
    """
    
    def _initialize(self):
        """Initialize the BFO importer."""
        self.logger = logging.getLogger(__name__)
        
        # Initialize namespace manager
        from rdflib.namespace import NamespaceManager
        self.namespace_manager = NamespaceManager(Graph())
        
        # Bind standard namespaces
        for prefix, ns in STANDARD_NAMESPACES.items():
            self.namespace_manager.bind(prefix, ns)
        
        # Bind BFO-specific namespaces
        for prefix, ns in BFO_NAMESPACES.items():
            self.namespace_manager.bind(prefix, ns)
        
        # Set up cache directory
        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)
    
    def import_bfo(self, version: str = "latest", force_refresh: bool = False) -> Dict[str, Any]:
        """
        Import the BFO (Basic Formal Ontology).
        
        Args:
            version: BFO version to import ("latest", "2.0", "2020", etc.)
            force_refresh: Force re-download even if cached
            
        Returns:
            Dictionary containing import results
        """
        # BFO URLs for different versions
        # The main BFO repository uses .owl files, we'll use the OBO Foundry version
        bfo_urls = {
            "latest": "http://purl.obolibrary.org/obo/bfo.owl",
            "2.0": "http://purl.obolibrary.org/obo/bfo/2.0/bfo.owl",
            "2020": "http://purl.obolibrary.org/obo/bfo/2020/bfo.owl",
            "github": "https://raw.githubusercontent.com/BFO-ontology/BFO/master/releases/2.0/bfo.owl",
        }
        
        bfo_url = bfo_urls.get(version, bfo_urls["latest"])
        
        self.logger.info(f"Importing BFO ontology (version: {version})...")
        
        result = self.import_from_url(
            bfo_url,
            ontology_id="bfo",
            name="Basic Formal Ontology (BFO)",
            description="BFO is a top-level ontology designed to support scientific research by providing a genuine upper ontology for scientific domains",
            format=None,  # Let it auto-detect the format
            force_refresh=force_refresh
        )
        
        # Extract BFO specific concepts
        if result.get('success'):
            result['upper_level_concepts'] = self._extract_bfo_upper_concepts(result['graph'])
            self.logger.info(f"Extracted {len(result['upper_level_concepts'])} BFO upper-level concepts")
        
        return result
    
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
            Dictionary containing import results
        """
        # Generate ontology ID if not provided
        if not ontology_id:
            ontology_id = self.generate_ontology_id(url)
        
        # Check cache first if not forcing refresh
        if not force_refresh and self.cache_dir:
            cache_file = os.path.join(self.cache_dir, f"{ontology_id}.ttl")
            metadata_file = os.path.join(self.cache_dir, f"{ontology_id}.json")
            
            if os.path.exists(cache_file) and os.path.exists(metadata_file):
                self.logger.info(f"Loading ontology {ontology_id} from cache")
                return self._load_from_cache(ontology_id)
        
        try:
            # Download ontology
            self.logger.info(f"Downloading ontology from {url}")
            response = requests.get(url, headers={'Accept': 'text/turtle, application/rdf+xml'}, timeout=30)
            response.raise_for_status()
            
            # Parse ontology
            g = Graph()
            
            # Auto-detect format if not specified
            if not format:
                format = self.detect_format(response.text, url)
            
            g.parse(data=response.text, format=format)
            self.logger.info(f"Successfully parsed ontology with {len(g)} triples")
            
            # Extract metadata
            metadata = self._extract_metadata(g, url, name, description)
            metadata['ontology_id'] = ontology_id
            metadata['source_url'] = url
            metadata['import_date'] = datetime.now().isoformat()
            metadata['format'] = format
            metadata['triple_count'] = len(g)
            
            # Save to cache if cache directory is set
            if self.cache_dir:
                cache_file = os.path.join(self.cache_dir, f"{ontology_id}.ttl")
                metadata_file = os.path.join(self.cache_dir, f"{ontology_id}.json")
                
                g.serialize(destination=cache_file, format='turtle')
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)
            
            # Store in memory
            self.imported_ontologies[ontology_id] = {
                'graph': g,
                'metadata': metadata,
                'content': g.serialize(format='turtle')
            }
            
            # Optionally save to storage backend
            if self.storage_backend:
                self.storage_backend.store(
                    ontology_id, 
                    g.serialize(format='turtle'),
                    metadata
                )
            
            return {
                'success': True,
                'ontology_id': ontology_id,
                'metadata': metadata,
                'graph': g,
                'message': f"Successfully imported ontology {ontology_id}"
            }
            
        except Exception as e:
            self.logger.error(f"Error importing ontology from {url}: {e}")
            raise ImportError(f"Failed to import ontology from {url}: {str(e)}")
    
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
        """
        # Generate ontology ID if not provided
        if not ontology_id:
            ontology_id = os.path.splitext(os.path.basename(file_path))[0]
        
        try:
            # Parse ontology
            g = Graph()
            g.parse(file_path, format=format)
            self.logger.info(f"Successfully parsed ontology from {file_path} with {len(g)} triples")
            
            # Extract metadata
            metadata = self._extract_metadata(g, file_path, name, description)
            metadata['ontology_id'] = ontology_id
            metadata['source_file'] = file_path
            metadata['import_date'] = datetime.now().isoformat()
            metadata['format'] = format
            metadata['triple_count'] = len(g)
            
            # Save to cache if cache directory is set
            if self.cache_dir:
                cache_file = os.path.join(self.cache_dir, f"{ontology_id}.ttl")
                metadata_file = os.path.join(self.cache_dir, f"{ontology_id}.json")
                
                g.serialize(destination=cache_file, format='turtle')
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)
            
            # Store in memory
            self.imported_ontologies[ontology_id] = {
                'graph': g,
                'metadata': metadata,
                'content': g.serialize(format='turtle')
            }
            
            # Optionally save to storage backend
            if self.storage_backend:
                self.storage_backend.store(
                    ontology_id,
                    g.serialize(format='turtle'),
                    metadata
                )
            
            return {
                'success': True,
                'ontology_id': ontology_id,
                'metadata': metadata,
                'graph': g,
                'content': g.serialize(format='turtle'),
                'message': f"Successfully imported ontology {ontology_id}"
            }
            
        except Exception as e:
            self.logger.error(f"Error importing ontology from {file_path}: {e}")
            raise ImportError(f"Failed to import ontology from {file_path}: {str(e)}")
    
    def extract_classes(self, ontology_id: str) -> List[Dict[str, Any]]:
        """
        Extract all classes from an imported ontology.
        
        Args:
            ontology_id: ID of the ontology
            
        Returns:
            List of class definitions
        """
        ont_data = self.get_imported_ontology(ontology_id)
        if not ont_data:
            return []
        
        g = ont_data['graph']
        classes = []
        
        for s in g.subjects(RDF.type, OWL.Class):
            class_info = {
                'uri': str(s),
                'label': self._get_label(g, s),
                'comment': self._get_comment(g, s),
                'definition': self._get_definition(g, s),
                'subclass_of': [str(o) for o in g.objects(s, RDFS.subClassOf)],
                'is_upper_level': self._is_bfo_upper_level(str(s))
            }
            classes.append(class_info)
        
        return classes
    
    def extract_properties(self, ontology_id: str) -> List[Dict[str, Any]]:
        """
        Extract all properties from an imported ontology.
        
        Args:
            ontology_id: ID of the ontology
            
        Returns:
            List of property definitions
        """
        ont_data = self.get_imported_ontology(ontology_id)
        if not ont_data:
            return []
        
        g = ont_data['graph']
        properties = []
        
        # Object properties
        for s in g.subjects(RDF.type, OWL.ObjectProperty):
            prop_info = {
                'uri': str(s),
                'type': 'object_property',
                'label': self._get_label(g, s),
                'comment': self._get_comment(g, s),
                'definition': self._get_definition(g, s),
                'domain': [str(o) for o in g.objects(s, RDFS.domain)],
                'range': [str(o) for o in g.objects(s, RDFS.range)]
            }
            properties.append(prop_info)
        
        # Datatype properties
        for s in g.subjects(RDF.type, OWL.DatatypeProperty):
            prop_info = {
                'uri': str(s),
                'type': 'datatype_property',
                'label': self._get_label(g, s),
                'comment': self._get_comment(g, s),
                'definition': self._get_definition(g, s),
                'domain': [str(o) for o in g.objects(s, RDFS.domain)],
                'range': [str(o) for o in g.objects(s, RDFS.range)]
            }
            properties.append(prop_info)
        
        return properties
    
    def extract_individuals(self, ontology_id: str) -> List[Dict[str, Any]]:
        """
        Extract all individuals from an imported ontology.
        
        Args:
            ontology_id: ID of the ontology
            
        Returns:
            List of individual definitions
        """
        ont_data = self.get_imported_ontology(ontology_id)
        if not ont_data:
            return []
        
        g = ont_data['graph']
        individuals = []
        
        # Find all subjects that are instances of classes
        for s, p, o in g.triples((None, RDF.type, None)):
            # Skip if object is a meta-class like owl:Class
            if o in [OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, 
                    RDFS.Class, RDF.Property]:
                continue
            
            individual_info = {
                'uri': str(s),
                'type': str(o),
                'label': self._get_label(g, s),
                'comment': self._get_comment(g, s),
                'definition': self._get_definition(g, s),
                'properties': {}
            }
            
            # Get all properties of this individual
            for pred, obj in g.predicate_objects(s):
                if pred not in [RDF.type, RDFS.label, RDFS.comment]:
                    individual_info['properties'][str(pred)] = str(obj)
            
            individuals.append(individual_info)
        
        return individuals
    
    def _extract_bfo_upper_concepts(self, graph: Graph) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract BFO upper-level concepts.
        
        Args:
            graph: RDF graph containing BFO ontology
            
        Returns:
            Dictionary of concept categories with their terms
        """
        concepts = {
            'continuants': [],
            'occurrents': [],
            'relations': [],
            'top_level': []
        }
        
        # Define BFO upper-level class URIs
        bfo = BFO_NAMESPACES['bfo']
        obo = BFO_NAMESPACES['obo']
        
        # Top-level BFO classes
        top_level_uris = [
            'http://purl.obolibrary.org/obo/BFO_0000001',  # entity
            'http://purl.obolibrary.org/obo/BFO_0000002',  # continuant
            'http://purl.obolibrary.org/obo/BFO_0000003',  # occurrent
            'http://purl.obolibrary.org/obo/BFO_0000004',  # independent continuant
            'http://purl.obolibrary.org/obo/BFO_0000020',  # specifically dependent continuant
            'http://purl.obolibrary.org/obo/BFO_0000031',  # generically dependent continuant
        ]
        
        # Process-related (occurrent) classes
        occurrent_uris = [
            'http://purl.obolibrary.org/obo/BFO_0000015',  # process
            'http://purl.obolibrary.org/obo/BFO_0000016',  # disposition
            'http://purl.obolibrary.org/obo/BFO_0000017',  # realizable entity
            'http://purl.obolibrary.org/obo/BFO_0000023',  # role
            'http://purl.obolibrary.org/obo/BFO_0000182',  # history
        ]
        
        # Extract all classes and categorize them
        for s in graph.subjects(RDF.type, OWL.Class):
            uri = str(s)
            
            # Skip blank nodes
            if not uri.startswith('http'):
                continue
            
            class_info = {
                'uri': uri,
                'label': self._get_label(graph, s) or uri.split('/')[-1],
                'comment': self._get_comment(graph, s),
                'definition': self._get_definition(graph, s)
            }
            
            # Categorize based on URI or parent class
            if uri in top_level_uris:
                concepts['top_level'].append(class_info)
                
                # Also add to specific categories
                if 'continuant' in class_info['label'].lower():
                    concepts['continuants'].append(class_info)
                elif 'occurrent' in class_info['label'].lower():
                    concepts['occurrents'].append(class_info)
            
            elif uri in occurrent_uris:
                concepts['occurrents'].append(class_info)
            
            else:
                # Check parent classes
                for parent in graph.objects(s, RDFS.subClassOf):
                    parent_uri = str(parent)
                    if 'continuant' in parent_uri.lower() or parent_uri in top_level_uris[:4]:
                        concepts['continuants'].append(class_info)
                        break
                    elif 'occurrent' in parent_uri.lower() or parent_uri in occurrent_uris:
                        concepts['occurrents'].append(class_info)
                        break
        
        # Extract BFO relations
        for s in graph.subjects(RDF.type, OWL.ObjectProperty):
            uri = str(s)
            
            # Check if it's a BFO relation
            if 'BFO' in uri or 'obo' in uri:
                prop_info = {
                    'uri': uri,
                    'label': self._get_label(graph, s) or uri.split('/')[-1],
                    'comment': self._get_comment(graph, s),
                    'definition': self._get_definition(graph, s),
                    'type': 'object_property'
                }
                concepts['relations'].append(prop_info)
        
        return concepts
    
    def _is_bfo_upper_level(self, uri: str) -> bool:
        """
        Check if a URI represents a BFO upper-level concept.
        
        Args:
            uri: URI to check
            
        Returns:
            True if it's a BFO upper-level concept
        """
        upper_level_patterns = [
            'BFO_0000001',  # entity
            'BFO_0000002',  # continuant
            'BFO_0000003',  # occurrent
            'BFO_0000004',  # independent continuant
            'BFO_0000020',  # specifically dependent continuant
            'BFO_0000031',  # generically dependent continuant
        ]
        
        return any(pattern in uri for pattern in upper_level_patterns)
    
    def _extract_metadata(self, graph: Graph, source: str,
                         name: Optional[str] = None, 
                         description: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract metadata from an ontology graph.
        
        Args:
            graph: RDF graph
            source: Source URL or file path
            name: Override name
            description: Override description
            
        Returns:
            Dictionary containing metadata
        """
        metadata = {
            'source': source,
            'name': name or '',
            'description': description or ''
        }
        
        # Try to find ontology declaration
        for s in graph.subjects(RDF.type, OWL.Ontology):
            if not name:
                metadata['name'] = self._get_label(graph, s) or str(s)
            if not description:
                comment = self._get_comment(graph, s)
                if comment:
                    metadata['description'] = comment
            
            # Get version info
            version = next(graph.objects(s, OWL.versionInfo), None)
            if version:
                metadata['version'] = str(version)
            
            # Get other metadata
            for pred, key in [
                (DCTERMS.title, 'title'),
                (DCTERMS.creator, 'creator'),
                (DCTERMS.publisher, 'publisher'),
                (DCTERMS.license, 'license'),
                (DCTERMS.created, 'created'),
                (DCTERMS.modified, 'modified')
            ]:
                value = next(graph.objects(s, pred), None)
                if value:
                    metadata[key] = str(value)
            
            break  # Use first ontology declaration found
        
        # Count classes and properties
        metadata['class_count'] = len(list(graph.subjects(RDF.type, OWL.Class)))
        metadata['property_count'] = (
            len(list(graph.subjects(RDF.type, OWL.ObjectProperty))) +
            len(list(graph.subjects(RDF.type, OWL.DatatypeProperty)))
        )
        
        return metadata
    
    def _get_label(self, graph: Graph, subject: Any) -> Optional[str]:
        """Get rdfs:label for a subject."""
        label = next(graph.objects(subject, RDFS.label), None)
        return str(label) if label else None
    
    def _get_comment(self, graph: Graph, subject: Any) -> Optional[str]:
        """Get rdfs:comment for a subject."""
        comment = next(graph.objects(subject, RDFS.comment), None)
        return str(comment) if comment else None
    
    def _get_definition(self, graph: Graph, subject: Any) -> Optional[str]:
        """Get IAO:definition for a subject (common in BFO and OBO ontologies)."""
        iao_def = BFO_NAMESPACES['iao']['0000115']  # IAO definition annotation
        definition = next(graph.objects(subject, iao_def), None)
        
        if not definition:
            # Try obo:IAO_0000115 format
            obo_def = BFO_NAMESPACES['obo']['IAO_0000115']
            definition = next(graph.objects(subject, obo_def), None)
        
        return str(definition) if definition else None
    
    def _load_from_cache(self, ontology_id: str) -> Optional[Dict[str, Any]]:
        """Load an ontology from cache."""
        if not self.cache_dir:
            return None
        
        cache_file = os.path.join(self.cache_dir, f"{ontology_id}.ttl")
        metadata_file = os.path.join(self.cache_dir, f"{ontology_id}.json")
        
        if not os.path.exists(cache_file) or not os.path.exists(metadata_file):
            return None
        
        try:
            # Load metadata
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            # Load graph
            g = Graph()
            g.parse(cache_file, format='turtle')
            
            # Store in memory
            self.imported_ontologies[ontology_id] = {
                'graph': g,
                'metadata': metadata,
                'content': g.serialize(format='turtle')
            }
            
            return {
                'success': True,
                'ontology_id': ontology_id,
                'metadata': metadata,
                'graph': g,
                'message': f"Loaded ontology {ontology_id} from cache"
            }
            
        except Exception as e:
            self.logger.error(f"Error loading ontology {ontology_id} from cache: {e}")
            return None
