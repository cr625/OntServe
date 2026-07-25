"""SHACL-shape + class-property-schema helpers (split from helpers.py)."""
import re as _re

import rdflib
from sqlalchemy import select

from web.models import db, Ontology, OntologyEntity
from web.ontology_routes.component_page_rulebook import property_structure_groups

from .hierarchy import _class_ancestor_uris_all


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
    # information content entity: citesProvision is domained here, and rendering it on
    # every ICE-descended component page wrongly implied resources/principles cite
    # provisions; the actual citing subjects (the cases-layer analysis records) carry
    # the association through the descriptive CaseAnalysisCitationShape instead.
    "http://purl.obolibrary.org/obo/IAO_0000030",
}


def shape_attr_schema(shape_name):
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
            tgts = [str(t) for t in g.objects(s, SH.targetClass)]
            if tgts:
                out[str(s).rsplit("#", 1)[-1]] = tgts
    except Exception:
        out = {}
    cache["shapes"]["__targets__"] = out
    return out


def _class_shape_schemas(ancestor_list):
    """The SHACL property schema for a class = the UNION of the descriptive shapes whose targetClass is in the
    class chain (general -> specific): a base Role gets RoleDefinitionShape; a ProfessionalRole also gets
    ProfessionalRoleDefinitionShape + ProfessionalRolePropertyShape; a ParticipantRole only the universal
    one. *DefinitionShape -> definitional (type-level), *PropertyShape -> bearer (individual). Returns
    (definitional, bearer)."""
    targets = _shape_target_map()
    by_target = {}
    for name, tgts in targets.items():
        for tgt in tgts:
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
            for a in shape_attr_schema(name):
                if a["uri"] not in seen:
                    seen.add(a["uri"])
                    tier.append(a)
    return definitional, bearer


