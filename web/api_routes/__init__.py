"""JSON API routes for the OntServe web application (split into a register-function package)."""
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

api_bp = Blueprint('api', __name__)

from web.api_routes.sparql_routes import register_sparql
from web.api_routes.ontology_routes import register_ontology
from web.api_routes.versioning_routes import register_versioning
from web.api_routes.entity_routes import register_entities

register_sparql(api_bp)
register_ontology(api_bp)
register_versioning(api_bp)
register_entities(api_bp)


__all__ = ["api_bp"]
