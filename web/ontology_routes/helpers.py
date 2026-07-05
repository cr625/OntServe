"""Entity property/semantic-link helpers + constants."""
import logging
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from sqlalchemy import select, func, or_
import rdflib

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from web.ontology_stats import build_stats_context
from web.entity_extraction import extract_entities_from_content
from web.ontology_routes.component_page_rulebook import property_structure_groups


import re as _re


# SKOS / see-also / source crosswalk predicates surfaced on the entity page as links.
_SEMANTIC_LINK_PREDS = [
    ('http://www.w3.org/2004/02/skos/core#exactMatch', 'exactly matches'),
    ('http://www.w3.org/2004/02/skos/core#closeMatch', 'closely matches'),
    ('http://www.w3.org/2004/02/skos/core#broadMatch', 'broader match'),
    ('http://www.w3.org/2004/02/skos/core#relatedMatch', 'related match'),
    ('http://www.w3.org/2000/01/rdf-schema#seeAlso', 'see also'),
    ('http://purl.org/dc/terms/source', 'source'),
]


def _entity_semantic_links(entity, ontology):
    """Crosswalk links (SKOS mappings, seeAlso, source) for an entity, resolved at render
    time from the ontology's current TTL. A target that is itself an OntServe entity becomes
    an INTERNAL link. That is the navigable crosswalk. For example ClientRole links to the IFC
    'Client' term, which carries the IFC and AEC provenance. An external IRI (buildingSMART,
    Wikipedia) becomes an outbound link. This makes a borrowed term's origin reachable by
    clicking, instead of an unexplained mapping that looks invented."""
    try:
        v = db.session.execute(
            select(OntologyVersion).where(
                OntologyVersion.ontology_id == ontology.id,
                OntologyVersion.is_current.is_(True)
            )
        ).scalar_one_or_none()
        if not v or not v.content:
            return []
        g = rdflib.Graph()
        g.parse(data=v.content, format='turtle')
    except Exception:
        return []
    subj = rdflib.URIRef(entity.uri)
    links = []
    seen = set()
    for pred_uri, rel_label in _SEMANTIC_LINK_PREDS:
        for o in g.objects(subj, rdflib.URIRef(pred_uri)):
            tgt = str(o)
            if (rel_label, tgt) in seen:
                continue
            seen.add((rel_label, tgt))
            frag = tgt.rsplit('#', 1)[-1].rsplit('/', 1)[-1]
            ent = db.session.execute(
                select(OntologyEntity).where(OntologyEntity.uri == tgt)
            ).scalar_one_or_none()
            if ent is not None and ent.ontology is not None:
                links.append({
                    'relation': rel_label, 'label': ent.label or frag,
                    'url': url_for('ontology.entity_detail',
                                   ontology_name=ent.ontology.name, fragment=frag),
                    'external': False, 'note': ent.ontology.name,
                })
            elif tgt.startswith('http'):
                links.append({
                    'relation': rel_label, 'label': frag or tgt,
                    'url': tgt, 'external': True, 'note': None,
                })
    return links


_CASE_ONTOLOGY_RE = _re.compile(r'^proethica-case-(\d+)$')


def _entity_using_cases(entity):
    """Case ontologies that instantiate this class. An individual's rdf:type is stored
    as parent_uri, so this is a single equality scan. Computed live rather than
    materialized on the class, so the list stays accurate as new cases are extracted;
    the originating case is recorded separately as firstDiscoveredInCase."""
    if not entity or entity.entity_type != 'class':
        return []
    names = db.session.execute(
        select(Ontology.name)
        .join(OntologyEntity, OntologyEntity.ontology_id == Ontology.id)
        .where(OntologyEntity.parent_uri == entity.uri,
               Ontology.name.like('proethica-case-%'))
        .distinct()
    ).scalars().all()
    cases = []
    for name in names:
        m = _CASE_ONTOLOGY_RE.match(name)
        cases.append({
            'name': name,
            'num': int(m.group(1)) if m else None,
            'url': url_for('ontology.ontology_detail_or_uri_resolution', ontology_name=name),
        })
    cases.sort(key=lambda c: (c['num'] is None, c['num'] or 0, c['name']))
    return cases


# Property keys that represent extraction/provenance metadata (sidebar)
_EXTRACTION_META_KEYS = frozenset({
    'discoveredincase', 'discoveredinpass', 'discoveredinsection',
    'firstdiscoveredat', 'firstdiscoveredincase',
    'generatedattime', 'generatedAtTime',
    'wasattributedto', 'wasGeneratedBy',
    # Commit-time match provenance (proeth-prov). Without these entries the
    # keys fall through to groups['core'] and render as if they were bearer
    # attributes (nine-component correspondence audit, 2026-07-05).
    'matchconfidence', 'matchreasoning', 'matchedontologylabel',
    'matchedontologyclass', 'matchesexisting', 'synthesisliteral',
})

# Property keys that represent textual evidence from the case
_EVIDENCE_KEYS = frozenset({'sourcetext', 'textreferences'})

# Property keys rendered as the entity description (below Definition)
_DESCRIPTION_KEYS = frozenset({'caseinvolvement', 'casecontext'})

# Property keys to skip entirely (redundant or internal).
# dtupleComponent: the D-tuple letter (R/P/O/...) is already shown in the page header.
_SKIP_KEYS = frozenset({'type', 'NamedIndividual', 'rdf_types', 'dtupleComponent'})

# Definition-layer keys -> the Definition card (kept out of the raw "core" property list).
_DEFINITION_LAYER_GROUP = {
    'definition': 'definition',          # skos:definition textual definition (primary)
    'IAO_0000115': 'definition',         # IAO textual definition (primary; same group)
    'IAO_0000119': 'definition_source',  # definition source / citations
    'IAO_0000116': 'editor_note',        # editor note / extraction framing
}

