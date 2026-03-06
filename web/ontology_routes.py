"""
Ontology CRUD routes for OntServe web application.

Handles ontology detail view, content negotiation, format conversion,
import, edit, save, validation, versions, and settings.
"""

import os
import re
import logging
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from sqlalchemy import select, func
import rdflib

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from web.ontology_stats import build_stats_context
from web.entity_extraction import extract_entities_from_content

ontology_bp = Blueprint('ontology', __name__)


@ontology_bp.route('/ontology/<ontology_name>')
def ontology_detail_or_uri_resolution(ontology_name):
    """
    Unified endpoint for ontology detail view and URI resolution.

    - Browser requests (Accept: text/html) -> Detail page
    - Semantic web clients (Accept: text/turtle, etc.) -> Ontology content
    """
    # Check Accept header to determine response type
    accept_header = request.headers.get('Accept', '')
    user_agent = request.headers.get('User-Agent', '')

    # Determine if this is a semantic web client request
    semantic_formats = [
        'text/turtle', 'application/rdf+xml', 'application/ld+json',
        'application/n-triples', 'text/n3', 'application/rdf+json'
    ]

    is_semantic_request = any(fmt in accept_header for fmt in semantic_formats)
    is_browser = 'Mozilla' in user_agent and 'text/html' in accept_header and not is_semantic_request

    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.one_or_404(stmt)

    # Handle semantic web client requests (content negotiation)
    if is_semantic_request or (not is_browser and not 'text/html' in accept_header):
        current_app.logger.info(f"URI resolution request for {ontology_name}: Accept={accept_header}")

        # Check if merged ontology is requested
        include_derived = request.args.get('include_derived', 'false').lower() == 'true'
        include_drafts = request.args.get('include_drafts', 'false').lower() == 'true'

        if include_derived and ontology.has_children:
            try:
                # Use merger service to get combined ontology
                merged_content, merge_metadata = current_app.ontology_merger.merge_ontology_with_children(
                    ontology, include_drafts=include_drafts
                )
                content = merged_content

                current_app.logger.info(f"Serving merged ontology {ontology_name} with {len(merge_metadata['merged_children'])} children")
            except Exception as e:
                current_app.logger.error(f"Failed to merge ontology {ontology_name}: {e}")
                # Fallback to base ontology only
                content = ontology.current_content
        else:
            content = ontology.current_content

        if content is None:
            return jsonify({
                'error': 'No content available for this ontology',
                'ontology': ontology_name,
                'uri': ontology.base_uri
            }), 404

        # Determine response format based on Accept header
        if 'application/rdf+xml' in accept_header or 'application/xml' in accept_header:
            try:
                from rdflib import Graph
                g = Graph()
                g.parse(data=content, format='turtle')
                rdf_xml_content = g.serialize(format='xml')

                response = current_app.response_class(
                    rdf_xml_content,
                    mimetype='application/rdf+xml',
                    headers={
                        'Content-Disposition': f'inline; filename="{ontology_name}.rdf"',
                        'Link': f'<{ontology.base_uri}>; rel="canonical"',
                        'Access-Control-Allow-Origin': '*'
                    }
                )
                current_app.logger.info(f"Served ontology {ontology_name} as RDF/XML")
                return response
            except Exception as e:
                current_app.logger.error(f"Error converting to RDF/XML: {e}")

        elif 'application/ld+json' in accept_header or 'application/json' in accept_header:
            try:
                from rdflib import Graph
                g = Graph()
                g.parse(data=content, format='turtle')
                jsonld_content = g.serialize(format='json-ld')

                response = current_app.response_class(
                    jsonld_content,
                    mimetype='application/ld+json',
                    headers={
                        'Content-Disposition': f'inline; filename="{ontology_name}.jsonld"',
                        'Link': f'<{ontology.base_uri}>; rel="canonical"',
                        'Access-Control-Allow-Origin': '*'
                    }
                )
                current_app.logger.info(f"Served ontology {ontology_name} as JSON-LD")
                return response
            except Exception as e:
                current_app.logger.error(f"Error converting to JSON-LD: {e}")

        elif 'application/n-triples' in accept_header:
            try:
                from rdflib import Graph
                g = Graph()
                g.parse(data=content, format='turtle')
                nt_content = g.serialize(format='nt')

                response = current_app.response_class(
                    nt_content,
                    mimetype='application/n-triples',
                    headers={
                        'Content-Disposition': f'inline; filename="{ontology_name}.nt"',
                        'Link': f'<{ontology.base_uri}>; rel="canonical"',
                        'Access-Control-Allow-Origin': '*'
                    }
                )
                current_app.logger.info(f"Served ontology {ontology_name} as N-Triples")
                return response
            except Exception as e:
                current_app.logger.error(f"Error converting to N-Triples: {e}")

        # Default to Turtle format for semantic web clients
        response = current_app.response_class(
            content,
            mimetype='text/turtle',
            headers={
                'Content-Disposition': f'inline; filename="{ontology_name}.ttl"',
                'Link': f'<{ontology.base_uri}>; rel="canonical"',
                'Access-Control-Allow-Origin': '*',
                'Vary': 'Accept'
            }
        )

        current_app.logger.info(f"Served ontology {ontology_name} as Turtle to semantic web client")
        return response

    # Browser request - show detail page
    current_app.logger.info(f"Browser request for {ontology_name}, showing detail page")

    # Get all entities for this ontology
    stmt = select(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id
    )
    all_entities = db.session.execute(stmt).scalars().all()

    # Check if user explicitly requested standard view
    view_mode = request.args.get('view', 'auto')

    # Check if this is a case ontology (use case view by default for cases)
    from web.case_display import is_case_ontology, organize_entities_for_case, get_domain_from_ontology

    if view_mode != 'standard' and is_case_ontology(ontology_name, all_entities):
        # Use case view
        current_app.logger.info(f"Using case view for {ontology_name}")
        domain = get_domain_from_ontology(ontology_name)
        case_data = organize_entities_for_case(all_entities, domain)

        return render_template('ontology_case.html',
                             ontology=ontology,
                             case_sections=case_data['sections'],
                             stats=case_data['stats'])

    # Standard ontology view - group entities by type
    classes = [e for e in all_entities if e.entity_type == 'class']
    properties = [e for e in all_entities if e.entity_type == 'property']
    individuals = [e for e in all_entities if e.entity_type == 'individual']

    entities = {
        'classes': classes,
        'properties': properties,
        'individuals': individuals
    }

    # Count relationship instances
    stmt = select(func.count()).select_from(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        OntologyEntity.entity_type == 'class',
        OntologyEntity.parent_uri.isnot(None)
    )
    hierarchical_count = db.session.execute(stmt).scalar()

    stmt = select(func.count()).select_from(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        OntologyEntity.entity_type == 'property',
        OntologyEntity.domain.isnot(None)
    )
    domain_count = db.session.execute(stmt).scalar()

    stmt = select(func.count()).select_from(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        OntologyEntity.entity_type == 'property',
        OntologyEntity.range.isnot(None)
    )
    range_count = db.session.execute(stmt).scalar()

    relationships = {
        'hierarchical': hierarchical_count,
        'domain': domain_count,
        'range': range_count
    }
    relationships['total'] = relationships['hierarchical'] + relationships['domain'] + relationships['range']

    # Get versions
    stmt = select(OntologyVersion).where(
        OntologyVersion.ontology_id == ontology.id
    ).order_by(OntologyVersion.created_at.desc())
    versions = db.session.execute(stmt).scalars().all()

    # Build enhanced stats context with display_config support
    stats = build_stats_context(ontology, entities, relationships)

    return render_template('ontology_detail.html',
                         ontology=ontology,
                         entities=entities,
                         relationships=relationships,
                         versions=versions,
                         stats=stats)


