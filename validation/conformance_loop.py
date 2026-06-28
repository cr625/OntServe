#!/usr/bin/env python3
"""
Phase D spine: the validate-repair LOOP + Tier-0 deterministic repairs.

Anthropic evaluator-optimizer workflow with a SYMBOLIC evaluator (conformance.py /
SHACL+OWL-RL). Implemented as a plain while-loop. That is the research-recommended
minimum. A LangGraph wrapper (for per-case repair traces/checkpointing) is an optional
later refinement, not needed for the fixed control flow.

Tiering is by VIOLATION TYPE. This module is TIER 0: deterministic, no-LLM repairs keyed
by violation shape. The LLM tiers (Haiku -> Sonnet -> Opus) plug in via the `llm_repair`
callback (Phase D3 Tier 1/2); when Tier 0 cannot fix a violation and no llm_repair is
provided, the loop stops and reports the residual for escalation.

The loop, per round: validate (conformance.py) -> if conforms, done -> apply Tier-0 repairs
(then llm_repair for the rest) -> re-validate. Capped at max_rounds, with EARLY-ABORT if the
violation set does not strictly shrink (the oscillation/no-progress guard).

Tier-0 DisjointCoreCategoryShape repair: an individual reaches two disjoint core categories.
Defer to the PROPERTY-DOMAIN-implied category (a curated, authoritative signal in
core+intermediate) over a type chain to an accumulated extended class. This is the same
authority rule the matcher gate applies at the source, here applied post-hoc. Coarse by
design (re-types to the core category); the LLM tier refines the specific class choice.

Usage (library):
    from conformance_loop import repair_loop
    r = repair_loop(case_ttl_string)            # Tier 0 only
    r = repair_loop(case_ttl_string, llm_repair=my_fn)   # + LLM tiers
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any

from rdflib import Graph, URIRef, RDF, RDFS, OWL

ONTSERVE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ONTSERVE_ROOT))
sys.path.insert(0, str(ONTSERVE_ROOT / "web"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from conformance import validate_conformance_content  # noqa: E402
from pellet_validate import CORE_TTL, INTERMEDIATE_TTL  # noqa: E402

CORE = "http://proethica.org/ontology/core#"
EXTENDED_TTL = ONTSERVE_ROOT / "ontologies" / "proethica-intermediate-extended.ttl"
CORE9 = ["Role", "Principle", "Obligation", "State", "Resource",
         "Action", "Event", "Capability", "Constraint"]
CORE9_URIS = {URIRef(CORE + c) for c in CORE9}


@dataclass
class OntologyContext:
    """class-URI -> core category, and property-URI -> domain core category, resolved
    over the curated core + intermediate (+ extended) ontologies. Built once per loop."""
    class_core: Dict[str, str] = field(default_factory=dict)
    prop_domain_core: Dict[str, str] = field(default_factory=dict)


def build_ontology_context() -> OntologyContext:
    g = Graph()
    for p in (CORE_TTL, INTERMEDIATE_TTL, EXTENDED_TTL):
        if Path(p).exists():
            g.parse(str(p), format="turtle")

    parents: Dict[URIRef, set] = {}
    for s, _, o in g.triples((None, RDFS.subClassOf, None)):
        if isinstance(o, URIRef):
            parents.setdefault(s, set()).add(o)

    def reach_core(cls):
        seen, stack = set(), [cls]
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            if c in CORE9_URIS:
                return str(c).rsplit("#", 1)[-1]
            for sup in parents.get(c, ()):
                stack.append(sup)
        return None

    class_core: Dict[str, str] = {}
    for cls in set(parents.keys()) | set(g.subjects(RDF.type, OWL.Class)):
        if isinstance(cls, URIRef):
            cat = reach_core(cls)
            if cat:
                class_core[str(cls)] = cat

    prop_domain_core: Dict[str, str] = {}
    for p in set(g.subjects(RDF.type, OWL.DatatypeProperty)) | set(g.subjects(RDF.type, OWL.ObjectProperty)):
        for dom in g.objects(p, RDFS.domain):
            cat = class_core.get(str(dom)) or (str(dom).rsplit("#", 1)[-1] if dom in CORE9_URIS else None)
            if cat:
                prop_domain_core[str(p)] = cat
                break
    return OntologyContext(class_core=class_core, prop_domain_core=prop_domain_core)


def _resolve_class_core(cls, case_g: Graph, ctx: OntologyContext, _seen=None) -> Optional[str]:
    """Resolve a class to its core category via the ontology context (core+intermediate+
    extended) AND the case graph's OWN subClassOf chains. This way case-LOCAL classes (declared
    only in the candidate TTL, e.g. a freshly minted FooObligation subClassOf core:Principle)
    resolve too, not just classes already in the curated/accumulated ontologies."""
    s = str(cls)
    if s in ctx.class_core:
        return ctx.class_core[s]
    if cls in CORE9_URIS:
        return s.rsplit("#", 1)[-1]
    _seen = _seen if _seen is not None else set()
    if cls in _seen:
        return None
    _seen.add(cls)
    for parent in case_g.objects(cls, RDFS.subClassOf):
        if isinstance(parent, URIRef):
            cat = _resolve_class_core(parent, case_g, ctx, _seen)
            if cat:
                return cat
    return None


def _individual_type_cats(case_g: Graph, ind: URIRef, ctx: OntologyContext):
    """{type_class_uri: core_cat} for an individual's rdf:type assertions, resolving via
    both the ontology context and the case graph's local subClassOf chains."""
    out = {}
    for t in case_g.objects(ind, RDF.type):
        if t == OWL.NamedIndividual or not isinstance(t, URIRef):
            continue
        cat = _resolve_class_core(t, case_g, ctx)
        if cat:
            out[t] = cat
    return out


