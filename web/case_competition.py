"""Build the obligation-competition view model for a case ontology.

Read-only display helper: parses a case ontology's TTL and groups the defeasibility
edges (competesWith / prevailsOver / defeasibleUnder) and the R->P->O lineage edges
(hasObligation / adheresToPrinciple / derivedFromPrinciple) into one cluster per
obligation, so the case page can show the competition structure the KI2026 paper
describes rather than a flat edge dump.

These edges are already materialized in the committed case TTL (corpus-wide
2026-05-23). Two grounding layers are surfaced, each degrading gracefully when
absent: the entity-level `sourceText` quote carried on each obligation/state
individual, and (2026-07-08) the PER-EDGE provenance -- the commit-time emitters
reify each defeasibility edge as a `prov:Derivation` individual
(`defeasibility_edge_provenance_<S>_<pred>_<O>`) carrying the passage the
extractor cited in `prov:value`, "source_field=...; confidence=..." in
`rdfs:comment` and the individuals it read in `prov:wasDerivedFrom`, so every
rendered edge can show the passage that justified IT, not only the quotes
attached to its endpoints. The fresh-architecture cases carry these nodes; older
commits fall back to the entity-level quotes.

The passage in `prov:value` is a verbatim quote of the case text only when
`source_field` is textReferences or sourceText. For every other field
(tensionResolution, balancingWith, caseContext, ...) it is a passage of a
narrative field written by the extraction model on another individual, so the
panel labels it "derived from <field> of <individual>" (case 24-1 review, 2026-10)
instead of presenting it as case text. See edge_provenance.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from rdflib import Graph, Namespace, RDF, RDFS, URIRef

from web.property_labels import humanize_key

CORE = Namespace("http://proethica.org/ontology/core#")
PROETH = Namespace("http://proethica.org/ontology/intermediate#")
PROETH_PROV = Namespace("http://proethica.org/provenance#")
PROV = Namespace("http://www.w3.org/ns/prov#")

COMPETES_WITH = CORE.competesWith
PREVAILS_OVER = CORE.prevailsOver
DEFEASIBLE_UNDER = CORE.defeasibleUnder
HAS_OBLIGATION = CORE.hasObligation
ADHERES_TO_PRINCIPLE = CORE.adheresToPrinciple
# derivedFromPrinciple moved namespaces: the legacy corpus (2026-05-23 R->P->O
# backfill) emits intermediate#, the fresh-architecture commits emit core# (where
# the property is declared since the nine-component work). Match both.
DERIVED_FROM_PRINCIPLE_PREDS = (CORE.derivedFromPrinciple, PROETH.derivedFromPrinciple)
# Grounding quote. The commit serializer emits it as proeth-prov:sourceText
# (typed provenance). Older case TTLs (pre the 2026-05 serializer cleanup, before
# the corpus is re-extracted) carry it as proeth:sourceText / proeth:sourcetext, so
# all three are tried in order for the transition window.
SOURCETEXT_CANDIDATES = (PROETH_PROV.sourceText, PROETH.sourceText, PROETH.sourcetext)

# Reified per-edge provenance node naming, as emitted by the ProEthica commit
# pipeline (defeasibility_pipeline / edge prov emitters): the node's localname
# encodes the directed edge it grounds.
_EDGE_PROV_PREFIX = "defeasibility_edge_provenance_"
_EDGE_PROV_PREDICATES = ("competesWith", "prevailsOver", "defeasibleUnder")
# The two source_field values that quote the case text itself. Every other value
# of the DefeasibilityEdge.source_field vocabulary (ProEthica schemas.py) names a
# narrative datatype field of an individual, written by the extraction model.
_VERBATIM_SOURCE_FIELDS = frozenset({"textreferences", "sourcetext"})
_SOURCE_FIELD_RE = re.compile(r"source_field=([^;\s]+)")


def _localname(iri: str) -> str:
    for sep in ("#", "/"):
        if sep in iri:
            return iri.rsplit(sep, 1)[1]
    return iri


def _source_field(note: Optional[str]) -> Optional[str]:
    """The source_field value of a "source_field=...; confidence=..." note, or None."""
    if not note:
        return None
    m = _SOURCE_FIELD_RE.search(note)
    return m.group(1) if m else None


def _source_individual(g: Graph, node: URIRef, subj_frag: str, obj_frag: str) -> Optional[URIRef]:
    """The individual whose field supplied the passage: the prov:wasDerivedFrom
    target that is neither endpoint of the edge (the emitter adds the source
    individual as a third target when it knows one), else the edge subject (the
    obligation whose own narrative field was read)."""
    targets = [t for t in g.objects(node, PROV.wasDerivedFrom) if isinstance(t, URIRef)]
    for t in targets:
        if _localname(str(t)) not in (subj_frag, obj_frag):
            return t
    for t in targets:
        if _localname(str(t)) == subj_frag:
            return t
    return None


def edge_provenance(g: Graph, node: URIRef, subj_frag: str, obj_frag: str, label) -> Dict[str, Any]:
    """The provenance record of one reified edge node.

    Keys: ``quote`` (prov:value), ``note`` (rdfs:comment), ``source_field``,
    ``verbatim`` (True when the field is textReferences or sourceText, or when the
    note names no field), ``derived_from`` ({iri, label, field} when the passage
    comes from a narrative field of an individual, else None) and ``hover``, the
    badge title the panel shows: "<quote> [<note>]" for a verbatim passage,
    prefixed with "derived from <field> of <individual>: " otherwise.
    """
    quote = g.value(node, PROV.value)
    note = g.value(node, RDFS.comment)
    quote_s = str(quote) if quote else None
    note_s = str(note) if note else None
    field = _source_field(note_s)
    verbatim = field is None or field.lower() in _VERBATIM_SOURCE_FIELDS
    derived_from = None
    if not verbatim:
        source = _source_individual(g, node, subj_frag, obj_frag)
        derived_from = {
            "iri": str(source) if source is not None else None,
            "label": label(source) if source is not None else None,
            "field": field,
        }
    hover = None
    if quote_s:
        hover = f"{quote_s} [{note_s or ''}]"
        if derived_from is not None:
            field_text = humanize_key(field) or field
            field_text = field_text[0].lower() + field_text[1:]
            of = f" of {derived_from['label']}" if derived_from["label"] else ""
            hover = f"derived from {field_text}{of}: {hover}"
    return {
        "quote": quote_s,
        "note": note_s,
        "source_field": field,
        "verbatim": verbatim,
        "derived_from": derived_from,
        "hover": hover,
    }


def build_competition_clusters(ttl_content: Optional[str]) -> Dict[str, Any]:
    """Return the obligation-competition view model for a case TTL.

    Shape: {has_edges, obligation_count, edge_counts{...}, clusters:[{iri,label,
    source_text, competes_with[], prevails_over[], prevailed_over_by[],
    defeasible_under[], derived_from_principle[], borne_by_roles[]}]}.
    Degrades to has_edges=False / clusters=[] for empty or edge-free ontologies.
    """
    empty = {
        "has_edges": False,
        "obligation_count": 0,
        "competing_count": 0,
        "edge_counts": {},
        "clusters": [],
    }
    if not ttl_content:
        return empty

    g = Graph()
    try:
        g.parse(data=ttl_content, format="turtle")
    except Exception:  # noqa: BLE001 - a malformed TTL should not break the page
        return empty

    def label(iri: URIRef) -> str:
        lbl = g.value(iri, RDFS.label)
        return str(lbl) if lbl else _localname(str(iri))

    def source_text(iri: URIRef) -> Optional[str]:
        for pred in SOURCETEXT_CANDIDATES:
            st = g.value(iri, pred)
            if st:
                return str(st)
        return None

    def ref(iri: URIRef) -> Dict[str, Optional[str]]:
        return {"iri": str(iri), "label": label(iri)}

    # Per-edge provenance index: (subject-frag, predicate, object-frag) -> the
    # edge_provenance record. Parsed from the reified prov:Derivation nodes whose
    # localname encodes the edge.
    edge_prov: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for node in g.subjects(RDF.type, PROV.Derivation):
        local = _localname(str(node))
        if not local.startswith(_EDGE_PROV_PREFIX):
            continue
        rest = local[len(_EDGE_PROV_PREFIX):]
        for pred in _EDGE_PROV_PREDICATES:
            sep = f"_{pred}_"
            if sep in rest:
                subj_frag, obj_frag = rest.split(sep, 1)
                edge_prov[(subj_frag, pred, obj_frag)] = edge_provenance(
                    g, node, subj_frag, obj_frag, label)
                break

    def edge_ref(display: URIRef, subj: URIRef, pred: str, obj: URIRef) -> Dict[str, Any]:
        """ref(display) plus the (subj, pred, obj) edge's reified provenance when
        present. For competesWith the emitters reify both closure directions, but a
        legacy graph may carry only one, so the reverse key is the fallback."""
        r: Dict[str, Any] = ref(display)
        key = (_localname(str(subj)), pred, _localname(str(obj)))
        p = edge_prov.get(key)
        if p is None and pred == "competesWith":
            p = edge_prov.get((_localname(str(obj)), pred, _localname(str(subj))))
        r["prov"] = p
        return r

    edge_counts = {
        "competesWith": len(list(g.triples((None, COMPETES_WITH, None)))),
        "prevailsOver": len(list(g.triples((None, PREVAILS_OVER, None)))),
        "defeasibleUnder": len(list(g.triples((None, DEFEASIBLE_UNDER, None)))),
        "hasObligation": len(list(g.triples((None, HAS_OBLIGATION, None)))),
        "adheresToPrinciple": len(list(g.triples((None, ADHERES_TO_PRINCIPLE, None)))),
        "derivedFromPrinciple": sum(
            len(list(g.triples((None, p, None)))) for p in DERIVED_FROM_PRINCIPLE_PREDS
        ),
    }
    if not any(edge_counts.values()):
        return {**empty, "edge_counts": edge_counts}

    # Obligations = nodes participating in the competition / lineage graph as the
    # subject of an obligation-side edge or the object of competition / hasObligation.
    obligations: set = set()
    for s, _, o in g.triples((None, COMPETES_WITH, None)):
        obligations.add(s); obligations.add(o)
    for s, _, o in g.triples((None, PREVAILS_OVER, None)):
        obligations.add(s); obligations.add(o)
    for s, _, _o in g.triples((None, DEFEASIBLE_UNDER, None)):
        obligations.add(s)
    for pred in DERIVED_FROM_PRINCIPLE_PREDS:
        for s, _, _o in g.triples((None, pred, None)):
            obligations.add(s)
    for _s, _, o in g.triples((None, HAS_OBLIGATION, None)):
        obligations.add(o)

    # Role -> [obligations] for the borne_by_roles lineage (inverse of hasObligation).
    role_of: Dict[URIRef, List[URIRef]] = {}
    for s, _, o in g.triples((None, HAS_OBLIGATION, None)):
        role_of.setdefault(o, []).append(s)

    clusters: List[Dict[str, Any]] = []
    for obl in sorted(obligations, key=lambda u: label(u).lower()):
        prevailed_over_by = [
            edge_ref(s, s, "prevailsOver", obl)
            for s, _, o in g.triples((None, PREVAILS_OVER, obl)) if o == obl
        ]
        roles = role_of.get(obl, [])
        # principles the bearing role adheres to (R->P), plus this obligation's own P
        adhered: List[Dict] = []
        for r in roles:
            adhered += [ref(p) for _, _, p in g.triples((r, ADHERES_TO_PRINCIPLE, None))]

        cluster = {
            "iri": str(obl),
            "label": label(obl),
            "source_text": source_text(obl),
            "competes_with": [
                edge_ref(o, obl, "competesWith", o)
                for _, _, o in g.triples((obl, COMPETES_WITH, None))
            ],
            "prevails_over": [
                edge_ref(o, obl, "prevailsOver", o)
                for _, _, o in g.triples((obl, PREVAILS_OVER, None))
            ],
            "prevailed_over_by": prevailed_over_by,
            "defeasible_under": [
                {**edge_ref(st, obl, "defeasibleUnder", st), "source_text": source_text(st)}
                for _, _, st in g.triples((obl, DEFEASIBLE_UNDER, None))
            ],
            "derived_from_principle": [
                ref(p)
                for pred in DERIVED_FROM_PRINCIPLE_PREDS
                for _, _, p in g.triples((obl, pred, None))
            ],
            "borne_by_roles": [ref(r) for r in roles],
            "adheres_to_principles": adhered,
        }
        # An obligation can enter the cluster set through lineage edges alone
        # (derivedFromPrinciple / hasObligation); only trio participation makes
        # it part of a competition. The view renders the two kinds differently
        # and the panel count reports competing obligations, not all clusters.
        cluster["in_competition"] = bool(
            cluster["competes_with"] or cluster["prevails_over"]
            or cluster["prevailed_over_by"] or cluster["defeasible_under"]
        )
        clusters.append(cluster)

    return {
        "has_edges": True,
        "obligation_count": len(clusters),
        "competing_count": sum(1 for c in clusters if c["in_competition"]),
        "edge_counts": edge_counts,
        "clusters": clusters,
    }
