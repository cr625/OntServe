#!/usr/bin/env python3
"""
ProEthica Intermediate Ontology BFO Alignment Migrator

This script provides utilities for migrating the ProEthica Intermediate Ontology
to full BFO compliance using OntServe's entity extraction and validation capabilities.
"""

import os
import sys
import yaml
import logging
import json
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import re
from dataclasses import dataclass
from pathlib import Path

# Add OntServe modules to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from editor.services import OntologyEntityService, OntologyValidationService
    from core.enhanced_processor import EnhancedOntologyProcessor, ProcessingOptions
    from storage.file_storage import FileStorage
    from web.models import db, Ontology, OntologyEntity, OntologyVersion
except ImportError as e:
    logging.error(f"Failed to import OntServe modules: {e}")
    logging.info("Ensure OntServe is properly installed and configured")
    sys.exit(1)

# Configure logging - ensure logs directory exists
logs_dir = Path("OntServe/logs")
logs_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('OntServe/logs/bfo_alignment_migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class MigrationRule:
    """Configuration for entity migration rules."""
    entity_type: str
    target_parent: str
    pattern_match: List[str]
    validation_rules: List[str]
    examples: List[str]
    alternative_parent: Optional[str] = None


@dataclass
class MigrationResult:
    """Result of a migration operation."""
    success: bool
    entities_migrated: int
    entities_skipped: int
    errors: List[str]
    warnings: List[str]
    compliance_before: float
    compliance_after: float
    migration_summary: Dict[str, Any]


class BFOAlignmentMigrator:
    """Main class for performing BFO alignment migration on intermediate ontology."""
    
    def __init__(self, config_path: str = None):
        """Initialize the migrator with configuration."""
        self.config_path = config_path or 'config/intermediate-ontology-upgrade.yaml'
        self.config = self._load_configuration()
        
        # Initialize storage backend
        self.storage = FileStorage()
        
        # Initialize OntServe services
        self.entity_service = OntologyEntityService(self.storage)
        self.validation_service = OntologyValidationService(self.storage)
        self.enhanced_processor = EnhancedOntologyProcessor(self.storage)
        
        # Migration state
        self.migration_rules = self._parse_migration_rules()
        self.current_ontology = None
        self.backup_created = False
        
        logger.info("BFO Alignment Migrator initialized")
        
    def _load_configuration(self) -> Dict[str, Any]:
        """Load YAML configuration file."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {self.config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration file: {e}")
            raise
            
    def _parse_migration_rules(self) -> Dict[str, MigrationRule]:
        """Parse migration rules from configuration."""
        rules = {}
        entity_mappings = self.config.get('bfo_alignment', {}).get('entity_mappings', {})
        
        for entity_type, mapping in entity_mappings.items():
            rule = MigrationRule(
                entity_type=entity_type,
                target_parent=mapping['target_parent'],
                pattern_match=mapping.get('pattern_match', []),
                validation_rules=mapping.get('validation_rules', []),
                examples=mapping.get('examples', []),
                alternative_parent=mapping.get('alternative_parent')
            )
            rules[entity_type] = rule
            
        logger.info(f"Loaded {len(rules)} migration rules")
        return rules
    
    def load_foundation_ontologies(self) -> bool:
        """Load BFO, RO, and IAO ontologies into OntServe."""
        logger.info("Loading foundation ontologies...")
        
        try:
            foundation_configs = self.config.get('foundation_ontologies', [])
            
            for foundation in foundation_configs:
                ontology_id = foundation['ontology_id']
                uri = foundation['uri']
                local_path = foundation.get('local_path', '')
                
                logger.info(f"Loading {ontology_id} from {uri}")
                
                # Check if ontology file exists
                if local_path and os.path.exists(local_path):
                    with open(local_path, 'r') as f:
                        content = f.read()
                else:
                    # Attempt to download or load from URI
                    logger.warning(f"Local file not found for {ontology_id}, attempting to load from URI")
                    # This would require web fetching capability
                    content = self._fetch_ontology_from_uri(uri)
                
                # Store in OntServe
                result = self.storage.store(ontology_id, content, {
                    'uri': uri,
                    'role': foundation.get('role', 'foundation'),
                    'loaded_at': datetime.utcnow().isoformat()
                })
                
                # Extract entities for semantic search
                entities = self.entity_service.extract_and_store_entities(
                    ontology_id, force_refresh=True
                )
                
                logger.info(f"Successfully loaded {ontology_id} with {len(entities)} entities")
                
            return True
            
        except Exception as e:
            logger.error(f"Error loading foundation ontologies: {e}")
            return False
    
    def _fetch_ontology_from_uri(self, uri: str) -> str:
        """Fetch ontology content from URI (placeholder implementation)."""
        # This would need to be implemented with proper web fetching
        logger.warning(f"URI fetching not implemented for {uri}")
        return ""
    
    def import_current_intermediate_ontology(self) -> bool:
        """Import the current intermediate ontology into OntServe."""
        logger.info("Importing current intermediate ontology...")
        
        try:
            target_config = self.config.get('target_ontology', {})
            current_file = target_config.get('current_file')
            ontology_id = target_config.get('ontology_id', 'proethica-intermediate')
            
            if not current_file or not os.path.exists(current_file):
                logger.error(f"Current ontology file not found: {current_file}")
                return False
                
            # Create backup
            backup_file = target_config.get('backup_file')
            if backup_file and not self.backup_created:
                self._create_backup(current_file, backup_file)
                self.backup_created = True
            
            # Read current ontology content
            with open(current_file, 'r') as f:
                content = f.read()
                
            # Store in OntServe
            result = self.storage.store(ontology_id, content, {
                'source_file': current_file,
                'imported_at': datetime.utcnow().isoformat(),
                'backup_created': self.backup_created
            })
            
            # Extract entities for analysis
            entities = self.entity_service.extract_and_store_entities(
                ontology_id, force_refresh=True
            )
            
            logger.info(f"Successfully imported intermediate ontology with {len(entities)} entities")
            self.current_ontology = ontology_id
            return True
            
        except Exception as e:
            logger.error(f"Error importing current ontology: {e}")
            return False
            
    def _create_backup(self, source_file: str, backup_file: str) -> None:
        """Create backup of the current ontology file."""
        try:
            import shutil
            os.makedirs(os.path.dirname(backup_file), exist_ok=True)
            shutil.copy2(source_file, backup_file)
            logger.info(f"Backup created: {backup_file}")
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            raise
    
    def analyze_current_compliance(self) -> Dict[str, Any]:
        """Analyze current BFO compliance of the intermediate ontology."""
        logger.info("Analyzing current BFO compliance...")
        
        if not self.current_ontology:
            raise ValueError("No ontology loaded. Call import_current_intermediate_ontology() first.")
            
        try:
            # Get all entities for the ontology
            ontology = db.session.query(Ontology).filter_by(
                ontology_id=self.current_ontology
            ).first()
            
            if not ontology:
                raise ValueError(f"Ontology {self.current_ontology} not found in database")
                
            entities = db.session.query(OntologyEntity).filter_by(
                ontology_id=ontology.id
            ).all()
            
            # Analyze each entity for BFO compliance
            compliance_results = {
                'total_entities': len(entities),
                'compliant_entities': 0,
                'non_compliant_entities': [],
                'compliance_by_type': {},
                'missing_annotations': [],
                'recommendations': []
            }
            
            for entity in entities:
                entity_analysis = self._analyze_entity_compliance(entity)
                
                if entity_analysis['compliant']:
                    compliance_results['compliant_entities'] += 1
                else:
                    compliance_results['non_compliant_entities'].append({
                        'uri': entity.uri,
                        'label': entity.label,
                        'issues': entity_analysis['issues'],
                        'recommendations': entity_analysis['recommendations']
                    })
                
                # Track compliance by entity type
                entity_type = entity_analysis.get('detected_type', 'unknown')
                if entity_type not in compliance_results['compliance_by_type']:
                    compliance_results['compliance_by_type'][entity_type] = {
                        'total': 0, 'compliant': 0
                    }
                
                compliance_results['compliance_by_type'][entity_type]['total'] += 1
                if entity_analysis['compliant']:
                    compliance_results['compliance_by_type'][entity_type]['compliant'] += 1
                    
            # Calculate overall compliance percentage
            compliance_percentage = (
                compliance_results['compliant_entities'] / 
                compliance_results['total_entities'] * 100
                if compliance_results['total_entities'] > 0 else 0
            )
            
            compliance_results['compliance_percentage'] = round(compliance_percentage, 2)
            
            logger.info(f"Compliance analysis complete: {compliance_percentage:.1f}% compliant")
            return compliance_results
            
        except Exception as e:
            logger.error(f"Error during compliance analysis: {e}")
            raise
    
    def _analyze_entity_compliance(self, entity: OntologyEntity) -> Dict[str, Any]:
        """Analyze a single entity for BFO compliance."""
        analysis = {
            'compliant': True,
            'issues': [],
            'recommendations': [],
            'detected_type': 'unknown'
        }
        
        # Detect entity type based on name patterns
        detected_type = self._detect_entity_type(entity.uri, entity.label or "")
        analysis['detected_type'] = detected_type
        
        if detected_type in self.migration_rules:
            rule = self.migration_rules[detected_type]
            expected_parent = rule.target_parent
            
            # Check if entity has proper BFO parent
            if not self._has_bfo_parent(entity, expected_parent):
                analysis['compliant'] = False
                analysis['issues'].append(f"Missing proper BFO parent: should be {expected_parent}")
                analysis['recommendations'].append(f"Add {expected_parent} as superclass")
        
        # Check for required annotations
        if not entity.label:
            analysis['issues'].append("Missing rdfs:label")
            analysis['recommendations'].append("Add rdfs:label annotation")
            
        if not entity.comment:
            analysis['issues'].append("Missing iao:definition")
            analysis['recommendations'].append("Add iao:definition annotation")
        
        if analysis['issues']:
            analysis['compliant'] = False
            
        return analysis
    
    def _detect_entity_type(self, uri: str, label: str) -> str:
        """Detect entity type based on URI and label patterns."""
        text_to_check = f"{uri} {label}".lower()
        
        # Check against migration rule patterns
        for entity_type, rule in self.migration_rules.items():
            for pattern in rule.pattern_match:
                # Convert pattern to regex (simple * wildcard support)
                regex_pattern = pattern.lower().replace('*', '.*')
                if re.search(regex_pattern, text_to_check):
                    return entity_type
                    
        # Check examples
        for entity_type, rule in self.migration_rules.items():
            for example in rule.examples:
                if example.lower() in text_to_check:
                    return entity_type
        
        return 'unknown'
    
    def _has_bfo_parent(self, entity: OntologyEntity, expected_parent: str) -> bool:
        """Check if entity has the expected BFO parent class."""
        if entity.parent_uri:
            return expected_parent.lower() in entity.parent_uri.lower()
        return False
    
    def generate_migration_plan(self) -> Dict[str, Any]:
        """Generate a detailed migration plan based on compliance analysis."""
        logger.info("Generating migration plan...")
        
        compliance_analysis = self.analyze_current_compliance()
        
        migration_plan = {
            'total_entities_to_migrate': len(compliance_analysis['non_compliant_entities']),
            'migrations_by_type': {},
            'migration_steps': [],
            'estimated_duration_minutes': 0,
            'prerequisites': [],
            'risks': []
        }
        
        # Group migrations by type
        for entity in compliance_analysis['non_compliant_entities']:
            uri = entity['uri']
            entity_type = self._detect_entity_type(uri, entity.get('label', ''))
            
            if entity_type not in migration_plan['migrations_by_type']:
                migration_plan['migrations_by_type'][entity_type] = {
                    'count': 0,
                    'target_parent': self.migration_rules.get(entity_type, {}).target_parent,
                    'entities': []
                }
                
            migration_plan['migrations_by_type'][entity_type]['count'] += 1
            migration_plan['migrations_by_type'][entity_type]['entities'].append(entity)
        
        # Generate migration steps
        step_id = 1
        for entity_type, migration_info in migration_plan['migrations_by_type'].items():
            if entity_type in self.migration_rules:
                rule = self.migration_rules[entity_type]
                
                step = {
                    'step_id': step_id,
                    'entity_type': entity_type,
                    'target_parent': rule.target_parent,
                    'entity_count': migration_info['count'],
                    'validation_rules': rule.validation_rules,
                    'estimated_minutes': migration_info['count'] * 0.5  # 30 seconds per entity
                }
                
                migration_plan['migration_steps'].append(step)
                migration_plan['estimated_duration_minutes'] += step['estimated_minutes']
                step_id += 1
        
        # Add prerequisites
        migration_plan['prerequisites'] = [
            'Foundation ontologies (BFO, RO, IAO) loaded',
            'Backup created',
            'Validation pipeline configured'
        ]
        
        # Add risks
        migration_plan['risks'] = [
            'Potential reasoning inconsistencies after migration',
            'Changes may affect existing ProEthica integration',
            'Some manual review may be required for complex cases'
        ]
        
        logger.info(f"Migration plan generated: {len(migration_plan['migration_steps'])} steps, "
                   f"{migration_plan['estimated_duration_minutes']:.1f} minutes estimated")
        
        return migration_plan
    
    def execute_migration(self, migration_plan: Dict[str, Any] = None, dry_run: bool = False) -> MigrationResult:
        """Execute the BFO alignment migration."""
        logger.info(f"Starting migration execution (dry_run={dry_run})")
        
        if migration_plan is None:
            migration_plan = self.generate_migration_plan()
        
        # Get baseline compliance
        baseline_analysis = self.analyze_current_compliance()
        compliance_before = baseline_analysis['compliance_percentage']
        
        result = MigrationResult(
            success=True,
            entities_migrated=0,
            entities_skipped=0,
            errors=[],
            warnings=[],
            compliance_before=compliance_before,
            compliance_after=compliance_before,
            migration_summary={}
        )
        
        try:
            # Execute migration steps
            for step in migration_plan['migration_steps']:
                step_result = self._execute_migration_step(step, dry_run)
                
                result.entities_migrated += step_result['migrated']
                result.entities_skipped += step_result['skipped']
                result.errors.extend(step_result['errors'])
                result.warnings.extend(step_result['warnings'])
                
                if step_result['errors']:
                    logger.warning(f"Step {step['step_id']} completed with errors")
                else:
                    logger.info(f"Step {step['step_id']} completed successfully")
            
            # Validate after migration
            if not dry_run and not result.errors:
                logger.info("Running post-migration validation...")
                post_analysis = self.analyze_current_compliance()
                result.compliance_after = post_analysis['compliance_percentage']
                
                # Run consistency check
                consistency_result = self._run_consistency_check()
                if not consistency_result['consistent']:
                    result.errors.extend(consistency_result['errors'])
                    result.success = False
            
            # Generate summary
            result.migration_summary = {
                'steps_completed': len(migration_plan['migration_steps']),
                'compliance_improvement': result.compliance_after - result.compliance_before,
                'dry_run': dry_run,
                'completed_at': datetime.utcnow().isoformat()
            }
            
            if result.errors:
                result.success = False
                logger.error(f"Migration completed with {len(result.errors)} errors")
            else:
                logger.info(f"Migration completed successfully: "
                           f"{result.compliance_after:.1f}% compliance "
                           f"(+{result.compliance_after - result.compliance_before:.1f}%)")
            
        except Exception as e:
            logger.error(f"Migration execution failed: {e}")
            result.success = False
            result.errors.append(str(e))
        
        return result
    
    def _execute_migration_step(self, step: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
        """Execute a single migration step."""
        entity_type = step['entity_type']
        target_parent = step['target_parent']
        
        logger.info(f"Executing step {step['step_id']}: migrating {entity_type} to {target_parent}")
        
        step_result = {
            'migrated': 0,
            'skipped': 0,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Find entities matching this type
            entities_to_migrate = self._find_entities_by_type(entity_type)
            
            for entity in entities_to_migrate:
                try:
                    if dry_run:
                        logger.info(f"DRY RUN: Would migrate {entity.uri} to {target_parent}")
                        step_result['migrated'] += 1
                    else:
                        # Perform actual migration
                        migration_success = self._migrate_entity(entity, target_parent)
                        
                        if migration_success:
                            step_result['migrated'] += 1
                            logger.debug(f"Migrated {entity.uri}")
                        else:
                            step_result['skipped'] += 1
                            step_result['warnings'].append(f"Failed to migrate {entity.uri}")
                            
                except Exception as e:
                    step_result['errors'].append(f"Error migrating {entity.uri}: {str(e)}")
                    
        except Exception as e:
            step_result['errors'].append(f"Step execution error: {str(e)}")
        
        return step_result
    
    def _find_entities_by_type(self, entity_type: str) -> List[OntologyEntity]:
        """Find entities matching the specified type."""
        if not self.current_ontology:
            return []
            
        ontology = db.session.query(Ontology).filter_by(
            ontology_id=self.current_ontology
        ).first()
        
        if not ontology:
            return []
        
        entities = db.session.query(OntologyEntity).filter_by(
            ontology_id=ontology.id
        ).all()
        
        # Filter entities by detected type
        matching_entities = []
        for entity in entities:
            detected_type = self._detect_entity_type(entity.uri, entity.label or "")
            if detected_type == entity_type:
                matching_entities.append(entity)
                
        return matching_entities
    
    def _migrate_entity(self, entity: OntologyEntity, target_parent: str) -> bool:
        """Migrate a single entity to the target BFO parent."""
        try:
            # Update parent_uri
            entity.parent_uri = target_parent
            
            # Update modification timestamp
            entity.updated_at = datetime.utcnow()
            
            # Commit to database
            db.session.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to migrate entity {entity.uri}: {e}")
            db.session.rollback()
            return False
    
    def _run_consistency_check(self) -> Dict[str, Any]:
        """Run consistency check on the ontology after migration."""
        logger.info("Running consistency check...")
        
        try:
            # This would use the enhanced processor's reasoning capabilities
            options = ProcessingOptions(
                use_reasoning=True,
                reasoner_type='elk',  # Fast reasoner for consistency check
                validate_consistency=True,
                include_inferred=False
            )
            
            result = self.enhanced_processor.process_ontology(
                self.current_ontology, options
            )
            
            return {
                'consistent': result.success and not result.errors,
                'errors': result.errors if result.errors else [],
                'warnings': result.warnings if result.warnings else []
            }
            
        except Exception as e:
            logger.error(f"Consistency check failed: {e}")
            return {
                'consistent': False,
                'errors': [str(e)],
                'warnings': []
            }
    
    def export_upgraded_ontology(self, output_path: str = None) -> str:
        """Export the upgraded ontology to a file."""
        if not output_path:
            target_config = self.config.get('target_ontology', {})
            output_path = target_config.get('output_file', 'proethica-intermediate-v2.ttl')
        
        logger.info(f"Exporting upgraded ontology to {output_path}")
        
        try:
            # Retrieve ontology content from storage
            result = self.storage.retrieve(self.current_ontology)
            content = result['content']
            
            # Add upgrade metadata
            metadata = {
                'upgraded_at': datetime.utcnow().isoformat(),
                'bfo_compliant': True,
                'upgrade_version': '2.0.0',
                'original_file': self.config.get('target_ontology', {}).get('current_file')
            }
            
            # Write to output file
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(content)
                
            # Write metadata
            metadata_path = output_path.replace('.ttl', '_metadata.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
                
            logger.info(f"Successfully exported to {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            raise


def main():
    """Main entry point for the migration script."""
    import argparse
    
    parser = argparse.ArgumentParser(description='BFO Alignment Migrator for ProEthica Intermediate Ontology')
    parser.add_argument('--config', default='config/intermediate-ontology-upgrade.yaml',
                       help='Configuration file path')
    parser.add_argument('--dry-run', action='store_true',
                       help='Perform a dry run without making changes')
    parser.add_argument('--skip-foundation', action='store_true',
                       help='Skip loading foundation ontologies')
    parser.add_argument('--analyze-only', action='store_true',
                       help='Only analyze compliance, do not migrate')
    parser.add_argument('--output', help='Output file path for upgraded ontology')
    
    args = parser.parse_args()
    
    try:
        # Initialize migrator
        migrator = BFOAlignmentMigrator(config_path=args.config)
        
        # Load foundation ontologies
        if not args.skip_foundation:
            if not migrator.load_foundation_ontologies():
                logger.error("Failed to load foundation ontologies")
                return 1
        
        # Import current intermediate ontology
        if not migrator.import_current_intermediate_ontology():
            logger.error("Failed to import current intermediate ontology")
            return 1
        
        # Analyze compliance
        compliance_analysis = migrator.analyze_current_compliance()
        print(f"\nCurrent BFO Compliance: {compliance_analysis['compliance_percentage']}%")
        print(f"Non-compliant entities: {len(compliance_analysis['non_compliant_entities'])}")
        
        if args.analyze_only:
            return 0
        
        # Generate and execute migration
        migration_plan = migrator.generate_migration_plan()
        print(f"\nMigration Plan: {len(migration_plan['migration_steps'])} steps")
        print(f"Estimated duration: {migration_plan['estimated_duration_minutes']:.1f} minutes")
        
        result = migrator.execute_migration(migration_plan, dry_run=args.dry_run)
        
        print(f"\nMigration Result:")
        print(f"Success: {result.success}")
        print(f"Entities migrated: {result.entities_migrated}")
        print(f"Entities skipped: {result.entities_skipped}")
        print(f"Compliance: {result.compliance_before:.1f}% -> {result.compliance_after:.1f}%")
        
        if result.errors:
            print(f"Errors ({len(result.errors)}):")
            for error in result.errors:
                print(f"  - {error}")
        
        if result.warnings:
            print(f"Warnings ({len(result.warnings)}):")
            for warning in result.warnings:
                print(f"  - {warning}")
        
        # Export if successful
        if result.success and not args.dry_run:
            output_path = migrator.export_upgraded_ontology(args.output)
            print(f"\nUpgraded ontology exported to: {output_path}")
        
        return 0 if result.success else 1
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
