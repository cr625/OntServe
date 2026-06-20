"""Version detail, make-current, tagging, and history."""
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
from web.api_routes.helpers import (
    _compute_divergence,
)


def register_versioning(bp):
    @bp.route('/api/versions/<int:version_id>')
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


    @bp.route('/api/versions/<int:version_id>/make-current', methods=['POST'])
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
    @bp.route('/api/ontology/<ontology_name>/tag-version', methods=['POST'])
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


    @bp.route('/api/ontology/<ontology_name>/version-history')
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
