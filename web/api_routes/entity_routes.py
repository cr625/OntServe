"""Entity API integration, hash-check, and update."""
import hashlib
import logging

import rdflib
from datetime import datetime, timezone
from rdflib import RDF, OWL, RDFS
from rdflib.namespace import SKOS

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import select, func

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from web.entity_extraction import extract_entities_from_content

logger = logging.getLogger(__name__)


def register_entities(bp):
    @bp.route('/editor/api/ontologies/<ontology_name>/entities')
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
    @bp.route('/api/entity-hash-check', methods=['POST'])
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


    @bp.route('/api/entity/<int:entity_id>', methods=['PUT'])
    @login_required
    def update_entity(entity_id):
        """Update entity label and/or comment. Recomputes content hash."""
        entity = db.get_or_404(OntologyEntity, entity_id)

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        old_hash = entity.content_hash

        if 'label' in data:
            entity.label = data['label'] or None
        if 'comment' in data:
            entity.comment = data['comment'] or None

        entity.content_hash = OntologyEntity.compute_content_hash(
            entity.uri, entity.label, entity.comment
        )
        entity.updated_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
            current_app.logger.info(
                f"Entity {entity.uri} updated by {current_user.username}: "
                f"hash {old_hash[:8] if old_hash else 'none'}... -> {entity.content_hash[:8]}..."
            )
            return jsonify({
                'success': True,
                'content_hash': entity.content_hash,
                'old_hash': old_hash,
                'hash_changed': old_hash != entity.content_hash
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
