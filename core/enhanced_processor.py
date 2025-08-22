"""
Enhanced Ontology Processor: Hybrid RDFLib + Owlready2 Approach

This module provides a comprehensive hybrid processing system that combines:
- RDFLib's flexible parsing capabilities
- Owlready2's powerful reasoning features
- OntServe's storage and database integration

The processor serves as the core bridge between file-based ontology storage
and database-backed semantic search, with optional reasoning capabilities.
"""

import os
import logging
import tempfile
import shutil
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime
from pathlib import Path

# RDF Processing
import rdflib
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL

# Enhanced Ontology Processing
try:
    import owlready2
    from owlready2 import get_ontology, sync_reasoner, Thing, ObjectProperty, DataProperty
    # HermiT and Pellet are not directly importable, they're used via sync_reasoner
    try:
        from owlready2.reasoning import InconsistentOntologyError
    except ImportError:
        # Fallback for different owlready2 versions
        InconsistentOntologyError = Exception
    OWLREADY2_AVAILABLE = True
except ImportError:
    OWLREADY2_AVAILABLE = False
    logging.warning("owlready2 not available. Reasoning features will be disabled.")

# Vector Embeddings
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logging.warning("sentence-transformers not available. Semantic search will be disabled.")

# OntServe Components
from storage.base import StorageBackend
from web.models import db, Ontology, OntologyEntity, OntologyVersion
from importers.owlready_importer import OwlreadyImporter


# Configure logging
logger = logging.getLogger(__name__)

# Define common namespaces
BFO = Namespace("http://purl.obolibrary.org/obo/")
PROV = Namespace("http://www.w3.org/ns/prov#")
PROETHICA = Namespace("http://proethica.org/ontology/engineering-ethics#")


class ProcessingOptions:
    """Configuration options for enhanced processing."""
    
    def __init__(self,
                 use_reasoning: bool = True,
                 reasoner_type: str = 'hermit',
                 validate_consistency: bool = True,
                 include_inferred: bool = True,
                 extract_restrictions: bool = True,
                 generate_embeddings: bool = True,
                 cache_reasoning: bool = True,
                 force_refresh: bool = False):
        """
        Initialize processing options.
        
        Args:
            use_reasoning: Enable Owlready2 reasoning
            reasoner_type: 'hermit' or 'pellet'
            validate_consistency: Check ontology consistency
            include_inferred: Include inferred relationships in results
            extract_restrictions: Extract OWL restrictions
            generate_embeddings: Generate vector embeddings for search
            cache_reasoning: Cache reasoning results for performance
            force_refresh: Force re-processing even if cached
        """
        self.use_reasoning = use_reasoning and OWLREADY2_AVAILABLE
        self.reasoner_type = reasoner_type
        self.validate_consistency = validate_consistency
        self.include_inferred = include_inferred
        self.extract_restrictions = extract_restrictions
        self.generate_embeddings = generate_embeddings and EMBEDDINGS_AVAILABLE
        self.cache_reasoning = cache_reasoning
        self.force_refresh = force_refresh


class ProcessingResult:
    """Container for enhanced processing results."""
    
    def __init__(self):
        self.success: bool = False
        self.ontology_id: str = ""
        self.metadata: Dict[str, Any] = {}
        self.entities: List[OntologyEntity] = []
        self.reasoning_applied: bool = False
        self.consistency_check: Optional[bool] = None
        self.inferred_count: int = 0
        self.error_message: Optional[str] = None
        self.warnings: List[str] = []
        self.processing_time: float = 0.0
        self.visualization_data: Dict[str, Any] = {}
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            'success': self.success,
            'ontology_id': self.ontology_id,
            'metadata': self.metadata,
            'entity_count': len(self.entities),
            'reasoning_applied': self.reasoning_applied,
            'consistency_check': self.consistency_check,
            'inferred_count': self.inferred_count,
            'error_message': self.error_message,
            'warnings': self.warnings,
            'processing_time': self.processing_time,
            'has_visualization_data': bool(self.visualization_data)
        }