def class_property_schema(entity):
    """For a CLASS entity, the property schema applicable to its instances:
    object, datatype, and annotation properties whose rdfs:domain is this class or an
    ancestor (annotation rows carry kind='annotation' and render with a marker), plus -- for
    roles (core:Role in the ancestor chain) -- the controlled role-attribute schema from the
    SHACL RolePropertyShape (those properties are deliberately domain-less / leak-safe).
    Read-only. Returns None for non-class entities or when nothing applies."""
    if not entity or entity.entity_type != "class":
        return None
    # Drop the universal/abstract tops: properties domained to them (extraction provenance,
    # over-broad structural predicates) apply to everything, not specifically to this class.
    anc_list = _class_ancestor_uris_all(entity)
    ancestor_set = set(anc_list) - _UNIVERSAL_TOP_URIS

    prop_rows = db.session.execute(
        select(OntologyEntity).where(OntologyEntity.entity_type == "property")
    ).scalars().all()

    def _local(u):
        return u.rsplit("#", 1)[-1].rsplit("/", 1)[-1] if isinstance(u, str) else None

    # When a CASE-defined property shares a local name with a definitional one (e.g. an
    # intermediate-defined involvesRole with domain DecisionPoint and a case-defined one with
    # domain Case), the case row must not clobber the definitional row. Definitional homonyms
    # across base layers, by contrast, are real schema (distinct URIs; the Range/From cells
    # disambiguate) and all render. So: every non-case property keeps its own row; case-defined
    # properties are deduped per local name and shown only when no definitional row exists,
    # with a deterministic rank so the choice cannot flip on re-extraction.
    ont_name_by_id = dict(db.session.execute(select(Ontology.id, Ontology.name)).all())

    def _is_case(p):
        return (ont_name_by_id.get(p.ontology_id, "") or "").startswith("proethica-case")

    def _ref_rank(p):
        ont = ont_name_by_id.get(p.ontology_id, "") or ""
        return (1 if ont.startswith("proethica-case") else 0, ont, p.uri)

    def _select_rows(candidates):
        """The visible rows per the dedup rule above, deterministically ordered."""
        definitional = [p for p in candidates if not _is_case(p)]
        names_def = {_local(p.uri) for p in definitional}
        case_best = {}
        for p in candidates:
            if not _is_case(p):
                continue
            name = _local(p.uri)
            if name in names_def:
                continue
            cur = case_best.get(name)
            if cur is None or _ref_rank(p) < _ref_rank(cur):
                case_best[name] = p
        return sorted(definitional + list(case_best.values()), key=_ref_rank)

    domain_candidates = []
    for p in prop_rows:
        dom = p.domain
        dom_uris = dom if isinstance(dom, list) else [dom]
        if not any(isinstance(d, str) and d in ancestor_set for d in dom_uris):
            continue
        if not _local(p.uri) or (p.properties or {}).get('deprecated'):
            continue  # owl:deprecated property (e.g. the retired role-to-role duplicates); hide from the page
        domain_candidates.append(p)
    domain_props = []
    for p in _select_rows(domain_candidates):
        dom = p.domain
        dom_uris = dom if isinstance(dom, list) else [dom]
        rng = p.range
        # A union range (e.g. establishes: (Principle or Obligation or Constraint)) is stored as
        # a list; emit EVERY named member -- collapsing to the first member misstated union
        # ranges in the Range cell (the domain-table analogue of the referenced_by union-domain
        # fan-out below).
        rng_uris = [r for r in (rng if isinstance(rng, list) else [rng]) if isinstance(r, str)] if rng else []
        domain_props.append({
            "name": _local(p.uri),
            "uri": p.uri,
            "comment": (p.comment or ""),
            "ranges": [{"uri": r, "name": _local(r)} for r in rng_uris],
            "kind": (p.properties or {}).get("kind"),
            "on_self": any(isinstance(d, str) and d == entity.uri for d in dom_uris),
        })
    domain_props.sort(key=lambda x: (not x["on_self"], x["name"].lower()))

    # Incoming: properties whose rdfs:range is this class or a (non-universal) ancestor -- the edges that
    # point AT instances of this class (its in-degree). Mirrors domain_props but keyed on range, and
    # records the source class (the property's rdfs:domain) as "from".
    referenced_candidates = []
    for p in prop_rows:
        rng = p.range
        rng_uris = rng if isinstance(rng, list) else [rng]
        if not any(isinstance(r, str) and r in ancestor_set for r in rng_uris):
            continue
        if not _local(p.uri) or (p.properties or {}).get('deprecated'):
            continue  # owl:deprecated property; hide from Referenced-By (mirrors the domain_props filter)
        referenced_candidates.append(p)
    referenced_by = []
    for p in _select_rows(referenced_candidates):
        name = _local(p.uri)
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
    link_uris = {r["uri"] for r in referenced_by} | {r["from_uri"] for r in referenced_by if r["from_uri"]}
    link_uris |= {m["uri"] for r in domain_props for m in r["ranges"]}
    if link_uris:
        rows = db.session.execute(
            select(OntologyEntity.uri, Ontology.name, OntologyEntity.label, Ontology.is_base)
            .join(Ontology, OntologyEntity.ontology_id == Ontology.id)
            .where(OntologyEntity.uri.in_(list(link_uris)))
        ).all()

        # The same upper-level IRI is copied into several stores; resolve to the home
        # ontology with the _hierarchy_node preference (canonical bfo/iao first, then
        # any base ontology) so links and labels are consistent across pages.
        def _canon_rank(u, ont_name, is_base):
            frag = u.rsplit('#', 1)[-1].rsplit('/', 1)[-1]
            canon = 'bfo' if frag.startswith('BFO_') else ('iao' if frag.startswith('IAO_') else None)
            return (0 if (canon and ont_name == canon) else 1, 0 if is_base else 1, ont_name)

        uri_to_ont, uri_to_label = {}, {}
        for u, ont_name, label, is_base in sorted(rows, key=lambda r: _canon_rank(r[0], r[1], r[3])):
            uri_to_ont.setdefault(u, ont_name)
            if label:
                uri_to_label.setdefault(u, label)

        # OBO-numeric fragments (BFO_0000015, IAO_0000310) are opaque; attach the DB
        # label so the templates can render "process (BFO 0000015)". PascalCase
        # proethica fragments keep the fragment-derived display standard.
        _obo_num = _re.compile(r'^(BFO|IAO)_\d+$')
        for r in referenced_by:
            r["prop_ontology"] = uri_to_ont.get(r["uri"])
            r["from_ontology"] = uri_to_ont.get(r["from_uri"])
            if r["from_uri"] and _obo_num.match(_local(r["from_uri"]) or ''):
                r["from_label"] = uri_to_label.get(r["from_uri"])
        for r in domain_props:
            for m in r["ranges"]:
                m["ontology"] = uri_to_ont.get(m["uri"])
                if _obo_num.match(m["name"] or ''):
                    m["label"] = uri_to_label.get(m["uri"])

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
        anc = set(_class_ancestor_uris_all(entity))
        SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
        sg = rdflib.Graph()
        sg.parse(str(shapes_path), format="turtle")
        for prefix, ns in sg.namespaces():
            out.bind(prefix, ns)
        for shape in sg.subjects(rdflib.RDF.type, SH.NodeShape):
            if not any(str(t) in anc for t in sg.objects(shape, SH.targetClass)):
                continue
            for p, o in sg.predicate_objects(shape):
                out.add((shape, p, o))
                if isinstance(o, rdflib.BNode):  # the sh:property nodes
                    for p2, o2 in sg.predicate_objects(o):
                        out.add((o, p2, o2))
    except Exception:
        pass
    return out