@ontology_bp.route('/ontology/<ontology_name>/content')
def ontology_content(ontology_name):
    """Return raw TTL content of an ontology."""
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.one_or_404(stmt)
    content = ontology.current_content
    if content is None:
        return "No content available for this ontology", 404
    return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}


@ontology_bp.route('/ontology/<ontology_name>.<format_ext>')
def ontology_format_specific(ontology_name, format_ext):
    """
    Format-specific ontology endpoints for explicit format requests.

    Examples:
    - /ontology/w3c-prov-o.ttl -> Turtle
    - /ontology/w3c-prov-o.rdf -> RDF/XML
    - /ontology/w3c-prov-o.jsonld -> JSON-LD
    """
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.one_or_404(stmt)
    content = ontology.current_content

    if content is None:
        return jsonify({
            'error': 'No content available for this ontology',
            'ontology': ontology_name
        }), 404

    # Format mapping
    format_mapping = {
        'ttl': ('turtle', 'text/turtle'),
        'rdf': ('xml', 'application/rdf+xml'),
        'xml': ('xml', 'application/rdf+xml'),
        'jsonld': ('json-ld', 'application/ld+json'),
        'json': ('json-ld', 'application/ld+json'),
        'nt': ('nt', 'application/n-triples'),
        'n3': ('n3', 'text/n3')
    }

    if format_ext not in format_mapping:
        return jsonify({'error': f'Unsupported format: {format_ext}'}), 400

    rdf_format, mime_type = format_mapping[format_ext]

    try:
        from rdflib import Graph
        g = Graph()
        g.parse(data=content, format='turtle')

        if rdf_format == 'turtle':
            output_content = content  # Already in turtle
        else:
            output_content = g.serialize(format=rdf_format)

        response = current_app.response_class(
            output_content,
            mimetype=mime_type,
            headers={
                'Content-Disposition': f'attachment; filename="{ontology_name}.{format_ext}"',
                'Link': f'<{ontology.base_uri}>; rel="canonical"',
                'Access-Control-Allow-Origin': '*'
            }
        )

        current_app.logger.info(f"Served ontology {ontology_name} as {format_ext} format")
        return response

    except Exception as e:
        current_app.logger.error(f"Error converting ontology to {format_ext}: {e}")
        return jsonify({
            'error': f'Error converting to {format_ext} format',
            'details': str(e)
        }), 500


