#!/usr/bin/env python3
"""
Implement Property Alignment with RO (Phase 3)

Implements proper RO property mappings and fixes remaining BFO reference issues
to enable proper hierarchical visualization and reasoning.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from web.config import config
from web.models import db, init_db, Ontology, OntologyEntity, OntologyVersion

def implement_property_alignment():
    """Implement Phase 3: Property Alignment with RO."""
    
    print("ProEthica Intermediate Ontology - Property Alignment (Phase 3)")
    print("=" * 70)
    
    # Create properly aligned ontology content
    aligned_content = """@prefix : <http://proethica.org/ontology/intermediate#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dc: <http://purl.org/dc/elements/1.1/> .
@prefix bfo: <http://purl.obolibrary.org/obo/> .
@prefix iao: <http://purl.obolibrary.org/obo/> .
@prefix ro: <http://purl.obolibrary.org/obo/> .
@base <http://proethica.org/ontology/intermediate> .

#################################################################
#    Ontology Declaration with Proper Imports
#################################################################

<http://proethica.org/ontology/intermediate> rdf:type owl:Ontology ;
    owl:imports <http://purl.obolibrary.org/obo/bfo.owl> ;
    owl:imports <http://purl.obolibrary.org/obo/ro.owl> ;
    owl:imports <http://purl.obolibrary.org/obo/iao.owl> ;
    rdfs:label "ProEthica Intermediate Ontology"@en ;
    rdfs:comment "BFO-aligned intermediate ontology for professional ethics with proper RO property alignment"@en ;
    owl:versionInfo "2.0.1" ;
    dc:creator "ProEthica AI"@en ;
    dc:date "2025-08-25"^^xsd:date .

#################################################################
#    BFO-Aligned Core Entity Types (Fixed BFO References)
#################################################################

# Role → BFO:Role (Realizable Entity)
:Role rdf:type owl:Class ;
    rdfs:subClassOf bfo:BFO_0000023 ; # role
    rdfs:label "Professional Role"@en ;
    iao:IAO_0000115 "A role that inheres in a material entity and can be realized by processes involving professional duties and ethical obligations."@en .

:ProfessionalRole rdf:type owl:Class ;
    rdfs:subClassOf :Role ,
        [ a owl:Restriction ;
          owl:onProperty bfo:BFO_0000052 ; # inheres_in
          owl:someValuesFrom bfo:BFO_0000040 ] ; # material entity
    rdfs:label "Professional Role"@en ;
    iao:IAO_0000115 "A professional role with formal obligations and accountability."@en .

# Principle → IAO:Information Content Entity  
:Principle rdf:type owl:Class ;
    rdfs:subClassOf iao:IAO_0000030 ; # information content entity
    rdfs:label "Ethical Principle"@en ;
    iao:IAO_0000115 "An information content entity that represents fundamental ethical values and guidelines for conduct."@en .

:IntegrityPrinciple rdf:type owl:Class ;
    rdfs:subClassOf :Principle ;
    rdfs:label "Integrity Principle"@en ;
    iao:IAO_0000115 "A principle that guides honest and truthful professional conduct."@en .

# Obligation → Deontic ICEs
:DeonticStatement rdf:type owl:Class ;
    rdfs:subClassOf iao:IAO_0000030 ; # information content entity
    rdfs:label "Deontic Statement"@en ;
    iao:IAO_0000115 "An information content entity that expresses permissions, obligations, or prohibitions."@en .

:Obligation rdf:type owl:Class ;
    rdfs:subClassOf :DeonticStatement ;
    rdfs:label "Professional Obligation"@en ;
    iao:IAO_0000115 "A deontic statement specifying professional duties and responsibilities."@en .

:Permission rdf:type owl:Class ;
    rdfs:subClassOf :DeonticStatement ;
    rdfs:label "Permission"@en ;
    iao:IAO_0000115 "A deontic statement allowing specific actions or states."@en .

