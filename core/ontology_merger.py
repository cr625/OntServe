"""
OntologyMergerService for combining base ontologies with their derived children.

Provides functionality to merge RDF graphs from parent and child ontologies
while maintaining proper provenance and namespace management.
"""

import logging
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

import rdflib
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDF, RDFS, OWL, XSD, DCTERMS
from sqlalchemy import select

from web.models import Ontology, OntologyVersion, db


class OntologyMergerService:
    """
    Service for merging base ontologies with their derived children.
    
    Handles:
    - RDF graph merging
    - Namespace management
    - Conflict resolution
    - Provenance tracking
    - Version computation for composite ontologies
    """
    
    def __init__(self, logger=None):
        """Initialize the merger service."""
        self.logger = logger or logging.getLogger(__name__)
        
        # Define namespaces
        self.PROETHICA = Namespace("http://proethica.org/ontology/")
        self.PROV = Namespace("http://www.w3.org/ns/prov#")
        
    def merge_ontology_with_children(self, base_ontology: Ontology, 
                                   include_drafts: bool = False) -> Tuple[str, Dict[str, Any]]:
        """
        Merge a base ontology with all its derived children.
        
        Args:
            base_ontology: The base/parent ontology
            include_drafts: Whether to include draft versions of children
            
        Returns:
            Tuple of (merged_rdf_content, metadata)
        """
        self.logger.info(f"Starting merge for ontology: {base_ontology.name}")
        
        # Get base ontology content
        base_content = base_ontology.current_content
        if not base_content:
            raise ValueError(f"No content found for base ontology: {base_ontology.name}")
        
        # Create main graph and parse base ontology
        merged_graph = Graph()
        
        # Bind common namespaces
        merged_graph.bind("owl", OWL)
        merged_graph.bind("rdfs", RDFS)
        merged_graph.bind("rdf", RDF)
        merged_graph.bind("xsd", XSD)
        merged_graph.bind("dcterms", DCTERMS)
        merged_graph.bind("proethica", self.PROETHICA)
        merged_graph.bind("prov", self.PROV)
        
        try:
            merged_graph.parse(data=base_content, format='turtle')
            self.logger.info(f"Parsed base ontology: {len(merged_graph)} triples")
        except Exception as e:
            self.logger.error(f"Failed to parse base ontology: {e}")
            raise ValueError(f"Invalid RDF content in base ontology: {e}")
        
        # Get all derived children
        children = self._get_mergeable_children(base_ontology, include_drafts)
        merged_children = []
        
        # Merge each child ontology
        for child in children:
            try:
                child_content = child.current_content
                if not child_content:
                    self.logger.warning(f"Skipping child {child.name}: no content")
                    continue
                
                # Parse child RDF
                child_graph = Graph()
                child_graph.parse(data=child_content, format='turtle')
                
                # Merge child graph into main graph
                for triple in child_graph:
                    merged_graph.add(triple)
                
                merged_children.append({
                    'name': child.name,
                    'id': child.id,
                    'version': child.current_version.version_tag if child.current_version else 'unknown',
                    'triple_count': len(child_graph),
                    'ontology_type': child.ontology_type
                })
                
                self.logger.info(f"Merged child {child.name}: +{len(child_graph)} triples")
                
            except Exception as e:
                self.logger.error(f"Failed to merge child {child.name}: {e}")
                # Continue with other children rather than failing completely
                continue
        
        # Add provenance information to the merged graph
        self._add_provenance_info(merged_graph, base_ontology, merged_children)
        
        # Generate composite version identifier
        composite_version = self._generate_composite_version(base_ontology, merged_children)
        
        # Serialize merged graph
        try:
            merged_content = merged_graph.serialize(format='turtle')
            self.logger.info(f"Generated merged ontology: {len(merged_graph)} total triples")
        except Exception as e:
            self.logger.error(f"Failed to serialize merged graph: {e}")
            raise
        
        # Prepare metadata
        metadata = {
            'base_ontology': {
                'name': base_ontology.name,
                'id': base_ontology.id,
                'version': base_ontology.current_version.version_tag if base_ontology.current_version else 'unknown'
            },
            'merged_children': merged_children,
            'composite_version': composite_version,
            'total_triples': len(merged_graph),
            'merge_timestamp': datetime.utcnow().isoformat(),
            'include_drafts': include_drafts
        }
        
        return merged_content, metadata
    
    def _get_mergeable_children(self, base_ontology: Ontology, 
                              include_drafts: bool = False) -> List[Ontology]:
        """Get all child ontologies that should be included in the merge."""
        children = base_ontology.children
        
        if not include_drafts:
            # Filter to only include children with published versions
            mergeable_children = []
            for child in children:
                stmt = select(OntologyVersion).where(
                    OntologyVersion.ontology_id == child.id,
                    OntologyVersion.is_current == True,
                    OntologyVersion.is_draft == False
                )
                published_version = db.session.execute(stmt).scalar_one_or_none()

                if published_version:
                    mergeable_children.append(child)
                else:
                    self.logger.info(f"Skipping child {child.name}: no published version")

            return mergeable_children
        
        return children
    
    def _add_provenance_info(self, graph: Graph, base_ontology: Ontology, 
                           merged_children: List[Dict[str, Any]]):
        """Add provenance information to the merged graph."""
        # Create a provenance node for this merge operation
        merge_activity = BNode()
        graph.add((merge_activity, RDF.type, self.PROV.Activity))
        graph.add((merge_activity, RDFS.label, Literal("Ontology Merge Operation")))
        graph.add((merge_activity, self.PROV.startedAtTime, 
                  Literal(datetime.utcnow().isoformat(), datatype=XSD.dateTime)))
        
        # Link base ontology
        base_entity = URIRef(base_ontology.base_uri)
        graph.add((base_entity, self.PROV.wasInfluencedBy, merge_activity))
        graph.add((base_entity, self.PROETHICA.mergeRole, Literal("base")))
        
        # Link child ontologies
        for child_info in merged_children:
            child_uri = URIRef(f"{base_ontology.base_uri}/derived/{child_info['name']}")
            graph.add((child_uri, self.PROV.wasInfluencedBy, merge_activity))
            graph.add((child_uri, self.PROETHICA.mergeRole, Literal("derived")))
            graph.add((child_uri, self.PROETHICA.derivedFrom, base_entity))
    
    def _generate_composite_version(self, base_ontology: Ontology, 
                                  merged_children: List[Dict[str, Any]]) -> str:
        """Generate a version identifier for the composite ontology."""
        base_version = base_ontology.current_version.version_tag if base_ontology.current_version else "unknown"
        
        # Create hash from child versions
        child_versions = sorted([child['version'] for child in merged_children])
        child_hash = hashlib.md5('|'.join(child_versions).encode()).hexdigest()[:8]
        
        return f"{base_version}-composite-{len(merged_children)}children-{child_hash}"
    
    def get_ontology_hierarchy(self, ontology: Ontology) -> Dict[str, Any]:
        """Get the full hierarchy information for an ontology."""
        hierarchy = {
            'ontology': ontology.to_dict(),
            'parent': ontology.parent.to_dict() if ontology.parent else None,
            'children': [child.to_dict() for child in ontology.children],
            'ancestors': [],
            'descendants': []
        }
        
        # Get all ancestors
        current = ontology.parent
        while current:
            hierarchy['ancestors'].append(current.to_dict())
            current = current.parent
        
        # Get all descendants
        descendants = ontology.get_all_descendants()
        hierarchy['descendants'] = [desc.to_dict() for desc in descendants]
        
        return hierarchy
    
    def validate_merge_compatibility(self, base_ontology: Ontology) -> Dict[str, Any]:
        """
        Validate that a base ontology and its children can be safely merged.
        
        Returns validation results with any warnings or errors.
        """
        validation_result = {
            'is_valid': True,
            'warnings': [],
            'errors': [],
            'base_ontology': base_ontology.name,
            'children_count': len(base_ontology.children)
        }
        
        # Check base ontology
        if not base_ontology.current_content:
            validation_result['errors'].append(f"Base ontology {base_ontology.name} has no content")
            validation_result['is_valid'] = False
        
        # Validate each child
        for child in base_ontology.children:
            if not child.current_content:
                validation_result['warnings'].append(f"Child {child.name} has no content - will be skipped")
                continue
            
            # Check for namespace conflicts (simplified check)
            if child.base_uri == base_ontology.base_uri:
                validation_result['warnings'].append(
                    f"Child {child.name} has same base URI as parent - may cause conflicts"
                )
        
        return validation_result
    
    def clear_merge_cache(self):
        """Clear any cached merge results (placeholder for future caching)."""
        # Placeholder for future implementation if we add caching
        self.logger.info("Merge cache cleared")
