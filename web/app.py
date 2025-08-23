"""
OntServe Web Application

Flask application for managing and serving ontologies with semantic search capabilities.
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import OntServe modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import rdflib

from config import config
from models import db, init_db, Ontology, OntologyEntity, OntologyVersion
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
    def ontology_detail(ontology_name):
        """Detail view for a specific ontology."""
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        
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
        
        # Get versions
        versions = OntologyVersion.query.filter_by(
            ontology_id=ontology.id
        ).order_by(OntologyVersion.created_at.desc()).all()
        
        return render_template('ontology_detail.html',
                             ontology=ontology,
                             entities=entities,
                             versions=versions)
    
    @app.route('/ontology/<ontology_name>/content')
    def ontology_content(ontology_name):
        """Return raw TTL content of an ontology."""
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        content = ontology.current_content
        if content is None:
            return "No content available for this ontology", 404
        return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    
    @app.route('/import', methods=['GET', 'POST'])
    def import_ontology():
        """Import a new ontology from URL or file."""
        if request.method == 'POST':
            source = request.form.get('source')
            source_type = request.form.get('source_type', 'url')
            name = request.form.get('name')
            description = request.form.get('description')
            
            try:
                # Import using OntologyManager
                result = app.ontology_manager.import_ontology(
                    source=source,
                    name=name,
                    description=description
                )
                
                if result['success']:
                    # Save to database
                    ontology = Ontology(
                        ontology_id=result['ontology_id'],
                        name=name or result['metadata'].get('name', 'Unnamed'),
                        description=description or result['metadata'].get('description', ''),
                        content=result.get('content', ''),
                        format=result['metadata'].get('format', 'turtle'),
                        source_url=source if source_type == 'url' else None,
                        source_file=source if source_type == 'file' else None,
                        triple_count=result['metadata'].get('triple_count'),
                        class_count=result['metadata'].get('class_count'),
                        property_count=result['metadata'].get('property_count'),
                        meta_data=result['metadata']
                    )
                    db.session.add(ontology)
                    
                    # Extract and save entities
                    classes = app.ontology_manager.extract_classes(result['ontology_id'])
                    for cls in classes:
                        entity = OntologyEntity(
                            ontology_id=ontology.id,
                            entity_type='class',
                            uri=cls['uri'],
                            label=cls.get('label'),
                            comment=cls.get('comment'),
                            parent_uri=cls.get('subclass_of', [None])[0] if cls.get('subclass_of') else None
                        )
                        db.session.add(entity)
                    
                    properties = app.ontology_manager.extract_properties(result['ontology_id'])
                    for prop in properties:
                        entity = OntologyEntity(
                            ontology_id=ontology.id,
                            entity_type='property',
                            uri=prop['uri'],
                            label=prop.get('label'),
                            comment=prop.get('comment'),
                            domain=prop.get('domain'),
                            range=prop.get('range')
                        )
                        db.session.add(entity)
                    
                    db.session.commit()
                    
                    flash(f"Successfully imported ontology: {result['ontology_id']}", 'success')
                    return redirect(url_for('ontology_detail', ontology_id=result['ontology_id']))
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
            
            # Commit the changes
            db.session.commit()
            
            # Also update entities if needed
            # This could trigger re-extraction of entities from the new version
            
            return jsonify({
                'success': True,
                'message': f'Version {version.version_number} is now the current version'
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
    def edit_ontology(ontology_name):
        """Edit an ontology using ACE editor."""
        ontology = Ontology.query.filter_by(name=ontology_name).first_or_404()
        
        # Get the content from file storage
        try:
            ont_data = app.ontology_manager.get_ontology(ontology_id)
            content = ont_data.get('content', '')
        except:
            content = ontology.content or ''
        
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
    def save_ontology(ontology_name):
        """Save a new version of an ontology."""
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
            # Get ontology content
            ont_data = app.ontology_manager.get_ontology(ontology_name)
            content = ont_data.get('content', ontology.content)
            
            # Parse and extract entities
            g = rdflib.Graph()
            g.parse(data=content, format='turtle')
            
            from rdflib import RDF, RDFS, OWL
            
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
            
            # Update ontology counts
            ontology.class_count = entity_counts['class']
            ontology.property_count = entity_counts['property']
            
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
                "label": entity.label or entity.uri.split('#')[-1].split('/')[-1],
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
