# Canonical Reference Sheet (ProEthica extraction controlled vocabulary)

Status: DRAFT / provisional (2026-06-24), pending the Phase 2 calibration loop. Built during the
Stage-C canonicalization to stop the extractor minting compound classes that bake case-specific
context/state into class identity. Design + decisions: `proethica/.claude/plans/canonicalization-design.md`;
reusable method: `proethica/.claude/plans/canonicalization-methodology.md`.

## Files

- `<component>.yaml` (roles, principle, obligation, state, resource, capability, constraint): per-component
  curation. Each has `canonical` entries (`iri` / `label` / `definition` / `alt_labels`), `do_not_mint`
  decompose recipes, and `curate` open notes. `alt_labels` are synonym labels that MAP to the canonical
  entry (the deterministic alias tier).
- `action.yaml`, `event.yaml`: Actions/Events have no accumulator classes (they are per-case individuals),
  so these carry `canonical_types` (reusable Action/Event types) + an `iri_rule` for shortening the
  narrative-laden temporal-individual IRIs.
- `manifest.yaml`: the CROSS-COMPONENT authority. Links one concept's genuine facets across components and
  records which shadows are folded.

## Loader contract (IMPORTANT -- the manifest wins)

The effective canonical set is NOT just each file's `canonical` list. A consumer (prompt injection,
matcher alias tier, judge) MUST compute:

    effective_canonical(component) =
        component.canonical
        MINUS every label in manifest.constraint_fold        (folded into an Obligation)
        MINUS every manifest.concepts[].drop_shadows entry    (a restatement shadow)

and treat each folded/dropped label as an ALIAS that REDIRECTS to its `into:` / `fold_into:` target
(so a new mint of that label reuses the target rather than minting). The component files are not
physically pruned; the manifest is the single reconciliation authority. This keeps per-component
curation and cross-component linking in one place each.

Example: `constraint.yaml` lists 42 `canonical`, but `manifest.constraint_fold` folds 23 into their
Obligations, so the effective canonical Constraint set is ~19. Total effective canonical across all
components is ~162 (down from the 429-class accumulator).

## The three uses

1. INPUT to extraction: inject `effective_canonical` (label + definition + alt_labels + do_not_mint
   guidance) into the per-component extractor prompt, replacing the raw dump of the extended accumulator.
2. Matcher alias tier: a deterministic `{normalized alt_label/folded label -> canonical iri}` map, applied
   before the fuzzy embedding tier (decision 3: alias tier only, keep exact-only fallback).
3. Judge: `compare_extraction.py judge` scores each new case's classes as reused / should-decompose /
   over-compound / genuinely-new against this sheet.

## Locked policies (see manifest `policy:` + the design doc DECISIONS LOCKED)

State attaches via `core#affects` (State->Agent), no core change; a State is created only when it does
normative work; reuse is alias-tier-only; idioms kept canonical; facet-retention keeps linked genuine
facets and folds restatement shadows (Constraint = hard-limit-only; competition via prevailsOver edges).
