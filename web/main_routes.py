"""
Main routes for OntServe web application.

Handles index page, health check, search, and error handlers.
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from sqlalchemy import select, func, or_

from web.models import db, Ontology, OntologyEntity

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Home page showing list of ontologies with filtering."""
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config['ONTOLOGIES_PER_PAGE']

    # Filter parameters
    source_system = request.args.get('source', None)
    ontology_type = request.args.get('type', None)

    # Build query with filters
    stmt = select(Ontology)

    if source_system:
        stmt = stmt.where(Ontology.source_system == source_system)
    if ontology_type:
        stmt = stmt.where(Ontology.ontology_type == ontology_type)

    # Order by name
    stmt = stmt.order_by(Ontology.name)

    pagination = db.paginate(
        stmt,
        page=page,
        per_page=per_page,
        error_out=False
    )
    ontologies = pagination.items

    # Get counts for filter badges
    source_counts = db.session.execute(
        select(Ontology.source_system, func.count(Ontology.id))
        .group_by(Ontology.source_system)
    ).all()
    type_counts = db.session.execute(
        select(Ontology.ontology_type, func.count(Ontology.id))
        .group_by(Ontology.ontology_type)
    ).all()

    return render_template('index.html',
                         ontologies=ontologies,
                         pagination=pagination,
                         current_source=source_system,
                         current_type=ontology_type,
                         source_counts=dict(source_counts),
                         type_counts=dict(type_counts))


@main_bp.route('/health')
def health():
    """Health check endpoint for monitoring and testing."""
    return jsonify({
        'status': 'healthy',
        'service': 'ontserve-web',
        'database': 'connected' if db.engine else 'disconnected'
    })


@main_bp.route('/search')
def search():
    """Search for ontologies and entities."""
    query = request.args.get('q', '')
    search_type = request.args.get('type', 'all')

    results = {
        'ontologies': [],
        'entities': []
    }

    if query:
        # Search ontologies
        if search_type in ['all', 'ontologies']:
            stmt = select(Ontology).where(
                or_(
                    Ontology.name.ilike(f'%{query}%'),
                    Ontology.description.ilike(f'%{query}%'),
                    Ontology.base_uri.ilike(f'%{query}%')
                )
            )
            results['ontologies'] = db.session.execute(stmt).scalars().all()

        # Search entities
        if search_type in ['all', 'entities']:
            stmt = select(OntologyEntity).where(
                or_(
                    OntologyEntity.label.ilike(f'%{query}%'),
                    OntologyEntity.comment.ilike(f'%{query}%'),
                    OntologyEntity.uri.ilike(f'%{query}%')
                )
            ).limit(50)
            results['entities'] = db.session.execute(stmt).scalars().all()

    return render_template('search.html',
                         query=query,
                         search_type=search_type,
                         results=results)


@main_bp.app_errorhandler(404)
def not_found(error):
    """404 error handler."""
    return render_template('404.html'), 404


@main_bp.app_errorhandler(500)
def internal_error(error):
    """500 error handler."""
    db.session.rollback()
    return render_template('500.html'), 500
