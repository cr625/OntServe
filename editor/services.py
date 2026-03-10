"""
OntServe Editor Services

Core services for ontology editing, entity extraction, validation, and semantic search.
Adapted from proethica's Neo4j-based approach to use OntServe's pgvector semantic search.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

import rdflib
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL
from sentence_transformers import SentenceTransformer

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from storage.base import StorageBackend


# Configure logging
logger = logging.getLogger(__name__)

# Define common namespaces
BFO = Namespace("http://purl.obolibrary.org/obo/")
PROV = Namespace("http://www.w3.org/ns/prov#")
PROETHICA = Namespace("http://proethica.org/ontology/engineering-ethics#")


class OntologyEntityService:
    """
    Service for extracting entities from ontologies and managing semantic search.
    
    Replaces proethica's Neo4j-based approach with pgvector semantic search.
    """
    
    def __init__(self, storage_backend: StorageBackend, db_session=None):
        """
        Initialize the entity service.
        
        Args:
            storage_backend: File storage backend for retrieving TTL content
            db_session: Database session for storing entities (defaults to app context)
        """
        self.storage = storage_backend
        self.db_session = db_session or db.session
        
        # Initialize sentence transformer for embeddings
        self.embedding_available = False
        try:
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            self.embedding_available = True
        except Exception as e:
            logger.warning("Embedding model unavailable: %s. Semantic search disabled.", e)
            self.embedding_model = None
    
    def extract_and_store_entities(self, ontology_id: str, force_refresh: bool = False) -> List[OntologyEntity]:
        """
        Extract entities from an ontology and store them in the database.
        
        Args:
            ontology_id: The ontology identifier
            force_refresh: Whether to force re-extraction even if entities exist
            
        Returns:
            List of extracted entities
        """
        # Get the ontology record
        ontology = self.db_session.query(Ontology).filter_by(ontology_id=ontology_id).first()
        if not ontology:
            raise ValueError(f"Ontology {ontology_id} not found")
        
        # Check if entities already exist
        existing_entities = self.db_session.query(OntologyEntity).filter_by(ontology_id=ontology.id).all()
        if existing_entities and not force_refresh:
            logger.info(f"Using existing {len(existing_entities)} entities for {ontology_id}")
            return existing_entities
        
        # Clear existing entities if force refresh
        if force_refresh and existing_entities:
            for entity in existing_entities:
                self.db_session.delete(entity)
            self.db_session.commit()
        
        # Get TTL content from storage
        try:
            result = self.storage.retrieve(ontology_id)
            ttl_content = result['content']
        except Exception as e:
            logger.error(f"Failed to retrieve ontology {ontology_id}: {e}")
            raise
        
        # Parse the TTL content
        graph = Graph()
        try:
            graph.parse(data=ttl_content, format='turtle')
        except Exception as e:
            logger.error(f"Failed to parse TTL content for {ontology_id}: {e}")
            raise
        
        # Extract entities
        entities = []
        
        # Extract classes
        class_entities = self._extract_classes(graph, ontology.id)
        entities.extend(class_entities)
        
        # Extract properties
        property_entities = self._extract_properties(graph, ontology.id)
        entities.extend(property_entities)
        
        # Extract individuals
        individual_entities = self._extract_individuals(graph, ontology.id)
        entities.extend(individual_entities)
        
        # Generate embeddings and save entities
        entities_with_embeddings = self._generate_embeddings(entities)
        
        # Bulk insert entities
        for entity in entities_with_embeddings:
            self.db_session.add(entity)
        
        try:
            self.db_session.commit()
            logger.info(f"Successfully extracted and stored {len(entities)} entities for {ontology_id}")
        except Exception as e:
            self.db_session.rollback()
            logger.error(f"Failed to store entities for {ontology_id}: {e}")
            raise
        
        return entities_with_embeddings
    
    def _extract_classes(self, graph: Graph, ontology_db_id: int) -> List[OntologyEntity]:
        """Extract class entities from the RDF graph."""
        entities = []
        
        # Find all classes (both explicit and implicit)
        classes = set()
        
        # Explicit OWL classes
        for subj in graph.subjects(RDF.type, OWL.Class):
            classes.add(subj)
        
        # RDFS classes
        for subj in graph.subjects(RDF.type, RDFS.Class):
            classes.add(subj)
        
        # Classes mentioned in subclass relationships
        for subj, pred, obj in graph.triples((None, RDFS.subClassOf, None)):
            classes.add(subj)
            if isinstance(obj, URIRef):
                classes.add(obj)
        
        for class_uri in classes:
            if isinstance(class_uri, URIRef):
                entity = self._create_entity_from_uri(
                    graph, class_uri, 'class', ontology_db_id
                )
                if entity:
                    entities.append(entity)
        
        return entities
    
    def _extract_properties(self, graph: Graph, ontology_db_id: int) -> List[OntologyEntity]:
        """Extract property entities from the RDF graph."""
        entities = []
        
        # Find all properties
        properties = set()
        
        # Object properties
        for subj in graph.subjects(RDF.type, OWL.ObjectProperty):
            properties.add(subj)
        
        # Data properties
        for subj in graph.subjects(RDF.type, OWL.DatatypeProperty):
            properties.add(subj)
        
        # Annotation properties
        for subj in graph.subjects(RDF.type, OWL.AnnotationProperty):
            properties.add(subj)
        
        # Properties mentioned in domain/range relationships
        for subj, pred, obj in graph.triples((None, RDFS.domain, None)):
            properties.add(subj)
        for subj, pred, obj in graph.triples((None, RDFS.range, None)):
            properties.add(subj)
        
        for prop_uri in properties:
            if isinstance(prop_uri, URIRef):
                entity = self._create_entity_from_uri(
                    graph, prop_uri, 'property', ontology_db_id
                )
                if entity:
                    entities.append(entity)
        
        return entities
    
    def _extract_individuals(self, graph: Graph, ontology_db_id: int) -> List[OntologyEntity]:
        """Extract individual entities from the RDF graph."""
        entities = []
        
        # Find all individuals
        individuals = set()
        
        # Named individuals
        for subj in graph.subjects(RDF.type, OWL.NamedIndividual):
            individuals.add(subj)
        
        # Individuals with class types (but not classes themselves)
        for subj, pred, obj in graph.triples((None, RDF.type, None)):
            if isinstance(subj, URIRef) and isinstance(obj, URIRef):
                # Check if the object is a class
                if (obj, RDF.type, OWL.Class) in graph or (obj, RDF.type, RDFS.Class) in graph:
                    individuals.add(subj)
        
        for individual_uri in individuals:
            if isinstance(individual_uri, URIRef):
                entity = self._create_entity_from_uri(
                    graph, individual_uri, 'individual', ontology_db_id
                )
                if entity:
                    entities.append(entity)
        
        return entities
    
    def _create_entity_from_uri(self, graph: Graph, uri: URIRef, entity_type: str, ontology_db_id: int) -> Optional[OntologyEntity]:
        """Create an OntologyEntity from a URI in the graph."""
        try:
            # Get label
            label = None
            for label_pred in [RDFS.label, URIRef("http://www.w3.org/2004/02/skos/core#prefLabel")]:
                label_obj = graph.value(uri, label_pred)
                if label_obj:
                    label = str(label_obj)
                    break
            
            # If no label, use the fragment or last part of URI
            if not label:
                label = uri.fragment if uri.fragment else str(uri).split('/')[-1].split('#')[-1]
            
            # Get comment/description
            comment = None
            for comment_pred in [RDFS.comment, URIRef("http://purl.org/dc/terms/description")]:
                comment_obj = graph.value(uri, comment_pred)
                if comment_obj:
                    comment = str(comment_obj)
                    break
            
            # Get parent (subclass/subproperty relationships)
            parent_uri = None
            if entity_type == 'class':
                parent_obj = graph.value(uri, RDFS.subClassOf)
                if parent_obj and isinstance(parent_obj, URIRef):
                    parent_uri = str(parent_obj)
            elif entity_type == 'property':
                parent_obj = graph.value(uri, RDFS.subPropertyOf)
                if parent_obj and isinstance(parent_obj, URIRef):
                    parent_uri = str(parent_obj)
            
            # Get domain and range for properties
            domain = None
            range_val = None
            if entity_type == 'property':
                domain_obj = next((obj for obj in graph.objects(uri, RDFS.domain) if isinstance(obj, URIRef)), None)
                if domain_obj:
                    domain = str(domain_obj)

                range_obj = next((obj for obj in graph.objects(uri, RDFS.range) if isinstance(obj, URIRef)), None)
                if range_obj:
                    range_val = str(range_obj)
            
            # Get additional properties for individuals
            properties = None
            if entity_type == 'individual':
                props = {}
                for pred, obj in graph.predicate_objects(uri):
                    if pred not in [RDF.type, RDFS.label, RDFS.comment]:
                        pred_str = str(pred)
                        obj_str = str(obj)
                        if pred_str not in props:
                            props[pred_str] = []
                        props[pred_str].append(obj_str)
                if props:
                    properties = props
            
            # Determine specific entity type based on URI patterns and context
            specific_type = self._determine_specific_entity_type(uri, entity_type, graph)
            
            # Create entity
            entity = OntologyEntity(
                ontology_id=ontology_db_id,
                entity_type=specific_type,
                uri=str(uri),
                label=label,
                comment=comment,
                parent_uri=parent_uri,
                domain=domain,
                range=range_val,
                properties=properties,
                created_at=datetime.now(timezone.utc)
            )
            
            return entity
            
        except Exception as e:
            logger.warning(f"Failed to create entity for {uri}: {e}")
            return None
    
    def _determine_specific_entity_type(self, uri: URIRef, base_type: str, graph: Graph) -> str:
        """
        Determine the specific entity type based on URI patterns and context.
        Maps to proethica's entity types: role, condition, resource, action, event, capability.
        """
        uri_str = str(uri).lower()
        label = graph.value(uri, RDFS.label)
        label_str = str(label).lower() if label else ""
        
        # For BFO classes, return the base type
        if "purl.obolibrary.org/obo/bfo" in uri_str:
            return base_type
        
        # For PROV-O, return the base type
        if "w3.org/ns/prov" in uri_str:
            return base_type
        
        # For proethica-specific patterns, try to map to specific types
        if base_type == 'class':
            # Role patterns
            if 'role' in uri_str or 'role' in label_str:
                return 'role'
            
            # Condition patterns
            if any(term in uri_str or term in label_str for term in ['condition', 'constraint', 'requirement']):
                return 'condition'
            
            # Resource patterns
            if any(term in uri_str or term in label_str for term in ['resource', 'material', 'equipment', 'tool']):
                return 'resource'
            
            # Action patterns
            if any(term in uri_str or term in label_str for term in ['action', 'activity', 'task', 'process']):
                return 'action'
            
            # Event patterns
            if any(term in uri_str or term in label_str for term in ['event', 'occurrence', 'incident']):
                return 'event'
            
            # Capability patterns
            if any(term in uri_str or term in label_str for term in ['capability', 'ability', 'skill', 'competence']):
                return 'capability'
        
        # Default to base type
        return base_type
    
    def _generate_embeddings(self, entities: List[OntologyEntity]) -> List[OntologyEntity]:
        """Generate vector embeddings for semantic search."""
        if not self.embedding_model:
            logger.warning("No embedding model available, skipping embedding generation")
            return entities
        
        try:
            # Prepare texts for embedding
            texts = []
            for entity in entities:
                text_parts = []
                if entity.label:
                    text_parts.append(entity.label)
                if entity.comment:
                    text_parts.append(entity.comment)
                if entity.entity_type:
                    text_parts.append(entity.entity_type)
                
                text = " ".join(text_parts) if text_parts else entity.uri
                texts.append(text)
            
            # Generate embeddings
            embeddings = self.embedding_model.encode(texts)
            
            # Assign embeddings to entities
            for entity, embedding in zip(entities, embeddings):
                entity.embedding = embedding.tolist()
            
            logger.info(f"Generated embeddings for {len(entities)} entities")
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
        
        return entities
    
    def search_similar_entities(self, query: str, ontology_id: Optional[str] = None, 
                               entity_type: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for similar entities using semantic search.
        
        Args:
            query: Search query text
            ontology_id: Optional ontology to filter by
            entity_type: Optional entity type to filter by
            limit: Maximum number of results
            
        Returns:
            List of entity dictionaries with similarity scores
        """
        if not self.embedding_model:
            logger.debug("Semantic search unavailable (embedding model not loaded)")
            return []
        
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode([query])[0].tolist()
            
            # Build query
            db_query = self.db_session.query(OntologyEntity)
            
            if ontology_id:
                ontology = self.db_session.query(Ontology).filter_by(ontology_id=ontology_id).first()
                if ontology:
                    db_query = db_query.filter_by(ontology_id=ontology.id)
            
            if entity_type:
                db_query = db_query.filter_by(entity_type=entity_type)
            
            # Perform semantic search using pgvector
            results = OntologyEntity.search_similar(
                query_embedding, 
                limit=limit, 
                entity_type=entity_type,
                ontology_id=ontology.id if ontology_id else None
            )
            
            # Convert to dictionaries
            result_dicts = []
            for entity in results:
                entity_dict = entity.to_dict()
                # Calculate similarity score (cosine similarity)
                # Note: This is a simplified calculation
                entity_dict['similarity_score'] = 0.8  # Placeholder
                result_dicts.append(entity_dict)
            
            return result_dicts
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    def get_entity_hierarchy(self, ontology_id: str, entity_type: str = 'class') -> Dict[str, Any]:
        """
        Build hierarchical structure for entities in an ontology.
        
        Args:
            ontology_id: The ontology identifier
            entity_type: Type of entities to include in hierarchy
            
        Returns:
            Hierarchical structure as nested dictionaries
        """
        # Get ontology
        ontology = self.db_session.query(Ontology).filter_by(ontology_id=ontology_id).first()
        if not ontology:
            raise ValueError(f"Ontology {ontology_id} not found")
        
        # Get entities
        entities = self.db_session.query(OntologyEntity).filter_by(
            ontology_id=ontology.id,
            entity_type=entity_type
        ).all()
        
        # Build hierarchy using utils
        from .utils import HierarchyBuilder
        hierarchy_builder = HierarchyBuilder()
        
        return hierarchy_builder.build_hierarchy(entities, ontology)


