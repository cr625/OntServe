"""
JSON API routes for OntServe web application.

Provides REST API endpoints for ontology and version management.
"""

import hashlib
import rdflib
from datetime import datetime, timezone
from rdflib import RDF, OWL, RDFS
from rdflib.namespace import SKOS

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


# ===== Version Tagging API =====


@api_bp.route('/api/ontology/<ontology_name>/tag-version', methods=['POST'])
@login_required
def tag_version(ontology_name):
    """Tag a new manual version release for an ontology.

    Creates a snapshot of current TTL content as a tagged release and
    computes divergence percentage against the previous tagged release.
    """
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.session.execute(stmt).scalar_one_or_none()
    if not ontology:
        return jsonify({'success': False, 'error': f'Ontology {ontology_name} not found'}), 404

    data = request.get_json() or {}
    version_tag = data.get('version_tag', '').strip()
    change_summary = data.get('change_summary', '').strip()

    if not version_tag:
        return jsonify({'success': False, 'error': 'version_tag is required'}), 400

    try:
        # Get current version content
        current_version = ontology.current_version
        if not current_version:
            return jsonify({'success': False, 'error': 'No current version found'}), 404

        # Find previous tagged release for this ontology
        prev_tag_stmt = (
            select(OntologyVersion)
            .where(
                OntologyVersion.ontology_id == ontology.id,
                OntologyVersion.is_tagged_release == True
            )
            .order_by(OntologyVersion.version_number.desc())
            .limit(1)
        )
        prev_tagged = db.session.execute(prev_tag_stmt).scalar_one_or_none()

        # Compute divergence against previous tagged version
        divergence_pct = None
        if prev_tagged:
            divergence_pct = _compute_divergence(prev_tagged.content, current_version.content)

        # Create new version record as tagged release
        count_stmt = select(func.count()).select_from(OntologyVersion).where(
            OntologyVersion.ontology_id == ontology.id
        )
        version_count = db.session.execute(count_stmt).scalar()

        content_hash = hashlib.sha256(current_version.content.encode('utf-8')).hexdigest()

        new_version = OntologyVersion(
            ontology_id=ontology.id,
            version_number=version_count + 1,
            version_tag=version_tag,
            content=current_version.content,
            content_hash=content_hash,
            change_summary=change_summary or f'Tagged release {version_tag}',
            created_by=current_user.username if current_user.is_authenticated else 'system',
            created_at=datetime.now(timezone.utc),
            is_current=True,
            is_draft=False,
            workflow_status='published',
            is_tagged_release=True,
            divergence_pct=divergence_pct,
            previous_tagged_version_id=prev_tagged.id if prev_tagged else None
        )

        # Unmark current version
        current_version.is_current = False

        db.session.add(new_version)
        db.session.commit()

        return jsonify({
            'success': True,
            'version_id': new_version.id,
            'version_number': new_version.version_number,
            'version_tag': version_tag,
            'divergence_pct': divergence_pct,
            'previous_tag': prev_tagged.version_tag if prev_tagged else None
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error tagging version for {ontology_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/api/ontology/<ontology_name>/version-history')
def version_history(ontology_name):
    """Get tagged release history for an ontology."""
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.session.execute(stmt).scalar_one_or_none()
    if not ontology:
        return jsonify({'success': False, 'error': f'Ontology {ontology_name} not found'}), 404

    tagged_only = request.args.get('tagged_only', 'true').lower() == 'true'

    version_stmt = select(OntologyVersion).where(
        OntologyVersion.ontology_id == ontology.id
    )
    if tagged_only:
        version_stmt = version_stmt.where(OntologyVersion.is_tagged_release == True)
    version_stmt = version_stmt.order_by(OntologyVersion.version_number.desc())

    versions = db.session.execute(version_stmt).scalars().all()

    # Also compute current divergence from latest tag
    current_divergence = None
    current_version = ontology.current_version
    if versions and current_version:
        latest_tag = versions[0]
        if latest_tag.id != current_version.id:
            current_divergence = _compute_divergence(latest_tag.content, current_version.content)

    return jsonify({
        'success': True,
        'ontology_name': ontology_name,
        'current_divergence_pct': current_divergence,
        'versions': [{
            'id': v.id,
            'version_number': v.version_number,
            'version_tag': v.version_tag,
            'change_summary': v.change_summary,
            'created_at': v.created_at.isoformat() if v.created_at else None,
            'created_by': v.created_by,
            'is_current': v.is_current,
            'is_tagged_release': v.is_tagged_release,
            'divergence_pct': v.divergence_pct
        } for v in versions]
    })


@api_bp.route('/api/entity-hash-check', methods=['POST'])
def entity_hash_check():
    """Batch check entity content hashes for Shepard's signal comparison.

    Accepts a list of entity URIs and returns their current content hashes
    from OntServe. ProEthica compares these against its stored commit-time
    hashes to determine which entities have changed.
    """
    data = request.get_json()
    if not data or 'entity_uris' not in data:
        return jsonify({'success': False, 'error': 'entity_uris required'}), 400

    entity_uris = data['entity_uris']
    if not entity_uris:
        return jsonify({'success': True, 'entities': {}})

    stmt = select(
        OntologyEntity.uri,
        OntologyEntity.content_hash,
        OntologyEntity.label,
        OntologyEntity.comment,
        OntologyEntity.updated_at
    ).where(OntologyEntity.uri.in_(entity_uris))

    rows = db.session.execute(stmt).all()

    entities = {}
    for uri, content_hash, label, comment, updated_at in rows:
        entities[uri] = {
            'content_hash': content_hash,
            'label': label,
            'comment': comment,
            'updated_at': updated_at.isoformat() if updated_at else None
        }

    return jsonify({
        'success': True,
        'entities': entities,
        'checked_count': len(entities),
        'missing_count': len(entity_uris) - len(entities)
    })


def _compute_divergence(old_ttl_content: str, new_ttl_content: str) -> float:
    """Compute entity-level divergence between two TTL content strings.

    Returns percentage of entities that differ (added, removed, or modified)
    relative to the old version's entity count.
    """
    old_entities = _extract_entity_hashes(old_ttl_content)
    new_entities = _extract_entity_hashes(new_ttl_content)

    if not old_entities:
        return 100.0 if new_entities else 0.0

    old_uris = set(old_entities.keys())
    new_uris = set(new_entities.keys())

    added = new_uris - old_uris
    removed = old_uris - new_uris
    common = old_uris & new_uris
    modified = {uri for uri in common if old_entities[uri] != new_entities[uri]}

    total_changes = len(added) + len(removed) + len(modified)
    return round(total_changes / len(old_entities) * 100, 1)


def _extract_entity_hashes(ttl_content: str) -> dict:
    """Parse TTL content and return {uri: content_hash} for all entities."""
    g = rdflib.Graph()
    try:
        g.parse(data=ttl_content, format='turtle')
    except Exception:
        return {}

    entities = {}
    for entity_type in [OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.NamedIndividual]:
        for uri in g.subjects(RDF.type, entity_type):
            uri_str = str(uri)
            if not uri_str.startswith('http'):
                continue
            label = next(g.objects(uri, RDFS.label), None)
            comment = next(g.objects(uri, RDFS.comment), None)
            if comment is None:
                comment = next(g.objects(uri, SKOS.definition), None)
            label_str = str(label) if label else ''
            comment_str = str(comment) if comment else ''
            raw = f"{uri_str}|{label_str}|{comment_str}"
            entities[uri_str] = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    return entities
