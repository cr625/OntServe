"""Entity property/semantic-link helpers + constants.

Split into submodules (hierarchy, shapes, display, links); this package
`__init__` re-exports every name the original single-file module defined so
`from web.ontology_routes.helpers import X` keeps working unchanged for all
existing callers (web/uri_resolution.py, web/ontology_routes/__init__.py,
web/ontology_routes/detail_routes.py, tests).
"""
import logging  # noqa: F401
from datetime import datetime, timezone  # noqa: F401

from flask import (  # noqa: F401
    Blueprint, render_template, request, jsonify, flash, redirect, url_for,
    current_app,
)
from flask_login import login_required, current_user  # noqa: F401
from sqlalchemy import select, func, or_  # noqa: F401
import rdflib  # noqa: F401

from web.models import db, Ontology, OntologyEntity, OntologyVersion  # noqa: F401
from web.ontology_stats import build_stats_context  # noqa: F401
from web.entity_extraction import extract_entities_from_content  # noqa: F401
from web.ontology_routes.component_page_rulebook import property_structure_groups  # noqa: F401

import re as _re  # noqa: F401

from .hierarchy import (
    _base_subclass_closure,
    _is_secondary_parent_of,
    _get_entity_children,
    _class_ancestor_uris,
    _class_ancestor_uris_all,
    _uri_fragment,
    _is_bfo_uri,
    _canonical_upper_ontology,
    _hierarchy_node,
    class_hierarchy,
    _entity_secondary_parents,
)
from .shapes import (
    _CORE_ROLE_URI,
    _ROLE_ATTR_SCHEMA_CACHE,
    _UNIVERSAL_TOP_URIS,
    _shape_attr_schema,
    _shape_target_map,
    _class_shape_schemas,
    class_property_schema,
    _class_target_shapes_graph,
)
from .display import (
    _CROSSWALK_KEYS,
    _EXTRACTION_META_KEYS,
    _EVIDENCE_KEYS,
    _DESCRIPTION_KEYS,
    _SKIP_KEYS,
    _DEFINITION_LAYER_GROUP,
    _PROPERTY_LABELS,
    _humanize_property_key,
    _format_property_value,
    _categorize_entity_properties,
    _iri_values,
    _generate_entity_ttl_display,
    _extract_entity_from_ttl,
)
from .links import (
    _SEMANTIC_LINK_PREDS,
    _entity_semantic_links,
    _CASE_ONTOLOGY_RE,
    _entity_using_cases,
    _uri_ends_with_fragment,
    _find_entity_by_fragment,
    definitional_entity_for_uri,
    _entity_disjoint_classes,
    _entity_case_provenance,
    _entity_incoming_edges,
    _entity_equivalent_class,
)

__all__ = [
    # hierarchy
    "_base_subclass_closure",
    "_is_secondary_parent_of",
    "_get_entity_children",
    "_class_ancestor_uris",
    "_class_ancestor_uris_all",
    "_uri_fragment",
    "_is_bfo_uri",
    "_canonical_upper_ontology",
    "_hierarchy_node",
    "class_hierarchy",
    "_entity_secondary_parents",
    # shapes
    "_CORE_ROLE_URI",
    "_ROLE_ATTR_SCHEMA_CACHE",
    "_UNIVERSAL_TOP_URIS",
    "_shape_attr_schema",
    "_shape_target_map",
    "_class_shape_schemas",
    "class_property_schema",
    "_class_target_shapes_graph",
    # display
    "_CROSSWALK_KEYS",
    "_EXTRACTION_META_KEYS",
    "_EVIDENCE_KEYS",
    "_DESCRIPTION_KEYS",
    "_SKIP_KEYS",
    "_DEFINITION_LAYER_GROUP",
    "_PROPERTY_LABELS",
    "_humanize_property_key",
    "_format_property_value",
    "_categorize_entity_properties",
    "_iri_values",
    "_generate_entity_ttl_display",
    "_extract_entity_from_ttl",
    # links
    "_SEMANTIC_LINK_PREDS",
    "_entity_semantic_links",
    "_CASE_ONTOLOGY_RE",
    "_entity_using_cases",
    "_uri_ends_with_fragment",
    "_find_entity_by_fragment",
    "definitional_entity_for_uri",
    "_entity_disjoint_classes",
    "_entity_case_provenance",
    "_entity_incoming_edges",
    "_entity_equivalent_class",
]
