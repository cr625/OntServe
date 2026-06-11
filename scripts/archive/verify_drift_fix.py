#!/usr/bin/env python3
"""
Adversarial verification of the Phase 1.7 ProfessionalCompetence fix.

For each of the 18 cases, computes the EXACT triple-set delta between the
pre-fix backup (/tmp/drift_fix_backups/<name>_pre.ttl) and the post-fix
on-disk TTL. Asserts the change is EXACTLY:
  removed: {ProfessionalCompetence subClassOf Principle}
           + {<pc-ind> conceptCategory "Principle"} (1 per PC individual)
  added:   {<pc-ind> conceptCategory "Capability"}  (same count)
and NOTHING ELSE. Also confirms structure-preservation: the count of
augmentation / claimed-structure predicates is identical pre vs post
(time:* intervals, TemporalRelation, CausalChain, temporalSequence,
defeasibility competesWith/prevailsOver/defeasibleUnder, R->P->O
hasObligation/adheresToPrinciple/derivedFromPrinciple, citesProvision).

A fix that reached consistency by stripping any of these would FAIL here.
"""
import sys
from pathlib import Path
from collections import Counter

from rdflib import Graph, RDF, RDFS, URIRef, Literal

CORE = "http://proethica.org/ontology/core#"
INT = "http://proethica.org/ontology/intermediate#"
PC = URIRef(INT + "ProfessionalCompetence")
PRIN = URIRef(CORE + "Principle")
CC = URIRef(INT + "conceptCategory")

CASES = [7, 9, 12, 16, 58, 59, 85, 109, 112, 120, 131, 139, 142, 146, 147, 150, 161, 162]
ONTOLOGIES = Path(__file__).resolve().parent.parent / "ontologies"
BACKUP = Path("/tmp/drift_fix_backups")

STRUCTURE_SUBSTR = [
    "time#", "TemporalRelation", "CausalChain", "temporalSequence",
    "competesWith", "prevailsOver", "defeasibleUnder",
    "hasObligation", "adheresToPrinciple", "derivedFromPrinciple",
    "citesProvision",
]


def structure_counts(g: Graph) -> Counter:
    c = Counter()
    for s, p, o in g:
        ps = str(p)
        for key in STRUCTURE_SUBSTR:
            if key in ps:
                c[key] += 1
    return c


def main():
    failures = []
    print(f"{'case':>5} {'delta-':>7} {'delta+':>7} {'struct':>7} {'verdict':>8}")
    for c in CASES:
        name = f"proethica-case-{c}"
        pre_p = BACKUP / f"{name}_pre.ttl"
        post_p = ONTOLOGIES / f"{name}.ttl"
        if not pre_p.exists() or not post_p.exists():
            print(f"{c:>5}  MISSING backup or disk file")
            failures.append((c, "missing-file"))
            continue
        pre = Graph(); pre.parse(str(pre_p), format="turtle")
        post = Graph(); post.parse(str(post_p), format="turtle")
        pre_set = set(pre); post_set = set(post)
        removed = pre_set - post_set
        added = post_set - pre_set

        # Expected removed: 1 subClassOf-Principle + N cc="Principle" on PC inds
        pc_inds = set(pre.subjects(RDF.type, PC))
        exp_removed = {(PC, RDFS.subClassOf, PRIN)}
        for ind in pc_inds:
            exp_removed.add((ind, CC, Literal("Principle")))
        exp_added = set()
        for ind in pc_inds:
            exp_added.add((ind, CC, Literal("Capability")))

        delta_clean = (removed == exp_removed) and (added == exp_added)

        # Structure preservation: counts identical pre vs post
        pre_struct = structure_counts(pre)
        post_struct = structure_counts(post)
        struct_ok = pre_struct == post_struct

        verdict = "PASS" if (delta_clean and struct_ok) else "FAIL"
        if verdict == "FAIL":
            failures.append((c, {
                "unexpected_removed": [str(t) for t in (removed - exp_removed)][:5],
                "unexpected_added": [str(t) for t in (added - exp_added)][:5],
                "missing_removed": [str(t) for t in (exp_removed - removed)][:5],
                "struct_pre": dict(pre_struct),
                "struct_post": dict(post_struct),
            }))
        print(f"{c:>5} {len(removed):>7} {len(added):>7} {'eq' if struct_ok else 'DIFF':>7} {verdict:>8}")

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for c, detail in failures:
            print(f"  case {c}: {detail}")
        sys.exit(1)
    else:
        print("ALL 18 PASS: each case changed EXACTLY the bad triple + cc reconcile, "
              "and every augmentation/edge predicate count is preserved.")


if __name__ == "__main__":
    main()
