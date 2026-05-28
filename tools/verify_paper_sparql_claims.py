#!/usr/bin/env python3
"""
Verify KI2026 paper SPARQL-content claims against the live OntServe deployment.

Companion to ``tools/verify_paper_claims.py`` (which checks HTTP reachability of
named ontologies). This tool checks the *content* claims that a reviewer can
spot-check via SPARQL: corpus-level edge counts, case-86 (Figure 1) class
names and defeasibility edges, named-class existence, and the Obligation
subclass hierarchy.

Built 2026-05-28 from the camera-ready verification pass that consolidated
five ad-hoc ``verify_*.py`` scripts (previously in the KI2026 paper directory).
That audit found the case-86 fixture had drifted from the live deployment after
the recent case re-extraction (``ClientConfidentialityObligation`` and
``PublicWelfareParamountObligation`` were no longer in the live ontology;
``ConfidentialityObligation`` and ``SafetyObligation`` are the names the live
case-86 individual is typed under). The fixture was repaired; this tool stays
as the standing check so any future drift between the paper and the deployment
is visible from one command.

Usage
-----

    python tools/verify_paper_sparql_claims.py corpus
    python tools/verify_paper_sparql_claims.py case86
    python tools/verify_paper_sparql_claims.py case86-obligations
    python tools/verify_paper_sparql_claims.py classes
    python tools/verify_paper_sparql_claims.py classes --names Foo,Bar
    python tools/verify_paper_sparql_claims.py obligations
    python tools/verify_paper_sparql_claims.py all
    python tools/verify_paper_sparql_claims.py corpus --base-url https://ontserve.ontorealm.net
"""

import argparse
import json
import sys
import urllib.request
from typing import Dict, List

DEFAULT_BASE = "https://ontserve.ontorealm.net"


# ---------------------------------------------------------------------------
# Shared SPARQL helpers
# ---------------------------------------------------------------------------

def run(query: str, base_url: str, timeout: int = 90) -> Dict:
    """POST a SPARQL query to ``<base_url>/sparql`` and return the JSON result."""
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/sparql",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def shorten(iri: str) -> str:
    """Return the local name (fragment after ``#`` or last path segment)."""
    if "#" in iri:
        return iri.split("#")[-1]
    return iri.rsplit("/", 1)[-1]


def safe_print(s: str) -> None:
    """Print ASCII-only (some terminals on Windows trip on the source-text UTF)."""
    sys.stdout.write(s.encode("ascii", "replace").decode("ascii"))
    sys.stdout.write("\n")


def _first_value(result: Dict) -> str:
    try:
        b = result["results"]["bindings"][0]
        for _, v in b.items():
            return v.get("value", "?")
        return "?"
    except Exception:
        return f"?? {str(result)[:200]}"


# ---------------------------------------------------------------------------
# Subcommand: corpus
# Numeric claims a reviewer can check at a glance: case count, total
# defeasibility edges, and the case-86 type assertions used in Figure 1.
# ---------------------------------------------------------------------------

_CORPUS_QUERIES: Dict[str, str] = {
    "case_count": """
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT (COUNT(DISTINCT ?case) AS ?n) WHERE {
          ?case a owl:Ontology .
          FILTER(STRSTARTS(STR(?case), "http://proethica.org/ontology/case/"))
        }
    """,
    "competesWith_count": """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT (COUNT(*) AS ?n) WHERE { ?s core:competesWith ?o . }
    """,
    "prevailsOver_count": """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT (COUNT(*) AS ?n) WHERE { ?s core:prevailsOver ?o . }
    """,
    "defeasibleUnder_count": """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT (COUNT(*) AS ?n) WHERE { ?s core:defeasibleUnder ?o . }
    """,
    # The endpoint merges named graphs into the default graph, so GRAPH ?g
    # syntax 400s -- derive the case base from the subject IRI prefix instead.
    "cases_with_prevailsOver": """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT (COUNT(DISTINCT ?case) AS ?n) WHERE {
          ?s core:prevailsOver ?o .
          FILTER(STRSTARTS(STR(?s), "http://proethica.org/ontology/case/"))
          BIND(STRBEFORE(STR(?s), "#") AS ?case)
        }
    """,
    # Skip owl:NamedIndividual (every individual carries it; not informative).
    "case86_types": """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT ?ind ?cls WHERE {
          ?ind rdf:type ?cls .
          FILTER(STRSTARTS(STR(?ind), "http://proethica.org/ontology/case/86#"))
          FILTER(?cls != owl:NamedIndividual)
        }
    """,
}