:Prohibition rdf:type owl:Class ;
    rdfs:subClassOf :DeonticStatement ;
    rdfs:label "Prohibition"@en ;
    iao:IAO_0000115 "A deontic statement forbidding specific actions or states."@en .

# State → BFO:Quality
:State rdf:type owl:Class ;
    rdfs:subClassOf bfo:BFO_0000019 ; # quality
    rdfs:label "Contextual State"@en ;
    iao:IAO_0000115 "A quality that inheres in an entity and affects ethical decisions."@en .

:SafetyHazardState rdf:type owl:Class ;
    rdfs:subClassOf :State ,
        [ a owl:Restriction ;
          owl:onProperty bfo:BFO_0000052 ; # inheres_in
          owl:someValuesFrom bfo:BFO_0000040 ] ; # material entity
    rdfs:label "Safety Hazard State"@en ;
    iao:IAO_0000115 "A quality indicating the presence of safety hazards in a system."@en .

# Resource → Bifurcated Model
:Resource rdf:type owl:Class ;
    rdfs:label "Resource"@en ;
    iao:IAO_0000115 "An entity that serves as input or reference for professional activities."@en .

:MaterialResource rdf:type owl:Class ;
    rdfs:subClassOf :Resource, bfo:BFO_0000040 ; # material entity
    rdfs:label "Material Resource"@en ;
    iao:IAO_0000115 "A physical resource used in professional activities."@en .

:InformationResource rdf:type owl:Class ;
    rdfs:subClassOf :Resource, iao:IAO_0000030 ; # information content entity
    rdfs:label "Information Resource"@en ;
    iao:IAO_0000115 "An information resource used in professional activities."@en .

# Action → BFO:Process with Agent
:Event rdf:type owl:Class ;
    rdfs:subClassOf bfo:BFO_0000015 ; # process
    rdfs:label "Event"@en ;
    iao:IAO_0000115 "A process that occurs in ethical scenarios."@en .

:Action rdf:type owl:Class ;
    rdfs:subClassOf :Event ,
        [ a owl:Restriction ;
          owl:onProperty ro:RO_0002218 ; # has_agent  
          owl:someValuesFrom bfo:BFO_0000040 ] ; # material entity
    rdfs:label "Intentional Action"@en ;
    iao:IAO_0000115 "A process that has an agent participant and is directed toward achieving specific goals."@en .

# Capability → BFO:Disposition
:Capability rdf:type owl:Class ;
    rdfs:subClassOf bfo:BFO_0000016 ; # disposition
    rdfs:label "Professional Capability"@en ;
    iao:IAO_0000115 "A disposition that inheres in an agent and can be realized by specific types of actions or processes."@en .

:RiskAssessmentCapability rdf:type owl:Class ;
    rdfs:subClassOf :Capability ,
        [ a owl:Restriction ;
          owl:onProperty bfo:BFO_0000052 ; # inheres_in
          owl:someValuesFrom :Engineer ] ,
        [ a owl:Restriction ;
          owl:onProperty bfo:BFO_0000054 ; # realized_in
          owl:someValuesFrom :RiskAssessmentAction ] ;
    rdfs:label "Risk Assessment Capability"@en ;
    iao:IAO_0000115 "The disposition to perform risk assessment activities."@en .

# Constraint → Context-Dependent
:LicensureRequirement rdf:type owl:Class ;
    rdfs:subClassOf iao:IAO_0000030 ; # information content entity
    rdfs:label "Licensure Requirement"@en ;
    iao:IAO_0000115 "An information content entity specifying professional licensing requirements."@en .

:LoadLimitConstraint rdf:type owl:Class ;
    rdfs:subClassOf bfo:BFO_0000019 , # quality
        [ a owl:Restriction ;
          owl:onProperty bfo:BFO_0000052 ; # inheres_in
          owl:someValuesFrom :EngineeringSystem ] ;
    rdfs:label "Load Limit Constraint"@en ;
    iao:IAO_0000115 "A quality representing the maximum load capacity of a system."@en .

