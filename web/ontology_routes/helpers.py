"""Entity property/semantic-link helpers + constants."""
import logging
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from sqlalchemy import select, func
import rdflib

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from web.ontology_stats import build_stats_context
from web.entity_extraction import extract_entities_from_content


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
})

# Property keys that represent textual evidence from the case
_EVIDENCE_KEYS = frozenset({'sourcetext', 'textreferences'})

# Property keys rendered as the entity description (below Definition)
_DESCRIPTION_KEYS = frozenset({'caseinvolvement'})

# Property keys to skip entirely (redundant or internal)
_SKIP_KEYS = frozenset({'type', 'NamedIndividual', 'rdf_types'})

# Human-readable labels for property keys
_PROPERTY_LABELS = {
    'conceptCategory': 'Concept Category',
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
        'scope_notes': [],
        'core': [],
        'relationships': [],
        'evidence': [],
        'extraction_meta': [],
    }

    if not entity.properties:
        return groups

    for key, value in entity.properties.items():
        # Skip internal keys, the redundant conceptCategory (shown as the concept
        # chip in the header instead), and the <concept>class key (shown as the
        # "instance of" link instead).
        if key in _SKIP_KEYS or key.lower() == 'conceptcategory' or key.lower().endswith('class'):
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


def _find_entity_by_fragment(ontology, fragment):
    """Find entity by URI fragment (the part after #)."""
    # Try exact fragment match against known base URIs
    if ontology.base_uri:
        full_uri = f"{ontology.base_uri.rstrip('/#')}#{fragment}"
        stmt = select(OntologyEntity).where(
            OntologyEntity.ontology_id == ontology.id,
            OntologyEntity.uri == full_uri
        )
        entity = db.session.execute(stmt).scalar_one_or_none()
        if entity:
            return entity

    # Fallback: search by URI ending with #fragment
    stmt = select(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        OntologyEntity.uri.like(f'%#{fragment}')
    )
    return db.session.execute(stmt).scalar_one_or_none()


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
_ROLE_ATTR_SCHEMA_CACHE = {"mtime": None, "attrs": None}


def _role_attr_schema():
    """The controlled role-attribute schema, parsed from the descriptive
    pcsh:RolePropertyShape in validation/shapes/core-shapes.ttl. Cached on file mtime.
    Returns [{name, uri, description, order}] (the shape is the single source of truth)."""
    from pathlib import Path
    shapes = Path(__file__).resolve().parents[2] / "validation" / "shapes" / "core-shapes.ttl"
    try:
        mtime = shapes.stat().st_mtime
    except OSError:
        return []
    if _ROLE_ATTR_SCHEMA_CACHE["mtime"] == mtime and _ROLE_ATTR_SCHEMA_CACHE["attrs"] is not None:
        return _ROLE_ATTR_SCHEMA_CACHE["attrs"]
    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    PCSH = rdflib.Namespace("http://proethica.org/shapes/core#")
    attrs = []
    try:
        g = rdflib.Graph()
        g.parse(str(shapes), format="turtle")
        for pshape in g.objects(PCSH["RolePropertyShape"], SH.property):
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
    _ROLE_ATTR_SCHEMA_CACHE.update(mtime=mtime, attrs=attrs)
    return attrs


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


def class_property_schema(entity):
    """For a CLASS entity, the property schema applicable to its instances:
    object/datatype properties whose rdfs:domain is this class or an ancestor, plus -- for
    roles (core:Role in the ancestor chain) -- the controlled role-attribute schema from the
    SHACL RolePropertyShape (those properties are deliberately domain-less / leak-safe).
    Read-only. Returns None for non-class entities or when nothing applies."""
    if not entity or entity.entity_type != "class":
        return None
    ancestor_set = set(_class_ancestor_uris(entity))

    prop_rows = db.session.execute(
        select(OntologyEntity).where(
            OntologyEntity.entity_type == "property",
            OntologyEntity.domain.isnot(None),
        )
    ).scalars().all()

    def _local(u):
        return u.rsplit("#", 1)[-1].rsplit("/", 1)[-1] if isinstance(u, str) else None

    domain_props, seen = [], set()
    for p in prop_rows:
        dom = p.domain
        dom_uris = dom if isinstance(dom, list) else [dom]
        if not any(isinstance(d, str) and d in ancestor_set for d in dom_uris):
            continue
        name = _local(p.uri)
        if not name or name in seen:
            continue
        seen.add(name)
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

    is_role = _CORE_ROLE_URI in ancestor_set
    role_attrs = _role_attr_schema() if is_role else []

    if not (domain_props or role_attrs):
        return None
    return {"is_role": is_role, "domain_props": domain_props, "role_attrs": role_attrs}


def _generate_entity_ttl_display(entity, ontology):
    """TTL for display. Render the entity's ACTUAL source triples from the ontology's
    current version. This way skos:exactMatch, skos:inScheme, skos:Concept typing,
    skos:definition, and dcterms:source all show, not just the few fields the entity
    extractor stored. Fall back to the reconstruction if the source cannot be read."""
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
