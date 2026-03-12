"""
Ontology CRUD routes for OntServe web application.

Handles ontology detail view, content negotiation, format conversion,
import, edit, save, validation, versions, and settings.
"""

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

    # Optional case filter: ?case=7 filters classes/individuals by discoveredInCase property
    case_filter = request.args.get('case', type=int)

    if case_filter:
        def matches_case(entity):
            if not entity.properties:
                return False
            disc = entity.properties.get('discoveredincase') or entity.properties.get('discoveredInCase')
            if disc is None:
                return False
            if isinstance(disc, list):
                return str(case_filter) in [str(v) for v in disc]
            return str(disc) == str(case_filter)

        filtered = [e for e in all_entities if matches_case(e) or e.entity_type == 'property']
        all_entities = filtered

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
                         stats=stats,
                         case_filter=case_filter)


@ontology_bp.route('/ontology/<ontology_name>/content')
def ontology_content(ontology_name):
    """Return raw TTL content of an ontology."""
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.one_or_404(stmt)
    content = ontology.current_content
    if content is None:
        return "No content available for this ontology", 404
    return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}


@ontology_bp.route('/entity/<ontology_name>/<fragment>')
def entity_detail(ontology_name, fragment):
    """Entity detail page showing current state of an entity."""
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.session.execute(stmt).scalar_one_or_none()

    entity = _find_entity_by_fragment(ontology, fragment) if ontology else None

    # Cross-ontology fallback: entity may be in a related ontology
    # (e.g., classes targeted to proethica-intermediate live in proethica-intermediate-extended)
    if not entity:
        cross_stmt = select(OntologyEntity).where(
            OntologyEntity.uri.like(f'%#{fragment}')
        ).limit(1)
        entity = db.session.execute(cross_stmt).scalar_one_or_none()
        if entity:
            ontology = entity.ontology
        else:
            from flask import abort
            abort(404)

    children = _get_entity_children(ontology, entity)
    ttl_content = _generate_entity_ttl_display(entity, ontology)
    prop_groups = _categorize_entity_properties(entity)

    return render_template('entity_detail.html',
                         ontology=ontology,
                         entity=entity,
                         fragment=fragment,
                         children=children,
                         ttl_content=ttl_content,
                         prop_groups=prop_groups,
                         version_tag=None,
                         version_date=None)


@ontology_bp.route('/entity/<ontology_name>/version/<version_tag>/<fragment>')
def entity_detail_versioned(ontology_name, version_tag, fragment):
    """Entity detail page showing entity at a specific tagged version."""
    stmt = select(Ontology).where(Ontology.name == ontology_name)
    ontology = db.one_or_404(stmt)

    # Find the tagged version
    version_stmt = select(OntologyVersion).where(
        OntologyVersion.ontology_id == ontology.id,
        OntologyVersion.version_tag == version_tag
    )
    version = db.session.execute(version_stmt).scalar_one_or_none()
    if not version:
        from flask import abort
        abort(404)

    # Parse entity from the version's TTL content
    entity_data = _extract_entity_from_ttl(version.content, ontology, fragment)
    if not entity_data:
        from flask import abort
        abort(404)

    version_date = version.created_at.strftime('%Y-%m-%d') if version.created_at else None

    return render_template('entity_detail.html',
                         ontology=ontology,
                         entity=entity_data,
                         fragment=fragment,
                         children=[],
                         ttl_content=entity_data.get('_ttl', ''),
                         version_tag=version_tag,
                         version_date=version_date)


import re as _re


# Property keys that represent extraction/provenance metadata (sidebar)
_EXTRACTION_META_KEYS = frozenset({
    'discoveredincase', 'discoveredinpass', 'discoveredinsection',
    'firstdiscoveredat', 'firstdiscoveredincase',
    'generatedattime', 'generatedAtTime',
    'wasattributedto', 'wasGeneratedBy',
})

# Property keys that represent textual evidence from the case
_EVIDENCE_KEYS = frozenset({'sourcetext', 'textreferences'})

# Property keys rendered as the entity description (below Definition)
_DESCRIPTION_KEYS = frozenset({'caseinvolvement'})

# Property keys to skip entirely (redundant or internal)
_SKIP_KEYS = frozenset({'type', 'NamedIndividual', 'rdf_types'})

# Human-readable labels for property keys
_PROPERTY_LABELS = {
    'conceptCategory': 'Concept Category',
    'roleclass': 'Role Class',
    'rolecategory': 'Role Category',
    'importance': 'Importance',
    'confidence': 'Confidence',
    'attributes': 'Attributes',
    'relationships': 'Relationships',
    'caseinvolvement': 'Case Involvement',
    'sourcetext': 'Source Text',
    'textreferences': 'Text References',
    'discoveredincase': 'Discovered in Case',
    'discoveredinpass': 'Discovered in Pass',
    'discoveredinsection': 'Discovered in Section',
    'firstdiscoveredat': 'First Discovered',
    'firstdiscoveredincase': 'First Case',
    'generatedattime': 'Generated',
    'generatedAtTime': 'Generated',
    'wasattributedto': 'Attributed To',
    'wasGeneratedBy': 'Generated By',
    'discoveredInCase': 'Discovered in Case',
}


