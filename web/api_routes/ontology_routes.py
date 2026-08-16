"""Ontology listing, detail, and metadata CRUD."""
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


def register_ontology(bp):
    @bp.route('/api/ontologies')
    def api_ontologies():
        """API endpoint to list ontologies."""
        stmt = select(Ontology)
        ontologies = db.session.execute(stmt).scalars().all()
        return jsonify([ont.to_dict() for ont in ontologies])


    @bp.route('/api/ontology/<ontology_name>')
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


    @bp.route('/api/ontology/<ontology_name>/metadata', methods=['PUT'])
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
            ontology.source_system = data.get('source_system', ontology.source_system)
            ontology.is_editable = data.get('is_editable', ontology.is_editable)
            ontology.is_base = data.get('is_base', ontology.is_base)
            ontology.updated_at = datetime.now(timezone.utc)

            # Reassign the whole dict (db.JSON is not mutation-tracked, so an
            # in-place .update() would not persist).
            md = dict(ontology.meta_data or {})
            if 'is_stub' in data:
                md['stub'] = bool(data.get('is_stub'))
            # Category / subcategory: explicit values live in metadata; blank clears
            # the key so the rule-based default applies again.
            for key in ('category', 'subcategory'):
                if key in data:
                    value = (data.get(key) or '').strip()
                    if value:
                        md[key] = value
                    else:
                        md.pop(key, None)
            md['last_metadata_update'] = datetime.now(timezone.utc).isoformat()
            md['updated_by'] = current_user.username
            ontology.meta_data = md

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
