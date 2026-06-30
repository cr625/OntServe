#!/usr/bin/env python3
"""
build_foundation.py -- Regenerate proethica-foundation.ttl by bounded MIREOT
extraction from upstream BFO / IAO / RO, with verbatim labels and definitions.

This is the durable, reproducible implementation of Phase 2 of
OntServe/.claude/plans/foundation-mireot-rebuild.md. The previous build ran in a
job temp dir and was lost; this script + its inputs + its output all live under
tools/foundation_rebuild/ so the candidate is regenerable on any machine with:

    cd OntServe && source venv-ontserve/bin/activate
    python tools/foundation_rebuild/build_foundation.py

Inputs (all under tools/foundation_rebuild/sources/, pinned; see SOURCES.md):
    sources/bfo.owl  -- BFO 2020 release 2019-08-26
    sources/iao.owl  -- IAO release 2026-03-30
    sources/ro.owl   -- RO  release 2025-12-17
and the live ontologies/proethica-core.ttl + proethica-intermediate.ttl (seeds)
and ontologies/proethica-foundation.ttl (the curated file, for the parity diff).

Output:
    proethica-foundation.candidate.ttl  -- the regenerated module (drop-in for
    ontologies/proethica-foundation.ttl when Phase 5 swaps it in).

Method (faithful to the plan):
  * Seeds = every obo (BFO|IAO|RO) IRI referenced in core + intermediate, minus
    the three IAO annotation properties (115 definition, 116 editor note, 119
    definition source), plus the five RO grounding properties the methodology
    names. BFO_0000017 (realizable entity) enters as a re-derived ancestor.
  * Classes get their bounded upward subClassOf closure (nearest-in-set parent).
  * Disjointness = every BFO owl:disjointWith pair both of whose members are in
    the class set (yields the 5 pairwise axioms, including disposition/role).
  * Inverses = every owl:inverseOf pair both of whose members are in the prop set.
  * Definitions are verbatim upstream text under the selection policy documented
    at DEFINITION_POLICY below, then deterministically normalized (whitespace +
    apostrophe) to the curated house style.

Identity is unchanged (same ontology IRI, same term IRIs), so existing
extractions stay valid. No reasoning content changes versus the curated file
except the bonus disposition/role disjointness, which is redundant with core's
nine-component disjointness (see plan Phase 4).
"""
import re
import sys
from pathlib import Path

import rdflib
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL

OBO = "http://purl.obolibrary.org/obo/"
IAO_DEF = URIRef(OBO + "IAO_0000115")    # 'definition'
IAO_ELUC = URIRef(OBO + "IAO_0000600")   # 'elucidation' (BFO uses this for its upper terms)
SKOS_DEF = URIRef("http://www.w3.org/2004/02/skos/core#definition")

# Annotation properties that are vocabulary, not declared terms (excluded from seeds).
ANNOTATION_PROP_SEEDS = {OBO + n for n in ("IAO_0000115", "IAO_0000116", "IAO_0000119")}

# The five RO object properties the D-tuple methodology grounds its own relations
# under (plan Phase 1: "plus the 5 RO properties"). Two are inverses pulled below.
RO_GROUNDING_PROPS = {OBO + n for n in (
    "RO_0000087",  # has role
    "RO_0000081",  # role of            (inverse of has role)
    "RO_0000056",  # participates in
    "RO_0000057",  # has participant    (inverse of participates in)
    "RO_0002411",  # causally upstream of
)}

HERE = Path(__file__).resolve().parent
ONTOLOGIES = HERE.parent.parent / "ontologies"
SRC = HERE / "sources"
OUT = HERE / "proethica-foundation.candidate.ttl"

# ---------------------------------------------------------------------------
# DEFINITION_POLICY: which upstream annotation supplies each term's definition.
# Selection order (first hit wins): IAO IAO_0000115 -> BFO IAO_0000600 ->
# BFO IAO_0000115 -> RO IAO_0000115. Documented overrides force a specific
# source where the default would pick a defective string.
# ---------------------------------------------------------------------------
DEFINITION_OVERRIDE = {
    # IAO's IAO_0000115 for realizable entity is grammatically defective
    # ("inheres in continuant entities and are not exhibited..."); BFO's
    # [058-002] elucidation is the standard formal statement, and is what the
    # curated foundation used. Force the BFO elucidation here.
    OBO + "BFO_0000017": ("bfo", IAO_ELUC),
}

