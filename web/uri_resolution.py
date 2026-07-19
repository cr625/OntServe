"""
URI resolution routes for OntServe web application.

Handles resolving ontology entity URIs via query parameter and path-based access.
"""

from flask import Blueprint, request, jsonify, current_app, redirect, url_for

from web.models import db
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

        # Find entity in ontology_entities table first. The same URI holds a row in
        # every ontology that declares it (case stubs, the foundation mirror), so
        # resolve to the definitional row instead of scalar_one_or_none(), which
        # raises MultipleResultsFound for any shared URI.
        from web.ontology_routes.helpers import definitional_entity_for_uri
        entity = definitional_entity_for_uri(uri)

        # Check Accept header for content negotiation
        accept_header = request.headers.get('Accept', '')

        if entity:
            ontology = entity.ontology

            if 'application/json' in accept_header:
                props = entity.properties or {}
                return jsonify({
                    'uri': entity.uri,
                    'label': entity.label,
                    'type': entity.entity_type,
                    # Prefer the formal definition (iao:0000115 on classes per OBO convention;
                    # skos:definition on SKOS concepts/legacy), captured into properties, over the
                    # shorter rdfs:comment gloss, matching the entity page's Definition card.
                    'definition': props.get('IAO_0000115') or props.get('definition') or entity.comment,
                    'comment': entity.comment,
                    'ontology': ontology.name,
                    'ontology_base_uri': ontology.base_uri,
                    'properties': props
                })

            # Render the entity's ACTUAL source triples (skos:definition, IAO annotations,
            # restrictions, skos crosswalks), the same faithful TTL the entity page shows --
            # not the thin label/comment/parent projection from the structured columns.
            from web.ontology_routes.helpers import generate_entity_ttl_display
            ttl_content = generate_entity_ttl_display(entity, ontology)
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


@uri_bp.route('/resolve/embedding', methods=['GET', 'OPTIONS'])
def resolve_embedding():
    """Return an entity's vector embedding as CSV (dimension,value), for the Formats card / API.

    Usage:
        /resolve/embedding?uri=http://proethica.org/ontology/core#Role

    Returns text/csv as a download (one row per dimension) when the entity has an embedding,
    404 if the entity is unknown or has no embedding yet (run tools/populate_entity_embeddings.py
    for its ontology). A single entity's vector is small (384 float32 ~= a few KB), so CSV is
    used directly; a bulk/zip export is a future concern once we move embeddings around.
    """
    if request.method == 'OPTIONS':
        response = current_app.response_class(status=200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Accept, Content-Type'
        return response

    uri = request.args.get('uri')
    if not uri:
        return jsonify({
            'error': 'Missing required parameter: uri',
            'usage': '/resolve/embedding?uri=http://proethica.org/ontology/core#Role'
        }), 400

    try:
        from web.ontology_routes.helpers import definitional_entity_for_uri
        entity = definitional_entity_for_uri(uri)
        if not entity:
            return jsonify({'error': 'Entity not found', 'uri': uri}), 404

        emb = entity.embedding
        if emb is None:
            return jsonify({
                'error': 'No embedding for this entity',
                'uri': uri,
                'hint': 'Run tools/populate_entity_embeddings.py for its ontology'
            }), 404

        # pgvector returns a numpy array; normalize to a list of floats (string fallback for safety).
        if hasattr(emb, 'tolist'):
            values = emb.tolist()
        elif isinstance(emb, str):
            values = [float(x) for x in emb.strip('[]').split(',') if x.strip()]
        else:
            values = list(emb)

        import io
        import csv
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['dimension', 'value'])
        for i, v in enumerate(values):
            writer.writerow([i, float(v)])

        fragment = uri.rsplit('#', 1)[-1].rsplit('/', 1)[-1]
        filename = f"{entity.ontology.name}__{fragment}.embedding.csv"
        response = current_app.response_class(
            response=buf.getvalue(), status=200, mimetype='text/csv')
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['X-Embedding-Dimensions'] = str(len(values))
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

    except Exception as e:
        current_app.logger.error(f"Error returning embedding for {uri}: {e}")
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500


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
            # Direct call (not redirect): url_for would point back at this same
            # catch-all and loop. The direct call also lets edit_ontology's
            # @login_required fire, redirecting anonymous users to /auth/login.
            return current_app.view_functions['ontology.edit_ontology'](ontology_name)
        elif entity_name == 'save':
            from flask import abort
            abort(405)
        elif entity_name == 'settings':
            # Direct call (see the edit branch): redirecting here would loop.
            return current_app.view_functions['ontology.ontology_settings'](ontology_name)
        else:
            from flask import abort
            abort(404)

    # Construct the full URI
    base_uri = f"http://proethica.org/ontology/{ontology_path}"
    full_uri = f"{base_uri}#{entity_name}"

    # Find entity in database (definitional row; the URI may also exist as case stubs)
    from web.ontology_routes.helpers import definitional_entity_for_uri
    entity = definitional_entity_for_uri(full_uri)

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
