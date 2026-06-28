#!/usr/bin/env python3
"""Imports-aware orphan-class audit.

A type class used as an individual's rdf:type is an "orphan" if it has no
rdfs:subClassOf* chain to one of the nine proethica-core D-tuple categories
(Role, Principle, Obligation, State, Resource, Action, Event, Capability,
Constraint) or core:Agent. The earlier orphan counts (and the ad-hoc eval check)
loaded only the case TTL, which false-flags every reused curated class whose
declaration + chain lives in proethica-intermediate / -intermediate-extended.
This audit loads core + intermediate + extended before resolving, so the count
reflects reality.

It further splits the orphans into:
  - REAL D-tuple orphans: the class's individuals carry a materialized direct type
    that IS one of the nine, but the class does not chain to that core category.
    These threaten the nine-way disjointness guarantee and are the actionable kind.
  - non-D-tuple classes: no nine-category materialized direct type (analysis/synthesis
    or temporal-structural artifacts such as DecisionPoint, EthicalQuestion,
    EthicalConclusion, CausalChain, TemporalRelation). Outside the disjoint set
    by design; reported separately, not a defect.

Usage: python validation/orphan_audit.py [case_glob]
"""
import sys
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef

ONT = Path(__file__).resolve().parent.parent / "ontologies"
CORE_NS = Namespace("http://proethica.org/ontology/core#")
NINE = ["Role", "Principle", "Obligation", "State", "Resource",
        "Action", "Event", "Capability", "Constraint"]
CORE_TARGETS = {CORE_NS[c] for c in NINE} | {CORE_NS["Agent"]}


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
    # Follow rdfs:subClassOf and owl:equivalentClass (both directions -- it is symmetric),
    # so a proeth-cases: class equivalent to an anchored proeth: class resolves.
    nexts = (set(g.objects(cls, RDFS.subClassOf))
             | set(g.objects(cls, OWL.equivalentClass))
             | set(g.subjects(OWL.equivalentClass, cls)))
    for sup in nexts:
        if sup in CORE_TARGETS or _ln(sup) in NINE or _reaches_core(g, sup, seen):
            return True
    return False


def audit_case(imports_graph, case_path):
    g = Graph()
    for t in imports_graph:
        g.add(t)
    g.parse(str(case_path), format="turtle")

    real, nond = set(), set()  # orphan class local-names
    for ind in g.subjects(RDF.type, OWL.NamedIndividual):
        # The nine-category names claimed by the individual via its materialized
        # direct rdf:type proeth-core:<Category> (CMT-1), replacing the retired
        # conceptCategory literal.
        cats = {_ln(t) for t in g.objects(ind, RDF.type)
                if str(t).startswith(str(CORE_NS)) and _ln(t) in NINE}
        for cls in g.objects(ind, RDF.type):
            if cls == OWL.NamedIndividual or "#" not in str(cls):
                continue
            if _ln(cls) in NINE or cls in CORE_TARGETS:
                continue
            if _reaches_core(g, cls):
                continue
            # orphan: classify by whether the individual claims a nine-category
            if cats & set(NINE):
                real.add(_ln(cls))
            else:
                nond.add(_ln(cls))
    return real, nond


def main():
    glob = sys.argv[1] if len(sys.argv) > 1 else "proethica-case-*.ttl"
    cases = sorted(ONT.glob(glob))
    if not cases:
        print(f"no case TTLs match {glob} in {ONT}")
        return
    imports = _load_imports()
    print(f"loaded imports ({len(imports)} triples); auditing {len(cases)} case files\n")

    real_by_class = defaultdict(list)
    nond_by_class = defaultdict(int)
    cases_with_real = 0
    for c in cases:
        real, nond = audit_case(imports, c)
        if real:
            cases_with_real += 1
            for cls in real:
                real_by_class[cls].append(c.stem)
        for cls in nond:
            nond_by_class[cls] += 1

    print("=== REAL D-tuple orphans (claim a nine-category but do not chain to core) ===")
    if real_by_class:
        for cls, in_cases in sorted(real_by_class.items(), key=lambda kv: -len(kv[1])):
            print(f"  {cls}: {len(in_cases)} case(s) e.g. {in_cases[:3]}")
        print(f"  -> {len(real_by_class)} distinct real-orphan classes across {cases_with_real} cases")
    else:
        print("  none -- every nine-category class chains to its core category")

    print("\n=== non-D-tuple classes (analysis/temporal artifacts, outside the disjoint set) ===")
    for cls, n in sorted(nond_by_class.items(), key=lambda kv: -kv[1]):
        print(f"  {cls}: {n} case(s)")
    print(f"  -> {len(nond_by_class)} distinct non-D-tuple class names (expected; not a defect)")


if __name__ == "__main__":
    main()
