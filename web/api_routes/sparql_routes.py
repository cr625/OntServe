"""Public SPARQL endpoint and diagnostics."""
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
from web.api_routes.helpers import (
    _extract_sparql_query,
)


def register_sparql(bp):
    @bp.route('/sparql', methods=['GET', 'POST'])
    def sparql_endpoint():
        """Execute a SPARQL query against the full OntServe graph."""
        sparql_service = getattr(current_app, 'sparql_service', None)
        if sparql_service is None:
            return jsonify({'error': 'SPARQL service not available'}), 503

        query = _extract_sparql_query()
        if not query:
            return jsonify({'error': 'No SPARQL query provided'}), 400

        try:
            results = sparql_service.execute_query(query)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            logger.error("SPARQL endpoint error: %s", exc)
            return jsonify({'error': 'Internal server error'}), 500

        return jsonify(results)


    @bp.route('/sparql/status', methods=['GET'])
    def sparql_status():
        """Diagnostics: report the SPARQL service load source and ontology count."""
        sparql_service = getattr(current_app, 'sparql_service', None)
        if sparql_service is None:
            return jsonify({'error': 'SPARQL service not available'}), 503
        return jsonify(sparql_service.get_service_status())