def _repair_disjoint_core(case_g: Graph, focus_node: str, ctx: OntologyContext) -> bool:
    """The clash is between the individual's type-chain category(ies) and/or its
    property-domain-implied category. Defer to the PROPERTY DOMAIN (curated, authoritative)
    over a type chain to an accumulated extended class: strip the rdf:type assertion(s)
    whose category conflicts with the single property-domain category, and re-type to that
    category's core class. Deterministic only when exactly ONE property-domain category
    points the way; otherwise return False so the LLM tier handles it. Returns True if changed.
    """
    ind = URIRef(focus_node)
    type_cats = _individual_type_cats(case_g, ind, ctx)  # {type_uri: core_cat}

    prop_cats = set()
    for p, _o in case_g.predicate_objects(ind):
        c = ctx.prop_domain_core.get(str(p))
        if c:
            prop_cats.add(c)

    all_cats = set(type_cats.values()) | prop_cats
    if len(all_cats) < 2:
        return False  # no cross-category clash visible at the asserted/domain layer

    # Authoritative resolution: the property domain. Only act when it is unambiguous.
    if len(prop_cats) != 1:
        return False  # ambiguous -> defer to the LLM tier
    keep = next(iter(prop_cats))

    changed = False
    for t, cat in list(type_cats.items()):
        if cat != keep:
            case_g.remove((ind, RDF.type, t))
            changed = True
    if not changed:
        return False  # the only conflicting signal was the property itself; nothing to strip

    # Assert the kept category as the materialized direct rdf:type proeth-core:<keep>
    # (CMT-1). This direct type is now the sole category signal; the retired
    # conceptCategory literal is no longer written.
    case_g.add((ind, RDF.type, URIRef(CORE + keep)))
    return True


def retype_individual_to_category(case_g: Graph, ind: URIRef, keep: str,
                                  ctx: OntologyContext) -> bool:
    """Re-type an individual to a SINGLE core category `keep`: strip every rdf:type whose
    resolved core category conflicts with keep and assert the materialized direct
    rdf:type proeth-core:<keep> (CMT-1). Shared applier for the LLM tier (model-chosen
    category); the deterministic Tier-0 `_repair_disjoint_core` has its own
    property-domain authority rule and stripping guard. Returns True if the graph
    changed. `keep` must be one of CORE9."""
    if keep not in CORE9:
        return False
    type_cats = _individual_type_cats(case_g, ind, ctx)
    changed = False
    for t, cat in list(type_cats.items()):
        if cat != keep:
            case_g.remove((ind, RDF.type, t))
            changed = True
    keep_uri = URIRef(CORE + keep)
    if (ind, RDF.type, keep_uri) not in case_g:
        case_g.add((ind, RDF.type, keep_uri))
        changed = True
    return changed