def _humanize_property_key(key):
    """Convert a property key to a human-readable label."""
    if key in _PROPERTY_LABELS:
        return _PROPERTY_LABELS[key]
    # Split camelCase: insert space before uppercase letters
    spaced = _re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', key)
    # Capitalize first letter
    return spaced[0].upper() + spaced[1:] if spaced else key


def _format_property_value(value):
    """Format a property value for display, handling dict-like strings."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    # Detect Python dict-like strings: {'key': 'value'}
    if s.startswith('{') and s.endswith('}') and "'" in s:
        try:
            import ast
            parsed = ast.literal_eval(s)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, SyntaxError):
            pass
    return value


def _categorize_entity_properties(entity):
    """Categorize entity properties into display groups.

    Returns a dict with keys:
        description: list of (label, value) for case involvement text
        core: list of (label, value) for primary entity properties
        evidence: list of (label, value) for source text references
        extraction_meta: list of (label, value) for provenance metadata
    """
    groups = {
        'description': [],
        'core': [],
        'evidence': [],
        'extraction_meta': [],
    }

    if not entity.properties:
        return groups

    for key, value in entity.properties.items():
        if key in _SKIP_KEYS:
            continue

        label = _humanize_property_key(key)
        formatted = _format_property_value(value) if isinstance(value, str) else value
        # Format list items too
        if isinstance(value, list):
            formatted = [_format_property_value(v) for v in value]

        entry = (label, formatted)

        if key.lower() in {k.lower() for k in _DESCRIPTION_KEYS}:
            groups['description'].append(entry)
        elif key.lower() in {k.lower() for k in _EVIDENCE_KEYS}:
            groups['evidence'].append(entry)
        elif key.lower() in {k.lower() for k in _EXTRACTION_META_KEYS}:
            groups['extraction_meta'].append(entry)
        else:
            groups['core'].append(entry)

    return groups


def _find_entity_by_fragment(ontology, fragment):
    """Find entity by URI fragment (the part after #)."""
    # Try exact fragment match against known base URIs
    if ontology.base_uri:
        full_uri = f"{ontology.base_uri.rstrip('/#')}#{fragment}"
        stmt = select(OntologyEntity).where(
            OntologyEntity.ontology_id == ontology.id,
            OntologyEntity.uri == full_uri
        )
        entity = db.session.execute(stmt).scalar_one_or_none()
        if entity:
            return entity

    # Fallback: search by URI ending with #fragment
    stmt = select(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        OntologyEntity.uri.like(f'%#{fragment}')
    )
    return db.session.execute(stmt).scalar_one_or_none()


def _get_entity_children(ontology, entity):
    """Get entities that have this entity as parent_uri."""
    stmt = select(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        OntologyEntity.parent_uri == entity.uri
    ).order_by(OntologyEntity.label)
    return db.session.execute(stmt).scalars().all()


def _generate_entity_ttl_display(entity, ontology):
    """Generate TTL representation for display."""
    from web.rdf_helpers import generate_entity_ttl
    return generate_entity_ttl(entity, ontology)


def _extract_entity_from_ttl(ttl_content, ontology, fragment):
    """Extract a single entity's data from TTL content for versioned display.

    Returns a dict-like object with entity attributes, or None if not found.
    """
    g = rdflib.Graph()
    try:
        g.parse(data=ttl_content, format='turtle')
    except Exception:
        return None

    # Find the entity URI by fragment
    target_uri = None
    for s in g.subjects():
        s_str = str(s)
        if s_str.endswith(f'#{fragment}'):
            target_uri = s
            break

    if not target_uri:
        return None

    from rdflib import RDF, RDFS, OWL

    # Determine type
    entity_type = 'class'
    for type_uri in g.objects(target_uri, RDF.type):
        if type_uri == OWL.ObjectProperty or type_uri == OWL.DatatypeProperty:
            entity_type = 'property'
        elif type_uri == OWL.NamedIndividual:
            entity_type = 'individual'

    label = next(g.objects(target_uri, RDFS.label), None)
    comment = next(g.objects(target_uri, RDFS.comment), None)
    parent = next(g.objects(target_uri, RDFS.subClassOf), None)
    domain = next(g.objects(target_uri, RDFS.domain), None)
    range_val = next(g.objects(target_uri, RDFS.range), None)

    uri_str = str(target_uri)
    label_str = str(label) if label else None
    comment_str = str(comment) if comment else None
    content_hash = OntologyEntity.compute_content_hash(uri_str, label_str, comment_str)

    # Build TTL snippet for display
    from web.rdf_helpers import generate_entity_ttl

    class _EntityProxy:
        """Lightweight proxy mimicking OntologyEntity for TTL generation."""
        pass

    proxy = _EntityProxy()
    proxy.uri = uri_str
    proxy.label = label_str
    proxy.comment = comment_str
    proxy.entity_type = entity_type
    proxy.parent_uri = str(parent) if parent else None
    proxy.domain = str(domain) if domain else None
    proxy.range = str(range_val) if range_val else None
    proxy.properties = None
    proxy.content_hash = content_hash
    proxy.updated_at = None
    proxy.id = None
    proxy._ttl = generate_entity_ttl(proxy, ontology)

    return proxy


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


@ontology_bp.route('/ontology/<ontology_name>/save-draft', methods=['POST'])
@login_required
def save_draft(ontology_name):
    """Save a draft of an ontology (no version created)."""
    return jsonify({'success': False, 'message': 'Draft saving not yet implemented'}), 501


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
