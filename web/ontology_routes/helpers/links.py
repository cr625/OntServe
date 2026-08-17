"""Entity semantic-link, cross-ontology-lookup, and hierarchy-edge helpers (split
from helpers.py)."""
import re as _re

import rdflib
from flask import url_for
from sqlalchemy import select, or_

from web.models import db, Ontology, OntologyEntity, OntologyVersion

from .hierarchy import _base_subclass_closure, _uri_fragment, _canonical_upper_ontology
from .display import _humanize_property_key


# SKOS / see-also / source crosswalk predicates surfaced on the entity page as links.
_SEMANTIC_LINK_PREDS = [
    ('http://www.w3.org/2004/02/skos/core#exactMatch', 'exactly matches'),
    ('http://www.w3.org/2004/02/skos/core#closeMatch', 'closely matches'),
    ('http://www.w3.org/2004/02/skos/core#broadMatch', 'broader match'),
    ('http://www.w3.org/2004/02/skos/core#relatedMatch', 'related match'),
    ('http://www.w3.org/2000/01/rdf-schema#seeAlso', 'see also'),
    ('http://purl.org/dc/terms/source', 'source'),
    ('http://purl.org/dc/terms/references', 'references'),
]


def entity_semantic_links(entity, ontology):
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
            # A case-ontology declaration IRI (the dcterms:source citation on
            # case-discovered classes) resolves to the internal case page, not
            # an external link -- there is no entity row for an ontology IRI.
            case_m = _re.match(r'^https?://proethica\.org/ontology/case/(\d+)$', tgt)
            if case_m:
                case_name = f'proethica-case-{case_m.group(1)}'
                case_ont = db.session.execute(
                    select(Ontology).where(Ontology.name == case_name)).scalar_one_or_none()
                if case_ont is not None:
                    meta = case_ont.meta_data if isinstance(case_ont.meta_data, dict) else {}
                    links.append({
                        'relation': rel_label,
                        'label': f"Case {case_m.group(1)}: {meta.get('display_name') or case_name}",
                        'url': url_for('ontology.ontology_detail_or_uri_resolution',
                                       ontology_name=case_name),
                        'external': False, 'note': case_name,
                    })
                    continue
            ent = definitional_entity_for_uri(tgt)
            if ent is not None and ent.ontology is not None:
                links.append({
                    'relation': rel_label, 'label': ent.label or frag,
                    'url': url_for('ontology.entity_detail',
                                   ontology_name=ent.ontology.name, fragment=frag),
                    'external': False, 'note': ent.ontology.name,
                })
            elif tgt.startswith('http'):
                # Label DOIs with the full registrant-prefixed DOI (the bare final path
                # segment is not a valid DOI string) and other external IRIs host-first.
                label = None
                for pref in ('https://doi.org/', 'http://doi.org/',
                             'https://dx.doi.org/', 'http://dx.doi.org/'):
                    if tgt.startswith(pref):
                        label = tgt[len(pref):]
                        break
                if label is None:
                    label = _re.sub(r'^www\.', '', tgt.split('://', 1)[-1])
                links.append({
                    'relation': rel_label, 'label': label,
                    'url': tgt, 'external': True, 'note': None,
                })
    return links


from services.ontology_categories import CASE_NAME_RE as _CASE_ONTOLOGY_RE


