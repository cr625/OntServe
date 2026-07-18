"""
OntServe Editor Routes

Flask routes for the ontology editor web interface.
Provides API endpoints that replace Neo4j queries with pgvector semantic search.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from flask import Blueprint, request, jsonify, render_template, current_app, flash
from markupsafe import escape
from werkzeug.exceptions import BadRequest, NotFound
from sqlalchemy import select, func

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from storage.file_storage import FileStorage
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
    
    @bp.route('/')
    def index():
        """Main editor interface."""
        try:
            # Get list of available ontologies
            stmt = select(Ontology).order_by(Ontology.name)
            ontologies = db.session.execute(stmt).scalars().all()
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
            # Get ontology by name (ontology_id param is the name string like 'proethica-intermediate')
            stmt = select(Ontology).where(Ontology.name == ontology_id)
            ontology = db.session.execute(stmt).scalar_one_or_none()
            if not ontology:
                raise NotFound(f"Ontology {ontology_id} not found")

            # Get latest version
            stmt = select(OntologyVersion)\
                .where(OntologyVersion.ontology_id == ontology.id)\
                .order_by(OntologyVersion.created_at.desc())
            latest_version = db.session.execute(stmt).scalars().first()

            # Get version history
            stmt = select(OntologyVersion)\
                .where(OntologyVersion.ontology_id == ontology.id)\
                .order_by(OntologyVersion.created_at.desc())
            versions = db.session.execute(stmt).scalars().all()
            
            version_list = []
            for v in versions:
                version_list.append({
                    'version': v.version_number,
                    'created_at': v.created_at.isoformat(),
                    'created_by': v.created_by,
                    'commit_message': v.change_summary,
                    'triple_count': getattr(v, 'triple_count', None)
                })

            ontology_data = ontology.to_dict()
            ontology_data['versions'] = version_list
            ontology_data['latest_version'] = latest_version.version_number if latest_version else None
            
            # Get content from latest version
            content = latest_version.content if latest_version else ''

            return render_template('editor/edit.html',
                                 ontology=ontology_data,
                                 content=content,
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
            stmt = select(Ontology).where(Ontology.name == ontology_id)
            ontology = db.session.execute(stmt).scalar_one_or_none()
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
            count_stmt = select(func.count()).select_from(OntologyVersion).where(
                OntologyVersion.ontology_id == ontology.id
            )
            version_count = db.session.execute(count_stmt).scalar()
            new_version = OntologyVersion(
                ontology_id=ontology.id,
                version_number=version_count + 1,
                content=content,
                change_summary=commit_message,
                created_at=datetime.now(timezone.utc),
                created_by=data.get('user', 'system')
            )

            ontology.updated_at = datetime.now(timezone.utc)
            
            # Store in file system
            storage_result = storage_backend.store(
                ontology_id,
                content,
                metadata={
                    'version': new_version.version_number,
                    'commit_message': commit_message,
                    'updated_at': datetime.now(timezone.utc).isoformat()
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
            stmt = select(Ontology).where(Ontology.name == ontology_id)
            ontology = db.session.execute(stmt).scalar_one_or_none()
            if not ontology:
                raise NotFound(f"Ontology {ontology_id} not found")

            # Get query parameters
            entity_type = request.args.get('type')
            search_term = request.args.get('search', '').strip()
            limit = int(request.args.get('limit', 100))

            # Get entities from database
            stmt = select(OntologyEntity).where(OntologyEntity.ontology_id == ontology.id)

            if entity_type:
                stmt = stmt.where(OntologyEntity.entity_type == entity_type)

            stmt = stmt.limit(limit)
            entities = db.session.execute(stmt).scalars().all()
            
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
            stmt = select(Ontology).where(Ontology.name == ontology_name)
            ontology = db.session.execute(stmt).scalar_one_or_none()
            if not ontology:
                logger.warning(f"Ontology {ontology_name} not found in database")
                return (f"<h1>Ontology Not Found</h1><p>Ontology '{escape(ontology_name)}' "
                        f"was not found in the database.</p>"), 404

            logger.info(f"Found ontology: {ontology.name}, ID: {ontology.id}")

            return render_template('editor/visualize.html',
                                 ontology=ontology,
                                 ontology_name=ontology_name,
                                 page_title=f"Visualize {ontology.name}")

        except Exception as e:
            logger.error(f"Error loading visualization for {ontology_name}: {e}", exc_info=True)
            return f"<h1>Error</h1><p>Error loading visualization: {escape(str(e))}</p>", 500
    
    @bp.route('/ontology/<ontology_id>/versions')
    def get_versions(ontology_id: str):
        """Get version history for an ontology."""
        try:
            # Get ontology
            stmt = select(Ontology).where(Ontology.name == ontology_id)
            ontology = db.session.execute(stmt).scalar_one_or_none()
            if not ontology:
                raise NotFound(f"Ontology {ontology_id} not found")

            # Get versions
            stmt = select(OntologyVersion)\
                .where(OntologyVersion.ontology_id == ontology.id)\
                .order_by(OntologyVersion.created_at.desc())
            versions = db.session.execute(stmt).scalars().all()
            
            version_list = []
            for v in versions:
                version_list.append({
                    'version': v.version_number,
                    'created_at': v.created_at.isoformat(),
                    'created_by': v.created_by,
                    'commit_message': v.change_summary,
                    'triple_count': getattr(v, 'triple_count', None),
                    'changes_summary': v.change_summary
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
            entity = db.session.get(OntologyEntity, entity_id)
            if not entity:
                raise NotFound(f"Entity {entity_id} not found")

            # Get ontology information
            ontology = db.session.get(Ontology, entity.ontology_id)
            
            # Build entity details
            entity_dict = entity.to_dict()
            entity_dict['display_name'] = EntityTypeMapper.get_display_name(entity.entity_type)
            entity_dict['css_class'] = EntityTypeMapper.get_css_class(entity.entity_type)
            entity_dict['icon'] = EntityTypeMapper.get_icon(entity.entity_type)
            entity_dict['color'] = EntityTypeMapper.get_entity_color(entity.entity_type, entity.uri)
            entity_dict['is_bfo_aligned'] = EntityTypeMapper.is_bfo_aligned(entity.uri)
            entity_dict['ontology'] = ontology.to_dict() if ontology else None

            # Get related entities (children and parents)
            stmt = select(OntologyEntity).where(
                OntologyEntity.ontology_id == entity.ontology_id,
                OntologyEntity.parent_uri == entity.uri
            )
            children = db.session.execute(stmt).scalars().all()

            entity_dict['children'] = [child.to_dict() for child in children]

            # Get parent if exists
            if entity.parent_uri:
                stmt = select(OntologyEntity).where(
                    OntologyEntity.ontology_id == entity.ontology_id,
                    OntologyEntity.uri == entity.parent_uri
                )
                parent = db.session.execute(stmt).scalar_one_or_none()
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
            entity = db.session.get(OntologyEntity, entity_id)
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
            stmt = select(Ontology).where(Ontology.name == ontology_name)
            ontology = db.session.execute(stmt).scalar_one_or_none()
            if not ontology:
                return jsonify({
                    'success': False,
                    'error': f'Ontology {ontology_name} not found'
                }), 404

            # Get all entities for this ontology
            stmt = select(OntologyEntity).where(OntologyEntity.ontology_id == ontology.id)
            entities = db.session.execute(stmt).scalars().all()
            
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
        from .visualization_service import build_basic_visualization

        result = build_basic_visualization(ontology_name)
        status = 200 if result.get('success') else 404
        return jsonify(result), status

    @bp.route('/api/simple/reasoning/<ontology_name>', methods=['POST'])
    def simple_reasoning(ontology_name: str):
        """Simple reasoning endpoint using owlready2 directly."""
        from .reasoning_service import ReasoningRequest, execute_reasoning

        data = request.get_json() or {}
        req = ReasoningRequest(
            ontology_name=ontology_name,
            reasoner_type=data.get('reasoner_type', 'pellet'),
            save_as_version=data.get('save_as_version', False),
            auto_promote_significant=data.get('auto_promote_significant', False),
        )
        result = execute_reasoning(req)
        status = 200 if result.success else 500
        return jsonify(result.to_response_dict()), status
    
    @bp.route('/api/hierarchy/visualization/<ontology_name>', methods=['GET'])
    def hierarchy_visualization(ontology_name: str):
        """Get hierarchical visualization data extracted from ontology content."""
        from .visualization_service import build_hierarchy_visualization

        result = build_hierarchy_visualization(ontology_name)
        status = 200 if result.get('success') else (404 if 'not found' in result.get('error', '') else 500)
        return jsonify(result), status
    
    return bp
