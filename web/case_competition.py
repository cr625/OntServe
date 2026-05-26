"""Build the obligation-competition view model for a case ontology.

Read-only display helper: parses a case ontology's TTL and groups the defeasibility
edges (competesWith / prevailsOver / defeasibleUnder) and the R->P->O lineage edges
(hasObligation / adheresToPrinciple / derivedFromPrinciple) into one cluster per
obligation, so the case page can show the competition structure the KI2026 paper
describes rather than a flat edge dump.

These edges are already materialized in the committed case TTL (corpus-wide
2026-05-23). The verbatim grounding quote is the `proeth:sourcetext` carried on each
obligation/state individual (the committed cases attach the quote to the entity, not
to a per-edge prov:Derivation node), surfaced for auditability and degraded gracefully
when absent.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from rdflib import Graph, Namespace, RDFS, URIRef

CORE = Namespace("http://proethica.org/ontology/core#")
PROETH = Namespace("http://proethica.org/ontology/intermediate#")

COMPETES_WITH = CORE.competesWith
PREVAILS_OVER = CORE.prevailsOver
DEFEASIBLE_UNDER = CORE.defeasibleUnder
HAS_OBLIGATION = CORE.hasObligation
ADHERES_TO_PRINCIPLE = CORE.adheresToPrinciple
DERIVED_FROM_PRINCIPLE = PROETH.derivedFromPrinciple
SOURCETEXT = PROETH.sourcetext


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
        st = g.value(iri, SOURCETEXT)
        return str(st) if st else None

    def ref(iri: URIRef) -> Dict[str, Optional[str]]:
        return {"iri": str(iri), "label": label(iri)}

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
            ref(s) for s, _, o in g.triples((None, PREVAILS_OVER, obl)) if o == obl
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
            "competes_with": [ref(o) for _, _, o in g.triples((obl, COMPETES_WITH, None))],
            "prevails_over": [ref(o) for _, _, o in g.triples((obl, PREVAILS_OVER, None))],
            "prevailed_over_by": prevailed_over_by,
            "defeasible_under": [
                {**ref(st), "source_text": source_text(st)}
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