class EnhancedOntologyProcessor:
    """
    Hybrid processor combining RDFLib flexibility with Owlready2 reasoning.
    
    This processor provides the core functionality for OntServe's enhanced
    ontology processing pipeline, integrating:
    - File-based ontology storage
    - Database-backed entity management
    - Reasoning and consistency checking
    - Semantic search with vector embeddings
    - Visualization data generation
    """
    
    def __init__(self, storage_backend: StorageBackend, db_session=None):
        """
        Initialize the enhanced processor.
        
        Args:
            storage_backend: File storage backend
            db_session: Database session (defaults to app context)
        """
        self.storage = storage_backend
        self._db_session = db_session  # Store but don't evaluate db.session yet
        
        # Initialize components
        self.owlready_importer = OwlreadyImporter(storage_backend) if OWLREADY2_AVAILABLE else None
        self.embedding_model = self._initialize_embedding_model()
        
        # Temporary directory for processing
        self.temp_dir = tempfile.mkdtemp(prefix='ontserve_processor_')
        
        # Caches
        self.reasoning_cache: Dict[str, Dict[str, Any]] = {}
        self.entity_cache: Dict[str, List[OntologyEntity]] = {}
        
        logger.info(f"Enhanced processor initialized with reasoning: {OWLREADY2_AVAILABLE}, embeddings: {EMBEDDINGS_AVAILABLE}")
    
    @property
    def db_session(self):
        """Get database session, with lazy loading for Flask app context."""
        if self._db_session is not None:
            return self._db_session
        try:
            return db.session
        except RuntimeError as e:
            if "application context" in str(e):
                raise RuntimeError(
                    "Enhanced processor requires Flask application context for database operations. "
                    "Make sure to call within a Flask route or use app.app_context()."
                ) from e
            raise
    
    def process_ontology(self, ontology_id: str, options: Optional[ProcessingOptions] = None) -> ProcessingResult:
        """
        Enhanced processing of an ontology with optional reasoning.
        
        Args:
            ontology_id: The ontology identifier
            options: Processing configuration options
            
        Returns:
            ProcessingResult containing comprehensive results
        """
        start_time = datetime.now()
        result = ProcessingResult()
        result.ontology_id = ontology_id
        
        if not options:
            options = ProcessingOptions()
        
        try:
            logger.info(f"Starting enhanced processing of {ontology_id}")
            
            # Step 1: Get ontology record
            ontology_record = self._get_ontology_record(ontology_id)
            if not ontology_record:
                raise ValueError(f"Ontology {ontology_id} not found")
            
            # Step 2: Load content from storage
            rdf_content = self._load_ontology_content(ontology_id)
            
            # Step 3: Parse with RDFLib
            rdf_graph = self._parse_with_rdflib(rdf_content, ontology_id)
            
            # Step 4: Enhanced processing with Owlready2 (if enabled)
            reasoning_result = {}
            if options.use_reasoning and self.owlready_importer:
                reasoning_result = self._apply_reasoning(rdf_content, ontology_id, options)
                result.reasoning_applied = True
                result.consistency_check = reasoning_result.get('is_consistent')
                result.inferred_count = reasoning_result.get('inferred_count', 0)
            
            # Step 5: Extract entities with enhanced metadata
            entities = self._extract_enhanced_entities(
                rdf_graph, reasoning_result, ontology_record, options
            )
            
            # Step 6: Generate embeddings (if enabled)
            if options.generate_embeddings:
                entities = self._generate_embeddings(entities)
            
            # Step 7: Store entities in database
            stored_entities = self._store_entities(entities, ontology_record.id, options.force_refresh)
            
            # Step 8: Generate visualization data
            if reasoning_result:
                result.visualization_data = self._generate_visualization_data(
                    stored_entities, reasoning_result, ontology_id
                )
            
            # Step 9: Update metadata
            metadata = self._generate_metadata(
                ontology_record, rdf_graph, reasoning_result, len(stored_entities)
            )
            
            # Complete result
            result.success = True
            result.metadata = metadata
            result.entities = stored_entities
            result.processing_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"Successfully processed {ontology_id}: {len(stored_entities)} entities, "
                       f"reasoning: {result.reasoning_applied}, time: {result.processing_time:.2f}s")
            
            return result
            
        except Exception as e:
            result.success = False
            result.error_message = str(e)
            result.processing_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Processing failed for {ontology_id}: {e}")
            return result
    
    def get_enhanced_entity_data(self, ontology_id: str, entity_uri: str, 
                                include_reasoning: bool = True) -> Dict[str, Any]:
        """
        Get comprehensive entity data including reasoning information.
        
        Args:
            ontology_id: The ontology identifier
            entity_uri: The entity URI
            include_reasoning: Whether to include reasoning data
            
        Returns:
            Enhanced entity data dictionary
        """
        try:
            # Get base entity data
            ontology_record = self._get_ontology_record(ontology_id)
            if not ontology_record:
                return {}
            
            entity = self.db_session.query(OntologyEntity).filter_by(
                ontology_id=ontology_record.id,
                uri=entity_uri
            ).first()
            
            if not entity:
                return {}
            
            entity_data = entity.to_dict()
            
            # Add reasoning data if available and requested
            if include_reasoning and ontology_id in self.reasoning_cache:
                reasoning_data = self.reasoning_cache[ontology_id]
                entity_data['reasoning'] = self._get_entity_reasoning_data(
                    entity_uri, reasoning_data
                )
            
            # Add related entities through semantic search
            if self.embedding_model and entity.embedding:
                similar_entities = self._find_similar_entities(
                    entity.embedding, ontology_record.id, limit=5
                )
                entity_data['similar_entities'] = similar_entities
            
            return entity_data
            
        except Exception as e:
            logger.error(f"Failed to get enhanced entity data for {entity_uri}: {e}")
            return {}
    
    def search_entities_enhanced(self, query: str, ontology_id: Optional[str] = None,
                               entity_type: Optional[str] = None, 
                               include_reasoning: bool = True,
                               limit: int = 10) -> List[Dict[str, Any]]:
        """
        Enhanced semantic search with reasoning integration.
        
        Args:
            query: Search query
            ontology_id: Optional ontology filter
            entity_type: Optional entity type filter
            include_reasoning: Include reasoning data in results
            limit: Maximum results
            
        Returns:
            List of enhanced entity results
        """
        if not self.embedding_model:
            logger.warning("Embedding model not available for enhanced search")
            return []
        
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode([query])[0].tolist()
            
            # Build base query
            db_query = self.db_session.query(OntologyEntity)
            
            if ontology_id:
                ontology_record = self._get_ontology_record(ontology_id)
                if ontology_record:
                    db_query = db_query.filter_by(ontology_id=ontology_record.id)
            
            if entity_type:
                db_query = db_query.filter_by(entity_type=entity_type)
            
            # Perform vector similarity search
            # Note: This is a simplified implementation. In production, use proper pgvector queries
            entities = db_query.limit(limit * 3).all()  # Get more for filtering
            
            results = []
            for entity in entities:
                if entity.embedding:
                    # Calculate similarity (simplified)
                    similarity = self._calculate_similarity(query_embedding, entity.embedding)
                    
                    if similarity > 0.5:  # Threshold
                        entity_data = entity.to_dict()
                        entity_data['similarity_score'] = similarity
                        
                        # Add reasoning data if requested
                        if include_reasoning and ontology_id in self.reasoning_cache:
                            reasoning_data = self.reasoning_cache[ontology_id]
                            entity_data['reasoning'] = self._get_entity_reasoning_data(
                                entity.uri, reasoning_data
                            )
                        
                        results.append(entity_data)
            
            # Sort by similarity and limit
            results.sort(key=lambda x: x['similarity_score'], reverse=True)
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Enhanced search failed: {e}")
            return []
    
    def validate_ontology_enhanced(self, ontology_id: str) -> Dict[str, Any]:
        """
        Enhanced validation including consistency checking and BFO compliance.
        
        Args:
            ontology_id: The ontology identifier
            
        Returns:
            Comprehensive validation results
        """
        try:
            # Load ontology content
            rdf_content = self._load_ontology_content(ontology_id)
            rdf_graph = self._parse_with_rdflib(rdf_content, ontology_id)
            
            validation_result = {
                'ontology_id': ontology_id,
                'valid': True,
                'errors': [],
                'warnings': [],
                'suggestions': [],
                'consistency_check': None,
                'reasoning_applied': False
            }
            
            # Basic RDF validation (parsing already validates syntax)
            basic_issues = self._validate_basic_patterns(rdf_graph)
            validation_result['warnings'].extend(basic_issues)
            
            # Enhanced validation with reasoning
            if OWLREADY2_AVAILABLE and self.owlready_importer:
                reasoning_validation = self._validate_with_reasoning(rdf_content, ontology_id)
                validation_result.update(reasoning_validation)
            
            # BFO compliance check
            bfo_issues = self._check_bfo_compliance(rdf_graph)
            validation_result['warnings'].extend(bfo_issues)
            
            # Set overall validity
            validation_result['valid'] = len(validation_result['errors']) == 0
            
            return validation_result
            
        except Exception as e:
            return {
                'ontology_id': ontology_id,
                'valid': False,
                'errors': [f"Validation failed: {str(e)}"],
                'warnings': [],
                'suggestions': [],
                'consistency_check': None,
                'reasoning_applied': False
            }
    
    # Private helper methods
    
    def _initialize_embedding_model(self):
        """Initialize the sentence transformer model."""
        if not EMBEDDINGS_AVAILABLE:
            return None
        
        try:
            model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Sentence transformer model initialized")
            return model
        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            return None
    
    def _get_ontology_record(self, ontology_id: str) -> Optional[Ontology]:
        """Get ontology record from database."""
        return self.db_session.query(Ontology).filter_by(name=ontology_id).first()
    
    def _load_ontology_content(self, ontology_id: str) -> str:
        """Load ontology content from storage with database fallback."""
        try:
            # Try file storage first
            result = self.storage.retrieve(ontology_id)
            return result['content']
        except Exception as e:
            logger.warning(f"File storage failed for {ontology_id}: {e}")
            # Fallback to database
            try:
                ontology_record = self.db_session.query(Ontology).filter_by(name=ontology_id).first()
                if ontology_record and ontology_record.current_content:
                    logger.info(f"Using database content for {ontology_id}")
                    return ontology_record.current_content
                else:
                    raise ValueError(f"No content found in database for {ontology_id}")
            except Exception as db_error:
                raise ValueError(f"Failed to load ontology {ontology_id} from both file storage ({e}) and database ({db_error})")
    
    def _parse_with_rdflib(self, content: str, ontology_id: str) -> Graph:
        """Parse ontology content with RDFLib."""
        try:
            graph = Graph()
            graph.parse(data=content, format='turtle')
            logger.debug(f"Parsed {len(graph)} triples for {ontology_id}")
            return graph
        except Exception as e:
            raise ValueError(f"Failed to parse RDF content: {e}")
    
    def _apply_reasoning(self, content: str, ontology_id: str, options: ProcessingOptions) -> Dict[str, Any]:
        """Apply enhanced reasoning using Owlready2 with aggressive inference."""
        if not self.owlready_importer:
            return {}
        
        # Check cache
        cache_key = f"{ontology_id}:{hash(content)}"
        if options.cache_reasoning and cache_key in self.reasoning_cache:
            logger.debug(f"Using cached reasoning results for {ontology_id}")
            return self.reasoning_cache[cache_key]
        
        try:
            logger.info(f"Applying enhanced reasoning to {ontology_id} with {options.reasoner_type}")
            
            # Set up enhanced reasoning configuration
            enhanced_options = ProcessingOptions(
                use_reasoning=True,
                reasoner_type=options.reasoner_type,
                validate_consistency=True,
                include_inferred=True,
                extract_restrictions=True,
                generate_embeddings=options.generate_embeddings,
                cache_reasoning=options.cache_reasoning,
                force_refresh=options.force_refresh
            )
            
            # Configure the owlready importer for aggressive reasoning
            original_include_inferred = self.owlready_importer.include_inferred
            
            self.owlready_importer.include_inferred = True
            
            # Apply reasoning with the enhanced importer
            reasoning_result = self.owlready_importer._import_from_content(
                content, f"temp://{ontology_id}", ontology_id, None, None, 'turtle'
            )
            
            # Restore original settings
            self.owlready_importer.include_inferred = original_include_inferred
            
            extracted_reasoning = reasoning_result.get('reasoning_result', {})
            
            # Apply additional post-processing reasoning if we have owlready2 access
            if OWLREADY2_AVAILABLE and extracted_reasoning.get('reasoning_applied'):
                enhanced_reasoning = self._apply_additional_reasoning(content, ontology_id, options)
                extracted_reasoning.update(enhanced_reasoning)
            
            # Cache results
            if options.cache_reasoning:
                self.reasoning_cache[cache_key] = extracted_reasoning
            
            logger.info(f"Enhanced reasoning completed for {ontology_id}: "
                       f"consistent={extracted_reasoning.get('is_consistent')}, "
                       f"inferred={extracted_reasoning.get('inferred_count', 0)}")
            
            return extracted_reasoning
            
        except Exception as e:
            logger.error(f"Enhanced reasoning failed for {ontology_id}: {e}")
            return {'reasoning_applied': False, 'error': str(e)}
    
    def _apply_additional_reasoning(self, content: str, ontology_id: str, options: ProcessingOptions) -> Dict[str, Any]:
        """Apply additional comprehensive reasoning passes."""
        try:
            # Create temporary file for owlready2 processing
            temp_file = os.path.join(self.temp_dir, f"{ontology_id}_reasoning.ttl")
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Load with owlready2 for direct reasoning access
            onto = owlready2.get_ontology(f"file://{temp_file}").load()
            
            initial_count = len(list(onto.get_triples()))
            logger.debug(f"Initial triple count for {ontology_id}: {initial_count}")
            
            # Apply multiple reasoning passes with different configurations
            reasoning_results = {
                'additional_inferences': 0,
                'consistency_verified': True,
                'reasoning_passes': []
            }
            
            # Pass 1: Property hierarchy reasoning
            with onto:
                try:
                    if options.reasoner_type == 'hermit':
                        from owlready2.reasoning import sync_reasoner_hermit as sync_reasoner
                    else:
                        from owlready2.reasoning import sync_reasoner_pellet as sync_reasoner
                    
                    # Comprehensive inference configuration
                    sync_reasoner(
                        x=onto,
                        infer_property_values=True,
                        infer_data_property_values=True,
                        debug=False
                    )
                    
                    pass1_count = len(list(onto.get_triples()))
                    pass1_inferred = pass1_count - initial_count
                    reasoning_results['reasoning_passes'].append({
                        'pass': 1,
                        'type': 'property_hierarchy',
                        'inferred_count': pass1_inferred
                    })
                    
                    logger.debug(f"Pass 1 - Property hierarchy: {pass1_inferred} new inferences")
                    
                except Exception as e:
                    logger.warning(f"Reasoning pass 1 failed: {e}")
                    reasoning_results['consistency_verified'] = False
            
            # Pass 2: Class hierarchy and equivalence reasoning
            with onto:
                try:
                    # Force class hierarchy completion
                    for cls in onto.classes():
                        # Trigger parent/child relationship inference
                        list(cls.ancestors())
                        list(cls.descendants())
                    
                    # Apply reasoner again to capture hierarchy inferences
                    if options.reasoner_type == 'hermit':
                        from owlready2.reasoning import sync_reasoner_hermit as sync_reasoner
                    else:
                        from owlready2.reasoning import sync_reasoner_pellet as sync_reasoner
                    
                    sync_reasoner(
                        x=onto,
                        infer_property_values=True,
                        infer_data_property_values=True,
                        debug=False
                    )
                    
                    pass2_count = len(list(onto.get_triples()))
                    pass2_inferred = pass2_count - pass1_count
                    reasoning_results['reasoning_passes'].append({
                        'pass': 2,
                        'type': 'class_hierarchy',
                        'inferred_count': pass2_inferred
                    })
                    
                    logger.debug(f"Pass 2 - Class hierarchy: {pass2_inferred} new inferences")
                    
                except Exception as e:
                    logger.warning(f"Reasoning pass 2 failed: {e}")
                    reasoning_results['consistency_verified'] = False
            
            # Pass 3: Domain/Range reasoning for properties
            with onto:
                try:
                    # Force property domain/range inference
                    for prop in onto.properties():
                        # Access domain and range to trigger inference
                        list(prop.domain)
                        list(prop.range)
                        if hasattr(prop, 'inverse_property'):
                            list(prop.inverse_property)
                    
                    # Final reasoner pass
                    if options.reasoner_type == 'hermit':
                        from owlready2.reasoning import sync_reasoner_hermit as sync_reasoner
                    else:
                        from owlready2.reasoning import sync_reasoner_pellet as sync_reasoner
                    
                    sync_reasoner(
                        x=onto,
                        infer_property_values=True,
                        infer_data_property_values=True,
                        debug=False
                    )
                    
                    final_count = len(list(onto.get_triples()))
                    pass3_inferred = final_count - pass2_count
                    reasoning_results['reasoning_passes'].append({
                        'pass': 3,
                        'type': 'property_domain_range',
                        'inferred_count': pass3_inferred
                    })
                    
                    reasoning_results['additional_inferences'] = final_count - initial_count
                    
                    logger.debug(f"Pass 3 - Property domain/range: {pass3_inferred} new inferences")
                    logger.info(f"Total additional inferences for {ontology_id}: {reasoning_results['additional_inferences']}")
                    
                except Exception as e:
                    logger.warning(f"Reasoning pass 3 failed: {e}")
                    reasoning_results['consistency_verified'] = False
            
            # Clean up temporary file
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
            return reasoning_results
            
        except Exception as e:
            logger.error(f"Additional reasoning failed for {ontology_id}: {e}")
            return {
                'additional_inferences': 0,
                'consistency_verified': False,
                'error': str(e)
            }
    
    def _extract_enhanced_entities(self, rdf_graph: Graph, reasoning_result: Dict,
                                 ontology_record: Ontology, options: ProcessingOptions) -> List[OntologyEntity]:
        """Extract entities with enhanced metadata from reasoning."""
        entities = []
        
        # Extract classes
        for cls_uri in rdf_graph.subjects(RDF.type, OWL.Class):
            if isinstance(cls_uri, URIRef):
                entity = self._create_enhanced_entity(
                    rdf_graph, cls_uri, 'class', ontology_record.id, reasoning_result
                )
                if entity:
                    entities.append(entity)
        
        # Extract properties
        for prop_uri in rdf_graph.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(prop_uri, URIRef):
                entity = self._create_enhanced_entity(
                    rdf_graph, prop_uri, 'object_property', ontology_record.id, reasoning_result
                )
                if entity:
                    entities.append(entity)
        
        # Extract individuals
        for ind_uri in rdf_graph.subjects(RDF.type, OWL.NamedIndividual):
            if isinstance(ind_uri, URIRef):
                entity = self._create_enhanced_entity(
                    rdf_graph, ind_uri, 'individual', ontology_record.id, reasoning_result
                )
                if entity:
                    entities.append(entity)
        
        logger.debug(f"Extracted {len(entities)} enhanced entities")
        return entities
    
    def _create_enhanced_entity(self, graph: Graph, uri: URIRef, entity_type: str,
                              ontology_db_id: int, reasoning_result: Dict) -> Optional[OntologyEntity]:
        """Create an enhanced entity with reasoning metadata."""
        try:
            # Get basic properties
            label = self._get_rdf_label(graph, uri)
            comment = self._get_rdf_comment(graph, uri)
            
            # Get enhanced properties
            parent_uri = None
            if entity_type == 'class':
                parent_obj = graph.value(uri, RDFS.subClassOf)
                parent_uri = str(parent_obj) if parent_obj else None
            
            # Build properties dictionary with reasoning info
            properties = {
                'is_inferred': self._is_inferred_entity(uri, reasoning_result),
                'consistency_status': self._get_entity_consistency(uri, reasoning_result)
            }
            
            # Add reasoning-specific properties
            if reasoning_result.get('reasoning_applied'):
                properties.update({
                    'inferred_relationships': self._get_inferred_relationships(uri, reasoning_result),
                    'explanation': self._get_reasoning_explanation(uri, reasoning_result)
                })
            
            entity = OntologyEntity(
                ontology_id=ontology_db_id,
                entity_type=entity_type,
                uri=str(uri),
                label=label,
                comment=comment,
                parent_uri=parent_uri,
                properties=properties,
                created_at=datetime.utcnow()
            )
            
            return entity
            
        except Exception as e:
            logger.warning(f"Failed to create enhanced entity for {uri}: {e}")
            return None
    
    def _generate_embeddings(self, entities: List[OntologyEntity]) -> List[OntologyEntity]:
        """Generate vector embeddings for entities."""
        if not self.embedding_model:
            return entities
        
        try:
            texts = []
            for entity in entities:
                text_parts = []
                if entity.label:
                    text_parts.append(entity.label)
                if entity.comment:
                    text_parts.append(entity.comment)
                text_parts.append(entity.entity_type)
                texts.append(" ".join(text_parts))
            
            embeddings = self.embedding_model.encode(texts)
            
            for entity, embedding in zip(entities, embeddings):
                entity.embedding = embedding.tolist()
            
            logger.debug(f"Generated embeddings for {len(entities)} entities")
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
        
        return entities
    
    def _store_entities(self, entities: List[OntologyEntity], ontology_db_id: int, 
                       force_refresh: bool) -> List[OntologyEntity]:
        """Store entities in database."""
        try:
            # Clear existing if force refresh
            if force_refresh:
                existing = self.db_session.query(OntologyEntity).filter_by(ontology_id=ontology_db_id).all()
                for entity in existing:
                    self.db_session.delete(entity)
                self.db_session.commit()
            
            # Add new entities
            for entity in entities:
                self.db_session.add(entity)
            
            self.db_session.commit()
            logger.debug(f"Stored {len(entities)} entities in database")
            
            return entities
            
        except Exception as e:
            self.db_session.rollback()
            logger.error(f"Failed to store entities: {e}")
            return []
    
    def _generate_visualization_data(self, entities: List[OntologyEntity], 
                                   reasoning_result: Dict, ontology_id: str) -> Dict[str, Any]:
        """Generate visualization data optimized for Cytoscape.js."""
        if not self.owlready_importer:
            return {}
        
        try:
            return self.owlready_importer.get_visualization_data(ontology_id)
        except Exception as e:
            logger.error(f"Failed to generate visualization data: {e}")
            return {}
    
    def _generate_metadata(self, ontology_record: Ontology, rdf_graph: Graph,
                         reasoning_result: Dict, entity_count: int) -> Dict[str, Any]:
        """Generate enhanced metadata."""
        return {
            'ontology_id': ontology_record.ontology_id,
            'name': ontology_record.name,
            'description': ontology_record.description,
            'triple_count': len(rdf_graph),
            'entity_count': entity_count,
            'class_count': len(list(rdf_graph.subjects(RDF.type, OWL.Class))),
            'property_count': len(list(rdf_graph.subjects(RDF.type, OWL.ObjectProperty))),
            'reasoning_applied': reasoning_result.get('reasoning_applied', False),
            'consistency_check': reasoning_result.get('is_consistent'),
            'inferred_count': reasoning_result.get('inferred_count', 0),
            'last_processed': datetime.utcnow().isoformat()
        }
    
    # Additional helper methods for reasoning integration
    
    def _get_rdf_label(self, graph: Graph, uri: URIRef) -> Optional[str]:
        """Get label from RDF graph."""
        label_obj = graph.value(uri, RDFS.label)
        return str(label_obj) if label_obj else None
    
    def _get_rdf_comment(self, graph: Graph, uri: URIRef) -> Optional[str]:
        """Get comment from RDF graph."""
        comment_obj = graph.value(uri, RDFS.comment)
        return str(comment_obj) if comment_obj else None
    
    def _is_inferred_entity(self, uri: URIRef, reasoning_result: Dict) -> bool:
        """Check if entity was inferred by reasoning."""
        inferred_entities = reasoning_result.get('inferred_entities', [])
        return str(uri) in inferred_entities
    
    def _get_entity_consistency(self, uri: URIRef, reasoning_result: Dict) -> str:
        """Get consistency status of entity."""
        if not reasoning_result.get('reasoning_applied'):
            return 'unknown'
        return 'consistent' if reasoning_result.get('is_consistent', True) else 'inconsistent'
    
    def _get_inferred_relationships(self, uri: URIRef, reasoning_result: Dict) -> List[Dict[str, str]]:
        """Get inferred relationships for entity."""
        inferred_rels = reasoning_result.get('inferred_relationships', [])
        return [rel for rel in inferred_rels if rel.get('subject') == str(uri)]
    
    def _get_reasoning_explanation(self, uri: URIRef, reasoning_result: Dict) -> Optional[str]:
        """Get reasoning explanation for entity."""
        explanations = reasoning_result.get('explanations', {})
        return explanations.get(str(uri))
    
    def _get_entity_reasoning_data(self, entity_uri: str, reasoning_data: Dict) -> Dict[str, Any]:
        """Extract reasoning data for specific entity."""
        return {
            'is_inferred': entity_uri in reasoning_data.get('inferred_entities', []),
            'inferred_relationships': [
                rel for rel in reasoning_data.get('inferred_relationships', [])
                if rel.get('subject') == entity_uri
            ],
            'explanation': reasoning_data.get('explanations', {}).get(entity_uri)
        }
    
    def _find_similar_entities(self, embedding: List[float], ontology_db_id: int, 
                             limit: int = 5) -> List[Dict[str, Any]]:
        """Find similar entities using vector similarity."""
        # Simplified similarity search - in production, use proper pgvector queries
        try:
            entities = self.db_session.query(OntologyEntity).filter_by(ontology_id=ontology_db_id).all()
            similar = []
            
            for entity in entities:
                if entity.embedding:
                    similarity = self._calculate_similarity(embedding, entity.embedding)
                    if similarity > 0.7:  # Similarity threshold
                        similar.append({
                            'uri': entity.uri,
                            'label': entity.label,
                            'similarity': similarity
                        })
            
            return sorted(similar, key=lambda x: x['similarity'], reverse=True)[:limit]
            
        except Exception as e:
            logger.error(f"Similar entity search failed: {e}")
            return []
    
    def _calculate_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """Calculate cosine similarity between embeddings."""
        try:
            import numpy as np
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return dot_product / (norm1 * norm2)
            
        except Exception:
            return 0.0
    
    def _validate_basic_patterns(self, graph: Graph) -> List[str]:
        """Basic ontology pattern validation."""
        warnings = []
        
        # Check for classes without labels
        for cls in graph.subjects(RDF.type, OWL.Class):
            if not graph.value(cls, RDFS.label):
                warnings.append(f"Class {cls} missing rdfs:label")
        
        # Check for classes without comments
        for cls in graph.subjects(RDF.type, OWL.Class):
            if not graph.value(cls, RDFS.comment):
                warnings.append(f"Class {cls} missing rdfs:comment")
        
        return warnings
    
    def _validate_with_reasoning(self, content: str, ontology_id: str) -> Dict[str, Any]:
        """Enhanced validation using reasoning."""
        if not self.owlready_importer:
            return {
                'reasoning_applied': False,
                'consistency_check': None,
                'errors': [],
                'warnings': [],
                'suggestions': []
            }
        
        try:
            # Apply reasoning and check for consistency
            reasoning_result = self._apply_reasoning(content, ontology_id, ProcessingOptions())
            
            validation_result = {
                'reasoning_applied': True,
                'consistency_check': reasoning_result.get('is_consistent', True),
                'errors': [],
                'warnings': [],
                'suggestions': []
            }
            
            # Add consistency-based errors
            if not reasoning_result.get('is_consistent', True):
                validation_result['errors'].append("Ontology contains logical inconsistencies")
            
            # Add suggestions based on inferred relationships
            inferred_count = reasoning_result.get('inferred_count', 0)
            if inferred_count > 0:
                validation_result['suggestions'].append(
                    f"Consider making {inferred_count} inferred relationships explicit"
                )
            
            return validation_result
            
        except Exception as e:
            return {
                'reasoning_applied': False,
                'consistency_check': None,
                'errors': [f"Reasoning validation failed: {str(e)}"],
                'warnings': [],
                'suggestions': []
            }
    
    def _check_bfo_compliance(self, graph: Graph) -> List[str]:
        """Check Basic Formal Ontology compliance patterns."""
        warnings = []
        
        # Check if classes properly inherit from BFO
        for cls in graph.subjects(RDF.type, OWL.Class):
            if isinstance(cls, URIRef):
                # Check if it has a BFO superclass
                has_bfo_parent = False
                for parent in graph.objects(cls, RDFS.subClassOf):
                    if isinstance(parent, URIRef) and "purl.obolibrary.org/obo/BFO" in str(parent):
                        has_bfo_parent = True
                        break
                
                if not has_bfo_parent and "purl.obolibrary.org/obo/BFO" not in str(cls):
                    warnings.append(f"Class {cls} does not inherit from BFO")
        
        return warnings
    
    def __del__(self):
        """Cleanup temporary files."""
        try:
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception:
            pass
