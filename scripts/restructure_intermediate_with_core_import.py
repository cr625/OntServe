#!/usr/bin/env python3
"""
Restructure ProEthica Intermediate Ontology to Import and Extend Core

This script modifies the proethica-intermediate ontology to:
1. Import the proeth-core ontology
2. Change base classes to extend core classes instead of BFO directly  
3. Remove duplicate property definitions that exist in core
4. Keep specialized content and enhancements
5. Create clear hierarchical relationship for visualization

Author: Claude
Date: 2025-08-25
"""

import sys
import os
import psycopg2
import psycopg2.extras
from datetime import datetime

def create_restructured_intermediate_content():
    """Create the restructured intermediate ontology content that imports core."""
    
    content = """@prefix : <http://proethica.org/ontology/intermediate#> .
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
    rdfs:label "ProEthica Intermediate Ontology"@en ;
    dc:creator "ProEthica AI"@en ;
    dc:date "2025-08-25"^^xsd:date ;
    rdfs:comment "Enhanced BFO-aligned ontology for professional ethics extending ProEthica Core with class-instance boundaries, temporal scope, evaluation criteria, and advanced constraints"@en ;
    owl:versionInfo "8.1.0"^^xsd:string ;
    owl:imports <http://proethica.org/ontology/core> ;
    owl:imports <http://www.w3.org/2006/time> ;
    skos:note "This ontology extends the ProEthica Core ontology with specialized professional ethics concepts. Core concepts (R,P,O,S,Rs,A,E,Ca,Cs) are inherited from the core module."@en .

###############################################################
# Annotation Properties for Class-Instance Boundary Clarity
###############################################################

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

###############################################################
# Professional Role Extensions (Extending Core)
###############################################################

# Professional Role - extends core:Role
proeth:ProfessionalRole a owl:Class ;
    rdfs:subClassOf core:Role ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty bfo:0000052 ;  # inheres in
                      owl:someValuesFrom bfo:0000040 ] ;  # material entity
    rdfs:label "Professional Role"@en ;
    iao:0000115 "A professional role with formal obligations and accountability, extending the core Role concept."@en ;
    proeth:classificationGuidance "Model as class for role types (e.g., Engineer, Lawyer). Create individuals for specific role instances (e.g., senior_engineer_alice_123)."@en ;
    proeth:instanceExample "Individual: eng:alice_senior_engineer_role_2025 rdf:type proeth:ProfessionalEngineerRole"@en ;
    proeth:operationalizationNote "Use SHACL to enforce that role instances must have exactly one bearer agent."@en .

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

###############################################################
# Enhanced Principle Framework - extends core:Principle
###############################################################

proeth:FundamentalPrinciple a owl:Class ;
    rdfs:subClassOf core:Principle ;
    rdfs:label "Fundamental Principle"@en ;
    iao:0000115 "A basic ethical principle that serves as a foundation for professional conduct across domains."@en .

proeth:ProfessionalPrinciple a owl:Class ;
    rdfs:subClassOf core:Principle ;
    rdfs:label "Professional Principle"@en ;
    iao:0000115 "An ethical principle specific to professional practice and occupational roles."@en .

proeth:AccountabilityPrinciple a owl:Class ;
    rdfs:subClassOf proeth:ProfessionalPrinciple ;
    rdfs:label "Accountability Principle"@en ;
    iao:0000115 "The principle that professionals must take responsibility for their decisions and actions."@en .

proeth:TransparencyPrinciple a owl:Class ;
    rdfs:subClassOf proeth:ProfessionalPrinciple ;
    rdfs:label "Transparency Principle"@en ;
    iao:0000115 "The principle of maintaining openness and honesty in professional communications and processes."@en .

proeth:IntegrityPrinciple a owl:Class ;
    rdfs:subClassOf core:Principle ;
    rdfs:label "Integrity Principle"@en ;
    iao:0000115 "A principle that guides honest and truthful professional conduct."@en .

###############################################################
# Enhanced Deontic Framework - extends core:Obligation
###############################################################

proeth:ConditionalObligation a owl:Class ;
    rdfs:subClassOf core:Obligation ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty proeth:conditionallyAppliesWhen ;
                      owl:qualifiedCardinality "1"^^xsd:nonNegativeInteger ;
                      owl:onClass core:State ] ;
    rdfs:label "Conditional Obligation"@en ;
    iao:0000115 "An obligation that applies only when specific conditions or states are present."@en ;
    proeth:operationalizationNote "SHACL constraint: Every ConditionalObligation must have exactly one triggering State."@en .

proeth:OverridingObligation a owl:Class ;
    rdfs:subClassOf core:Obligation ;
    rdfs:label "Overriding Obligation"@en ;
    iao:0000115 "An obligation that takes precedence over conflicting obligations in specific contexts."@en .

proeth:PrimafacieObligation a owl:Class ;
    rdfs:subClassOf core:Obligation ;
    rdfs:label "Prima facie Obligation"@en ;
    iao:0000115 "An obligation that holds generally but may be overridden by stronger moral considerations."@en ;
    skos:note "From W.D. Ross's moral philosophy - duties that are binding unless overridden."@en .

proeth:PublicSafetyObligation a owl:Class ;
    rdfs:subClassOf core:Obligation ;
    rdfs:label "Public Safety Obligation"@en ;
    iao:0000115 "An obligation to prioritize public safety in professional activities."@en .

# Permission and Prohibition Extensions
proeth:Permission a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:label "Permission"@en ;
    iao:0000115 "A deontic statement expressing allowed actions or behaviors."@en .

proeth:ExplicitPermission a owl:Class ;
    rdfs:subClassOf proeth:Permission ;
    rdfs:label "Explicit Permission"@en ;
    iao:0000115 "A permission that is explicitly granted by authority or regulation."@en .

proeth:ImplicitPermission a owl:Class ;
    rdfs:subClassOf proeth:Permission ;
    rdfs:label "Implicit Permission"@en ;
    iao:0000115 "A permission that is implied by the absence of prohibition and presence of capability."@en .

proeth:Prohibition a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:label "Prohibition"@en ;
    iao:0000115 "A deontic statement expressing forbidden actions or behaviors."@en .

proeth:AbsoluteProhibition a owl:Class ;
    rdfs:subClassOf proeth:Prohibition ;
    rdfs:label "Absolute Prohibition"@en ;
    iao:0000115 "A prohibition that admits no exceptions and overrides all other considerations."@en .

proeth:ConditionalProhibition a owl:Class ;
    rdfs:subClassOf proeth:Prohibition ;
    rdfs:label "Conditional Prohibition"@en ;
    iao:0000115 "A prohibition that applies only under specific conditions or contexts."@en .

###############################################################
# Enhanced Action Framework - extends core:Action
###############################################################

proeth:EthicallyRequiredAction a owl:Class ;
    rdfs:subClassOf core:Action ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty core:fulfillsObligation ;
                      owl:someValuesFrom core:Obligation ] ;
    rdfs:label "Ethically Required Action"@en ;
    iao:0000115 "An action that is mandated by ethical obligations and must be performed."@en ;
    proeth:operationalizationNote "Use SHACL to enforce that these actions must be linked to specific obligations."@en .

proeth:EthicallyOptionalAction a owl:Class ;
    rdfs:subClassOf core:Action ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty proeth:enabledByPermission ;
                      owl:someValuesFrom proeth:Permission ] ;
    rdfs:label "Ethically Optional Action"@en ;
    iao:0000115 "An action that is permitted but not required by ethical considerations."@en .

proeth:EthicallyProhibitedAction a owl:Class ;
    rdfs:subClassOf core:Action ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty proeth:violatesProhibition ;
                      owl:someValuesFrom proeth:Prohibition ] ;
    rdfs:label "Ethically Prohibited Action"@en ;
    iao:0000115 "An action that violates ethical prohibitions and should not be performed."@en .

###############################################################
# Enhanced State Framework - extends core:State
###############################################################

proeth:ContextualState a owl:Class ;
    rdfs:subClassOf core:State ;
    rdfs:label "Contextual State"@en ;
    iao:0000115 "A quality that represents environmental, organizational, or situational conditions affecting professional decisions."@en .

proeth:EnvironmentalState a owl:Class ;
    rdfs:subClassOf proeth:ContextualState ;
    rdfs:label "Environmental State"@en ;
    iao:0000115 "A quality representing external environmental conditions affecting professional practice."@en .

proeth:OrganizationalState a owl:Class ;
    rdfs:subClassOf proeth:ContextualState ;
    rdfs:label "Organizational State"@en ;
    iao:0000115 "A quality representing the state of an organization or institutional context."@en .

proeth:LegalState a owl:Class ;
    rdfs:subClassOf proeth:ContextualState ;
    rdfs:label "Legal State"@en ;
    iao:0000115 "A quality representing the legal or regulatory context of a professional situation."@en .

proeth:TechnicalState a owl:Class ;
    rdfs:subClassOf proeth:ContextualState ;
    rdfs:label "Technical State"@en ;
    iao:0000115 "A quality representing technical conditions or system states relevant to professional decisions."@en .

proeth:UncertaintyState a owl:Class ;
    rdfs:subClassOf proeth:ContextualState ;
    rdfs:label "Uncertainty State"@en ;
    iao:0000115 "A quality representing incomplete information or ambiguous conditions affecting professional judgment."@en .

proeth:EmergencyState a owl:Class ;
    rdfs:subClassOf proeth:EnvironmentalState ;
    rdfs:label "Emergency State"@en ;
    iao:0000115 "A quality representing urgent conditions requiring immediate professional response."@en .

###############################################################
# Enhanced Resource Framework - extends core:Resource
###############################################################

proeth:MaterialResource a owl:Class ;
    rdfs:subClassOf core:Resource ;
    rdfs:subClassOf bfo:0000040 ;  # BFO:material entity
    rdfs:label "Material Resource"@en ;
    iao:0000115 "A physical resource used in professional activities."@en .

proeth:InformationResource a owl:Class ;
    rdfs:subClassOf core:Resource ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:label "Information Resource"@en ;
    iao:0000115 "An informational resource used in professional activities."@en .

###############################################################
# Enhanced Event Framework - extends core:Event
###############################################################

proeth:ViolationEvent a owl:Class ;
    rdfs:subClassOf core:Event ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty proeth:hasSeverityLevel ;
                      owl:someValuesFrom proeth:SeverityLevel ] ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty proeth:violatesObligation ;
                      owl:someValuesFrom core:Obligation ] ;
    rdfs:label "Violation Event"@en ;
    iao:0000115 "An event involving the breach of professional obligations with specified severity level."@en .

proeth:TriggeringEvent a owl:Class ;
    rdfs:subClassOf core:Event ;
    rdfs:label "Triggering Event"@en ;
    iao:0000115 "An event that initiates or activates professional obligations, permissions, or prohibitions."@en .

proeth:EthicalTrigger a owl:Class ;
    rdfs:subClassOf proeth:TriggeringEvent ;
    rdfs:label "Ethical Trigger"@en ;
    iao:0000115 "An event that creates an ethical decision point requiring professional judgment."@en .

proeth:ComplianceEvent a owl:Class ;
    rdfs:subClassOf core:Event ;
    rdfs:label "Compliance Event"@en ;
    iao:0000115 "An event demonstrating adherence to professional obligations or ethical standards."@en .

proeth:CompetencyAssessmentEvent a owl:Class ;
    rdfs:subClassOf core:Event ;
    rdfs:label "Competency Assessment Event"@en ;
    iao:0000115 "An event involving the evaluation of professional competencies or qualifications."@en .

proeth:ContinuingEducationEvent a owl:Class ;
    rdfs:subClassOf core:Event ;
    rdfs:label "Continuing Education Event"@en ;
    iao:0000115 "An event involving professional development or educational activities."@en .

###############################################################
# Enhanced Capability Framework - extends core:Capability
###############################################################

proeth:TechnicalCompetency a owl:Class ;
    rdfs:subClassOf core:Capability ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty proeth:requiresTrainingIn ;
                      owl:someValuesFrom proeth:ContinuingEducationEvent ] ;
    rdfs:label "Technical Competency"@en ;
    iao:0000115 "A professional capability related to technical skills and knowledge, requiring ongoing training."@en ;
    proeth:operationalizationNote "Link to specific training events and assessment records for competency validation."@en .

proeth:EthicalCompetency a owl:Class ;
    rdfs:subClassOf core:Capability ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty proeth:requiresTrainingIn ;
                      owl:someValuesFrom proeth:ContinuingEducationEvent ] ;
    rdfs:label "Ethical Competency"@en ;
    iao:0000115 "A professional capability related to ethical reasoning and decision-making."@en .

proeth:LeadershipCompetency a owl:Class ;
    rdfs:subClassOf core:Capability ;
    rdfs:label "Leadership Competency"@en ;
    iao:0000115 "A professional capability related to leading teams and organizations ethically."@en .

proeth:EthicalAnalysisCapability a owl:Class ;
    rdfs:subClassOf core:Capability ;
    rdfs:label "Ethical Analysis Capability"@en ;
    iao:0000115 "The capability to perform systematic ethical analysis and reasoning."@en .

###############################################################
# Temporal and Modal Scope Framework
###############################################################

# Time Interval Extensions
proeth:EthicalTimeframe a owl:Class ;
    rdfs:subClassOf time:Interval ;
    rdfs:label "Ethical Timeframe"@en ;
    iao:0000115 "A temporal interval relevant to ethical obligations, decisions, or evaluations."@en ;
    proeth:operationalizationNote "Use OWL-Time properties to specify start/end times for temporal obligations."@en .

proeth:DecisionTimeframe a owl:Class ;
    rdfs:subClassOf proeth:EthicalTimeframe ;
    rdfs:label "Decision Timeframe"@en ;
    iao:0000115 "A temporal interval within which a professional decision must be made."@en .

proeth:ComplianceTimeframe a owl:Class ;
    rdfs:subClassOf proeth:EthicalTimeframe ;
    rdfs:label "Compliance Timeframe"@en ;
    iao:0000115 "A temporal interval during which compliance with obligations is required."@en .

proeth:PrecedentTimeframe a owl:Class ;
    rdfs:subClassOf proeth:EthicalTimeframe ;
    rdfs:label "Precedent Timeframe"@en ;
    iao:0000115 "A temporal interval during which a case precedent is considered valid and applicable."@en .

###############################################################
# Assessment and Evaluation Framework
###############################################################

proeth:EthicalAssessment a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty proeth:assessesAction ;
                      owl:someValuesFrom core:Action ] ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty iao:0000136 ;  # is about
                      owl:someValuesFrom proeth:EthicalOutcome ] ;
    rdfs:label "Ethical Assessment"@en ;
    iao:0000115 "An information content entity representing evaluative output from ethical analysis, linking actions to outcomes."@en ;
    proeth:classificationGuidance "Create individuals for specific assessment instances from ProEthica AI system outputs."@en ;
    proeth:instanceExample "Individual: assessment_bridge_inspection_2025_001 rdf:type proeth:EthicalAssessment"@en ;
    proeth:operationalizationNote "Link assessment individuals to ProfessionalDecision outcomes for traceability."@en .

proeth:EthicalOutcome a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:label "Ethical Outcome"@en ;
    iao:0000115 "An information content entity describing the ethical consequences or results of professional actions."@en .

proeth:AssessmentCriteria a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:label "Assessment Criteria"@en ;
    iao:0000115 "An information content entity specifying the criteria used for ethical evaluation."@en .

proeth:EthicalScore a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty proeth:hasScoreValue ;
                      owl:someValuesFrom xsd:decimal ] ;
    rdfs:label "Ethical Score"@en ;
    iao:0000115 "A quantitative assessment score from ethical analysis systems."@en .

###############################################################
# Professional Standards Framework
###############################################################

proeth:ProfessionalStandard a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:label "Professional Standard"@en ;
    iao:0000115 "An information content entity that specifies professional requirements, guidelines, or best practices for a domain."@en .

proeth:Code a owl:Class ;
    rdfs:subClassOf proeth:ProfessionalStandard ;
    rdfs:label "Professional Code"@en ;
    iao:0000115 "A formal code of ethics or conduct established by a professional organization."@en .

proeth:Regulation a owl:Class ;
    rdfs:subClassOf proeth:ProfessionalStandard ;
    rdfs:label "Professional Regulation"@en ;
    iao:0000115 "A legally mandated standard governing professional practice."@en .

proeth:Guideline a owl:Class ;
    rdfs:subClassOf proeth:ProfessionalStandard ;
    rdfs:label "Professional Guideline"@en ;
    iao:0000115 "A recommended practice or procedure for professional activities."@en .

###############################################################
# Supporting Classes
###############################################################

proeth:SeverityLevel a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:label "Severity Level"@en ;
    iao:0000115 "A classification of the seriousness or impact of a violation or risk."@en .

proeth:EngineeringSystem a owl:Class ;
    rdfs:subClassOf bfo:0000040 ;  # BFO:material entity
    rdfs:label "Engineering System"@en ;
    iao:0000115 "A material entity that is an engineered system or artifact."@en .

proeth:EthicalConduct a owl:Class ;
    rdfs:subClassOf bfo:0000015 ;  # BFO:process
    rdfs:label "Ethical Conduct"@en ;
    iao:0000115 "Processes and behaviors that align with ethical principles."@en .

proeth:CasePrecedent a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty proeth:hasLegalStanding ;
                      owl:someValuesFrom proeth:LegalStanding ] ;
    rdfs:subClassOf [ a owl:Restriction ;
                      owl:onProperty proeth:applicableInJurisdiction ;
                      owl:someValuesFrom proeth:Jurisdiction ] ;
    rdfs:label "Case Precedent"@en ;
    iao:0000115 "An information content entity documenting a previous professional decision with legal standing and jurisdictional scope."@en .

proeth:LegalStanding a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:label "Legal Standing"@en ;
    iao:0000115 "The legal authority or precedential value of a case or decision."@en .

proeth:Jurisdiction a owl:Class ;
    rdfs:subClassOf bfo:0000029 ;  # BFO:site
    rdfs:label "Jurisdiction"@en ;
    iao:0000115 "A spatial region with defined legal or professional authority boundaries."@en .

proeth:ProfessionalDecision a owl:Class ;
    rdfs:subClassOf iao:0000030 ;  # IAO:information content entity
    rdfs:label "Professional Decision"@en ;
    iao:0000115 "An information content entity representing a professional decision made in practice."@en .

###############################################################
# Specialized Object Properties (not in core)
###############################################################

# Temporal Properties
proeth:hasTemporalScope a owl:ObjectProperty ;
    rdfs:subPropertyOf bfo:0000008 ;  # occurs during
    rdfs:domain [ owl:unionOf ( core:Obligation proeth:Permission proeth:Prohibition ) ] ;
    rdfs:range time:Interval ;
    rdfs:label "has temporal scope"@en ;
    iao:0000115 "Relates a deontic statement to its temporal validity period."@en .

proeth:validDuring a owl:ObjectProperty ;
    rdfs:subPropertyOf proeth:hasTemporalScope ;
    rdfs:domain core:Obligation ;
    rdfs:range time:Interval ;
    rdfs:label "valid during"@en ;
    iao:0000115 "Specifies the temporal interval during which an obligation is in effect."@en .

# Assessment Properties
proeth:assessesAction a owl:ObjectProperty ;
    rdfs:domain proeth:EthicalAssessment ;
    rdfs:range core:Action ;
    rdfs:label "assesses action"@en ;
    iao:0000115 "Relates an ethical assessment to the action it evaluates."@en .

proeth:hasAssessmentOutcome a owl:ObjectProperty ;
    rdfs:domain proeth:EthicalAssessment ;
    rdfs:range proeth:EthicalOutcome ;
    rdfs:label "has assessment outcome"@en ;
    iao:0000115 "Links an ethical assessment to its evaluated outcome."@en .

proeth:basedOnCriteria a owl:ObjectProperty ;
    rdfs:domain proeth:EthicalAssessment ;
    rdfs:range proeth:AssessmentCriteria ;
    rdfs:label "based on criteria"@en ;
    iao:0000115 "Relates an assessment to the criteria used for evaluation."@en .

proeth:linkedToProfessionalDecision a owl:ObjectProperty ;
    rdfs:domain proeth:EthicalAssessment ;
    rdfs:range proeth:ProfessionalDecision ;
    rdfs:label "linked to professional decision"@en ;
    iao:0000115 "Links an ethical assessment to professional decisions for traceability."@en .

# Legal and Jurisdictional Properties
proeth:hasLegalStanding a owl:ObjectProperty ;
    rdfs:domain proeth:CasePrecedent ;
    rdfs:range proeth:LegalStanding ;
    rdfs:label "has legal standing"@en ;
    iao:0000115 "Relates a case precedent to its legal authority or precedential value."@en .

proeth:applicableInJurisdiction a owl:ObjectProperty ;
    rdfs:domain proeth:CasePrecedent ;
    rdfs:range proeth:Jurisdiction ;
    rdfs:label "applicable in jurisdiction"@en ;
    iao:0000115 "Specifies the jurisdictions where a case precedent applies."@en .

# Training and Competency Properties
proeth:requiresTrainingIn a owl:ObjectProperty ;
    rdfs:domain core:Capability ;
    rdfs:range proeth:ContinuingEducationEvent ;
    rdfs:label "requires training in"@en ;
    iao:0000115 "Links a professional capability to required training events."@en .

# Enhanced Deontic Properties
proeth:enabledByPermission a owl:ObjectProperty ;
    rdfs:domain proeth:EthicallyOptionalAction ;
    rdfs:range proeth:Permission ;
    rdfs:label "enabled by permission"@en ;
    iao:0000115 "Links an optional action to the permission that enables it."@en .

proeth:violatesProhibition a owl:ObjectProperty ;
    rdfs:domain proeth:EthicallyProhibitedAction ;
    rdfs:range proeth:Prohibition ;
    rdfs:label "violates prohibition"@en ;
    iao:0000115 "Links a prohibited action to the prohibition it violates."@en .

proeth:violatesObligation a owl:ObjectProperty ;
    rdfs:domain proeth:ViolationEvent ;
    rdfs:range core:Obligation ;
    rdfs:label "violates obligation"@en ;
    iao:0000115 "Links a violation event to the obligation that was breached."@en .

proeth:conditionallyAppliesWhen a owl:ObjectProperty ;
    rdfs:subPropertyOf iao:0000136 ;  # is about
    rdfs:domain proeth:ConditionalObligation ;
    rdfs:range core:State ;
    rdfs:label "conditionally applies when"@en ;
    iao:0000115 "Relates a conditional obligation to states that trigger its application."@en .

proeth:overrides a owl:ObjectProperty ;
    rdfs:domain proeth:OverridingObligation ;
    rdfs:range core:Obligation ;
    rdfs:label "overrides"@en ;
    iao:0000115 "Relates an overriding obligation to obligations it takes precedence over."@en .

proeth:triggersObligation a owl:ObjectProperty ;
    rdfs:subPropertyOf ro:0000012 ;  # causally upstream of
    rdfs:domain proeth:TriggeringEvent ;
    rdfs:range core:Obligation ;
    rdfs:label "triggers obligation"@en ;
    iao:0000115 "Relates a triggering event to obligations it activates."@en .

###############################################################
# Data Properties
###############################################################

proeth:hasScoreValue a owl:DatatypeProperty ;
    rdfs:domain proeth:EthicalScore ;
    rdfs:range xsd:decimal ;
    rdfs:label "has score value"@en ;
    iao:0000115 "The numerical value of an ethical assessment score."@en .

proeth:hasSeverityLevel a owl:DatatypeProperty ;
    rdfs:domain proeth:ViolationEvent ;
    rdfs:range xsd:string ;
    rdfs:label "has severity level"@en ;
    iao:0000115 "The severity classification of a violation (e.g., 'minor', 'major', 'critical')."@en .

proeth:hasConfidenceScore a owl:DatatypeProperty ;
    rdfs:domain proeth:EthicalAssessment ;
    rdfs:range xsd:decimal ;
    rdfs:label "has confidence score"@en ;
    iao:0000115 "The confidence level of an ethical assessment (0.0 to 1.0)."@en .

###############################################################
# SHACL Validation Constraints
###############################################################

proeth:RoleObligationConstraint a sh:NodeShape ;
    sh:targetClass proeth:ProfessionalRole ;
    sh:property [
        sh:path core:hasObligation ;
        sh:minCount 1 ;
        sh:message "Every professional role must have at least one obligation."@en ;
    ] ;
    sh:property [
        sh:path core:hasCapability ;
        sh:minCount 1 ;
        sh:message "Every professional role must have at least one associated capability."@en ;
    ] .

proeth:ConditionalObligationConstraint a sh:NodeShape ;
    sh:targetClass proeth:ConditionalObligation ;
    sh:property [
        sh:path proeth:conditionallyAppliesWhen ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:class core:State ;
        sh:message "Every conditional obligation must have exactly one triggering state."@en ;
    ] .

proeth:EthicalAssessmentConstraint a sh:NodeShape ;
    sh:targetClass proeth:EthicalAssessment ;
    sh:property [
        sh:path proeth:assessesAction ;
        sh:minCount 1 ;
        sh:class core:Action ;
        sh:message "Every ethical assessment must assess at least one action."@en ;
    ] ;
    sh:property [
        sh:path proeth:hasConfidenceScore ;
        sh:datatype xsd:decimal ;
        sh:minInclusive 0.0 ;
        sh:maxInclusive 1.0 ;
        sh:message "Confidence score must be between 0.0 and 1.0."@en ;
    ] .

###############################################################
# Disjointness Axioms (Enhanced)
###############################################################

# Core disjointness
[] a owl:AllDisjointClasses ;
   owl:members ( proeth:MaterialResource proeth:InformationResource ) .

[] a owl:AllDisjointClasses ;
   owl:members ( proeth:ConditionalObligation proeth:OverridingObligation proeth:PrimafacieObligation ) .

[] a owl:AllDisjointClasses ;
   owl:members ( proeth:Permission proeth:Prohibition ) .

[] a owl:AllDisjointClasses ;
   owl:members ( proeth:Code proeth:Regulation proeth:Guideline ) .

[] a owl:AllDisjointClasses ;
   owl:members ( proeth:FundamentalPrinciple proeth:ProfessionalPrinciple ) .

[] a owl:AllDisjointClasses ;
   owl:members ( proeth:EnvironmentalState proeth:OrganizationalState proeth:LegalState proeth:TechnicalState ) .

# Enhanced disjointness for new classes
[] a owl:AllDisjointClasses ;
   owl:members ( proeth:EthicallyRequiredAction proeth:EthicallyOptionalAction proeth:EthicallyProhibitedAction ) .

[] a owl:AllDisjointClasses ;
   owl:members ( proeth:TechnicalCompetency proeth:EthicalCompetency proeth:LeadershipCompetency ) .

[] a owl:AllDisjointClasses ;
   owl:members ( proeth:ExplicitPermission proeth:ImplicitPermission ) .

[] a owl:AllDisjointClasses ;
   owl:members ( proeth:AbsoluteProhibition proeth:ConditionalProhibition ) .

# Temporal framework disjointness
[] a owl:AllDisjointClasses ;
   owl:members ( proeth:DecisionTimeframe proeth:ComplianceTimeframe proeth:PrecedentTimeframe ) .

# Assessment framework disjointness  
[] a owl:AllDisjointClasses ;
   owl:members ( proeth:EthicalAssessment proeth:EthicalOutcome proeth:AssessmentCriteria proeth:EthicalScore ) .

# Agent type disjointness
[] a owl:AllDisjointClasses ;
   owl:members ( proeth:EthicsReviewer proeth:AIAdvisor proeth:Engineer ) .
"""
    
    return content


