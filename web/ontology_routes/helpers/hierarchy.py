"""Class hierarchy + ancestor-closure helpers (split from helpers.py)."""
from sqlalchemy import select, or_

from web.models import db, Ontology, OntologyEntity


def _base_subclass_closure(uri):
    """The class URI plus its named descendants across the BASE ontologies (via
    parent_uri or a secondary rdf_superclasses parent). Lets a mid-chain class
    (Guideline) count the case individuals typed to its descendants (EthicalCode)."""
    rows = db.session.execute(
        select(OntologyEntity.uri, OntologyEntity.parent_uri, OntologyEntity.properties)
        .join(Ontology, OntologyEntity.ontology_id == Ontology.id)
        # Everything except the case ABoxes: proethica-core carries is_base=false
        # (ontology_type='core'), so an is_base filter dropped the core layer and
        # the closure over core classes found no subclasses (A/E properties review;
        # Event reported 10 cases instead of 15 on its first real test).
        .where(OntologyEntity.entity_type == 'class',
               ~Ontology.name.like('proethica-case-%'))
    ).all()
    children = {}
    for u, parent, props in rows:
        parents = set()
        if parent:
            parents.add(parent)
        extra = (props or {}).get('rdf_superclasses') if isinstance(props, dict) else None
        if isinstance(extra, list):
            parents.update(str(x) for x in extra)
        for p in parents:
            children.setdefault(p, set()).add(u)
    closure, frontier = {uri}, [uri]
    while frontier:
        nxt = []
        for u in frontier:
            for c in children.get(u, ()):
                if c not in closure:
                    closure.add(c)
                    nxt.append(c)
        frontier = nxt
    return closure


def _is_secondary_parent_of(uri):
    """SQL filter: entities whose properties JSON lists `uri` in rdf_superclasses (the asserted
    named parents beyond the single-valued materialized parent_uri; written at extraction only
    for multi-parent classes). Text match on the serialized array; URIs contain no quotes."""
    return OntologyEntity.properties.op('->>')('rdf_superclasses').like(f'%"{uri}"%')


def _get_entity_children(ontology, entity):
    """Get entities that have this entity as an asserted parent: the materialized parent_uri OR a
    secondary parent recorded in rdf_superclasses (multi-parent classes, e.g. PublicResponsibilityRole
    under both RelationalRole and ProfessionalRole)."""
    stmt = select(OntologyEntity).where(
        OntologyEntity.ontology_id == ontology.id,
        or_(OntologyEntity.parent_uri == entity.uri,
            _is_secondary_parent_of(entity.uri))
    ).order_by(OntologyEntity.label)
    return db.session.execute(stmt).scalars().all()


def _class_ancestor_uris(entity, cap=16):
    """Walk the (single-valued) parent_uri chain across ontologies to collect this class's
    ancestor URIs, including itself. Cycle- and depth-guarded.

    Each hop PREFERS the definitional row: a shared class exists once in its
    home ontology (intermediate#EngineerRole, parent ProfessionalRole) and
    again as a bare redeclaration in every case ontology that uses it (parent
    flattened to core#Role). An unordered LIMIT 1 could hop through a case
    stub, silently dropping the ProfessionalRole layer -- which hid the
    bearer-attribute SHACL schema and the four-kind principle layer on entity
    pages (correspondence audit T9, root-caused 2026-07-05)."""
    seen, uris, cur = set(), [], entity.uri
    while cur and cur not in seen and len(uris) < cap:
        seen.add(cur)
        uris.append(cur)
        rows = db.session.execute(
            select(OntologyEntity.parent_uri, Ontology.name)
            .join(Ontology, Ontology.id == OntologyEntity.ontology_id)
            .where(OntologyEntity.uri == cur)
        ).all()
        if not rows:
            break
        rows.sort(key=lambda r: (r[1].startswith('proethica-case-'), r[1]))
        cur = rows[0][0]
    return uris


def _class_ancestor_uris_all(entity, cap=32):
    """The UNION of ancestor URIs over ALL asserted named superclasses: the materialized parent_uri
    plus the rdf_superclasses secondaries stored at extraction for multi-parent classes. BFS from
    the class itself, cycle- and depth-guarded, with the same definitional-row preference per hop
    as _class_ancestor_uris (case stubs sort last). Use for schema, shape, and domain-property
    unions, where a multi-parent class must inherit from EVERY axis (PublicResponsibilityRole must
    see the ProfessionalRole shapes and property domains, not only the RelationalRole chain). The
    single-path _class_ancestor_uris stays for breadcrumb rendering, which needs a linear chain."""
    seen, uris, queue = set(), [], [entity.uri]
    while queue and len(uris) < cap:
        cur = queue.pop(0)
        if not cur or cur in seen:
            continue
        seen.add(cur)
        uris.append(cur)
        rows = db.session.execute(
            select(OntologyEntity.parent_uri, Ontology.name, OntologyEntity.properties)
            .join(Ontology, Ontology.id == OntologyEntity.ontology_id)
            .where(OntologyEntity.uri == cur)
        ).all()
        if not rows:
            continue
        rows.sort(key=lambda r: (r[1].startswith('proethica-case-'), r[1]))
        parent_uri, _, props = rows[0]
        parents = [parent_uri] if parent_uri else []
        if isinstance(props, str):
            import json as _json
            try:
                props = _json.loads(props)
            except Exception:
                props = {}
        for p in (props or {}).get('rdf_superclasses') or []:
            if p not in parents:
                parents.append(p)
        queue.extend(p for p in parents if p not in seen)
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
        .where(or_(OntologyEntity.parent_uri == entity.uri,
                   _is_secondary_parent_of(entity.uri)),
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


def _entity_secondary_parents(entity):
    """The asserted named superclasses of a multi-parent class beyond the materialized primary
    parent_uri, resolved to linkable rows. Read from the rdf_superclasses properties JSON written
    at extraction (multi-parent classes only); empty for the single-parent common case. Rendered
    as the 'Also subclass of' row so the non-primary axis is visible on the class's own page (the
    Class Hierarchy breadcrumb shows only the primary chain)."""
    props = entity.properties
    if isinstance(props, str):
        import json as _json
        try:
            props = _json.loads(props)
        except Exception:
            props = {}
    supers = (props or {}).get('rdf_superclasses') or []
    out = []
    for uri in supers:
        if uri == entity.parent_uri:
            continue
        frag = _uri_fragment(uri)
        row = db.session.execute(
            select(OntologyEntity.label, Ontology.name)
            .join(Ontology, Ontology.id == OntologyEntity.ontology_id)
            .where(OntologyEntity.uri == uri).limit(1)).first()
        out.append({"uri": uri, "fragment": frag,
                    "label": (row[0] if row and row[0] else frag),
                    "ontology": row[1] if row else None})
    out.sort(key=lambda d: d["label"].lower())
    return out
