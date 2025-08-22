"""
OntServe Editor Routes

Flask routes for the ontology editor web interface.
Provides API endpoints that replace Neo4j queries with pgvector semantic search.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from flask import Blueprint, request, jsonify, render_template, current_app, flash
from werkzeug.exceptions import BadRequest, NotFound

from models import db, Ontology, OntologyEntity, OntologyVersion
from storage.file_storage import FileStorage
from core.enhanced_processor import EnhancedOntologyProcessor, ProcessingOptions
from .services import OntologyEntityService, OntologyValidationService
from .utils import EntityTypeMapper, HierarchyBuilder, SearchHelper

logger = logging.getLogger(__name__)


def create_editor_blueprint(storage_backend=None, config: Dict[str, Any] = None) -> Blueprint:
    """
    Create the ontology editor blueprint.
    
    Args:
        storage_backend: Storage backend instance (will use FileStorage if not provided)
        config: Configuration dictionary
        
    Returns:
        Flask Blueprint for the ontology editor
    """
    bp = Blueprint('ontology_editor', __name__, url_prefix='/editor')
    
    # Configuration defaults
    config = config or {}
    require_auth = config.get('require_auth', False)
    admin_only = config.get('admin_only', False)
    
    # Initialize storage backend
    if storage_backend is None:
        storage_config = config.get('storage', {})
        storage_backend = FileStorage(storage_config)
    
    # Initialize services
    entity_service = OntologyEntityService(storage_backend)
    validation_service = OntologyValidationService(storage_backend)
    enhanced_processor = EnhancedOntologyProcessor(storage_backend)
    
    @bp.route('/')
    def index():
        """Main editor interface."""
        try:
            # Get list of available ontologies
            ontologies = db.session.query(Ontology).order_by(Ontology.name).all()
            ontology_list = [ont.to_dict() for ont in ontologies]
            
            return render_template('editor/main.html', 
                                 ontologies=ontology_list,
                                 page_title="Ontology Editor")
                                 
        except Exception as e:
            logger.error(f"Error loading editor: {e}")
            flash(f"Error loading editor: {str(e)}", 'error')
            return render_template('error.html', error=str(e)), 500
    
    @bp.route('/ontology/<ontology_id>')
    def edit_ontology(ontology_id: str):
        """Load ontology in the editor."""
        try:
            # Get ontology
            ontology = db.session.query(Ontology).filter_by(ontology_id=ontology_id).first()
            if not ontology:
                raise NotFound(f"Ontology {ontology_id} not found")
            
            # Get latest version
            latest_version = db.session.query(OntologyVersion)\
                .filter_by(ontology_id=ontology.id)\
                .order_by(OntologyVersion.created_at.desc())\
                .first()
            
            # Get version history
            versions = db.session.query(OntologyVersion)\
                .filter_by(ontology_id=ontology.id)\
                .order_by(OntologyVersion.created_at.desc())\
                .all()
            
            version_list = []
            for v in versions:
                version_list.append({
                    'version': v.version,
                    'created_at': v.created_at.isoformat(),
                    'created_by': v.created_by,
                    'commit_message': v.commit_message,
                    'triple_count': v.triple_count
                })
            
            ontology_data = ontology.to_dict()
            ontology_data['versions'] = version_list
            ontology_data['latest_version'] = latest_version.version if latest_version else None
            
            return render_template('editor/edit.html',
                                 ontology=ontology_data,
                                 content=ontology.content,
                                 page_title=f"Edit {ontology.name}")
                                 
        except Exception as e:
            logger.error(f"Error loading ontology {ontology_id}: {e}")
            flash(f"Error loading ontology: {str(e)}", 'error')
            return render_template('error.html', error=str(e)), 500
    
    @bp.route('/ontology/<ontology_id>/save', methods=['POST'])
    def save_ontology(ontology_id: str):
        """Save ontology content with versioning."""
        try:
            # Get request data
            data = request.get_json()
            if not data:
                raise BadRequest("No data provided")
            
            content = data.get('content', '').strip()
            commit_message = data.get('commit_message', '')
            
            if not content:
                raise BadRequest("Content cannot be empty")
            
            # Get ontology
            ontology = db.session.query(Ontology).filter_by(ontology_id=ontology_id).first()
            if not ontology:
                raise NotFound(f"Ontology {ontology_id} not found")
            
            # Validate the content first
            validation_result = validation_service.validate_ontology(content)
            if not validation_result['valid']:
                return jsonify({
                    'success': False,
                    'error': 'Validation failed',
                    'validation': validation_result
                }), 400
            
            # Create new version
            version_num = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_version = OntologyVersion(
                ontology_id=ontology.id,
                version=version_num,
                content=content,
                commit_message=commit_message,
                created_at=datetime.utcnow(),
                created_by=data.get('user', 'system')  # TODO: Get from auth
            )
            
            # Update ontology content
            ontology.content = content
            ontology.updated_at = datetime.utcnow()
            
            # Store in file system
            storage_result = storage_backend.store(
                ontology_id, 
                content,
                metadata={
                    'version': version_num,
                    'commit_message': commit_message,
                    'updated_at': datetime.utcnow().isoformat()
                }
            )
            
            # Save to database
            db.session.add(new_version)
            db.session.commit()
            
            # Extract and update entities
            try:
                entities = entity_service.extract_and_store_entities(ontology_id, force_refresh=True)
                logger.info(f"Extracted {len(entities)} entities for {ontology_id}")
            except Exception as e:
                logger.warning(f"Failed to extract entities: {e}")
            
            return jsonify({
                'success': True,
                'version': version_num,
                'storage_result': storage_result,
                'validation': validation_result
            })
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving ontology {ontology_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/ontology/<ontology_id>/validate', methods=['POST'])
    def validate_ontology_content(ontology_id: str):
        """Validate ontology content."""
        try:
            data = request.get_json()
            if not data:
                raise BadRequest("No data provided")
            
            content = data.get('content', '').strip()
            if not content:
                raise BadRequest("Content cannot be empty")
            
            # Validate the content
            validation_result = validation_service.validate_ontology(content)
            
            return jsonify({
                'success': True,
                'validation': validation_result
            })
            
        except Exception as e:
            logger.error(f"Error validating ontology {ontology_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/ontology/<ontology_id>/entities')
    def get_entities(ontology_id: str):
        """Get entities for an ontology with optional filtering and search."""
        try:
            # Get ontology
            ontology = db.session.query(Ontology).filter_by(ontology_id=ontology_id).first()
            if not ontology:
                raise NotFound(f"Ontology {ontology_id} not found")
            
            # Get query parameters
            entity_type = request.args.get('type')
            search_term = request.args.get('search', '').strip()
            limit = int(request.args.get('limit', 100))
            
            # Get entities from database
            query = db.session.query(OntologyEntity).filter_by(ontology_id=ontology.id)
            
            if entity_type:
                query = query.filter_by(entity_type=entity_type)
            
            entities = query.limit(limit).all()
            
            # Convert to dictionaries
            entity_list = [entity.to_dict() for entity in entities]
            
            # Apply text search if provided
            if search_term:
                entity_list = SearchHelper.filter_entities_by_text(entity_list, search_term)
            
            # Add entity type mapping information
            for entity in entity_list:
                entity['display_name'] = EntityTypeMapper.get_display_name(entity['entity_type'])
                entity['css_class'] = EntityTypeMapper.get_css_class(entity['entity_type'])
                entity['icon'] = EntityTypeMapper.get_icon(entity['entity_type'])
                entity['color'] = EntityTypeMapper.get_entity_color(entity['entity_type'], entity['uri'])
            
            return jsonify({
                'success': True,
                'entities': entity_list,
                'total_count': len(entity_list),
                'ontology': ontology.to_dict()
            })
            
        except Exception as e:
            logger.error(f"Error getting entities for {ontology_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/ontology/<ontology_id>/hierarchy')
    def get_hierarchy(ontology_id: str):
        """Get hierarchical structure for ontology entities."""
        try:
            # Get entity type filter
            entity_type = request.args.get('type', 'class')
            
            # Get hierarchy from service
            hierarchy = entity_service.get_entity_hierarchy(ontology_id, entity_type)
            
            # Calculate statistics
            hierarchy_builder = HierarchyBuilder()
            stats = hierarchy_builder.calculate_hierarchy_stats(hierarchy)
            
            return jsonify({
                'success': True,
                'hierarchy': hierarchy,
                'stats': stats,
                'ontology': {
                    'ontology_id': ontology_id,
                    'entity_type': entity_type
                }
            })
            
        except Exception as e:
            logger.error(f"Error getting hierarchy for {ontology_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/ontology/<ontology_name>/visualize')
    def visualize_ontology(ontology_name: str):
        """Visualization interface for ontology."""
        try:
            logger.info(f"Loading visualization for ontology: {ontology_name}")
            
            # Get ontology
            ontology = db.session.query(Ontology).filter_by(name=ontology_name).first()
            if not ontology:
                logger.warning(f"Ontology {ontology_name} not found in database")
                return f"<h1>Ontology Not Found</h1><p>Ontology '{ontology_name}' was not found in the database.</p>", 404
            
            logger.info(f"Found ontology: {ontology.name}, ID: {ontology.id}")
            
            return render_template('editor/visualize.html',
                                 ontology=ontology.to_dict(),
                                 ontology_name=ontology_name,
                                 page_title=f"Visualize {ontology.name}")
                                 
        except Exception as e:
            logger.error(f"Error loading visualization for {ontology_name}: {e}", exc_info=True)
            return f"<h1>Error</h1><p>Error loading visualization: {str(e)}</p>", 500
    
    @bp.route('/ontology/<ontology_id>/versions')
    def get_versions(ontology_id: str):
        """Get version history for an ontology."""
        try:
            # Get ontology
            ontology = db.session.query(Ontology).filter_by(ontology_id=ontology_id).first()
            if not ontology:
                raise NotFound(f"Ontology {ontology_id} not found")
            
            # Get versions
            versions = db.session.query(OntologyVersion)\
                .filter_by(ontology_id=ontology.id)\
                .order_by(OntologyVersion.created_at.desc())\
                .all()
            
            version_list = []
            for v in versions:
                version_list.append({
                    'version': v.version,
                    'created_at': v.created_at.isoformat(),
                    'created_by': v.created_by,
                    'commit_message': v.commit_message,
                    'triple_count': v.triple_count,
                    'changes_summary': v.changes_summary
                })
            
            return jsonify({
                'success': True,
                'versions': version_list,
                'ontology': ontology.to_dict()
            })
            
        except Exception as e:
            logger.error(f"Error getting versions for {ontology_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/entities/search')
    def search_entities():
        """Semantic search across entities using pgvector."""
        try:
            # Get search parameters
            query = request.args.get('query', '').strip()
            ontology_id = request.args.get('ontology_id')
            entity_type = request.args.get('entity_type')
            limit = int(request.args.get('limit', 10))
            
            if not query:
                raise BadRequest("Query parameter is required")
            
            # Perform semantic search
            results = entity_service.search_similar_entities(
                query, ontology_id, entity_type, limit
            )
            
            # Add display information
            for result in results:
                result['display_name'] = EntityTypeMapper.get_display_name(result['entity_type'])
                result['css_class'] = EntityTypeMapper.get_css_class(result['entity_type'])
                result['icon'] = EntityTypeMapper.get_icon(result['entity_type'])
                result['color'] = EntityTypeMapper.get_entity_color(result['entity_type'], result['uri'])
            
            return jsonify({
                'success': True,
                'results': results,
                'query': query,
                'total_count': len(results)
            })
            
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/entity/<int:entity_id>')
    def get_entity_details(entity_id: int):
        """Get detailed information about a specific entity."""
        try:
            # Get entity
            entity = db.session.query(OntologyEntity).get(entity_id)
            if not entity:
                raise NotFound(f"Entity {entity_id} not found")
            
            # Get ontology information
            ontology = db.session.query(Ontology).get(entity.ontology_id)
            
            # Build entity details
            entity_dict = entity.to_dict()
            entity_dict['display_name'] = EntityTypeMapper.get_display_name(entity.entity_type)
            entity_dict['css_class'] = EntityTypeMapper.get_css_class(entity.entity_type)
            entity_dict['icon'] = EntityTypeMapper.get_icon(entity.entity_type)
            entity_dict['color'] = EntityTypeMapper.get_entity_color(entity.entity_type, entity.uri)
            entity_dict['is_bfo_aligned'] = EntityTypeMapper.is_bfo_aligned(entity.uri)
            entity_dict['ontology'] = ontology.to_dict() if ontology else None
            
            # Get related entities (children and parents)
            children = db.session.query(OntologyEntity)\
                .filter_by(ontology_id=entity.ontology_id, parent_uri=entity.uri)\
                .all()
            
            entity_dict['children'] = [child.to_dict() for child in children]
            
            # Get parent if exists
            if entity.parent_uri:
                parent = db.session.query(OntologyEntity)\
                    .filter_by(ontology_id=entity.ontology_id, uri=entity.parent_uri)\
                    .first()
                entity_dict['parent'] = parent.to_dict() if parent else None
            else:
                entity_dict['parent'] = None
            
            return jsonify({
                'success': True,
                'entity': entity_dict
            })
            
        except Exception as e:
            logger.error(f"Error getting entity details {entity_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/entity/<int:entity_id>/similar')
    def get_similar_entities(entity_id: int):
        """Get entities similar to a specific entity using semantic search."""
        try:
            # Get entity
            entity = db.session.query(OntologyEntity).get(entity_id)
            if not entity:
                raise NotFound(f"Entity {entity_id} not found")
            
            # Build search query from entity
            search_parts = []
            if entity.label:
                search_parts.append(entity.label)
            if entity.comment:
                search_parts.append(entity.comment)
            
            query = " ".join(search_parts) if search_parts else entity.uri
            
            # Get limit
            limit = int(request.args.get('limit', 10))
            
            # Perform search
            results = entity_service.search_similar_entities(
                query, None, entity.entity_type, limit + 1  # +1 to account for self
            )
            
            # Remove the entity itself from results
            results = [r for r in results if r['id'] != entity_id][:limit]
            
            # Add display information
            for result in results:
                result['display_name'] = EntityTypeMapper.get_display_name(result['entity_type'])
                result['css_class'] = EntityTypeMapper.get_css_class(result['entity_type'])
                result['icon'] = EntityTypeMapper.get_icon(result['entity_type'])
                result['color'] = EntityTypeMapper.get_entity_color(result['entity_type'], result['uri'])
            
            return jsonify({
                'success': True,
                'similar_entities': results,
                'source_entity': entity.to_dict(),
                'total_count': len(results)
            })
            
        except Exception as e:
            logger.error(f"Error getting similar entities for {entity_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/extract-entities/<ontology_id>', methods=['POST'])
    def extract_entities(ontology_id: str):
        """Force re-extraction of entities for an ontology."""
        try:
            # Extract entities
            entities = entity_service.extract_and_store_entities(ontology_id, force_refresh=True)
            
            # Get statistics
            entity_counts = {}
            for entity in entities:
                entity_type = entity.entity_type
                entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
            
            return jsonify({
                'success': True,
                'total_entities': len(entities),
                'entity_counts': entity_counts,
                'message': f"Successfully extracted {len(entities)} entities"
            })
            
        except Exception as e:
            logger.error(f"Error extracting entities for {ontology_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    # ===== ENHANCED PROCESSOR ENDPOINTS =====
    
    @bp.route('/api/enhanced/process/<ontology_name>', methods=['GET'])
    def enhanced_get_entities(ontology_name: str):
        """Get entities for visualization from existing database entities."""
        try:
            # Find ontology by name 
            ontology = Ontology.query.filter_by(name=ontology_name).first()
            if not ontology:
                return jsonify({
                    'success': False,
                    'error': f'Ontology {ontology_name} not found'
                }), 404
            
            # Get all entities for this ontology
            entities = OntologyEntity.query.filter_by(ontology_id=ontology.id).all()
            
            # Transform entities to the format expected by the visualization
            nodes = []
            edges = []
            
            for entity in entities:
                node = {
                    'data': {
                        'id': entity.uri,
                        'label': entity.label or entity.uri.split('#')[-1].split('/')[-1],
                        'uri': entity.uri,
                        'type': entity.entity_type,
                        'comment': entity.comment or '',
                        'properties': entity.properties if hasattr(entity, 'properties') else {}
                    },
                    'classes': f'entity-{entity.entity_type}'
                }
                nodes.append(node)
            
            # For now, we'll create simple hierarchical relationships
            # This is a basic implementation - could be enhanced with actual relationships
            class_nodes = [n for n in nodes if n['data']['type'] == 'class']
            property_nodes = [n for n in nodes if n['data']['type'] == 'property']
            
            # Simple visualization: connect properties to classes
            edge_id = 0
            for prop in property_nodes:
                if class_nodes:  # Connect to first class as example
                    edge = {
                        'data': {
                            'id': f'edge_{edge_id}',
                            'source': prop['data']['id'],
                            'target': class_nodes[0]['data']['id'],
                            'relationship': 'relatedTo'
                        }
                    }
                    edges.append(edge)
                    edge_id += 1
            
            return jsonify({
                'success': True,
                'processing_result': {
                    'nodes': nodes,
                    'edges': edges,
                    'entity_counts': {
                        'classes': len([n for n in nodes if n['data']['type'] == 'class']),
                        'properties': len([n for n in nodes if n['data']['type'] == 'property']),
                        'individuals': len([n for n in nodes if n['data']['type'] == 'individual']),
                        'total': len(nodes)
                    }
                },
                'message': f"Retrieved {len(nodes)} entities for visualization"
            })
            
        except Exception as e:
            logger.error(f"Error getting entities for {ontology_name}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/enhanced/visualization/<ontology_name>')
    def enhanced_get_visualization(ontology_name: str):
        """Get visualization data for ontology."""
        try:
            # Find ontology by name 
            ontology = Ontology.query.filter_by(name=ontology_name).first()
            if not ontology:
                return jsonify({
                    'success': False,
                    'error': f'Ontology {ontology_name} not found'
                }), 404
            
            # Get all entities for this ontology
            entities = OntologyEntity.query.filter_by(ontology_id=ontology.id).all()
            
            # Transform entities to the format expected by the visualization
            nodes = []
            edges = []
            
            for entity in entities:
                node = {
                    'group': 'nodes',
                    'data': {
                        'id': entity.uri,
                        'label': entity.label or entity.uri.split('#')[-1].split('/')[-1],
                        'name': entity.label or entity.uri.split('#')[-1].split('/')[-1],
                        'uri': entity.uri,
                        'type': entity.entity_type,
                        'entity_type': entity.entity_type,
                        'description': entity.comment or '',
                        'comment': entity.comment or '',
                        'is_inferred': False,
                        'restrictions': 0,
                        'namespace': entity.uri.split('#')[0] if '#' in entity.uri else entity.uri.split('/')[:-1]
                    },
                    'classes': f'class-node entity-{entity.entity_type}'
                }
                nodes.append(node)
            
            # Create simple hierarchical relationships for visualization
            class_nodes = [n for n in nodes if n['data']['type'] == 'class']
            property_nodes = [n for n in nodes if n['data']['type'] == 'property']
            
            # Connect properties to classes for better visualization
            edge_id = 0
            for i, prop in enumerate(property_nodes):
                if i < len(class_nodes):  # Connect each property to a class
                    edge = {
                        'group': 'edges',
                        'data': {
                            'id': f'edge_{edge_id}',
                            'source': prop['data']['id'],
                            'target': class_nodes[i % len(class_nodes)]['data']['id'],
                            'type': 'relatedTo',
                            'is_inferred': False
                        },
                        'classes': 'explicit'
                    }
                    edges.append(edge)
                    edge_id += 1
            
            # Statistics for the UI
            entity_counts = {
                'class': len([n for n in nodes if n['data']['type'] == 'class']),
                'property': len([n for n in nodes if n['data']['type'] == 'property']),
                'individual': len([n for n in nodes if n['data']['type'] == 'individual'])
            }
            
            return jsonify({
                'success': True,
                'visualization': {
                    'nodes': nodes,
                    'edges': edges
                },
                'statistics': {
                    'total_entities': len(nodes),
                    'entity_type_counts': entity_counts,
                    'inferred_count': 0,
                    'consistency_check': True
                },
                'message': f"Retrieved {len(nodes)} entities for visualization"
            })
            
        except Exception as e:
            logger.error(f"Error getting visualization for {ontology_name}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @bp.route('/api/enhanced/process/<ontology_id>', methods=['POST'])
    def enhanced_process_ontology(ontology_id: str):
        """Process ontology with enhanced processor (reasoning + embeddings)."""
        try:
            # Get processing options from request
            data = request.get_json() or {}
            
            options = ProcessingOptions(
                use_reasoning=data.get('use_reasoning', True),
                reasoner_type=data.get('reasoner_type', 'hermit'),
                validate_consistency=data.get('validate_consistency', True),
                include_inferred=data.get('include_inferred', True),
                extract_restrictions=data.get('extract_restrictions', True),
                generate_embeddings=data.get('generate_embeddings', True),
                cache_reasoning=data.get('cache_reasoning', True),
                force_refresh=data.get('force_refresh', False)
            )
            
            # Create fresh enhanced processor for this request to ensure proper app context
            fresh_processor = EnhancedOntologyProcessor(storage_backend, db_session=db.session)
            result = fresh_processor.process_ontology(ontology_id, options)
            
            return jsonify({
                'success': result.success,
                'processing_result': result.to_dict(),
                'message': f"Enhanced processing {'completed' if result.success else 'failed'}"
            })
            
        except Exception as e:
            logger.error(f"Error in enhanced processing for {ontology_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/simple/reasoning/<ontology_name>', methods=['POST'])
    def simple_reasoning(ontology_name: str):
        """Simple reasoning endpoint using owlready2 directly."""
        try:
            # Get ontology from database
            ontology = Ontology.query.filter_by(name=ontology_name).first()
            if not ontology:
                return jsonify({
                    'success': False,
                    'error': f'Ontology {ontology_name} not found'
                }), 404
            
            # Get current content
            if not ontology.current_content:
                return jsonify({
                    'success': False,
                    'error': 'No content found for ontology'
                }), 404
            
            # Try reasoning with owlready2
            try:
                import owlready2
                import tempfile
                import os
                
                # Create temporary file with appropriate extension based on content
                content = ontology.current_content
                if content.strip().startswith('<?xml'):
                    # RDF/XML format
                    suffix = '.owl'
                else:
                    # Assume Turtle format
                    suffix = '.ttl'
                
                with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
                    f.write(content)
                    temp_file = f.name
                
                # Load and reason
                world = owlready2.World()
                onto = world.get_ontology(f'file://{temp_file}').load()
                
                # Count entities before reasoning
                classes_before = len(list(onto.classes()))
                properties_before = len(list(onto.properties()))
                
                # Collect class hierarchy before reasoning
                hierarchy_before = {}
                for cls in onto.classes():
                    parents = [str(p) for p in cls.is_a if hasattr(p, 'name')]
                    if parents:
                        hierarchy_before[str(cls)] = parents
                
                # Run reasoning
                with onto:
                    owlready2.sync_reasoner_pellet(world)
                
                # Count entities after reasoning
                classes_after = len(list(onto.classes()))
                properties_after = len(list(onto.properties()))
                
                # Collect class hierarchy after reasoning and find inferences
                hierarchy_after = {}
                inferred_relationships = []
                for cls in onto.classes():
                    parents = [str(p) for p in cls.is_a if hasattr(p, 'name')]
                    if parents:
                        hierarchy_after[str(cls)] = parents
                        # Check for new relationships
                        old_parents = set(hierarchy_before.get(str(cls), []))
                        new_parents = set(parents) - old_parents
                        for new_parent in new_parents:
                            inferred_relationships.append({
                                'child': str(cls),
                                'parent': new_parent,
                                'type': 'subClassOf'
                            })
                
                # Sample some key relationships found
                sample_hierarchy = []
                for cls_name, parents in list(hierarchy_after.items())[:10]:
                    if parents:
                        sample_hierarchy.append({
                            'class': cls_name.split('.')[-1] if '.' in cls_name else cls_name,
                            'parents': [p.split('.')[-1] if '.' in p else p for p in parents]
                        })
                
                # Clean up
                os.unlink(temp_file)
                
                return jsonify({
                    'success': True,
                    'message': f'Reasoning completed successfully. Found {len(hierarchy_after)} hierarchical relationships.',
                    'results': {
                        'classes_before': classes_before,
                        'classes_after': classes_after,
                        'properties_before': properties_before,
                        'properties_after': properties_after,
                        'classes_inferred': classes_after - classes_before,
                        'properties_inferred': properties_after - properties_before,
                        'hierarchical_relationships': len(hierarchy_after),
                        'new_inferred_relationships': len(inferred_relationships),
                        'sample_hierarchy': sample_hierarchy,
                        'inferred_relationships': inferred_relationships[:5]  # First 5 new relationships
                    }
                })
                
            except ImportError:
                return jsonify({
                    'success': False,
                    'error': 'owlready2 not available'
                }), 500
            except Exception as reasoning_error:
                return jsonify({
                    'success': False,
                    'error': f'Reasoning failed: {str(reasoning_error)}'
                }), 500
            
        except Exception as e:
            logger.error(f"Error in simple reasoning for {ontology_name}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/hierarchy/visualization/<ontology_name>', methods=['GET'])
    def hierarchy_visualization(ontology_name: str):
        """Get hierarchical visualization data extracted from ontology content."""
        try:
            # Get ontology from database
            ontology = Ontology.query.filter_by(name=ontology_name).first()
            if not ontology:
                return jsonify({
                    'success': False,
                    'error': f'Ontology {ontology_name} not found'
                }), 404
            
            # Get current content
            if not ontology.current_content:
                return jsonify({
                    'success': False,
                    'error': 'No content found for ontology'
                }), 404
            
            # Extract hierarchical relationships using owlready2
            try:
                import owlready2
                import tempfile
                import os
                
                # Create temporary file with appropriate extension
                content = ontology.current_content
                suffix = '.owl' if content.strip().startswith('<?xml') else '.ttl'
                
                with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
                    f.write(content)
                    temp_file = f.name
                
                # Load with owlready2
                world = owlready2.World()
                onto = world.get_ontology(f'file://{temp_file}').load()
                
                # Extract nodes and hierarchical edges
                nodes = []
                edges = []
                
                # Create nodes for all classes
                class_nodes = {}
                for cls in onto.classes():
                    class_name = cls.name or str(cls).split('.')[-1]
                    node_id = str(cls)
                    class_nodes[node_id] = {
                        'group': 'nodes',
                        'data': {
                            'id': node_id,
                            'label': class_name,
                            'name': class_name,
                            'uri': str(cls),
                            'type': 'class',
                            'entity_type': 'class',
                            'description': f'PROV-O class: {class_name}',
                            'namespace': 'prov'
                        },
                        'classes': 'class-node'
                    }
                    nodes.append(class_nodes[node_id])
                
                # Create hierarchical edges (subClassOf relationships)
                edge_id = 0
                for cls in onto.classes():
                    class_id = str(cls)
                    for parent in cls.is_a:
                        if hasattr(parent, 'name') and str(parent) in class_nodes:
                            parent_id = str(parent)
                            edges.append({
                                'group': 'edges',
                                'data': {
                                    'id': f'edge_{edge_id}',
                                    'source': class_id,
                                    'target': parent_id,
                                    'relationship': 'subClassOf',
                                    'type': 'subClassOf',
                                    'label': 'subClassOf'
                                },
                                'classes': 'hierarchy-edge'
                            })
                            edge_id += 1
                
                # Add key properties as nodes
                property_nodes = {}
                for prop in list(onto.properties())[:20]:  # Limit to avoid clutter
                    prop_name = prop.name or str(prop).split('.')[-1]
                    node_id = str(prop)
                    property_nodes[node_id] = {
                        'group': 'nodes',
                        'data': {
                            'id': node_id,
                            'label': prop_name,
                            'name': prop_name,
                            'uri': str(prop),
                            'type': 'property',
                            'entity_type': 'property',
                            'description': f'PROV-O property: {prop_name}',
                            'namespace': 'prov'
                        },
                        'classes': 'property-node'
                    }
                    nodes.append(property_nodes[node_id])
                
                # Clean up
                os.unlink(temp_file)
                
                return jsonify({
                    'success': True,
                    'message': f'Extracted {len(nodes)} nodes and {len(edges)} hierarchical relationships',
                    'visualization': {
                        'nodes': nodes,
                        'edges': edges
                    },
                    'statistics': {
                        'total_nodes': len(nodes),
                        'total_edges': len(edges),
                        'classes': len(class_nodes),
                        'properties': len(property_nodes),
                        'hierarchical_relationships': len(edges)
                    }
                })
                
            except ImportError:
                return jsonify({
                    'success': False,
                    'error': 'owlready2 not available'
                }), 500
            except Exception as extraction_error:
                return jsonify({
                    'success': False,
                    'error': f'Hierarchy extraction failed: {str(extraction_error)}'
                }), 500
            
        except Exception as e:
            logger.error(f"Error in hierarchy visualization for {ontology_name}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/enhanced/validate/<ontology_id>')
    def enhanced_validate_ontology(ontology_id: str):
        """Enhanced validation with reasoning and consistency checking."""
        try:
            validation_result = enhanced_processor.validate_ontology_enhanced(ontology_id)
            
            return jsonify({
                'success': True,
                'validation': validation_result
            })
            
        except Exception as e:
            logger.error(f"Error in enhanced validation for {ontology_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/enhanced/search')
    def enhanced_search_entities():
        """Enhanced semantic search with reasoning integration."""
        try:
            # Get search parameters
            query = request.args.get('query', '').strip()
            ontology_id = request.args.get('ontology_id')
            entity_type = request.args.get('entity_type')
            include_reasoning = request.args.get('include_reasoning', 'true').lower() == 'true'
            limit = int(request.args.get('limit', 10))
            
            if not query:
                raise BadRequest("Query parameter is required")
            
            # Perform enhanced semantic search
            results = enhanced_processor.search_entities_enhanced(
                query, ontology_id, entity_type, include_reasoning, limit
            )
            
            # Add display information
            for result in results:
                result['display_name'] = EntityTypeMapper.get_display_name(result.get('entity_type', 'unknown'))
                result['css_class'] = EntityTypeMapper.get_css_class(result.get('entity_type', 'unknown'))
                result['icon'] = EntityTypeMapper.get_icon(result.get('entity_type', 'unknown'))
                result['color'] = EntityTypeMapper.get_entity_color(result.get('entity_type', 'unknown'), result.get('uri', ''))
            
            return jsonify({
                'success': True,
                'results': results,
                'query': query,
                'total_count': len(results),
                'reasoning_included': include_reasoning
            })
            
        except Exception as e:
            logger.error(f"Error in enhanced search: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/enhanced/entity/<ontology_id>/<path:entity_uri>')
    def enhanced_get_entity_data(ontology_id: str, entity_uri: str):
        """Get enhanced entity data with reasoning information."""
        try:
            include_reasoning = request.args.get('include_reasoning', 'true').lower() == 'true'
            
            # Get enhanced entity data
            entity_data = enhanced_processor.get_enhanced_entity_data(
                ontology_id, entity_uri, include_reasoning
            )
            
            if not entity_data:
                raise NotFound(f"Entity {entity_uri} not found in {ontology_id}")
            
            # Add display information
            if 'entity_type' in entity_data:
                entity_data['display_name'] = EntityTypeMapper.get_display_name(entity_data['entity_type'])
                entity_data['css_class'] = EntityTypeMapper.get_css_class(entity_data['entity_type'])
                entity_data['icon'] = EntityTypeMapper.get_icon(entity_data['entity_type'])
                entity_data['color'] = EntityTypeMapper.get_entity_color(entity_data['entity_type'], entity_uri)
                entity_data['is_bfo_aligned'] = EntityTypeMapper.is_bfo_aligned(entity_uri)
            
            return jsonify({
                'success': True,
                'entity': entity_data,
                'reasoning_included': include_reasoning
            })
            
        except Exception as e:
            logger.error(f"Error getting enhanced entity data for {entity_uri}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/enhanced/visualization/')
    @bp.route('/api/enhanced/visualization/<ontology_name>')  
    def enhanced_visualization_data(ontology_name: str = None):
        """Get enhanced visualization data optimized for Cytoscape.js with reasoning."""
        try:
            # Get query parameters
            include_reasoning = request.args.get('include_reasoning', 'true').lower() == 'true'
            layout_type = request.args.get('layout', 'hierarchical')
            entity_limit = int(request.args.get('limit', 1000))
            
            # If no ontology_name in URL, try to get it from query parameter or request
            if not ontology_name:
                ontology_name = request.args.get('ontology_name') or request.args.get('ontology_id')
                if not ontology_name:
                    return jsonify({'error': 'ontology_name parameter is required'}), 400
            
            # Check if we have cached visualization data from enhanced processing
            ontology = db.session.query(Ontology).filter_by(name=ontology_name).first()
            if not ontology:
                raise NotFound(f"Ontology {ontology_name} not found")
            
            # Get entities with enhanced metadata
            entities_query = db.session.query(OntologyEntity).filter_by(ontology_id=ontology.id)
            entities = entities_query.limit(entity_limit).all()
            
            # Build nodes for Cytoscape.js
            nodes = []
            edges = []
            
            # Create a set of all entity URIs for filtering edges
            entity_uris = {entity.uri for entity in entities}
            
            for entity in entities:
                # Create node
                node_data = {
                    'id': entity.uri,
                    'label': entity.label or entity.uri.split('#')[-1].split('/')[-1],
                    'type': entity.entity_type,
                    'uri': entity.uri,
                    'comment': entity.comment or '',
                }
                
                # Add reasoning information if available
                if include_reasoning and entity.properties:
                    reasoning_info = entity.properties.get('reasoning', {})
                    node_data.update({
                        'is_inferred': reasoning_info.get('is_inferred', False),
                        'consistency_status': reasoning_info.get('consistency_status', 'unknown'),
                        'has_inferred_relationships': len(reasoning_info.get('inferred_relationships', [])) > 0
                    })
                
                # Add display styling
                node_data['display_name'] = EntityTypeMapper.get_display_name(entity.entity_type)
                node_data['color'] = EntityTypeMapper.get_entity_color(entity.entity_type, entity.uri)
                
                nodes.append({
                    'data': node_data,
                    'classes': f"entity-node {entity.entity_type}" + (' inferred' if node_data.get('is_inferred') else ' explicit')
                })
                
                # Create edges for parent relationships - only if target exists in current ontology
                if entity.parent_uri and entity.parent_uri in entity_uris:
                    edge_id = f"{entity.uri}-subClassOf-{entity.parent_uri}"
                    edges.append({
                        'data': {
                            'id': edge_id,
                            'source': entity.uri,
                            'target': entity.parent_uri,
                            'type': 'subClassOf',
                            'is_inferred': node_data.get('is_inferred', False)
                        },
                        'classes': 'hierarchy-edge' + (' inferred' if node_data.get('is_inferred') else ' explicit')
                    })
            
            # Get layout configuration
            layout_options = {
                'hierarchical': {'name': 'dagre', 'rankDir': 'TB'},
                'circular': {'name': 'circle'},
                'force': {'name': 'cose', 'nodeRepulsion': 400000},
                'breadthfirst': {'name': 'breadthfirst', 'directed': True}
            }
            
            # Get style configuration
            style_options = [
                {
                    'selector': 'node',
                    'style': {
                        'label': 'data(label)',
                        'width': '60px',
                        'height': '60px',
                        'background-color': 'data(color)',
                        'border-width': '2px',
                        'border-color': '#fff',
                        'color': '#333',
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'font-size': '10px'
                    }
                },
                {
                    'selector': 'node.inferred',
                    'style': {
                        'border-style': 'dashed',
                        'border-color': '#7ED321'
                    }
                },
                {
                    'selector': 'edge',
                    'style': {
                        'width': '2px',
                        'line-color': '#999',
                        'target-arrow-color': '#999',
                        'target-arrow-shape': 'triangle',
                        'curve-style': 'bezier'
                    }
                },
                {
                    'selector': 'edge.inferred',
                    'style': {
                        'line-color': '#7ED321',
                        'target-arrow-color': '#7ED321',
                        'line-style': 'dashed'
                    }
                }
            ]
            
            return jsonify({
                'success': True,
                'visualization': {
                    'nodes': nodes,
                    'edges': edges,
                    'layout_options': layout_options.get(layout_type, layout_options['hierarchical']),
                    'style_options': style_options
                },
                'stats': {
                    'node_count': len(nodes),
                    'edge_count': len(edges),
                    'inferred_nodes': len([n for n in nodes if n['data'].get('is_inferred')]),
                    'inferred_edges': len([e for e in edges if e['data'].get('is_inferred')])
                },
                'ontology': ontology.to_dict()
            })
            
        except Exception as e:
            logger.error(f"Error generating enhanced visualization for {ontology_name}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @bp.route('/api/enhanced/capabilities')
    def enhanced_capabilities():
        """Get information about enhanced processor capabilities."""
        try:
            # Check processor capabilities
            has_reasoning = hasattr(enhanced_processor, 'owlready_importer') and enhanced_processor.owlready_importer is not None
            has_embeddings = enhanced_processor.embedding_model is not None
            
            return jsonify({
                'success': True,
                'capabilities': {
                    'reasoning': has_reasoning,
                    'embeddings': has_embeddings,
                    'consistency_checking': has_reasoning,
                    'semantic_search': has_embeddings,
                    'bfo_validation': True,
                    'visualization': True,
                    'enhanced_processing': True
                },
                'processor_info': {
                    'reasoning_available': has_reasoning,
                    'embeddings_available': has_embeddings,
                    'supported_reasoners': ['hermit', 'pellet'] if has_reasoning else [],
                    'supported_formats': ['turtle', 'xml', 'n3', 'nt']
                }
            })
            
        except Exception as e:
            logger.error(f"Error getting enhanced capabilities: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    return bp
