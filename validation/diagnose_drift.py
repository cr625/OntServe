#!/usr/bin/env python3
"""
Diagnose the 18 Pellet-inconsistent dev case ontologies (Phase 1.7).

For each case it answers three questions:
  A. Reproduce: is it inconsistent under the CURRENT validator context
     (core + intermediate only, conceptCategory subclass fallback)?
  B. Context fix: does loading proethica-intermediate-extended.ttl (the 219
     discovered classes the validator currently omits) make it consistent?
  C. Deterministic clash: independent of any reasoner, which named individuals
     resolve via rdf:type -> subClassOf* to >= 2 DISJOINT core categories?
     Also: which object-property edges point at an endpoint whose resolved
     core category contradicts the property's declared range?

Pure-rdflib analysis (C) is deterministic; the conceptCategory fallback in
pellet_validate is NOT (it reads the first instance's literal in set order).

Usage:
  python validation/diagnose_drift.py 7 9 12 ...          # specific cases
  python validation/diagnose_drift.py                     # the known 18
"""
import json
import os
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import rdflib
from rdflib import Graph, OWL, RDF, RDFS, URIRef, Literal

ONTSERVE_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ONTSERVE_ROOT / "web"
sys.path.insert(0, str(ONTSERVE_ROOT))
sys.path.insert(0, str(WEB_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pellet_validate import (  # noqa: E402
    CORE_TTL,
    INTERMEDIATE_TTL,
    _add_missing_subclass_declarations,
    _fetch_case_content_from_db,
)

EXTENDED_TTL = ONTSERVE_ROOT / "ontologies" / "proethica-intermediate-extended.ttl"

CORE = "http://proethica.org/ontology/core#"
CORE_CATEGORIES = [
    "Role", "Principle", "Obligation", "State", "Resource",
    "Action", "Event", "Capability", "Constraint",
]
CORE_CAT_URIS = {URIRef(CORE + c): c for c in CORE_CATEGORIES}

DEFAULT_18 = [7, 9, 12, 16, 58, 59, 85, 109, 112, 120, 131, 139, 142, 146, 147, 150, 161, 162]


def _strip_external_imports(g: Graph) -> None:
    for s, p, o in list(g.triples((None, OWL.imports, None))):
        g.remove((s, p, o))


def _base_graph(with_extended: bool) -> Graph:
    g = Graph()
    g.parse(str(CORE_TTL), format="turtle")
    g.parse(str(INTERMEDIATE_TTL), format="turtle")
    if with_extended:
        g.parse(str(EXTENDED_TTL), format="turtle")
    return g


def run_pellet(g: Graph):
    """Return (consistent: bool|None, note: str). None = parse/serialize error."""
    import owlready2
    try:
        serialized = g.serialize(format="nt")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nt", delete=False, encoding="utf-8") as f:
            f.write(serialized)
            tmp = f.name
    except Exception as exc:  # noqa: BLE001
        return None, f"serialize-failed: {type(exc).__name__}"
    try:
        try:
            world = owlready2.World()
            world.get_ontology(f"file://{tmp}").load(format="ntriples")
        except Exception as exc:  # noqa: BLE001
            return None, f"parse-failed: {type(exc).__name__}: {str(exc)[:200]}"
        try:
            onto = list(world.ontologies.values())[0]
            with onto:
                owlready2.sync_reasoner_pellet(world, infer_property_values=False, debug=0)
            return True, "consistent"
        except owlready2.OwlReadyInconsistentOntologyError:
            return False, "inconsistent"
        except Exception as exc:  # noqa: BLE001
            return None, f"reasoner-error: {type(exc).__name__}: {str(exc)[:200]}"
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def resolve_core_categories(g: Graph):
    """For every class in g, compute the set of core-category names reachable
    via rdfs:subClassOf* (transitive). Deterministic. Returns dict[class]->set."""
    # direct parents
    parents = defaultdict(set)
    for s, _, o in g.triples((None, RDFS.subClassOf, None)):
        if isinstance(o, URIRef):
            parents[s].add(o)
    cache = {}

    def reach(cls, seen):
        if cls in cache:
            return cache[cls]
        cats = set()
        if cls in CORE_CAT_URIS:
            cats.add(CORE_CAT_URIS[cls])
        for p in parents.get(cls, ()):  # walk up
            if p in seen:
                continue
            cats |= reach(p, seen | {p})
        # don't cache while inside an active recursion path that hit a cycle guard
        cache[cls] = cats
        return cats

    out = {}
    classes = set(g.subjects(RDF.type, OWL.Class)) | set(parents.keys())
    for c in classes:
        if isinstance(c, URIRef):
            out[c] = reach(c, {c})
    return out


def object_properties(g: Graph):
    """Return dict[prop] -> (set(domain core cats), set(range core cats)) using
    declared rdfs:domain/range resolved through the class->core map."""
    cat_map = resolve_core_categories(g)
    props = {}
    for p in g.subjects(RDF.type, OWL.ObjectProperty):
        dom = set()
        rng = set()
        for d in g.objects(p, RDFS.domain):
            dom |= cat_map.get(d, set())
        for r in g.objects(p, RDFS.range):
            rng |= cat_map.get(r, set())
        props[p] = (dom, rng)
    return props


def deterministic_clashes(case_content: str):
    """Build core+intermediate+extended+case, then find:
       - individuals whose rdf:type chain reaches >= 2 disjoint core cats
       - object-property edges whose endpoint core cat contradicts range
       - object properties given literal values
    """
    g = _base_graph(with_extended=True)
    g.parse(data=case_content, format="turtle")
    _strip_external_imports(g)

    cat_map = resolve_core_categories(g)
    props = object_properties(g)
    obj_props = set(props.keys())

    multi = []  # individual clashes
    for ind in set(g.subjects(RDF.type, OWL.NamedIndividual)):
        types = [t for t in g.objects(ind, RDF.type) if t != OWL.NamedIndividual and isinstance(t, URIRef)]
        cats = set()
        type_cat = {}
        for t in types:
            tc = cat_map.get(t, set())
            type_cat[str(t)] = sorted(tc)
            cats |= tc
        if len(cats) >= 2:
            multi.append({
                "individual": str(ind),
                "categories": sorted(cats),
                "types": type_cat,
            })

    # object property given a literal
    lit_on_objprop = []
    for s, p, o in g:
        if p in obj_props and isinstance(o, Literal):
            lit_on_objprop.append({"s": str(s), "p": str(p), "literal": str(o)[:60]})

    # range violations on edges
    range_viol = []
    for p, (dom, rng) in props.items():
        if not rng:
            continue
        for s, _, o in g.triples((None, p, None)):
            if not isinstance(o, URIRef):
                continue
            ocats = set()
            for t in g.objects(o, RDF.type):
                if isinstance(t, URIRef):
                    ocats |= cat_map.get(t, set())
            if ocats and not (ocats & rng):
                range_viol.append({
                    "s": str(s), "p": str(p), "o": str(o),
                    "object_cats": sorted(ocats), "range_cats": sorted(rng),
                })

    return {
        "individual_category_clashes": multi,
        "object_prop_literal_values": lit_on_objprop,
        "range_violations": range_viol,
    }


def diagnose(case_num: int):
    name = f"proethica-case-{case_num}"
    content = _fetch_case_content_from_db(name)

    # A: current validator behavior (core+intermediate + conceptCategory fallback)
    gA = _base_graph(with_extended=False)
    gA.parse(data=content, format="turtle")
    _strip_external_imports(gA)
    _add_missing_subclass_declarations(gA)
    consA, noteA = run_pellet(gA)

    # B: with extended loaded (+ fallback for any still-orphan class)
    gB = _base_graph(with_extended=True)
    gB.parse(data=content, format="turtle")
    _strip_external_imports(gB)
    _add_missing_subclass_declarations(gB)
    consB, noteB = run_pellet(gB)

    det = deterministic_clashes(content)
    return {
        "case": case_num,
        "name": name,
        "current_context_consistent": consA,
        "current_note": noteA,
        "with_extended_consistent": consB,
        "extended_note": noteB,
        "n_individual_clashes": len(det["individual_category_clashes"]),
        "n_objprop_literals": len(det["object_prop_literal_values"]),
        "n_range_violations": len(det["range_violations"]),
        "detail": det,
    }


def main():
    args = sys.argv[1:]
    cases = [int(a) for a in args] if args else DEFAULT_18
    out = []
    print(f"Diagnosing {len(cases)} cases...\n")
    print(f"{'case':>5} {'A:cur':>7} {'B:+ext':>7} {'clash':>6} {'litOP':>6} {'rngV':>5}")
    for c in cases:
        t0 = time.time()
        try:
            r = diagnose(c)
        except Exception as exc:  # noqa: BLE001
            print(f"{c:>5}  ERROR {type(exc).__name__}: {str(exc)[:80]}")
            out.append({"case": c, "error": f"{type(exc).__name__}: {exc}"})
            continue
        out.append(r)
        def fmt(v):
            return {True: "OK", False: "INCON", None: "ERR"}[v]
        print(f"{r['case']:>5} {fmt(r['current_context_consistent']):>7} "
              f"{fmt(r['with_extended_consistent']):>7} "
              f"{r['n_individual_clashes']:>6} {r['n_objprop_literals']:>6} "
              f"{r['n_range_violations']:>5}  ({time.time()-t0:.1f}s)")

    out_path = ONTSERVE_ROOT / "docs-internal" / "KI2026" / "drift_diagnosis.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nFull detail: {out_path}")


if __name__ == "__main__":
    main()
