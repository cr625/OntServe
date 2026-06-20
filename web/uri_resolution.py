"""
URI resolution routes for OntServe web application.

Handles resolving ontology entity URIs via query parameter and path-based access.
"""

from flask import Blueprint, request, jsonify, current_app, redirect, url_for
from sqlalchemy import select

from web.models import db, OntologyEntity
from web.rdf_helpers import generate_entity_ttl, generate_concept_ttl

uri_bp = Blueprint('uri', __name__)


@uri_bp.route('/resolve', methods=['GET', 'OPTIONS'])
def resolve_uri():
    """
    Resolve ontology entity URIs and return entity information.

    Handles URIs like:
    - http://proethica.org/ontology/intermediate#Honesty
    - http://proethica.org/ontology/core#Principle

    Usage:
        /resolve?uri=http://proethica.org/ontology/intermediate#Honesty

    Returns:
        TTL format by default, with content negotiation support
    """
    try:
        # Handle OPTIONS request for CORS preflight
        if request.method == 'OPTIONS':
            response = current_app.response_class(status=200)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Accept, Content-Type'
            return response

        # Get URI from query parameter
        uri = request.args.get('uri')
        if not uri:
            return jsonify({
                'error': 'Missing required parameter: uri',
                'usage': '/resolve?uri=http://proethica.org/ontology/intermediate#Honesty'
            }), 400

        current_app.logger.info(f"Resolving URI: {uri}")

        # Find entity in ontology_entities table first
        stmt = select(OntologyEntity).where(OntologyEntity.uri == uri)
        entity = db.session.execute(stmt).scalar_one_or_none()

        # Check Accept header for content negotiation
        accept_header = request.headers.get('Accept', '')

        if entity:
            ontology = entity.ontology

            if 'application/json' in accept_header:
                return jsonify({
                    'uri': entity.uri,
                    'label': entity.label,
                    'type': entity.entity_type,
                    'definition': entity.comment,
                    'ontology': ontology.name,
                    'ontology_base_uri': ontology.base_uri,
                    'properties': entity.properties or {}
                })

            ttl_content = generate_entity_ttl(entity, ontology)
        else:
            # Fallback: check concepts table
            concept = db.session.execute(
                db.text("SELECT uri, label, semantic_label, primary_type, description, metadata FROM concepts WHERE uri = :uri"),
                {'uri': uri}
            ).mappings().first()

            if not concept:
                current_app.logger.warning(f"Entity not found for URI: {uri}")
                return jsonify({
                    'error': 'Entity not found',
                    'uri': uri
                }), 404

            current_app.logger.info(f"Found concept in concepts table: {concept['label']}")

            if 'application/json' in accept_header:
                return jsonify({
                    'uri': concept['uri'],
                    'label': concept['semantic_label'] or concept['label'],
                    'type': concept['primary_type'],
                    'definition': concept['description'],
                    'source': 'concepts',
                    'metadata': concept['metadata'] or {}
                })

            ttl_content = generate_concept_ttl(concept)

        response = current_app.response_class(
            response=ttl_content,
            status=200,
            mimetype='text/turtle'
        )

        # Add CORS headers for cross-origin access
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Accept, Content-Type'

        return response

    except Exception as e:
        current_app.logger.error(f"Error resolving URI {request.args.get('uri', 'unknown')}: {e}")
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500


@uri_bp.route('/ontology/<path:ontology_path>/<entity_name>')
def resolve_uri_path(ontology_path, entity_name):
    """
    Direct path-based URI resolution.

    Examples:
        /ontology/intermediate/Honesty
        /ontology/core/Principle
    """
    # Exclude reserved route names that have specific handlers.
    # Call the handler directly instead of redirecting to avoid redirect
    # loops (this catch-all route matches the same URL the redirect targets).
    reserved_names = {'content', 'edit', 'save', 'settings', 'version', 'draft', 'save-draft'}

    if entity_name in reserved_names and '/' not in ontology_path:
        ontology_name = ontology_path

        if entity_name == 'content':
            # The handler now lives in the ontology_routes package (register-fn
            # sub-module), so call it by endpoint via view_functions (current_app
            # is imported module-level) rather than importing the nested function.
            # Still a direct call (no redirect loop).
            return current_app.view_functions['ontology.ontology_content'](ontology_name)
        elif entity_name == 'edit':
            return redirect(url_for('ontology.edit_ontology', ontology_name=ontology_name))
        elif entity_name == 'save':
            from flask import abort
            abort(405)
        elif entity_name == 'settings':
            return redirect(url_for('ontology.ontology_settings', ontology_name=ontology_name))
        else:
            from flask import abort
            abort(404)

    # Construct the full URI
    base_uri = f"http://proethica.org/ontology/{ontology_path}"
    full_uri = f"{base_uri}#{entity_name}"

    # Find entity in database
    stmt = select(OntologyEntity).where(OntologyEntity.uri == full_uri)
    entity = db.session.execute(stmt).scalar_one_or_none()

    if not entity:
        return jsonify({
            'error': 'Entity not found',
            'uri': full_uri
        }), 404

    ontology = entity.ontology

    # Check Accept header for content negotiation
    accept_header = request.headers.get('Accept', '')

    if 'application/json' in accept_header:
        return jsonify({
            'uri': entity.uri,
            'label': entity.label,
            'type': entity.entity_type,
            'definition': entity.comment,
            'ontology': ontology.name,
            'ontology_base_uri': ontology.base_uri,
            'properties': entity.properties or {}
        })

    # Default: Return TTL representation
    ttl_content = generate_entity_ttl(entity, ontology)

    response = current_app.response_class(
        response=ttl_content,
        status=200,
        mimetype='text/turtle'
    )

    # Add CORS headers for cross-origin access
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Accept, Content-Type'

    return response
