"""Build the NSPE citation-chain view model for a case ontology.

Read-only display helper. A case's board conclusions carry
``proeth-core:citesProvision`` edges to ``nspe:`` CodeProvision IRIs (materialized
by the ProEthica citation-resolution hook / backfill). The NSPE Code of Ethics
ontology in turn records, per provision, the Principles, Obligations, and
Constraints it ``establishes``. This joins the two so the case page can show the
chain: conclusion -> cited provision -> established concept.

Degrades to has_citations=False when the case carries no citesProvision edges or
the NSPE ontology content is unavailable.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from rdflib import Graph, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import SKOS, DCTERMS

CORE = Namespace("http://proethica.org/ontology/core#")
CITES_PROVISION = CORE.citesProvision
ESTABLISHES = CORE.establishes
CONCEPT_TYPE = {
    CORE.Principle: "Principle",
    CORE.Obligation: "Obligation",
    CORE.Constraint: "Constraint",
}


def _localname(iri: str) -> str:
    for sep in ("#", "/"):
        if sep in iri:
            return iri.rsplit(sep, 1)[1]
    return iri


def build_citation_chain(
    case_ttl: Optional[str], nspe_ttl: Optional[str]
) -> Dict[str, Any]:
    """Return the citation-chain view model.

    Shape: {has_citations, provision_count, citation_count,
            provisions:[{iri, code, label, text,
                         establishes:[{iri,label,type}],
                         cited_by:[{iri,label}]}]}.
    """
    empty = {"has_citations": False, "provision_count": 0, "citation_count": 0, "provisions": []}
    if not case_ttl:
        return empty

    cg = Graph()
    try:
        cg.parse(data=case_ttl, format="turtle")
    except Exception:  # noqa: BLE001 - malformed TTL must not break the page
        return empty

    # provision IRI -> [citing conclusion refs]
    cited: Dict[URIRef, List[Dict[str, str]]] = {}
    citation_count = 0
    for s, _, prov in cg.triples((None, CITES_PROVISION, None)):
        lbl = cg.value(s, RDFS.label)
        cited.setdefault(prov, []).append(
            {"iri": str(s), "label": str(lbl) if lbl else _localname(str(s))}
        )
        citation_count += 1
    if not cited:
        return empty

    # Provision details + established concepts come from the NSPE ontology graph.
    ng = Graph()
    if nspe_ttl:
        try:
            ng.parse(data=nspe_ttl, format="turtle")
        except Exception:  # noqa: BLE001
            ng = Graph()

    def concept_type(c: URIRef) -> str:
        for t in ng.objects(c, RDF.type):
            if t in CONCEPT_TYPE:
                return CONCEPT_TYPE[t]
        return "Concept"

    def concept_ref(c: URIRef) -> Dict[str, str]:
        lbl = ng.value(c, RDFS.label)
        return {"iri": str(c), "label": str(lbl) if lbl else _localname(str(c)),
                "type": concept_type(c)}

    provisions: List[Dict[str, Any]] = []
    for prov in cited:
        code = ng.value(prov, DCTERMS.identifier)
        label = ng.value(prov, RDFS.label)
        text = ng.value(prov, SKOS.definition)
        establishes = sorted(
            (concept_ref(c) for c in ng.objects(prov, ESTABLISHES)),
            key=lambda r: (r["type"], r["label"].lower()),
        )
        provisions.append({
            "iri": str(prov),
            "code": str(code) if code else _localname(str(prov)).replace("_", "."),
            "label": str(label) if label else _localname(str(prov)),
            "text": str(text) if text else None,
            "establishes": establishes,
            "cited_by": sorted(cited[prov], key=lambda r: r["label"]),
        })

    # Sort provisions by code (natural-ish: split on dots).
    def code_key(p):
        parts = p["code"].replace("_", ".").split(".")
        return [(len(x), x) for x in parts]

    provisions.sort(key=code_key)

    return {
        "has_citations": True,
        "provision_count": len(provisions),
        "citation_count": citation_count,
        "provisions": provisions,
    }
