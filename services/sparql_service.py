"""
SPARQL Service for OntServe

Provides SPARQL query execution over loaded ontologies using RDFLib.
Supports querying ProEthica ontologies including cases, core concepts, and domain-specific knowledge.
"""

import os
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import json

from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, SKOS, DCTERMS

logger = logging.getLogger(__name__)

# Define ProEthica namespaces
PROETHICA_CORE = Namespace("http://proethica.org/ontology/core#")
PROETHICA_CASES = Namespace("http://proethica.org/ontology/cases#")
ENGINEERING_ETHICS = Namespace("http://proethica.org/ontology/engineering-ethics#")

class SPARQLService:
    """
    Service for executing SPARQL queries over ProEthica ontologies.
    
    Loads ontology files and provides a unified query interface.
    """
    
    def __init__(self, ontology_storage_path: str = None):
        """
        Initialize SPARQL service.
        
        Args:
            ontology_storage_path: Path to ontology storage directory
        """
        self.graph = Graph()
        self.ontology_path = ontology_storage_path or self._get_default_ontology_path()
        self.loaded_ontologies = set()
        
        # Bind namespaces for cleaner queries
        self.graph.bind("proeth-core", PROETHICA_CORE)
        self.graph.bind("proeth-cases", PROETHICA_CASES)
        self.graph.bind("eng-ethics", ENGINEERING_ETHICS)
        self.graph.bind("rdfs", RDFS)
        self.graph.bind("skos", SKOS)
        self.graph.bind("dcterms", DCTERMS)
        
        # Load ontologies on initialization
        self._load_ontologies()
    
    def _get_default_ontology_path(self) -> str:
        """Get default ontology storage path."""
        current_dir = Path(__file__).parent.parent
        return str(current_dir / "ontologies")
    
    def _load_ontologies(self):
        """Load all available ontology files."""
        if not os.path.exists(self.ontology_path):
            logger.warning(f"Ontology path does not exist: {self.ontology_path}")
            return
        
        ontology_files = [
            "proethica-core.ttl",
            "proethica-provenance.ttl",
            "proethica-intermediate.ttl",
            "proethica-cases.ttl",
            "engineering-ethics.ttl"
        ]
        
        loaded_count = 0
        for filename in ontology_files:
            filepath = os.path.join(self.ontology_path, filename)
            if os.path.exists(filepath):
                try:
                    self.graph.parse(filepath, format="turtle")
                    self.loaded_ontologies.add(filename)
                    loaded_count += 1
                    logger.info(f"Loaded ontology: {filename}")
                except Exception as e:
                    logger.error(f"Failed to load ontology {filename}: {e}")
        
        logger.info(f"SPARQL service initialized with {loaded_count} ontologies")
        logger.info(f"Total triples loaded: {len(self.graph)}")
    
    def execute_query(self, query: str) -> Dict[str, Any]:
        """
        Execute SPARQL query and return results.
        
        Args:
            query: SPARQL query string
            
        Returns:
            Query results in SPARQL JSON format
        """
        try:
            logger.debug(f"Executing SPARQL query: {query[:200]}...")
            
            # Execute query
            results = self.graph.query(query)
            
            # Convert results to SPARQL JSON format
            bindings = []
            for row in results:
                binding = {}
                for var_name, value in zip(results.vars, row):
                    var_key = str(var_name)
                    
                    if value is not None:
                        if isinstance(value, URIRef):
                            binding[var_key] = {
                                "type": "uri",
                                "value": str(value)
                            }
                        elif isinstance(value, Literal):
                            binding[var_key] = {
                                "type": "literal", 
                                "value": str(value)
                            }
                            if value.datatype:
                                binding[var_key]["datatype"] = str(value.datatype)
                            if value.language:
                                binding[var_key]["xml:lang"] = str(value.language)
                        else:
                            binding[var_key] = {
                                "type": "literal",
                                "value": str(value)
                            }
                
                bindings.append(binding)
            
            result = {
                "head": {
                    "vars": [str(var) for var in results.vars]
                },
                "results": {
                    "bindings": bindings
                }
            }
            
            logger.debug(f"Query returned {len(bindings)} results")
            return result
            
        except Exception as e:
            logger.error(f"SPARQL query execution failed: {e}")
            raise ValueError(f"SPARQL query error: {str(e)}")
    
    def get_service_status(self) -> Dict[str, Any]:
        """
        Get service status information.
        
        Returns:
            Service status dictionary
        """
        return {
            "service": "SPARQL",
            "status": "available" if self.loaded_ontologies else "no_ontologies",
            "loaded_ontologies": list(self.loaded_ontologies),
            "total_triples": len(self.graph),
            "ontology_path": self.ontology_path,
            "available_namespaces": list(self.graph.namespaces())
        }
    
    def validate_query(self, query: str) -> Dict[str, Any]:
        """
        Validate SPARQL query syntax without executing.
        
        Args:
            query: SPARQL query to validate
            
        Returns:
            Validation result
        """
        try:
            # Try to parse the query
            self.graph.query(query, dryrun=True)
            return {
                "valid": True,
                "message": "Query syntax is valid"
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }