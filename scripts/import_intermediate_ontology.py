"""
Import ProEthica Intermediate Ontology for BFO Alignment Analysis

Imports the current proethica-intermediate.ttl into OntServe for analysis and migration.
Performs initial validation and entity extraction to prepare for BFO alignment.
"""

import os
import sys
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Add OntServe to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from core.ontology_manager import OntologyManager
    from utils.validation import ValidationManager
    # Import progress dashboard from relative path
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'web'))
    from progress_dashboard import BFOAlignmentProgressDashboard
except ImportError:
    print("Warning: OntServe imports not available. Running in standalone mode.")
    OntologyManager = None
    ValidationManager = None
    BFOAlignmentProgressDashboard = None

class IntermediateOntologyImporter:
    """
    Imports and analyzes the current ProEthica Intermediate Ontology.
    Prepares for BFO alignment migration with initial compliance assessment.
    """
    
    def __init__(self):
        # Progress tracking integration (optional)
        if BFOAlignmentProgressDashboard:
            self.dashboard = BFOAlignmentProgressDashboard()
        else:
            self.dashboard = None
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Source ontology configuration
        self.source_ontology = {
            "name": "ProEthica Intermediate Ontology",
            "file_path": "proethica/ontologies/proethica-intermediate.ttl",
            "backup_path": "proethica/ontologies/proethica-intermediate-backup-20250117.ttl",
            "namespace": "http://proethica.org/ontology/intermediate#",
            "ontology_iri": "http://proethica.org/ontology/intermediate",
            "description": "Mid-level ethical modeling framework for AI-driven professional ethics analysis"
        }
        
        # Target configuration for OntServe
        self.target_config = {
            "ontology_id": "proethica-intermediate",
            "version": "1.0.0",  # Pre-upgrade version
            "target_version": "2.0.0",  # Post-upgrade version
            "profile": "mixed",  # Will be migrated to OWL 2 EL
            "reasoning_enabled": True
        }

    def import_ontology(self) -> Dict:
        """
        Import the intermediate ontology into OntServe.
        
        Returns:
            Dict: Import results and analysis summary
        """
        self.logger.info("Starting ProEthica Intermediate Ontology import...")
        
        # Step 1: Validate source file exists
        source_path = Path(self.source_ontology["file_path"])
        if not source_path.exists():
            # Try backup file
            backup_path = Path(self.source_ontology["backup_path"])
            if backup_path.exists():
                self.logger.warning(f"Main file not found, using backup: {backup_path}")
                source_path = backup_path
            else:
                raise FileNotFoundError(f"Neither main nor backup intermediate ontology file found")
        
        # Step 2: Create working copy in OntServe
        target_path = self._create_working_copy(source_path)
        
        # Step 3: Perform initial analysis
        analysis_results = self._analyze_current_ontology(target_path)
        
        # Step 4: Load into OntServe (if available)
        if OntologyManager:
            ontserve_results = self._load_into_ontserve(target_path, analysis_results)
        else:
            ontserve_results = {"ontserve_loaded": False, "reason": "OntologyManager not available"}
        
        # Step 5: Update progress tracking
        self._update_progress_tracking(analysis_results, ontserve_results)
        
        # Compile final results
        import_results = {
            "source_file": str(source_path),
            "target_file": str(target_path),
            "analysis": analysis_results,
            "ontserve_import": ontserve_results,
            "timestamp": datetime.now().isoformat(),
            "ready_for_migration": self._assess_migration_readiness(analysis_results, ontserve_results)
        }
        
        self.logger.info("Intermediate ontology import complete!")
        return import_results

    def _create_working_copy(self, source_path: Path) -> Path:
        """Create working copy of ontology in OntServe data directory."""
        target_dir = Path("OntServe/data/ontologies")
        target_dir.mkdir(parents=True, exist_ok=True)
        
        target_path = target_dir / "proethica-intermediate-working.ttl"
        
        # Copy source to working location
        shutil.copy2(source_path, target_path)
        
        self.logger.info(f"Created working copy: {source_path} → {target_path}")
        if self.dashboard:
            self.dashboard.add_activity(
                "Working Copy Created",
                f"Copied {source_path.name} to OntServe working directory",
                "import"
            )
        
        return target_path

    def _analyze_current_ontology(self, file_path: Path) -> Dict:
        """Perform detailed analysis of current ontology structure."""
        self.logger.info("Analyzing current ontology structure...")
        
        analysis = {
            "file_info": {
                "path": str(file_path),
                "size_bytes": file_path.stat().st_size,
                "last_modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
            },
            "entities": {},
            "bfo_compliance": {},
            "quality_issues": [],
            "namespace_analysis": {}
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Basic entity counting
            analysis["entities"] = {
                "classes": content.count('owl:Class'),
                "object_properties": content.count('owl:ObjectProperty'),
                "datatype_properties": content.count('owl:DatatypeProperty'),
                "individuals": content.count('owl:NamedIndividual'),
                "total_lines": len(content.split('\n'))
            }
            
            # Check for quality issues identified in feedback
            analysis["quality_issues"] = self._detect_quality_issues(content)
            
            # Namespace analysis
            analysis["namespace_analysis"] = self._analyze_namespaces(content)
            
            # Core entity detection
            analysis["core_entities"] = self._detect_core_entities(content)
            
            self.logger.info(f"Analysis complete: {analysis['entities']['classes']} classes, {len(analysis['quality_issues'])} issues found")
            
        except Exception as e:
            self.logger.error(f"Failed to analyze ontology: {str(e)}")
            analysis["error"] = str(e)
        
        return analysis

    def _detect_quality_issues(self, content: str) -> List[Dict]:
        """Detect quality issues mentioned in the feedback."""
        issues = []
        
        # Check for rdf:type placeholders in comments
        if 'rdf:type' in content and 'rdfs:comment' in content:
            issues.append({
                "type": "annotation_artifact",
                "description": "Found 'rdf:type' placeholders in rdfs:comment fields",
                "priority": "high",
                "fix_required": "Clean templating artifacts to human-readable definitions"
            })
        
        # Check for meta-typing conflicts
        if 'EntityType' in content or 'EventType' in content:
            issues.append({
                "type": "meta_typing_conflict",
                "description": "Found EntityType/EventType meta-classes mixed with domain classes", 
                "priority": "high",
                "fix_required": "Remove meta-types, use OWL class hierarchy only"
            })
        
        # Check for missing BFO imports
        if 'bfo:' in content and 'owl:imports' not in content:
            issues.append({
                "type": "missing_imports",
                "description": "BFO classes referenced but no import statements found",
                "priority": "medium", 
                "fix_required": "Add proper owl:imports for BFO, RO, IAO"
            })
        
        # Check for disjointness coverage
        if content.count('owl:disjointWith') < 3:
            issues.append({
                "type": "insufficient_disjointness",
                "description": "Limited disjointness axioms found",
                "priority": "medium",
                "fix_required": "Add systematic Continuant/Occurrent and other BFO disjointness"
            })
        
        return issues

    def _analyze_namespaces(self, content: str) -> Dict:
        """Analyze namespace usage and conflicts."""
        namespaces = {}
        
        # Extract namespace prefixes
        lines = content.split('\n')
        for line in lines:
            if line.strip().startswith('@prefix'):
                parts = line.strip().split()
                if len(parts) >= 3:
                    prefix = parts[1].rstrip(':')
                    uri = parts[2].strip('<>')
                    namespaces[prefix] = uri
        
        # Check for required namespaces
        required = {
            'bfo': 'http://purl.obolibrary.org/obo/',
            'ro': 'http://purl.obolibrary.org/obo/', 
            'iao': 'http://purl.obolibrary.org/obo/',
            'owl': 'http://www.w3.org/2002/07/owl#',
            'rdfs': 'http://www.w3.org/2000/01/rdf-schema#'
        }
        
        missing_namespaces = []
        for prefix, expected_uri in required.items():
            if prefix not in namespaces:
                missing_namespaces.append(prefix)
        
        return {
            "declared_namespaces": namespaces,
            "missing_required": missing_namespaces,
            "namespace_count": len(namespaces)
        }

    def _detect_core_entities(self, content: str) -> Dict:
        """Detect the 9 core entity types in the current ontology."""
        core_entities = {
            "Role": {"found": "Role" in content, "classes": []},
            "Principle": {"found": "Principle" in content, "classes": []},
            "Obligation": {"found": "Obligation" in content, "classes": []},
            "State": {"found": "State" in content, "classes": []},
            "Resource": {"found": "Resource" in content, "classes": []},
            "Action": {"found": "Action" in content, "classes": []},
            "Event": {"found": "Event" in content, "classes": []},
            "Capability": {"found": "Capability" in content, "classes": []},
            "Constraint": {"found": "Constraint" in content, "classes": []}
        }
        
        # Basic detection - could be enhanced with proper OWL parsing
        lines = content.split('\n')
        current_class = None
        
        for line in lines:
            line = line.strip()
            if 'a owl:Class' in line:
                # Extract class name (simplified)
                if ':' in line:
                    current_class = line.split(':')[1].split()[0]
                    
                    # Check which core entity this might be
                    for entity_type in core_entities:
                        if entity_type.lower() in current_class.lower():
                            core_entities[entity_type]["classes"].append(current_class)
        
        return core_entities

    def _load_into_ontserve(self, file_path: Path, analysis: Dict) -> Dict:
        """Load ontology into OntServe if available."""
        try:
            manager = OntologyManager()
            
            import_data = {
                "ontology_id": self.target_config["ontology_id"],
                "name": self.source_ontology["name"],
                "version": self.target_config["version"],
                "file_path": str(file_path),
                "namespace": self.source_ontology["namespace"],
                "ontology_iri": self.source_ontology["ontology_iri"],
                "description": self.source_ontology["description"],
                "analysis_summary": analysis,
                "upgrade_target": self.target_config["target_version"]
            }
            
            result = manager.import_ontology(import_data)
            
            if result.get("success", False):
                self.logger.info("✅ Successfully loaded into OntServe")
                return {
                    "ontserve_loaded": True,
                    "ontology_id": self.target_config["ontology_id"],
                    "result": result
                }
            else:
                self.logger.error(f"❌ Failed to load into OntServe: {result.get('error', 'Unknown error')}")
                return {
                    "ontserve_loaded": False,
                    "error": result.get('error', 'Unknown error')
                }
                
        except Exception as e:
            self.logger.error(f"❌ Exception loading into OntServe: {str(e)}")
            return {
                "ontserve_loaded": False,
                "error": str(e)
            }

    def _update_progress_tracking(self, analysis: Dict, ontserve_results: Dict):
        """Update progress tracking with import results."""
        
        if not self.dashboard:
            return
            
        # Mark Foundation Setup tasks as partially complete
        progress_data = self.dashboard._load_progress_data()
        
        # Update Phase 1 progress
        phase_1_progress = progress_data.get("phase_progress", {}).get("1_foundation_setup", {})
        phase_1_progress["completed_tasks"] = 3  # F3.1, F3.2 partially done
        phase_1_progress["status"] = "in_progress"
        phase_1_progress["start_date"] = datetime.now().isoformat()
        
        if "phase_progress" not in progress_data:
            progress_data["phase_progress"] = {}
        progress_data["phase_progress"]["1_foundation_setup"] = phase_1_progress
        
        # Update entity alignment with current status
        for entity_name in self.dashboard.core_entities:
            entity_data = analysis.get("core_entities", {}).get(entity_name, {})
            if entity_data.get("found", False):
                progress_data["entity_alignment"][entity_name]["current_parent"] = "unknown"
                progress_data["entity_alignment"][entity_name]["alignment_status"] = "needs_analysis"
        
        # Update milestone progress
        foundation_milestone = progress_data.get("milestones", {}).get("Foundation Setup Complete", {})
        foundation_milestone["completion_percentage"] = 25  # Import phase complete
        foundation_milestone["status"] = "in_progress"
        
        progress_data["milestones"]["Foundation Setup Complete"] = foundation_milestone
        
        # Add activity log
        progress_data["activity_log"].append({
            "timestamp": datetime.now().isoformat(),
            "action": "Intermediate Ontology Imported",
            "details": f"Loaded {self.source_ontology['name']} - {analysis['entities']['classes']} classes found",
            "category": "import"
        })
        
        self.dashboard._save_progress_data(progress_data)

    def _assess_migration_readiness(self, analysis: Dict, ontserve_results: Dict) -> bool:
        """Assess if ontology is ready for BFO alignment migration."""
        
        readiness_checks = {
            "file_accessible": "error" not in analysis,
            "entities_detected": analysis.get("entities", {}).get("classes", 0) > 0,
            "core_entities_found": sum(1 for entity in analysis.get("core_entities", {}).values() if entity.get("found", False)) >= 7,
            "no_critical_issues": len([issue for issue in analysis.get("quality_issues", []) if issue.get("priority") == "high"]) == 0,
            "ontserve_loaded": ontserve_results.get("ontserve_loaded", False)
        }
        
        return all(readiness_checks.values())

    def generate_import_report(self, import_results: Dict) -> str:
        """Generate comprehensive import report."""
        
        report_lines = [
            "# ProEthica Intermediate Ontology Import Report",
            "",
            f"**Import Date**: {import_results['timestamp']}",
            f"**Source File**: {import_results['source_file']}",
            f"**Working Copy**: {import_results['target_file']}",
            "",
            "## File Analysis",
            ""
        ]
        
        analysis = import_results["analysis"]
        
        # File information
        file_info = analysis.get("file_info", {})
        report_lines.extend([
            f"- **File Size**: {file_info.get('size_bytes', 0):,} bytes",
            f"- **Last Modified**: {file_info.get('last_modified', 'Unknown')}",
            f"- **Total Lines**: {analysis.get('entities', {}).get('total_lines', 0):,}",
            ""
        ])
        
        # Entity counts
        entities = analysis.get("entities", {})
        report_lines.extend([
            "## Entity Summary",
            "",
            f"- **Classes**: {entities.get('classes', 0)}",
            f"- **Object Properties**: {entities.get('object_properties', 0)}",
            f"- **Datatype Properties**: {entities.get('datatype_properties', 0)}", 
            f"- **Individuals**: {entities.get('individuals', 0)}",
            ""
        ])
        
        # Core entities detection
        core_entities = analysis.get("core_entities", {})
        found_count = sum(1 for entity in core_entities.values() if entity.get("found", False))
        
        report_lines.extend([
            "## Core Entity Types Detection",
            "",
            f"**Found**: {found_count}/9 core entity types",
            ""
        ])
        
        for entity_type, entity_data in core_entities.items():
            status = "✅" if entity_data.get("found", False) else "❌"
            classes_found = len(entity_data.get("classes", []))
            report_lines.append(f"- {status} **{entity_type}**: {classes_found} classes detected")
        
        report_lines.append("")
        
        # Quality issues
        quality_issues = analysis.get("quality_issues", [])
        report_lines.extend([
            "## Quality Issues",
            ""
        ])
        
        if quality_issues:
            for issue in quality_issues:
                priority_emoji = "🔥" if issue["priority"] == "high" else "⚠️"
                report_lines.extend([
                    f"### {priority_emoji} {issue['type'].replace('_', ' ').title()}",
                    f"- **Description**: {issue['description']}",
                    f"- **Priority**: {issue['priority'].upper()}",
                    f"- **Fix Required**: {issue['fix_required']}",
                    ""
                ])
        else:
            report_lines.append("No critical quality issues detected.")
        
        report_lines.append("")
        
        # Namespace analysis
        ns_analysis = analysis.get("namespace_analysis", {})
        report_lines.extend([
            "## Namespace Analysis", 
            "",
            f"- **Declared Namespaces**: {ns_analysis.get('namespace_count', 0)}",
            f"- **Missing Required**: {len(ns_analysis.get('missing_required', []))} ({', '.join(ns_analysis.get('missing_required', []))})",
            ""
        ])
        
        # OntServe import status
        ontserve_results = import_results["ontserve_import"]
        status_emoji = "✅" if ontserve_results.get("ontserve_loaded", False) else "❌"
        
        report_lines.extend([
            "## OntServe Import Status",
            "",
            f"{status_emoji} **OntServe Loaded**: {ontserve_results.get('ontserve_loaded', False)}",
        ])
        
        if not ontserve_results.get("ontserve_loaded", False):
            report_lines.append(f"- **Reason**: {ontserve_results.get('error', 'Unknown error')}")
        
        report_lines.extend([
            "",
            "## Migration Readiness",
            "",
            f"**Ready for BFO Migration**: {'✅ YES' if import_results['ready_for_migration'] else '❌ NO'}",
            ""
        ])
        
        # Next steps
        report_lines.extend([
            "## Immediate Next Steps",
            "",
            "1. ✅ Intermediate ontology imported",
            "2. ⏳ Run initial BFO compliance analysis",
            "3. ⏳ Address quality issues if found",
            "4. ⏳ Begin entity migration to BFO patterns",
            "",
            "---",
            f"*Report generated by IntermediateOntologyImporter at {datetime.now().isoformat()}*"
        ])
        
        # Save report
        report_content = "\n".join(report_lines)
        report_path = f"OntServe/data/reports/import_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, 'w') as f:
            f.write(report_content)
        
        self.logger.info(f"Import report saved to {report_path}")
        return report_path

def main():
    """Main execution function."""
    print("ProEthica Intermediate Ontology Importer")
    print("=" * 50)
    
    importer = IntermediateOntologyImporter()
    
    try:
        # Import ontology
        print("\n1. Importing intermediate ontology...")
        results = importer.import_ontology()
        
        # Generate report
        print("\n2. Generating import report...")
        report_path = importer.generate_import_report(results)
        
        # Summary
        print("\n" + "=" * 50)
        print("IMPORT SUMMARY")
        print("=" * 50)
        
        analysis = results["analysis"]
        entities = analysis.get("entities", {})
        
        print(f"📁 Source: {results['source_file']}")
        print(f"📁 Working copy: {results['target_file']}")
        print(f"📊 Classes found: {entities.get('classes', 0)}")
        print(f"🔍 Quality issues: {len(analysis.get('quality_issues', []))}")
        print(f"🎯 Core entities: {sum(1 for e in analysis.get('core_entities', {}).values() if e.get('found', False))}/9")
        print(f"🔧 OntServe loaded: {results['ontserve_import'].get('ontserve_loaded', False)}")
        print(f"✅ Migration ready: {results['ready_for_migration']}")
        print(f"📋 Report: {report_path}")
        
        if results['ready_for_migration']:
            print("\n🚀 Ready for BFO compliance analysis!")
            print("Next: python OntServe/scripts/bfo_alignment_migrator.py --analyze-only")
        else:
            print("\n⚠️ Address quality issues before proceeding with migration.")
        
        return results['ready_for_migration']
        
    except Exception as e:
        print(f"\n❌ Import failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
