#!/usr/bin/env python3
"""
SHACL + OWL-RL conformance gate (Phase C of the extraction-conformance plan).

Complements the Pellet OWL-DL reasoner: Pellet gives a binary consistent/inconsistent
verdict; this gives ACTIONABLE per-node violation reports (which individual, which rule)
and is the rules-as-data, domain-portable layer. It is also the foundation of the
Phase-D validate-repair loop's `validate_concept` step.

Mechanism: build the same merged graph pellet_validate uses (core + intermediate + case,
with the materialized-direct-type subClassOf fallback and external owl:imports stripped), then run
pyshacl with inference='owlrl' so the OWL-RL closure (subClassOf* transitivity + rdfs:domain
inference + disjointness) is materialized before the shapes run. The core shapes
(validation/shapes/core-shapes.ttl) then flag any individual reaching two disjoint core
categories, with a per-node message. This is the F2-class clash.

Domain portability: core-shapes.ttl is domain-general; a per-domain
validation/shapes/<domain>-shapes.ttl (or the list in config/domains/<domain>.yaml,
key `shapes_files`) layers on top. Adding a domain = adding a shapes file, not new code.

Usage (library):
    from conformance import validate_conformance_case, validate_conformance_file
    r = validate_conformance_case("proethica-case-8")
    r = validate_conformance_file("/path/to/case.ttl")

Usage (CLI):
    python validation/conformance.py proethica-case-8
    python validation/conformance.py --file /path/to/case.ttl
"""
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any

from rdflib import Graph, URIRef
from rdflib.namespace import SH, RDF