@ontology_bp.route('/ontology/<ontology_name>', methods=['DELETE'])
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


@ontology_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_ontology():
    """Import a new ontology from URL or file upload."""
    if not current_user.can_perform_action('import'):
        flash('You do not have permission to import ontologies', 'error')
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        source_type = request.form.get('source_type', 'url')
        name = request.form.get('name')
        description = request.form.get('description')
        format_hint = request.form.get('format', '')
        use_reasoning = request.form.get('use_reasoning') == 'on'
        reasoner_type = request.form.get('reasoner_type', 'pellet')

        source = None
        content = None
        filename = None

        try:
            # Handle different source types
            if source_type == 'url':
                source = request.form.get('source_url')
                if not source:
                    flash('Please provide a URL', 'error')
                    return render_template('import.html')

                # Fetch content from URL
                import requests
                current_app.logger.info(f"Fetching ontology from URL: {source}")

                headers = {
                    'Accept': 'text/turtle, application/rdf+xml, application/n-triples, application/ld+json, text/n3, */*',
                    'User-Agent': 'OntServe/1.0 (ontology importer)'
                }

                response = requests.get(source, headers=headers, timeout=30)
                response.raise_for_status()
                content = response.text
                filename = source.split('/')[-1] or 'ontology'

            elif source_type == 'upload':
                uploaded_file = request.files.get('ontology_file')
                if not uploaded_file or uploaded_file.filename == '':
                    flash('Please select a file to upload', 'error')
                    return render_template('import.html')

                # Read file content
                content = uploaded_file.read().decode('utf-8')
                filename = uploaded_file.filename
                source = f"uploaded://{filename}"
                current_app.logger.info(f"Processing uploaded file: {filename}")
            else:
                flash('Invalid source type', 'error')
                return render_template('import.html')

            # Auto-detect format if not specified
            if not format_hint:
                if filename:
                    if filename.endswith('.ttl'):
                        format_hint = 'turtle'
                    elif filename.endswith('.rdf') or filename.endswith('.xml') or filename.endswith('.owl'):
                        format_hint = 'xml'
                    elif filename.endswith('.n3'):
                        format_hint = 'n3'
                    elif filename.endswith('.jsonld') or filename.endswith('.json'):
                        format_hint = 'json-ld'
                    elif filename.endswith('.nt'):
                        format_hint = 'nt'

                # Content-based detection if still no format
                if not format_hint:
                    if '@prefix' in content or '@base' in content:
                        format_hint = 'turtle'
                    elif '<?xml' in content or '<rdf:RDF' in content or 'xmlns:rdf' in content:
                        format_hint = 'xml'
                    elif content.strip().startswith('{'):
                        format_hint = 'json-ld'
                    else:
                        format_hint = 'turtle'  # Default fallback

            current_app.logger.info(f"Detected format: {format_hint}")

            # Check if content needs vocabulary conversion
            from utils.vocabulary_converter import VocabularyConverter, is_vocabulary_convertible

            needs_conversion = False
            original_content = content

            try:
                if is_vocabulary_convertible(content, format_hint):
                    current_app.logger.info("Detected non-OWL vocabulary that needs conversion")

                    converter = VocabularyConverter()
                    ontology_uri = f"http://example.org/{name.lower().replace(' ', '-')}" if name else None

                    converted_content = converter.convert_vocabulary_content(
                        content,
                        input_format=format_hint,
                        output_format='turtle',
                        ontology_uri=ontology_uri
                    )

                    content = converted_content
                    format_hint = 'turtle'
                    needs_conversion = True

                    current_app.logger.info(f"Successfully converted vocabulary to OWL (original: {len(original_content)} chars, converted: {len(content)} chars)")

            except Exception as conversion_error:
                current_app.logger.warning(f"Vocabulary conversion failed: {conversion_error}. Proceeding with original content.")
                content = original_content

            # Use OwlreadyImporter for enhanced processing if reasoning is enabled
            if use_reasoning:
                from importers.owlready_importer import OwlreadyImporter

                importer = OwlreadyImporter()
                importer.use_reasoner = True
                importer.reasoner_type = reasoner_type
                importer.validate_consistency = True
                importer.include_inferred = True

                current_app.logger.info(f"Using OwlreadyImporter with {reasoner_type} reasoning")

                # Import with reasoning
                if source_type == 'url':
                    result = importer.import_from_url(
                        source,
                        name=name,
                        description=description,
                        format=format_hint
                    )
                else:
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{format_hint}', delete=False) as temp_file:
                        temp_file.write(content)
                        temp_path = temp_file.name

                    try:
                        result = importer.import_from_file(
                            temp_path,
                            name=name,
                            description=description,
                            format=format_hint
                        )
                    finally:
                        os.unlink(temp_path)

            else:
                current_app.logger.info("Using basic OntologyManager (no reasoning)")

                if source_type == 'upload':
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{format_hint}', delete=False) as temp_file:
                        temp_file.write(content)
                        temp_path = temp_file.name

                    try:
                        result = current_app.ontology_manager.import_ontology(
                            source=temp_path,
                            importer_type='prov',
                            name=name,
                            description=description,
                            format=format_hint,
                            source_type='file'
                        )
                        if result.get('success'):
                            result['content'] = content
                    finally:
                        os.unlink(temp_path)
                else:
                    result = current_app.ontology_manager.import_ontology(
                        source=source,
                        importer_type='prov',
                        name=name,
                        description=description,
                        format=format_hint,
                        source_type='url'
                    )
                    if result.get('success'):
                        result['content'] = content

            if result['success']:
                ontology_name = name or result['metadata'].get('name', 'Unnamed')

                # Create URI-safe name
                uri_safe_name = ontology_name.lower().replace(' ', '-').replace('&', 'and').replace('/', '-').replace('\\', '-')
                uri_safe_name = re.sub(r'[^a-z0-9\-]', '', uri_safe_name)
                uri_safe_name = re.sub(r'-+', '-', uri_safe_name).strip('-')

                stmt = select(Ontology).where(Ontology.name == uri_safe_name)
                existing_ontology = db.session.execute(stmt).scalar_one_or_none()

                if existing_ontology:
                    flash(f"Ontology '{uri_safe_name}' already exists", 'warning')
                    return redirect(url_for('ontology.ontology_detail_or_uri_resolution', ontology_name=uri_safe_name))

                # Generate base URI using configured domain
                default_base_uri = current_app.config['ONTOLOGY_NAMESPACE_TEMPLATE'].format(
                    base_uri=current_app.config['ONTOLOGY_BASE_URI'],
                    name=uri_safe_name
                )

                # Create new ontology with URI-safe name
                ontology = Ontology(
                    name=uri_safe_name,
                    base_uri=result['metadata'].get('namespace', default_base_uri),
                    description=description or result['metadata'].get('description', ''),
                    meta_data={
                        **result['metadata'],
                        'original_name': ontology_name,
                        'display_name': ontology_name
                    }
                )
                db.session.add(ontology)
                db.session.flush()

                # Get content
                if use_reasoning and 'enhanced_data' in result:
                    content = content or result.get('rdf_content', '')
                    reasoning_metadata = {
                        'reasoning_applied': True,
                        'reasoner_type': reasoner_type,
                        'inferred_relationships': result.get('reasoning_result', {}).get('inferred_count', 0),
                        'consistency_check': result.get('reasoning_result', {}).get('is_consistent'),
                    }
                    change_summary = f"Initial import with {reasoner_type} reasoning"
                else:
                    content = content or result.get('content', '')
                    reasoning_metadata = {'reasoning_applied': False}
                    change_summary = "Initial import"

                # Create initial version with content
                version = OntologyVersion(
                    ontology_id=ontology.id,
                    version_number=1,
                    version_tag="1.0.0",
                    content=content,
                    change_summary=change_summary,
                    created_by="web-import",
                    is_current=True,
                    is_draft=False,
                    workflow_status='published',
                    meta_data={
                        'source': source,
                        'source_type': source_type,
                        'format': result['metadata'].get('format', format_hint),
                        'import_date': datetime.now(timezone.utc).isoformat(),
                        **reasoning_metadata
                    }
                )
                db.session.add(version)

                # Extract and save entities
                if use_reasoning and 'enhanced_data' in result:
                    enhanced_data = result['enhanced_data']

                    for cls in enhanced_data.get('classes', []):
                        entity = OntologyEntity(
                            ontology_id=ontology.id,
                            entity_type='class',
                            uri=cls['uri'],
                            label=cls.get('label', [None])[0] if cls.get('label') else None,
                            comment=cls.get('comment', [None])[0] if cls.get('comment') else None,
                            parent_uri=cls.get('parents', [None])[0] if cls.get('parents') else None
                        )
                        db.session.add(entity)

                    for prop in enhanced_data.get('properties', []):
                        entity = OntologyEntity(
                            ontology_id=ontology.id,
                            entity_type='property',
                            uri=prop['uri'],
                            label=prop.get('label', [None])[0] if prop.get('label') else None,
                            comment=prop.get('comment', [None])[0] if prop.get('comment') else None,
                            domain=prop.get('domain', [None])[0] if prop.get('domain') else None,
                            range=prop.get('range', [None])[0] if prop.get('range') else None
                        )
                        db.session.add(entity)

                    for ind in enhanced_data.get('individuals', []):
                        entity = OntologyEntity(
                            ontology_id=ontology.id,
                            entity_type='individual',
                            uri=ind['uri'],
                            label=ind.get('label', [None])[0] if ind.get('label') else None,
                            comment=ind.get('comment', [None])[0] if ind.get('comment') else None
                        )
                        db.session.add(entity)
                else:
                    entity_counts = extract_entities_from_content(ontology, content, format_hint)
                    current_app.logger.info(f"Extracted {sum(entity_counts.values())} entities using basic parsing")

                db.session.commit()

                success_msg = f"Successfully imported ontology: {ontology_name}"
                if use_reasoning:
                    reasoning_result = result.get('reasoning_result', {})
                    inferred_count = reasoning_result.get('inferred_count', 0)
                    consistency = reasoning_result.get('is_consistent', 'unknown')
                    success_msg += f" (Reasoning: {inferred_count} inferred relationships, consistency: {consistency})"

                flash(success_msg, 'success')
                return redirect(url_for('ontology.ontology_detail_or_uri_resolution', ontology_name=uri_safe_name))
            else:
                flash(f"Import failed: {result.get('message', 'Unknown error')}", 'error')

        except Exception as e:
            flash(f"Error importing ontology: {str(e)}", 'error')
            current_app.logger.error(f"Import error: {e}", exc_info=True)

    return render_template('import.html')


