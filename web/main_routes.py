"""
Main routes for OntServe web application.

Handles the home page, the collections index and landing pages, health check,
search, and error handlers.
"""

import logging
import time
from functools import lru_cache
from pathlib import Path

import yaml
from flask import Blueprint, abort, render_template, request, jsonify, current_app, redirect, url_for
from flask_login import current_user
from sqlalchemy import select, func, or_

from web.models import db, Ontology, OntologyEntity
from web.level_views import headline_counts
from services import collections as coll
from services import ontology_categories as categories
from services import proethica_stack as stack
from services.ontology_credit import credit_for

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


_counts_cache = {'at': 0.0, 'value': None}


def cached_headline_counts():
    """headline_counts, kept per process for HEADLINE_COUNTS_TTL seconds: the
    counts change only when a sync or a commit rewrites the entity rows."""
    ttl = current_app.config.get('HEADLINE_COUNTS_TTL', 300)
    now = time.monotonic()
    if _counts_cache['value'] is None or now - _counts_cache['at'] >= ttl:
        _counts_cache['value'] = headline_counts(db.session)
        _counts_cache['at'] = now
    return _counts_cache['value']


def collections_index_url():
    """The URL of the collections index: / when / renders it, else /collections."""
    return url_for('main.index') if coll.get_config().home == coll.HOME_INDEX else url_for('main.collections_index')


def _all_ontologies():
    return db.session.execute(select(Ontology).order_by(Ontology.name)).scalars().all()


def _render_stack(canonical_url=None):
    """The landing page of the ProEthica collection: the ProEthica stack
    (services.proethica_stack) over the ontologies of the ProEthica scope, the
    four levels with their headline counts, the cases by decade, and every
    other ontology of the scope in a Reference list."""
    config = coll.get_config()
    scope = coll.proethica_scope(config)
    ontologies = [o for o in _all_ontologies() if coll.resolve(o, config) in scope]
    partition = stack.partition(ontologies)
    case_groups = categories.group_ontologies(partition.cases)
    publications = () if current_app.config.get('ANONYMOUS_MODE', True) else load_publications()
    return render_template('index.html',
                           stack=partition,
                           counts=cached_headline_counts(),
                           case_group=case_groups[0] if case_groups else None,
                           publications=publications,
                           total_count=len(ontologies),
                           canonical_url=canonical_url)


def _render_index(canonical_url=None):
    """The collections index: the default collection first and in full, then
    the other collections. Signed-in users also see the collections that are
    not public and the ontologies of no collection."""
    config = coll.get_config()
    ontologies = _all_ontologies()
    signed_in = current_user.is_authenticated
    entries = coll.index_entries(ontologies, include_private=signed_in, config=config)
    lead = next((e for e in entries if e.collection.key == config.default_collection), None)
    others = [e for e in entries if e is not lead]
    cases = [o for o in lead.ontologies if o.category == stack.CASES_CATEGORY] if lead else []
    return render_template('collections.html',
                           lead=lead,
                           others=others,
                           case_count=len(cases),
                           unassigned=coll.unassigned(ontologies, config) if signed_in else [],
                           canonical_url=canonical_url)


def _render_landing(collection, canonical_url=None):
    """The landing page of one collection: the ProEthica stack, or the
    members by category and subcategory with the summary of their credit."""
    if collection.landing == 'proethica_stack':
        return _render_stack(canonical_url)
    config = coll.get_config()
    groups = coll.landing_groups(collection.key, _all_ontologies(), config)
    members = [o for group in groups for _, rows in group.subgroups for o in rows]
    return render_template('collection_landing.html',
                           collection=collection,
                           groups=groups,
                           credits={o.name: credit_for(o) for o in members},
                           member_count=len(members),
                           uses=[config.get(key) for key in collection.uses],
                           canonical_url=canonical_url)


@main_bp.route('/collections')
def collections_index():
    """The collections index, at / as well when / renders it (config/collections.yaml, home)."""
    config = coll.get_config()
    return _render_index(url_for('main.index') if config.home == coll.HOME_INDEX else None)


@main_bp.route('/collections/<key>')
def collection_landing(key):
    """The landing page of a collection. A collection that is not public
    answers signed-in users only. The default collection carries a canonical
    link to / when / renders its landing page."""
    config = coll.get_config()
    collection = config.get(key)
    if collection is None or not (collection.public or current_user.is_authenticated):
        abort(404)
    at_home = config.home == coll.HOME_DEFAULT and key == config.default_collection
    return _render_landing(collection, url_for('main.index') if at_home else None)


@main_bp.route('/')
def index():
    """Home page.

    Unfiltered: the collections index, or the landing page of the default
    collection (config/collections.yaml, home). A link with ``origin`` naming
    a collection (ProEthica links /?origin=proethica) is redirected to the
    landing page of that collection. With any filter (source, type, category,
    subcategory): the flat paginated table, or the case index for a category
    listed as cases.
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
        config = coll.get_config()
        origin = config.get(request.args.get('origin'))
        home_landing = config.home == coll.HOME_DEFAULT
        if origin and not (home_landing and origin.key == config.default_collection):
            return redirect(url_for('main.collection_landing', key=origin.key))
        if home_landing:
            return _render_landing(config.get(config.default_collection))
        return _render_index()

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
                               current_subcategory=subcategory)

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