# Frozen at the 2026-05-25 deployment that the camera-ready paper was verified
# against. If these change, either the paper needs a corresponding update or
# the corpus state has unexpectedly drifted.
_CORPUS_EXPECTED: Dict[str, int] = {
    "case_count": 119,
    "competesWith_count": 1872,
    "prevailsOver_count": 788,
    "defeasibleUnder_count": 2177,
    "cases_with_prevailsOver": 118,
}


def cmd_corpus(args: argparse.Namespace) -> int:
    exit_code = 0
    for name, q in _CORPUS_QUERIES.items():
        safe_print(f"== {name} ==")
        try:
            r = run(q, args.base_url)
        except Exception as e:
            safe_print(f"  ERROR: {e}")
            exit_code = 1
            continue
        if name == "case86_types":
            bindings = r.get("results", {}).get("bindings", [])
            safe_print(f"  {len(bindings)} type assertions in case 86 graph")
            for b in bindings:
                ind = shorten(b.get("ind", {}).get("value", "?"))
                cls = shorten(b.get("cls", {}).get("value", "?"))
                safe_print(f"    {ind:45s} a {cls}")
        else:
            v = _first_value(r)
            expected = _CORPUS_EXPECTED.get(name)
            mark = "OK" if expected is not None and str(v) == str(expected) else "DIFF"
            if mark == "DIFF":
                exit_code = 1
            safe_print(f"  live={v}   expected={expected}   [{mark}]")
    return exit_code


# ---------------------------------------------------------------------------
# Subcommand: case86
# Class names + defeasibility edges for the Figure 1 worked example.
# ---------------------------------------------------------------------------

_CASE86_QUERIES = {
    "CONFIDENTIALITY-class individuals in case 86": """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?ind ?cls WHERE {
          ?ind rdf:type ?cls .
          FILTER(STRSTARTS(STR(?ind), "http://proethica.org/ontology/case/86#"))
          FILTER(CONTAINS(LCASE(STR(?cls)), "confidential"))
        }
    """,
    "PUBLIC-WELFARE/SAFETY-class individuals in case 86": """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?ind ?cls WHERE {
          ?ind rdf:type ?cls .
          FILTER(STRSTARTS(STR(?ind), "http://proethica.org/ontology/case/86#"))
          FILTER(CONTAINS(LCASE(STR(?cls)), "publicwelfare")
              || CONTAINS(LCASE(STR(?cls)), "public_welfare")
              || CONTAINS(LCASE(STR(?cls)), "safety"))
        }
    """,
    # VALUES on ?p is much faster than a disjunctive FILTER -- the planner
    # iterates the property set and does focused lookups rather than enumerating
    # the whole graph and filtering. Without this the query 504s on prod.
    "DEFEASIBILITY EDGES with subject in case 86": """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT ?s ?p ?o WHERE {
          VALUES ?p { core:competesWith core:prevailsOver core:defeasibleUnder }
          ?s ?p ?o .
          FILTER(STRSTARTS(STR(?s), "http://proethica.org/ontology/case/86#"))
        }
    """,
}


def cmd_case86(args: argparse.Namespace) -> int:
    exit_code = 0
    for label, q in _CASE86_QUERIES.items():
        safe_print(f"== {label} ==")
        try:
            r = run(q, args.base_url)
        except Exception as e:
            safe_print(f"  ERROR: {e}")
            exit_code = 1
            continue
        bindings = r.get("results", {}).get("bindings", [])
        if not bindings:
            safe_print("  (none)")
            continue
        for b in bindings:
            if "cls" in b:
                safe_print(f"  {shorten(b['ind']['value']):55s} a {shorten(b['cls']['value'])}")
            else:
                s_ = shorten(b["s"]["value"])
                p_ = shorten(b["p"]["value"])
                o_ = shorten(b["o"]["value"])
                safe_print(f"  {s_:50s} {p_:18s} {o_}")
        safe_print("")
    return exit_code


# ---------------------------------------------------------------------------
# Subcommand: case86-obligations
# All Obligation-typed individuals in case 86 (using rdfs:subClassOf+
# core:Obligation, so any LLM-minted Obligation subclass matches).
# ---------------------------------------------------------------------------

