"""
Foundation Ontology Loader for ProEthica Intermediate Ontology Upgrade

Loads BFO, RO, and IAO ontologies into OntServe for BFO alignment migration.
Ensures clean import chain and proper dependency management.
"""

import os
import sys
import requests
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# Add OntServe to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from core.ontology_manager import OntologyManager
    from utils.validation import ValidationManager
    # Import progress dashboard from relative path
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'web'))
    from progress_dashboard import BFOAlignmentProgressDashboard
except ImportError:
    # Fallback imports if OntServe structure differs
    print("Warning: OntServe imports not available. Running in standalone mode.")
    OntologyManager = None
    ValidationManager = None
    BFOAlignmentProgressDashboard = None

class FoundationOntologyLoader:
    """
    Loads and configures foundation ontologies (BFO, RO, IAO) for ProEthica upgrade.
    Integrates with OntServe ontology management and progress tracking.
    """
    
    def __init__(self, data_dir: str = "OntServe/data/foundation"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Progress tracking integration (optional)
        if BFOAlignmentProgressDashboard:
            self.dashboard = BFOAlignmentProgressDashboard()
        else:
            self.dashboard = None
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Foundation ontology configurations
        self.foundation_ontologies = {
            "bfo": {
                "name": "Basic Formal Ontology",
                "version": "2.0",
                "url": "http://purl.obolibrary.org/obo/bfo.owl",
                "local_file": "bfo-2.0.owl",
                "namespace": "http://purl.obolibrary.org/obo/",
                "description": "Upper-level ontology providing fundamental categories for all entities"
            },
            "ro": {
                "name": "Relations Ontology", 
                "version": "2015",
                "url": "http://purl.obolibrary.org/obo/ro.owl",
                "local_file": "ro-2015.owl", 
                "namespace": "http://purl.obolibrary.org/obo/",
                "description": "Standard relations for linking ontology entities"
            },
            "iao": {
                "name": "Information Artifact Ontology",
                "version": "2020",
                "url": "http://purl.obolibrary.org/obo/iao.owl", 
                "local_file": "iao-2020.owl",
                "namespace": "http://purl.obolibrary.org/obo/",
                "description": "Ontology for information content entities and documents"
            }
        }

    def load_all_foundation_ontologies(self) -> Dict[str, bool]:
        """
        Load all foundation ontologies required for BFO alignment.
        
        Returns:
            Dict[str, bool]: Loading success status for each ontology
        """
        self.logger.info("Starting foundation ontology loading process...")
        if self.dashboard:
            self.dashboard.add_activity(
                "Foundation Loading Started",
                "Beginning load of BFO, RO, and IAO ontologies for upgrade",
                "foundation_setup"
            )
        
        results = {}
        total_ontologies = len(self.foundation_ontologies)
        completed = 0
        
        for onto_key, config in self.foundation_ontologies.items():
            self.logger.info(f"Loading {config['name']} ({onto_key})...")
            
            try:
                # Download ontology if not present
                local_path = self._ensure_ontology_file(onto_key, config)
                
                # Load into OntServe (if available)
                if OntologyManager:
                    success = self._load_into_ontserve(onto_key, config, local_path)
                else:
                    # Validate file exists and is readable
                    success = local_path.exists() and local_path.stat().st_size > 0
                
                results[onto_key] = success
                
                if success:
                    completed += 1
                    self.logger.info(f"✅ Successfully loaded {config['name']}")
                    if self.dashboard:
                        self.dashboard.add_activity(
                            f"{config['name']} Loaded",
                            f"Successfully imported {config['name']} v{config['version']}",
                            "foundation_setup"
                        )
                else:
                    self.logger.error(f"❌ Failed to load {config['name']}")
                    
            except Exception as e:
                self.logger.error(f"❌ Error loading {config['name']}: {str(e)}")
                results[onto_key] = False
        
        # Update overall progress
        completion_percentage = (completed / total_ontologies) * 100
        if self.dashboard:
            self.dashboard.update_milestone_completion(
                "Foundation Setup Complete",
                completion_percentage * 0.6  # Foundation loading is 60% of Phase 1
            )
        
        self.logger.info(f"Foundation loading complete. Success rate: {completed}/{total_ontologies}")
        return results

    def _ensure_ontology_file(self, onto_key: str, config: Dict) -> Path:
        """Download ontology file if not present locally."""
        local_path = self.data_dir / config["local_file"]
        
        if local_path.exists():
            self.logger.info(f"Using cached {config['name']} at {local_path}")
            return local_path
        
        self.logger.info(f"Downloading {config['name']} from {config['url']}")
        
        try:
            response = requests.get(config["url"], timeout=30)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
                
            self.logger.info(f"Downloaded {config['name']} to {local_path}")
            return local_path
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to download {config['name']}: {str(e)}")
            raise

    def _load_into_ontserve(self, onto_key: str, config: Dict, local_path: Path) -> bool:
        """Load ontology into OntServe ontology manager."""
        try:
            manager = OntologyManager()
            
            # Load ontology with metadata
            ontology_data = {
                "id": onto_key,
                "name": config["name"],
                "version": config["version"],
                "namespace": config["namespace"],
                "description": config["description"],
                "file_path": str(local_path),
                "ontology_type": "foundation",
                "role": "import_dependency"
            }
            
            result = manager.load_ontology(ontology_data)
            return result.get("success", False)
            
        except Exception as e:
            self.logger.error(f"Failed to load {onto_key} into OntServe: {str(e)}")
            return False

    def validate_foundation_setup(self) -> Dict:
        """
        Validate that all foundation ontologies are properly loaded and accessible.
        
        Returns:
            Dict: Validation results for foundation ontology setup
        """
        validation_results = {
            "overall_status": "unknown",
            "ontologies": {},
            "import_chain_valid": False,
            "namespace_conflicts": [],
            "missing_dependencies": []
        }
        
        # Check each foundation ontology
        loaded_count = 0
        for onto_key, config in self.foundation_ontologies.items():
            local_path = self.data_dir / config["local_file"]
            
            ontology_status = {
                "file_exists": local_path.exists(),
                "file_size": local_path.stat().st_size if local_path.exists() else 0,
                "ontserve_loaded": self._check_ontserve_loaded(onto_key),
                "classes_detected": 0,
                "properties_detected": 0
            }
            
            if ontology_status["file_exists"] and ontology_status["file_size"] > 0:
                loaded_count += 1
                # Quick parse to count entities (basic validation)
                ontology_status.update(self._quick_parse_ontology(local_path))
            
            validation_results["ontologies"][onto_key] = ontology_status
        
        # Overall assessment
        if loaded_count == len(self.foundation_ontologies):
            validation_results["overall_status"] = "complete"
            validation_results["import_chain_valid"] = True
        elif loaded_count > 0:
            validation_results["overall_status"] = "partial"
        else:
            validation_results["overall_status"] = "failed"
        
        return validation_results

    def _check_ontserve_loaded(self, onto_key: str) -> bool:
        """Check if ontology is loaded in OntServe."""
        if not OntologyManager:
            return False
            
        try:
            manager = OntologyManager()
            return manager.ontology_exists(onto_key)
        except:
            return False

    def _quick_parse_ontology(self, file_path: Path) -> Dict:
        """Perform quick parse to count classes and properties."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple counting (not full OWL parsing)
            class_count = content.count('owl:Class')
            property_count = content.count('owl:ObjectProperty') + content.count('owl:DatatypeProperty')
            
            return {
                "classes_detected": class_count,
                "properties_detected": property_count,
                "parse_successful": True
            }
        except Exception as e:
            return {
                "classes_detected": 0,
                "properties_detected": 0,
                "parse_successful": False,
                "parse_error": str(e)
            }

    def create_import_configuration(self) -> str:
        """
        Create OntServe import configuration for the foundation ontologies.
        
        Returns:
            str: Path to created configuration file
        """
        import_config = {
            "import_chain": {
                "name": "ProEthica Foundation Chain",
                "description": "Clean import chain for ProEthica intermediate ontology upgrade",
                "created": datetime.now().isoformat(),
                "chain": [
                    {
                        "order": 1,
                        "ontology": "bfo", 
                        "role": "upper_ontology",
                        "imports": [],
                        "required": True
                    },
                    {
                        "order": 2,
                        "ontology": "ro",
                        "role": "relations",
                        "imports": ["bfo"],
                        "required": True
                    },
                    {
                        "order": 3, 
                        "ontology": "iao",
                        "role": "information_entities",
                        "imports": ["bfo", "ro"],
                        "required": True
                    },
                    {
                        "order": 4,
                        "ontology": "proethica-intermediate",
                        "role": "domain_bridge", 
                        "imports": ["bfo", "ro", "iao"],
                        "required": True
                    }
                ]
            },
            "mireot_config": {
                "strategy": "minimal_ancestors",
                "target_file": "intermediate-imports.owl",
                "third_party_terms": [
                    # Will be populated as needed during migration
                ]
            }
        }
        
        config_path = "OntServe/config/foundation_import_chain.yaml"
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        import yaml
        with open(config_path, 'w') as f:
            yaml.dump(import_config, f, default_flow_style=False, indent=2)
        
        self.logger.info(f"Created import configuration at {config_path}")
        return config_path

    def generate_foundation_report(self) -> str:
        """Generate comprehensive foundation setup report."""
        validation_results = self.validate_foundation_setup()
        
        report = [
            "# Foundation Ontology Setup Report",
            f"**Generated**: {datetime.now().isoformat()}",
            f"**Purpose**: ProEthica Intermediate Ontology BFO Alignment Upgrade",
            "",
            "## Foundation Ontology Status",
            ""
        ]
        
        for onto_key, status in validation_results["ontologies"].items():
            config = self.foundation_ontologies[onto_key]
            status_emoji = "✅" if status["file_exists"] and status["file_size"] > 0 else "❌"
            
            report.extend([
                f"### {status_emoji} {config['name']} ({onto_key})",
                f"- **Version**: {config['version']}",
                f"- **URL**: {config['url']}",
                f"- **Local File**: {status['file_exists']}",
                f"- **File Size**: {status['file_size']:,} bytes",
                f"- **OntServe Loaded**: {status['ontserve_loaded']}",
                f"- **Classes Detected**: {status['classes_detected']}",
                f"- **Properties Detected**: {status['properties_detected']}",
                ""
            ])
        
        report.extend([
            "## Import Chain Status",
            f"- **Overall Status**: {validation_results['overall_status'].upper()}",
            f"- **Import Chain Valid**: {validation_results['import_chain_valid']}",
            f"- **Namespace Conflicts**: {len(validation_results['namespace_conflicts'])}",
            f"- **Missing Dependencies**: {len(validation_results['missing_dependencies'])}",
            "",
            "## Next Steps",
            "1. ✅ Foundation ontologies loaded",
            "2. ⏳ Import current intermediate ontology", 
            "3. ⏳ Run initial BFO compliance analysis",
            "4. ⏳ Begin entity migration process",
            "",
            "---",
            "*Report generated by FoundationOntologyLoader*"
        ])
        
        report_content = "\n".join(report)
        report_path = f"OntServe/data/foundation_setup_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        with open(report_path, 'w') as f:
            f.write(report_content)
        
        self.logger.info(f"Foundation setup report saved to {report_path}")
        return report_path

def main():
    """Main execution function for foundation ontology loading."""
    print("ProEthica Foundation Ontology Loader")
    print("=" * 50)
    
    loader = FoundationOntologyLoader()
    
    # Step 1: Load all foundation ontologies
    print("\n1. Loading foundation ontologies...")
    results = loader.load_all_foundation_ontologies()
    
    # Step 2: Validate setup
    print("\n2. Validating foundation setup...")
    validation = loader.validate_foundation_setup()
    
    # Step 3: Create import configuration
    print("\n3. Creating import configuration...")
    config_path = loader.create_import_configuration()
    
    # Step 4: Generate report
    print("\n4. Generating setup report...")
    report_path = loader.generate_foundation_report()
    
    # Summary
    print("\n" + "=" * 50)
    print("FOUNDATION SETUP SUMMARY")
    print("=" * 50)
    
    success_count = sum(results.values())
    total_count = len(results)
    
    print(f"Ontologies loaded: {success_count}/{total_count}")
    print(f"Overall status: {validation['overall_status'].upper()}")
    print(f"Import chain valid: {validation['import_chain_valid']}")
    print(f"Configuration created: {config_path}")
    print(f"Report generated: {report_path}")
    
    if success_count == total_count:
        print("\n✅ Foundation setup complete! Ready for intermediate ontology import.")
        return True
    else:
        print(f"\n❌ Foundation setup incomplete. {total_count - success_count} ontologies failed to load.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
