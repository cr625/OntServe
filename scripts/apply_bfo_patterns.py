"""
Apply Concrete BFO Patterns to ProEthica Intermediate Ontology

Implements the specific BFO alignment patterns provided in the feedback,
starting with Role entities and progressing through all 9 core entity types.
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Add OntServe to path for progress tracking
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'web'))

try:
    from progress_dashboard import BFOAlignmentProgressDashboard
    dashboard = BFOAlignmentProgressDashboard()
except ImportError:
    print("Warning: Progress dashboard not available")
    dashboard = None

class BFOPatternApplicator:
    """
    Applies concrete BFO patterns from the feedback to the intermediate ontology.
    Updates entities step-by-step with progress tracking.
    """
    
    def __init__(self):
        self.source_file = "proethica/ontologies/proethica-intermediate.ttl"
        self.working_file = "OntServe/data/ontologies/proethica-intermediate-working.ttl"
        self.backup_file = f"OntServe/data/backups/proethica-intermediate-backup-{datetime.now().strftime('%Y%m%d_%H%M%S')}.ttl"
        
        # Ensure directories exist
        Path("OntServe/data/backups").mkdir(parents=True, exist_ok=True)
        
        # BFO patterns from feedback (concrete implementations ready to use)
        self.bfo_patterns = {
            "Role": {
                "target_parent": "bfo:Role",
                "pattern": """
# Role → BFO:Role (Realizable Entity)
proeth:Role a owl:Class ;
    rdfs:subClassOf bfo:Role ;
    rdfs:label "Professional Role"@en ;
    iao:definition "A role that inheres in a material entity and can be realized by processes involving professional duties and ethical obligations."@en .

proeth:ProfessionalRole a owl:Class ;
    rdfs:subClassOf proeth:Role ,
        [ a owl:Restriction ;
          owl:onProperty bfo:inheres_in ;
          owl:someValuesFrom bfo:MaterialEntity ] ;
    rdfs:label "Professional Role"@en .

# Property alignment
proeth:hasRole rdfs:subPropertyOf ro:has_role .
""",
                "description": "Roles as BFO realizable entities that inhere in material entities"
            },
            
            "Principle": {
                "target_parent": "iao:InformationContentEntity",
                "pattern": """
# Principle → IAO:Information Content Entity
proeth:Principle a owl:Class ;
    rdfs:subClassOf iao:InformationContentEntity ,
        [ a owl:Restriction ;
          owl:onProperty iao:is_about ;
          owl:someValuesFrom proeth:EthicalConduct ] ;
    rdfs:label "Ethical Principle"@en ;
    iao:definition "An information content entity that represents fundamental ethical values and guidelines for conduct."@en .

proeth:IntegrityPrinciple a owl:Class ;
    rdfs:subClassOf proeth:Principle ;
    rdfs:label "Integrity Principle"@en ;
    iao:definition "A principle that guides honest and truthful professional conduct."@en .
""",
                "description": "Principles as information content entities about ethical conduct"
            },
            
            "Obligation": {
                "target_parent": "iao:InformationContentEntity", 
                "pattern": """
# Obligation → Deontic ICEs
proeth:DeonticStatement a owl:Class ;
    rdfs:subClassOf iao:InformationContentEntity ;
    rdfs:label "Deontic Statement"@en ;
    iao:definition "An information content entity that expresses permissions, obligations, or prohibitions."@en .

proeth:Obligation a owl:Class ;
    rdfs:subClassOf proeth:DeonticStatement ,
        [ a owl:Restriction ;
          owl:onProperty proeth:constrains ;
          owl:someValuesFrom bfo:Role ] ,
        [ a owl:Restriction ;
          owl:onProperty proeth:appliesToRole ;
          owl:someValuesFrom proeth:ProfessionalRole ] ;
    rdfs:label "Professional Obligation"@en .

proeth:Permission a owl:Class ;
    rdfs:subClassOf proeth:DeonticStatement ;
    rdfs:label "Permission"@en .