def get_db_connection():
    """Get database connection using same pattern as working scripts."""
    return psycopg2.connect(
        host='localhost',
        port=5432,
        database='ontserve',
        user='ontserve_user',
        password='ontserve_development_password'
    )


def restructure_intermediate_ontology():
    """Main function to restructure the intermediate ontology with core import."""
    
    try:
        print("🔄 Creating restructured ProEthica Intermediate ontology...")
        
        # Get the restructured content
        new_content = create_restructured_intermediate_content()
        
        # Connect to database
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if intermediate ontology exists
        cur.execute("SELECT id FROM ontologies WHERE name = %s", ("proethica-intermediate",))
        result = cur.fetchone()
        
        if not result:
            print("❌ ProEthica Intermediate ontology not found!")
            cur.close()
            conn.close()
            return False
            
        ontology_id = result[0]
        
        # Create a backup version first
        backup_name = f"proethica-intermediate-backup-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"💾 Creating backup as: {backup_name}")
        
        # Get current content for backup
        cur.execute("SELECT content FROM ontology_versions WHERE ontology_id = %s AND is_current = true", (ontology_id,))
        current_content = cur.fetchone()
        
        if current_content:
            # Create backup version
            cur.execute("""
                INSERT INTO ontology_versions (ontology_id, version_number, content, created_by, is_current)
                VALUES (%s, (SELECT COALESCE(MAX(version_number), 0) + 1 FROM ontology_versions WHERE ontology_id = %s), %s, %s, %s)
            """, (ontology_id, ontology_id, current_content[0], 'restructure_script', False))
        
        # Update current version to not be current
        cur.execute("UPDATE ontology_versions SET is_current = false WHERE ontology_id = %s", (ontology_id,))
        
        # Create new version with restructured content
        cur.execute("""
            INSERT INTO ontology_versions (ontology_id, version_number, content, created_by, is_current)
            VALUES (%s, (SELECT COALESCE(MAX(version_number), 0) + 1 FROM ontology_versions WHERE ontology_id = %s), %s, %s, %s)
        """, (ontology_id, ontology_id, new_content, 'restructure_script', True))
        
        # Commit changes
        conn.commit()
        cur.close()
        conn.close()
        
        print("✅ Successfully restructured ProEthica Intermediate ontology!")
        print("📊 Changes made:")
        print("   - Added import: <http://proethica.org/ontology/core>")
        print("   - Changed base classes to extend core: instead of BFO: directly")
        print("   - Removed duplicate property definitions from core")
        print("   - Kept all specialized enhancements and SHACL constraints")
        print("   - Updated version to 8.1.0")
        print()
        print("🎯 Expected visualization improvements:")
        print("   - Core concepts (Role, Principle, Obligation, etc.) visible as parent classes")
        print("   - Clear hierarchical relationship: BFO → Core → Intermediate")
        print("   - Properties properly connected through inheritance")
        print()
        print("🌐 View updated ontology at:")
        print("   http://localhost:5003/ontology/proethica-intermediate")
        print("   http://localhost:5003/editor/ontology/proethica-intermediate/visualize")
        
        return True
        
    except Exception as e:
        print(f"❌ Error restructuring ontology: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False


if __name__ == "__main__":
    print("🚀 ProEthica Intermediate Ontology Restructuring")
    print("=" * 50)
    
    success = restructure_intermediate_ontology()
    
    if success:
        print("\n✅ Restructuring completed successfully!")
        print("\nNext steps:")
        print("1. Check the visualization to see the hierarchical structure")
        print("2. Verify that properties are properly inherited from core")
        print("3. Test ontology consistency with reasoner")
    else:
        print("\n❌ Restructuring failed!")
        print("Check the error messages above and try again.")
    
    print("\n" + "=" * 50)