ONTSERVE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ONTSERVE_ROOT))
sys.path.insert(0, str(ONTSERVE_ROOT / "web"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pellet_validate import (  # noqa: E402
    _build_merged_graph,
    _fetch_case_content_from_db,
)

SHAPES_DIR = Path(__file__).resolve().parent / "shapes"
CORE_SHAPES = SHAPES_DIR / "core-shapes.ttl"


@dataclass
class Violation:
    focus_node: str
    message: str
    severity: str
    source_shape: str


@dataclass
class ConformanceResult:
    name: str
    conforms: bool
    violations: List[Violation] = field(default_factory=list)
    error: Optional[str] = None
    report_text: Optional[str] = None

    def summary(self) -> str:
        if self.error:
            return f"{self.name}: ERROR {self.error}"
        if self.conforms:
            return f"{self.name}: CONFORMS (0 violations)"
        return f"{self.name}: {len(self.violations)} violation(s)"


def _default_shapes(domain: str = "engineering") -> List[Path]:
    """core-shapes (always) + a per-domain shapes file if present."""
    shapes = [CORE_SHAPES]
    domain_file = SHAPES_DIR / f"{domain}-shapes.ttl"
    if domain_file.exists():
        shapes.append(domain_file)
    return shapes


def _load_shapes(shapes_paths: List[Path]) -> Graph:
    g = Graph()
    for p in shapes_paths:
        g.parse(str(p), format="turtle")
    return g


def _parse_report(report_graph: Graph) -> List[Violation]:
    out: List[Violation] = []
    for result in report_graph.subjects(RDF.type, SH.ValidationResult):
        focus = report_graph.value(result, SH.focusNode)
        msg = report_graph.value(result, SH.resultMessage)
        sev = report_graph.value(result, SH.resultSeverity)
        shape = report_graph.value(result, SH.sourceShape)

        def _local(u):
            if u is None:
                return ""
            s = str(u)
            return s.split("#")[-1].split("/")[-1] if isinstance(u, URIRef) else s
        out.append(Violation(
            focus_node=str(focus) if focus is not None else "",
            message=str(msg) if msg is not None else "",
            severity=_local(sev) or "Violation",
            source_shape=_local(shape),
        ))
    return out


def validate_conformance_content(
    name: str, case_content: str,
    shapes_paths: Optional[List[Path]] = None, domain: str = "engineering",
) -> ConformanceResult:
    import pyshacl
    try:
        data = _build_merged_graph(case_content)
    except Exception as exc:  # noqa: BLE001
        return ConformanceResult(name=name, conforms=False,
                                 error=f"merge-failed: {type(exc).__name__}: {exc}")
    try:
        shapes = _load_shapes(shapes_paths or _default_shapes(domain))
    except Exception as exc:  # noqa: BLE001
        return ConformanceResult(name=name, conforms=False,
                                 error=f"shapes-load-failed: {type(exc).__name__}: {exc}")
    try:
        conforms, report_graph, report_text = pyshacl.validate(
            data,
            shacl_graph=shapes,
            inference="owlrl",
            advanced=True,          # enable sh:sparql constraints
            abort_on_first=False,
            allow_warnings=True,
            meta_shacl=False,
            js=False,
            debug=False,
        )
    except Exception as exc:  # noqa: BLE001
        return ConformanceResult(name=name, conforms=False,
                                 error=f"shacl-validate-failed: {type(exc).__name__}: {str(exc)[:300]}")
    return ConformanceResult(
        name=name,
        conforms=bool(conforms),
        violations=_parse_report(report_graph),
        report_text=report_text,
    )


def validate_conformance_case(case_name: str, domain: str = "engineering") -> ConformanceResult:
    try:
        content = _fetch_case_content_from_db(case_name)
    except Exception as exc:  # noqa: BLE001
        return ConformanceResult(name=case_name, conforms=False,
                                 error=f"db-fetch-failed: {exc}")
    return validate_conformance_content(case_name, content, domain=domain)


def validate_conformance_file(ttl_path: str, domain: str = "engineering") -> ConformanceResult:
    p = Path(ttl_path)
    content = p.read_text(encoding="utf-8")
    return validate_conformance_content(p.name, content, domain=domain)


# --- D1: repair-oriented report (grouped by signature + NL gloss) -----------------
# The Phase-D loop's `validate_concept` evaluator. Groups violations by shape so the
# repair tier handles an equivalence class once (the xpSHACL pattern), and attaches a
# concise NL gloss (the repair INSTRUCTION) instead of raw Turtle. Domain-general for the
# core shapes; per-domain shapes can extend SHAPE_GLOSS via their own entry.
SHAPE_GLOSS: Dict[str, str] = {
    "DisjointCoreCategoryShape": (
        "Entity is typed to two disjoint core categories. Re-type it to the single category "
        "its definition + properties support, or drop the conflicting type/property "
        "(e.g. an obligation-domain property on a Principle-typed entity)."
    ),
    "NoOwlNothingShape": (
        "Entity is unsatisfiable (inferred owl:Nothing). Resolve the underlying disjointness "
        "or cardinality clash before committing."
    ),
}


def conformance_report_content(
    name: str, case_content: str, domain: str = "engineering",
) -> Dict[str, Any]:
    """JSON-serializable, repair-oriented report for the validate-repair loop.

    {name, conforms, n_violations, groups:[{shape, gloss, focus_nodes:[...], count,
     sample_message}], error?}
    """
    r = validate_conformance_content(name, case_content, domain=domain)
    if r.error:
        return {"name": name, "conforms": False, "error": r.error, "n_violations": 0, "groups": []}
    groups: Dict[str, Dict[str, Any]] = {}
    for v in r.violations:
        sig = v.source_shape or "UnknownShape"
        g = groups.setdefault(sig, {
            "shape": sig,
            "gloss": SHAPE_GLOSS.get(sig, (v.message or "")[:160]),
            "focus_nodes": [],
            "count": 0,
            "sample_message": v.message,
        })
        if v.focus_node and v.focus_node not in g["focus_nodes"]:
            g["focus_nodes"].append(v.focus_node)
        g["count"] += 1
    return {
        "name": name,
        "conforms": bool(r.conforms),
        "n_violations": len(r.violations),
        "groups": list(groups.values()),
    }


def conformance_report_case(case_name: str, domain: str = "engineering") -> Dict[str, Any]:
    try:
        content = _fetch_case_content_from_db(case_name)
    except Exception as exc:  # noqa: BLE001
        return {"name": case_name, "conforms": False, "error": f"db-fetch-failed: {exc}",
                "n_violations": 0, "groups": []}
    return conformance_report_content(case_name, content, domain=domain)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--file":
        r = validate_conformance_file(args[1])
    else:
        r = validate_conformance_case(args[0])
    print(r.summary())
    for v in r.violations[:40]:
        node = v.focus_node.split("#")[-1].split("/")[-1]
        print(f"  [{v.severity}] {node} <- {v.source_shape}: {v.message[:160]}")
    return 0 if (r.conforms or r.error is None) else 1


if __name__ == "__main__":
    main()
