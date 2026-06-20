"""register_manage_routes."""
import logging
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from sqlalchemy import select, func
import rdflib

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from web.ontology_stats import build_stats_context
from web.entity_extraction import extract_entities_from_content


def register_manage_routes(bp):
    @bp.route('/ontology/<ontology_name>', methods=['DELETE'])
    @login_required
    def delete_ontology(ontology_name):
        """Delete an ontology and all its related data."""
        if not current_user.can_perform_action('delete'):
            return jsonify({
                'success': False,
                'error': 'You do not have permission to delete ontologies'
            }), 403

        try:
            stmt = select(Ontology).where(Ontology.name == ontology_name)
            ontology = db.one_or_404(stmt)

            current_app.logger.info(f"Admin {current_user.username} is deleting ontology: {ontology_name}")

            # Count what we're deleting for logging
            stmt = select(func.count()).select_from(OntologyEntity).where(
                OntologyEntity.ontology_id == ontology.id
            )
            entity_count = db.session.execute(stmt).scalar()

            stmt = select(func.count()).select_from(OntologyVersion).where(
                OntologyVersion.ontology_id == ontology.id
            )
            version_count = db.session.execute(stmt).scalar()

            # Delete in proper order to avoid foreign key constraints

            # 1. Delete all entities
            stmt = select(OntologyEntity).where(OntologyEntity.ontology_id == ontology.id)
            entities_to_delete = db.session.execute(stmt).scalars().all()
            for entity in entities_to_delete:
                db.session.delete(entity)

            # 2. Delete all versions
            stmt = select(OntologyVersion).where(OntologyVersion.ontology_id == ontology.id)
            versions_to_delete = db.session.execute(stmt).scalars().all()
            for version in versions_to_delete:
                db.session.delete(version)

            # 3. Clean up file storage if using file backend
            try:
                current_app.ontology_manager.delete_ontology(ontology_name)
            except Exception as storage_error:
                current_app.logger.warning(f"File storage cleanup failed for {ontology_name}: {storage_error}")

            # 4. Delete the ontology itself
            ontology_id = ontology.id
            db.session.delete(ontology)

            # Commit all changes
            db.session.commit()

            current_app.logger.info(f"Successfully deleted ontology {ontology_name} (ID: {ontology_id}) with {entity_count} entities and {version_count} versions")

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
            current_app.logger.error(f"Error deleting ontology {ontology_name}: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500


    @bp.route('/import', methods=['GET', 'POST'])
    @login_required
    def import_ontology():
        """Import a new ontology from URL or file upload."""
        if not current_user.can_perform_action('import'):
            flash('You do not have permission to import ontologies', 'error')
            return redirect(url_for('main.index'))

        if request.method == 'POST':
            from web.services.ontology_import import ImportRequest, execute_import

            # Parse request into service input
            uploaded_file = request.files.get('ontology_file')
            file_content = None
            filename = None
            if uploaded_file and uploaded_file.filename:
                file_content = uploaded_file.read().decode('utf-8')
                filename = uploaded_file.filename

            req = ImportRequest(
                source_type=request.form.get('source_type', 'url'),
                name=request.form.get('name'),
                description=request.form.get('description'),
                format_hint=request.form.get('format', ''),
                use_reasoning=request.form.get('use_reasoning') == 'on',
                reasoner_type=request.form.get('reasoner_type', 'pellet'),
                source_url=request.form.get('source_url'),
                file_content=file_content,
                filename=filename,
            )

            try:
                result = execute_import(req)
                if result.success:
                    flash(result.message, 'success')
                    return redirect(url_for(
                        'ontology.ontology_detail_or_uri_resolution',
                        ontology_name=result.redirect_name,
                    ))
                elif result.redirect_name:
                    flash(result.message, 'warning')
                    return redirect(url_for(
                        'ontology.ontology_detail_or_uri_resolution',
                        ontology_name=result.redirect_name,
                    ))
                else:
                    flash(result.message, 'error')
            except ValueError as e:
                flash(str(e), 'error')
            except Exception as e:
                flash(f"Error importing ontology: {e}", 'error')
                current_app.logger.error("Import error: %s", e, exc_info=True)

        return render_template('import.html')