# Emission order, matching the curated file (verified to equal the derived set).
BFO_CLASS_ORDER = ["BFO_0000001", "BFO_0000002", "BFO_0000003", "BFO_0000004",
                   "BFO_0000020", "BFO_0000031", "BFO_0000017", "BFO_0000023",
                   "BFO_0000016", "BFO_0000015", "BFO_0000040"]
IAO_CLASS_ORDER = ["IAO_0000030", "IAO_0000033", "IAO_0000310", "IAO_0000314"]
RO_PROP_ORDER = ["RO_0000087", "RO_0000081", "RO_0000056", "RO_0000057", "RO_0002411"]

# ProEthica-specific annotations carried over from the curated foundation (not
# upstream): a domain stipulation on the directive-information-entity branch.
SCOPE_NOTES = {
    OBO + "IAO_0000033": (
        "Used by proethica-core for Principle, Obligation, and Constraint (the "
        "prescriptive, world-to-word components). IAO declares no descriptive-ICE "
        "counterpart and no directive/descriptive disjointness; the Resource-vs-"
        "normative separation in proethica-core is a domain stipulation of the "
        "D-tuple methodology, not an IAO entailment."
    ),
}


def norm(text):
    """Deterministic house-style normalization: straighten apostrophes, collapse
    whitespace runs. Selection is verbatim; this is a fixed post-step."""
    if text is None:
        return None
    s = str(text).replace("’", "'").replace("‘", "'")
    return " ".join(s.split())


def obo_refs(graph):
    """All obo (BFO|IAO|RO)_NNN IRIs referenced anywhere in a graph."""
    pat = re.compile(r"^(BFO|IAO|RO)_\d+$")
    out = set()
    for triple in graph:
        for node in triple:
            if isinstance(node, URIRef) and str(node).startswith(OBO):
                if pat.match(str(node)[len(OBO):]):
                    out.add(str(node))
    return out


def nearest_parent_in_set(up, term, class_set):
    """Walk rdfs:subClassOf upward to the first named obo class in class_set."""
    seen = set()
    frontier = [term]
    while frontier:
        nxt = []
        for c in frontier:
            for parent in up.objects(URIRef(c), RDFS.subClassOf):
                if not isinstance(parent, URIRef):
                    continue  # skip anonymous restrictions
                ps = str(parent)
                if ps in class_set and ps != term:
                    return ps
                if ps not in seen:
                    seen.add(ps)
                    nxt.append(ps)
        frontier = nxt
    return None


def pick_definition(term, iao, bfo, ro):
    src_g = {"iao": iao, "bfo": bfo, "ro": ro}
    if term in DEFINITION_OVERRIDE:
        which, prop = DEFINITION_OVERRIDE[term]
        return src_g[which].value(URIRef(term), prop)
    for g, prop in ((iao, IAO_DEF), (bfo, IAO_ELUC), (bfo, IAO_DEF), (ro, IAO_DEF)):
        v = g.value(URIRef(term), prop)
        if v is not None:
            return v
    return None


