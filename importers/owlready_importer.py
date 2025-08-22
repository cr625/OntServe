"""
Enhanced ontology importer using Owlready2 for reasoning and validation.

This importer provides advanced OWL processing capabilities including:
- Automatic reasoning with HermiT/Pellet reasoners
- Consistency checking
- Inferred relationship discovery
- Enhanced class hierarchy extraction
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
import tempfile

try:
    import owlready2
    from owlready2 import get_ontology, sync_reasoner, Ontology, Thing, ObjectProperty, DataProperty
    # HermiT and Pellet are not directly importable, they're used via sync_reasoner
    try:
        from owlready2.reasoning import InconsistentOntologyError
    except ImportError:
        # Fallback for different owlready2 versions
        InconsistentOntologyError = Exception
    OWLREADY2_AVAILABLE = True
except ImportError:
    OWLREADY2_AVAILABLE = False
    logging.warning("owlready2 not available. OwlreadyImporter will be disabled.")
    # Create stub classes for graceful degradation
    get_ontology = sync_reasoner = Ontology = Thing = ObjectProperty = DataProperty = None
    InconsistentOntologyError = None

try:
    import rdflib
    from rdflib import Graph, Namespace, RDF, RDFS, OWL
except ImportError:
    raise ImportError("rdflib is required. Install with: pip install rdflib")

from .base import BaseImporter, ImportError


class OwlreadyImporter(BaseImporter):
    """
    Enhanced ontology importer using Owlready2 for reasoning and validation.
    
    This importer combines the flexibility of RDFLib parsing with the power of
    Owlready2's reasoning capabilities to provide:
    - Inferred class hierarchies
    - Consistency checking
    - Enhanced entity extraction
    - OWL construct support
    """
    
    def _initialize(self):
        """Initialize the Owlready2 importer."""
        self.logger = logging.getLogger(__name__)
        
        # Configuration options
        self.use_reasoner = True
        self.reasoner_type = 'hermit'  # 'hermit' or 'pellet'
        self.validate_consistency = True
        self.include_inferred = True
        self.extract_restrictions = True
        
        # Temporary ontology storage for Owlready2
        self.temp_dir = tempfile.mkdtemp(prefix='ontserve_owlready_')
        
        # Cache for ontologies and reasoning results
        self.ontology_cache = {}
        self.reasoning_cache = {}
        
        self.logger.info(f"OwlreadyImporter initialized with temp dir: {self.temp_dir}")
    
    def import_from_url(self, url: str, ontology_id: Optional[str] = None,
                       name: Optional[str] = None, description: Optional[str] = None,
                       format: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Import an ontology from a URL with enhanced processing.
        
        Args:
            url: URL of the ontology to import
            ontology_id: Optional unique identifier for the ontology
            name: Optional human-readable name
            description: Optional description
            format: Optional RDF format (turtle, xml, n3, etc.)
            force_refresh: Force re-download even if cached
            
        Returns:
            Dictionary containing enhanced import results
        """
        if not ontology_id:
            ontology_id = self.generate_ontology_id(url)
        
        self.logger.info(f"Importing ontology {ontology_id} from {url}")
        
        try:
            # Step 1: Parse with RDFLib for format flexibility
            rdf_result = self._parse_with_rdflib(url, format)
            
            # Step 2: Convert and load with Owlready2 for reasoning
            owlready_result = self._load_with_owlready(rdf_result['graph'], ontology_id)
            
            # Step 3: Apply reasoning if enabled
            reasoning_result = self._apply_reasoning(owlready_result['ontology'], ontology_id)
            
            # Step 4: Extract enhanced metadata and entities
            enhanced_data = self._extract_enhanced_data(
                owlready_result['ontology'],
                reasoning_result,
                rdf_result['graph']
            )
            
            # Step 5: Combine results
            metadata = {
                'ontology_id': ontology_id,
                'source_url': url,
                'name': name or enhanced_data.get('name', ontology_id),
                'description': description or enhanced_data.get('description', ''),
                'import_date': datetime.now().isoformat(),
                'format': format or rdf_result.get('format', 'turtle'),
                'triple_count': len(rdf_result['graph']),
                'class_count': enhanced_data['statistics']['class_count'],
                'property_count': enhanced_data['statistics']['property_count'],
                'individual_count': enhanced_data['statistics']['individual_count'],
                'reasoning_applied': self.use_reasoner,
                'reasoner_type': self.reasoner_type if self.use_reasoner else None,
                'consistency_check': reasoning_result.get('is_consistent', None),
                'inferred_relationships': reasoning_result.get('inferred_count', 0)
            }
            
            # Store in cache and storage backend
            self._store_results(ontology_id, {
                'metadata': metadata,
                'enhanced_data': enhanced_data,
                'reasoning_result': reasoning_result,
                'rdf_content': rdf_result['graph'].serialize(format='turtle')
            })
            
            return {
                'success': True,
                'ontology_id': ontology_id,
                'metadata': metadata,
                'enhanced_data': enhanced_data,
                'reasoning_result': reasoning_result,
                'message': f"Successfully imported and processed ontology {ontology_id}"
            }
            
        except Exception as e:
            self.logger.error(f"Error importing ontology {ontology_id} from {url}: {e}")
            raise ImportError(f"Failed to import ontology from {url}: {str(e)}")
    
    def import_from_file(self, file_path: str, ontology_id: Optional[str] = None,
                        name: Optional[str] = None, description: Optional[str] = None,
                        format: str = 'turtle') -> Dict[str, Any]:
        """
        Import an ontology from a local file with enhanced processing.
        """
        if not ontology_id:
            ontology_id = os.path.splitext(os.path.basename(file_path))[0]
        
        self.logger.info(f"Importing ontology {ontology_id} from file {file_path}")
        
        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Create temporary URL for processing
            temp_file_url = f"file://{os.path.abspath(file_path)}"
            
            # Use the URL import method with the file content
            return self._import_from_content(
                content, temp_file_url, ontology_id, name, description, format
            )
            
        except Exception as e:
            self.logger.error(f"Error importing ontology from {file_path}: {e}")
            raise ImportError(f"Failed to import ontology from {file_path}: {str(e)}")
    
    def extract_classes(self, ontology_id: str) -> List[Dict[str, Any]]:
        """
        Extract enhanced class information including inferred relationships.
        """
        cached_data = self.ontology_cache.get(ontology_id)
        if not cached_data:
            self.logger.warning(f"No cached data for ontology {ontology_id}")
            return []
        
        enhanced_data = cached_data.get('enhanced_data', {})
        return enhanced_data.get('classes', [])
    
    def extract_properties(self, ontology_id: str) -> List[Dict[str, Any]]:
        """
        Extract enhanced property information including domains and ranges.
        """
        cached_data = self.ontology_cache.get(ontology_id)
        if not cached_data:
            return []
        
        enhanced_data = cached_data.get('enhanced_data', {})
        return enhanced_data.get('properties', [])
    
    def extract_individuals(self, ontology_id: str) -> List[Dict[str, Any]]:
        """
        Extract enhanced individual information including inferred types.
        """
        cached_data = self.ontology_cache.get(ontology_id)
        if not cached_data:
            return []
        
        enhanced_data = cached_data.get('enhanced_data', {})
        return enhanced_data.get('individuals', [])
    
    def get_visualization_data(self, ontology_id: str) -> Dict[str, Any]:
        """
        Get enhanced visualization data optimized for Cytoscape.js.
        """
        cached_data = self.ontology_cache.get(ontology_id)
        if not cached_data:
            return {'nodes': [], 'edges': []}
        
        enhanced_data = cached_data.get('enhanced_data', {})
        reasoning_result = cached_data.get('reasoning_result', {})
        
        return {
            'nodes': self._build_cytoscape_nodes(enhanced_data),
            'edges': self._build_cytoscape_edges(enhanced_data, reasoning_result),
            'layout_options': self._get_layout_options(enhanced_data),
            'style_options': self._get_style_options(enhanced_data)
        }
    
    def _parse_with_rdflib(self, source: str, format: Optional[str] = None) -> Dict[str, Any]:
        """Parse ontology using RDFLib for format flexibility."""
        try:
            import requests
            
            # Download content
            response = requests.get(source, headers={'Accept': 'text/turtle, application/rdf+xml'})
            response.raise_for_status()
            content = response.text
            
            # Auto-detect format if not specified
            if not format:
                format = self.detect_format(content, source)
            
            # Parse with RDFLib
            g = Graph()
            g.parse(data=content, format=format)
            
            self.logger.info(f"RDFLib parsed {len(g)} triples in format {format}")
            
            return {
                'graph': g,
                'content': content,
                'format': format
            }
            
        except Exception as e:
            raise ImportError(f"RDFLib parsing failed: {str(e)}")
    
    def _load_with_owlready(self, rdf_graph: Graph, ontology_id: str) -> Dict[str, Any]:
        """Load ontology with Owlready2 for reasoning capabilities."""
        try:
            # Create temporary OWL file for Owlready2
            temp_file = os.path.join(self.temp_dir, f"{ontology_id}.owl")
            
            # Serialize as RDF/XML (Owlready2's preferred format)
            rdf_graph.serialize(destination=temp_file, format='xml')
            
            # Load with Owlready2
            onto_url = f"file://{temp_file}"
            onto = get_ontology(onto_url).load()
            
            self.logger.info(f"Owlready2 loaded ontology with {len(list(onto.classes()))} classes")
            
            return {
                'ontology': onto,
                'temp_file': temp_file
            }
            
        except Exception as e:
            raise ImportError(f"Owlready2 loading failed: {str(e)}")
    
    def _apply_reasoning(self, onto: Ontology, ontology_id: str) -> Dict[str, Any]:
        """Apply reasoning to discover inferred relationships."""
        if not self.use_reasoner:
            return {'reasoning_applied': False}
        
        try:
            self.logger.info(f"Applying {self.reasoner_type} reasoner to {ontology_id}")
            
            # Store original state
            original_classes = set(onto.classes())
            original_relationships = self._count_relationships(onto)
            
            # Apply reasoner with comprehensive inference options
            with onto:
                if self.reasoner_type == 'hermit':
                    sync_reasoner(
                        reasoner=HermiT,
                        infer_property_values=True,
                        infer_data_property_values=True,
                        debug=False
                    )
                else:
                    sync_reasoner(
                        reasoner=Pellet,
                        infer_property_values=True, 
                        infer_data_property_values=True,
                        debug=False
                    )
                
                # Additional reasoning passes for complex inferences
                self.logger.info(f"Running additional inference passes for {ontology_id}")
                
                # Run reasoner multiple times to catch complex inferences
                for pass_num in range(2):
                    try:
                        if self.reasoner_type == 'hermit':
                            sync_reasoner(reasoner=HermiT, infer_property_values=True)
                        else:
                            sync_reasoner(reasoner=Pellet, infer_property_values=True)
                        self.logger.debug(f"Completed reasoning pass {pass_num + 1}")
                    except Exception as e:
                        self.logger.warning(f"Reasoning pass {pass_num + 1} failed: {e}")
                        break
            
            # Calculate inferred data
            inferred_classes = set(onto.classes()) - original_classes
            inferred_relationships = self._count_relationships(onto) - original_relationships
            
            # Check consistency
            is_consistent = self._check_consistency(onto)
            
            result = {
                'reasoning_applied': True,
                'reasoner_type': self.reasoner_type,
                'is_consistent': is_consistent,
                'inferred_classes': len(inferred_classes),
                'inferred_count': inferred_relationships,
                'original_class_count': len(original_classes),
                'total_class_count': len(list(onto.classes()))
            }
            
            self.logger.info(f"Reasoning complete: {result}")
            return result
            
        except InconsistentOntologyError as e:
            self.logger.warning(f"Ontology is inconsistent: {e}")
            return {
                'reasoning_applied': True,
                'is_consistent': False,
                'error': str(e),
                'inferred_count': 0
            }
        except Exception as e:
            self.logger.error(f"Reasoning failed: {e}")
            return {
                'reasoning_applied': False,
                'error': str(e),
                'inferred_count': 0
            }
    
    def _extract_enhanced_data(self, onto: Ontology, reasoning_result: Dict, rdf_graph: Graph) -> Dict[str, Any]:
        """Extract comprehensive ontology data for visualization."""
        classes = []
        properties = []
        individuals = []
        
        # Extract classes with enhanced information
        for cls in onto.classes():
            class_info = {
                'uri': str(cls.iri),
                'name': cls.name,
                'label': self._get_labels(cls),
                'comment': self._get_comments(cls),
                'parents': [str(parent.iri) for parent in cls.is_a if hasattr(parent, 'iri')],
                'children': [str(child.iri) for child in cls.subclasses()],
                'equivalent_to': [str(eq.iri) for eq in cls.equivalent_to if hasattr(eq, 'iri')],
                'disjoint_with': [str(dj.iri) for dj in cls.disjoints() if hasattr(dj, 'iri')],
                'restrictions': self._extract_restrictions(cls) if self.extract_restrictions else [],
                'is_inferred': cls not in reasoning_result.get('original_classes', set()),
                'namespace': str(cls.namespace.base_iri) if cls.namespace else None
            }
            classes.append(class_info)
        
        # Extract properties
        for prop in onto.properties():
            prop_info = {
                'uri': str(prop.iri),
                'name': prop.name,
                'label': self._get_labels(prop),
                'comment': self._get_comments(prop),
                'type': self._get_property_type(prop),
                'domain': [str(d.iri) for d in prop.domain if hasattr(d, 'iri')],
                'range': [str(r.iri) for r in prop.range if hasattr(r, 'iri')],
                'inverse': str(prop.inverse_property.iri) if prop.inverse_property else None,
                'functional': prop in onto.functional_properties(),
                'transitive': prop in onto.transitive_properties(),
                'symmetric': prop in onto.symmetric_properties()
            }
            properties.append(prop_info)
        
        # Extract individuals
        for ind in onto.individuals():
            ind_info = {
                'uri': str(ind.iri),
                'name': ind.name,
                'label': self._get_labels(ind),
                'comment': self._get_comments(ind),
                'types': [str(t.iri) for t in ind.is_a if hasattr(t, 'iri')],
                'properties': self._extract_individual_properties(ind)
            }
            individuals.append(ind_info)
        
        # Calculate statistics
        statistics = {
            'class_count': len(classes),
            'property_count': len(properties),
            'individual_count': len(individuals),
            'namespace_count': len(set(c.get('namespace') for c in classes if c.get('namespace')))
        }
        
        return {
            'classes': classes,
            'properties': properties,
            'individuals': individuals,
            'statistics': statistics,
            'name': onto.name,
            'description': self._extract_ontology_description(onto)
        }
    
    def _build_cytoscape_nodes(self, enhanced_data: Dict) -> List[Dict[str, Any]]:
        """Build Cytoscape.js compatible nodes."""
        nodes = []
        
        for cls in enhanced_data.get('classes', []):
            node = {
                'data': {
                    'id': cls['uri'],
                    'label': cls['label'][0] if cls['label'] else cls['name'],
                    'name': cls['name'],
                    'type': 'class',
                    'uri': cls['uri'],
                    'parents': cls['parents'],
                    'children': cls['children'],
                    'restrictions': len(cls.get('restrictions', [])),
                    'is_inferred': cls.get('is_inferred', False),
                    'namespace': cls.get('namespace', '')
                },
                'classes': self._get_node_classes(cls)
            }
            nodes.append(node)
        
        return nodes
    
    def _build_cytoscape_edges(self, enhanced_data: Dict, reasoning_result: Dict) -> List[Dict[str, Any]]:
        """Build Cytoscape.js compatible edges."""
        edges = []
        
        for cls in enhanced_data.get('classes', []):
            for parent_uri in cls['parents']:
                edge = {
                    'data': {
                        'id': f"{cls['uri']}-subClassOf-{parent_uri}",
                        'source': cls['uri'],
                        'target': parent_uri,
                        'type': 'subClassOf',
                        'is_inferred': cls.get('is_inferred', False)
                    },
                    'classes': 'subclass-edge' + (' inferred' if cls.get('is_inferred', False) else ' explicit')
                }
                edges.append(edge)
        
        return edges
    
    def _get_layout_options(self, enhanced_data: Dict) -> Dict[str, Any]:
        """Get layout options optimized for the ontology structure."""
        class_count = len(enhanced_data.get('classes', []))
        
        if class_count < 50:
            return {'name': 'dagre', 'rankDir': 'TB'}
        elif class_count < 200:
            return {'name': 'cose', 'nodeRepulsion': 400000}
        else:
            return {'name': 'fcose', 'samplingType': True}
    
    def _get_style_options(self, enhanced_data: Dict) -> List[Dict[str, Any]]:
        """Get style options for Cytoscape.js visualization."""
        return [
            {
                'selector': 'node',
                'style': {
                    'label': 'data(label)',
                    'width': '60px',
                    'height': '60px',
                    'background-color': '#4A90E2',
                    'border-width': '2px',
                    'border-color': '#fff',
                    'color': '#333',
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'font-size': '10px'
                }
            },
            {
                'selector': 'node.inferred',
                'style': {
                    'background-color': '#7ED321',
                    'border-style': 'dashed'
                }
            },
            {
                'selector': 'edge',
                'style': {
                    'width': '2px',
                    'line-color': '#999',
                    'target-arrow-color': '#999',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier'
                }
            },
            {
                'selector': 'edge.inferred',
                'style': {
                    'line-color': '#7ED321',
                    'target-arrow-color': '#7ED321',
                    'line-style': 'dashed'
                }
            }
        ]
    
    # Helper methods
    def _get_labels(self, entity) -> List[str]:
        """Extract labels from an entity."""
        return [str(label) for label in entity.label] if hasattr(entity, 'label') else []
    
    def _get_comments(self, entity) -> List[str]:
        """Extract comments from an entity."""
        return [str(comment) for comment in entity.comment] if hasattr(entity, 'comment') else []
    
    def _get_property_type(self, prop) -> str:
        """Determine property type."""
        if isinstance(prop, ObjectProperty):
            return 'object_property'
        elif isinstance(prop, DataProperty):
            return 'data_property'
        else:
            return 'property'
    
    def _extract_restrictions(self, cls) -> List[Dict[str, Any]]:
        """Extract OWL restrictions from a class."""
        restrictions = []
        
        for restriction in cls.is_a:
            if hasattr(restriction, 'property') and hasattr(restriction, 'value'):
                rest_info = {
                    'type': type(restriction).__name__,
                    'property': str(restriction.property.iri) if restriction.property else None,
                    'value': str(restriction.value) if restriction.value else None
                }
                restrictions.append(rest_info)
        
        return restrictions
    
    def _extract_individual_properties(self, ind) -> Dict[str, Any]:
        """Extract properties of an individual."""
        properties = {}
        
        for prop in ind.get_properties():
            prop_values = [str(v) for v in prop[ind]]
            if prop_values:
                properties[str(prop.iri)] = prop_values
        
        return properties
    
    def _extract_ontology_description(self, onto: Ontology) -> str:
        """Extract ontology description from annotations."""
        # Try to find description in common annotation properties
        for cls in onto.classes():
            if hasattr(cls, 'comment') and cls.comment:
                return str(cls.comment[0])
        
        return f"Ontology containing {len(list(onto.classes()))} classes"
    
    def _count_relationships(self, onto: Ontology) -> int:
        """Count explicit relationships in ontology."""
        count = 0
        for cls in onto.classes():
            count += len([p for p in cls.is_a if hasattr(p, 'iri')])
        return count
    
    def _check_consistency(self, onto: Ontology) -> bool:
        """Check ontology consistency."""
        try:
            # Try to run reasoner - if it succeeds, ontology is consistent
            with onto:
                sync_reasoner(reasoner=HermiT)
            return True
        except InconsistentOntologyError:
            return False
        except:
            return None  # Unknown consistency state
    
    def _get_node_classes(self, cls: Dict) -> str:
        """Get CSS classes for a node based on its properties."""
        classes = ['class-node']
        
        if cls.get('is_inferred'):
            classes.append('inferred')
        
        if cls.get('restrictions'):
            classes.append('has-restrictions')
        
        # Add namespace-based classes
        if cls.get('namespace'):
            namespace_class = cls['namespace'].replace('http://', '').replace('https://', '').replace('/', '-').replace('.', '-')
            classes.append(f'ns-{namespace_class}')
        
        return ' '.join(classes)
    
    def _store_results(self, ontology_id: str, data: Dict[str, Any]):
        """Store results in cache and storage backend."""
        self.ontology_cache[ontology_id] = data
        
        if self.storage_backend:
            self.storage_backend.store(
                ontology_id,
                data['rdf_content'],
                data['metadata']
            )
    
    def _import_from_content(self, content: str, source_url: str, ontology_id: str,
                           name: Optional[str], description: Optional[str], format: str) -> Dict[str, Any]:
        """Import ontology from content string."""
        try:
            # Parse with RDFLib
            g = Graph()
            g.parse(data=content, format=format)
            
            rdf_result = {
                'graph': g,
                'content': content,
                'format': format
            }
            
            # Continue with standard processing
            owlready_result = self._load_with_owlready(g, ontology_id)
            reasoning_result = self._apply_reasoning(owlready_result['ontology'], ontology_id)
            enhanced_data = self._extract_enhanced_data(
                owlready_result['ontology'],
                reasoning_result,
                g
            )
            
            metadata = {
                'ontology_id': ontology_id,
                'source_url': source_url,
                'name': name or enhanced_data.get('name', ontology_id),
                'description': description or enhanced_data.get('description', ''),
                'import_date': datetime.now().isoformat(),
                'format': format,
                'triple_count': len(g),
                'class_count': enhanced_data['statistics']['class_count'],
                'property_count': enhanced_data['statistics']['property_count'],
                'individual_count': enhanced_data['statistics']['individual_count'],
                'reasoning_applied': self.use_reasoner,
                'reasoner_type': self.reasoner_type if self.use_reasoner else None,
                'consistency_check': reasoning_result.get('is_consistent', None),
                'inferred_relationships': reasoning_result.get('inferred_count', 0)
            }
            
            self._store_results(ontology_id, {
                'metadata': metadata,
                'enhanced_data': enhanced_data,
                'reasoning_result': reasoning_result,
                'rdf_content': content
            })
            
            return {
                'success': True,
                'ontology_id': ontology_id,
                'metadata': metadata,
                'enhanced_data': enhanced_data,
                'reasoning_result': reasoning_result,
                'message': f"Successfully imported and processed ontology {ontology_id}"
            }
            
        except Exception as e:
            raise ImportError(f"Failed to import ontology from content: {str(e)}")
    
    def __del__(self):
        """Cleanup temporary files."""
        try:
            import shutil
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except:
            pass
