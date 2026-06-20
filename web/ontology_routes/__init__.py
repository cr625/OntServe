"""Ontology blueprint package -- detail/view, editor, and manage routes."""
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

from web.ontology_routes.detail_routes import register_detail_routes
from web.ontology_routes.manage_routes import register_manage_routes
from web.ontology_routes.editor_routes import register_editor_routes

register_detail_routes(ontology_bp)
register_manage_routes(ontology_bp)
register_editor_routes(ontology_bp)

# Back-compat re-export: tests/unit/test_property_categorization.py imports these helpers directly.
from web.ontology_routes.helpers import _categorize_entity_properties, _iri_values  # noqa: E402,F401

__all__ = ["ontology_bp"]