def main():
    # Load everything.
    bfo, iao, ro = Graph(), Graph(), Graph()
    bfo.parse(SRC / "bfo.owl")
    iao.parse(SRC / "iao.owl")
    ro.parse(SRC / "ro.owl")
    up = bfo + iao + ro
    core = Graph(); core.parse(ONTOLOGIES / "proethica-core.ttl")
    inter = Graph(); inter.parse(ONTOLOGIES / "proethica-intermediate.ttl")
    cur = Graph(); cur.parse(ONTOLOGIES / "proethica-foundation.ttl")

    # 1. Derive seeds.
    referenced = (obo_refs(core) | obo_refs(inter)) - ANNOTATION_PROP_SEEDS
    prop_seeds = {t for t in (referenced | RO_GROUNDING_PROPS)
                  if (URIRef(t), RDF.type, OWL.ObjectProperty) in up}
    class_direct = {t for t in referenced
                    if (URIRef(t), RDF.type, OWL.Class) in up} - prop_seeds

    # 2. Class set = direct seeds + bounded upward closure (named obo ancestors).
    class_set = set(class_direct)
    changed = True
    while changed:
        changed = False
        for c in list(class_set):
            for parent in up.objects(URIRef(c), RDFS.subClassOf):
                ps = str(parent)
                if isinstance(parent, URIRef) and ps.startswith(OBO) and ps not in class_set:
                    if re.match(r"^(BFO|IAO|RO)_\d+$", ps[len(OBO):]):
                        class_set.add(ps); changed = True

    # 3. Footprint parity check against the curated file.
    expected_classes = {OBO + x for x in BFO_CLASS_ORDER + IAO_CLASS_ORDER}
    expected_props = {OBO + x for x in RO_PROP_ORDER}
    problems = []
    if class_set != expected_classes:
        problems.append(f"class set != curated footprint\n  extra:   "
                        f"{sorted(s[len(OBO):] for s in class_set - expected_classes)}\n  missing: "
                        f"{sorted(s[len(OBO):] for s in expected_classes - class_set)}")
    if prop_seeds != expected_props:
        problems.append(f"property set != curated footprint\n  extra:   "
                        f"{sorted(s[len(OBO):] for s in prop_seeds - expected_props)}\n  missing: "
                        f"{sorted(s[len(OBO):] for s in expected_props - prop_seeds)}")

    # 4. Extract per-term data.
    def short(uri):
        local = uri[len(OBO):]
        pre = {"BFO": "bfo", "IAO": "iao", "RO": "ro"}[local.split("_")[0]]
        return f"{pre}:{local.split('_')[1]}"

    def src_file(uri):
        return {"BFO": "obo:bfo.owl", "IAO": "obo:iao.owl",
                "RO": "obo:ro.owl"}[uri[len(OBO):].split("_")[0]]

    labels, defs, parents = {}, {}, {}
    for uri in expected_classes | expected_props:
        labels[uri] = norm(up.value(URIRef(uri), RDFS.label))
        defs[uri] = norm(pick_definition(uri, iao, bfo, ro))
    for uri in expected_classes:
        parents[uri] = nearest_parent_in_set(up, uri, class_set)

    # Disjointness: BFO disjointWith pairs both members in the class set.
    disjoint = []
    for s, _, o in bfo.triples((None, OWL.disjointWith, None)):
        if str(s) in class_set and str(o) in class_set:
            pair = tuple(sorted((str(s), str(o))))
            if pair not in disjoint:
                disjoint.append(pair)
    disjoint.sort(key=lambda p: (BFO_CLASS_ORDER.index(p[0][len(OBO):]) if p[0][len(OBO):] in BFO_CLASS_ORDER else 99,
                                 BFO_CLASS_ORDER.index(p[1][len(OBO):]) if p[1][len(OBO):] in BFO_CLASS_ORDER else 99))

    # Inverses: owl:inverseOf pairs both members in the prop set.
    inverses = {}
    for s, _, o in ro.triples((None, OWL.inverseOf, None)):
        if str(s) in prop_seeds and str(o) in prop_seeds:
            inverses[str(s)] = str(o)

    # 5. Emit the candidate TTL text.
    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')

    lines = []
    A = lines.append
    A("@prefix : <http://proethica.org/ontology/foundation#> .")
    A("@prefix bfo: <http://purl.obolibrary.org/obo/BFO_> .")
    A("@prefix iao: <http://purl.obolibrary.org/obo/IAO_> .")
    A("@prefix ro: <http://purl.obolibrary.org/obo/RO_> .")
    A("@prefix obo: <http://purl.obolibrary.org/obo/> .")
    A("@prefix owl: <http://www.w3.org/2002/07/owl#> .")
    A("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
    A("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .")
    A("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .")
    A("@prefix dc: <http://purl.org/dc/elements/1.1/> .")
    A("@prefix skos: <http://www.w3.org/2004/02/skos/core#> .")
    A("")
    A("#################################################################")
    A("# ProEthica Foundation Stub (tool-extracted)")
    A("#")
    A("# Regenerated by tools/foundation_rebuild/build_foundation.py via bounded")
    A("# MIREOT extraction from pinned upstream releases, with verbatim labels and")
    A("# definitions. Holds only the BFO / IAO / RO terms that proethica-core and")
    A("# proethica-intermediate reference, declared locally so the alignment")
    A("# resolves and is reasoned, without importing the full upstream ontologies.")
    A("#")
    A("# Upstream sources (versionIRI):")
    A("#   BFO  http://purl.obolibrary.org/obo/bfo/2019-08-26/bfo.owl")
    A("#   IAO  http://purl.obolibrary.org/obo/iao/2026-03-30/iao.owl")
    A("#   RO   http://purl.obolibrary.org/obo/ro/releases/2025-12-17/ro.owl")
    A("#")
    A("# Definitions: IAO IAO_0000115 preferred, else BFO IAO_0000600 elucidation,")
    A("# else BFO/RO IAO_0000115 (one override: realizable entity uses the BFO")
    A("# elucidation). Text is upstream-verbatim, normalized for whitespace and")
    A("# apostrophes only. Disjointness axioms are the BFO owl:disjointWith pairs")
    A("# whose members are both in scope (continuant/occurrent; the IC/SDC/GDC")
    A("# triangle; and disposition/role).")
    A("#################################################################")
    A("")
    A("<http://proethica.org/ontology/foundation> a owl:Ontology ;")
    A('    rdfs:label "ProEthica Foundation Stub"@en ;')
    A('    dc:creator "ProEthica AI"@en ;')
    A('    dc:date "2026-06-30"^^xsd:date ;')
    A('    owl:versionInfo "2.0.0"^^xsd:string ;')
    A('    rdfs:comment "Tool-extracted BFO 2020 / IAO / RO subset: the foundational '
      'terms proethica-core references, MIREOT-extracted with verbatim labels and '
      'definitions so the alignment resolves and is reasoned. Regenerated by '
      'tools/foundation_rebuild/build_foundation.py."@en .')
    A("")

    def emit_term(uri, kind):
        A(f"{short(uri)} a {kind} ;")
        if kind == "owl:Class" and parents.get(uri):
            A(f"    rdfs:subClassOf {short(parents[uri])} ;")
        if kind == "owl:ObjectProperty" and uri in inverses:
            A(f"    owl:inverseOf {short(inverses[uri])} ;")
        A(f'    rdfs:label "{esc(labels[uri])}"@en ;')
        A(f'    skos:definition "{esc(defs[uri])}"@en ;')
        if uri in SCOPE_NOTES:
            A(f"    rdfs:isDefinedBy {src_file(uri)} ;")
            A(f'    skos:scopeNote "{esc(SCOPE_NOTES[uri])}"@en .')
        else:
            A(f"    rdfs:isDefinedBy {src_file(uri)} .")
        A("")

    A("#################################################################")
    A("# BFO 2020 classes (the upper backbone core aligns to)")
    A("#################################################################")
    A("")
    for x in BFO_CLASS_ORDER:
        emit_term(OBO + x, "owl:Class")

    A("#################################################################")
    A("# BFO 2020 foundational disjointness (owl:disjointWith pairs in scope)")
    A("#################################################################")
    A("")
    label_of = {OBO + x: labels[OBO + x] for x in BFO_CLASS_ORDER}
    for a, b in disjoint:
        A(f"{short(a)} owl:disjointWith {short(b)} .   # {label_of[a]} vs {label_of[b]}")
    A("")

    A("#################################################################")
    A("# IAO classes (the information-artifact branch core aligns to)")
    A("#################################################################")
    A("")
    for x in IAO_CLASS_ORDER:
        emit_term(OBO + x, "owl:Class")

    A("#################################################################")
    A("# OBO Relations Ontology object properties (the relation superproperties")
    A("# core grounds its own properties under)")
    A("#################################################################")
    A("")
    for x in RO_PROP_ORDER:
        emit_term(OBO + x, "owl:ObjectProperty")

    OUT.write_text("\n".join(lines).rstrip() + "\n")

    # 6. Verification report.
    print("=" * 70)
    print("FOUNDATION CANDIDATE BUILD REPORT")
    print("=" * 70)
    if problems:
        print("\n!!! FOOTPRINT PARITY PROBLEMS:")
        for p in problems:
            print("  " + p.replace("\n", "\n  "))
        print()
    else:
        print(f"\nFootprint parity OK: {len(expected_classes)} classes "
              f"({len(BFO_CLASS_ORDER)} BFO + {len(IAO_CLASS_ORDER)} IAO) + "
              f"{len(expected_props)} object properties, derived set == curated set.")

    print(f"\nDisjointness pairs extracted from BFO ({len(disjoint)}):")
    for a, b in disjoint:
        print(f"  {short(a)} <> {short(b)}   ({label_of[a]} / {label_of[b]})")

    print("\nDefinition diff vs curated foundation (skos:definition):")
    n_same = 0
    for uri in [OBO + x for x in BFO_CLASS_ORDER + IAO_CLASS_ORDER + RO_PROP_ORDER]:
        c = cur.value(URIRef(uri), SKOS_DEF)
        cand = defs[uri]
        if c is not None and str(c) == cand:
            n_same += 1
        else:
            print(f"  CHANGED {short(uri)} ({labels[uri]}):")
            print(f"    curated:   {c}")
            print(f"    candidate: {cand}")
    print(f"\n  {n_same}/{len(BFO_CLASS_ORDER)+len(IAO_CLASS_ORDER)+len(RO_PROP_ORDER)} "
          f"definitions identical to the curated file.")

    print(f"\nWrote {OUT}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
