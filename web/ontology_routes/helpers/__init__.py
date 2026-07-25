"""Entity property/semantic-link helpers + constants.

Split into submodules (hierarchy, shapes, display, links). This package
`__init__` re-exports only the names actually imported from OUTSIDE this
package (web/uri_resolution.py, web/ontology_routes/__init__.py,
web/ontology_routes/detail_routes.py, tests) -- all public (no leading
underscore). Names used only across submodules are imported directly
between submodules (e.g. `from .hierarchy import ...` in links.py); names
used only within one submodule stay local to it and are not re-exported
here.
"""
from .hierarchy import (
    get_entity_children,
    class_hierarchy,
    entity_secondary_parents,
)
from .shapes import (
    shape_attr_schema,
    class_property_schema,
)
from .display import (
    categorize_entity_properties,
    iri_values,
    generate_entity_ttl_display,
    extract_entity_from_ttl,
)
from .links import (
    entity_semantic_links,
    entity_using_cases,
    uri_ends_with_fragment,
    find_entity_by_fragment,
    definitional_entity_for_uri,
    entity_disjoint_classes,
    entity_case_provenance,
    entity_incoming_edges,
    entity_equivalent_class,
)

__all__ = [
    # hierarchy
    "get_entity_children",
    "class_hierarchy",
    "entity_secondary_parents",
    # shapes
    "shape_attr_schema",
    "class_property_schema",
    # display
    "categorize_entity_properties",
    "iri_values",
    "generate_entity_ttl_display",
    "extract_entity_from_ttl",
    # links
    "entity_semantic_links",
    "entity_using_cases",
    "uri_ends_with_fragment",
    "find_entity_by_fragment",
    "definitional_entity_for_uri",
    "entity_disjoint_classes",
    "entity_case_provenance",
    "entity_incoming_edges",
    "entity_equivalent_class",
]
