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
(`defeasibility_edge_provenance_<S>_<pred>_<O>`) carrying the verbatim grounding
quote in `prov:value` and "source_field=...; confidence=..." in `rdfs:comment`,
so every rendered edge can show the quote that justified IT, not only the quotes
attached to its endpoints. The fresh-architecture cases carry these nodes; older
commits fall back to the entity-level quotes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from rdflib import Graph, Namespace, RDF, RDFS, URIRef

CORE = Namespace("http://proethica.org/ontology/core#")
PROETH = Namespace("http://proethica.org/ontology/intermediate#")
PROETH_PROV = Namespace("http://proethica.org/provenance#")
PROV = Namespace("http://www.w3.org/ns/prov#")

COMPETES_WITH = CORE.competesWith
PREVAILS_OVER = CORE.prevailsOver
DEFEASIBLE_UNDER = CORE.defeasibleUnder
HAS_OBLIGATION = CORE.hasObligation
ADHERES_TO_PRINCIPLE = CORE.adheresToPrinciple
DERIVED_FROM_PRINCIPLE = PROETH.derivedFromPrinciple
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


def _localname(iri: str) -> str:
    for sep in ("#", "/"):
        if sep in iri:
            return iri.rsplit(sep, 1)[1]
    return iri


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

    # Per-edge provenance index: (subject-frag, predicate, object-frag) -> {quote, note}.
    # Parsed from the reified prov:Derivation nodes whose localname encodes the edge.
    edge_prov: Dict[Tuple[str, str, str], Dict[str, Optional[str]]] = {}
    for node in g.subjects(RDF.type, PROV.Derivation):
        local = _localname(str(node))
        if not local.startswith(_EDGE_PROV_PREFIX):
            continue
        rest = local[len(_EDGE_PROV_PREFIX):]
        for pred in _EDGE_PROV_PREDICATES:
            sep = f"_{pred}_"
            if sep in rest:
                subj_frag, obj_frag = rest.split(sep, 1)
                quote = g.value(node, PROV.value)
                note = g.value(node, RDFS.comment)
                edge_prov[(subj_frag, pred, obj_frag)] = {
                    "quote": str(quote) if quote else None,
                    "note": str(note) if note else None,
                }
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
        "derivedFromPrinciple": len(list(g.triples((None, DERIVED_FROM_PRINCIPLE, None)))),
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
    for s, _, _o in g.triples((None, DERIVED_FROM_PRINCIPLE, None)):
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

        clusters.append({
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
                ref(p) for _, _, p in g.triples((obl, DERIVED_FROM_PRINCIPLE, None))
            ],
            "borne_by_roles": [ref(r) for r in roles],
            "adheres_to_principles": adhered,
        })

    return {
        "has_edges": True,
        "obligation_count": len(clusters),
        "edge_counts": edge_counts,
        "clusters": clusters,
    }