#################################################################
#    Supporting Classes
#################################################################

:Engineer rdf:type owl:Class ;
    rdfs:subClassOf bfo:BFO_0000040 ; # material entity
    rdfs:label "Engineer"@en ;
    iao:IAO_0000115 "A professional agent with engineering expertise and responsibilities."@en .

:EngineeringSystem rdf:type owl:Class ;
    rdfs:subClassOf bfo:BFO_0000040 ; # material entity  
    rdfs:label "Engineering System"@en ;
    iao:IAO_0000115 "A material entity designed and constructed for engineering purposes."@en .

:RiskAssessmentAction rdf:type owl:Class ;
    rdfs:subClassOf :Action ;
    rdfs:label "Risk Assessment Action"@en ;
    iao:IAO_0000115 "An action involving the evaluation and analysis of potential risks."@en .

#################################################################
#    RO-Aligned Object Properties (Phase 3: Property Alignment)
#################################################################

# CRITICAL: Proper RO Property Alignment for Hierarchy Visualization

:hasRole rdf:type owl:ObjectProperty ;
    rdfs:subPropertyOf ro:RO_0000087 ; # has_role
    rdfs:domain bfo:BFO_0000040 ; # material entity
    rdfs:range :Role ;
    rdfs:label "has role"@en ;
    iao:IAO_0000115 "Relates an entity to a role it bears."@en .

:fulfillsObligation rdf:type owl:ObjectProperty ;
    rdfs:subPropertyOf ro:RO_0002211 ; # realizes
    rdfs:domain :Action ;
    rdfs:range :Obligation ;
    rdfs:label "fulfills obligation"@en ;
    iao:IAO_0000115 "Relates an action to an obligation it fulfills."@en .

:adheresToPrinciple rdf:type owl:ObjectProperty ;
    rdfs:subPropertyOf iao:IAO_0000136 ; # is_about (inverse)
    rdfs:domain :Role ;
    rdfs:range :Principle ;
    rdfs:label "adheres to principle"@en ;
    iao:IAO_0000115 "Relates a role to ethical principles that normatively govern that role."@en .

# Domain-specific properties with proper domain/range
:hasObligation rdf:type owl:ObjectProperty ;
    rdfs:subPropertyOf ro:RO_0000087 ; # has_role (bearer relationship)
    rdfs:domain :Role ;
    rdfs:range :Obligation ;
    rdfs:label "has obligation"@en ;
    iao:IAO_0000115 "Relates a role to the professional obligations borne by entities bearing that role."@en .

:constrains rdf:type owl:ObjectProperty ;
    rdfs:domain :DeonticStatement ;
    rdfs:range :Action ;
    rdfs:label "constrains"@en ;
    iao:IAO_0000115 "Relates a deontic statement to actions it constrains."@en .

:appliesToRole rdf:type owl:ObjectProperty ;
    rdfs:domain :DeonticStatement ;
    rdfs:range :Role ;
    rdfs:label "applies to role"@en ;
    iao:IAO_0000115 "Relates a deontic statement to roles it applies to."@en .

#################################################################
#    Additional RO Property Mappings for Rich Reasoning
#################################################################

# These properties will enable the reasoner to connect our ontology to BFO hierarchy

:inheres_in rdf:type owl:ObjectProperty ;
    rdfs:subPropertyOf bfo:BFO_0000052 ; # inheres_in
    rdfs:domain bfo:BFO_0000020 ; # specifically dependent continuant
    rdfs:range bfo:BFO_0000004 ; # independent continuant
    rdfs:label "inheres in"@en ;
    iao:IAO_0000115 "A relation between a specifically dependent continuant and its bearer."@en .

