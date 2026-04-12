#!/usr/bin/env python3
"""
Pellet mutation test: deliberately mistype a State individual as an Action.

The paper's worked example (§4) claims: "A State misclassified as an Action
would place a specifically dependent continuant under BFO:process, violating
the continuant/occurrent boundary and producing an inconsistency that the
reasoner detects."

This script verifies that claim by:
  1. Loading case 72 (consistent baseline).
  2. Adding rdf:type proeth-core:Action to a State individual — keeping
     its existing CompetingDutiesState type so it is simultaneously a
     subclass of both State and Action.
  3. Running Pellet on the merged graph (core + intermediate + mutated case).
  4. Expecting OwlReadyInconsistentOntologyError from the AllDisjointClasses
     axiom covering {State, Action, ...}.
"""
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ONTSERVE_ROOT = SCRIPT_DIR.parent
WEB_DIR = ONTSERVE_ROOT / "web"
sys.path.insert(0, str(ONTSERVE_ROOT))
sys.path.insert(0, str(WEB_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

import rdflib
from rdflib import URIRef, RDF

from pellet_validate import _fetch_case_content_from_db, validate_case_from_content

CORE_ACTION = URIRef("http://proethica.org/ontology/core#Action")
# The competing-duties state individual (URI has em dash)
TARGET_IND = URIRef(
    "http://proethica.org/ontology/case/72#"
    "Doe_Competing_Duties_\u2014_Faithful_Agent_vs._Public_Safety_Paramount"
)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("=== Pellet mutation test: State->Action mistyping ===\n")

    # 1. Baseline (no mutation)
    print("[1/2] Baseline: validating unmodified case 72...")
    clean_content = _fetch_case_content_from_db("proethica-case-72")
    baseline = validate_case_from_content("proethica-case-72", clean_content)
    print(f"  consistent: {baseline.consistent}")
    print(f"  runtime:    {baseline.runtime_seconds:.2f}s")
    print(f"  inferred:   {baseline.inferred_type_assertions} type + "
          f"{baseline.inferred_subclass_assertions} subclass assertions\n")

    # 2. Mutation: add rdf:type Action to a State individual
    print("[2/2] Mutation: adding rdf:type proeth-core:Action to")
    print(f"  <...#Doe_Competing_Duties_(CompetingDutiesState)>")
    g = rdflib.Graph()
    g.parse(data=clean_content, format="turtle")

    # Verify the individual exists and currently has a State-subclass type
    types_before = list(g.objects(TARGET_IND, RDF.type))
    print(f"  types before mutation: {[str(t).split('#')[-1] for t in types_before]}")
    assert types_before, f"Target individual {TARGET_IND} not found"

    # Add the contradictory type (keep existing types so disjointness fires)
    g.add((TARGET_IND, RDF.type, CORE_ACTION))
    types_after = list(g.objects(TARGET_IND, RDF.type))
    print(f"  types after mutation:  {[str(t).split('#')[-1] for t in types_after]}\n")

    mutated_content = g.serialize(format="turtle")
    mutated = validate_case_from_content("proethica-case-72-MUTATED", mutated_content)

    print(f"  consistent: {mutated.consistent}")
    print(f"  error:      {mutated.error}")
    print(f"  runtime:    {mutated.runtime_seconds:.2f}s")

    if mutated.error_explanation:
        print(f"  explanation: {mutated.error_explanation[:500]}")

    # 3. Summary
    print("\n=== Summary ===")
    if baseline.consistent and not mutated.consistent:
        print("PASS: Pellet correctly detects the State/Action disjointness "
              "violation introduced by the mutation.")
    elif baseline.consistent and mutated.consistent:
        print("FAIL: Pellet did NOT catch the mutation. "
              f"Disjointness violations found: {mutated.disjointness_violations}")
    else:
        print("UNEXPECTED: baseline was already inconsistent.")

    report = {
        "test": "State->Action mutation on case 72",
        "baseline": asdict(baseline),
        "mutated": asdict(mutated),
        "verdict": "PASS" if (baseline.consistent and not mutated.consistent) else "FAIL",
    }
    report_path = ONTSERVE_ROOT / "docs-internal" / "KI2026" / "pellet_mutation_evidence.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
