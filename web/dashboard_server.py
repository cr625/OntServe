"""
Simple Flask server for ProEthica Intermediate Ontology Progress Dashboard

Runs a standalone web server to display the BFO alignment progress in real-time.
"""

from flask import Flask, render_template, jsonify, request
import os
import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

try:
    from progress_dashboard import BFOAlignmentProgressDashboard
except ImportError:
    print("Error: Could not import progress_dashboard module")
    sys.exit(1)

# Initialize Flask app
app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')

# Initialize dashboard
dashboard = BFOAlignmentProgressDashboard()

@app.route('/')
def index():
    """Redirect to progress dashboard."""
    from flask import redirect
    return redirect('/progress')

@app.route('/progress')
def progress_dashboard():
    """Main progress dashboard view."""
    try:
        data = dashboard.get_dashboard_data()
        return render_template('progress_dashboard.html', **data)
    except Exception as e:
        return f"Error loading dashboard: {str(e)}", 500

@app.route('/api/progress/dashboard')
def api_dashboard_data():
    """API endpoint for dashboard data."""
    try:
        data = dashboard.get_dashboard_data()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/progress/entity/<entity_name>/update', methods=['POST'])
def update_entity_status(entity_name):
    """Update entity alignment status."""
    try:
        data = request.get_json()
        dashboard.update_entity_alignment(
            entity_name=entity_name,
            status=data['status'],
            parent=data.get('parent'),
            errors=data.get('errors', [])
        )
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/progress/milestone/<milestone_name>/update', methods=['POST'])
def update_milestone_status(milestone_name):
    """Update milestone completion status."""
    try:
        data = request.get_json()
        dashboard.update_milestone_completion(
            milestone_name=milestone_name,
            completion_percentage=data['completion_percentage'],
            status=data.get('status')
        )
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/progress/activity', methods=['POST'])
def add_activity():
    """Add new activity to the log."""
    try:
        data = request.get_json()
        dashboard.add_activity(
            action=data['action'],
            details=data['details'],
            category=data.get('category', 'general')
        )
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """Force refresh of dashboard data."""
    try:
        data = dashboard.get_dashboard_data()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "dashboard_available": True,
        "timestamp": dashboard.get_dashboard_data()["project_info"]["start_date"]
    })

if __name__ == '__main__':
    print("=" * 60)
    print("ProEthica Intermediate Ontology Progress Dashboard")
    print("=" * 60)
    print("Starting dashboard server...")
    print("Dashboard will be available at: http://localhost:5002/progress")
    print("API endpoint: http://localhost:5002/api/progress/dashboard")
    print("=" * 60)
    
    # Create necessary directories
    Path("OntServe/web/static").mkdir(parents=True, exist_ok=True)
    
    # Run Flask development server
    app.run(
        host='0.0.0.0',
        port=5002,
        debug=True,
        threaded=True
    )