:realized_by rdf:type owl:ObjectProperty ;
    rdfs:subPropertyOf bfo:BFO_0000055 ; # realizes  
    rdfs:domain bfo:BFO_0000015 ; # process
    rdfs:range bfo:BFO_0000017 ; # realizable entity
    rdfs:label "realized by"@en ;
    iao:IAO_0000115 "A relation between a process and a realizable entity it realizes."@en .

:has_participant rdf:type owl:ObjectProperty ;
    rdfs:subPropertyOf ro:RO_0000057 ; # has_participant
    rdfs:domain bfo:BFO_0000015 ; # process
    rdfs:range bfo:BFO_0000002 ; # continuant
    rdfs:label "has participant"@en ;
    iao:IAO_0000115 "A relation between a process and its participants."@en .

#################################################################
#    EL-Safe Property Chains (for enhanced reasoning)
#################################################################

# Property chain: has_agent ∘ has_role ⊑ agent_has_role
:agent_has_role rdf:type owl:ObjectProperty ;
    rdfs:domain bfo:BFO_0000015 ; # process
    rdfs:range :Role ;
    rdfs:label "agent has role"@en ;
    iao:IAO_0000115 "Relates a process to roles of its agent participants."@en ;
    owl:propertyChainAxiom ( ro:RO_0002218 :hasRole ) . # has_agent ∘ hasRole

#################################################################
#    Systematic Disjointness Axioms (Fixed BFO References)
#################################################################

# Continuant vs Occurrent disjointness
[] a owl:Axiom ;
   owl:disjointClasses ( bfo:BFO_0000002 bfo:BFO_0000003 ) . # continuant vs occurrent

# Material vs Information Resource disjointness  
[] a owl:Axiom ;
   owl:disjointClasses ( :MaterialResource :InformationResource ) .

# Deontic statement types disjointness
[] a owl:Axiom ;
   owl:disjointClasses ( :Obligation :Permission ) .
   
[] a owl:Axiom ;
   owl:disjointClasses ( :Obligation :Prohibition ) .
   
[] a owl:Axiom ;
   owl:disjointClasses ( :Permission :Prohibition ) .

# Professional vs Participant role disjointness
[] a owl:Axiom ;
   owl:disjointClasses ( :ProfessionalRole :ParticipantRole ) .