class OntologyValidationService:
    """
    Service for validating ontologies against BFO and other standards.
    """

    def __init__(self, storage_backend: StorageBackend):
        """
        Initialize the validation service.

        Args:
            storage_backend: Storage backend for accessing foundation ontologies
        """
        self.storage = storage_backend
        # Use lazy loading to avoid accessing db.session before app context is ready
        self._foundation_loaded = False
        self.bfo_graph = None
        self.prov_graph = None
        self.intermediate_graph = None

    def _ensure_foundation_ontologies_loaded(self):
        """Lazy load foundation ontologies for validation from database.

        Called on first use to ensure Flask app context is available.
        """
        if self._foundation_loaded:
            return

        self._foundation_loaded = True

        try:
            from sqlalchemy import select
            from flask import current_app

            # Verify we have an app context
            if not current_app:
                logger.debug("No Flask app context available, skipping foundation ontology loading")
                return

            # Load BFO from database
            bfo_ont = db.session.execute(
                select(Ontology).where(Ontology.name == 'bfo')
            ).scalar_one_or_none()

            if bfo_ont and bfo_ont.current_content:
                self.bfo_graph = Graph()
                self.bfo_graph.parse(data=bfo_ont.current_content, format='turtle')
                logger.info("Loaded BFO for validation")
            else:
                logger.debug("BFO not found in database")

            # Load PROV-O from database
            prov_ont = db.session.execute(
                select(Ontology).where(Ontology.name == 'prov-o')
            ).scalar_one_or_none()

            if prov_ont and prov_ont.current_content:
                self.prov_graph = Graph()
                self.prov_graph.parse(data=prov_ont.current_content, format='turtle')
                logger.info("Loaded PROV-O for validation")
            else:
                logger.debug("PROV-O not found in database")

            # Load proethica intermediate from database
            intermediate_ont = db.session.execute(
                select(Ontology).where(Ontology.name == 'proethica-intermediate')
            ).scalar_one_or_none()

            if intermediate_ont and intermediate_ont.current_content:
                self.intermediate_graph = Graph()
                self.intermediate_graph.parse(data=intermediate_ont.current_content, format='turtle')
                logger.info("Loaded proethica-intermediate for validation")
            else:
                logger.debug("proethica-intermediate not found in database")

            # Log summary
            loaded = []
            if self.bfo_graph: loaded.append('BFO')
            if self.prov_graph: loaded.append('PROV-O')
            if self.intermediate_graph: loaded.append('proethica-intermediate')

            if loaded:
                logger.info(f"Validation service initialized with: {', '.join(loaded)}")
            else:
                logger.info("Validation service running without foundation ontology checks")

        except RuntimeError as e:
            # RuntimeError is raised when accessing current_app outside app context
            if "Working outside of application context" in str(e):
                logger.debug("Foundation ontologies will be loaded on first validation request")
            else:
                logger.warning(f"Error loading foundation ontologies: {e}")
                logger.info("Validation service will run without foundation ontology checks")
        except Exception as e:
            logger.warning(f"Error loading foundation ontologies: {e}")
            logger.info("Validation service will run without foundation ontology checks")
    
    def validate_ontology(self, ttl_content: str) -> Dict[str, Any]:
        """
        Validate an ontology against BFO and other standards.

        Args:
            ttl_content: The TTL content to validate

        Returns:
            Validation result with errors and warnings
        """
        # Ensure foundation ontologies are loaded (lazy loading)
        self._ensure_foundation_ontologies_loaded()

        errors = []
        warnings = []

        try:
            # Parse the ontology
            graph = Graph()
            graph.parse(data=ttl_content, format='turtle')

            # Basic syntax validation (already done by parsing)

            # BFO compliance checks
            if self.bfo_graph:
                bfo_warnings = self._check_bfo_compliance(graph)
                warnings.extend(bfo_warnings)
            
            # Check for common ontology patterns
            pattern_warnings = self._check_ontology_patterns(graph)
            warnings.extend(pattern_warnings)
            
            # Check for consistency
            consistency_errors = self._check_consistency(graph)
            errors.extend(consistency_errors)
            
        except Exception as e:
            errors.append(f"Failed to parse ontology: {str(e)}")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'summary': {
                'error_count': len(errors),
                'warning_count': len(warnings)
            }
        }
    
    def _check_bfo_compliance(self, graph: Graph) -> List[str]:
        """Check BFO compliance patterns."""
        warnings = []
        
        # Check if classes properly inherit from BFO
        for subj in graph.subjects(RDF.type, OWL.Class):
            if isinstance(subj, URIRef):
                # Check if it has a BFO superclass
                has_bfo_parent = False
                for obj in graph.objects(subj, RDFS.subClassOf):
                    if isinstance(obj, URIRef) and "purl.obolibrary.org/obo/BFO" in str(obj):
                        has_bfo_parent = True
                        break
                
                if not has_bfo_parent and "purl.obolibrary.org/obo/BFO" not in str(subj):
                    warnings.append(f"Class {subj} does not inherit from BFO")
        
        return warnings
    
    def _check_ontology_patterns(self, graph: Graph) -> List[str]:
        """Check for common ontology patterns and best practices."""
        warnings = []
        
        # Check for missing labels
        for subj in graph.subjects(RDF.type, OWL.Class):
            if not graph.value(subj, RDFS.label):
                warnings.append(f"Class {subj} missing rdfs:label")
        
        # Check for missing comments
        for subj in graph.subjects(RDF.type, OWL.Class):
            if not graph.value(subj, RDFS.comment):
                warnings.append(f"Class {subj} missing rdfs:comment")
        
        return warnings
    
    def _check_consistency(self, graph: Graph) -> List[str]:
        """Check for logical consistency issues."""
        errors = []
        
        # Check for circular subclass relationships
        # This is a simplified check - a full reasoner would be better
        for subj in graph.subjects(RDFS.subClassOf, None):
            if self._has_circular_subclass(graph, subj, subj, set()):
                errors.append(f"Circular subclass relationship detected involving {subj}")
        
        return errors
    
    def _has_circular_subclass(self, graph: Graph, current: URIRef, target: URIRef, visited: set) -> bool:
        """Check for circular subclass relationships."""
        if current in visited:
            return current == target
        
        visited.add(current)
        
        for parent in graph.objects(current, RDFS.subClassOf):
            if isinstance(parent, URIRef):
                if parent == target:
                    return True
                if self._has_circular_subclass(graph, parent, target, visited.copy()):
                    return True
        
        return False
