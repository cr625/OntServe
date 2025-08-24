"""
OntServe Web Application

Flask application for managing and serving ontologies with semantic search capabilities.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path to import OntServe modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from flask_migrate import Migrate
from flask_login import LoginManager, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import rdflib

from config import config
from models import db, init_db, Ontology, OntologyEntity, OntologyVersion, User
from core.ontology_manager import OntologyManager
from editor.routes import create_editor_blueprint
from storage.file_storage import FileStorage


def create_app(config_name=None):
    """
    Application factory for creating Flask app.
    
    Args:
        config_name: Configuration to use (development, production, testing)
        
    Returns:
        Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    config_name = config_name or os.environ.get('FLASK_CONFIG', 'development')
    app.config.from_object(config[config_name])
    
    # Initialize database
    init_db(app)
    migrate = Migrate(app, db)
    
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
    
    # Register authentication routes
    register_auth_routes(app)
    
    # Register routes
    register_routes(app)
    
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
    
    # Initialize CLI commands
    from cli import init_cli
    init_cli(app)
    
    return app


def generate_rdf_from_concepts(ontology_name, concepts, base_imports):
    """Generate RDF/Turtle content from extracted concepts."""
    from datetime import datetime
    
    # Base prefixes
    prefixes = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix proethica: <http://proethica.org/ontology/> .