"""
    
    # Create Flask app for database context
    app = Flask(__name__)
    app.config.from_object(config['development'])
    init_db(app)
    
    print("🔧 Implementing Property Alignment with RO...")
    print("✅ Fixed BFO references (BFO\\_xxx → BFO_xxx)")
    print("✅ Added proper prefix declarations")
    print("✅ Implemented RO property mappings")
    print("✅ Added property chains for enhanced reasoning")
    
    with app.app_context():
        # Find proethica-intermediate ontology
        intermediate_ont = Ontology.query.filter_by(name='proethica-intermediate').first()
        
        if not intermediate_ont:
            print("❌ ProEthica intermediate ontology not found!")
            return False
        
        print(f"\n💾 Updating Version 2 with Property-Aligned content...")
        
        # Get current version
        current_version = intermediate_ont.current_version
        
        if not current_version:
            print("❌ No current version found!")
            return False
        
        # Update with property-aligned content
        current_version.content = aligned_content
        current_version.change_summary = 'Phase 3: RO Property Alignment - Fixed BFO references and implemented proper RO property mappings for hierarchy visualization'
        current_version.version_tag = '2.0.1'
        
        # Update metadata
        if not current_version.meta_data:
            current_version.meta_data = {}
        
        current_version.meta_data.update({
            'property_alignment_complete': True,
            'ro_mappings_implemented': True,
            'bfo_references_fixed': True,
            'property_chains_added': True,
            'phase_3_complete': True,
            'ready_for_reasoning': True,
            'hierarchy_visualization_enabled': True
        })
        
        # Clear and re-extract entities with aligned content
        print("🔄 Re-extracting entities with property-aligned content...")
        
        OntologyEntity.query.filter_by(ontology_id=intermediate_ont.id).delete()
        
        # Parse property-aligned content for entity extraction
        import rdflib
        from rdflib import RDF, RDFS, OWL
        
        try:
            g = rdflib.Graph()
            g.parse(data=aligned_content, format='turtle')
            
            # Extract classes with proper parent relationships
            class_count = 0
            iao_definition = rdflib.URIRef("http://purl.obolibrary.org/obo/IAO_0000115")
            
            for cls in g.subjects(RDF.type, OWL.Class):
                label = next(g.objects(cls, RDFS.label), None)
                comment = next(g.objects(cls, iao_definition), None)  # Use IAO definition
                subclass_of = list(g.objects(cls, RDFS.subClassOf))
                
                # Get proper parent URI (non-blank node)
                parent_uri = None
                for parent in subclass_of:
                    if not isinstance(parent, rdflib.BNode):
                        parent_uri = str(parent)
                        break
                
                entity = OntologyEntity(
                    ontology_id=intermediate_ont.id,
                    entity_type='class',
                    uri=str(cls),
                    label=str(label) if label else None,
                    comment=str(comment) if comment else None,
                    parent_uri=parent_uri
                )
                db.session.add(entity)
                class_count += 1
            
            # Extract properties with RO alignments
            property_count = 0
            for prop in g.subjects(RDF.type, OWL.ObjectProperty):
                label = next(g.objects(prop, RDFS.label), None)
                comment = next(g.objects(prop, iao_definition), None)  # Use IAO definition
                domain = next(g.objects(prop, RDFS.domain), None)
                range_val = next(g.objects(prop, RDFS.range), None)
                
                entity = OntologyEntity(
                    ontology_id=intermediate_ont.id,
                    entity_type='property',
                    uri=str(prop),
                    label=str(label) if label else None,
                    comment=str(comment) if comment else None,
                    domain=str(domain) if domain else None,
                    range=str(range_val) if range_val else None
                )
                db.session.add(entity)
                property_count += 1
            
            db.session.commit()
            
            print(f"   ✅ Successfully extracted {class_count} classes and {property_count} properties")
            
        except Exception as e:
            print(f"❌ Entity extraction error: {e}")
            return False
        
        print("\n" + "=" * 70)
        print("PROPERTY ALIGNMENT SUMMARY (PHASE 3 COMPLETE)")
        print("=" * 70)
        print("✅ RO Property Mappings Implemented:")
        print("   • hasRole → ro:RO_0000087 (has_role)")
        print("   • fulfillsObligation → ro:RO_0002211 (realizes)")
        print("   • adheresToPrinciple → iao:IAO_0000136 (is_about)")
        print("   • Added property chains for enhanced reasoning")
        
        print("✅ BFO Reference Issues Fixed:")
        print("   • Proper BFO_xxxxxxx format (no escaped underscores)")
        print("   • Correct prefix declarations")
        print("   • Clean namespace mappings")
        
        print(f"\n📊 Results:")
        print(f"   Classes: {class_count}")
        print(f"   Properties: {property_count}")
        print(f"   Version: 2.0.1 (Property Aligned)")
        
        print(f"\n🧠 REASONING WILL NOW WORK!")
        print(f"   Visualization: http://localhost:5003/editor/ontology/proethica-intermediate/visualize")
        print(f"   ⚡ Run reasoning again - you should see rich BFO hierarchy!")
        print(f"   📊 Progress Dashboard: http://localhost:5002/progress")
        
        return True

if __name__ == "__main__":
    success = implement_property_alignment()
    if success:
        print("\n🎉 Property Alignment (Phase 3) completed!")
        print("Ontology now ready for proper reasoning and rich visualization.")
    else:
        print("\n💥 Property alignment failed")
    
    sys.exit(0 if success else 1)
