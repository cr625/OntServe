"""
RDF generation helpers for OntServe web application.

Provides functions to generate TTL (Turtle) content from concepts and entities.
"""

from datetime import datetime


def generate_rdf_from_concepts(ontology_name, concepts, base_imports):
    """Generate RDF/Turtle content from extracted concepts."""
    # Base prefixes
    prefixes = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix proethica: <http://proethica.org/ontology/> .

"""

    # Ontology declaration
    base_uri = f'http://proethica.org/ontology/{ontology_name}'
    ontology_declaration = f"""<{base_uri}>
    a owl:Ontology ;
    rdfs:comment "Extracted concepts from ProEthica guideline analysis" ;
    owl:versionInfo "1.0-draft" ;
    proethica:extractedAt "{datetime.utcnow().isoformat()}"^^xsd:dateTime"""

    # Add imports
    for import_ont in base_imports:
        ontology_declaration += f' ;\n    owl:imports <http://proethica.org/ontology/{import_ont}>'

    ontology_declaration += " .\n\n"

    # Generate concept triples
    concept_triples = ""
    for concept in concepts:
        concept_uri = f"<{base_uri}#{concept.get('label', '').replace(' ', '')}>"
        concept_type = concept.get('type', 'class').lower()

        # Map ProEthica types to intermediate ontology classes
        type_mapping = {
            'role': 'http://proethica.org/ontology/intermediate#Role',
            'principle': 'http://proethica.org/ontology/intermediate#Principle',
            'obligation': 'http://proethica.org/ontology/intermediate#Obligation',
            'state': 'http://proethica.org/ontology/intermediate#State',
            'resource': 'http://proethica.org/ontology/intermediate#Resource',
            'action': 'http://proethica.org/ontology/intermediate#Action',
            'event': 'http://proethica.org/ontology/intermediate#Event',
            'capability': 'http://proethica.org/ontology/intermediate#Capability',
            'constraint': 'http://proethica.org/ontology/intermediate#Constraint'
        }

        parent_class = type_mapping.get(concept_type, 'owl:Thing')

        concept_triples += f"""{concept_uri}
    a owl:Class ;
    rdfs:subClassOf <{parent_class}> ;
    rdfs:label "{concept.get('label', '')}" """

        if concept.get('description'):
            desc = concept.get('description')
            concept_triples += f';\n    rdfs:comment "{desc}"'

        if concept.get('confidence'):
            conf = concept.get('confidence')
            concept_triples += f';\n    proethica:extractionConfidence "{conf}"^^xsd:float'

        concept_triples += " .\n\n"

    return prefixes + ontology_declaration + concept_triples


def generate_entity_ttl(entity, ontology):
    """Generate TTL representation for an entity."""
    lines = []

    # Add prefixes
    lines.append("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
    lines.append("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .")
    lines.append("@prefix owl: <http://www.w3.org/2002/07/owl#> .")

    # Add ontology prefix
    if ontology.base_uri:
        prefix_name = ontology.name.replace('-', '_')
        lines.append(f"@prefix {prefix_name}: <{ontology.base_uri}> .")

    lines.append("")  # Empty line

    # Entity declaration
    entity_type_mapping = {
        'class': 'owl:Class',
        'property': 'owl:ObjectProperty',
        'datatype_property': 'owl:DatatypeProperty',
        'individual': 'owl:NamedIndividual'
    }

    entity_rdf_type = entity_type_mapping.get(entity.entity_type, 'owl:Thing')
    lines.append(f"<{entity.uri}> a {entity_rdf_type} ;")

    # Add label
    if entity.label:
        lines.append(f'    rdfs:label "{entity.label}" ;')

    # Add comment/definition
    if entity.comment:
        lines.append(f'    rdfs:comment "{entity.comment}" ;')

    # Add parent class if available
    if entity.parent_uri:
        lines.append(f'    rdfs:subClassOf <{entity.parent_uri}> ;')

    # Add domain and range for properties (a union is stored as a list of member URIs)
    if entity.domain:
        doms = entity.domain if isinstance(entity.domain, list) else [entity.domain]
        lines.append('    rdfs:domain ' + ', '.join(f'<{d}>' for d in doms) + ' ;')
    if entity.range:
        rngs = entity.range if isinstance(entity.range, list) else [entity.range]
        lines.append('    rdfs:range ' + ', '.join(f'<{r}>' for r in rngs) + ' ;')

    # Remove trailing semicolon from last line and add period
    if lines and lines[-1].endswith(' ;'):
        lines[-1] = lines[-1][:-2] + ' .'

    return '\n'.join(lines)


def generate_concept_ttl(concept):
    """Generate TTL representation for a concept from the concepts table."""
    lines = []

    # Add prefixes
    lines.append("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
    lines.append("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .")
    lines.append("@prefix owl: <http://www.w3.org/2002/07/owl#> .")
    lines.append("@prefix skos: <http://www.w3.org/2004/02/skos/core#> .")
    lines.append("@prefix proeth-core: <http://proethica.org/ontology/core#> .")
    lines.append("")

    # Map primary_type to OWL class
    type_mapping = {
        'Provision': 'proeth-core:CodeProvision',
        'Guideline': 'proeth-core:Guideline',
        'Principle': 'proeth-core:Principle',
        'Obligation': 'proeth-core:Obligation',
        'Constraint': 'proeth-core:Constraint',
        'Role': 'proeth-core:Role',
        'State': 'proeth-core:State',
        'Resource': 'proeth-core:Resource',
        'Action': 'proeth-core:Action',
        'Event': 'proeth-core:Event',
        'Capability': 'proeth-core:Capability'
    }

    rdf_type = type_mapping.get(concept['primary_type'], 'owl:Thing')
    lines.append(f"<{concept['uri']}> a {rdf_type} ;")

    # Add label
    label = concept.get('semantic_label') or concept.get('label') or ''
    if label:
        escaped_label = label.replace('"', '\\"').replace('\n', ' ')
        lines.append(f'    rdfs:label "{escaped_label}"@en ;')

    # Add description/definition
    description = concept.get('description') or ''
    if description:
        # Truncate and escape
        desc_truncated = description[:1000].replace('"', '\\"').replace('\n', ' ')
        lines.append(f'    rdfs:comment "{desc_truncated}"@en ;')

    # Add metadata-specific properties for provisions
    metadata = concept.get('metadata') or {}
    if concept['primary_type'] == 'Provision':
        if metadata.get('provision_code'):
            lines.append(f'    proeth-core:provisionCode "{metadata["provision_code"]}" ;')
        if metadata.get('provision_category'):
            lines.append(f'    proeth-core:provisionCategory "{metadata["provision_category"]}" ;')

    # Remove trailing semicolon from last line and add period
    if lines and lines[-1].endswith(' ;'):
        lines[-1] = lines[-1][:-2] + ' .'

    return '\n'.join(lines)