# Human-readable labels for property keys
_PROPERTY_LABELS = {
    'roleclass': 'Role Class',
    'rolecategory': 'Role Category',
    'importance': 'Importance',
    'confidence': 'Confidence',
    'attributes': 'Attributes',
    'relationships': 'Relationships',
    'caseinvolvement': 'Case Involvement',
    'sourcetext': 'Source Text',
    'textreferences': 'Text References',
    'discoveredincase': 'Discovered in Case',
    'discoveredinpass': 'Discovered in Pass',
    'discoveredinsection': 'Discovered in Section',
    'firstdiscoveredat': 'First Discovered',
    'firstdiscoveredincase': 'First Case',
    'generatedattime': 'Generated',
    'generatedAtTime': 'Generated',
    'wasattributedto': 'Attributed To',
    'wasGeneratedBy': 'Generated By',
    'discoveredInCase': 'Discovered in Case',
}


def _humanize_property_key(key):
    """Convert a property key to a human-readable label (shared with the cards)."""
    from web.property_labels import humanize_key
    return humanize_key(key)


def _format_property_value(value):
    """Format a property value for display, handling dict-like strings."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    # Detect Python dict-like strings: {'key': 'value'}
    if s.startswith('{') and s.endswith('}') and "'" in s:
        try:
            import ast
            parsed = ast.literal_eval(s)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, SyntaxError):
            pass
    return value


def _categorize_entity_properties(entity):
    """Categorize entity properties into display groups.

    Returns a dict with keys:
        description: list of (label, value) for case involvement text
        core: list of (label, value) for literal-valued entity attributes
        relationships: list of (predicate_key, [iri, ...]) for IRI-valued
            object-property triples (rendered like the case-page cards)
        evidence: list of (label, value) for source text references
        extraction_meta: list of (label, value) for provenance metadata
    """
    groups = {
        'description': [],
        'definition': [],
        'definition_source': [],
        'editor_note': [],
        'scope_notes': [],
        'core': [],
        'relationships': [],
        'evidence': [],
        'extraction_meta': [],
    }

    if not entity.properties:
        return groups

    for key, value in entity.properties.items():
        # Skip internal keys, the rdf_types list (the materialized direct type is
        # shown as the concept chip in the header instead), the <concept>class
        # key (shown as the "instance of" link instead), and the retired
        # conceptCategory literal (VIEW-1 / VER-1: no longer written, but legacy
        # committed entities still carry it; the concept chip conveys the category).
        if (key in _SKIP_KEYS or key.lower() == 'rdf_types'
                or key.lower() == 'conceptcategory' or key.lower().endswith('class')):
            continue

        # Skip a literal identical to the entity's rdfs:comment: the commit
        # routes one descriptor field (caseInvolvement, concreteExpression,
        # obligationStatement, ...) into the comment AND keeps the field
        # literal, and the Definition card already shows the comment.
        if isinstance(value, str) and value == (getattr(entity, 'comment', None) or ''):
            continue

        # skos:scopeNote is an inherited / contextual definition (e.g. the matched
        # parent class's definition), distinct from the entity's own primary
        # definition (rdfs:comment / skos:definition). Collect the raw values so the
        # Definition card can render them demarcated rather than burying them as a
        # core attribute. Each value carries a leading [source] tag from commit time.
        if key.lower() == 'scopenote':
            vals = value if isinstance(value, list) else [value]
            groups['scope_notes'].extend(str(v) for v in vals if v)
            continue

        # IAO definition layer -> the Definition card, not the raw core list:
        # IAO_0000115 (definition text), IAO_0000119 (definition source), IAO_0000116 (editor note).
        if key in _DEFINITION_LAYER_GROUP:
            vals = value if isinstance(value, list) else [value]
            groups[_DEFINITION_LAYER_GROUP[key]].extend(str(v) for v in vals if v)
            continue

        # IRI-valued triples are object properties (R->P->O / defeasibility
        # edges); group them as relationships, keeping the bare predicate and the
        # target IRIs so the template can link them (mirrors the card view).
        iris = _iri_values(value)
        if iris is not None:
            groups['relationships'].append((key, iris))
            continue

        label = _humanize_property_key(key)
        formatted = _format_property_value(value) if isinstance(value, str) else value
        # Format list items too
        if isinstance(value, list):
            formatted = [_format_property_value(v) for v in value]

        entry = (label, formatted)

        if key.lower() in {k.lower() for k in _DESCRIPTION_KEYS}:
            groups['description'].append(entry)
        elif key.lower() in {k.lower() for k in _EVIDENCE_KEYS}:
            groups['evidence'].append(entry)
        elif key.lower() in {k.lower() for k in _EXTRACTION_META_KEYS}:
            groups['extraction_meta'].append(entry)
        else:
            groups['core'].append(entry)

    return groups


def _iri_values(value):
    """Return a list of IRI strings if value is IRI-valued (object property),
    else None. Mirrors the literal-vs-IRI split used by the case-page cards."""
    if isinstance(value, str) and value.startswith(('http://', 'https://')):
        return [value]
    if isinstance(value, (list, tuple)) and value and isinstance(value[0], str) \
            and value[0].startswith(('http://', 'https://')):
        return [v for v in value if isinstance(v, str) and v.startswith(('http://', 'https://'))]
    return None


def _uri_ends_with_fragment(fragment):
    """SQLAlchemy predicate matching a URI whose final segment is `fragment`,
    delimited by either '#' (proethica URIs) or '/' (OBO/BFO URIs). Lets the
    entity page resolve slash-delimited BFO links such as obo/BFO_0000001."""
    return or_(OntologyEntity.uri.like(f'%#{fragment}'),
               OntologyEntity.uri.like(f'%/{fragment}'))


def _find_entity_by_fragment(ontology, fragment):
    """Find entity by URI fragment (the final segment after # or /)."""
    # Try exact fragment match against the ontology's base URI (hash form).
    if ontology.base_uri:
        full_uri = f"{ontology.base_uri.rstrip('/#')}#{fragment}"
        stmt = select(OntologyEntity).where(
            OntologyEntity.ontology_id == ontology.id,
            OntologyEntity.uri == full_uri
        )
        entity = db.session.execute(stmt).scalar_one_or_none()
        if entity:
            return entity

    # Fallback: URI ending with #fragment or /fragment (OBO/BFO are slash-delimited).
    stmt = select(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        _uri_ends_with_fragment(fragment)
    ).limit(1)
    return db.session.execute(stmt).scalars().first()


def _get_entity_children(ontology, entity):
    """Get entities that have this entity as parent_uri."""
    stmt = select(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        OntologyEntity.parent_uri == entity.uri
    ).order_by(OntologyEntity.label)
    return db.session.execute(stmt).scalars().all()


# ---------------------------------------------------------------------------
# Per-class property schema: which properties apply to instances of a class.
# Object/datatype properties via rdfs:domain on the class or an ancestor, PLUS the
# controlled role-attribute schema declared (descriptively) in the SHACL RolePropertyShape
# for classes that are Roles. This makes the class<->property association visible on the
# class page instead of leaving classes and properties as two disconnected lists.
# ---------------------------------------------------------------------------

_CORE_ROLE_URI = "http://proethica.org/ontology/core#Role"
_ROLE_ATTR_SCHEMA_CACHE = {"mtime": None, "shapes": {}}

# Universal/abstract top classes. A property whose rdfs:domain is one of these applies to
# (almost) everything -- extraction provenance (extractedBy/extractedFromSection/sourceText
# are domained owl:Thing) and over-broad case-structural predicates (hasQuestion is domained
# BFO entity). These are NOT "properties of this class" so they are excluded from the
# per-class schema, even though every class transitively chains to them.
_UNIVERSAL_TOP_URIS = {
    "http://www.w3.org/2002/07/owl#Thing",
    "http://purl.obolibrary.org/obo/BFO_0000001",  # entity
    "http://purl.obolibrary.org/obo/BFO_0000002",  # continuant
    "http://purl.obolibrary.org/obo/BFO_0000003",  # occurrent
}


def _shape_attr_schema(shape_name):
    """Parse a descriptive SHACL property shape (sh:path/sh:name/sh:description/sh:order) by local
    name from validation/shapes/core-shapes.ttl. Cached per shape on file mtime; the shape is the
    single source of truth. Returns [{name, uri, description, order}]."""
    from pathlib import Path
    shapes = Path(__file__).resolve().parents[2] / "validation" / "shapes" / "core-shapes.ttl"
    try:
        mtime = shapes.stat().st_mtime
    except OSError:
        return []
    cache = _ROLE_ATTR_SCHEMA_CACHE
    if cache["mtime"] != mtime:
        cache.update(mtime=mtime, shapes={})  # file changed -> drop all cached shapes
    if shape_name in cache["shapes"]:
        return cache["shapes"][shape_name]
    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    PCSH = rdflib.Namespace("http://proethica.org/shapes/core#")
    attrs = []
    try:
        g = rdflib.Graph()
        g.parse(str(shapes), format="turtle")
        for pshape in g.objects(PCSH[shape_name], SH.property):
            path = next(g.objects(pshape, SH.path), None)
            if path is None:
                continue
            name = next(g.objects(pshape, SH.name), None)
            desc = next(g.objects(pshape, SH.description), None)
            order = next(g.objects(pshape, SH.order), None)
            attrs.append({
                "uri": str(path),
                "name": str(name) if name is not None else str(path).rsplit("#", 1)[-1],
                "description": str(desc) if desc is not None else "",
                "order": int(order) if order is not None else 999,
            })
        attrs.sort(key=lambda a: a["order"])
    except Exception:  # malformed/absent shape must not break the entity page
        attrs = []
    cache["shapes"][shape_name] = attrs
    return attrs


def _shape_target_map():
    """All descriptive NodeShapes in core-shapes.ttl -> their targetClass URI. Cached on file mtime
    (shares the shape cache). Used to pick the shapes that apply along an entity's class chain."""
    from pathlib import Path
    shapes = Path(__file__).resolve().parents[2] / "validation" / "shapes" / "core-shapes.ttl"
    try:
        mtime = shapes.stat().st_mtime
    except OSError:
        return {}
    cache = _ROLE_ATTR_SCHEMA_CACHE
    if cache["mtime"] != mtime:
        cache.update(mtime=mtime, shapes={})
    if "__targets__" in cache["shapes"]:
        return cache["shapes"]["__targets__"]
    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    out = {}
    try:
        g = rdflib.Graph()
        g.parse(str(shapes), format="turtle")
        for s in g.subjects(rdflib.RDF.type, SH.NodeShape):
            tgt = next(g.objects(s, SH.targetClass), None)
            if tgt is not None:
                out[str(s).rsplit("#", 1)[-1]] = str(tgt)
    except Exception:
        out = {}
    cache["shapes"]["__targets__"] = out
    return out


def _class_shape_schemas(ancestor_list):
    """The SHACL property schema for a class = the UNION of the descriptive shapes whose targetClass is in the
    class chain (general -> specific): a base Role gets RoleDefinitionShape; a ProfessionalRole also gets
    ProfessionalRoleDefinitionShape + ProfessionalRolePropertyShape; a StakeholderRole only the universal
    one. *DefinitionShape -> definitional (type-level), *PropertyShape -> bearer (individual). Returns
    (definitional, bearer)."""
    targets = _shape_target_map()
    by_target = {}
    for name, tgt in targets.items():
        by_target.setdefault(tgt, []).append(name)
    definitional, bearer = [], []
    seen_d, seen_b = set(), set()
    for cls in reversed(ancestor_list):  # general (Role) -> specific (ProfessionalRole, ...)
        for name in sorted(by_target.get(cls, [])):
            if name.endswith("DefinitionShape"):
                tier, seen = definitional, seen_d
            elif name.endswith("PropertyShape"):
                tier, seen = bearer, seen_b
            else:
                continue
            for a in _shape_attr_schema(name):
                if a["uri"] not in seen:
                    seen.add(a["uri"])
                    tier.append(a)
    return definitional, bearer


def _class_ancestor_uris(entity, cap=16):
    """Walk the (single-valued) parent_uri chain across ontologies to collect this class's
    ancestor URIs, including itself. Cycle- and depth-guarded."""
    seen, uris, cur = set(), [], entity.uri
    while cur and cur not in seen and len(uris) < cap:
        seen.add(cur)
        uris.append(cur)
        cur = db.session.execute(
            select(OntologyEntity.parent_uri).where(OntologyEntity.uri == cur).limit(1)
        ).scalar_one_or_none()
    return uris


def _uri_fragment(uri):
    return uri.split('#')[-1] if '#' in uri else uri.rstrip('/').split('/')[-1]


def _is_bfo_uri(uri):
    return '/obo/BFO_' in uri or _uri_fragment(uri).startswith('BFO_')


def _canonical_upper_ontology(uri):
    """The canonical home ontology for an upper-level IRI (BFO -> 'bfo', IAO -> 'iao'),
    or None for non-upper IRIs. Upper terms are copied into several stores (the canonical
    bfo/iao ontologies and the proethica-foundation reasoner stub); the hierarchy attributes
    them to their canonical source, not whichever store physically holds the row."""
    frag = _uri_fragment(uri)
    if '/obo/BFO_' in uri or frag.startswith('BFO_'):
        return 'bfo'
    if '/obo/IAO_' in uri or frag.startswith('IAO_'):
        return 'iao'
    return None


def _hierarchy_node(uri, is_current=False):
    """Resolve a class URI to a display node for the Class Hierarchy tree."""
    frag = _uri_fragment(uri)
    # owl:Thing is the formal top; not a stored entity and not linkable.
    if uri.endswith('#Thing') or uri.endswith('/Thing'):
        return {'uri': uri, 'label': 'Thing', 'ontology': None, 'fragment': frag,
                'is_bfo': False, 'purl': None, 'is_current': False, 'linkable': False}
    is_bfo = _is_bfo_uri(uri)
    canon = _canonical_upper_ontology(uri)
    # The same upper-level IRI is copied into several stores (the canonical bfo/iao
    # ontologies plus the proethica-foundation reasoner stub). Resolve to the home ontology:
    # an upper class (BFO/IAO) to its canonical source, otherwise prefer any base ontology
    # over the stub.
    q = (select(OntologyEntity.label, Ontology.name)
         .join(Ontology, Ontology.id == OntologyEntity.ontology_id)
         .where(OntologyEntity.uri == uri))
    if canon:
        q = q.order_by((Ontology.name == canon).desc(), Ontology.is_base.desc(), Ontology.name)
    else:
        q = q.order_by(Ontology.is_base.desc(), Ontology.name)
    row = db.session.execute(q.limit(1)).first()
    label = (row[0] if row and row[0] else frag)
    ontology = row[1] if row else None
    purl = uri if uri.startswith('http://purl.obolibrary.org/obo/') else (
        f'http://purl.obolibrary.org/obo/{frag}' if is_bfo else None)
    return {'uri': uri, 'label': label, 'ontology': ontology, 'fragment': frag,
            'is_bfo': is_bfo, 'purl': purl, 'is_current': is_current,
            'linkable': ontology is not None}


def class_hierarchy(entity, child_cap=25):
    """Build the BFO-rooted ancestry chain (owl:Thing first, this class last) plus this
    class's direct structural subclasses (core + intermediate layers, not per-case ABoxes),
    for the Class Hierarchy display. Reuses the cross-ontology _class_ancestor_uris walk."""
    if getattr(entity, 'entity_type', None) == 'individual':
        # The Class Hierarchy shows classes only. An individual's chain routes
        # through its MOST SPECIFIC rdf:type (parent_uri holds the materialized
        # core type, which would skip e.g. DesignEngineerRole), and the
        # individual itself hangs off the chain as an element-of (instance)
        # line, never as a subclass hop.
        from types import SimpleNamespace
        props = entity.properties
        if isinstance(props, str):
            import json as _json
            try:
                props = _json.loads(props)
            except Exception:
                props = {}
        cand = list((props or {}).get('rdf_types') or [])
        if entity.parent_uri and entity.parent_uri not in cand:
            cand.append(entity.parent_uri)
        cand = [c for c in cand if isinstance(c, str) and c.startswith('http')]
        anc_map = {c: _class_ancestor_uris(SimpleNamespace(uri=c)) for c in cand}
        # A candidate that is a proper ancestor of another candidate is less
        # specific; drop it. Among the survivors take the deepest chain.
        proper_ancestors = set()
        for ancs in anc_map.values():
            proper_ancestors.update(ancs[1:])
        specific = [c for c in cand if c not in proper_ancestors] or cand
        specific.sort(key=lambda c: (-len(anc_map.get(c, [])), c))
        anc_uris = anc_map.get(specific[0], []) if specific else []
        chain = [_hierarchy_node(u) for u in reversed(anc_uris)]
        node = _hierarchy_node(entity.uri, is_current=True)
        node['is_individual'] = True
        chain.append(node)
    else:
        anc_uris = _class_ancestor_uris(entity)      # [entity.uri, parent, ..., owl:Thing]
        chain = [_hierarchy_node(u, is_current=(u == entity.uri)) for u in reversed(anc_uris)]
    rows = db.session.execute(
        select(OntologyEntity.uri, OntologyEntity.label, Ontology.name, OntologyEntity.properties)
        .join(Ontology, Ontology.id == OntologyEntity.ontology_id)
        .where(OntologyEntity.parent_uri == entity.uri,
               OntologyEntity.entity_type == 'class',
               ~Ontology.name.like('proethica-case-%'),
               # Hide owl:deprecated subclasses (the retired Decision Point / Ethical Question bridge
               # stubs etc.) from the tree. They stay in the graph for the equivalentClass bridge but
               # should not clutter the Class Hierarchy -- mirrors the deprecated filters in the
               # domain-props + Referenced-By sections below (op('->>') JSON access per line 521).
               OntologyEntity.properties.op('->>')('deprecated').is_distinct_from('true'))
        .order_by(Ontology.name, OntologyEntity.label).limit(child_cap + 1)
    ).all()

    def _axes(props):
        # archetypeAxis (occupational/relational) + specializationAxis (discipline/function), so the
        # Class Hierarchy can show WHY a subclass sits where it does, not just list it flat.
        if isinstance(props, str):
            import json as _json
            try:
                props = _json.loads(props)
            except Exception:
                props = {}
        p = props or {}
        return ((p.get('archetypeAxis') or '').strip() or None,
                (p.get('specializationAxis') or '').strip() or None)

    children = []
    for (u, lbl, name, props) in rows[:child_cap]:
        arch, spec = _axes(props)  # now SKOS concept URIs (RoleArchetypeAxis/RoleSpecialization scheme)
        children.append({'uri': u, 'label': lbl or _uri_fragment(u),
                         'fragment': _uri_fragment(u), 'ontology': name,
                         'archetype_axis': arch, 'specialization_axis': spec})

    # The axis values are SKOS concept URIs. Resolve each to its concept so the badge shows the concept's
    # skos:notation (not the raw URI), links to the concept page, and shows its definition on hover. Then
    # the axis fields hold the notation (for display + the rank sort). Scoped query; fires only when tagged.
    axis_uris = {c['archetype_axis'] for c in children} | {c['specialization_axis'] for c in children}
    axis_uris.discard(None)
    cmap = {}
    if axis_uris:
        crows = db.session.execute(
            select(OntologyEntity.uri, OntologyEntity.comment, Ontology.name,
                   OntologyEntity.properties.op('->>')('notation').label('notation'))
            .join(Ontology, Ontology.id == OntologyEntity.ontology_id)
            .where(OntologyEntity.uri.in_(list(axis_uris)))
        ).all()
        cmap = {r.uri: {'fragment': _uri_fragment(r.uri), 'ontology': r.name,
                        'notation': r.notation or _uri_fragment(r.uri),
                        'definition': (r.comment or '')} for r in crows}
    for c in children:
        ac, sc = cmap.get(c['archetype_axis']), cmap.get(c['specialization_axis'])
        c['archetype_concept'], c['specialization_concept'] = ac, sc
        c['archetype_axis'] = ac['notation'] if ac else None        # display + rank by the notation
        c['specialization_axis'] = sc['notation'] if sc else None

    # Group by axis so like sits with like (occupational discipline, then function, then unspecialized,
    # then relational), each still alphabetized within its group.
    _rank = {('occupational', 'discipline'): 0, ('occupational', 'function'): 1, ('occupational', None): 2}
    children.sort(key=lambda c: (_rank.get((c['archetype_axis'], c['specialization_axis']), 3),
                                 (c['label'] or '').lower()))
    return {'chain': chain, 'children': children, 'children_overflow': len(rows) > child_cap}


def _entity_disjoint_classes(entity, ontology):
    """All classes disjoint with this entity: explicit owl:disjointWith (either direction) PLUS the
    co-members of any owl:AllDisjointClasses it belongs to. Parsed from the current version content,
    because the AllDisjointClasses node is not stored as an entity triple (so the entity page would
    otherwise show only the explicit pairwise disjointness)."""
    try:
        from rdflib.collection import Collection
        v = db.session.execute(
            select(OntologyVersion).where(
                OntologyVersion.ontology_id == ontology.id, OntologyVersion.is_current.is_(True)
            )).scalar_one_or_none()
        if not (v and v.content):
            return []
        g = rdflib.Graph()
        g.parse(data=v.content, format='turtle')
        subj = rdflib.URIRef(entity.uri)
        OWL, RDF = rdflib.OWL, rdflib.RDF
        disjoint = set()
        for o in g.objects(subj, OWL.disjointWith):
            if isinstance(o, rdflib.URIRef):
                disjoint.add(str(o))
        for s in g.subjects(OWL.disjointWith, subj):
            if isinstance(s, rdflib.URIRef):
                disjoint.add(str(s))
        for adc in g.subjects(RDF.type, OWL.AllDisjointClasses):
            ml = next(g.objects(adc, OWL.members), None)
            if ml is None:
                continue
            members = list(Collection(g, ml))
            if subj in members:
                for m in members:
                    if isinstance(m, rdflib.URIRef) and m != subj:
                        disjoint.add(str(m))
        disjoint.discard(str(subj))
        out = []
        for uri in disjoint:
            frag = _uri_fragment(uri)
            row = db.session.execute(
                select(OntologyEntity.label, Ontology.name)
                .join(Ontology, Ontology.id == OntologyEntity.ontology_id)
                .where(OntologyEntity.uri == uri).limit(1)).first()
            out.append({"uri": uri, "fragment": frag,
                        "label": (row[0] if row and row[0] else frag),
                        "ontology": row[1] if row else ontology.name})
        out.sort(key=lambda d: d["label"].lower())
        return out
    except Exception:
        return []


def _entity_incoming_edges(entity, ontology):
    """Object-property edges POINTING AT this entity in the current ontology
    version: [(predicate_localname, [{uri, fragment, label}])]. The commit
    writes several families one-directional (Agent hasRole facet, Obligation
    requiresCapability, obligatedParty, isPerformedBy ...), so without this an
    individual never shows who bears/requires/performs it (correspondence
    audit T8, 2026-07-05). Mirrors _entity_disjoint_classes: parsed from the
    version content because inverse edges are not stored on the entity row."""
    try:
        v = db.session.execute(
            select(OntologyVersion).where(
                OntologyVersion.ontology_id == ontology.id, OntologyVersion.is_current.is_(True)
            )).scalar_one_or_none()
        if not (v and v.content):
            return []
        g = rdflib.Graph()
        g.parse(data=v.content, format='turtle')
        obj = rdflib.URIRef(entity.uri)
        skip = {str(rdflib.RDF.type), str(rdflib.OWL.disjointWith),
                str(rdflib.RDFS.subClassOf), str(rdflib.RDFS.domain),
                str(rdflib.RDFS.range), str(rdflib.OWL.inverseOf)}
        by_predicate = {}
        for s, p, _ in g.triples((None, None, obj)):
            if not isinstance(s, rdflib.URIRef) or str(p) in skip:
                continue
            # Skip provenance plumbing (prov:, time:) so the section shows
            # domain edges, not derivation nodes.
            if str(p).startswith(('http://www.w3.org/ns/prov#', 'http://www.w3.org/2006/time#')):
                continue
            by_predicate.setdefault(_uri_fragment(str(p)), set()).add(str(s))
        out = []
        for pred, subject_uris in sorted(by_predicate.items()):
            subjects = []
            for uri in sorted(subject_uris):
                frag = _uri_fragment(uri)
                row = db.session.execute(
                    select(OntologyEntity.label)
                    .where(OntologyEntity.uri == uri).limit(1)).first()
                subjects.append({"uri": uri, "fragment": frag,
                                 "label": (row[0] if row and row[0] else frag)})
            out.append((pred, subjects))
        return out
    except Exception:
        return []


def _entity_equivalent_class(entity, ontology):
    """For a DEFINED class (owl:equivalentClass with an owl:intersectionOf), the human-readable
    definition: the ordered conjuncts -- named classes and property restrictions (onProperty +
    some/only filler). Parsed from the current version content because the intersection/restriction
    nodes are anonymous blank nodes (not stored as entity triples). Returns {'conjuncts': [...]} or
    None. Mirrors _entity_disjoint_classes."""
    try:
        from rdflib.collection import Collection
        v = db.session.execute(
            select(OntologyVersion).where(
                OntologyVersion.ontology_id == ontology.id, OntologyVersion.is_current.is_(True)
            )).scalar_one_or_none()
        if not (v and v.content):
            return None
        g = rdflib.Graph()
        g.parse(data=v.content, format='turtle')
        OWL = rdflib.OWL
        subj = rdflib.URIRef(entity.uri)

        def _term(node):
            """A linkable term dict for a URI (class or property), else a bare label."""
            if not isinstance(node, rdflib.URIRef):
                return {"label": str(node)}
            uri = str(node)
            frag = _uri_fragment(uri)
            row = db.session.execute(
                select(OntologyEntity.label, Ontology.name)
                .join(Ontology, Ontology.id == OntologyEntity.ontology_id)
                .where(OntologyEntity.uri == uri).limit(1)).first()
            return {"uri": uri, "fragment": frag,
                    "label": (row[0] if row and row[0] else _humanize_property_key(frag)),
                    "ontology": row[1] if row else None}

        for eq in g.objects(subj, OWL.equivalentClass):
            inter = next(g.objects(eq, OWL.intersectionOf), None)
            if inter is None:
                continue
            conjuncts = []
            for m in Collection(g, inter):
                if isinstance(m, rdflib.URIRef):
                    t = _term(m); t["kind"] = "class"; conjuncts.append(t)
                    continue
                prop = next(g.objects(m, OWL.onProperty), None)
                some = next(g.objects(m, OWL.someValuesFrom), None)
                allv = next(g.objects(m, OWL.allValuesFrom), None)
                quant, filler = ("some", some) if some is not None else ("only", allv)
                if prop is None or filler is None:
                    continue
                conjuncts.append({"kind": "restriction", "quantifier": quant,
                                  "property": _term(prop), "filler": _term(filler)})
            if conjuncts:
                return {"conjuncts": conjuncts}
        return None
    except Exception:
        return None


def class_property_schema(entity):
    """For a CLASS entity, the property schema applicable to its instances:
    object/datatype properties whose rdfs:domain is this class or an ancestor, plus -- for
    roles (core:Role in the ancestor chain) -- the controlled role-attribute schema from the
    SHACL RolePropertyShape (those properties are deliberately domain-less / leak-safe).
    Read-only. Returns None for non-class entities or when nothing applies."""
    if not entity or entity.entity_type != "class":
        return None
    # Drop the universal/abstract tops: properties domained to them (extraction provenance,
    # over-broad structural predicates) apply to everything, not specifically to this class.
    anc_list = _class_ancestor_uris(entity)
    ancestor_set = set(anc_list) - _UNIVERSAL_TOP_URIS

    prop_rows = db.session.execute(
        select(OntologyEntity).where(OntologyEntity.entity_type == "property")
    ).scalars().all()

    def _local(u):
        return u.rsplit("#", 1)[-1].rsplit("/", 1)[-1] if isinstance(u, str) else None

    # When two properties share a local name (e.g. an intermediate-defined involvesRole with domain
    # DecisionPoint and a case-defined one with domain Case), the property tables can show only one row.
    # Rank by ontology so the DEFINITIONAL declaration wins over a case-ontology duplicate, with the URI as
    # a deterministic final tiebreak -- otherwise the displayed row depends on DB row order and flips on every
    # re-extraction, and a core/intermediate entity page can surface a case-specific edge.
    ont_name_by_id = dict(db.session.execute(select(Ontology.id, Ontology.name)).all())

    def _ref_rank(p):
        ont = ont_name_by_id.get(p.ontology_id, "") or ""
        return (1 if ont.startswith("proethica-case") else 0, ont, p.uri)

    def _pick_best(p, name, best):
        """Keep the best-ranked property per local name; True if p is the (new) winner."""
        rank = _ref_rank(p)
        cur = best.get(name)
        if cur is None or rank < cur[0]:
            best[name] = (rank, p)
            return True
        return False

    domain_best = {}
    for p in prop_rows:
        dom = p.domain
        dom_uris = dom if isinstance(dom, list) else [dom]
        if not any(isinstance(d, str) and d in ancestor_set for d in dom_uris):
            continue
        name = _local(p.uri)
        if not name or (p.properties or {}).get('deprecated'):
            continue  # owl:deprecated property (e.g. the retired role-to-role duplicates); hide from the page
        _pick_best(p, name, domain_best)
    domain_props = []
    for name, (_, p) in domain_best.items():
        dom = p.domain
        dom_uris = dom if isinstance(dom, list) else [dom]
        rng = p.range
        rng_uri = (rng[0] if isinstance(rng, list) and rng else rng) if rng else None
        domain_props.append({
            "name": name,
            "uri": p.uri,
            "comment": (p.comment or ""),
            "range_name": _local(rng_uri),
            "range_uri": rng_uri if isinstance(rng_uri, str) else None,
            "on_self": any(isinstance(d, str) and d == entity.uri for d in dom_uris),
        })
    domain_props.sort(key=lambda x: (not x["on_self"], x["name"].lower()))

    # Incoming: properties whose rdfs:range is this class or a (non-universal) ancestor -- the edges that
    # point AT instances of this class (its in-degree). Mirrors domain_props but keyed on range, and
    # records the source class (the property's rdfs:domain) as "from".
    referenced_best = {}
    for p in prop_rows:
        rng = p.range
        rng_uris = rng if isinstance(rng, list) else [rng]
        if not any(isinstance(r, str) and r in ancestor_set for r in rng_uris):
            continue
        name = _local(p.uri)
        if not name or (p.properties or {}).get('deprecated'):
            continue  # owl:deprecated property; hide from Referenced-By (mirrors the domain_props filter)
        _pick_best(p, name, referenced_best)
    referenced_by = []
    for name, (_, p) in referenced_best.items():
        rng = p.range
        rng_uris = rng if isinstance(rng, list) else [rng]
        on_self = any(isinstance(r, str) and r == entity.uri for r in rng_uris)
        dom = p.domain
        # A union domain (e.g. initiates: (Action or Event)) is stored as a list; emit one From row per
        # named member so each renders as a proper class, not the anonymous-union blank-node id.
        dom_uris = dom if isinstance(dom, list) else ([dom] if dom else [None])
        for dom_uri in dom_uris:
            referenced_by.append({
                "name": name,
                "uri": p.uri,
                "comment": (p.comment or ""),
                "from_name": _local(dom_uri),
                "from_uri": dom_uri if isinstance(dom_uri, str) else None,
                "on_self": on_self,
            })
    referenced_by.sort(key=lambda x: (not x["on_self"], (x["from_name"] or "").lower(), x["name"].lower()))

    # Resolve the actual ontology of each referenced-by source class and property so the macro links
    # them cross-ontology correctly (e.g. derivedFromPrinciple lives in proethica-intermediate, not core).
    if referenced_by:
        link_uris = {r["uri"] for r in referenced_by} | {r["from_uri"] for r in referenced_by if r["from_uri"]}
        uri_to_ont = dict(db.session.execute(
            select(OntologyEntity.uri, Ontology.name)
            .join(Ontology, OntologyEntity.ontology_id == Ontology.id)
            .where(OntologyEntity.uri.in_(list(link_uris)))
        ).all())
        for r in referenced_by:
            r["prop_ontology"] = uri_to_ont.get(r["uri"])
            r["from_ontology"] = uri_to_ont.get(r["from_uri"])

    # SHACL definitional/bearer schemas for ANY class a shape targets along its chain. Currently only
    # roles have such shapes, so non-role classes get empty lists; written generically so a future
    # per-component shape (e.g. a PrincipleDefinitionShape) renders through the same path with no change.
    definitional, bearer = _class_shape_schemas(anc_list)
    # Copy (the attr dicts come from a shared cache) and resolve each definitional/bearer attribute's
    # sh:path property to its home ontology, so the macro can LINK the property each field maps to --
    # demystifying where the schema comes from. render_iri_target falls back to a code label (full IRI
    # on hover) when the property is not a stored entity.
    definitional = [dict(a) for a in definitional]
    bearer = [dict(a) for a in bearer]
    attr_uris = {a["uri"] for a in definitional} | {a["uri"] for a in bearer}
    if attr_uris:
        attr_ont = dict(db.session.execute(
            select(OntologyEntity.uri, Ontology.name)
            .join(Ontology, OntologyEntity.ontology_id == Ontology.id)
            .where(OntologyEntity.uri.in_(list(attr_uris)))
        ).all())
        for a in definitional + bearer:
            a["path_ontology"] = attr_ont.get(a["uri"])

    # Merge the data rows with the view chrome from the component-page rulebook (the single source of
    # the group labels/badges/tooltips, harmonized across all nine component pages). The macro renders
    # the returned groups generically.
    groups = property_structure_groups(
        {"domain_props": domain_props, "definitional": definitional,
         "bearer": bearer, "referenced_by": referenced_by}
    )
    if not groups:
        return None
    return {"groups": groups}


def _class_target_shapes_graph(entity):
    """rdflib.Graph of the descriptive SHACL shapes (validation/shapes/core-shapes.ttl) whose
    sh:targetClass is this class or an ancestor -- the shape node plus its sh:property blank-node
    closure. Returned separately so the entity TTL can APPEND it: SHACL shapes are NOT entailed by the
    ontology (a separate graph that must travel with the data to be applied), so without this the
    exported TTL would omit the definitional field schema the entity page shows."""
    out = rdflib.Graph()
    if not entity or getattr(entity, "entity_type", None) != "class":
        return out
    try:
        from pathlib import Path
        shapes_path = Path(__file__).resolve().parents[2] / "validation" / "shapes" / "core-shapes.ttl"
        anc = set(_class_ancestor_uris(entity))
        SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
        sg = rdflib.Graph()
        sg.parse(str(shapes_path), format="turtle")
        for prefix, ns in sg.namespaces():
            out.bind(prefix, ns)
        for shape in sg.subjects(rdflib.RDF.type, SH.NodeShape):
            tgt = next(sg.objects(shape, SH.targetClass), None)
            if tgt is None or str(tgt) not in anc:
                continue
            for p, o in sg.predicate_objects(shape):
                out.add((shape, p, o))
                if isinstance(o, rdflib.BNode):  # the sh:property nodes
                    for p2, o2 in sg.predicate_objects(o):
                        out.add((o, p2, o2))
    except Exception:
        pass
    return out


def _generate_entity_ttl_display(entity, ontology):
    """TTL for display. Render the entity's ACTUAL source triples from the ontology's
    current version. This way skos:exactMatch, skos:inScheme, skos:Concept typing,
    skos:definition, and dcterms:source all show, not just the few fields the entity
    extractor stored, PLUS the descriptive SHACL shapes targeting the class (so the TTL is
    self-contained: the class and its definitional field schema). Fall back to the reconstruction
    if the source cannot be read."""
    try:
        v = db.session.execute(
            select(OntologyVersion).where(
                OntologyVersion.ontology_id == ontology.id,
                OntologyVersion.is_current.is_(True)
            )
        ).scalar_one_or_none()
        if v and v.content:
            g = rdflib.Graph()
            g.parse(data=v.content, format='turtle')
            subj = rdflib.URIRef(entity.uri)
            sub = rdflib.Graph()
            for prefix, ns in g.namespaces():
                sub.bind(prefix, ns)
            for p, o in g.predicate_objects(subj):
                sub.add((subj, p, o))
                # Pull one level of blank-node closure so owl:Restriction nodes render.
                if isinstance(o, rdflib.BNode):
                    for p2, o2 in g.predicate_objects(o):
                        sub.add((o, p2, o2))
            # Append the descriptive SHACL shapes targeting this class (self-contained TTL): SHACL is
            # a separate graph (not entailed), so the field schema would otherwise be absent.
            shapes_g = _class_target_shapes_graph(entity)
            if len(shapes_g):
                for prefix, ns in shapes_g.namespaces():
                    sub.bind(prefix, ns)
                for t in shapes_g:
                    sub.add(t)
            if len(sub):
                return sub.serialize(format='turtle')
    except Exception:
        pass
    from web.rdf_helpers import generate_entity_ttl
    return generate_entity_ttl(entity, ontology)


def _extract_entity_from_ttl(ttl_content, ontology, fragment):
    """Extract a single entity's data from TTL content for versioned display.

    Returns a dict-like object with entity attributes, or None if not found.
    """
    g = rdflib.Graph()
    try:
        g.parse(data=ttl_content, format='turtle')
    except Exception:
        return None

    # Find the entity URI by fragment
    target_uri = None
    for s in g.subjects():
        s_str = str(s)
        if s_str.endswith(f'#{fragment}'):
            target_uri = s
            break

    if not target_uri:
        return None

    from rdflib import RDF, RDFS, OWL

    # Determine type
    entity_type = 'class'
    for type_uri in g.objects(target_uri, RDF.type):
        if type_uri == OWL.ObjectProperty or type_uri == OWL.DatatypeProperty:
            entity_type = 'property'
        elif type_uri == OWL.NamedIndividual:
            entity_type = 'individual'

    label = next(g.objects(target_uri, RDFS.label), None)
    comment = next(g.objects(target_uri, RDFS.comment), None)
    parent = next(g.objects(target_uri, RDFS.subClassOf), None)
    domain = next(g.objects(target_uri, RDFS.domain), None)
    range_val = next(g.objects(target_uri, RDFS.range), None)

    uri_str = str(target_uri)
    label_str = str(label) if label else None
    comment_str = str(comment) if comment else None
    content_hash = OntologyEntity.compute_content_hash(uri_str, label_str, comment_str)

    # Build TTL snippet for display
    from web.rdf_helpers import generate_entity_ttl

    class _EntityProxy:
        """Lightweight proxy mimicking OntologyEntity for TTL generation."""
        pass

    proxy = _EntityProxy()
    proxy.uri = uri_str
    proxy.label = label_str
    proxy.comment = comment_str
    proxy.entity_type = entity_type
    proxy.parent_uri = str(parent) if parent else None
    proxy.domain = str(domain) if domain else None
    proxy.range = str(range_val) if range_val else None
    proxy.properties = None
    proxy.content_hash = content_hash
    proxy.updated_at = None
    proxy.id = None
    proxy._ttl = generate_entity_ttl(proxy, ontology)

    return proxy
