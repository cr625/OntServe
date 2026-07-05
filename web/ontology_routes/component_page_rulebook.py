"""Component-page view rulebook.

Single source of truth for the PRESENTATION conventions of the nine core-component entity pages
(Role, Principle, Obligation, State, Resource, Action, Event, Capability, Constraint) as rendered by
``web/templates/macros/component_sections.html``. Edit the wording here once to change it across all
nine pages at the same time.

Division of responsibility (the harmonization contract):
  - STRUCTURE comes from the ontology + SHACL data: which property groups exist, the attribute names
    and descriptions (``rdfs:domain`` for relations; the descriptive SHACL shapes for definitional and
    bearer attributes). ``class_property_schema`` in ``helpers.py`` reads that.
  - CHROME comes from this file: the human-facing group label, the badge, the (i) hover tooltip, the
    Bootstrap colour, and the table layout. ``class_property_schema`` merges each group's data rows with
    its spec below, and the macro renders generically by iterating the merged groups.

When working on the core ontology entity pages, reference THIS file together with
``macros/component_sections.html``; do not reintroduce per-component or per-page wording in the macro or
the template. New per-component backing (e.g. a future ``PrincipleDefinitionShape``) needs no change
here: it simply makes the matching group's data non-empty, so the group appears with the chrome below.

Tooltip strings may contain inline HTML (``<code>``, ``<strong>``, ``<em>``); the macro renders them
with ``|safe`` into a Bootstrap ``data-bs-html`` tooltip. Do not use double quotes in tooltip text (it
is placed in a ``title="..."`` attribute).
"""

# Property Structure section: the ordered property-schema groups shown for a class.
# Each entry's ROWS are filled in by class_property_schema from the ontology/SHACL data keyed by
# ``data_key``; everything else here is the fixed, harmonized view chrome.
#   data_key     -- key in the schema-data dict whose rows feed this group
#   label        -- group heading
#   colour       -- Bootstrap contextual colour (border / text / icon)
#   badge        -- pill badge naming the backing (e.g. the SHACL shape or rdfs:domain)
#   badge2       -- optional second pill badge
#   kind         -- table layout: 'relations' (Property/Range/Description), 'attributes'
#                   (Attribute/Description), or 'referenced_by' (From/Property/Description, incoming edges)
#   tooltip      -- (i) hover text; the single explanation for the group (HTML allowed, no double quotes)
#   multi_suffix -- optional extra tooltip sentence appended only when the page shows more than one group
PROPERTY_STRUCTURE_GROUPS = [
    {
        "data_key": "domain_props",
        "label": "Object and Data Properties",
        "colour": "success",
        "badge": "rdfs:domain on this class or ancestor",
        "kind": "relations",
        "tooltip": (
            "Object and data properties whose <code>rdfs:domain</code> is this class or an ancestor. "
            "On an instance, an object property is a graph <strong>edge</strong> to another entity "
            "(its <em>Range</em>) and a data property is a literal value."
        ),
        "multi_suffix": (
            " Unlike the schemas below, these are relations in the graph, not declared attribute fields."
        ),
    },
    {
        "data_key": "definitional",
        "label": "Definitional Attributes",
        "colour": "primary",
        "badge": "SHACL definitional shape",
        "kind": "attributes",
        "tooltip": (
            "The literature-grounded fields that individuate this class as a <strong>type</strong>. "
            "A controlled schema (the same fields for every instance of the type), filled in on the class. "
            "Declared by the SHACL definition shape(s) targeting this class, browsable in the "
            "<a href=\"/ontology/proethica-shapes\">proethica-shapes</a> ontology "
            "(source: <code>validation/shapes/core-shapes.ttl</code>); the shape is included in the TTL "
            "below, and each row's <em>Property</em> column links the underlying <code>sh:path</code>."
        ),
    },
    {
        "data_key": "bearer",
        "label": "Bearer Attributes",
        "colour": "secondary",
        "badge": "SHACL property shape",
        "badge2": "individual data",
        "kind": "attributes",
        "tooltip": (
            "The controlled schema of per-individual facts an instance may carry. These do "
            "<strong>not</strong> define the type; their values are on the <em>individual</em>, not the class. "
            "Declared by the SHACL property shape targeting this class, browsable in the "
            "<a href=\"/ontology/proethica-shapes\">proethica-shapes</a> ontology "
            "(source: <code>validation/shapes/core-shapes.ttl</code>; included in the TTL below)."
        ),
    },
    {
        "data_key": "referenced_by",
        "label": "Referenced By",
        "colour": "info",
        "badge": "rdfs:range on this class or ancestor",
        "kind": "referenced_by",
        "tooltip": (
            "Incoming edges: object properties whose <strong>range</strong> is this class or an ancestor, "
            "so they point AT instances of this class. <em>From</em> is the class that declares the property "
            "(its <code>rdfs:domain</code>); that is usually another class, but can be this class itself. "
            "This is the in-degree a domain-only view would hide, e.g. a Principle is referenced by Role, "
            "Obligation and Action."
        ),
    },
]


def property_structure_groups(schema_data):
    """Merge each rulebook group spec with its data rows, in rulebook order, dropping empty groups.

    ``schema_data`` maps each group's ``data_key`` to a list of row dicts. Returns a list of
    ``{**spec, "rows": [...]}`` for the groups that have data, ready for the macro to render.
    """
    merged = []
    for spec in PROPERTY_STRUCTURE_GROUPS:
        rows = schema_data.get(spec["data_key"])
        if rows:
            merged.append({**spec, "rows": rows})
    return merged
