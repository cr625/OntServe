"""register_editor_routes."""
import logging
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from sqlalchemy import select, func
import rdflib

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from web.ontology_stats import build_stats_context
from web.entity_extraction import extract_entities_from_content


def register_editor_routes(bp):
    @bp.route('/ontology/<ontology_name>/edit')
    @login_required
    def edit_ontology(ontology_name):
        """Edit an ontology using ACE editor."""
        if not current_user.can_perform_action('edit'):
            flash('You do not have permission to edit ontologies', 'error')
            return redirect(url_for('ontology.ontology_detail_or_uri_resolution', ontology_name=ontology_name))
        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.one_or_404(stmt)

        # Get the content from file storage
        try:
            ont_data = current_app.ontology_manager.get_ontology(ontology_name)
            content = ont_data.get('content', '')
        except Exception as e:
            current_app.logger.warning(f"Failed to load from file storage, using DB content: {e}")
            content = ontology.current_content or ''

        # Get versions with proper formatting
        stmt = select(OntologyVersion).where(
            OntologyVersion.ontology_id == ontology.id
        ).order_by(OntologyVersion.created_at.desc())
        versions = db.session.execute(stmt).scalars().all()

        version_list = []
        for v in versions:
            version_list.append({
                'version': str(v.version_number),
                'created_at': v.created_at.isoformat() if v.created_at else '',
                'created_by': v.created_by or 'system',
                'commit_message': v.change_summary or '',
                'triple_count': 0
            })

        ontology_data = ontology.to_dict()
        ontology_data['versions'] = version_list
        ontology_data['latest_version'] = version_list[0]['version'] if version_list else None

        return render_template('editor/edit.html',
                             ontology=ontology_data,
                             content=content,
                             page_title=f"Edit {ontology.name}")


    @bp.route('/ontology/<ontology_name>/save', methods=['POST'])
    @login_required
    def save_ontology(ontology_name):
        """Save a new version of an ontology."""
        if not current_user.can_perform_action('edit'):
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.one_or_404(stmt)

        data = request.get_json()
        content = data.get('content', '')
        commit_message = data.get('commit_message', '')

        try:
            # Save to file storage
            result = current_app.ontology_manager.store_ontology(
                ontology_name,
                content,
                metadata={'commit_message': commit_message}
            )

            # Validate TTL parses correctly
            g = rdflib.Graph()
            g.parse(data=content, format='turtle')

            ontology.updated_at = datetime.now(timezone.utc)

            # Create version record
            count_stmt = select(func.count()).select_from(OntologyVersion).where(
                OntologyVersion.ontology_id == ontology.id
            )
            version_count = db.session.execute(count_stmt).scalar()
            version = OntologyVersion(
                ontology_id=ontology.id,
                version_number=version_count + 1,
                content=content,
                change_summary=commit_message,
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(version)
            db.session.commit()

            return jsonify({'success': True, 'version_id': version.id})

        except Exception as e:
            current_app.logger.error(f"Error saving ontology: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500


    @bp.route('/ontology/<ontology_name>/save-draft', methods=['POST'])
    @login_required
    def save_draft(ontology_name):
        """Save a draft of an ontology (no version created)."""
        return jsonify({'success': False, 'message': 'Draft saving not yet implemented'}), 501


    @bp.route('/validate', methods=['POST'])
    def validate_ontology():
        """Validate an ontology."""
        data = request.get_json()
        content = data.get('content', '')

        try:
            g = rdflib.Graph()
            g.parse(data=content, format='turtle')

            from rdflib import RDF, RDFS, OWL
            stats = {
                'triples': len(g),
                'classes': len(list(g.subjects(RDF.type, OWL.Class))),
                'properties': (
                    len(list(g.subjects(RDF.type, OWL.ObjectProperty))) +
                    len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))
                )
            }

            entities = {
                'classes': [],
                'properties': []
            }

            for s in list(g.subjects(RDF.type, OWL.Class))[:10]:
                label = next(g.objects(s, RDFS.label), None)
                entities['classes'].append({
                    'uri': str(s),
                    'label': str(label) if label else None
                })

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


    @bp.route('/editor/ontology/<ontology_name>/validate', methods=['POST'])
    def validate_ontology_editor(ontology_name):
        """Validate an ontology for the editor interface."""
        data = request.get_json()
        content = data.get('content', '')

        try:
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


    @bp.route('/editor/ontology/<ontology_name>/version/<version_id>')
    def get_editor_version(ontology_name, version_id):
        """Get a specific version of an ontology for the editor."""
        version = db.get_or_404(OntologyVersion, version_id)

        return jsonify({
            'success': True,
            'content': version.content,
            'version': version.version_number,
            'commit_message': version.change_summary,
            'created_at': version.created_at.isoformat() if version.created_at else None
        })


    @bp.route('/editor/ontology/<ontology_name>/save', methods=['POST'])
    @login_required
    def save_ontology_editor(ontology_name):
        """Save a new version of an ontology from the editor."""
        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.one_or_404(stmt)

        data = request.get_json()
        content = data.get('content', '')
        commit_message = data.get('commit_message', '')
        extract_entities = data.get('extract_entities', False)

        try:
            g = rdflib.Graph()
            g.parse(data=content, format='turtle')

            result = current_app.ontology_manager.store_ontology(
                ontology_name,
                content,
                metadata={'commit_message': commit_message}
            )

            ontology.updated_at = datetime.now(timezone.utc)

            count_stmt = select(func.count()).select_from(OntologyVersion).where(
                OntologyVersion.ontology_id == ontology.id
            )
            version_count = db.session.execute(count_stmt).scalar()
            version = OntologyVersion(
                ontology_id=ontology.id,
                version_number=version_count + 1,
                content=content,
                change_summary=commit_message,
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(version)
            db.session.commit()

            response_data = {
                'success': True,
                'version_id': version.id,
                'version': version.version_number
            }

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
            current_app.logger.error(f"Error saving ontology: {e}")
            return jsonify({
                'success': False,
                'error': str(e),
                'validation': {
                    'valid': False,
                    'errors': [str(e)]
                }
            }), 500


    @bp.route('/editor/api/extract-entities/<ontology_name>', methods=['POST'])
    def extract_entities_editor(ontology_name):
        """Extract entities from an ontology for the editor."""
        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.one_or_404(stmt)

        try:
            content = ontology.current_content
            if not content:
                ont_data = current_app.ontology_manager.get_ontology(ontology_name)
                content = ont_data.get('content', ontology.content)

            if not content:
                return jsonify({
                    'success': False,
                    'error': 'No content available for entity extraction'
                }), 400

            entity_counts = extract_entities_from_content(ontology, content)

            db.session.commit()

            total_entities = sum(entity_counts.values())

            return jsonify({
                'success': True,
                'total_entities': total_entities,
                'entity_counts': entity_counts,
                'message': f'Successfully extracted {total_entities} entities'
            })

        except Exception as e:
            current_app.logger.error(f"Error extracting entities: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