"""
    
    # Ontology declaration
    base_uri = f'http://proethica.org/ontology/{ontology_name}'
    ontology_declaration = f"""<{base_uri}> 
    a owl:Ontology ;
    rdfs:comment "Extracted concepts from ProEthica guideline analysis" ;
    owl:versionInfo "1.0-draft" ;
    proethica:extractedAt "{datetime.utcnow().isoformat()}"^^xsd:dateTime"""
    
    # Add imports
    for import_ont in base_imports:
        ontology_declaration += f' ;\n    owl:imports <http://proethica.org/ontology/{import_ont}>'
    
    ontology_declaration += " .\n\n"
    
    # Generate concept triples
    concept_triples = ""
    for concept in concepts:
        concept_uri = f"<{base_uri}#{concept.get('label', '').replace(' ', '')}>"
        concept_type = concept.get('type', 'class').lower()
        
        # Map ProEthica types to intermediate ontology classes
        type_mapping = {
            'role': 'http://proethica.org/ontology/intermediate#Role',
            'principle': 'http://proethica.org/ontology/intermediate#Principle', 
            'obligation': 'http://proethica.org/ontology/intermediate#Obligation',
            'state': 'http://proethica.org/ontology/intermediate#State',
            'resource': 'http://proethica.org/ontology/intermediate#Resource',
            'action': 'http://proethica.org/ontology/intermediate#Action',
            'event': 'http://proethica.org/ontology/intermediate#Event',
            'capability': 'http://proethica.org/ontology/intermediate#Capability',
            'constraint': 'http://proethica.org/ontology/intermediate#Constraint'
        }
        
        parent_class = type_mapping.get(concept_type, 'owl:Thing')
        
        concept_triples += f"""{concept_uri} 
    a owl:Class ;
    rdfs:subClassOf <{parent_class}> ;
    rdfs:label "{concept.get('label', '')}" """
        
        if concept.get('description'):
            concept_triples += f';\n    rdfs:comment "{concept.get('description')}"'
        
        if concept.get('confidence'):
            concept_triples += f';\n    proethica:extractionConfidence "{concept.get('confidence')}"^^xsd:float'
        
        concept_triples += " .\n\n"
    
    return prefixes + ontology_declaration + concept_triples


def register_auth_routes(app):
    """Register authentication routes"""
    from flask import Blueprint
    
    auth_bp = Blueprint('auth', __name__)
    
    @auth_bp.route('/login', methods=['GET', 'POST'])
    def login():
        """User login"""
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            remember = bool(request.form.get('remember'))
            
            if not username or not password:
                flash('Please enter both username and password', 'error')
                return render_template('auth/login.html')
            
            user = User.query.filter_by(username=username).first()
            
            if user and user.check_password(password) and user.is_active:
                from flask_login import login_user
                login_user(user, remember=remember)
                
                # Update last login with timezone-aware datetime
                user.last_login = datetime.now(timezone.utc)
                db.session.commit()
                
                # Log successful login
                app.logger.info(f"User {username} logged in successfully")
                
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect(url_for('index'))
            else:
                app.logger.warning(f"Failed login attempt for username: {username}")
                flash('Invalid username or password', 'error')
        
        return render_template('auth/login.html')
    
    @auth_bp.route('/logout')
    @login_required
    def logout():
        """User logout"""
        username = current_user.username if current_user.is_authenticated else 'Unknown'
        from flask_login import logout_user
        logout_user()
        app.logger.info(f"User {username} logged out")
        flash('You have been logged out', 'info')
        return redirect(url_for('auth.login'))
    
    @auth_bp.route('/profile')
    @login_required  
    def profile():
        """User profile page"""
        return render_template('auth/profile.html', user=current_user)
    
    # Register blueprint
    app.register_blueprint(auth_bp, url_prefix='/auth')


def register_routes(app):
    """Register all application routes."""
    
    @app.route('/')
    def index():
        """Home page showing list of ontologies."""
        page = request.args.get('page', 1, type=int)
        per_page = app.config['ONTOLOGIES_PER_PAGE']
        
        # Get ontologies from database
        pagination = Ontology.query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        ontologies = pagination.items
        
        return render_template('index.html', 
                             ontologies=ontologies,
                             pagination=pagination)
    
    @app.route('/ontology/<ontology_name>')
    def ontology_detail_or_uri_resolution(ontology_name):
        """
        Unified endpoint for ontology detail view and URI resolution.
        
        - Browser requests (Accept: text/html) → Detail page
        - Semantic web clients (Accept: text/turtle, etc.) → Ontology content
        """
        # Check Accept header to determine response type
        accept_header = request.headers.get('Accept', '')
        user_agent = request.headers.get('User-Agent', '')
        
        # Determine if this is a semantic web client request
        semantic_formats = [
            'text/turtle', 'application/rdf+xml', 'application/ld+json',
            'application/n-triples', 'text/n3', 'application/rdf+json'
        ]
        
        is_semantic_request = any(fmt in accept_header for fmt in semantic_formats)
        is_browser = 'Mozilla' in user_agent and 'text/html' in accept_header and not is_semantic_request
        
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        
        # Handle semantic web client requests (content negotiation)
        if is_semantic_request or (not is_browser and not 'text/html' in accept_header):
            app.logger.info(f"URI resolution request for {ontology_name}: Accept={accept_header}")
            
            content = ontology.current_content
            if content is None:
                return jsonify({
                    'error': 'No content available for this ontology',
                    'ontology': ontology_name,
                    'uri': ontology.base_uri
                }), 404
            
            # Determine response format based on Accept header
            if 'application/rdf+xml' in accept_header or 'application/xml' in accept_header:
                # Convert to RDF/XML
                try:
                    from rdflib import Graph
                    g = Graph()
                    g.parse(data=content, format='turtle')
                    rdf_xml_content = g.serialize(format='xml')
                    
                    response = app.response_class(
                        rdf_xml_content,
                        mimetype='application/rdf+xml',
                        headers={
                            'Content-Disposition': f'inline; filename="{ontology_name}.rdf"',
                            'Link': f'<{ontology.base_uri}>; rel="canonical"',
                            'Access-Control-Allow-Origin': '*'
                        }
                    )
                    app.logger.info(f"Served ontology {ontology_name} as RDF/XML")
                    return response
                except Exception as e:
                    app.logger.error(f"Error converting to RDF/XML: {e}")
                    # Fallback to turtle
            
            elif 'application/ld+json' in accept_header or 'application/json' in accept_header:
                # Convert to JSON-LD
                try:
                    from rdflib import Graph
                    g = Graph()
                    g.parse(data=content, format='turtle')
                    jsonld_content = g.serialize(format='json-ld')
                    
                    response = app.response_class(
                        jsonld_content,
                        mimetype='application/ld+json',
                        headers={
                            'Content-Disposition': f'inline; filename="{ontology_name}.jsonld"',
                            'Link': f'<{ontology.base_uri}>; rel="canonical"',
                            'Access-Control-Allow-Origin': '*'
                        }
                    )
                    app.logger.info(f"Served ontology {ontology_name} as JSON-LD")
                    return response
                except Exception as e:
                    app.logger.error(f"Error converting to JSON-LD: {e}")
                    # Fallback to turtle
            
            elif 'application/n-triples' in accept_header:
                # Convert to N-Triples
                try:
                    from rdflib import Graph
                    g = Graph()
                    g.parse(data=content, format='turtle')
                    nt_content = g.serialize(format='nt')
                    
                    response = app.response_class(
                        nt_content,
                        mimetype='application/n-triples',
                        headers={
                            'Content-Disposition': f'inline; filename="{ontology_name}.nt"',
                            'Link': f'<{ontology.base_uri}>; rel="canonical"',
                            'Access-Control-Allow-Origin': '*'
                        }
                    )
                    app.logger.info(f"Served ontology {ontology_name} as N-Triples")
                    return response
                except Exception as e:
                    app.logger.error(f"Error converting to N-Triples: {e}")
                    # Fallback to turtle
            
            # Default to Turtle format for semantic web clients
            response = app.response_class(
                content,
                mimetype='text/turtle',
                headers={
                    'Content-Disposition': f'inline; filename="{ontology_name}.ttl"',
                    'Link': f'<{ontology.base_uri}>; rel="canonical"',
                    'Access-Control-Allow-Origin': '*',
                    'Vary': 'Accept'
                }
            )
            
            app.logger.info(f"Served ontology {ontology_name} as Turtle to semantic web client")
            return response
        
        # Browser request - show detail page
        app.logger.info(f"Browser request for {ontology_name}, showing detail page")
        
        # Get entities grouped by type
        entities = {
            'classes': OntologyEntity.query.filter_by(
                ontology_id=ontology.id, 
                entity_type='class'
            ).all(),
            'properties': OntologyEntity.query.filter_by(
                ontology_id=ontology.id, 
                entity_type='property'
            ).all(),
            'individuals': OntologyEntity.query.filter_by(
                ontology_id=ontology.id, 
                entity_type='individual'
            ).all()
        }
        
        # Count relationship instances
        relationships = {
            'hierarchical': OntologyEntity.query.filter_by(
                ontology_id=ontology.id, 
                entity_type='class'
            ).filter(OntologyEntity.parent_uri.isnot(None)).count(),
            'domain': OntologyEntity.query.filter_by(
                ontology_id=ontology.id, 
                entity_type='property'
            ).filter(OntologyEntity.domain.isnot(None)).count(),
            'range': OntologyEntity.query.filter_by(
                ontology_id=ontology.id, 
                entity_type='property'
            ).filter(OntologyEntity.range.isnot(None)).count()
        }
        relationships['total'] = relationships['hierarchical'] + relationships['domain'] + relationships['range']
        
        # Get versions
        versions = OntologyVersion.query.filter_by(
            ontology_id=ontology.id
        ).order_by(OntologyVersion.created_at.desc()).all()
        
        return render_template('ontology_detail.html',
                             ontology=ontology,
                             entities=entities,
                             relationships=relationships,
                             versions=versions)
    
    @app.route('/ontology/<ontology_name>/content')
    def ontology_content(ontology_name):
        """Return raw TTL content of an ontology."""
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        content = ontology.current_content
        if content is None:
            return "No content available for this ontology", 404
        return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    
    
    @app.route('/ontology/<ontology_name>.<format_ext>')
    def ontology_format_specific(ontology_name, format_ext):
        """
        Format-specific ontology endpoints for explicit format requests.
        
        Examples:
        - /ontology/w3c-prov-o.ttl -> Turtle
        - /ontology/w3c-prov-o.rdf -> RDF/XML
        - /ontology/w3c-prov-o.jsonld -> JSON-LD
        """
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        content = ontology.current_content
        
        if content is None:
            return jsonify({
                'error': 'No content available for this ontology',
                'ontology': ontology_name
            }), 404
        
        # Format mapping
        format_mapping = {
            'ttl': ('turtle', 'text/turtle'),
            'rdf': ('xml', 'application/rdf+xml'),
            'xml': ('xml', 'application/rdf+xml'),
            'jsonld': ('json-ld', 'application/ld+json'),
            'json': ('json-ld', 'application/ld+json'),
            'nt': ('nt', 'application/n-triples'),
            'n3': ('n3', 'text/n3')
        }
        
        if format_ext not in format_mapping:
            return jsonify({'error': f'Unsupported format: {format_ext}'}), 400
        
        rdf_format, mime_type = format_mapping[format_ext]
        
        try:
            # Convert content to requested format
            from rdflib import Graph
            g = Graph()
            g.parse(data=content, format='turtle')
            
            if rdf_format == 'turtle':
                output_content = content  # Already in turtle
            else:
                output_content = g.serialize(format=rdf_format)
            
            response = app.response_class(
                output_content,
                mimetype=mime_type,
                headers={
                    'Content-Disposition': f'attachment; filename="{ontology_name}.{format_ext}"',
                    'Link': f'<{ontology.base_uri}>; rel="canonical"',
                    'Access-Control-Allow-Origin': '*'
                }
            )
            
            app.logger.info(f"Served ontology {ontology_name} as {format_ext} format")
            return response
            
        except Exception as e:
            app.logger.error(f"Error converting ontology to {format_ext}: {e}")
            return jsonify({
                'error': f'Error converting to {format_ext} format',
                'details': str(e)
            }), 500
    
    @app.route('/ontology/<ontology_name>', methods=['DELETE'])
    @login_required
    def delete_ontology(ontology_name):
        """Delete an ontology and all its related data."""
        # Check if user has admin/delete permissions
        if not current_user.can_perform_action('delete'):
            return jsonify({
                'success': False,
                'error': 'You do not have permission to delete ontologies'
            }), 403
        
        try:
            ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
            
            app.logger.info(f"Admin {current_user.username} is deleting ontology: {ontology_name}")
            
            # Count what we're deleting for logging
            entity_count = OntologyEntity.query.filter_by(ontology_id=ontology.id).count()
            version_count = OntologyVersion.query.filter_by(ontology_id=ontology.id).count()
            
            # Delete in proper order to avoid foreign key constraints
            
            # 1. Delete all entities
            OntologyEntity.query.filter_by(ontology_id=ontology.id).delete()
            
            # 2. Delete all versions
            OntologyVersion.query.filter_by(ontology_id=ontology.id).delete()
            
            # 3. Clean up file storage if using file backend
            try:
                app.ontology_manager.delete_ontology(ontology_name)
            except Exception as storage_error:
                app.logger.warning(f"File storage cleanup failed for {ontology_name}: {storage_error}")
                # Don't fail the deletion if file cleanup fails
            
            # 4. Delete the ontology itself
            ontology_id = ontology.id
            db.session.delete(ontology)
            
            # Commit all changes
            db.session.commit()
            
            app.logger.info(f"Successfully deleted ontology {ontology_name} (ID: {ontology_id}) with {entity_count} entities and {version_count} versions")
            
            return jsonify({
                'success': True,
                'message': f'Ontology "{ontology_name}" deleted successfully',
                'deleted_data': {
                    'ontology_name': ontology_name,
                    'entities_deleted': entity_count,
                    'versions_deleted': version_count
                }
            })
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error deleting ontology {ontology_name}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.route('/import', methods=['GET', 'POST'])
    @login_required
    def import_ontology():
        """Import a new ontology from URL or file upload."""
        # Check if user can import ontologies
        if not current_user.can_perform_action('import'):
            flash('You do not have permission to import ontologies', 'error')
            return redirect(url_for('index'))
        if request.method == 'POST':
            source_type = request.form.get('source_type', 'url')
            name = request.form.get('name')
            description = request.form.get('description')
            format_hint = request.form.get('format', '')
            use_reasoning = request.form.get('use_reasoning') == 'on'
            reasoner_type = request.form.get('reasoner_type', 'pellet')
            
            source = None
            content = None
            filename = None
            
            try:
                # Handle different source types
                if source_type == 'url':
                    source = request.form.get('source_url')
                    if not source:
                        flash('Please provide a URL', 'error')
                        return render_template('import.html')
                    
                    # Fetch content from URL
                    import requests
                    app.logger.info(f"Fetching ontology from URL: {source}")
                    
                    headers = {
                        'Accept': 'text/turtle, application/rdf+xml, application/n-triples, application/ld+json, text/n3, */*',
                        'User-Agent': 'OntServe/1.0 (ontology importer)'
                    }
                    
                    response = requests.get(source, headers=headers, timeout=30)
                    response.raise_for_status()
                    content = response.text
                    filename = source.split('/')[-1] or 'ontology'
                    
                elif source_type == 'upload':
                    uploaded_file = request.files.get('ontology_file')
                    if not uploaded_file or uploaded_file.filename == '':
                        flash('Please select a file to upload', 'error')
                        return render_template('import.html')
                    
                    # Read file content
                    content = uploaded_file.read().decode('utf-8')
                    filename = uploaded_file.filename
                    source = f"uploaded://{filename}"
                    app.logger.info(f"Processing uploaded file: {filename}")
                else:
                    flash('Invalid source type', 'error')
                    return render_template('import.html')
                
                # Auto-detect format if not specified
                if not format_hint:
                    if filename:
                        if filename.endswith('.ttl'):
                            format_hint = 'turtle'
                        elif filename.endswith('.rdf') or filename.endswith('.xml') or filename.endswith('.owl'):
                            format_hint = 'xml'
                        elif filename.endswith('.n3'):
                            format_hint = 'n3'
                        elif filename.endswith('.jsonld') or filename.endswith('.json'):
                            format_hint = 'json-ld'
                        elif filename.endswith('.nt'):
                            format_hint = 'nt'
                    
                    # Content-based detection if still no format
                    if not format_hint:
                        if '@prefix' in content or '@base' in content:
                            format_hint = 'turtle'
                        elif '<?xml' in content or '<rdf:RDF' in content or 'xmlns:rdf' in content:
                            format_hint = 'xml'
                        elif content.strip().startswith('{'):
                            format_hint = 'json-ld'
                        else:
                            format_hint = 'turtle'  # Default fallback
                
                app.logger.info(f"Detected format: {format_hint}")
                
                # Check if content needs vocabulary conversion
                from utils.vocabulary_converter import VocabularyConverter, is_vocabulary_convertible
                
                needs_conversion = False
                original_content = content
                
                try:
                    if is_vocabulary_convertible(content, format_hint):
                        app.logger.info("Detected non-OWL vocabulary that needs conversion")
                        
                        converter = VocabularyConverter()
                        ontology_uri = f"http://example.org/{name.lower().replace(' ', '-')}" if name else None
                        
                        converted_content = converter.convert_vocabulary_content(
                            content,
                            input_format=format_hint,
                            output_format='turtle',
                            ontology_uri=ontology_uri
                        )
                        
                        content = converted_content
                        format_hint = 'turtle'  # Converted output is always turtle
                        needs_conversion = True
                        
                        app.logger.info(f"Successfully converted vocabulary to OWL (original: {len(original_content)} chars, converted: {len(content)} chars)")
                        
                except Exception as conversion_error:
                    app.logger.warning(f"Vocabulary conversion failed: {conversion_error}. Proceeding with original content.")
                    content = original_content
                
                # Use OwlreadyImporter for enhanced processing if reasoning is enabled
                if use_reasoning:
                    from importers.owlready_importer import OwlreadyImporter
                    
                    importer = OwlreadyImporter()
                    importer.use_reasoner = True
                    importer.reasoner_type = reasoner_type
                    importer.validate_consistency = True
                    importer.include_inferred = True
                    
                    app.logger.info(f"Using OwlreadyImporter with {reasoner_type} reasoning")
                    
                    # Import with reasoning
                    if source_type == 'url':
                        result = importer.import_from_url(
                            source,
                            name=name,
                            description=description,
                            format=format_hint
                        )
                    else:
                        # For uploads, create temporary file for OwlreadyImporter
                        import tempfile
                        with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{format_hint}', delete=False) as temp_file:
                            temp_file.write(content)
                            temp_path = temp_file.name
                        
                        try:
                            result = importer.import_from_file(
                                temp_path,
                                name=name,
                                description=description,
                                format=format_hint
                            )
                        finally:
                            os.unlink(temp_path)  # Clean up temp file
                    
                else:
                    # Use basic OntologyManager for faster processing
                    app.logger.info("Using basic OntologyManager (no reasoning)")
                    
                    # For content-based imports, we need to create a temporary file
                    if source_type == 'upload':
                        # Create temporary file for uploaded content
                        import tempfile
                        with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{format_hint}', delete=False) as temp_file:
                            temp_file.write(content)
                            temp_path = temp_file.name
                        
                        try:
                            # Import using file path
                            result = app.ontology_manager.import_ontology(
                                source=temp_path,
                                importer_type='prov',  # Use PROV importer as default
                                name=name,
                                description=description,
                                format=format_hint,
                                source_type='file'
                            )
                            # Add content to result since OntologyManager might not include it
                            if result.get('success'):
                                result['content'] = content
                        finally:
                            os.unlink(temp_path)  # Clean up temp file
                    else:
                        # URL-based import
                        result = app.ontology_manager.import_ontology(
                            source=source,
                            importer_type='prov',  # Use PROV importer as default
                            name=name,
                            description=description,
                            format=format_hint,
                            source_type='url'
                        )
                        # Add content to result
                        if result.get('success'):
                            result['content'] = content
                
                if result['success']:
                    # Check if ontology already exists and normalize name for URI safety
                    ontology_name = name or result['metadata'].get('name', 'Unnamed')
                    
                    # Create URI-safe name by replacing spaces and special characters
                    uri_safe_name = ontology_name.lower().replace(' ', '-').replace('&', 'and').replace('/', '-').replace('\\', '-')
                    # Remove any remaining non-alphanumeric characters except hyphens
                    import re
                    uri_safe_name = re.sub(r'[^a-z0-9\-]', '', uri_safe_name)
                    # Remove multiple consecutive hyphens
                    uri_safe_name = re.sub(r'-+', '-', uri_safe_name).strip('-')
                    
                    existing_ontology = Ontology.query.filter_by(name=uri_safe_name).first()
                    
                    if existing_ontology:
                        flash(f"Ontology '{uri_safe_name}' already exists", 'warning')
                        return redirect(url_for('ontology_detail_or_uri_resolution', ontology_name=uri_safe_name))
                    
                    # Generate base URI using configured domain
                    default_base_uri = app.config['ONTOLOGY_NAMESPACE_TEMPLATE'].format(
                        base_uri=app.config['ONTOLOGY_BASE_URI'],
                        name=uri_safe_name
                    )
                    
                    # Create new ontology with URI-safe name
                    ontology = Ontology(
                        name=uri_safe_name,
                        base_uri=result['metadata'].get('namespace', default_base_uri),
                        description=description or result['metadata'].get('description', ''),
                        meta_data={
                            **result['metadata'],
                            'original_name': ontology_name,  # Preserve original name
                            'display_name': ontology_name    # For display purposes
                        }
                    )
                    db.session.add(ontology)
                    db.session.flush()  # Get the ID
                    
                    # Get content - different handling for OwlreadyImporter vs basic manager
                    if use_reasoning and 'enhanced_data' in result:
                        # OwlreadyImporter result
                        content = content or result.get('rdf_content', '')
                        reasoning_metadata = {
                            'reasoning_applied': True,
                            'reasoner_type': reasoner_type,
                            'inferred_relationships': result.get('reasoning_result', {}).get('inferred_count', 0),
                            'consistency_check': result.get('reasoning_result', {}).get('is_consistent'),
                        }
                        change_summary = f"Initial import with {reasoner_type} reasoning"
                    else:
                        # Basic import result
                        content = content or result.get('content', '')
                        reasoning_metadata = {'reasoning_applied': False}
                        change_summary = "Initial import"
                    
                    # Create initial version with content
                    version = OntologyVersion(
                        ontology_id=ontology.id,
                        version_number=1,
                        version_tag="1.0.0",
                        content=content,
                        change_summary=change_summary,
                        created_by="web-import",
                        is_current=True,
                        is_draft=False,
                        workflow_status='published',
                        meta_data={
                            'source': source,
                            'source_type': source_type,
                            'format': result['metadata'].get('format', format_hint),
                            'import_date': datetime.now(timezone.utc).isoformat(),
                            **reasoning_metadata
                        }
                    )
                    db.session.add(version)
                    
                    # Extract and save entities
                    if use_reasoning and 'enhanced_data' in result:
                        # Use enhanced data from OwlreadyImporter
                        enhanced_data = result['enhanced_data']
                        
                        # Import classes
                        for cls in enhanced_data.get('classes', []):
                            entity = OntologyEntity(
                                ontology_id=ontology.id,
                                entity_type='class',
                                uri=cls['uri'],
                                label=cls.get('label', [None])[0] if cls.get('label') else None,
                                comment=cls.get('comment', [None])[0] if cls.get('comment') else None,
                                parent_uri=cls.get('parents', [None])[0] if cls.get('parents') else None
                            )
                            db.session.add(entity)
                        
                        # Import properties
                        for prop in enhanced_data.get('properties', []):
                            entity = OntologyEntity(
                                ontology_id=ontology.id,
                                entity_type='property',
                                uri=prop['uri'],
                                label=prop.get('label', [None])[0] if prop.get('label') else None,
                                comment=prop.get('comment', [None])[0] if prop.get('comment') else None,
                                domain=prop.get('domain', [None])[0] if prop.get('domain') else None,
                                range=prop.get('range', [None])[0] if prop.get('range') else None
                            )
                            db.session.add(entity)
                        
                        # Import individuals
                        for ind in enhanced_data.get('individuals', []):
                            entity = OntologyEntity(
                                ontology_id=ontology.id,
                                entity_type='individual',
                                uri=ind['uri'],
                                label=ind.get('label', [None])[0] if ind.get('label') else None,
                                comment=ind.get('comment', [None])[0] if ind.get('comment') else None
                            )
                            db.session.add(entity)
                    else:
                        # Use basic content parsing for entity extraction
                        entity_counts = _extract_entities_from_content(ontology, content, format_hint)
                        app.logger.info(f"Extracted {sum(entity_counts.values())} entities using basic parsing")
                    
                    db.session.commit()
                    
                    success_msg = f"Successfully imported ontology: {ontology_name}"
                    if use_reasoning:
                        reasoning_result = result.get('reasoning_result', {})
                        inferred_count = reasoning_result.get('inferred_count', 0)
                        consistency = reasoning_result.get('is_consistent', 'unknown')
                        success_msg += f" (Reasoning: {inferred_count} inferred relationships, consistency: {consistency})"
                    
                    flash(success_msg, 'success')
                    return redirect(url_for('ontology_detail_or_uri_resolution', ontology_name=uri_safe_name))
                else:
                    flash(f"Import failed: {result.get('message', 'Unknown error')}", 'error')
                    
            except Exception as e:
                flash(f"Error importing ontology: {str(e)}", 'error')
                app.logger.error(f"Import error: {e}", exc_info=True)
        
        return render_template('import.html')
    
    @app.route('/api/versions/<int:version_id>')
    def get_version_api(version_id):
        """Get version details via API."""
        version = OntologyVersion.query.get_or_404(version_id)
        return jsonify({
            'success': True,
            'version': {
                'id': version.id,
                'version_number': version.version_number,
                'version_tag': version.version_tag,
                'change_summary': version.change_summary,
                'created_at': version.created_at.isoformat() if version.created_at else None,
                'created_by': version.created_by,
                'is_current': version.is_current,
                'is_draft': version.is_draft,
                'workflow_status': version.workflow_status,
                'meta_data': version.meta_data
            }
        })
    
    def _extract_entities_from_content(ontology, content, format_hint='turtle'):
        """Helper function to extract entities from ontology content."""
        from rdflib import RDF, RDFS, OWL
        
        # Auto-detect format if needed
        if not format_hint or format_hint == 'turtle':
            if '<?xml' in content or '<rdf:RDF' in content or 'xmlns:rdf' in content:
                format_hint = 'xml'
            elif '@prefix' in content or '@base' in content:
                format_hint = 'turtle'
            else:
                format_hint = 'turtle'  # Default fallback
        
        # Parse content with detected format
        g = rdflib.Graph()
        try:
            g.parse(data=content, format=format_hint)
        except Exception as parse_error:
            # Try alternative formats if parsing fails
            if format_hint == 'turtle':
                try:
                    g.parse(data=content, format='xml')
                    format_hint = 'xml'
                except:
                    raise parse_error
            elif format_hint == 'xml':
                try:
                    g.parse(data=content, format='turtle')
                    format_hint = 'turtle'
                except:
                    raise parse_error
            else:
                raise parse_error
        
        # Clear existing entities for this ontology
        OntologyEntity.query.filter_by(ontology_id=ontology.id).delete()
        
        entity_counts = {'class': 0, 'property': 0, 'individual': 0}
        
        # Extract classes
        for cls in g.subjects(RDF.type, OWL.Class):
            label = next(g.objects(cls, RDFS.label), None)
            comment = next(g.objects(cls, RDFS.comment), None)
            subclass_of = list(g.objects(cls, RDFS.subClassOf))
            
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='class',
                uri=str(cls),
                label=str(label) if label else None,
                comment=str(comment) if comment else None,
                parent_uri=str(subclass_of[0]) if subclass_of else None
            )
            db.session.add(entity)
            entity_counts['class'] += 1
        
        # Extract properties
        for prop in g.subjects(RDF.type, OWL.ObjectProperty):
            label = next(g.objects(prop, RDFS.label), None)
            comment = next(g.objects(prop, RDFS.comment), None)
            domain = next(g.objects(prop, RDFS.domain), None)
            range_val = next(g.objects(prop, RDFS.range), None)
            
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='property',
                uri=str(prop),
                label=str(label) if label else None,
                comment=str(comment) if comment else None,
                domain=str(domain) if domain else None,
                range=str(range_val) if range_val else None
            )
            db.session.add(entity)
            entity_counts['property'] += 1
        
        for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
            label = next(g.objects(prop, RDFS.label), None)
            comment = next(g.objects(prop, RDFS.comment), None)
            domain = next(g.objects(prop, RDFS.domain), None)
            range_val = next(g.objects(prop, RDFS.range), None)
            
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='property',
                uri=str(prop),
                label=str(label) if label else None,
                comment=str(comment) if comment else None,
                domain=str(domain) if domain else None,
                range=str(range_val) if range_val else None
            )
            db.session.add(entity)
            entity_counts['property'] += 1
        
        # Note: class_count and property_count are computed properties, no need to set them
        
        return entity_counts

    @app.route('/api/versions/<int:version_id>/make-current', methods=['POST'])
    def make_version_current(version_id):
        """Make a version the current version."""
        try:
            version = OntologyVersion.query.get_or_404(version_id)
            ontology = version.ontology
            
            # Set all versions to not current
            OntologyVersion.query.filter_by(
                ontology_id=ontology.id
            ).update({'is_current': False})
            
            # Make this version current
            version.is_current = True
            version.is_draft = False
            version.workflow_status = 'published'
            
            # Re-extract entities from the new current version content
            entities_updated = False
            try:
                entity_counts = _extract_entities_from_content(ontology, version.content)
                total_entities = sum(entity_counts.values())
                entities_updated = True
                app.logger.info(f"Re-extracted {total_entities} entities for ontology {ontology.name} version {version.version_number}")
            except Exception as e:
                app.logger.warning(f"Failed to re-extract entities when making version current: {e}")
                # Don't fail the version change if entity extraction fails
            
            # Commit the changes
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Version {version.version_number} is now the current version',
                'entities_updated': entities_updated
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.route('/drafts')
    def drafts():
        """View all draft ontologies."""
        page = request.args.get('page', 1, type=int)
        per_page = 10
        
        # Get draft ontologies with version info
        draft_query = db.session.query(Ontology, OntologyVersion).join(
            OntologyVersion, Ontology.id == OntologyVersion.ontology_id
        ).filter(
            OntologyVersion.is_draft == True
        ).order_by(OntologyVersion.created_at.desc())
        
        pagination = draft_query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        # Get entity counts for each draft
        draft_data = []
        for ont, version in pagination.items:
            entity_count = OntologyEntity.query.filter_by(ontology_id=ont.id).count()
            draft_data.append({
                'ontology': ont,
                'version': version,
                'entity_count': entity_count
            })
        
        return render_template('drafts.html', 
                             drafts=draft_data,
                             pagination=pagination)
    
    @app.route('/search')
    def search():
        """Search for ontologies and entities."""
        query = request.args.get('q', '')
        search_type = request.args.get('type', 'all')
        
        results = {
            'ontologies': [],
            'entities': []
        }
        
        if query:
            # Search ontologies
            if search_type in ['all', 'ontologies']:
                results['ontologies'] = Ontology.query.filter(
                    db.or_(
                        Ontology.name.ilike(f'%{query}%'),
                        Ontology.description.ilike(f'%{query}%'),
                        Ontology.ontology_id.ilike(f'%{query}%')
                    )
                ).all()
            
            # Search entities
            if search_type in ['all', 'entities']:
                results['entities'] = OntologyEntity.query.filter(
                    db.or_(
                        OntologyEntity.label.ilike(f'%{query}%'),
                        OntologyEntity.comment.ilike(f'%{query}%'),
                        OntologyEntity.uri.ilike(f'%{query}%')
                    )
                ).limit(50).all()
        
        return render_template('search.html', 
                             query=query,
                             search_type=search_type,
                             results=results)
    
    @app.route('/ontology/<ontology_name>/edit')
    @login_required
    def edit_ontology(ontology_name):
        """Edit an ontology using ACE editor."""
        # Check if user can edit ontologies
        if not current_user.can_perform_action('edit'):
            flash('You do not have permission to edit ontologies', 'error')
            return redirect(url_for('ontology_detail_or_uri_resolution', ontology_name=ontology_name))
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        
        # Get the content from file storage
        try:
            ont_data = app.ontology_manager.get_ontology(ontology_name)
            content = ont_data.get('content', '')
        except:
            content = ontology.current_content or ''
        
        # Get versions with proper formatting
        versions = OntologyVersion.query.filter_by(
            ontology_id=ontology.id
        ).order_by(OntologyVersion.created_at.desc()).all()
        
        version_list = []
        for v in versions:
            version_list.append({
                'version': str(v.version),
                'created_at': v.created_at.isoformat() if v.created_at else '',
                'created_by': v.created_by or 'system',
                'commit_message': v.commit_message or '',
                'triple_count': v.triple_count
            })
        
        ontology_data = ontology.to_dict()
        ontology_data['versions'] = version_list
        ontology_data['latest_version'] = version_list[0]['version'] if version_list else None
        
        return render_template('editor/edit.html',
                             ontology=ontology_data,
                             content=content,
                             page_title=f"Edit {ontology.name}")
    
    @app.route('/ontology/<ontology_name>/save', methods=['POST'])
    @login_required
    def save_ontology(ontology_name):
        """Save a new version of an ontology."""
        # Check if user can edit ontologies
        if not current_user.can_perform_action('edit'):
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        
        data = request.get_json()
        content = data.get('content', '')
        commit_message = data.get('commit_message', '')
        
        try:
            # Save to file storage
            result = app.ontology_manager.store_ontology(
                ontology_id, 
                content,
                metadata={'commit_message': commit_message}
            )
            
            # Update database
            ontology.content = content
            ontology.updated_at = datetime.now()
            
            # Parse to get stats
            g = rdflib.Graph()
            g.parse(data=content, format='turtle')
            ontology.triple_count = len(g)
            
            # Count classes and properties
            from rdflib import RDF, RDFS, OWL
            ontology.class_count = len(list(g.subjects(RDF.type, OWL.Class)))
            ontology.property_count = (
                len(list(g.subjects(RDF.type, OWL.ObjectProperty))) +
                len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))
            )
            
            # Create version record
            version = OntologyVersion(
                ontology_id=ontology.id,
                version=OntologyVersion.query.filter_by(ontology_id=ontology.id).count() + 1,
                content=content,
                commit_message=commit_message,
                created_at=datetime.now()
            )
            db.session.add(version)
            db.session.commit()
            
            return jsonify({'success': True, 'version_id': version.id})
            
        except Exception as e:
            app.logger.error(f"Error saving ontology: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/ontology/<ontology_name>/save-draft', methods=['POST'])
    def save_draft(ontology_name):
        """Save a draft of an ontology (no version created)."""
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        
        data = request.get_json()
        content = data.get('content', '')
        
        try:
            # Save to temporary location or session
            # For now, just return success
            return jsonify({'success': True})
            
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/validate', methods=['POST'])
    def validate_ontology():
        """Validate an ontology."""
        data = request.get_json()
        content = data.get('content', '')
        
        try:
            # Parse the ontology
            g = rdflib.Graph()
            g.parse(data=content, format='turtle')
            
            # Get statistics
            from rdflib import RDF, RDFS, OWL
            stats = {
                'triples': len(g),
                'classes': len(list(g.subjects(RDF.type, OWL.Class))),
                'properties': (
                    len(list(g.subjects(RDF.type, OWL.ObjectProperty))) +
                    len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))
                )
            }
            
            # Extract entities for preview
            entities = {
                'classes': [],
                'properties': []
            }
            
            # Get first 10 classes
            for s in list(g.subjects(RDF.type, OWL.Class))[:10]:
                label = next(g.objects(s, RDFS.label), None)
                entities['classes'].append({
                    'uri': str(s),
                    'label': str(label) if label else None
                })
            
            # Get first 10 properties
            for s in list(g.subjects(RDF.type, OWL.ObjectProperty))[:10]:
                label = next(g.objects(s, RDFS.label), None)
                entities['properties'].append({
                    'uri': str(s),
                    'label': str(label) if label else None
                })
            
            return jsonify({
                'valid': True,
                'stats': stats,
                'entities': entities
            })
            
        except Exception as e:
            return jsonify({
                'valid': False,
                'errors': [str(e)]
            })
    
    @app.route('/editor/ontology/<ontology_name>/validate', methods=['POST'])
    def validate_ontology_editor(ontology_name):
        """Validate an ontology for the editor interface."""
        data = request.get_json()
        content = data.get('content', '')
        
        try:
            # Parse the ontology
            g = rdflib.Graph()
            g.parse(data=content, format='turtle')
            
            validation_result = {
                'valid': True,
                'errors': [],
                'warnings': [],
                'stats': {
                    'triples': len(g),
                    'classes': 0,
                    'properties': 0,
                    'individuals': 0
                }
            }
            
            # Count entities
            from rdflib import RDF, RDFS, OWL
            validation_result['stats']['classes'] = len(list(g.subjects(RDF.type, OWL.Class)))
            validation_result['stats']['properties'] = (
                len(list(g.subjects(RDF.type, OWL.ObjectProperty))) +
                len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))
            )
            validation_result['stats']['individuals'] = len(list(g.subjects(RDF.type, OWL.NamedIndividual)))
            
            return jsonify({'validation': validation_result})
            
        except Exception as e:
            return jsonify({
                'validation': {
                    'valid': False,
                    'errors': [str(e)],
                    'warnings': [],
                    'stats': {}
                }
            })
    
    @app.route('/editor/ontology/<ontology_name>/version/<version_id>')
    def get_editor_version(ontology_name, version_id):
        """Get a specific version of an ontology for the editor."""
        version = OntologyVersion.query.get_or_404(version_id)
        
        return jsonify({
            'success': True,
            'content': version.content,
            'version': version.version,
            'commit_message': version.commit_message,
            'created_at': version.created_at.isoformat() if version.created_at else None
        })
    
    @app.route('/editor/ontology/<ontology_name>/save', methods=['POST'])
    def save_ontology_editor(ontology_name):
        """Save a new version of an ontology from the editor."""
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        
        data = request.get_json()
        content = data.get('content', '')
        commit_message = data.get('commit_message', '')
        extract_entities = data.get('extract_entities', False)
        
        try:
            # Validate the content first
            g = rdflib.Graph()
            g.parse(data=content, format='turtle')
            
            # Save to file storage
            result = app.ontology_manager.store_ontology(
                ontology_id, 
                content,
                metadata={'commit_message': commit_message}
            )
            
            # Update database
            ontology.content = content
            ontology.updated_at = datetime.now()
            
            # Get stats from parsed graph
            from rdflib import RDF, RDFS, OWL
            ontology.triple_count = len(g)
            ontology.class_count = len(list(g.subjects(RDF.type, OWL.Class)))
            ontology.property_count = (
                len(list(g.subjects(RDF.type, OWL.ObjectProperty))) +
                len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))
            )
            
            # Create version record
            version = OntologyVersion(
                ontology_id=ontology.id,
                version=OntologyVersion.query.filter_by(ontology_id=ontology.id).count() + 1,
                content=content,
                commit_message=commit_message,
                created_at=datetime.now(),
                triple_count=ontology.triple_count
            )
            db.session.add(version)
            db.session.commit()
            
            response_data = {
                'success': True, 
                'version_id': version.id,
                'version': version.version
            }
            
            # If requested, extract entities (simplified for now)
            if extract_entities:
                response_data['entity_extraction'] = {
                    'total_entities': ontology.class_count + ontology.property_count,
                    'entity_counts': {
                        'class': ontology.class_count,
                        'property': ontology.property_count
                    }
                }
            
            return jsonify(response_data)
            
        except Exception as e:
            app.logger.error(f"Error saving ontology: {e}")
            return jsonify({
                'success': False, 
                'error': str(e),
                'validation': {
                    'valid': False,
                    'errors': [str(e)]
                }
            }), 500
    
    @app.route('/editor/api/extract-entities/<ontology_name>', methods=['POST'])
    def extract_entities_editor(ontology_name):
        """Extract entities from an ontology for the editor."""
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        
        try:
            # Get ontology content (use current version content)
            content = ontology.current_content
            if not content:
                # Fallback to ontology manager if no content in database
                ont_data = app.ontology_manager.get_ontology(ontology_name)
                content = ont_data.get('content', ontology.content)
            
            if not content:
                return jsonify({
                    'success': False,
                    'error': 'No content available for entity extraction'
                }), 400
            
            # Use the helper function for extraction
            entity_counts = _extract_entities_from_content(ontology, content)
            
            db.session.commit()
            
            total_entities = sum(entity_counts.values())
            
            return jsonify({
                'success': True,
                'total_entities': total_entities,
                'entity_counts': entity_counts,
                'message': f'Successfully extracted {total_entities} entities'
            })
            
        except Exception as e:
            app.logger.error(f"Error extracting entities: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.route('/ontology/<ontology_name>/version/<version_id>')
    def get_ontology_version(ontology_name, version_id):
        """Get a specific version of an ontology."""
        version = OntologyVersion.query.get_or_404(version_id)
        
        return jsonify({
            'content': version.content,
            'version': version.version,
            'commit_message': version.commit_message,
            'created_at': version.created_at.isoformat() if version.created_at else None
        })
    
    @app.route('/api/ontologies')
    def api_ontologies():
        """API endpoint to list ontologies."""
        ontologies = Ontology.query.all()
        return jsonify([ont.to_dict() for ont in ontologies])
    
    @app.route('/api/ontology/<ontology_name>')
    def api_ontology_detail(ontology_name):
        """API endpoint for ontology details."""
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        data = ontology.to_dict()
        
        # Add entity counts
        data['entity_counts'] = {
            'classes': OntologyEntity.query.filter_by(
                ontology_id=ontology.id, entity_type='class'
            ).count(),
            'properties': OntologyEntity.query.filter_by(
                ontology_id=ontology.id, entity_type='property'
            ).count(),
            'individuals': OntologyEntity.query.filter_by(
                ontology_id=ontology.id, entity_type='individual'
            ).count()
        }
        
        return jsonify(data)
    
    @app.route('/editor/api/ontologies/<ontology_name>/entities')
    def api_ontology_entities(ontology_name):
        """API endpoint for ProEthica integration - get entities for an ontology."""
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        
        # Get all entities for this ontology
        entities = OntologyEntity.query.filter_by(ontology_id=ontology.id).all()
        
        # Organize entities by category for ProEthica format
        entities_by_category = {}
        
        for entity in entities:
            category = entity.entity_type
            if category not in entities_by_category:
                entities_by_category[category] = []
            
            # Format entity to match ProEthica expectations
            entity_data = {
                "id": entity.uri,
                "uri": entity.uri,
                "label": entity.label or (entity.uri.split('#')[-1] if '#' in str(entity.uri) else str(entity.uri).split('/')[-1]),
                "description": entity.comment or "",
                "category": category,
                "type": category,
                "from_base": True,
                "parent_class": entity.domain if entity.entity_type == 'property' else None
            }
            
            # Add additional properties for roles/capabilities if needed
            if category == 'role':
                entity_data["capabilities"] = []
            
            entities_by_category[category].append(entity_data)
        
        # Return in ProEthica expected format
        return jsonify({
            "entities": entities_by_category,
            "is_mock": False,
            "source": "ontserve",
            "total_entities": len(entities),
            "ontology_name": ontology_name
        })
    
    # ================================
    # Draft Ontology Management APIs
    # ================================
    
    @app.route('/editor/api/ontologies/<ontology_name>/draft', methods=['POST'])
    def create_draft_ontology(ontology_name):
        """Create a new draft ontology from extracted concepts."""
        try:
            data = request.get_json()
            concepts = data.get('concepts', [])
            base_imports = data.get('base_imports', [])
            metadata = data.get('metadata', {})
            created_by = data.get('created_by', 'system')
            
            # Check if ontology already exists
            ontology = Ontology.query.filter_by(name=ontology_name).first()
            
            if ontology:
                # Check if there's already a draft version
                existing_draft = OntologyVersion.query.filter_by(
                    ontology_id=ontology.id,
                    is_draft=True
                ).first()
                
                if existing_draft:
                    return jsonify({
                        'success': False,
                        'error': f'Draft version already exists for {ontology_name}'
                    }), 409
            else:
                # Create new ontology
                ontology = Ontology(
                    name=ontology_name,
                    base_uri=f'http://proethica.org/ontology/{ontology_name}',
                    description=f'Extracted concepts ontology: {ontology_name}',
                    is_base=False,
                    is_editable=True,
                    meta_data=metadata
                )
                db.session.add(ontology)
                db.session.flush()  # Get the ID
            
            # Generate RDF content from concepts
            rdf_content = generate_rdf_from_concepts(ontology_name, concepts, base_imports)
            
            # Create draft version
            version = OntologyVersion(
                ontology_id=ontology.id,
                version_number=1,
                version_tag='v1.0-draft',
                content=rdf_content,
                change_summary='Initial draft from concept extraction',
                created_by=created_by,
                is_current=True,
                is_draft=True,
                workflow_status='draft',
                meta_data=metadata
            )
            db.session.add(version)
            db.session.commit()
            
            # Parse RDF content and extract entities into ontology_entities table
            try:
                g = rdflib.Graph()
                g.parse(data=rdf_content, format='turtle')
                
                from rdflib import RDF, RDFS, OWL
                
                # Clear existing entities for this ontology (in case of recreate)
                OntologyEntity.query.filter_by(ontology_id=ontology.id).delete()
                
                entity_counts = {'class': 0, 'property': 0, 'individual': 0}
                
                # Extract classes
                for cls in g.subjects(RDF.type, OWL.Class):
                    label = next(g.objects(cls, RDFS.label), None)
                    comment = next(g.objects(cls, RDFS.comment), None)
                    subclass_of = list(g.objects(cls, RDFS.subClassOf))
                    
                    entity = OntologyEntity(
                        ontology_id=ontology.id,
                        entity_type='class',
                        uri=str(cls),
                        label=str(label) if label else None,
                        comment=str(comment) if comment else None,
                        parent_uri=str(subclass_of[0]) if subclass_of else None
                    )
                    db.session.add(entity)
                    entity_counts['class'] += 1
                
                # Extract properties
                for prop in g.subjects(RDF.type, OWL.ObjectProperty):
                    label = next(g.objects(prop, RDFS.label), None)
                    comment = next(g.objects(prop, RDFS.comment), None)
                    domain = next(g.objects(prop, RDFS.domain), None)
                    range_val = next(g.objects(prop, RDFS.range), None)
                    
                    entity = OntologyEntity(
                        ontology_id=ontology.id,
                        entity_type='property',
                        uri=str(prop),
                        label=str(label) if label else None,
                        comment=str(comment) if comment else None,
                        domain={'uri': str(domain)} if domain else None,
                        range={'uri': str(range_val)} if range_val else None
                    )
                    db.session.add(entity)
                    entity_counts['property'] += 1
                
                for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
                    label = next(g.objects(prop, RDFS.label), None)
                    comment = next(g.objects(prop, RDFS.comment), None)
                    domain = next(g.objects(prop, RDFS.domain), None)
                    range_val = next(g.objects(prop, RDFS.range), None)
                    
                    entity = OntologyEntity(
                        ontology_id=ontology.id,
                        entity_type='property',
                        uri=str(prop),
                        label=str(label) if label else None,
                        comment=str(comment) if comment else None,
                        domain={'uri': str(domain)} if domain else None,
                        range={'uri': str(range_val)} if range_val else None
                    )
                    db.session.add(entity)
                    entity_counts['property'] += 1
                
                db.session.commit()
                
                app.logger.info(f"Extracted {entity_counts['class']} classes and {entity_counts['property']} properties for draft ontology {ontology_name}")
                
                return jsonify({
                    'success': True,
                    'ontology_name': ontology_name,
                    'version_id': version.id,
                    'version_number': version.version_number,
                    'concepts_count': len(concepts),
                    'entities_extracted': entity_counts,
                    'message': f'Draft ontology created with {len(concepts)} concepts and {sum(entity_counts.values())} extracted entities'
                })
                
            except Exception as parse_error:
                app.logger.error(f"Error parsing RDF content for entity extraction: {parse_error}")
                # Return success anyway since the ontology was created, just mention the parsing issue
                return jsonify({
                    'success': True,
                    'ontology_name': ontology_name,
                    'version_id': version.id,
                    'version_number': version.version_number,
                    'concepts_count': len(concepts),
                    'message': f'Draft ontology created with {len(concepts)} concepts (entity extraction failed: {parse_error})'
                })
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error creating draft ontology: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.route('/editor/api/ontologies/<ontology_name>/draft', methods=['DELETE'])
    def delete_draft_ontology(ontology_name):
        """Delete draft ontology (replaces Clear Pending functionality)."""
        try:
            ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
            
            # Find all draft versions
            draft_versions = OntologyVersion.query.filter_by(
                ontology_id=ontology.id,
                is_draft=True
            ).all()
            
            if not draft_versions:
                return jsonify({
                    'success': False,
                    'error': f'No draft versions found for {ontology_name}'
                }), 404
            
            # Delete all draft versions
            for version in draft_versions:
                db.session.delete(version)
            
            # Check if this ontology has any published versions
            published_versions = OntologyVersion.query.filter_by(
                ontology_id=ontology.id,
                is_draft=False
            ).count()
            
            # If no published versions, delete the entire ontology
            if published_versions == 0:
                # Also delete any extracted entities
                OntologyEntity.query.filter_by(ontology_id=ontology.id).delete()
                db.session.delete(ontology)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'ontology_name': ontology_name,
                'draft_versions_deleted': len(draft_versions),
                'ontology_deleted': published_versions == 0,
                'message': f'Deleted {len(draft_versions)} draft versions'
            })
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error deleting draft ontology: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.errorhandler(404)
    def not_found(error):
        """404 error handler."""
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """500 error handler."""
        db.session.rollback()
        return render_template('500.html'), 500


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
