"""Shared non-route helpers for the api blueprint."""
import hashlib
import logging

import rdflib
from datetime import datetime, timezone
from rdflib import RDF, OWL, RDFS
from rdflib.namespace import SKOS

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import select, func

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from web.entity_extraction import extract_entities_from_content

logger = logging.getLogger(__name__)


def _extract_sparql_query():
    """Pull a SPARQL query string from the current Flask request.

    Accepts the four shapes the SPARQL 1.1 Protocol allows:
    - GET /sparql?query=...
    - POST application/sparql-query (raw body)
    - POST application/x-www-form-urlencoded (query=...)
    - POST application/json {"query": "..."}
    """
    if request.method == 'GET':
        return request.args.get('query')

    content_type = (request.headers.get('Content-Type') or '').lower()
    if 'application/sparql-query' in content_type:
        return request.get_data(as_text=True) or None
    if 'application/x-www-form-urlencoded' in content_type:
        return request.form.get('query')

    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data.get('query')
    return None


def _compute_divergence(old_ttl_content: str, new_ttl_content: str) -> float:
    """Compute entity-level divergence between two TTL content strings.

    Returns percentage of entities that differ (added, removed, or modified)
    relative to the old version's entity count.
    """
    old_entities = _extract_entity_hashes(old_ttl_content)
    new_entities = _extract_entity_hashes(new_ttl_content)

    if not old_entities:
        return 100.0 if new_entities else 0.0

    old_uris = set(old_entities.keys())
    new_uris = set(new_entities.keys())

    added = new_uris - old_uris
    removed = old_uris - new_uris
    common = old_uris & new_uris
    modified = {uri for uri in common if old_entities[uri] != new_entities[uri]}

    total_changes = len(added) + len(removed) + len(modified)
    return round(total_changes / len(old_entities) * 100, 1)


def _extract_entity_hashes(ttl_content: str) -> dict:
    """Parse TTL content and return {uri: content_hash} for all entities."""
    g = rdflib.Graph()
    try:
        g.parse(data=ttl_content, format='turtle')
    except Exception:
        return {}

    entities = {}
    for entity_type in [OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.NamedIndividual]:
        for uri in g.subjects(RDF.type, entity_type):
            uri_str = str(uri)
            if not uri_str.startswith('http'):
                continue
            label = next(g.objects(uri, RDFS.label), None)
            comment = next(g.objects(uri, RDFS.comment), None)
            if comment is None:
                comment = next(g.objects(uri, SKOS.definition), None)
            label_str = str(label) if label else ''
            comment_str = str(comment) if comment else ''
            raw = f"{uri_str}|{label_str}|{comment_str}"
            entities[uri_str] = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    return entities
