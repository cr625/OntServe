"""
Draft ontology management routes for OntServe web application.

Handles draft listing, creation, and deletion.
"""

import rdflib
from rdflib import RDF, RDFS, OWL

from flask import Blueprint, render_template, request, jsonify, current_app
from sqlalchemy import select, func

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from web.rdf_helpers import generate_rdf_from_concepts

draft_bp = Blueprint('draft', __name__)


@draft_bp.route('/drafts')
def drafts():
    """View all draft ontologies."""
    page = request.args.get('page', 1, type=int)
    per_page = 10

    stmt = select(OntologyVersion).where(
        OntologyVersion.is_draft == True
    ).order_by(OntologyVersion.created_at.desc())

    pagination = db.paginate(
        stmt,
        page=page,
        per_page=per_page,
        error_out=False
    )

    draft_data = []
    for version in pagination.items:
        ont = version.ontology

        count_stmt = select(func.count()).select_from(OntologyEntity).where(
            OntologyEntity.ontology_id == ont.id
        )
        entity_count = db.session.execute(count_stmt).scalar()
        draft_data.append({
            'ontology': ont,
            'version': version,
            'entity_count': entity_count
        })

    return render_template('drafts.html',
                         drafts=draft_data,
                         pagination=pagination)


@draft_bp.route('/editor/api/ontologies/<ontology_name>/draft', methods=['POST'])
def create_draft_ontology(ontology_name):
    """Create a new draft ontology from extracted concepts."""
    try:
        data = request.get_json()
        concepts = data.get('concepts', [])
        base_imports = data.get('base_imports', [])
        metadata = data.get('metadata', {})
        created_by = data.get('created_by', 'system')
        parent_ontology_name = data.get('parent_ontology', None)

        # Check if ontology already exists
        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.session.execute(stmt).scalar_one_or_none()

        if ontology:
            # Check if there's already a draft version
            stmt = select(OntologyVersion).where(
                OntologyVersion.ontology_id == ontology.id,
                OntologyVersion.is_draft == True
            )
            existing_draft = db.session.execute(stmt).scalar_one_or_none()

            if existing_draft:
                return jsonify({
                    'success': False,
                    'error': f'Draft version already exists for {ontology_name}'
                }), 409
        else:
            # Resolve parent ontology if specified
            parent_ontology_id = None
            if parent_ontology_name:
                stmt = select(Ontology).where(Ontology.name == parent_ontology_name)
                parent_ontology = db.session.execute(stmt).scalar_one_or_none()
                if parent_ontology:
                    parent_ontology_id = parent_ontology.id
                    current_app.logger.info(f"Creating derived ontology {ontology_name} with parent {parent_ontology_name}")
                else:
                    current_app.logger.warning(f"Parent ontology {parent_ontology_name} not found for {ontology_name}")

            # Create new ontology with parent relationship
            ontology = Ontology(
                name=ontology_name,
                base_uri=f'http://proethica.org/ontology/{ontology_name}',
                description=f'Extracted concepts ontology: {ontology_name}',
                is_base=False,
                is_editable=True,
                parent_ontology_id=parent_ontology_id,
                ontology_type='derived' if parent_ontology_id else 'base',
                meta_data=metadata
            )
            db.session.add(ontology)
            db.session.flush()

        # Generate RDF content from concepts
        rdf_content = generate_rdf_from_concepts(ontology_name, concepts, base_imports)

        # Create draft version
        version = OntologyVersion(
            ontology_id=ontology.id,
            version_number=1,
            version_tag='v1.0-draft',
            content=rdf_content,
            change_summary='Initial draft from concept extraction',
            created_by=created_by,
            is_current=True,
            is_draft=True,
            workflow_status='draft',
            meta_data=metadata
        )
        db.session.add(version)
        db.session.commit()

        # Parse RDF content and extract entities into ontology_entities table
        try:
            g = rdflib.Graph()
            g.parse(data=rdf_content, format='turtle')

            # Clear existing entities for this ontology (in case of recreate)
            stmt = select(OntologyEntity).where(OntologyEntity.ontology_id == ontology.id)
            entities_to_clear = db.session.execute(stmt).scalars().all()
            for entity in entities_to_clear:
                db.session.delete(entity)

            entity_counts = {'class': 0, 'property': 0, 'individual': 0}

            # Extract classes
            for cls in g.subjects(RDF.type, OWL.Class):
                label = next(g.objects(cls, RDFS.label), None)
                comment = next(g.objects(cls, RDFS.comment), None)
                subclass_of = list(g.objects(cls, RDFS.subClassOf))

                entity = OntologyEntity(
                    ontology_id=ontology.id,
                    entity_type='class',
                    uri=str(cls),
                    label=str(label) if label else None,
                    comment=str(comment) if comment else None,
                    parent_uri=str(subclass_of[0]) if subclass_of else None
                )
                db.session.add(entity)
                entity_counts['class'] += 1

            # Extract object properties
            for prop in g.subjects(RDF.type, OWL.ObjectProperty):
                label = next(g.objects(prop, RDFS.label), None)
                comment = next(g.objects(prop, RDFS.comment), None)
                domain = next(g.objects(prop, RDFS.domain), None)
                range_val = next(g.objects(prop, RDFS.range), None)

                entity = OntologyEntity(
                    ontology_id=ontology.id,
                    entity_type='property',
                    uri=str(prop),
                    label=str(label) if label else None,
                    comment=str(comment) if comment else None,
                    domain={'uri': str(domain)} if domain else None,
                    range={'uri': str(range_val)} if range_val else None
                )
                db.session.add(entity)
                entity_counts['property'] += 1

            # Extract datatype properties
            for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
                label = next(g.objects(prop, RDFS.label), None)
                comment = next(g.objects(prop, RDFS.comment), None)
                domain = next(g.objects(prop, RDFS.domain), None)
                range_val = next(g.objects(prop, RDFS.range), None)

                entity = OntologyEntity(
                    ontology_id=ontology.id,
                    entity_type='property',
                    uri=str(prop),
                    label=str(label) if label else None,
                    comment=str(comment) if comment else None,
                    domain={'uri': str(domain)} if domain else None,
                    range={'uri': str(range_val)} if range_val else None
                )
                db.session.add(entity)
                entity_counts['property'] += 1

            db.session.commit()

            current_app.logger.info(f"Extracted {entity_counts['class']} classes and {entity_counts['property']} properties for draft ontology {ontology_name}")

            return jsonify({
                'success': True,
                'ontology_name': ontology_name,
                'version_id': version.id,
                'version_number': version.version_number,
                'concepts_count': len(concepts),
                'entities_extracted': entity_counts,
                'message': f'Draft ontology created with {len(concepts)} concepts and {sum(entity_counts.values())} extracted entities'
            })

        except Exception as parse_error:
            current_app.logger.error(f"Error parsing RDF content for entity extraction: {parse_error}")
            return jsonify({
                'success': True,
                'ontology_name': ontology_name,
                'version_id': version.id,
                'version_number': version.version_number,
                'concepts_count': len(concepts),
                'message': f'Draft ontology created with {len(concepts)} concepts (entity extraction failed: {parse_error})'
            })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating draft ontology: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@draft_bp.route('/editor/api/ontologies/<ontology_name>/draft', methods=['DELETE'])