proeth:Prohibition a owl:Class ;
    rdfs:subClassOf proeth:DeonticStatement ;
    rdfs:label "Prohibition"@en .

# Properties for deontic statements
proeth:constrains a owl:ObjectProperty ;
    rdfs:domain proeth:DeonticStatement ;
    rdfs:range proeth:Action .

proeth:appliesToRole a owl:ObjectProperty ;
    rdfs:domain proeth:DeonticStatement ;
    rdfs:range proeth:ProfessionalRole .
""",
                "description": "Obligations as deontic information content entities"
            },
            
            "Action": {
                "target_parent": "bfo:Process",
                "pattern": """
# Action → BFO:Process with Agent
proeth:Event a owl:Class ; 
    rdfs:subClassOf bfo:Process ;
    rdfs:label "Event"@en ;
    iao:definition "A process that occurs in ethical scenarios."@en .

proeth:Action a owl:Class ; 
    rdfs:subClassOf proeth:Event ,
        [ a owl:Restriction ; 
          owl:onProperty ro:has_agent ; 
          owl:someValuesFrom proeth:Agent ] ;
    rdfs:label "Intentional Action"@en ;
    iao:definition "A process that has an agent participant and is directed toward achieving specific goals."@en .
""",
                "description": "Actions as processes with required agent participants"
            },
            
            "Resource": {
                "target_parent": ["bfo:MaterialEntity", "iao:InformationContentEntity"],
                "pattern": """
# Resource → Bifurcated Model
proeth:Resource a owl:Class ;
    rdfs:label "Resource"@en ;
    iao:definition "An entity that serves as input or reference for professional activities."@en .

proeth:MaterialResource a owl:Class ;
    rdfs:subClassOf proeth:Resource, bfo:MaterialEntity ;
    rdfs:label "Material Resource"@en ;
    iao:definition "A physical resource used in professional activities."@en .

proeth:InformationResource a owl:Class ;
    rdfs:subClassOf proeth:Resource, iao:InformationContentEntity ;
    rdfs:label "Information Resource"@en ;
    iao:definition "An information resource used in professional activities."@en .

# Disjointness
[] a owl:Axiom ;
   owl:disjointClasses ( proeth:MaterialResource proeth:InformationResource ) .
