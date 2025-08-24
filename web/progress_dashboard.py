"""
ProEthica Intermediate Ontology Upgrade Progress Dashboard

Real-time progress tracking for BFO alignment migration with web UI integration.
Provides milestone visibility and detailed task completion status.
"""

import os
import json
import yaml
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class MilestoneStatus:
    """Represents the status of a project milestone."""
    name: str
    phase: str
    target_date: str
    completion_percentage: float
    status: str  # 'not_started', 'in_progress', 'completed', 'blocked'
    tasks_completed: int
    tasks_total: int
    validation_passed: bool
    notes: Optional[str] = None

@dataclass
class EntityAlignmentStatus:
    """Tracks BFO alignment status for each core entity type."""
    entity_name: str
    current_parent: Optional[str]
    target_bfo_parent: str
    alignment_status: str  # 'unaligned', 'partial', 'complete'
    validation_errors: List[str]
    migration_date: Optional[str] = None

class BFOAlignmentProgressDashboard:
    """
    Dashboard for tracking ProEthica Intermediate Ontology BFO alignment progress.
    Integrates with OntServe editor for real-time milestone visibility.
    """
    
    def __init__(self, config_path: str = "OntServe/config/intermediate-ontology-upgrade.yaml"):
        self.config_path = config_path
        self.project_start_date = "2025-08-24"
        self.target_completion_date = "2025-10-19"
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize core entities tracking
        self.core_entities = [
            "Role", "Principle", "Obligation", "State", "Resource", 
            "Action", "Event", "Capability", "Constraint"
        ]
        
        # Progress data file
        self.progress_file = "OntServe/data/upgrade_progress.json"
        self._ensure_progress_file()

    def _load_config(self) -> Dict:
        """Load the upgrade configuration file."""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return self._default_config()
    
    def _default_config(self) -> Dict:
        """Default configuration if config file not found."""
        return {
            "project": {
                "name": "ProEthica Intermediate Ontology BFO Alignment",
                "version": "2.0.0",
                "target_profile": "OWL_2_EL"
            },
            "phases": {
                "1_foundation_setup": {"weeks": 2, "tasks": 16},
                "2_entity_migration": {"weeks": 2, "tasks": 36}, 
                "3_relations_properties": {"weeks": 1, "tasks": 12},
                "4_quality_assurance": {"weeks": 1, "tasks": 15},
                "5_ontserver_integration": {"weeks": 1, "tasks": 8},
                "6_documentation_validation": {"weeks": 1, "tasks": 10}
            }
        }

    def _ensure_progress_file(self):
        """Create progress file if it doesn't exist."""
        if not os.path.exists(self.progress_file):
            os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
            initial_data = {
                "project_start": self.project_start_date,
                "last_updated": datetime.now().isoformat(),
                "overall_progress": 0.0,
                "current_phase": "1_foundation_setup",
                "entity_alignment": {},
                "milestones": {},
                "validation_results": {}
            }
            with open(self.progress_file, 'w') as f:
                json.dump(initial_data, f, indent=2)

    def get_dashboard_data(self) -> Dict:
        """
        Generate complete dashboard data for web UI display.
        
        Returns:
            Dict: Comprehensive progress data for web dashboard
        """
        progress_data = self._load_progress_data()
        
        return {
            "project_info": {
                "name": "ProEthica Intermediate Ontology BFO Alignment",
                "start_date": self.project_start_date,
                "target_completion": self.target_completion_date,
                "current_phase": progress_data.get("current_phase", "1_foundation_setup"),
                "overall_progress": self.calculate_overall_progress(),
                "days_elapsed": self._calculate_days_elapsed(),
                "estimated_days_remaining": self._estimate_remaining_days()
            },
            "bfo_alignment": self.get_bfo_alignment_status(),
            "milestones": self.get_milestone_status(),
            "validation_status": self.get_validation_summary(),
            "tasks": self.get_task_progress(),
            "phase_breakdown": self.get_phase_breakdown(),
            "recent_activity": self.get_recent_activity()
        }

    def get_bfo_alignment_status(self) -> Dict:
        """Get BFO alignment status for all 9 core entities."""
        progress_data = self._load_progress_data()
        entity_statuses = []
        
        # BFO alignment targets from feedback
        bfo_targets = {
            "Role": "bfo:Role",
            "Principle": "iao:InformationContentEntity", 
            "Obligation": "iao:InformationContentEntity",  # Deontic ICE pattern
            "State": "bfo:Quality",
            "Resource": ["bfo:MaterialEntity", "iao:InformationContentEntity"],  # Bifurcated
            "Action": "bfo:Process",
            "Event": "bfo:Process", 
            "Capability": "bfo:Disposition",
            "Constraint": ["bfo:Quality", "iao:InformationContentEntity"]  # Context-dependent
        }
        
        aligned_count = 0
        for entity in self.core_entities:
            entity_data = progress_data.get("entity_alignment", {}).get(entity, {})
            status = entity_data.get("alignment_status", "unaligned")
            if status == "complete":
                aligned_count += 1
                
            entity_statuses.append(EntityAlignmentStatus(
                entity_name=entity,
                current_parent=entity_data.get("current_parent"),
                target_bfo_parent=bfo_targets.get(entity, "unknown"),
                alignment_status=status,
                validation_errors=entity_data.get("validation_errors", []),
                migration_date=entity_data.get("migration_date")
            ))
        
        return {
            "total_entities": len(self.core_entities),
            "aligned_entities": aligned_count,
            "alignment_percentage": (aligned_count / len(self.core_entities)) * 100,
            "entity_details": [status.__dict__ for status in entity_statuses],
            "next_entity_to_migrate": self._get_next_entity_to_migrate(entity_statuses)
        }

    def get_milestone_status(self) -> List[Dict]:
        """Get status of all project milestones."""
        milestones = [
            {
                "name": "Foundation Setup Complete",
                "phase": "1_foundation_setup", 
                "target_date": "2025-09-09",
                "dependencies": ["BFO Loaded", "RO Loaded", "IAO Loaded", "Validation Pipeline"],
                "completion_criteria": "All foundation ontologies imported and validation rules active"
            },
            {
                "name": "Core Entity Migration Complete", 
                "phase": "2_entity_migration",
                "target_date": "2025-09-23",
                "dependencies": ["9/9 entities BFO-aligned", "Disjointness added", "Quality checks passed"],
                "completion_criteria": "All 9 core entities properly aligned with BFO categories"
            },
            {
                "name": "Property Alignment Complete",
                "phase": "3_relations_properties", 
                "target_date": "2025-09-30",
                "dependencies": ["RO mappings", "Domain/range specs", "EL-safe chains"],
                "completion_criteria": "All custom properties aligned with RO/BFO relations"
            },
            {
                "name": "Quality Assurance Complete",
                "phase": "4_quality_assurance",
                "target_date": "2025-10-07", 
                "dependencies": ["Annotations cleaned", "SHACL shapes", "Competency queries"],
                "completion_criteria": "All quality issues resolved, full validation suite passing"
            },
            {
                "name": "OntServer Integration Complete",
                "phase": "5_ontserver_integration",
                "target_date": "2025-10-14",
                "dependencies": ["Module config", "API endpoints", "Performance validated"],
                "completion_criteria": "Successfully deployed and integrated with OntServer"
            },
            {
                "name": "Documentation & Paper Ready",
                "phase": "6_documentation_validation",
                "target_date": "2025-10-21",
                "dependencies": ["Tech spec complete", "Paper draft", "Examples created"],
                "completion_criteria": "Complete documentation suite and academic paper ready"
            }
        ]
        
        # Add completion status to each milestone
        progress_data = self._load_progress_data()
        for milestone in milestones:
            milestone_status = progress_data.get("milestones", {}).get(milestone["name"], {})
            milestone["status"] = milestone_status.get("status", "not_started")
            milestone["completion_percentage"] = milestone_status.get("completion_percentage", 0)
            milestone["actual_completion_date"] = milestone_status.get("completion_date")
            
        return milestones

    def get_validation_summary(self) -> Dict:
        """Get current validation status across all validation types."""
        return {
            "bfo_compliance": self._check_bfo_compliance(),
            "owl_profile": self._check_owl_profile_compliance(),
            "annotation_quality": self._check_annotation_quality(),
            "reasoning_consistency": self._check_reasoning_consistency(),
            "shacl_validation": self._check_shacl_validation()
        }

    def get_task_progress(self) -> Dict:
        """Get detailed task completion progress by phase."""
        phases_config = self.config.get("phases", {})
        progress_data = self._load_progress_data()
        
        task_progress = {}
        total_completed = 0
        total_tasks = 0
        
        # Define default phase structure if config is missing
        if not phases_config:
            phases_config = {
                "1_foundation_setup": {"tasks": 16},
                "2_entity_migration": {"tasks": 36}, 
                "3_relations_properties": {"tasks": 12},
                "4_quality_assurance": {"tasks": 15},
                "5_ontserver_integration": {"tasks": 8},
                "6_documentation_validation": {"tasks": 10}
            }
        
        for phase_name, phase_config in phases_config.items():
            phase_tasks = phase_config.get("tasks", 0)
            phase_completed = progress_data.get("phase_progress", {}).get(phase_name, {}).get("completed_tasks", 0)
            
            task_progress[phase_name] = {
                "total_tasks": phase_tasks,
                "completed_tasks": phase_completed,
                "completion_percentage": (phase_completed / phase_tasks) * 100 if phase_tasks > 0 else 0,
                "status": self._determine_phase_status(phase_name, phase_completed, phase_tasks)
            }
            
            total_completed += phase_completed
            total_tasks += phase_tasks
        
        task_progress["overall"] = {
            "total_tasks": total_tasks,
            "completed_tasks": total_completed,
            "completion_percentage": (total_completed / total_tasks) * 100 if total_tasks > 0 else 0
        }
        
        return task_progress

    def update_entity_alignment(self, entity_name: str, status: str, parent: str = None, errors: List[str] = None):
        """Update alignment status for a specific entity."""
        progress_data = self._load_progress_data()
        
        if "entity_alignment" not in progress_data:
            progress_data["entity_alignment"] = {}
            
        progress_data["entity_alignment"][entity_name] = {
            "alignment_status": status,
            "current_parent": parent,
            "validation_errors": errors or [],
            "last_updated": datetime.now().isoformat()
        }
        
        if status == "complete":
            progress_data["entity_alignment"][entity_name]["migration_date"] = datetime.now().isoformat()
        
        self._save_progress_data(progress_data)

    def update_milestone_completion(self, milestone_name: str, completion_percentage: float, status: str = None):
        """Update milestone completion status."""
        progress_data = self._load_progress_data()
        
        if "milestones" not in progress_data:
            progress_data["milestones"] = {}
            
        progress_data["milestones"][milestone_name] = {
            "completion_percentage": completion_percentage,
            "status": status or ("completed" if completion_percentage >= 100 else "in_progress"),
            "last_updated": datetime.now().isoformat()
        }
        
        if completion_percentage >= 100:
            progress_data["milestones"][milestone_name]["completion_date"] = datetime.now().isoformat()
        
        self._save_progress_data(progress_data)

    def calculate_overall_progress(self) -> float:
        """Calculate overall project progress percentage."""
        progress_data = self._load_progress_data()
        
        # Weight phases by their task count
        phases_config = self.config.get("phases", {})
        total_weighted_progress = 0
        total_weight = 0
        
        for phase_name, phase_config in phases_config.items():
            phase_weight = phase_config.get("tasks", 0)
            phase_completed = progress_data.get("phase_progress", {}).get(phase_name, {}).get("completed_tasks", 0)
            phase_total = phase_config.get("tasks", 0)
            
            if phase_total > 0:
                phase_progress = (phase_completed / phase_total) * 100
                total_weighted_progress += phase_progress * phase_weight
                total_weight += phase_weight
        
        return total_weighted_progress / total_weight if total_weight > 0 else 0

    def get_phase_breakdown(self) -> Dict:
        """Get detailed breakdown of progress by phase."""
        progress_data = self._load_progress_data()
        phases_config = self.config.get("phases", {})
        
        breakdown = {}
        for phase_name, phase_config in phases_config.items():
            phase_data = progress_data.get("phase_progress", {}).get(phase_name, {})
            breakdown[phase_name] = {
                "name": phase_name.replace("_", " ").title(),
                "weeks_allocated": phase_config.get("weeks", 1),
                "total_tasks": phase_config.get("tasks", 0),
                "completed_tasks": phase_data.get("completed_tasks", 0),
                "status": phase_data.get("status", "not_started"),
                "start_date": phase_data.get("start_date"),
                "completion_date": phase_data.get("completion_date")
            }
        return breakdown

    def get_recent_activity(self) -> List[Dict]:
        """Get recent activity log entries."""
        progress_data = self._load_progress_data()
        activities = progress_data.get("activity_log", [])
        
        # Return last 10 activities, sorted by timestamp
        return sorted(activities, key=lambda x: x.get("timestamp", ""), reverse=True)[:10]

    def add_activity(self, action: str, details: str, category: str = "general"):
        """Add an activity to the log."""
        progress_data = self._load_progress_data()
        
        if "activity_log" not in progress_data:
            progress_data["activity_log"] = []
        
        activity = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details,
            "category": category
        }
        
        progress_data["activity_log"].append(activity)
        progress_data["last_updated"] = datetime.now().isoformat()
        
        self._save_progress_data(progress_data)

    def _get_next_entity_to_migrate(self, entity_statuses: List[EntityAlignmentStatus]) -> Optional[str]:
        """Determine the next entity that needs BFO alignment."""
        for status in entity_statuses:
            if status.alignment_status == "unaligned":
                return status.entity_name
        return None

    def _determine_phase_status(self, phase_name: str, completed: int, total: int) -> str:
        """Determine phase status based on completion."""
        if completed == 0:
            return "not_started"
        elif completed == total:
            return "completed"
        else:
            return "in_progress"

    def _calculate_days_elapsed(self) -> int:
        """Calculate days since project start."""
        start = datetime.fromisoformat(self.project_start_date)
        now = datetime.now()
        return (now - start).days

    def _estimate_remaining_days(self) -> int:
        """Estimate remaining days based on target completion."""
        target = datetime.fromisoformat(self.target_completion_date)
        now = datetime.now()
        return max(0, (target - now).days)

    def _check_bfo_compliance(self) -> Dict:
        """Check BFO compliance status."""
        # This would integrate with OntServe validation
        return {
            "status": "pending_analysis",
            "compliant_entities": 0,
            "total_entities": 9,
            "last_check": None
        }

    def _check_owl_profile_compliance(self) -> Dict:
        """Check OWL 2 EL profile compliance."""
        return {
            "profile": "OWL_2_EL",
            "status": "pending_analysis", 
            "violations": [],
            "last_check": None
        }

    def _check_annotation_quality(self) -> Dict:
        """Check annotation completeness and quality."""
        return {
            "entities_with_definitions": 0,
            "entities_with_labels": 0,
            "missing_annotations": [],
            "status": "pending_analysis"
        }

    def _check_reasoning_consistency(self) -> Dict:
        """Check reasoning consistency results."""
        return {
            "status": "pending_analysis",
            "reasoner": "elk",
            "consistent": None,
            "last_check": None
        }

    def _check_shacl_validation(self) -> Dict:
        """Check SHACL shape validation results."""
        return {
            "shapes_loaded": False,
            "validation_passed": None,
            "violations": [],
            "last_check": None
        }

    def _load_progress_data(self) -> Dict:
        """Load progress data from JSON file."""
        try:
            with open(self.progress_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self._ensure_progress_file()
            with open(self.progress_file, 'r') as f:
                return json.load(f)

    def _save_progress_data(self, data: Dict):
        """Save progress data to JSON file."""
        data["last_updated"] = datetime.now().isoformat()
        with open(self.progress_file, 'w') as f:
            json.dump(data, f, indent=2)

# Flask/API Integration for OntServe Web UI

def create_progress_dashboard_routes(app):
    """Create Flask routes for the progress dashboard."""
    dashboard = BFOAlignmentProgressDashboard()
    
    @app.route('/editor/ontology/proethica-intermediate/progress')
    def progress_dashboard():
        """Main progress dashboard view."""
        data = dashboard.get_dashboard_data()
        return render_template('progress_dashboard.html', **data)
    
    @app.route('/editor/api/progress/dashboard')
    def api_dashboard_data():
        """API endpoint for dashboard data."""
        return jsonify(dashboard.get_dashboard_data())
    
    @app.route('/editor/api/progress/entity/<entity_name>/update', methods=['POST'])
    def update_entity_status(entity_name):
        """Update entity alignment status."""
        data = request.get_json()
        dashboard.update_entity_alignment(
            entity_name=entity_name,
            status=data['status'],
            parent=data.get('parent'),
            errors=data.get('errors', [])
        )
        return jsonify({"success": True})
    
    @app.route('/editor/api/progress/milestone/<milestone_name>/update', methods=['POST'])
    def update_milestone_status(milestone_name):
        """Update milestone completion status."""
        data = request.get_json()
        dashboard.update_milestone_completion(
            milestone_name=milestone_name,
            completion_percentage=data['completion_percentage'],
            status=data.get('status')
        )
        return jsonify({"success": True})
    
    @app.route('/editor/api/progress/activity', methods=['POST'])
    def add_activity():
        """Add new activity to the log."""
        data = request.get_json()
        dashboard.add_activity(
            action=data['action'],
            details=data['details'],
            category=data.get('category', 'general')
        )
        return jsonify({"success": True})

if __name__ == "__main__":
    # Command line testing
    dashboard = BFOAlignmentProgressDashboard()
    print("Dashboard Data:")
    print(json.dumps(dashboard.get_dashboard_data(), indent=2))
