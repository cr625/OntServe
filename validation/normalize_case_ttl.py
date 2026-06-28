"""D15 normalization: lean (normalized) <-> flat (self-contained) case TTLs.

The corpus denormalizes: each case TTL copies the shared classes it uses (core /
intermediate / extended) alongside the `owl:imports` it already declares. On case-15, 51 of
53 class declarations are such copies. This module provides the two transforms of the D15
"single source of truth, self-containment by export" pattern:

  normalize(case)  -> LEAN form: strip class-declaration triples for classes that already
                      live in the shared store; keep individuals, edges, and genuinely-new
                      (case-only) classes; ensure the imports are declared. The working form.
  flatten(lean)    -> SELF-CONTAINED form: re-materialize the used shared classes (declaration
                      + subClassOf chain to core, bnode-complete) back into the file, for a
                      standalone publishable deposit. The export form.

Validation note (2026-06-01): the LEAN form is Pellet-consistent under the per-case
`pellet_validate._add_missing_subclass_declarations` patch with NO extended load (the patch
reconstructs each case's own subClassOf-core from its individuals' materialized direct type,
locally and drift-free). The harness must NOT load the extended store wholesale -- it is cross-case and
drifted (measured: 119/119 -> 117/119, plus a SafetyObligation self-loop). See
`.claude/plans/ontology-architecture.md` Group A.

This is a reference / backfill tool. The primary landing of D15 is the commit serializer
emitting the lean form directly (so Section C produces lean cases natively), and NOT
re-declaring a matched-to-existing class in extended at all.
"""
from __future__ import annotations

from pathlib import Path
from typing import Set

from rdflib import Graph, RDF, RDFS, OWL, URIRef, BNode

CORE = "http://proethica.org/ontology/core#"
INT_NS = URIRef("http://proethica.org/ontology/intermediate")
EXT_NS = URIRef("http://proethica.org/ontology/intermediate-extended")


def shared_class_set(ont_dir: Path) -> Set[URIRef]:
    """Union of class IRIs declared in core + intermediate + extended (the shared store)."""
    classes: Set[URIRef] = set()
    for name in ("proethica-core.ttl", "proethica-intermediate.ttl",
                 "proethica-intermediate-extended.ttl"):
        p = ont_dir / name
        if not p.exists():
            continue
        g = Graph()
        g.parse(str(p), format="turtle")
        classes |= {s for s in g.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)}
    return classes


def normalize(case_graph: Graph, shared: Set[URIRef]) -> Graph:
    """Return a LEAN copy: class-declaration triples for shared-store classes removed,
    imports of intermediate + extended ensured. Individuals, edges, and case-only class
    declarations are preserved (an individual's `rdf:type <sharedClass>` is kept; the class
    resolves through the import / the per-case validation patch)."""
    lean = Graph()
    for t in case_graph:
        lean.add(t)
    case_classes = {s for s in case_graph.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)}
    for cls in case_classes & shared:
        for t in list(lean.triples((cls, None, None))):
            lean.remove(t)
    # ensure the case declares the imports that supply the stripped classes
    ont = _ontology_subject(lean)
    lean.add((ont, OWL.imports, INT_NS))
    lean.add((ont, OWL.imports, EXT_NS))
    return lean


def flatten(lean_graph: Graph, store: Graph) -> Graph:
    """Return a SELF-CONTAINED copy: every shared class used as a type is re-materialized
    from `store` with its full subClassOf chain to core (bnode-complete), and the volatile
    extended import is dropped. Used for standalone deposit artifacts."""
    flat = Graph()
    for t in lean_graph:
        flat.add(t)
    store_classes = {s for s in store.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)}
    used = {o for _, _, o in flat.triples((None, RDF.type, None))
            if isinstance(o, URIRef) and o not in (OWL.NamedIndividual, OWL.Class)}
    seen: Set[URIRef] = set()
    for cls in used:
        if cls in store_classes:
            _copy_class_chain(cls, store, flat, seen)
    for t in list(flat.triples((None, OWL.imports, EXT_NS))):
        flat.remove(t)
    return flat


def _copy_class_chain(cls: URIRef, store: Graph, dest: Graph, seen: Set[URIRef]) -> None:
    if cls in seen:
        return
    seen.add(cls)
    for s, p, o in store.triples((cls, None, None)):
        dest.add((s, p, o))
        if isinstance(o, BNode):
            _copy_bnode(o, store, dest, set())
    for parent in store.objects(cls, RDFS.subClassOf):
        if isinstance(parent, URIRef) and not str(parent).startswith(CORE):
            _copy_class_chain(parent, store, dest, seen)


def _copy_bnode(b: BNode, store: Graph, dest: Graph, seen: Set[BNode]) -> None:
    """Copy a blank node's triples transitively (restrictions, unionOf lists), so the
    flattened file has no dangling bnodes for the reasoner."""
    if b in seen:
        return
    seen.add(b)
    for s, p, o in store.triples((b, None, None)):
        dest.add((s, p, o))
        if isinstance(o, BNode):
            _copy_bnode(o, store, dest, seen)


def _ontology_subject(g: Graph) -> URIRef:
    for s in g.subjects(RDF.type, OWL.Ontology):
        if isinstance(s, URIRef):
            return s
    # fall back to deriving from a case individual namespace
    for s in g.subjects(RDF.type, OWL.NamedIndividual):
        if isinstance(s, URIRef) and "#" in str(s):
            return URIRef(str(s).split("#")[0])
    raise ValueError("no owl:Ontology subject and no case individual to derive one from")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3 or sys.argv[1] not in ("normalize", "flatten"):
        print("usage: normalize_case_ttl.py {normalize|flatten} <case.ttl> [out.ttl]")
        raise SystemExit(1)
    mode, case_path = sys.argv[1], Path(sys.argv[2])
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else case_path.with_suffix(f".{mode}.ttl")
    ont_dir = Path(__file__).resolve().parents[1] / "ontologies"
    cg = Graph(); cg.parse(str(case_path), format="turtle")
    if mode == "normalize":
        result = normalize(cg, shared_class_set(ont_dir))
    else:
        store = Graph()
        for n in ("proethica-core.ttl", "proethica-intermediate.ttl",
                  "proethica-intermediate-extended.ttl"):
            p = ont_dir / n
            if p.exists():
                store.parse(str(p), format="turtle")
        result = flatten(cg, store)
    result.serialize(destination=str(out), format="turtle")
    print(f"{mode}: {len(cg)} -> {len(result)} triples, wrote {out}")
