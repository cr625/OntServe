#!/usr/bin/env python3
"""
BFO Compliance Validation Rules for ProEthica Intermediate Ontology

This module provides comprehensive validation rules for ensuring BFO-faithful
alignment of the ProEthica Intermediate Ontology entities.
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class BFOCategory(Enum):
    """BFO top-level categories for entity classification."""
    CONTINUANT = "bfo:Continuant"
    OCCURRENT = "bfo:Occurrent"
    SPECIFICALLY_DEPENDENT_CONTINUANT = "bfo:SpecificallyDependentContinuant"
    GENERICALLY_DEPENDENT_CONTINUANT = "bfo:GenericallyDependentContinuant"
    INDEPENDENT_CONTINUANT = "bfo:IndependentContinuant"
    MATERIAL_ENTITY = "bfo:MaterialEntity"
    PROCESS = "bfo:Process"
    REALIZABLE_ENTITY = "bfo:RealizableEntity"
    ROLE = "bfo:Role"
    DISPOSITION = "bfo:Disposition"
    QUALITY = "bfo:Quality"


@dataclass
class ValidationRule:
    """Represents a single BFO compliance validation rule."""
    rule_id: str
    name: str
    description: str
    severity: str  # 'error', 'warning', 'info'
    bfo_requirement: str
    validation_function: str
    entity_types: List[str]
    examples: List[str]


@dataclass
class ValidationResult:
    """Result of BFO compliance validation."""
    rule_id: str
    entity_uri: str
    entity_label: str
    compliant: bool
    severity: str
    message: str
    recommendations: List[str]
    bfo_category: Optional[str] = None


class BFOComplianceValidator:
    """Main validator for BFO compliance rules."""
    
    def __init__(self):
        """Initialize the BFO compliance validator."""
        self.validation_rules = self._initialize_validation_rules()
        logger.info(f"BFO Compliance Validator initialized with {len(self.validation_rules)} rules")
    
    def _initialize_validation_rules(self) -> List[ValidationRule]:
        """Initialize all BFO compliance validation rules."""
        rules = [
            # Rule 1: Role entities must inherit from bfo:Role
            ValidationRule(
                rule_id="BFO_001",
                name="Role BFO Inheritance",
                description="Role entities must be subclasses of bfo:Role",
                severity="error",
                bfo_requirement="Roles are realizable entities that inhere in material entities",
                validation_function="validate_role_inheritance",
                entity_types=["role_entities"],
                examples=["EngineerRole", "ClientRole", "ProfessionalRole"]
            ),
            
            # Rule 2: Principles must inherit from iao:InformationContentEntity
            ValidationRule(
                rule_id="BFO_002", 
                name="Principle ICE Inheritance",
                description="Principle entities must be subclasses of iao:InformationContentEntity",
                severity="error",
                bfo_requirement="Principles are information content entities about ethical conduct",
                validation_function="validate_principle_inheritance",
                entity_types=["principle_entities"],
                examples=["IntegrityPrinciple", "PublicWelfarePrinciple", "SustainabilityPrinciple"]
            ),
            
            # Rule 3: Actions must inherit from bfo:Process
            ValidationRule(
                rule_id="BFO_003",
                name="Action Process Inheritance", 
                description="Action entities must be subclasses of bfo:Process with agent restrictions",
                severity="error",
                bfo_requirement="Actions are processes with agent participants",
                validation_function="validate_action_inheritance",
                entity_types=["action_entities"],
                examples=["DesignAction", "AssessmentAction", "ReportingAction"]
            ),
            
            # Rule 4: Events must inherit from bfo:Process
            ValidationRule(
                rule_id="BFO_004",
                name="Event Process Inheritance",
                description="Event entities must be subclasses of bfo:Process",
                severity="error", 
                bfo_requirement="Events are temporal processes in professional contexts",
                validation_function="validate_event_inheritance",
                entity_types=["event_entities"],
                examples=["SafetyIncident", "ContractualEvent", "MilestoneEvent"]
            ),
            
            # Rule 5: Capabilities must inherit from bfo:Disposition
            ValidationRule(
                rule_id="BFO_005",
                name="Capability Disposition Inheritance",
                description="Capability entities must be subclasses of bfo:Disposition",
                severity="error",
                bfo_requirement="Capabilities are dispositions that inhere in agents",
                validation_function="validate_capability_inheritance", 
                entity_types=["capability_entities"],
                examples=["TechnicalCapability", "RiskAssessmentCapability"]
            ),
            
            # Rule 6: States must inherit from bfo:Quality
            ValidationRule(
                rule_id="BFO_006",
                name="State Quality Inheritance",
                description="State entities must be subclasses of bfo:Quality",
                severity="error",
                bfo_requirement="States are qualities that inhere in material entities",
                validation_function="validate_state_inheritance",
                entity_types=["state_entities"],
                examples=["SafetyHazardState", "OperationalState"]
            ),
            
            # Rule 7: Material Resources must inherit from bfo:MaterialEntity
            ValidationRule(
                rule_id="BFO_007",
                name="Material Resource Entity Inheritance",
                description="Material resource entities must be subclasses of bfo:MaterialEntity",
                severity="error",
                bfo_requirement="Material resources are physical entities",
                validation_function="validate_material_resource_inheritance",
                entity_types=["resource_material"],
                examples=["Tool", "Equipment", "Infrastructure"]
            ),
            
            # Rule 8: Information Resources must inherit from iao:InformationContentEntity
            ValidationRule(
                rule_id="BFO_008",
                name="Information Resource ICE Inheritance",
                description="Information resource entities must be subclasses of iao:InformationContentEntity",
                severity="error",
                bfo_requirement="Information resources are information content entities",
                validation_function="validate_information_resource_inheritance",
                entity_types=["resource_information"],
                examples=["TechnicalSpecification", "Report", "Standard"]
            ),
            
            # Rule 9: Rule Constraints must inherit from iao:InformationContentEntity
            ValidationRule(
                rule_id="BFO_009",
                name="Rule Constraint ICE Inheritance",
                description="Rule constraint entities must be subclasses of iao:InformationContentEntity",
                severity="error",
                bfo_requirement="Rule constraints are documented rules and regulations",
                validation_function="validate_rule_constraint_inheritance",
                entity_types=["constraint_rule"],
                examples=["LicensureRequirement", "SafetyStandard"]
            ),
            
            # Rule 10: System Constraints must inherit from bfo:Quality
            ValidationRule(
                rule_id="BFO_010",
                name="System Constraint Quality Inheritance",
                description="System constraint entities must be subclasses of bfo:Quality",
                severity="error",
                bfo_requirement="System constraints are qualities of systems representing limitations",
                validation_function="validate_system_constraint_inheritance",
                entity_types=["constraint_system"],
                examples=["LoadLimitConstraint", "BudgetLimitConstraint"]
            ),
            
            # Rule 11: Obligations must have deontic nature (ICE or Disposition)
            ValidationRule(
                rule_id="BFO_011",
                name="Obligation Deontic Nature",
                description="Obligation entities must inherit from either iao:InformationContentEntity or bfo:Disposition",
                severity="warning",
                bfo_requirement="Obligations can be modeled as ICEs (deontic statements) or dispositions (realizable)",
                validation_function="validate_obligation_deontic_nature",
                entity_types=["obligation_entities"],
                examples=["PublicSafetyObligation", "ConfidentialityObligation"]
            ),
            
            # Rule 12: Professional Roles must have obligation relationships
            ValidationRule(
                rule_id="BFO_012",
                name="Professional Role Obligations",
                description="Professional role entities must have associated obligations",
                severity="warning",
                bfo_requirement="Professional roles are characterized by their obligations",
                validation_function="validate_professional_role_obligations",
                entity_types=["role_entities"],
                examples=["EngineerRole", "ProjectManagerRole"]
            ),
            
            # Rule 13: Required annotations for all entities
            ValidationRule(
                rule_id="BFO_013",
                name="Required Annotations",
                description="All entities must have rdfs:label and iao:definition annotations",
                severity="warning",
                bfo_requirement="Proper annotation ensures interoperability and clarity",
                validation_function="validate_required_annotations",
                entity_types=["all"],
                examples=["All classes and properties"]
            ),
            
            # Rule 14: Proper genus-differentia definitions
            ValidationRule(
                rule_id="BFO_014",
                name="Genus-Differentia Definitions",
                description="Class definitions should follow genus (BFO parent) + differentia pattern",
                severity="info",
                bfo_requirement="Aristotelian definitions improve ontological clarity",
                validation_function="validate_genus_differentia",
                entity_types=["all"],
                examples=["All intermediate-level classes"]
            ),
            
            # Rule 15: Disjointness declarations
            ValidationRule(
                rule_id="BFO_015",
                name="Systematic Disjointness",
                description="Sibling classes should be declared disjoint where appropriate",
                severity="warning", 
                bfo_requirement="Disjointness prevents category errors",
                validation_function="validate_disjointness_declarations",
                entity_types=["all"],
                examples=["MaterialResource vs InformationResource", "Obligation vs Permission"]
            )
        ]
        
        return rules
    
    def validate_entity(self, entity_data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate a single entity against all applicable BFO compliance rules."""
        results = []
        
        entity_uri = entity_data.get('uri', '')
        entity_label = entity_data.get('label', '')
        entity_type = entity_data.get('entity_type', 'unknown')
        
        logger.debug(f"Validating entity: {entity_uri}")
        
        # Apply all relevant validation rules
        for rule in self.validation_rules:
            if self._rule_applies_to_entity(rule, entity_type, entity_uri, entity_label):
                validation_result = self._apply_validation_rule(rule, entity_data)
                if validation_result:
                    results.append(validation_result)
        
        return results
    
    def _rule_applies_to_entity(self, rule: ValidationRule, entity_type: str, 
                               entity_uri: str, entity_label: str) -> bool:
        """Check if a validation rule applies to a specific entity."""
        # Check if rule applies to all entities
        if 'all' in rule.entity_types:
            return True
            
        # Check if rule applies to specific entity types
        for rule_entity_type in rule.entity_types:
            if rule_entity_type == entity_type:
                return True
                
        # Check examples for pattern matching
        text_to_check = f"{entity_uri} {entity_label}".lower()
        for example in rule.examples:
            if example.lower() in text_to_check:
                return True
                
        return False
    
    def _apply_validation_rule(self, rule: ValidationRule, entity_data: Dict[str, Any]) -> Optional[ValidationResult]:
        """Apply a specific validation rule to an entity."""
        try:
            # Get the validation function by name
            validation_func = getattr(self, rule.validation_function, None)
            if not validation_func:
                logger.warning(f"Validation function {rule.validation_function} not found")
                return None
                
            # Execute validation
            is_compliant, message, recommendations, bfo_category = validation_func(entity_data)
            
            # Only return result if there's an issue or it's an info rule
            if not is_compliant or rule.severity == 'info':
                return ValidationResult(
                    rule_id=rule.rule_id,
                    entity_uri=entity_data.get('uri', ''),
                    entity_label=entity_data.get('label', ''),
                    compliant=is_compliant,
                    severity=rule.severity,
                    message=message,
                    recommendations=recommendations,
                    bfo_category=bfo_category
                )
                
        except Exception as e:
            logger.error(f"Error applying rule {rule.rule_id}: {e}")
            return ValidationResult(
                rule_id=rule.rule_id,
                entity_uri=entity_data.get('uri', ''),
                entity_label=entity_data.get('label', ''),
                compliant=False,
                severity='error',
                message=f"Validation error: {str(e)}",
                recommendations=["Review entity definition"],
                bfo_category=None
            )
        
        return None
    
    # Validation Functions
    
    def validate_role_inheritance(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that role entities inherit from bfo:Role."""
        parent_uri = entity_data.get('parent_uri', '')
        uri = entity_data.get('uri', '')
        
        # Check for bfo:Role inheritance
        if 'bfo:Role' in parent_uri or 'bfo.owl#Role' in parent_uri:
            return True, "Correctly inherits from bfo:Role", [], BFOCategory.ROLE.value
            
        # Check if it's a role entity
        if self._is_role_entity(uri, entity_data.get('label', '')):
            return False, "Role entity must inherit from bfo:Role", [
                "Add 'rdfs:subClassOf bfo:Role' axiom",
                "Add restriction: inheres_in some bfo:MaterialEntity"
            ], BFOCategory.ROLE.value
            
        return True, "Not a role entity", [], None
    
    def validate_principle_inheritance(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that principle entities inherit from iao:InformationContentEntity."""
        parent_uri = entity_data.get('parent_uri', '')
        uri = entity_data.get('uri', '')
        
        # Check for iao:InformationContentEntity inheritance
        if 'iao:InformationContentEntity' in parent_uri or 'InformationContentEntity' in parent_uri:
            return True, "Correctly inherits from iao:InformationContentEntity", [], "iao:InformationContentEntity"
            
        # Check if it's a principle entity
        if self._is_principle_entity(uri, entity_data.get('label', '')):
            return False, "Principle entity must inherit from iao:InformationContentEntity", [
                "Add 'rdfs:subClassOf iao:InformationContentEntity' axiom",
                "Add restriction: is_about some proeth:EthicalConduct"
            ], "iao:InformationContentEntity"
            
        return True, "Not a principle entity", [], None
    
    def validate_action_inheritance(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that action entities inherit from bfo:Process with agent restriction."""
        parent_uri = entity_data.get('parent_uri', '')
        uri = entity_data.get('uri', '')
        
        # Check for bfo:Process inheritance
        if 'bfo:Process' in parent_uri or 'bfo.owl#Process' in parent_uri:
            # Check for agent restriction (this would need additional analysis)
            return True, "Correctly inherits from bfo:Process", [
                "Verify has_agent restriction is present"
            ], BFOCategory.PROCESS.value
            
        # Check if it's an action entity
        if self._is_action_entity(uri, entity_data.get('label', '')):
            return False, "Action entity must inherit from bfo:Process", [
                "Add 'rdfs:subClassOf bfo:Process' axiom",
                "Add restriction: has_agent some proeth:Agent",
                "Consider making subclass of proeth:Event"
            ], BFOCategory.PROCESS.value
            
        return True, "Not an action entity", [], None
    
    def validate_event_inheritance(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that event entities inherit from bfo:Process."""
        parent_uri = entity_data.get('parent_uri', '')
        uri = entity_data.get('uri', '')
        
        # Check for bfo:Process inheritance
        if 'bfo:Process' in parent_uri or 'bfo.owl#Process' in parent_uri:
            return True, "Correctly inherits from bfo:Process", [], BFOCategory.PROCESS.value
            
        # Check if it's an event entity
        if self._is_event_entity(uri, entity_data.get('label', '')):
            return False, "Event entity must inherit from bfo:Process", [
                "Add 'rdfs:subClassOf bfo:Process' axiom",
                "Add temporal occurrence restrictions"
            ], BFOCategory.PROCESS.value
            
        return True, "Not an event entity", [], None
    
    def validate_capability_inheritance(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that capability entities inherit from bfo:Disposition."""
        parent_uri = entity_data.get('parent_uri', '')
        uri = entity_data.get('uri', '')
        
        # Check for bfo:Disposition inheritance
        if 'bfo:Disposition' in parent_uri or 'bfo.owl#Disposition' in parent_uri:
            return True, "Correctly inherits from bfo:Disposition", [], BFOCategory.DISPOSITION.value
            
        # Check if it's a capability entity
        if self._is_capability_entity(uri, entity_data.get('label', '')):
            return False, "Capability entity must inherit from bfo:Disposition", [
                "Add 'rdfs:subClassOf bfo:Disposition' axiom",
                "Add restriction: inheres_in some proeth:Agent",
                "Add restriction: realized_in some proeth:Action"
            ], BFOCategory.DISPOSITION.value
            
        return True, "Not a capability entity", [], None
    
    def validate_state_inheritance(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that state entities inherit from bfo:Quality."""
        parent_uri = entity_data.get('parent_uri', '')
        uri = entity_data.get('uri', '')
        
        # Check for bfo:Quality inheritance
        if 'bfo:Quality' in parent_uri or 'bfo.owl#Quality' in parent_uri:
            return True, "Correctly inherits from bfo:Quality", [], BFOCategory.QUALITY.value
            
        # Check if it's a state entity
        if self._is_state_entity(uri, entity_data.get('label', '')):
            return False, "State entity must inherit from bfo:Quality", [
                "Add 'rdfs:subClassOf bfo:Quality' axiom",
                "Add restriction: inheres_in some bfo:MaterialEntity"
            ], BFOCategory.QUALITY.value
            
        return True, "Not a state entity", [], None
    
    def validate_material_resource_inheritance(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that material resource entities inherit from bfo:MaterialEntity."""
        parent_uri = entity_data.get('parent_uri', '')
        uri = entity_data.get('uri', '')
        
        # Check for bfo:MaterialEntity inheritance
        if 'bfo:MaterialEntity' in parent_uri or 'bfo.owl#MaterialEntity' in parent_uri:
            return True, "Correctly inherits from bfo:MaterialEntity", [], BFOCategory.MATERIAL_ENTITY.value
            
        # Check if it's a material resource entity
        if self._is_material_resource_entity(uri, entity_data.get('label', '')):
            return False, "Material resource entity must inherit from bfo:MaterialEntity", [
                "Add 'rdfs:subClassOf bfo:MaterialEntity' axiom",
                "Consider adding to proeth:MaterialResource hierarchy"
            ], BFOCategory.MATERIAL_ENTITY.value
            
        return True, "Not a material resource entity", [], None
    
    def validate_information_resource_inheritance(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that information resource entities inherit from iao:InformationContentEntity."""
        parent_uri = entity_data.get('parent_uri', '')
        uri = entity_data.get('uri', '')
        
        # Check for iao:InformationContentEntity inheritance
        if 'iao:InformationContentEntity' in parent_uri or 'InformationContentEntity' in parent_uri:
            return True, "Correctly inherits from iao:InformationContentEntity", [], "iao:InformationContentEntity"
            
        # Check if it's an information resource entity
        if self._is_information_resource_entity(uri, entity_data.get('label', '')):
            return False, "Information resource entity must inherit from iao:InformationContentEntity", [
                "Add 'rdfs:subClassOf iao:InformationContentEntity' axiom",
                "Consider adding to proeth:InformationResource hierarchy"
            ], "iao:InformationContentEntity"
            
        return True, "Not an information resource entity", [], None
    
    def validate_rule_constraint_inheritance(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that rule constraint entities inherit from iao:InformationContentEntity."""
        parent_uri = entity_data.get('parent_uri', '')
        uri = entity_data.get('uri', '')
        
        # Check for iao:InformationContentEntity inheritance
        if 'iao:InformationContentEntity' in parent_uri or 'InformationContentEntity' in parent_uri:
            return True, "Correctly inherits from iao:InformationContentEntity", [], "iao:InformationContentEntity"
            
        # Check if it's a rule constraint entity
        if self._is_rule_constraint_entity(uri, entity_data.get('label', '')):
            return False, "Rule constraint entity must inherit from iao:InformationContentEntity", [
                "Add 'rdfs:subClassOf iao:InformationContentEntity' axiom",
                "Document constraint as rule or regulation"
            ], "iao:InformationContentEntity"
            
        return True, "Not a rule constraint entity", [], None
    
    def validate_system_constraint_inheritance(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that system constraint entities inherit from bfo:Quality."""
        parent_uri = entity_data.get('parent_uri', '')
        uri = entity_data.get('uri', '')
        
        # Check for bfo:Quality inheritance
        if 'bfo:Quality' in parent_uri or 'bfo.owl#Quality' in parent_uri:
            return True, "Correctly inherits from bfo:Quality", [], BFOCategory.QUALITY.value
            
        # Check if it's a system constraint entity
        if self._is_system_constraint_entity(uri, entity_data.get('label', '')):
            return False, "System constraint entity must inherit from bfo:Quality", [
                "Add 'rdfs:subClassOf bfo:Quality' axiom",
                "Add restriction: inheres_in some proeth:System"
            ], BFOCategory.QUALITY.value
            
        return True, "Not a system constraint entity", [], None
    
    def validate_obligation_deontic_nature(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that obligation entities have proper deontic modeling."""
        parent_uri = entity_data.get('parent_uri', '')
        uri = entity_data.get('uri', '')
        
        # Check for either ICE or Disposition inheritance
        is_ice = 'iao:InformationContentEntity' in parent_uri or 'InformationContentEntity' in parent_uri
        is_disposition = 'bfo:Disposition' in parent_uri or 'bfo.owl#Disposition' in parent_uri
        
        if is_ice or is_disposition:
            pattern = "ICE (deontic statement)" if is_ice else "Disposition (realizable entity)"
            return True, f"Correctly modeled as {pattern}", [], parent_uri
            
        # Check if it's an obligation entity
        if self._is_obligation_entity(uri, entity_data.get('label', '')):
            return False, "Obligation entity must inherit from iao:InformationContentEntity or bfo:Disposition", [
                "Choose ICE pattern: Add 'rdfs:subClassOf iao:InformationContentEntity'",
                "OR choose Disposition pattern: Add 'rdfs:subClassOf bfo:Disposition'",
                "Add appropriate constraints for chosen pattern"
            ], "iao:InformationContentEntity"
            
        return True, "Not an obligation entity", [], None
    
    def validate_professional_role_obligations(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that professional role entities have obligation relationships."""
        uri = entity_data.get('uri', '')
        properties = entity_data.get('properties', {})
        
        # Check if it's a professional role
        if self._is_professional_role_entity(uri, entity_data.get('label', '')):
            # Check for obligation relationships (this would need relationship analysis)
            has_obligations = any(
                'obligation' in prop.lower() 
                for prop in properties.keys() 
                if isinstance(properties, dict)
            )
            
            if has_obligations:
                return True, "Has obligation relationships", [], BFOCategory.ROLE.value
            else:
                return False, "Professional role missing obligation relationships", [
                    "Add hasObligation property assertions",
                    "Define specific obligations for this professional role"
                ], BFOCategory.ROLE.value
                
        return True, "Not a professional role entity", [], None
    
    def validate_required_annotations(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that entities have required annotations."""
        label = entity_data.get('label', '')
        comment = entity_data.get('comment', '')
        uri = entity_data.get('uri', '')
        
        issues = []
        if not label:
            issues.append("Missing rdfs:label")
        if not comment:
            issues.append("Missing iao:definition")
            
        if issues:
            return False, f"Missing required annotations: {', '.join(issues)}", [
                "Add rdfs:label with human-readable name",
                "Add iao:definition with genus-differentia definition"
            ], None
            
        return True, "Has required annotations", [], None
    
    def validate_genus_differentia(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that class definitions follow genus-differentia pattern."""
        comment = entity_data.get('comment', '')
        parent_uri = entity_data.get('parent_uri', '')
        
        # Check if definition includes genus (BFO parent) and differentia
        if comment and parent_uri:
            # Basic check for meaningful definition
            if len(comment.split()) >= 5 and any(bfo_term in parent_uri for bfo_term in ['bfo:', 'iao:']):
                return True, "Has genus-differentia definition structure", [], None
                
        return False, "Definition should follow genus (BFO parent) + differentia pattern", [
            "Structure definition as: 'A [BFO genus] that [specific differentia]'",
            "Include restrictions and properties as differentia"
        ], None
    
    def validate_disjointness_declarations(self, entity_data: Dict[str, Any]) -> Tuple[bool, str, List[str], Optional[str]]:
        """Validate that appropriate disjointness declarations exist."""
        # This is a complex validation that would need access to full ontology
        # For now, return info message
        return True, "Disjointness checking requires full ontology analysis", [
            "Verify MaterialResource and InformationResource are disjoint",
            "Check Obligation, Permission, Prohibition disjointness",
            "Ensure Continuant/Occurrent disjointness"
        ], None
    
    # Entity Type Detection Helper Functions
    
    def _is_role_entity(self, uri: str, label: str) -> bool:
        """Check if entity is a role based on naming patterns."""
        text = f"{uri} {label}".lower()
        role_patterns = ['role', 'position', 'stakeholder']
        return any(pattern in text for pattern in role_patterns)
    
    def _is_principle_entity(self, uri: str, label: str) -> bool:
        """Check if entity is a principle based on naming patterns."""
        text = f"{uri} {label}".lower()
        principle_patterns = ['principle', 'value', 'ethic']
        return any(pattern in text for pattern in principle_patterns)
    
    def _is_action_entity(self, uri: str, label: str) -> bool:
        """Check if entity is an action based on naming patterns."""
        text = f"{uri} {label}".lower()
        action_patterns = ['action', 'activity', 'task', 'process', 'procedure']
        return any(pattern in text for pattern in action_patterns)
    
    def _is_event_entity(self, uri: str, label: str) -> bool:
        """Check if entity is an event based on naming patterns."""
        text = f"{uri} {label}".lower()
        event_patterns = ['event', 'occurrence', 'incident', 'happening']
        return any(pattern in text for pattern in event_patterns)
    
    def _is_capability_entity(self, uri: str, label: str) -> bool:
        """Check if entity is a capability based on naming patterns."""
        text = f"{uri} {label}".lower()
        capability_patterns = ['capability', 'ability', 'skill', 'competence', 'capacity']
        return any(pattern in text for pattern in capability_patterns)
    
    def _is_state_entity(self, uri: str, label: str) -> bool:
        """Check if entity is a state based on naming patterns."""
        text = f"{uri} {label}".lower()
        state_patterns = ['state', 'condition', 'status', 'situation']
        return any(pattern in text for pattern in state_patterns)
    
    def _is_material_resource_entity(self, uri: str, label: str) -> bool:
        """Check if entity is a material resource based on naming patterns."""
        text = f"{uri} {label}".lower()
        material_patterns = ['tool', 'equipment', 'material', 'device', 'instrument', 'infrastructure']
        return any(pattern in text for pattern in material_patterns)
    
    def _is_information_resource_entity(self, uri: str, label: str) -> bool:
        """Check if entity is an information resource based on naming patterns."""
        text = f"{uri} {label}".lower()
        info_patterns = ['specification', 'report', 'document', 'standard', 'guideline', 'manual']
        return any(pattern in text for pattern in info_patterns)
    
    def _is_rule_constraint_entity(self, uri: str, label: str) -> bool:
        """Check if entity is a rule constraint based on naming patterns."""
        text = f"{uri} {label}".lower()
        rule_patterns = ['requirement', 'standard', 'regulation', 'policy', 'rule']
        return any(pattern in text for pattern in rule_patterns)
    
    def _is_system_constraint_entity(self, uri: str, label: str) -> bool:
        """Check if entity is a system constraint based on naming patterns."""
        text = f"{uri} {label}".lower()
        constraint_patterns = ['limit', 'constraint', 'boundary', 'restriction']
        return any(pattern in text for pattern in constraint_patterns)
    
    def _is_obligation_entity(self, uri: str, label: str) -> bool:
        """Check if entity is an obligation based on naming patterns."""
        text = f"{uri} {label}".lower()
        obligation_patterns = ['obligation', 'duty', 'responsibility', 'requirement', 'permission', 'prohibition']
        return any(pattern in text for pattern in obligation_patterns)
    
    def _is_professional_role_entity(self, uri: str, label: str) -> bool:
        """Check if entity is a professional role based on naming patterns."""
        text = f"{uri} {label}".lower()
        professional_patterns = ['engineer', 'manager', 'architect', 'designer', 'professional']
        return any(pattern in text for pattern in professional_patterns) and 'role' in text
    
    def validate_ontology(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate an entire ontology's BFO compliance."""
        logger.info(f"Validating BFO compliance for {len(entities)} entities")
        
        validation_summary = {
            'total_entities': len(entities),
            'compliant_entities': 0,
            'total_violations': 0,
            'violations_by_severity': {'error': 0, 'warning': 0, 'info': 0},
            'violations_by_rule': {},
            'entities_with_issues': [],
            'compliance_percentage': 0.0,
            'recommendations_summary': []
        }
        
        all_recommendations = set()
        
        for entity in entities:
            entity_results = self.validate_entity(entity)
            
            entity_has_issues = False
            entity_issues = {
                'uri': entity.get('uri', ''),
                'label': entity.get('label', ''),
                'violations': []
            }
            
            for result in entity_results:
                if not result.compliant:
                    entity_has_issues = True
                    entity_issues['violations'].append({
                        'rule_id': result.rule_id,
                        'severity': result.severity,
                        'message': result.message,
                        'recommendations': result.recommendations
                    })
                    
                    # Update summary statistics
                    validation_summary['total_violations'] += 1
                    validation_summary['violations_by_severity'][result.severity] += 1
                    
                    if result.rule_id not in validation_summary['violations_by_rule']:
                        validation_summary['violations_by_rule'][result.rule_id] = 0
                    validation_summary['violations_by_rule'][result.rule_id] += 1
                    
                    # Collect recommendations
                    all_recommendations.update(result.recommendations)
            
            if entity_has_issues:
                validation_summary['entities_with_issues'].append(entity_issues)
            else:
                validation_summary['compliant_entities'] += 1
        
        # Calculate compliance percentage
        if validation_summary['total_entities'] > 0:
            validation_summary['compliance_percentage'] = (
                validation_summary['compliant_entities'] / 
                validation_summary['total_entities'] * 100
            )
        
        # Create recommendations summary
        validation_summary['recommendations_summary'] = list(all_recommendations)
        
        logger.info(f"Validation complete: {validation_summary['compliance_percentage']:.1f}% compliant, "
                   f"{validation_summary['total_violations']} violations found")
        
        return validation_summary
    
    def generate_compliance_report(self, validation_summary: Dict[str, Any]) -> str:
        """Generate a human-readable compliance report."""
        report_lines = [
            "=" * 80,
            "BFO COMPLIANCE VALIDATION REPORT",
            "=" * 80,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "SUMMARY:",
            f"  Total Entities: {validation_summary['total_entities']}",
            f"  Compliant Entities: {validation_summary['compliant_entities']}",
            f"  Compliance Percentage: {validation_summary['compliance_percentage']:.1f}%",
            f"  Total Violations: {validation_summary['total_violations']}",
            "",
            "VIOLATIONS BY SEVERITY:",
            f"  Errors: {validation_summary['violations_by_severity']['error']}",
            f"  Warnings: {validation_summary['violations_by_severity']['warning']}",
            f"  Info: {validation_summary['violations_by_severity']['info']}",
            "",
        ]
        
        # Add violations by rule
        if validation_summary['violations_by_rule']:
            report_lines.extend([
                "VIOLATIONS BY RULE:",
                ""
            ])
            for rule_id, count in validation_summary['violations_by_rule'].items():
                rule = next((r for r in self.validation_rules if r.rule_id == rule_id), None)
                rule_name = rule.name if rule else rule_id
                report_lines.append(f"  {rule_id} ({rule_name}): {count} violations")
            report_lines.append("")
        
        # Add top recommendations
        if validation_summary['recommendations_summary']:
            report_lines.extend([
                "TOP RECOMMENDATIONS:",
                ""
            ])
            for i, rec in enumerate(validation_summary['recommendations_summary'][:10], 1):
                report_lines.append(f"  {i}. {rec}")
            report_lines.append("")
        
        # Add detailed entity issues (first 10)
        if validation_summary['entities_with_issues']:
            report_lines.extend([
                "ENTITY ISSUES (first 10):",
                ""
            ])
            for entity in validation_summary['entities_with_issues'][:10]:
                report_lines.append(f"Entity: {entity['label'] or entity['uri']}")
                for violation in entity['violations']:
                    report_lines.append(f"  [{violation['severity'].upper()}] {violation['message']}")
                report_lines.append("")
        
        report_lines.extend([
            "=" * 80,
            "END OF REPORT",
            "=" * 80
        ])
        
        return "\n".join(report_lines)


def main():
    """Main function for running BFO compliance validation."""
    import argparse
    
    parser = argparse.ArgumentParser(description='BFO Compliance Validator for ProEthica Intermediate Ontology')
    parser.add_argument('--ontology-file', required=True, help='Path to ontology TTL file')
    parser.add_argument('--output-report', help='Output file for validation report')
    parser.add_argument('--json-output', help='Output file for JSON validation results')
    
    args = parser.parse_args()
    
    try:
        # Initialize validator
        validator = BFOComplianceValidator()
        
        # This is a simplified version - in real implementation,
        # entities would be loaded from OntServe database
        logger.info("BFO Compliance validation would run here")
        logger.info(f"Ontology file: {args.ontology_file}")
        logger.info(f"Validation rules loaded: {len(validator.validation_rules)}")
        
        # Example usage (would need actual entity data)
        sample_entity = {
            'uri': 'http://proethica.org/ontology/intermediate#EngineerRole',
            'label': 'Engineer Role',
            'comment': 'A professional role in engineering',
            'parent_uri': '',  # Missing BFO parent - should trigger validation
            'entity_type': 'role_entities',
            'properties': {}
        }
        
        results = validator.validate_entity(sample_entity)
        
        print(f"Sample validation results for {sample_entity['uri']}:")
        for result in results:
            print(f"  [{result.severity.upper()}] {result.message}")
            for rec in result.recommendations:
                print(f"    → {rec}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
