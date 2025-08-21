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
    
    @bp.route('/ontology/<ontology_id>/visualize')
    def visualize_ontology(ontology_id: str):
        """Visualization interface for ontology."""
        try:
            # Get ontology
            ontology = db.session.query(Ontology).filter_by(ontology_id=ontology_id).first()
            if not ontology:
                raise NotFound(f"Ontology {ontology_id} not found")
            
            return render_template('editor/visualize.html',
                                 ontology=ontology.to_dict(),
                                 ontology_id=ontology_id,
                                 page_title=f"Visualize {ontology.name}")
                                 
        except Exception as e:
            logger.error(f"Error loading visualization for {ontology_id}: {e}")
            flash(f"Error loading visualization: {str(e)}", 'error')
            return render_template('error.html', error=str(e)), 500
    
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
            
            # Process with enhanced processor
            result = enhanced_processor.process_ontology(ontology_id, options)
            
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
    
    @bp.route('/api/enhanced/visualization/<ontology_id>')
    def enhanced_visualization_data(ontology_id: str):
        """Get enhanced visualization data optimized for Cytoscape.js with reasoning."""
        try:
            # Get query parameters
            include_reasoning = request.args.get('include_reasoning', 'true').lower() == 'true'
            layout_type = request.args.get('layout', 'hierarchical')
            entity_limit = int(request.args.get('limit', 1000))
            
            # Check if we have cached visualization data from enhanced processing
            ontology = db.session.query(Ontology).filter_by(ontology_id=ontology_id).first()
            if not ontology:
                raise NotFound(f"Ontology {ontology_id} not found")
            
            # Get entities with enhanced metadata
            entities_query = db.session.query(OntologyEntity).filter_by(ontology_id=ontology.id)
            entities = entities_query.limit(entity_limit).all()
            
            # Build nodes for Cytoscape.js
            nodes = []
            edges = []
            
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
                
                # Create edges for parent relationships
                if entity.parent_uri:
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
            logger.error(f"Error generating enhanced visualization for {ontology_id}: {e}")
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