_CASE86_OBLIGATIONS_Q = """
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX core: <http://proethica.org/ontology/core#>
    SELECT ?ind ?cls WHERE {
      ?ind rdf:type ?cls .
      ?cls rdfs:subClassOf+ core:Obligation .
      FILTER(STRSTARTS(STR(?ind), "http://proethica.org/ontology/case/86#"))
    }
    ORDER BY ?cls
"""


def cmd_case86_obligations(args: argparse.Namespace) -> int:
    safe_print("== Case 86: all Obligation-typed individuals ==")
    try:
        r = run(_CASE86_OBLIGATIONS_Q, args.base_url)
    except Exception as e:
        safe_print(f"  ERROR: {e}")
        return 1
    bindings = r.get("results", {}).get("bindings", [])
    if not bindings:
        safe_print("  (none found)")
        return 1
    for b in bindings:
        ind = shorten(b["ind"]["value"])
        cls = shorten(b["cls"]["value"])
        safe_print(f"  {ind:60s} a {cls}")
    safe_print("")
    safe_print(f"  Total: {len(bindings)}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: classes
# Existence check for specific class local-names. Defaults to the list the
# 2026-05-28 audit cared about; override with --names.
# ---------------------------------------------------------------------------

_DEFAULT_CLASSES_TO_CHECK: List[str] = [
    "ConfidentialityObligation",
    "ClientConfidentialityObligation",
    "PublicWelfareParamountObligation",
    "PublicWelfareParamount",
    "SafetyObligation",
    "UnpermittedWetlandFillViolationState",
]


def cmd_classes(args: argparse.Namespace) -> int:
    names = (
        [s.strip() for s in args.names.split(",") if s.strip()]
        if args.names else _DEFAULT_CLASSES_TO_CHECK
    )
    for cls in names:
        q = f"""
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT ?defining_iri (COUNT(?ind) AS ?nIndividuals) WHERE {{
              ?defining_iri a owl:Class .
              FILTER(STRENDS(STR(?defining_iri), "#{cls}"))
              OPTIONAL {{ ?ind a ?defining_iri . }}
            }} GROUP BY ?defining_iri
        """
        try:
            r = run(q, args.base_url)
            bindings = r.get("results", {}).get("bindings", [])
            if bindings:
                for b in bindings:
                    iri = b.get("defining_iri", {}).get("value", "?")
                    n = b.get("nIndividuals", {}).get("value", "?")
                    safe_print(f"  {cls:42s} EXISTS at {iri}  (individuals: {n})")
            else:
                safe_print(f"  {cls:42s} NOT FOUND")
        except Exception as e:
            safe_print(f"  {cls:42s} ERROR: {e}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: obligations
# Hierarchy + Public/Welfare/Safety class naming survey + PublicWelfareParamount
# parentage check (the 2026-05-28 audit found PWParamount is a Principle
# subclass, not an Obligation; don't use it as an Obligation type).
# ---------------------------------------------------------------------------

_Q_OBLIG_SUBCLASSES = """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX core: <http://proethica.org/ontology/core#>
    SELECT DISTINCT ?cls (COUNT(?ind) AS ?nInd) WHERE {
      ?cls rdfs:subClassOf+ core:Obligation .
      OPTIONAL { ?ind a ?cls . }
    }
    GROUP BY ?cls
    ORDER BY DESC(?nInd)
"""

_Q_PUBLIC_CLASSES = """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX core: <http://proethica.org/ontology/core#>
    SELECT DISTINCT ?cls ?parent (COUNT(?ind) AS ?nInd) WHERE {
      ?cls a owl:Class .
      FILTER(REGEX(STR(?cls), "(Public|Welfare|Safety)", "i"))
      OPTIONAL { ?cls rdfs:subClassOf ?parent . }
      OPTIONAL { ?ind a ?cls . }
    }
    GROUP BY ?cls ?parent
    ORDER BY DESC(?nInd)
"""

_Q_PWP_PARENT = """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?super WHERE {
      <http://proethica.org/ontology/intermediate#PublicWelfareParamount> rdfs:subClassOf ?super .
    }
"""


def cmd_obligations(args: argparse.Namespace) -> int:
    safe_print("== All subclasses of core:Obligation (direct + transitive) ==")
    try:
        r = run(_Q_OBLIG_SUBCLASSES, args.base_url)
        bindings = r.get("results", {}).get("bindings", [])
        if not bindings:
            safe_print("  (none returned)")
        for b in bindings[:30]:
            cls = shorten(b.get("cls", {}).get("value", "?"))
            n = b.get("nInd", {}).get("value", "?")
            safe_print(f"  {cls:55s} ({n} individuals)")
        if len(bindings) > 30:
            safe_print(f"  ... and {len(bindings) - 30} more")
    except Exception as e:
        safe_print(f"  ERROR: {e}")

    safe_print("")
    safe_print("== PublicWelfareParamount: what is it a subclass of? ==")
    try:
        r = run(_Q_PWP_PARENT, args.base_url)
        bindings = r.get("results", {}).get("bindings", [])
        if not bindings:
            safe_print("  (no parent found)")
        for b in bindings:
            safe_print(f"  parent: {shorten(b['super']['value'])}")
    except Exception as e:
        safe_print(f"  ERROR: {e}")

    safe_print("")
    safe_print("== Classes containing Public/Welfare/Safety (top 30 by usage) ==")
    try:
        r = run(_Q_PUBLIC_CLASSES, args.base_url)
        bindings = r.get("results", {}).get("bindings", [])
        if not bindings:
            safe_print("  (none returned)")
        for b in bindings[:30]:
            cls = shorten(b.get("cls", {}).get("value", "?"))
            parent = shorten(b.get("parent", {}).get("value", "?")) if b.get("parent") else "-"
            n = b.get("nInd", {}).get("value", "?")
            safe_print(f"  {cls:55s} sub: {parent:30s} ({n})")
        if len(bindings) > 30:
            safe_print(f"  ... and {len(bindings) - 30} more")
    except Exception as e:
        safe_print(f"  ERROR: {e}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: temporal
# Step-3 temporal-dynamics RDF: Action / Event individuals, Allen temporal
# relations (proeth:TemporalRelation + the OWL-Time interval predicate set),
# causal chains, per-case timelines. These come from the LangGraph pipeline at
# proethica/app/services/temporal_dynamics/ ; before the 2026-05-28 fix the
# commit serializer dropped them all into a bare label-only stub.
# ---------------------------------------------------------------------------

_TEMPORAL_QUERIES: Dict[str, str] = {
    "Action_typed": "PREFIX core: <http://proethica.org/ontology/core#> SELECT (COUNT(*) AS ?n) { ?s a core:Action }",
    "Event_typed":  "PREFIX core: <http://proethica.org/ontology/core#> SELECT (COUNT(*) AS ?n) { ?s a core:Event }",
    "Event_via_subClassOf_chain":
        "PREFIX core: <http://proethica.org/ontology/core#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
        "SELECT (COUNT(*) AS ?n) { ?s a ?t . ?t rdfs:subClassOf* core:Event }",
    "TemporalRelation": "PREFIX proeth: <http://proethica.org/ontology/intermediate#> SELECT (COUNT(*) AS ?n) { ?s a proeth:TemporalRelation }",
    "CausalChain":      "PREFIX proeth: <http://proethica.org/ontology/intermediate#> SELECT (COUNT(*) AS ?n) { ?s a proeth:CausalChain }",
    "TemporalEntity":   "PREFIX time: <http://www.w3.org/2006/time#> SELECT (COUNT(*) AS ?n) { ?s a time:TemporalEntity }",
    "time_predicates_any":
        "PREFIX time: <http://www.w3.org/2006/time#> SELECT (COUNT(*) AS ?n) "
        "{ ?s ?p ?o FILTER(STRSTARTS(STR(?p), 'http://www.w3.org/2006/time#')) }",
    "time_intervalBefore": "PREFIX time: <http://www.w3.org/2006/time#> SELECT (COUNT(*) AS ?n) { ?s time:intervalBefore ?o }",
    "proeth_hasAgent":         'PREFIX proeth: <http://proethica.org/ontology/intermediate#> SELECT (COUNT(*) AS ?n) { ?s proeth:hasAgent ?o }',
    "proeth_temporalSequence": 'PREFIX proeth: <http://proethica.org/ontology/intermediate#> SELECT (COUNT(*) AS ?n) { ?s proeth:temporalSequence ?o }',
    "proeth_causalLanguage":   'PREFIX proeth: <http://proethica.org/ontology/intermediate#> SELECT (COUNT(*) AS ?n) { ?s proeth:causalLanguage ?o }',
    "conceptCategory_Action_literal": 'PREFIX proeth: <http://proethica.org/ontology/intermediate#> SELECT (COUNT(*) AS ?n) { ?s proeth:conceptCategory "Action" }',
    "conceptCategory_Event_literal":  'PREFIX proeth: <http://proethica.org/ontology/intermediate#> SELECT (COUNT(*) AS ?n) { ?s proeth:conceptCategory "Event" }',
    "prov_Activity":  "PREFIX prov: <http://www.w3.org/ns/prov#> SELECT (COUNT(*) AS ?n) { ?s a prov:Activity }",
}

# Expected after the temporal data push lands on the live deployment. Measured
# on dev 2026-05-28 post-augmentation. Until the data push completes (gated on
# `project_pellet-corpus-drift`), prod will return 0/preserved values where dev
# returns the augmented counts, so DIFF is the expected interim signal.
_TEMPORAL_EXPECTED: Dict[str, int] = {
    "Action_typed":               668,
    "Event_typed":                691,
    "TemporalRelation":          1263,
    "CausalChain":                605,
    "TemporalEntity":             119,
    "time_predicates_any":       1263,
    "time_intervalBefore":        998,
    "proeth_hasAgent":            668,
    "proeth_temporalSequence":   1359,
    "proeth_causalLanguage":      605,
    "conceptCategory_Action_literal": 688,  # preservation: must not lose stubs
    "conceptCategory_Event_literal":  714,
    # prov_Activity and Event_via_subClassOf_chain intentionally have no expected
    # (PROV-O sync is a separate item; the subclass chain count varies with
    # how many Event subclasses the corpus has defined).
}


def cmd_temporal(args: argparse.Namespace) -> int:
    exit_code = 0
    for name, q_text in _TEMPORAL_QUERIES.items():
        try:
            r = run(q_text, args.base_url)
            v = _first_value(r)
        except Exception as e:
            safe_print(f"== {name} ==\n  ERROR: {e}")
            exit_code = 1
            continue
        expected = _TEMPORAL_EXPECTED.get(name)
        if expected is None:
            safe_print(f"== {name} ==\n  live={v}   (no fixed expected)")
        else:
            mark = "OK" if str(v) == str(expected) else "DIFF"
            if mark == "DIFF":
                exit_code = 1
            safe_print(f"== {name} ==\n  live={v}   expected={expected}   [{mark}]")
    return exit_code


# ---------------------------------------------------------------------------
# Subcommand: all
# ---------------------------------------------------------------------------

def cmd_all(args: argparse.Namespace) -> int:
    rc = 0
    for label, fn in [
        ("CORPUS", cmd_corpus),
        ("CASE 86", cmd_case86),
        ("CASE 86 OBLIGATIONS", cmd_case86_obligations),
        ("CLASSES", cmd_classes),
        ("OBLIGATIONS", cmd_obligations),
        ("TEMPORAL", cmd_temporal),
    ]:
        safe_print(f"\n###################  {label}  ###################")
        rc = fn(args) or rc
    return rc


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="Verify KI2026 paper SPARQL-content claims against the live OntServe deployment.",
    )
    p.add_argument("--base-url", default=DEFAULT_BASE,
                   help=f"OntServe base URL (default: {DEFAULT_BASE})")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("corpus", help="Numeric claims: case count + edge counts + case-86 types.")
    sub.add_parser("case86", help="Case 86 class names + defeasibility edges (Figure 1).")
    sub.add_parser("case86-obligations",
                   help="All Obligation-typed individuals in case 86.")
    c = sub.add_parser("classes", help="Check existence of specific class local-names.")
    c.add_argument("--names",
                   help="Comma-separated class local-names (default: 2026-05-28 audit set).")
    sub.add_parser("obligations",
                   help="Obligation subclass hierarchy + PublicWelfareParamount parentage.")
    sub.add_parser("temporal",
                   help="Step-3 temporal RDF: Action/Event/TemporalRelation/CausalChain/Timeline + time:* + PROV-O counts.")
    sub.add_parser("all", help="Run every subcommand in sequence.")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return 2

    if not getattr(args, "names", None):
        args.names = None  # cmd_classes expects the attribute to exist

    dispatch = {
        "corpus": cmd_corpus,
        "case86": cmd_case86,
        "case86-obligations": cmd_case86_obligations,
        "classes": cmd_classes,
        "obligations": cmd_obligations,
        "temporal": cmd_temporal,
        "all": cmd_all,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
