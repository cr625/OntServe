"""
Main routes for OntServe web application.

Handles index page, health check, search, and error handlers.
"""

import logging
from functools import lru_cache
from pathlib import Path

import yaml
from flask import Blueprint, render_template, request, jsonify, current_app
from sqlalchemy import select, func, or_

from web.models import db, Ontology, OntologyEntity
from web.level_views import headline_counts
from services import ontology_categories as categories
from services import proethica_stack as stack

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

PUBLICATIONS_PATH = Path(__file__).resolve().parent.parent / 'config' / 'publications.yaml'


@lru_cache(maxsize=1)
def load_publications():
    """The publications list of config/publications.yaml, read once per process."""
    try:
        data = yaml.safe_load(PUBLICATIONS_PATH.read_text(encoding='utf-8')) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning('Publications list not loaded: %s', exc)
        return ()
    return tuple(p for p in data.get('publications') or []
                 if isinstance(p, dict) and p.get('title'))


@main_bp.route('/')
def index():
    """Home page.

    Unfiltered: the ProEthica stack (services.proethica_stack): the four
    levels with their headline counts, the cases by decade, and every other
    ontology in a Reference list. With any filter (source, type, category,
    subcategory): the flat paginated table.
    """
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config['ONTOLOGIES_PER_PAGE']

    # Filter parameters
    source_system = request.args.get('source', None) or None
    ontology_type = request.args.get('type', None) or None
    category = request.args.get('category', None) or None
    subcategory = request.args.get('subcategory', None) or None
    filtered = bool(source_system or ontology_type or category or subcategory)

    # Build query with filters
    stmt = select(Ontology)

    if source_system:
        stmt = stmt.where(Ontology.source_system == source_system)
    if ontology_type:
        stmt = stmt.where(Ontology.ontology_type == ontology_type)
    if category or subcategory:
        # Category is resolved in Python (explicit metadata or rule default),
        # so restrict by id. The ontologies table is small (hundreds of rows);
        # revisit with a persisted column if it grows by orders of magnitude.
        candidates = db.session.execute(select(Ontology)).scalars().all()
        ids = [o.id for o in candidates if categories.matches(o, category, subcategory)]
        stmt = stmt.where(Ontology.id.in_(ids)) if ids else stmt.where(False)

    # Order by name
    stmt = stmt.order_by(Ontology.name)

    if not filtered:
        ontologies = db.session.execute(stmt).scalars().all()
        partition = stack.partition(ontologies)
        case_groups = categories.group_ontologies(partition.cases)
        publications = () if current_app.config.get('ANONYMOUS_MODE', True) else load_publications()
        return render_template('index.html',
                               stack=partition,
                               counts=headline_counts(db.session),
                               case_group=case_groups[0] if case_groups else None,
                               publications=publications,
                               total_count=len(ontologies))

    # A category listed as 'cases' renders the case index: every matching case on
    # one page, newest NSPE case first, with the decades of the whole category.
    cat = categories.category_info(category) if category else None
    if cat and cat.listing == 'cases' and not (source_system or ontology_type):
        rows = db.session.execute(stmt).scalars().all()
        all_cases = [o for o in candidates if categories.matches(o, category, None)]
        decades = categories.group_ontologies(all_cases)
        return render_template('index.html',
                               stack=None,
                               case_index=_case_rows(rows),
                               case_category=cat,
                               case_decades=decades[0].subgroups if decades else [],
                               case_total=len(all_cases),
                               current_category=category,
                               current_subcategory=subcategory,
                               total_count=len(candidates))

    pagination = db.paginate(
        stmt,
        page=page,
        per_page=per_page,
        error_out=False
    )
    ontologies = pagination.items
    _prefetch_entity_counts(ontologies)

    # Unfiltered repository total: lets the template distinguish "no ontologies
    # exist" from "no ontologies match this filter" (zero results)
    total_count = db.session.execute(select(func.count(Ontology.id))).scalar() or 0

    return render_template('index.html',
                         stack=None,
                         ontologies=ontologies,
                         pagination=pagination,
                         current_source=source_system,
                         current_type=ontology_type,
                         current_category=category,
                         current_subcategory=subcategory,
                         category_info=categories.category_info,
                         total_count=total_count)


def _case_rows(ontologies):
    """Rows of the case index, newest NSPE case number first (two-digit-year
    pivot of categories.nspe_case_order); cases without a number come last."""
    rows = []
    for o in ontologies:
        md = o.meta_data if isinstance(o.meta_data, dict) else {}
        number = md.get(categories.CASE_NUMBER_KEY)
        rows.append({'name': o.name, 'title': md.get(categories.DISPLAY_NAME_KEY) or o.name,
                     'case_number': number, 'decade': o.subcategory,
                     'order': categories.nspe_case_order(number)})
    rows.sort(key=lambda r: (r['order'] is None, tuple(-v for v in (r['order'] or (0, 0))), r['name']))
    return rows


def _prefetch_entity_counts(ontologies):
    """Preload entity counts in a single query to avoid N+1 (2 COUNT queries per ontology)."""
    if not ontologies:
        return
    ont_ids = [o.id for o in ontologies]
    count_rows = db.session.execute(
        select(
            OntologyEntity.ontology_id,
            OntologyEntity.entity_type,
            func.count(OntologyEntity.id)
        )
        .where(OntologyEntity.ontology_id.in_(ont_ids))
        .group_by(OntologyEntity.ontology_id, OntologyEntity.entity_type)
    ).all()
    counts_by_ont = {}
    for ont_id, etype, cnt in count_rows:
        if ont_id not in counts_by_ont:
            counts_by_ont[ont_id] = {'class': 0, 'property': 0, 'individual': 0}
        counts_by_ont[ont_id][etype] = cnt
    for ont in ontologies:
        c = counts_by_ont.get(ont.id, {})
        ont._prefetched_class_count = c.get('class', 0)
        ont._prefetched_triple_count = c.get('class', 0) + c.get('property', 0) + c.get('individual', 0)


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

        # Search entities. Deprecated entities are excluded: they are retained
        # in the graphs only as machine-readable markers (owl:deprecated
        # bridge/stub classes), and surfacing them beside their live successors
        # presents duplicate vocabulary (e.g. the intermediate DecisionPoint
        # stub next to the live proeth-cases:DecisionPoint).
        if search_type in ['all', 'entities']:
            stmt = select(OntologyEntity).where(
                or_(
                    OntologyEntity.label.ilike(f'%{query}%'),
                    OntologyEntity.comment.ilike(f'%{query}%'),
                    OntologyEntity.uri.ilike(f'%{query}%')
                ),
                OntologyEntity.properties.op('->>')('deprecated').is_distinct_from('true')
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