def entity_using_cases(entity):
    """Case ontologies that instantiate this class or a base-ontology descendant of it.
    An individual's rdf:type is stored as parent_uri; the base-layer subclass closure
    makes mid-chain classes (Guideline) report the cases typed to their descendants.
    Computed live rather than materialized on the class, so the list stays accurate as
    new cases are extracted; the originating case is recorded separately as
    firstDiscoveredInCase."""
    if not entity or entity.entity_type != 'class':
        return []
    closure = _base_subclass_closure(entity.uri)
    names = db.session.execute(
        select(Ontology.name)
        .join(OntologyEntity, OntologyEntity.ontology_id == Ontology.id)
        .where(OntologyEntity.parent_uri.in_(list(closure)),
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


def uri_ends_with_fragment(fragment):
    """SQLAlchemy predicate matching a URI whose final segment is `fragment`,
    delimited by either '#' (proethica URIs) or '/' (OBO/BFO URIs). Lets the
    entity page resolve slash-delimited BFO links such as obo/BFO_0000001."""
    return or_(OntologyEntity.uri.like(f'%#{fragment}'),
               OntologyEntity.uri.like(f'%/{fragment}'))


def find_entity_by_fragment(ontology, fragment):
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
        uri_ends_with_fragment(fragment)
    ).limit(1)
    return db.session.execute(stmt).scalars().first()


def definitional_entity_for_uri(uri):
    """The definitional OntologyEntity row for a URI that may appear in several
    ontologies. The same URI legitimately holds a row in every store that declares
    it: an intermediate class is re-extracted as a stub row in each case ontology
    that uses it (100+ ontologies for common classes), upper-level BFO/IAO IRIs sit
    in bfo/iao plus the proethica-foundation reasoner stub, and the provenance
    properties are mirrored into the extended discovery store. A bare
    scalar_one_or_none() on uri therefore raises MultipleResultsFound.

    Preference order: the canonical upper ontology for BFO/IAO IRIs, then
    definitional stores (ontology_type upper/core/base/domain) over derived ones
    (extracted, case), then non-case ontologies, with the ontology name as the
    deterministic tie-break. Returns None when the URI is unknown."""
    rows = db.session.execute(
        select(OntologyEntity).where(OntologyEntity.uri == uri)
    ).scalars().all()
    if len(rows) <= 1:
        return rows[0] if rows else None
    canon = _canonical_upper_ontology(uri)

    def rank(e):
        o = e.ontology
        name = o.name if o else ''
        otype = (o.ontology_type or '') if o else ''
        return (
            0 if (canon and name == canon) else 1,
            0 if otype in ('upper', 'core', 'base', 'domain') else 1,
            1 if name.startswith('proethica-case-') else 0,
            name,
        )
    return min(rows, key=rank)


def entity_disjoint_classes(entity, ontology):
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


def entity_case_provenance(entity):
    """Case citations for a case-discovered class: the cases recorded by the
    commit-time proeth-prov:discoveredInCase / firstDiscoveredInCase markers,
    resolved to linked case ontologies with their display titles.

    A discovered class in the extended store is grounded EXTENSIONALLY by the
    case(s) it was found in (McLaren); the raw numbers sat in the collapsed
    provenance panel, which reads as unexplained rather than as the class's
    citation. Returns [{num, title, url, first}] ordered first-discovery
    first. Empty for curated classes (no markers)."""
    props = entity.properties if isinstance(entity.properties, dict) else {}
    if not props:
        return []

    def _nums(value):
        values = value if isinstance(value, list) else [value]
        out = []
        for v in values:
            try:
                out.append(int(str(v)))
            except (TypeError, ValueError):
                continue
        return out

    first = None
    numbers = []
    for key, value in props.items():
        if key.lower() == 'firstdiscoveredincase':
            got = _nums(value)
            first = got[0] if got else None
        elif key.lower() == 'discoveredincase':
            numbers.extend(_nums(value))
    ordered = []
    for n in ([first] if first is not None else []) + numbers:
        if n is not None and n not in ordered:
            ordered.append(n)
    out = []
    for n in ordered:
        name = f'proethica-case-{n}'
        ont = db.session.execute(
            select(Ontology).where(Ontology.name == name)).scalar_one_or_none()
        if ont is None:
            continue
        meta = ont.meta_data if isinstance(ont.meta_data, dict) else {}
        title = meta.get('display_name') or name
        out.append({
            'num': n, 'title': title, 'first': (n == first),
            'url': url_for('ontology.ontology_detail_or_uri_resolution', ontology_name=name),
        })
    return out


def entity_incoming_edges(entity, ontology):
    """Object-property edges POINTING AT this entity in the current ontology
    version: [(predicate_localname, [{uri, fragment, label}])]. The commit
    writes several families one-directional (Agent hasRole facet, Obligation
    requiresCapability, obligatedParty, isPerformedBy ...), so without this an
    individual never shows who bears/requires/performs it (correspondence
    audit T8, 2026-07-05). Mirrors entity_disjoint_classes: parsed from the
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


def entity_equivalent_class(entity, ontology):
    """For a DEFINED class (owl:equivalentClass with an owl:intersectionOf), the human-readable
    definition: the ordered conjuncts -- named classes and property restrictions (onProperty +
    some/only filler). Parsed from the current version content because the intersection/restriction
    nodes are anonymous blank nodes (not stored as entity triples). Returns {'conjuncts': [...]} or
    None. Mirrors entity_disjoint_classes."""
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
