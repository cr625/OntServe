"""
OntServe Web Application

Flask application for managing and serving ontologies with semantic search capabilities.
"""

import os
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_cors import CORS

from web.models import db, init_db, User
from core.ontology_manager import OntologyManager
from core.ontology_merger import OntologyMergerService
from editor.routes import create_editor_blueprint
from storage.file_storage import FileStorage
from services.wolfram_service import WolframService


def create_app(config_name=None):
    """
    Application factory for creating Flask app.

    Args:
        config_name: Configuration to use (development, production, testing)

    Returns:
        Flask application instance
    """
    # Load environment variables from .env files before reading Config class
    from config.config_loader import load_ontserve_config
    config_summary = load_ontserve_config()
    logging.getLogger(__name__).info(
        "Loaded configuration from: %s", ", ".join(config_summary["loaded_files"]),
    )

    app = Flask(__name__)

    # Configure CORS to allow requests from ProEthica
    CORS(app, resources={
        r"/api/*": {
            "origins": [
                "https://proethica.org",
                "http://localhost:5000",
                "http://127.0.0.1:5000"
            ]
        }
    })

    # Load configuration — import deferred so .env is loaded before Config class body runs
    from web.config import config
    config_name = config_name or os.environ.get('FLASK_CONFIG', 'development')
    config_class = config[config_name]
    app.config.from_object(config_class)
    if hasattr(config_class, 'init_app'):
        config_class.init_app(app)

    # Initialize database
    init_db(app)
    migrate = Migrate(app, db)

    # Auto-sync ontology entities from TTL files on startup
    with app.app_context():
        try:
            from services.ontology_sync_service import sync_ontologies_on_startup
            from pathlib import Path
            ontologies_dir = Path(__file__).parent.parent / 'ontologies'
            sync_result = sync_ontologies_on_startup(db.session, ontologies_dir)
            if sync_result.get('updated', 0) > 0:
                logging.info(f"Ontology sync: {sync_result['updated']} ontologies updated")
            else:
                logging.debug(f"Ontology sync: all ontologies up to date")
        except Exception as e:
            logging.warning(f"Ontology sync failed (non-fatal): {e}")

    # Initialize OntologyManager
    ontology_config = {
        'storage_type': 'file',
        'storage_config': {
            'storage_dir': app.config['ONTSERVE_STORAGE_DIR']
        },
        'cache_dir': app.config['ONTSERVE_CACHE_DIR'],
        'log_level': 'INFO'
    }
    app.ontology_manager = OntologyManager(ontology_config)

    # Initialize OntologyMergerService
    app.ontology_merger = OntologyMergerService(logger=logging.getLogger('ontology_merger'))

    # Initialize Wolfram AgentOne service
    app.wolfram_service = WolframService(
        api_key=os.environ.get("WOLFRAM_API_KEY"),
        timeout=int(os.environ.get("WOLFRAM_TIMEOUT", "120")),
    )

    # Setup logging
    if not app.debug:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login"""
        return db.session.get(User, int(user_id))

    # Register blueprints
    from web.auth_routes import auth_bp
    from web.main_routes import main_bp
    from web.ontology_routes import ontology_bp
    from web.api_routes import api_bp
    from web.draft_routes import draft_bp
    from web.uri_resolution import uri_bp
    from web.wolfram_routes import wolfram_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(ontology_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(draft_bp)
    app.register_blueprint(uri_bp)
    app.register_blueprint(wolfram_bp)

    # Register enhanced editor blueprint
    storage_backend = FileStorage({'storage_dir': app.config['ONTSERVE_STORAGE_DIR']})
    editor_config = {
        'require_auth': False,
        'admin_only': False,
        'storage': {'storage_dir': app.config['ONTSERVE_STORAGE_DIR']}
    }
    editor_blueprint = create_editor_blueprint(storage_backend, editor_config)
    app.register_blueprint(editor_blueprint)

    # Add custom template filters for safe URI handling
    @app.template_filter('extract_name')
    def extract_name_filter(uri):
        """Safely extract a name from a URI, handling lists and None values."""
        if not uri:
            return 'Unknown'

        # Handle case where uri might be a list
        if isinstance(uri, list):
            if not uri:
                return 'Unknown'
            uri = uri[0] if uri[0] else 'Unknown'

        # Ensure uri is a string
        uri = str(uri)

        # Extract the last part after # or /
        if '#' in uri:
            return uri.split('#')[-1]
        elif '/' in uri:
            return uri.split('/')[-1]
        else:
            return uri

    @app.template_filter('from_json')
    def from_json_filter(json_str):
        """Parse JSON string into Python object, returning empty dict on error."""
        if not json_str:
            return {}
        try:
            if isinstance(json_str, str):
                return json.loads(json_str)
            return json_str
        except (json.JSONDecodeError, TypeError):
            return {}

    @app.template_filter('render_entity_props')
    def render_entity_props_filter(properties, parent_uri=None):
        """Render entity properties using display configuration."""
        from web.entity_display import render_entity_properties
        if not properties:
            return {'badges': [], 'fields': [], 'extra': []}
        # Handle both dict and JSON string
        if isinstance(properties, str):
            try:
                properties = json.loads(properties)
            except (json.JSONDecodeError, TypeError):
                return {'badges': [], 'fields': [], 'extra': []}
        return render_entity_properties(properties, parent_uri)

    # Make config available in templates
    @app.context_processor
    def inject_config():
        """Make app config available in templates."""
        return {'config': app.config}

    # Add render_props as a Jinja global (available in macros too)
    from web.entity_display import render_entity_properties
    app.jinja_env.globals['render_props'] = render_entity_properties

    # Add custom filter to format camelCase/snake_case to Title Case
    def format_property_key(key):
        """Convert camelCase or snake_case to Title Case with spaces."""
        # Replace underscores with spaces
        result = key.replace('_', ' ')
        # Insert space before uppercase letters (camelCase)
        result = re.sub(r'([a-z])([A-Z])', r'\1 \2', result)
        # Title case and clean up
        return ' '.join(word.capitalize() for word in result.split())

    app.jinja_env.filters['format_key'] = format_property_key

    def split_pascal_case(text):
        """Split PascalCase/camelCase into readable words.

        'CompetenceBoundaryComplianceObligation' -> 'Competence Boundary Compliance Obligation'
        'Post-FailureInvestigationState' -> 'Post-Failure Investigation State'
        'PublicSafetyatRisk' -> 'Public Safety at Risk'
        """
        if not text:
            return text
        # Insert space before uppercase letters preceded by lowercase
        result = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        # Insert space between consecutive uppercase + lowercase (e.g., 'HTMLParser' -> 'HTML Parser')
        result = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', result)
        # After PascalCase splitting, some words end with lowercase joiners
        # glued to the next word, e.g., 'Safetyat Risk' or 'Standardsvs Emerging'.
        # Split these: look for a known joiner suffix on a word.
        # Sorted longest-first to avoid 'or' matching before 'for'
        _JOINERS = ['for', 'the', 'and', 'at', 'vs', 'of', 'to', 'in', 'or', 'by']
        words = result.split()
        fixed = []
        for w in words:
            split_found = False
            for j in _JOINERS:
                if len(w) > len(j) + 1 and w.endswith(j) and w[0].isupper():
                    # e.g., 'Safetyat' -> 'Safety' + 'at'
                    fixed.append(w[:-len(j)])
                    fixed.append(j)
                    split_found = True
                    break
            if not split_found:
                fixed.append(w)
        return ' '.join(fixed)

    app.jinja_env.filters['split_pascal'] = split_pascal_case

    # Initialize CLI commands
    from web.cli import init_cli
    init_cli(app)

    return app


if __name__ == '__main__':
    app = create_app()

    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()

    # Run the application
    host = app.config.get('HOST', '0.0.0.0')
    port = int(os.environ.get('ONTSERVE_PORT', app.config.get('PORT', 5003)))
    debug = app.config.get('DEBUG', False)

    print(f"Starting OntServe Flask Web Server on {host}:{port} (debug={debug})")

    app.run(
        host=host,
        port=port,
        debug=debug
    )
else:
    # Create app instance for WSGI servers (like gunicorn) and VSCode launch tasks
    app = create_app()
