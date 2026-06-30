# Foundation rebuild (durable)

Durable, regenerable home for the `proethica-foundation` reasoning-module rebuild.
Implements Phase 2 of `OntServe/.claude/plans/foundation-mireot-rebuild.md`. The
prior build ran in a job temp dir and was lost; everything needed to reproduce the
candidate now lives here and is committed.

## Contents

| File | Role |
|------|------|
| `build_foundation.py` | Regenerates the candidate by bounded MIREOT from upstream. |
| `sources/{bfo,iao,ro}.owl` | Pinned upstream releases (see `SOURCES.md`). |
| `SOURCES.md` | Upstream versionIRIs, URLs, SHA-256. |
| `proethica-foundation.candidate.ttl` | The regenerated module (build output). |

## Regenerate

```bash
cd OntServe && source venv-ontserve/bin/activate
python tools/foundation_rebuild/build_foundation.py
```

The script prints a build report: footprint parity vs the live foundation, the
extracted disjointness pairs, and a definition diff. Same inputs produce byte-
identical output (no nondeterminism).

## What the candidate is

A tool-extracted replacement for the hand-curated `ontologies/proethica-foundation.ttl`:
the 15 BFO/IAO classes and 5 RO object properties that `proethica-core` and
`proethica-intermediate` reference, declared locally with verbatim upstream labels
and definitions, plus the BFO disjointness axioms whose signature is in scope.

Method: per-source bounded MIREOT (seed terms + their named ancestor chain) plus
programmatic verbatim backfill of labels, definitions, and disjointness. Pure STAR
was rejected in Phase 2 because it over-pulled RO's cross-ontology biomedical web.

## Validation status (regenerated 2026-06-30)

- **Footprint parity**: derived set == live foundation (15 classes + 5 properties).
- **Logical-axiom diff vs the live foundation**: `rdf:type`, `rdfs:subClassOf`,
  and `owl:inverseOf` identical; the only disjointness difference is the added
  `disposition` `owl:disjointWith` `role` pair (BFO-asserted, redundant with core's
  nine-component disjointness). Reasoning-equivalent by construction.
- **Pellet (owlready2)**: local cases 7, 103, 121 are consistent under both the
  live foundation and the candidate, no flip. The full 119-corpus lives in
  production/deposit, not locally; it must pass for the same structural reason.
- **Definitions**: 15/20 identical to the curated file; the 5 differences are the
  candidate being strictly more verbatim (a straightened apostrophe; dropped
  editorial trailing periods; the current RO `has role` text including "for its
  existence"; the appended "Inverse of participates in." sentence removed).

## Phase 5 (still pending, parked by user)

Swapping the candidate into the live foundation is Phase 5 and is intentionally not
done here. To execute it: archive `ontologies/proethica-foundation.ttl`, copy the
candidate over it, run `python tools/sync_ontology_to_db.py proethica-foundation
--force`, re-run the definition audit, and commit. Rollback baseline is git commit
`fd46c9c`. Dev-only; production is untouched until a separate sync.
