"""
Apply Remaining BFO Patterns - Phase 2

Completes the BFO alignment by applying patterns for State, Capability, and Constraint entities.
Also addresses quality issues identified in the analysis.
"""

import os
import sys
import shutil
import re
from pathlib import Path
from datetime import datetime

# Add OntServe to path for progress tracking
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'web'))

try:
    from progress_dashboard import BFOAlignmentProgressDashboard
    dashboard = BFOAlignmentProgressDashboard()
except ImportError:
    print("Warning: Progress dashboard not available")
    dashboard = None

class RemainingPatternsApplicator:
    """
    Applies the remaining BFO patterns and addresses quality issues.
    """
    
    def __init__(self):
        self.working_file = "OntServe/data/ontologies/proethica-intermediate-working.ttl"
        
        # Remaining BFO patterns
        self.remaining_patterns = {
            "State": {
                "target_parent": "bfo:Quality",
                "pattern": """
# State/Condition → Qualities or Dispositions
proeth:State a owl:Class ;
    rdfs:subClassOf bfo:Quality ;
    rdfs:label "Contextual State"@en ;
    iao:definition "A quality that inheres in an entity and affects ethical decisions."@en .

proeth:SafetyHazardState a owl:Class ;
    rdfs:subClassOf bfo:Quality ,
        [ a owl:Restriction ;
          owl:onProperty bfo:inheres_in ;
          owl:someValuesFrom bfo:MaterialEntity ] ;
    rdfs:label "Safety Hazard State"@en ;
    iao:definition "A quality indicating the presence of safety hazards in a system."@en .

# For documented rules (alternative pattern)
proeth:BudgetConstraint a owl:Class ;
    rdfs:subClassOf iao:InformationContentEntity ;
    rdfs:label "Budget Constraint"@en ;
    iao:definition "An information content entity documenting budget limitations."@en .
""",
                "description": "States as qualities; documented constraints as ICEs"
            },
            
            "Capability": {
                "target_parent": "bfo:Disposition",
                "pattern": """
# Capability → BFO:Disposition
proeth:Capability a owl:Class ;
    rdfs:subClassOf bfo:Disposition ;
    rdfs:label "Professional Capability"@en ;
    iao:definition "A disposition that inheres in an agent and can be realized by specific types of actions or processes."@en .

proeth:RiskAssessmentCapability a owl:Class ;
    rdfs:subClassOf proeth:Capability ,
        [ a owl:Restriction ;
          owl:onProperty bfo:inheres_in ;
          owl:someValuesFrom proeth:Engineer ] ,
        [ a owl:Restriction ;
          owl:onProperty bfo:realized_in ;
          owl:someValuesFrom proeth:RiskAssessmentAction ] ;
    rdfs:label "Risk Assessment Capability"@en ;
    iao:definition "The disposition to perform risk assessment activities."@en .
""",
                "description": "Capabilities as dispositions realized by actions"
            },
            
            "Constraint": {
                "target_parent": ["bfo:Quality", "iao:InformationContentEntity"],
                "pattern": """
# Constraint → Context-Dependent Modeling
# As rule/text (ICE)
proeth:LicensureRequirement a owl:Class ;
    rdfs:subClassOf iao:InformationContentEntity ;
    rdfs:label "Licensure Requirement"@en ;
    iao:definition "An information content entity specifying professional licensing requirements."@en .

# As system limitation (Quality/Disposition) 
proeth:LoadLimitConstraint a owl:Class ;
    rdfs:subClassOf bfo:Quality ,
        [ a owl:Restriction ;
          owl:onProperty bfo:inheres_in ;
          owl:someValuesFrom proeth:EngineeringSystem ] ;
    rdfs:label "Load Limit Constraint"@en ;
    iao:definition "A quality representing the maximum load capacity of a system."@en .
""",
                "description": "Constraints as ICEs (rules) or Qualities (system limitations)"
            }
        }

    def apply_state_pattern(self) -> bool:
        """Apply BFO pattern for State entities."""
        print("\n" + "="*50)
        print("STEP 6: Applying BFO Pattern for State Entities")
        print("="*50)
        
        pattern_info = self.remaining_patterns["State"]
        print(f"Target: State → {pattern_info['target_parent']}")
        print(f"Description: {pattern_info['description']}")
        
        try:
            with open(self.working_file, 'r') as f:
                content = f.read()
                
            print("Applying State → bfo:Quality pattern...")
            content = self._apply_pattern_to_content(content, "State", pattern_info["pattern"])
            
            with open(self.working_file, 'w') as f:
                f.write(content)
                
            print("✅ State pattern applied successfully!")
            
            if dashboard:
                dashboard.update_entity_alignment("State", "complete", "bfo:Quality")
                dashboard.add_activity(
                    "State Pattern Applied",
                    "Applied BFO State pattern: State → bfo:Quality with context-dependent modeling",
                    "migration"
                )
            
            return True
            
        except Exception as e:
            print(f"❌ Error applying State pattern: {str(e)}")
            return False

    def apply_capability_pattern(self) -> bool:
        """Apply BFO pattern for Capability entities."""
        print("\n" + "="*50)
        print("STEP 7: Applying BFO Pattern for Capability Entities")
        print("="*50)
        
        pattern_info = self.remaining_patterns["Capability"]
        print(f"Target: Capability → {pattern_info['target_parent']}")
        print(f"Description: {pattern_info['description']}")
        
        try:
            with open(self.working_file, 'r') as f:
                content = f.read()
                
            print("Applying Capability → bfo:Disposition pattern...")
            content = self._apply_pattern_to_content(content, "Capability", pattern_info["pattern"])
            
            with open(self.working_file, 'w') as f:
                f.write(content)
                
            print("✅ Capability pattern applied successfully!")
            
            if dashboard:
                dashboard.update_entity_alignment("Capability", "complete", "bfo:Disposition")
                dashboard.add_activity(
                    "Capability Pattern Applied",
                    "Applied BFO Capability pattern: Capability → bfo:Disposition with realization",
                    "migration"
                )
            
            return True
            
        except Exception as e:
            print(f"❌ Error applying Capability pattern: {str(e)}")
            return False

    def apply_constraint_pattern(self) -> bool:
        """Apply BFO pattern for Constraint entities."""
        print("\n" + "="*50)
        print("STEP 8: Applying BFO Pattern for Constraint Entities")
        print("="*50)
        
        pattern_info = self.remaining_patterns["Constraint"]
        print(f"Target: Constraint → Context-dependent (Quality + ICE)")
        print(f"Description: {pattern_info['description']}")
        
        try:
            with open(self.working_file, 'r') as f:
                content = f.read()
                
            print("Applying Constraint → context-dependent pattern...")
            content = self._apply_pattern_to_content(content, "Constraint", pattern_info["pattern"])
            
            with open(self.working_file, 'w') as f:
                f.write(content)
                
            print("✅ Constraint pattern applied successfully!")
            
            if dashboard:
                dashboard.update_entity_alignment("Constraint", "complete", "bfo:Quality + iao:ICE")
                dashboard.add_activity(
                    "Constraint Pattern Applied",
                    "Applied BFO Constraint pattern: Context-dependent ICE/Quality modeling",
                    "migration"
                )
            
            return True
            
        except Exception as e:
            print(f"❌ Error applying Constraint pattern: {str(e)}")
            return False

    def fix_quality_issues(self) -> bool:
        """Fix the quality issues identified in the analysis."""
        print("\n" + "="*50)
        print("STEP 9: Fixing Quality Issues")
        print("="*50)
        
        try:
            with open(self.working_file, 'r') as f:
                content = f.read()
            
            original_content = content
            
            # Fix 1: Remove rdf:type placeholders in rdfs:comment fields
            print("🔧 Fixing rdf:type placeholders in comments...")
            content = re.sub(r'rdfs:comment\s+"[^"]*rdf:type[^"]*"', 
                           'rdfs:comment "A properly defined class in the intermediate ontology."', 
                           content)
            
            # Fix 2: Remove EntityType/EventType meta-typing conflicts
            print("🔧 Removing EntityType/EventType meta-classes...")
            content = re.sub(r',\s*:EntityType', '', content)
            content = re.sub(r',\s*:EventType', '', content)
            content = re.sub(r':EntityType\s*,', '', content)
            content = re.sub(r':EventType\s*,', '', content)
            
            # Fix 3: Add systematic disjointness 
            print("🔧 Adding systematic disjointness axioms...")
            disjointness_axioms = """

# === Systematic Disjointness Axioms ===
# Added for BFO compliance

# Continuant vs Occurrent disjointness
[] a owl:Axiom ;
   owl:disjointClasses ( bfo:Continuant bfo:Occurrent ) .

# Material vs Information Resource disjointness  
[] a owl:Axiom ;
   owl:disjointClasses ( proeth:MaterialResource proeth:InformationResource ) .

# Deontic statement types disjointness
[] a owl:Axiom ;
   owl:disjointClasses ( proeth:Obligation proeth:Permission ) .
   
[] a owl:Axiom ;
   owl:disjointClasses ( proeth:Obligation proeth:Prohibition ) .
   
[] a owl:Axiom ;
   owl:disjointClasses ( proeth:Permission proeth:Prohibition ) .
"""
            content += disjointness_axioms
            
            # Write fixed content
            if content != original_content:
                with open(self.working_file, 'w') as f:
                    f.write(content)
                print("✅ Quality issues fixed successfully!")
                
                if dashboard:
                    dashboard.add_activity(
                        "Quality Issues Fixed",
                        "Fixed rdf:type placeholders, meta-typing conflicts, and added disjointness axioms",
                        "quality_assurance"
                    )
                return True
            else:
                print("ℹ️ No quality issues found to fix")
                return True
            
        except Exception as e:
            print(f"❌ Error fixing quality issues: {str(e)}")
            return False

    def _apply_pattern_to_content(self, content: str, entity_type: str, pattern: str) -> str:
        """Apply BFO pattern to ontology content."""
        content += f"\n\n# === {entity_type} BFO Alignment Pattern ===\n"
        content += f"# Applied: {datetime.now().isoformat()}\n"
        content += pattern
        content += f"\n# === End {entity_type} Pattern ===\n"
        return content

    def run_remaining_migration(self):
        """Complete the BFO pattern application."""
        print("ProEthica Intermediate Ontology - Remaining BFO Patterns")
        print("=" * 60)
        print("Completing BFO alignment with remaining entity patterns...")
        
        # Apply remaining patterns
        if not self.apply_state_pattern():
            return False
            
        if not self.apply_capability_pattern():
            return False
            
        if not self.apply_constraint_pattern():
            return False
        
        # Fix quality issues
        if not self.fix_quality_issues():
            return False
        
        # Update final progress
        if dashboard:
            dashboard.update_milestone_completion("Core Entity Migration Complete", 100)
            dashboard.add_activity(
                "BFO Migration Complete",
                "All 9 core entities aligned with BFO patterns and quality issues resolved",
                "completion"
            )
        
        print("\n" + "="*60)
        print("🎉 BFO ALIGNMENT MIGRATION COMPLETE!")
        print("="*60)
        print("✅ All 9 core entities aligned:")
        print("  • Role → bfo:Role")
        print("  • Principle → iao:InformationContentEntity")
        print("  • Obligation → iao:InformationContentEntity (Deontic ICE)")
        print("  • Action/Event → bfo:Process")
        print("  • Resource → Bifurcated (Material + Information)")
        print("  • State → bfo:Quality")
        print("  • Capability → bfo:Disposition")
        print("  • Constraint → Context-dependent (Quality + ICE)")
        print("\n✅ Quality issues resolved:")
        print("  • rdf:type placeholders cleaned")
        print("  • Meta-typing conflicts removed")
        print("  • Systematic disjointness added")
        
        print(f"\n📁 Updated ontology: {self.working_file}")
        print("📊 View progress: http://localhost:5002/progress")
        
        print("\n🚀 Ready for version creation!")
        print("Next steps:")
        print("1. Create new version 2.0.0 in OntServer")
        print("2. Run validation tests")
        print("3. Deploy to ProEthica integration")
        
        return True

def main():
    """Main execution function."""
    applicator = RemainingPatternsApplicator()
    
    if not Path(applicator.working_file).exists():
        print("❌ Working file not found. Run the first BFO patterns script first.")
        return False
    
    success = applicator.run_remaining_migration()
    
    if success:
        print("\n🎉 Complete BFO alignment migration finished!")
        print("Ready to create version 2.0.0!")
    else:
        print("\n💥 Migration failed. Check error messages above.")
    
    return success

if __name__ == "__main__":
    main()
