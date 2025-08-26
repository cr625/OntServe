#!/usr/bin/env python3
"""
Create Merged Visualization Ontology for ProEthica Intermediate

This script creates a merged ontology that includes the core ontology content
directly within the intermediate ontology for visualization purposes.
This allows the visualization tool to show the full hierarchy:
BFO → Core → Intermediate

Author: Claude
Date: 2025-08-25
"""

import sys
import os
import psycopg2
import psycopg2.extras
from datetime import datetime

def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(
        host='localhost',
        port=5432,
        database='ontserve',
        user='ontserve_user',
        password='ontserve_development_password'
    )

def get_ontology_content(ontology_name):
    """Get current ontology content from database."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT ov.content 
        FROM ontologies o 
        JOIN ontology_versions ov ON o.id = ov.ontology_id 
        WHERE o.name = %s AND ov.is_current = true
    """, (ontology_name,))
    
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    return result[0] if result else None

def create_merged_content():
    """Create merged visualization ontology content."""
    
    # Get core ontology content
    core_content = get_ontology_content("proeth-core")
    intermediate_content = get_ontology_content("proethica-intermediate")
    
    if not core_content or not intermediate_content:
        print("❌ Could not retrieve ontology content")
        return None
    
    # Parse core content to extract classes and properties (simplified approach)
    # Remove XML declaration and RDF wrapper from core, keep content
    core_lines = core_content.split('\n')
    core_body_lines = []
    skip_lines = True
    
    for line in core_lines:
        if '<!-- Core Tuple Concepts' in line:
            skip_lines = False
        if not skip_lines and '</rdf:RDF>' not in line:
            core_body_lines.append(line)
    
    core_body = '\n'.join(core_body_lines)
    
    # Create merged content
    merged_content = f"""@prefix : <http://proethica.org/ontology/intermediate#> .
@prefix proeth: <http://proethica.org/ontology/intermediate#> .
@prefix core: <http://proethica.org/ontology/core#> .
@prefix bfo: <http://purl.obolibrary.org/obo/BFO_> .
@prefix iao: <http://purl.obolibrary.org/obo/IAO_> .
@prefix ro: <http://purl.obolibrary.org/obo/RO_> .
@prefix time: <http://www.w3.org/2006/time#> .
@prefix dc: <http://purl.org/dc/elements/1.1/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .

# Ontology Declaration
<http://proethica.org/ontology/intermediate> a owl:Ontology ;
    rdfs:label "ProEthica Intermediate Ontology (Merged for Visualization)"@en ;
    dc:creator "ProEthica AI"@en ;
    dc:date "2025-08-25"^^xsd:date ;
    rdfs:comment "Enhanced BFO-aligned ontology for professional ethics with core entities included for visualization purposes"@en ;
    owl:versionInfo "8.1.0-merged"^^xsd:string ;
    owl:imports <http://purl.obolibrary.org/obo/bfo.owl> ;
    owl:imports <http://purl.obolibrary.org/obo/iao.owl> ;
    owl:imports <http://purl.obolibrary.org/obo/ro.owl> ;
    owl:imports <http://www.w3.org/2006/time> ;
    skos:note "This version includes ProEthica Core classes directly for complete visualization of the hierarchy."@en .

###############################################################
# CORE ONTOLOGY CLASSES (from proeth-core) 
###############################################################

# R (Roles) - BFO:Role alignment
core:Role a owl:Class ;
    rdfs:subClassOf bfo:0000023 ;  # BFO:role
    rdfs:label "Role"@en ;
    skos:definition "A role that can be realized by processes involving professional duties and ethical obligations. This is the R component of the formal specification D=(R,P,O,S,Rs,A,E,Ca,Cs)."@en ;
    skos:note "Abstract concept - domain ontologies should subclass for specific role types (e.g., EngineerRole, LawyerRole)."@en .

# P (Principles) - IAO:Information Content Entity alignment  
core:Principle a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:label "Principle"@en ;
    skos:definition "An information content entity representing ethical values and guidelines for conduct. This is the P component of the formal specification D=(R,P,O,S,Rs,A,E,Ca,Cs)."@en ;
    skos:note "Abstract concept - domain ontologies should subclass for specific principles (e.g., PublicSafetyPrinciple, PrivacyPrinciple)."@en .

# O (Obligations) - IAO:Information Content Entity alignment
core:Obligation a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:label "Obligation"@en ;
    skos:definition "An information content entity expressing required actions or behaviors in professional contexts. This is the O component of the formal specification D=(R,P,O,S,Rs,A,E,Ca,Cs)."@en ;
    skos:note "Abstract concept - domain ontologies should subclass for specific obligation types (e.g., ReportingObligation, SafetyObligation)."@en .

# S (States) - BFO:Quality alignment
core:State a owl:Class ;
    rdfs:subClassOf bfo:0000019 ;  # BFO:quality
    rdfs:label "State"@en ;
    skos:definition "A quality representing conditions that affect ethical decisions and professional conduct. This is the S component of the formal specification D=(R,P,O,S,Rs,A,E,Ca,Cs)."@en ;
    skos:note "Abstract concept - domain ontologies should subclass for specific states (e.g., EmergencyState, ConflictState)."@en .

# Rs (Resources) - BFO:Continuant alignment
core:Resource a owl:Class ;
    rdfs:subClassOf bfo:0000002 ;  # BFO:continuant
    rdfs:label "Resource"@en ;
    skos:definition "A continuant entity that serves as input or reference for professional activities. This is the Rs component of the formal specification D=(R,P,O,S,Rs,A,E,Ca,Cs)."@en ;
    skos:note "Abstract concept - domain ontologies should subclass for specific resources (e.g., TechnicalResource, InformationResource)."@en .

# A (Actions) - BFO:Process alignment
core:Action a owl:Class ;
    rdfs:subClassOf bfo:0000015 ;  # BFO:process
    rdfs:label "Action"@en ;
    skos:definition "A process directed toward achieving specific goals in professional contexts. This is the A component of the formal specification D=(R,P,O,S,Rs,A,E,Ca,Cs)."@en ;
    skos:note "Abstract concept - domain ontologies should subclass for specific actions (e.g., DesignAction, ConsultationAction)."@en .

# E (Events) - BFO:Process alignment
core:Event a owl:Class ;
    rdfs:subClassOf bfo:0000015 ;  # BFO:process
    rdfs:label "Event"@en ;
    skos:definition "A process that occurs in professional contexts, which may or may not involve intentional agency. This is the E component of the formal specification D=(R,P,O,S,Rs,A,E,Ca,Cs)."@en ;
    skos:note "Abstract concept - domain ontologies should subclass for specific events (e.g., ViolationEvent, ComplianceEvent)."@en .

# Ca (Capabilities) - BFO:Disposition alignment
core:Capability a owl:Class ;
    rdfs:subClassOf bfo:0000016 ;  # BFO:disposition
    rdfs:label "Capability"@en ;
    skos:definition "A disposition that can be realized by specific types of actions or processes in professional contexts. This is the Ca component of the formal specification D=(R,P,O,S,Rs,A,E,Ca,Cs)."@en ;
    skos:note "Abstract concept - domain ontologies should subclass for specific capabilities (e.g., TechnicalCapability, LeadershipCapability)."@en .

# Agent - BFO:Material Entity alignment  
core:Agent a owl:Class ;
    rdfs:subClassOf bfo:0000040 ;  # BFO:material entity
    rdfs:label "Agent"@en ;
    skos:definition "A material entity capable of bearing roles and performing intentional actions in professional contexts."@en ;
    skos:note "Abstract concept - domain ontologies should subclass for specific agent types (e.g., Professional, Organization, System)."@en .

###############################################################
# CORE ONTOLOGY PROPERTIES (from proeth-core)
###############################################################

# Role Relations
core:hasRole a owl:ObjectProperty ;
    rdfs:subPropertyOf ro:0000087 ;  # RO:has_role
    rdfs:domain core:Agent ;
    rdfs:range core:Role ;
    rdfs:label "has role"@en ;
    skos:definition "Relates an agent to a role it bears."@en .

# Principle Relations
core:adheresToPrinciple a owl:ObjectProperty ;
    rdfs:subPropertyOf iao:0000136 ;  # IAO:is_about
    rdfs:domain core:Role ;
    rdfs:range core:Principle ;
    rdfs:label "adheres to principle"@en ;
    skos:definition "Relates a role to principles that guide its conduct."@en .

# Obligation Relations
core:hasObligation a owl:ObjectProperty ;
    rdfs:domain core:Role ;
    rdfs:range core:Obligation ;
    rdfs:label "has obligation"@en ;
    skos:definition "Relates a role to its professional obligations."@en .

core:fulfillsObligation a owl:ObjectProperty ;
    rdfs:subPropertyOf ro:0000057 ;  # RO:has_participant
    rdfs:domain core:Action ;
    rdfs:range core:Obligation ;
    rdfs:label "fulfills obligation"@en ;
    skos:definition "Relates an action to obligations it fulfills."@en .

# State Relations
core:hasState a owl:ObjectProperty ;
    rdfs:subPropertyOf bfo:0000051 ;  # BFO:has_part
    rdfs:domain core:Action ;
    rdfs:range core:State ;
    rdfs:label "has state"@en ;
    skos:definition "Relates an action to contextual states that affect its evaluation."@en .

# Resource Relations
core:usesResource a owl:ObjectProperty ;
    rdfs:domain core:Action ;
    rdfs:range core:Resource ;
    rdfs:label "uses resource"@en ;
    skos:definition "Relates an action to resources it utilizes."@en .

# Action Relations
core:performsAction a owl:ObjectProperty ;
    rdfs:subPropertyOf ro:0000056 ;  # RO:participates_in
    rdfs:domain core:Agent ;
    rdfs:range core:Action ;
    rdfs:label "performs action"@en ;
    skos:definition "Relates an agent to actions they perform."@en .

# Event Relations
core:triggersEvent a owl:ObjectProperty ;
    rdfs:subPropertyOf ro:0000012 ;  # RO:causally_upstream_of
    rdfs:domain core:Action ;
    rdfs:range core:Event ;
    rdfs:label "triggers event"@en ;
    skos:definition "Relates an action to events it causes or initiates."@en .

# Capability Relations
core:hasCapability a owl:ObjectProperty ;
    rdfs:domain core:Agent ;
    rdfs:range core:Capability ;
    rdfs:label "has capability"@en ;
    skos:definition "Relates an agent to capabilities they possess."@en .

core:realizesCapability a owl:ObjectProperty ;
    rdfs:subPropertyOf bfo:0000054 ;  # BFO:realizes
    rdfs:domain core:Action ;
    rdfs:range core:Capability ;
    rdfs:label "realizes capability"@en ;
    skos:definition "Relates an action to capabilities it realizes."@en .

###############################################################
# INTERMEDIATE ONTOLOGY EXTENSIONS
###############################################################

# Annotation Properties for Class-Instance Boundary Clarity
proeth:classificationGuidance a owl:AnnotationProperty ;
    rdfs:subPropertyOf skos:scopeNote ;
    rdfs:label "Classification Guidance"@en ;
    iao:0000115 "Provides guidance on when to model as a class versus an individual."@en .

proeth:instanceExample a owl:AnnotationProperty ;
    rdfs:subPropertyOf skos:example ;
    rdfs:label "Instance Example"@en ;
    iao:0000115 "Provides example of how instances of this class would be created."@en .

proeth:operationalizationNote a owl:AnnotationProperty ;
    rdfs:subPropertyOf skos:note ;
    rdfs:label "Operationalization Note"@en ;
    iao:0000115 "Guidance for operationalizing this concept in SHACL, SWRL, or other tools."@en .

# Professional Role Extensions (Extending Core)
proeth:ProfessionalRole a owl:Class ;
    rdfs:subClassOf core:Role ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty bfo:0000052 ;  # inheres in
                      owl:someValuesFrom bfo:0000040 ] ;  # material entity
    rdfs:label "Professional Role"@en ;
    iao:0000115 "A professional role with formal obligations and accountability, extending the core Role concept."@en ;
    proeth:classificationGuidance "Model as class for role types (e.g., Engineer, Lawyer). Create individuals for specific role instances (e.g., senior_engineer_alice_123)."@en ;
    proeth:instanceExample "Individual: eng:alice_senior_engineer_role_2025 rdf:type proeth:ProfessionalEngineerRole"@en .

# Enhanced Agent Framework - extends core:Agent
proeth:EthicsReviewer a owl:Class ;
    rdfs:subClassOf core:Agent ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty core:hasRole ;
                      owl:someValuesFrom proeth:EthicsReviewerRole ] ;
    rdfs:label "Ethics Reviewer"@en ;
    iao:0000115 "An agent who has the role and competency to review ethical assessments and decisions."@en .

proeth:AIAdvisor a owl:Class ;
    rdfs:subClassOf core:Agent ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty core:hasCapability ;
                      owl:someValuesFrom proeth:EthicalAnalysisCapability ] ;
    rdfs:label "AI Advisor"@en ;
    iao:0000115 "An artificial agent capable of providing ethical guidance and analysis."@en .

proeth:Engineer a owl:Class ;
    rdfs:subClassOf core:Agent ;
    rdfs:label "Engineer"@en ;
    iao:0000115 "An agent who bears engineering-related professional roles."@en .

proeth:EthicsReviewerRole a owl:Class ;
    rdfs:subClassOf proeth:ProfessionalRole ;
    rdfs:label "Ethics Reviewer Role"@en ;
    iao:0000115 "A professional role involving the review and evaluation of ethical decisions and conduct."@en .

# Enhanced Principle Framework - extends core:Principle
proeth:FundamentalPrinciple a owl:Class ;
    rdfs:subClassOf core:Principle ;
    rdfs:label "Fundamental Principle"@en ;
    iao:0000115 "A basic ethical principle that serves as a foundation for professional conduct across domains."@en .

proeth:ProfessionalPrinciple a owl:Class ;
    rdfs:subClassOf core:Principle ;
    rdfs:label "Professional Principle"@en ;
    iao:0000115 "An ethical principle specific to professional practice
