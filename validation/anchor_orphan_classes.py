#!/usr/bin/env python3
"""Anchor orphan type classes in a case TTL to their proethica-core D-tuple category.

For a case whose discovered classes were committed without an rdfs:subClassOf chain to
core (so the nine-way disjointness cannot fire on them), emit the missing
`rdfs:subClassOf proeth-core:<Category>` from the materialized direct type carried by the
class's individuals. Guarded: emits ONLY when every individual of the class agrees on a
single one of the nine categories (the materialized direct type can disagree -- in that
case the class is left for manual review rather than mis-anchored). Orphans are detected
against the merged
core+intermediate+extended closure (a class already chained via an imported declaration is
left alone); the new triples are written to the CASE TTL only.

Usage: python validation/anchor_orphan_classes.py <case-stem> [--apply]
       (dry-run by default; --apply writes the TTL back)
"""
import sys
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef

ONT = Path(__file__).resolve().parent.parent / "ontologies"
CORE = Namespace("http://proethica.org/ontology/core#")
NINE = ["Role", "Principle", "Obligation", "State", "Resource",
        "Action", "Event", "Capability", "Constraint"]
CATEGORY_TO_CORE = {c: CORE[c] for c in NINE}
CORE_TARGETS = set(CATEGORY_TO_CORE.values()) | {CORE["Agent"]}


def _ln(u):
    return str(u).split("#")[-1].split("/")[-1]


def _load_imports():
    g = Graph()
    for f in ("proethica-core.ttl", "proethica-intermediate.ttl",
              "proethica-intermediate-extended.ttl"):
        p = ONT / f
        if p.exists():
            g.parse(str(p), format="turtle")
    return g


def _reaches_core(g, cls, seen=None):
    seen = seen or set()
    if cls in seen:
        return False
    seen.add(cls)
    nexts = (set(g.objects(cls, RDFS.subClassOf))
             | set(g.objects(cls, OWL.equivalentClass))
             | set(g.subjects(OWL.equivalentClass, cls)))
    for sup in nexts:
        if sup in CORE_TARGETS or _ln(sup) in NINE or _reaches_core(g, sup, seen):
            return True
    return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    stem = sys.argv[1]
    apply = "--apply" in sys.argv
    case_path = ONT / f"{stem}.ttl"
    if not case_path.exists():
        print(f"not found: {case_path}")
        return

    case = Graph()
    case.parse(str(case_path), format="turtle")
    merged = _load_imports()
    for t in case:
        merged.add(t)

    # class -> set of category names claimed by its individuals, read from each
    # individual's materialized direct rdf:type proeth-core:<Category> (CMT-1),
    # replacing the retired conceptCategory literal.
    cls_cats = defaultdict(set)
    for ind in case.subjects(RDF.type, OWL.NamedIndividual):
        cats = {_ln(t) for t in case.objects(ind, RDF.type)
                if str(t).startswith(str(CORE)) and _ln(t) in NINE}
        for cls in case.objects(ind, RDF.type):
            if cls == OWL.NamedIndividual or "#" not in str(cls):
                continue
            cls_cats[cls] |= cats

    anchored, skipped = [], []
    for cls, cats in cls_cats.items():
        if _ln(cls) in NINE or cls in CORE_TARGETS:
            continue
        if _reaches_core(merged, cls):
            continue  # already anchored via case or imports
        nine_cats = cats & set(NINE)
        if len(nine_cats) == 1:
            cat = next(iter(nine_cats))
            case.add((cls, RDF.type, OWL.Class))
            case.add((cls, RDFS.subClassOf, CATEGORY_TO_CORE[cat]))
            anchored.append((_ln(cls), cat))
        else:
            skipped.append((_ln(cls), sorted(cats)))

    print(f"[{stem}] orphan classes anchored: {len(anchored)} | skipped (no single category): {len(skipped)}")
    for name, cat in sorted(anchored):
        print(f"  + {name} -> core:{cat}")
    for name, cats in sorted(skipped):
        print(f"  ! {name} (categories: {cats}) -- left for review")

    if apply and anchored:
        case.serialize(destination=str(case_path), format="turtle")
        print(f"WROTE {len(anchored)} subClassOf triples to {case_path}")
    elif not apply:
        print("(dry-run; pass --apply to write)")


if __name__ == "__main__":
    main()