def delete_draft_ontology(ontology_name):
    """Delete draft ontology (replaces Clear Pending functionality)."""
    try:
        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.one_or_404(stmt)

        # Find all draft versions
        stmt = select(OntologyVersion).where(
            OntologyVersion.ontology_id == ontology.id,
            OntologyVersion.is_draft == True
        )
        draft_versions = db.session.execute(stmt).scalars().all()

        if not draft_versions:
            return jsonify({
                'success': False,
                'error': f'No draft versions found for {ontology_name}'
            }), 404

        # Delete all draft versions
        for version in draft_versions:
            db.session.delete(version)

        # Check if this ontology has any published versions
        stmt = select(func.count()).select_from(OntologyVersion).where(
            OntologyVersion.ontology_id == ontology.id,
            OntologyVersion.is_draft == False
        )
        published_versions = db.session.execute(stmt).scalar()

        # If no published versions, delete the entire ontology
        if published_versions == 0:
            stmt = select(OntologyEntity).where(OntologyEntity.ontology_id == ontology.id)
            entities_to_delete = db.session.execute(stmt).scalars().all()
            for entity in entities_to_delete:
                db.session.delete(entity)
            db.session.delete(ontology)

        db.session.commit()

        return jsonify({
            'success': True,
            'ontology_name': ontology_name,
            'draft_versions_deleted': len(draft_versions),
            'ontology_deleted': published_versions == 0,
            'message': f'Deleted {len(draft_versions)} draft versions'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting draft ontology: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
