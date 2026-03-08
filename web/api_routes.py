"""
JSON API routes for OntServe web application.

Provides REST API endpoints for ontology and version management.
"""

from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import select, func

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from web.entity_extraction import extract_entities_from_content

api_bp = Blueprint('api', __name__)


@api_bp.route('/api/versions/<int:version_id>')
def get_version_api(version_id):
    """Get version details via API."""
    version = db.get_or_404(OntologyVersion, version_id)
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


@api_bp.route('/api/versions/<int:version_id>/make-current', methods=['POST'])
@login_required
def make_version_current(version_id):
    """Make a version the current version."""
    try:
        version = db.get_or_404(OntologyVersion, version_id)
        ontology = version.ontology

        # Set all versions to not current
        stmt = select(OntologyVersion).where(
            OntologyVersion.ontology_id == ontology.id
        )
        versions_to_update = db.session.execute(stmt).scalars().all()
        for v in versions_to_update:
            v.is_current = False

        # Make this version current
        version.is_current = True
        version.is_draft = False
        version.workflow_status = 'published'

        # Re-extract entities from the new current version content
        entities_updated = False
        try:
            entity_counts = extract_entities_from_content(ontology, version.content)
            total_entities = sum(entity_counts.values())
            entities_updated = True
            current_app.logger.info(f"Re-extracted {total_entities} entities for ontology {ontology.name} version {version.version_number}")
        except Exception as e:
            current_app.logger.warning(f"Failed to re-extract entities when making version current: {e}")

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


@api_bp.route('/api/ontologies')
def api_ontologies():
    """API endpoint to list ontologies."""
    stmt = select(Ontology)
    ontologies = db.session.execute(stmt).scalars().all()
    return jsonify([ont.to_dict() for ont in ontologies])


@api_bp.route('/api/ontology/<ontology_name>')
def api_ontology_detail(ontology_name):
    """API endpoint for ontology details."""
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.one_or_404(stmt)
    data = ontology.to_dict()

    # Add entity counts
    stmt = select(func.count()).select_from(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        OntologyEntity.entity_type == 'class'
    )
    class_count = db.session.execute(stmt).scalar()

    stmt = select(func.count()).select_from(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        OntologyEntity.entity_type == 'property'
    )
    property_count = db.session.execute(stmt).scalar()

    stmt = select(func.count()).select_from(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        OntologyEntity.entity_type == 'individual'
    )
    individual_count = db.session.execute(stmt).scalar()

    data['entity_counts'] = {
        'classes': class_count,
        'properties': property_count,
        'individuals': individual_count
    }

    return jsonify(data)


@api_bp.route('/api/ontology/<ontology_name>/metadata', methods=['PUT'])
@login_required
def update_ontology_metadata(ontology_name):
    """Update ontology metadata (name, description, etc.)."""
    if not current_user.can_perform_action('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.one_or_404(stmt)

    try:
        data = request.get_json()
        old_name = ontology.name

        # Validate new name if changed
        new_name = data.get('name', ontology.name)
        if new_name != old_name:
            check_stmt = select(Ontology).where(Ontology.name == new_name)
            existing = db.session.execute(check_stmt).scalar_one_or_none()
            if existing:
                return jsonify({
                    'success': False,
                    'error': f'An ontology with name "{new_name}" already exists'
                }), 409

        # Update ontology metadata
        ontology.name = new_name
        ontology.base_uri = data.get('base_uri', ontology.base_uri)
        ontology.description = data.get('description', ontology.description)
        ontology.ontology_type = data.get('ontology_type', ontology.ontology_type)
        ontology.is_editable = data.get('is_editable', ontology.is_editable)
        ontology.is_base = data.get('is_base', ontology.is_base)
        ontology.updated_at = datetime.now(timezone.utc)

        if not ontology.meta_data:
            ontology.meta_data = {}
        ontology.meta_data.update({
            'last_metadata_update': datetime.now(timezone.utc).isoformat(),
            'updated_by': current_user.username
        })

        db.session.commit()

        current_app.logger.info(f"Updated ontology metadata for {old_name} -> {new_name} by {current_user.username}")

        return jsonify({
            'success': True,
            'message': 'Ontology metadata updated successfully',
            'name_changed': old_name != new_name,
            'old_name': old_name,
            'new_name': new_name
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating ontology metadata: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/editor/api/ontologies/<ontology_name>/entities')
def api_ontology_entities(ontology_name):
    """API endpoint for ProEthica integration - get entities for an ontology."""
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.one_or_404(stmt)

    stmt = select(OntologyEntity).where(OntologyEntity.ontology_id == ontology.id)
    entities = db.session.execute(stmt).scalars().all()

    # Organize entities by category for ProEthica format
    entities_by_category = {}

    for entity in entities:
        category = entity.entity_type
        if category not in entities_by_category:
            entities_by_category[category] = []

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

        if category == 'role':
            entity_data["capabilities"] = []

        entities_by_category[category].append(entity_data)

    return jsonify({
        "entities": entities_by_category,
        "is_mock": False,
        "source": "ontserve",
        "total_entities": len(entities),
        "ontology_name": ontology_name
    })