def individual_repair_context(case_g: Graph, ind: URIRef, ctx: OntologyContext) -> Dict[str, Any]:
    """Assemble the facts an LLM tier needs to choose a single core category for a
    clashing individual: its label, its type classes + resolved categories, and the
    core categories implied by its properties' domains. Domain-general (no model)."""
    label = next((str(o) for o in case_g.objects(ind, RDFS.label)), str(ind).rsplit("#", 1)[-1])
    type_cats = _individual_type_cats(case_g, ind, ctx)
    prop_cats = {}
    for p, _o in case_g.predicate_objects(ind):
        c = ctx.prop_domain_core.get(str(p))
        if c:
            prop_cats[str(p).rsplit("#", 1)[-1]] = c
    return {
        "individual": str(ind),
        "label": label,
        "type_classes": {str(t).rsplit("#", 1)[-1]: cat for t, cat in type_cats.items()},
        "property_domain_categories": prop_cats,
        "clashing_categories": sorted(set(type_cats.values()) | set(prop_cats.values())),
    }


TIER0: Dict[str, Callable[[Graph, str, OntologyContext], bool]] = {
    "DisjointCoreCategoryShape": _repair_disjoint_core,
}


def apply_tier0(case_g: Graph, violations, ctx: OntologyContext) -> int:
    """Apply deterministic repairs; returns the number of focus nodes changed.
    Groups by (shape, focus_node) so an equivalence class is repaired once."""
    seen = set()
    changed = 0
    for v in violations:
        key = (v.source_shape, v.focus_node)
        if key in seen:
            continue
        seen.add(key)
        fn = TIER0.get(v.source_shape)
        if fn and v.focus_node and fn(case_g, v.focus_node, ctx):
            changed += 1
    return changed


@dataclass
class LoopResult:
    conforms: bool
    rounds: List[Dict[str, Any]]
    reason: str
    case_content: str
    repairs_applied: int = 0


def repair_loop(
    case_content: str,
    max_rounds: int = 3,
    domain: str = "engineering",
    llm_repair: Optional[Callable[[Graph, List, OntologyContext], int]] = None,
) -> LoopResult:
    case_g = Graph()
    case_g.parse(data=case_content, format="turtle")
    ctx = build_ontology_context()
    rounds: List[Dict[str, Any]] = []
    prev_set = None
    total_repairs = 0

    for i in range(max_rounds + 1):
        report = validate_conformance_content("loop", case_g.serialize(format="turtle"), domain=domain)
        if report.error:
            return LoopResult(False, rounds, f"validate-error: {report.error}",
                              case_g.serialize(format="turtle"), total_repairs)
        vset = frozenset((v.source_shape, v.focus_node) for v in report.violations)
        rounds.append({"round": i, "n_violations": len(vset),
                       "shapes": sorted({v.source_shape for v in report.violations})})
        if report.conforms:
            return LoopResult(True, rounds, "conforms",
                              case_g.serialize(format="turtle"), total_repairs)
        if i == max_rounds:
            return LoopResult(False, rounds, "max-rounds",
                              case_g.serialize(format="turtle"), total_repairs)
        if prev_set is not None and not (vset < prev_set):
            return LoopResult(False, rounds, "no-progress (violation set did not strictly shrink)",
                              case_g.serialize(format="turtle"), total_repairs)
        prev_set = vset

        applied = apply_tier0(case_g, report.violations, ctx)
        if llm_repair is not None:
            applied += llm_repair(case_g, report.violations, ctx)
        total_repairs += applied
        if applied == 0:
            return LoopResult(False, rounds, "no-fix-available (Tier-0 exhausted; needs LLM tier)",
                              case_g.serialize(format="turtle"), total_repairs)

    return LoopResult(False, rounds, "max-rounds",
                      case_g.serialize(format="turtle"), total_repairs)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ttl_file")
    ap.add_argument("--max-rounds", type=int, default=3)
    args = ap.parse_args()
    content = Path(args.ttl_file).read_text(encoding="utf-8")
    r = repair_loop(content, max_rounds=args.max_rounds)
    print(f"conforms={r.conforms} reason={r.reason} repairs={r.repairs_applied}")
    for rd in r.rounds:
        print(f"  round {rd['round']}: {rd['n_violations']} violation(s) {rd['shapes']}")