@ontology_bp.route('/ontology/<ontology_name>/edit')
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
    except:
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


@ontology_bp.route('/ontology/<ontology_name>/save', methods=['POST'])
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
            ontology_id,
            content,
            metadata={'commit_message': commit_message}
        )

        # Update database
        ontology.content = content
        ontology.updated_at = datetime.now()

        # Parse to get stats
        g = rdflib.Graph()
        g.parse(data=content, format='turtle')
        ontology.triple_count = len(g)

        # Count classes and properties
        from rdflib import RDF, RDFS, OWL
        ontology.class_count = len(list(g.subjects(RDF.type, OWL.Class)))
        ontology.property_count = (
            len(list(g.subjects(RDF.type, OWL.ObjectProperty))) +
            len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))
        )

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
            created_at=datetime.now()
        )
        db.session.add(version)
        db.session.commit()

        return jsonify({'success': True, 'version_id': version.id})

    except Exception as e:
        current_app.logger.error(f"Error saving ontology: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ontology_bp.route('/ontology/<ontology_name>/save-draft', methods=['POST'])
def save_draft(ontology_name):
    """Save a draft of an ontology (no version created)."""
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.one_or_404(stmt)

    data = request.get_json()
    content = data.get('content', '')

    try:
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@ontology_bp.route('/validate', methods=['POST'])
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


@ontology_bp.route('/editor/ontology/<ontology_name>/validate', methods=['POST'])
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


@ontology_bp.route('/editor/ontology/<ontology_name>/version/<version_id>')
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


@ontology_bp.route('/editor/ontology/<ontology_name>/save', methods=['POST'])
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
            ontology_id,
            content,
            metadata={'commit_message': commit_message}
        )

        ontology.content = content
        ontology.updated_at = datetime.now()

        from rdflib import RDF, RDFS, OWL
        ontology.triple_count = len(g)
        ontology.class_count = len(list(g.subjects(RDF.type, OWL.Class)))
        ontology.property_count = (
            len(list(g.subjects(RDF.type, OWL.ObjectProperty))) +
            len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))
        )

        count_stmt = select(func.count()).select_from(OntologyVersion).where(
            OntologyVersion.ontology_id == ontology.id
        )
        version_count = db.session.execute(count_stmt).scalar()
        version = OntologyVersion(
            ontology_id=ontology.id,
            version_number=version_count + 1,
            content=content,
            change_summary=commit_message,
            created_at=datetime.now()
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


@ontology_bp.route('/editor/api/extract-entities/<ontology_name>', methods=['POST'])
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


@ontology_bp.route('/ontology/<ontology_name>/version/<version_id>')
def get_ontology_version(ontology_name, version_id):
    """Get a specific version of an ontology."""
    version = db.get_or_404(OntologyVersion, version_id)

    return jsonify({
        'content': version.content,
        'version': version.version_number,
        'commit_message': version.change_summary,
        'created_at': version.created_at.isoformat() if version.created_at else None
    })


@ontology_bp.route('/ontology/<ontology_name>/settings')
@login_required
def ontology_settings(ontology_name):
    """Ontology settings page."""
    if not current_user.can_perform_action('edit'):
        flash('You do not have permission to edit ontology settings', 'error')
        return redirect(url_for('ontology.ontology_detail_or_uri_resolution', ontology_name=ontology_name))

    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.one_or_404(stmt)
    return render_template('ontology_settings.html', ontology=ontology)
