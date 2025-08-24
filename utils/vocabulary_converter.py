"""
Vocabulary Converter for Non-OWL Vocabularies

Converts various vocabulary formats (SKOS, Dublin Core, basic RDF) to OWL-compatible ontologies.
"""

import logging
from typing import Dict, List, Any, Optional
import rdflib
from rdflib import Graph, Namespace, RDF, RDFS, OWL
from rdflib.namespace import SKOS, DC, DCTERMS, FOAF


class VocabularyConverter:
    """Convert non-OWL vocabularies to OWL-compatible format."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Define namespace mappings
        self.namespaces = {
            'skos': SKOS,
            'dc': DC,
            'dcterms': DCTERMS,
            'foaf': FOAF,
            'rdfs': RDFS,
            'rdf': RDF,
            'owl': OWL
        }
    
    def detect_vocabulary_type(self, graph: Graph) -> str:
        """
        Detect the primary vocabulary type used in the graph.
        
        Args:
            graph: RDF graph to analyze
            
        Returns:
            Detected vocabulary type ('skos', 'dublin_core', 'foaf', 'rdfs', 'owl')
        """
        type_indicators = {
            'skos': [
                (None, RDF.type, SKOS.Concept),
                (None, RDF.type, SKOS.ConceptScheme),
                (None, SKOS.broader, None),
                (None, SKOS.narrower, None),
                (None, SKOS.prefLabel, None)
            ],
            'dublin_core': [
                (None, DC.title, None),
                (None, DC.creator, None),
                (None, DCTERMS.title, None),
                (None, DCTERMS.creator, None)
            ],
            'foaf': [
                (None, RDF.type, FOAF.Person),
                (None, FOAF.name, None),
                (None, FOAF.knows, None),
                (None, FOAF.mbox, None)
            ],
            'owl': [
                (None, RDF.type, OWL.Class),
                (None, RDF.type, OWL.ObjectProperty),
                (None, RDF.type, OWL.Ontology)
            ]
        }
        
        scores = {}
        for vocab_type, patterns in type_indicators.items():
            score = 0
            for pattern in patterns:
                try:
                    matches = len(list(graph.triples(pattern)))
                    score += matches
                except:
                    continue
            scores[vocab_type] = score
        
        # Return the vocabulary type with the highest score
        detected = max(scores.items(), key=lambda x: x[1])
        self.logger.info(f"Detected vocabulary type: {detected[0]} (score: {detected[1]})")
        
        return detected[0] if detected[1] > 0 else 'rdfs'
    
    def convert_to_owl(self, input_graph: Graph, vocabulary_type: str = None, 
                      ontology_uri: str = None) -> Graph:
        """
        Convert a vocabulary graph to OWL format.
        
        Args:
            input_graph: Input RDF graph
            vocabulary_type: Type of vocabulary to convert (auto-detected if None)
            ontology_uri: URI for the resulting ontology
            
        Returns:
            OWL-compatible graph
        """
        if vocabulary_type is None:
            vocabulary_type = self.detect_vocabulary_type(input_graph)
        
        self.logger.info(f"Converting {vocabulary_type} vocabulary to OWL")
        
        # Create output graph with OWL ontology structure
        output_graph = Graph()
        
        # Add namespace bindings
        for prefix, ns in self.namespaces.items():
            output_graph.bind(prefix, ns)
        
        # Add ontology declaration if URI provided
        if ontology_uri:
            ontology_node = rdflib.URIRef(ontology_uri)
            output_graph.add((ontology_node, RDF.type, OWL.Ontology))
            output_graph.add((ontology_node, RDFS.comment, 
                            rdflib.Literal(f"Converted from {vocabulary_type} vocabulary")))
        
        # Convert based on vocabulary type
        if vocabulary_type == 'skos':
            self._convert_skos(input_graph, output_graph)
        elif vocabulary_type == 'dublin_core':
            self._convert_dublin_core(input_graph, output_graph)
        elif vocabulary_type == 'foaf':
            self._convert_foaf(input_graph, output_graph)
        else:
            # Generic RDFS conversion
            self._convert_rdfs(input_graph, output_graph)
        
        # Copy over any existing OWL constructs
        self._preserve_owl_constructs(input_graph, output_graph)
        
        self.logger.info(f"Conversion complete: {len(output_graph)} triples in output graph")
        return output_graph
    
    def _convert_skos(self, input_graph: Graph, output_graph: Graph):
        """Convert SKOS vocabulary to OWL classes and properties."""
        self.logger.info("Converting SKOS concepts and relationships")
        
        # Convert SKOS Concepts to OWL Classes
        for concept in input_graph.subjects(RDF.type, SKOS.Concept):
            output_graph.add((concept, RDF.type, OWL.Class))
            
            # Convert labels
            for pref_label in input_graph.objects(concept, SKOS.prefLabel):
                output_graph.add((concept, RDFS.label, pref_label))
            
            for alt_label in input_graph.objects(concept, SKOS.altLabel):
                output_graph.add((concept, RDFS.label, alt_label))
            
            # Convert definitions
            for definition in input_graph.objects(concept, SKOS.definition):
                output_graph.add((concept, RDFS.comment, definition))
            
            # Convert notes
            for note in input_graph.objects(concept, SKOS.note):
                output_graph.add((concept, RDFS.comment, note))
        
        # Convert SKOS hierarchical relationships to OWL class hierarchy
        for concept in input_graph.subjects(SKOS.broader, None):
            for broader in input_graph.objects(concept, SKOS.broader):
                output_graph.add((concept, RDFS.subClassOf, broader))
        
        # Convert SKOS ConceptSchemes to OWL Classes
        for scheme in input_graph.subjects(RDF.type, SKOS.ConceptScheme):
            output_graph.add((scheme, RDF.type, OWL.Class))
            
            # Add labels and comments
            for label in input_graph.objects(scheme, SKOS.prefLabel):
                output_graph.add((scheme, RDFS.label, label))
            for definition in input_graph.objects(scheme, SKOS.definition):
                output_graph.add((scheme, RDFS.comment, definition))
        
        # Convert SKOS semantic relationships to OWL object properties
        semantic_relations = [SKOS.related, SKOS.exactMatch, SKOS.closeMatch, 
                            SKOS.broadMatch, SKOS.narrowMatch]
        
        for relation in semantic_relations:
            if list(input_graph.triples((None, relation, None))):
                # Create OWL object property for this relation
                output_graph.add((relation, RDF.type, OWL.ObjectProperty))
                
                # Copy the relation triples
                for s, p, o in input_graph.triples((None, relation, None)):
                    output_graph.add((s, p, o))
    
    def _convert_dublin_core(self, input_graph: Graph, output_graph: Graph):
        """Convert Dublin Core metadata elements to OWL properties."""
        self.logger.info("Converting Dublin Core metadata elements")
        
        # DC and DCTERMS properties to convert
        dc_properties = [
            DC.title, DC.creator, DC.subject, DC.description, DC.publisher,
            DC.contributor, DC.date, DC.type, DC.format, DC.identifier,
            DC.source, DC.language, DC.relation, DC.coverage, DC.rights
        ]
        
        dcterms_properties = [
            DCTERMS.title, DCTERMS.creator, DCTERMS.subject, DCTERMS.description,
            DCTERMS.abstract, DCTERMS.created, DCTERMS.modified, DCTERMS.issued,
            DCTERMS.license, DCTERMS.rightsHolder
        ]
        
        # Convert DC properties to OWL annotation properties
        for prop in dc_properties + dcterms_properties:
            if list(input_graph.triples((None, prop, None))):
                output_graph.add((prop, RDF.type, OWL.AnnotationProperty))
                
                # Copy all triples using this property
                for s, p, o in input_graph.triples((None, prop, None)):
                    output_graph.add((s, p, o))
                    
                    # If subject isn't already typed, make it a resource
                    if not list(output_graph.triples((s, RDF.type, None))):
                        output_graph.add((s, RDF.type, RDFS.Resource))
    
    def _convert_foaf(self, input_graph: Graph, output_graph: Graph):
        """Convert FOAF vocabulary to OWL classes and properties."""
        self.logger.info("Converting FOAF vocabulary")
        
        # Convert FOAF classes
        foaf_classes = [FOAF.Person, FOAF.Organization, FOAF.Group, FOAF.Document, FOAF.Image]
        
        for foaf_class in foaf_classes:
            if list(input_graph.subjects(RDF.type, foaf_class)):
                output_graph.add((foaf_class, RDF.type, OWL.Class))
        
        # Convert FOAF properties to OWL properties
        foaf_object_props = [FOAF.knows, FOAF.member, FOAF.maker, FOAF.depicts, FOAF.account]
        foaf_data_props = [FOAF.name, FOAF.mbox, FOAF.homepage, FOAF.phone, FOAF.title]
        
        for prop in foaf_object_props:
            if list(input_graph.triples((None, prop, None))):
                output_graph.add((prop, RDF.type, OWL.ObjectProperty))
        
        for prop in foaf_data_props:
            if list(input_graph.triples((None, prop, None))):
                output_graph.add((prop, RDF.type, OWL.DatatypeProperty))
        
        # Copy all FOAF triples
        for s, p, o in input_graph:
            if str(p).startswith(str(FOAF)):
                output_graph.add((s, p, o))
    
    def _convert_rdfs(self, input_graph: Graph, output_graph: Graph):
        """Convert generic RDFS vocabulary to OWL."""
        self.logger.info("Converting generic RDFS vocabulary")
        
        # Convert RDFS Classes to OWL Classes
        for rdfs_class in input_graph.subjects(RDF.type, RDFS.Class):
            output_graph.add((rdfs_class, RDF.type, OWL.Class))
            
            # Copy labels and comments
            for label in input_graph.objects(rdfs_class, RDFS.label):
                output_graph.add((rdfs_class, RDFS.label, label))
            for comment in input_graph.objects(rdfs_class, RDFS.comment):
                output_graph.add((rdfs_class, RDFS.comment, comment))
        
        # Convert RDF Properties to OWL Properties
        for rdf_prop in input_graph.subjects(RDF.type, RDF.Property):
            # Default to ObjectProperty, could be refined based on range/domain analysis
            output_graph.add((rdf_prop, RDF.type, OWL.ObjectProperty))
            
            # Copy domain and range
            for domain in input_graph.objects(rdf_prop, RDFS.domain):
                output_graph.add((rdf_prop, RDFS.domain, domain))
            for range_val in input_graph.objects(rdf_prop, RDFS.range):
                output_graph.add((rdf_prop, RDFS.range, range_val))
        
        # Copy RDFS subclass relationships
        for s, p, o in input_graph.triples((None, RDFS.subClassOf, None)):
            output_graph.add((s, p, o))
        
        # Copy RDFS subproperty relationships  
        for s, p, o in input_graph.triples((None, RDFS.subPropertyOf, None)):
            output_graph.add((s, p, o))
    
    def _preserve_owl_constructs(self, input_graph: Graph, output_graph: Graph):
        """Preserve any existing OWL constructs from the input graph."""
        owl_types = [OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, 
                    OWL.AnnotationProperty, OWL.Ontology, OWL.NamedIndividual]
        
        for owl_type in owl_types:
            for entity in input_graph.subjects(RDF.type, owl_type):
                # Copy the type declaration
                output_graph.add((entity, RDF.type, owl_type))
                
                # Copy associated properties
                for p, o in input_graph.predicate_objects(entity):
                    output_graph.add((entity, p, o))
    
    def convert_vocabulary_file(self, file_path: str, output_format: str = 'turtle',
                              ontology_uri: str = None) -> str:
        """
        Convert a vocabulary file to OWL format.
        
        Args:
            file_path: Path to input vocabulary file
            output_format: Output format ('turtle', 'xml', 'n3', etc.)
            ontology_uri: URI for the resulting ontology
            
        Returns:
            Converted ontology as string
        """
        # Load input graph
        input_graph = Graph()
        input_graph.parse(file_path)
        
        # Convert to OWL
        output_graph = self.convert_to_owl(input_graph, ontology_uri=ontology_uri)
        
        # Serialize and return
        return output_graph.serialize(format=output_format)
    
    def convert_vocabulary_content(self, content: str, input_format: str = 'turtle',
                                 output_format: str = 'turtle', ontology_uri: str = None) -> str:
        """
        Convert vocabulary content to OWL format.
        
        Args:
            content: Input vocabulary content as string
            input_format: Input format
            output_format: Output format
            ontology_uri: URI for the resulting ontology
            
        Returns:
            Converted ontology as string
        """
        # Load input graph
        input_graph = Graph()
        input_graph.parse(data=content, format=input_format)
        
        # Convert to OWL
        output_graph = self.convert_to_owl(input_graph, ontology_uri=ontology_uri)
        
        # Serialize and return
        return output_graph.serialize(format=output_format)


def is_vocabulary_convertible(content: str, format_hint: str = 'turtle') -> bool:
    """
    Check if content contains a convertible vocabulary.
    
    Args:
        content: Content to check
        format_hint: Format hint for parsing
        
    Returns:
        True if content appears to be a convertible vocabulary
    """
    try:
        graph = Graph()
        graph.parse(data=content, format=format_hint)
        
        # Check for vocabulary indicators
        vocab_indicators = [
            # SKOS
            (None, RDF.type, SKOS.Concept),
            (None, RDF.type, SKOS.ConceptScheme),
            # Dublin Core
            (None, DC.title, None),
            (None, DCTERMS.title, None),
            # FOAF
            (None, RDF.type, FOAF.Person),
            (None, FOAF.name, None),
            # Generic RDFS
            (None, RDF.type, RDFS.Class),
            (None, RDF.type, RDF.Property)
        ]
        
        for pattern in vocab_indicators:
            if list(graph.triples(pattern)):
                return True
        
        return False
        
    except Exception:
        return False


# Example usage and test function
if __name__ == "__main__":
    # Test with a simple SKOS example
    skos_content = """
    @prefix skos: <http://www.w3.org/2004/02/skos/core#> .
    @prefix ex: <http://example.org/> .
    
    ex:animals a skos:ConceptScheme ;
        skos:prefLabel "Animals" .
    
    ex:mammal a skos:Concept ;
        skos:prefLabel "Mammal" ;
        skos:inScheme ex:animals .
    
    ex:dog a skos:Concept ;
        skos:prefLabel "Dog" ;
        skos:broader ex:mammal ;
        skos:inScheme ex:animals .
    """
    
    converter = VocabularyConverter()
    owl_result = converter.convert_vocabulary_content(
        skos_content, 
        ontology_uri="http://example.org/animals-ontology"
    )
    
    print("SKOS to OWL conversion result:")
    print(owl_result)
