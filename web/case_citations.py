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
PROETH = Namespace("http://proethica.org/ontology/intermediate#")
CASES = Namespace("http://proethica.org/ontology/cases#")
CITES_PROVISION = CORE.citesProvision
ESTABLISHES = CORE.establishes
ETHICAL_CONCLUSION = CASES.EthicalConclusion
CONCLUSION_TYPE = PROETH.conclusionType
CONCLUSION_NUMBER = PROETH.conclusionNumber
CONCLUSION_TEXT = PROETH.conclusionText
# Object property since proethica-cases v3.5.0 (edge-primary; the former
# intermediate-namespace string literal is deprecated and no longer emitted).
ANSWERS_QUESTION = CASES.answersQuestion
EXTRACTION_REASONING = PROETH.extractionReasoning
QUESTION_NUMBER = PROETH.questionNumber
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


def _humanize_type(t: Optional[str]) -> str:
    """analytical_extension -> 'Analytical Extension'."""
    return " ".join(w.capitalize() for w in (t or "conclusion").replace("_", " ").split())


def _conclusion_index(cg: Graph) -> Dict[str, Dict[str, Any]]:
    """Map each EthicalConclusion IRI -> a display record with a HUMAN label.

    Conclusion individuals carry opaque IRIs (Conclusion_101). Derive a readable
    label from conclusionType + a per-type ordinal ('Analytical Extension 3'),
    keeping the IRI localname as the stable anchor. Presentation-only; the stored
    rdfs:label is untouched.
    """
    raw = []
    for s in cg.subjects(RDF.type, ETHICAL_CONCLUSION):
        ctype = cg.value(s, CONCLUSION_TYPE)
        num = cg.value(s, CONCLUSION_NUMBER)
        text = cg.value(s, CONCLUSION_TEXT)
        try:
            n = int(str(num))
        except (TypeError, ValueError):
            n = 0
        raw.append((s, str(ctype) if ctype else "conclusion", n, str(text) if text else ""))

    by_type: Dict[str, list] = {}
    for rec in sorted(raw, key=lambda r: (r[1], r[2])):
        by_type.setdefault(rec[1], []).append(rec)

    index: Dict[str, Dict[str, Any]] = {}
    for ctype, items in by_type.items():
        tlabel = _humanize_type(ctype)
        for ordinal, (s, _, num, text) in enumerate(items, start=1):
            index[str(s)] = {
                "iri": str(s),
                "anchor": _localname(str(s)),
                "type": ctype,
                "type_label": tlabel,
                "number": num,
                "label": f"{tlabel} {ordinal}",
                "text": text,
            }
    return index


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

    # Human-readable conclusion labels + anchors (Conclusion_101 -> 'Analytical Extension 3').
    cidx = _conclusion_index(cg)

    # provision IRI -> [citing conclusion refs]
    cited: Dict[URIRef, List[Dict[str, str]]] = {}
    citation_count = 0
    for s, _, prov in cg.triples((None, CITES_PROVISION, None)):
        rec = cidx.get(str(s))
        if rec:
            entry = {"iri": str(s), "anchor": rec["anchor"], "label": rec["label"],
                     "type_label": rec["type_label"], "number": rec["number"],
                     "snippet": rec["text"][:160]}
        else:
            lbl = cg.value(s, RDFS.label)
            entry = {"iri": str(s), "anchor": _localname(str(s)),
                     "label": str(lbl) if lbl else _localname(str(s)),
                     "type_label": None, "number": 0, "snippet": None}
        cited.setdefault(prov, []).append(entry)
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
            "cited_by": sorted(cited[prov], key=lambda r: (r.get("type_label") or "", r.get("number") or 0)),
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


def build_conclusions(case_ttl: Optional[str]) -> Dict[str, Any]:
    """View model for the case's EthicalConclusion individuals.

    Surfaces the conclusions the 'cited by' chips point at, so they have an
    on-page anchor target (id=conclusion-<localname>) and readable text rather
    than only an opaque IRI. Shape:
        {has_conclusions, count, conclusions:[{iri, anchor, label, type_label,
            number, text, cited_provisions:[code]}]}.
    """
    empty = {"has_conclusions": False, "count": 0, "conclusions": []}
    if not case_ttl:
        return empty
    cg = Graph()
    try:
        cg.parse(data=case_ttl, format="turtle")
    except Exception:  # noqa: BLE001
        return empty

    cidx = _conclusion_index(cg)
    if not cidx:
        return empty

    out: List[Dict[str, Any]] = []
    for iri, rec in cidx.items():
        s = URIRef(iri)
        cited = sorted({_localname(str(o)).replace("_", ".")
                        for o in cg.objects(s, CITES_PROVISION)})
        # answersQuestion targets the Question individual directly; the chip
        # number comes from the target's questionNumber, falling back to the
        # digits of the localname (Question_101) when the literal is absent.
        answers = []
        for q in cg.objects(s, ANSWERS_QUESTION):
            anchor = _localname(str(q))
            qnum = cg.value(q, QUESTION_NUMBER)
            answers.append({"number": str(qnum) if qnum is not None
                            else anchor.rsplit("_", 1)[-1],
                            "anchor": anchor})
        answers.sort(key=lambda a: (len(a["number"]), a["number"]))
        reasoning = cg.value(s, EXTRACTION_REASONING)
        out.append({**rec, "cited_provisions": cited,
                    "answers_questions": answers,
                    "reasoning": str(reasoning) if reasoning else ""})
    out.sort(key=lambda c: (c["type_label"], c["number"]))
    return {"has_conclusions": True, "count": len(out), "conclusions": out}