""",
                "description": "Resources split into disjoint Material and Information categories"
            }
        }

    def create_backup(self):
        """Create backup of current ontology before making changes."""
        print(f"Creating backup: {self.backup_file}")
        shutil.copy2(self.source_file, self.backup_file)
        
        if dashboard:
            dashboard.add_activity(
                "Backup Created",
                f"Created backup before applying BFO patterns: {Path(self.backup_file).name}",
                "backup"
            )
        
        return self.backup_file

    def apply_role_pattern(self) -> bool:
        """Apply BFO pattern for Role entities (Step 1)."""
        print("\n" + "="*50)
        print("STEP 1: Applying BFO Pattern for Role Entities")
        print("="*50)
        
        pattern_info = self.bfo_patterns["Role"]
        print(f"Target: Role → {pattern_info['target_parent']}")
        print(f"Description: {pattern_info['description']}")
        
        try:
            # Read current ontology
            with open(self.working_file, 'r') as f:
                content = f.read()
            
            # Check if BFO imports are present
            if "bfo:" not in content or "@prefix bfo:" not in content:
                print("Adding BFO namespace and imports...")
                content = self._add_bfo_imports(content)
            
            # Apply Role pattern
            print("Applying Role → bfo:Role pattern...")
            content = self._apply_pattern_to_content(content, "Role", pattern_info["pattern"])
            
            # Write updated content
            with open(self.working_file, 'w') as f:
                f.write(content)
            
            print("✅ Role pattern applied successfully!")
            
            # Update progress tracking
            if dashboard:
                dashboard.update_entity_alignment("Role", "complete", "bfo:Role")
                dashboard.add_activity(
                    "Role Pattern Applied",
                    "Applied BFO Role pattern: Role → bfo:Role with proper restrictions",
                    "migration"
                )
            
            return True
            
        except Exception as e:
            print(f"❌ Error applying Role pattern: {str(e)}")
            return False

    def apply_principle_pattern(self) -> bool:
        """Apply BFO pattern for Principle entities (Step 2)."""
        print("\n" + "="*50)
        print("STEP 2: Applying BFO Pattern for Principle Entities") 
        print("="*50)
        
        pattern_info = self.bfo_patterns["Principle"]
        print(f"Target: Principle → {pattern_info['target_parent']}")
        print(f"Description: {pattern_info['description']}")
        
        try:
            with open(self.working_file, 'r') as f:
                content = f.read()
            
            # Check if IAO imports are present
            if "iao:" not in content or "@prefix iao:" not in content:
                print("Adding IAO namespace and imports...")
                content = self._add_iao_imports(content)
            
            # Apply Principle pattern
            print("Applying Principle → iao:InformationContentEntity pattern...")
            content = self._apply_pattern_to_content(content, "Principle", pattern_info["pattern"])
            
            with open(self.working_file, 'w') as f:
                f.write(content)
                
            print("✅ Principle pattern applied successfully!")
            
            if dashboard:
                dashboard.update_entity_alignment("Principle", "complete", "iao:InformationContentEntity")
                dashboard.add_activity(
                    "Principle Pattern Applied",
                    "Applied BFO Principle pattern: Principle → iao:InformationContentEntity",
                    "migration"
                )
            
            return True
            
        except Exception as e:
            print(f"❌ Error applying Principle pattern: {str(e)}")
            return False

    def apply_obligation_pattern(self) -> bool:
        """Apply BFO pattern for Obligation entities (Step 3)."""
        print("\n" + "="*50)
        print("STEP 3: Applying BFO Pattern for Obligation Entities")
        print("="*50)
        
        pattern_info = self.bfo_patterns["Obligation"]
        print(f"Target: Obligation → {pattern_info['target_parent']} (Deontic ICE)")
        print(f"Description: {pattern_info['description']}")
        
        try:
            with open(self.working_file, 'r') as f:
                content = f.read()
                
            print("Applying Obligation → Deontic ICE pattern...")
            content = self._apply_pattern_to_content(content, "Obligation", pattern_info["pattern"])
            
            with open(self.working_file, 'w') as f:
                f.write(content)
                
            print("✅ Obligation pattern applied successfully!")
            
            if dashboard:
                dashboard.update_entity_alignment("Obligation", "complete", "iao:InformationContentEntity")
                dashboard.add_activity(
                    "Obligation Pattern Applied", 
                    "Applied BFO Obligation pattern: Deontic ICE with constrains/appliesToRole",
                    "migration"
                )
            
            return True
            
        except Exception as e:
            print(f"❌ Error applying Obligation pattern: {str(e)}")
            return False

    def apply_action_pattern(self) -> bool:
        """Apply BFO pattern for Action entities (Step 4)."""
        print("\n" + "="*50)
        print("STEP 4: Applying BFO Pattern for Action Entities")
        print("="*50)
        
        pattern_info = self.bfo_patterns["Action"]
        print(f"Target: Action → {pattern_info['target_parent']} (with agent)")
        print(f"Description: {pattern_info['description']}")
        
        try:
            with open(self.working_file, 'r') as f:
                content = f.read()
                
            # Check if RO imports are present  
            if "ro:" not in content or "@prefix ro:" not in content:
                print("Adding RO namespace and imports...")
                content = self._add_ro_imports(content)
                
            print("Applying Action/Event → bfo:Process pattern...")
            content = self._apply_pattern_to_content(content, "Action", pattern_info["pattern"])
            
            with open(self.working_file, 'w') as f:
                f.write(content)
                
            print("✅ Action pattern applied successfully!")
            
            if dashboard:
                dashboard.update_entity_alignment("Action", "complete", "bfo:Process")
                dashboard.update_entity_alignment("Event", "complete", "bfo:Process")
                dashboard.add_activity(
                    "Action/Event Pattern Applied",
                    "Applied BFO Action/Event patterns: Process with agentivity differentia",
                    "migration"
                )
            
            return True
            
        except Exception as e:
            print(f"❌ Error applying Action pattern: {str(e)}")
            return False

    def apply_resource_pattern(self) -> bool:
        """Apply BFO pattern for Resource entities (Step 5)."""
        print("\n" + "="*50)
        print("STEP 5: Applying BFO Pattern for Resource Entities")
        print("="*50)
        
        pattern_info = self.bfo_patterns["Resource"]
        print(f"Target: Resource → Bifurcated (Material + Information)")
        print(f"Description: {pattern_info['description']}")
        
        try:
            with open(self.working_file, 'r') as f:
                content = f.read()
                
            print("Applying Resource bifurcation pattern...")
            content = self._apply_pattern_to_content(content, "Resource", pattern_info["pattern"])
            
            with open(self.working_file, 'w') as f:
                f.write(content)
                
            print("✅ Resource pattern applied successfully!")
            
            if dashboard:
                dashboard.update_entity_alignment("Resource", "complete", "bfo:MaterialEntity + iao:ICE")
                dashboard.add_activity(
                    "Resource Pattern Applied",
                    "Applied BFO Resource bifurcation: MaterialResource + InformationResource with disjointness",
                    "migration"
                )
            
            return True
            
        except Exception as e:
            print(f"❌ Error applying Resource pattern: {str(e)}")
            return False

    def _add_bfo_imports(self, content: str) -> str:
        """Add BFO namespace and imports to ontology."""
        lines = content.split('\n')
        
        # Find where to insert imports (after existing @prefix declarations)
        insert_line = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('@prefix'):
                insert_line = i + 1
        
        # Add BFO namespace if not present
        if "@prefix bfo:" not in content:
            lines.insert(insert_line, "@prefix bfo: <http://purl.obolibrary.org/obo/> .")
            insert_line += 1
        
        # Add import statement if not present
        if "owl:imports" not in content and "bfo.owl" not in content:
            # Find ontology declaration to add import
            for i, line in enumerate(lines):
                if "a owl:Ontology" in line:
                    lines.insert(i + 1, "    owl:imports <http://purl.obolibrary.org/obo/bfo.owl> ;")
                    break
        
        return '\n'.join(lines)

    def _add_iao_imports(self, content: str) -> str:
        """Add IAO namespace and imports to ontology."""
        lines = content.split('\n')
        
        # Add IAO namespace if not present
        if "@prefix iao:" not in content:
            insert_line = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('@prefix'):
                    insert_line = i + 1
            lines.insert(insert_line, "@prefix iao: <http://purl.obolibrary.org/obo/> .")
        
        # Add import statement if not present
        if "iao.owl" not in content:
            for i, line in enumerate(lines):
                if "owl:imports" in line:
                    # Add after existing import
                    lines.insert(i + 1, "    owl:imports <http://purl.obolibrary.org/obo/iao.owl> ;")
                    break
                elif "a owl:Ontology" in line:
                    lines.insert(i + 1, "    owl:imports <http://purl.obolibrary.org/obo/iao.owl> ;")
                    break
        
        return '\n'.join(lines)

    def _add_ro_imports(self, content: str) -> str:
        """Add RO namespace and imports to ontology.""" 
        lines = content.split('\n')
        
        # Add RO namespace if not present
        if "@prefix ro:" not in content:
            insert_line = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('@prefix'):
                    insert_line = i + 1
            lines.insert(insert_line, "@prefix ro: <http://purl.obolibrary.org/obo/> .")
        
        # Add import statement if not present
        if "ro.owl" not in content:
            for i, line in enumerate(lines):
                if "owl:imports" in line:
                    lines.insert(i + 1, "    owl:imports <http://purl.obolibrary.org/obo/ro.owl> ;")
                    break
                elif "a owl:Ontology" in line:
                    lines.insert(i + 1, "    owl:imports <http://purl.obolibrary.org/obo/ro.owl> ;")
                    break
        
        return '\n'.join(lines)

    def _apply_pattern_to_content(self, content: str, entity_type: str, pattern: str) -> str:
        """Apply BFO pattern to ontology content."""
        
        # For now, append the pattern to the end of the file
        # In a more sophisticated implementation, this would parse and integrate properly
        
        content += f"\n\n# === {entity_type} BFO Alignment Pattern ===\n"
        content += f"# Applied: {datetime.now().isoformat()}\n"
        content += pattern
        content += f"\n# === End {entity_type} Pattern ===\n"
        
        return content

    def run_step_by_step_migration(self):
        """Run step-by-step BFO pattern application."""
        print("ProEthica Intermediate Ontology - BFO Pattern Application")
        print("=" * 60)
        print("Applying concrete BFO patterns from feedback step-by-step...")
        
        # Step 0: Create backup
        print("\n🔒 Creating backup...")
        backup_path = self.create_backup()
        print(f"✅ Backup created: {backup_path}")
        
        # Step 1: Apply Role pattern
        if not self.apply_role_pattern():
            print("❌ Failed at Role pattern. Stopping migration.")
            return False
        
        # Step 2: Apply Principle pattern  
        if not self.apply_principle_pattern():
            print("❌ Failed at Principle pattern. Stopping migration.")
            return False
        
        # Step 3: Apply Obligation pattern
        if not self.apply_obligation_pattern():
            print("❌ Failed at Obligation pattern. Stopping migration.")
            return False
        
        # Step 4: Apply Action pattern
        if not self.apply_action_pattern():
            print("❌ Failed at Action pattern. Stopping migration.")
            return False
        
        # Step 5: Apply Resource pattern
        if not self.apply_resource_pattern():
            print("❌ Failed at Resource pattern. Stopping migration.")
            return False
        
        # Update overall progress
        if dashboard:
            dashboard.update_milestone_completion("Core Entity Migration Complete", 50)
            dashboard.add_activity(
                "Phase 1 BFO Patterns Applied",
                "Successfully applied BFO patterns for Role, Principle, Obligation, Action, Resource entities",
                "milestone"
            )
        
        print("\n" + "="*60)
        print("✅ FIRST PHASE COMPLETE!")
        print("="*60)
        print("Applied BFO patterns for:")
        print("✅ Role → bfo:Role") 
        print("✅ Principle → iao:InformationContentEntity")
        print("✅ Obligation → iao:InformationContentEntity (Deontic ICE)")
        print("✅ Action/Event → bfo:Process (with agentivity differentia)")
        print("✅ Resource → Bifurcated (Material + Information)")
        print(f"\n📁 Updated ontology: {self.working_file}")
        print(f"🔒 Backup available: {backup_path}")
        
        if dashboard:
            print("📊 View progress dashboard: http://localhost:5002/progress")
        
        print("\n🚀 Next steps:")
        print("1. Review the updated ontology file")
        print("2. Apply remaining patterns (State, Capability, Constraint)")
        print("3. Address quality issues (rdf:type placeholders, meta-typing)")
        print("4. Run validation and reasoning tests")
        
        return True

def main():
    """Main execution function."""
    applicator = BFOPatternApplicator()
    
    # Ensure working file exists
    if not Path(applicator.working_file).exists():
        print("Working file not found. Copying from source...")
        shutil.copy2(applicator.source_file, applicator.working_file)
    
    # Run step-by-step migration
    success = applicator.run_step_by_step_migration()
    
    if success:
        print("\n🎉 First phase of BFO pattern application complete!")
        print("Ready to continue with remaining entity types and quality fixes.")
    else:
        print("\n💥 Migration failed. Check error messages above.")
    
    return success

if __name__ == "__main__":
    main()
