# Archived One-Off Scripts

Executed historical repair and backfill scripts, retained for reference. Each script ran to completion and its effect is persisted in the database and deployed; none is part of any current operational procedure. Content also recoverable from git history.

| Script | Purpose | Executed | Record |
|--------|---------|----------|--------|
| `fix_professional_competence_drift.py` | Phase 1.7 repair of the ProfessionalCompetence `subClassOf` drift across case ontologies | 2026-05-28 (dev), deployed to production 2026-05-29 | Commit `4fd20de`; ROADMAP Phase 1.7 record |
| `verify_drift_fix.py` | Companion verification for the drift repair | 2026-05-28 | Commit `4fd20de` |
| `backfill_r1_self_contained.py` | R1 self-contained TTL backfill (subClassOf-core emission via `established`) across the 9 priority-case baselines | 2026-06-04 | OntServe commit `9803fe7` / ProEthica `c6541fcd` context |
| `backfill_case_display_names.py` | One-time `display_name` backfill from `ai_ethical_dm.documents.title` (119/119 dev and production) | 2026-05-27/28, prod deploy `006e801` | Superseded by the durable `dcterms:title` commit path (ProEthica emits at commit; `ontology_sync_service.py` reads into `display_name` on create) |

Note on imports: `fix_professional_competence_drift.py` imported `diagnose_drift` from its former `validation/` location; if ever re-run from this directory, add `validation/` to `sys.path` or run it from the repository root with the old path restored. `validation/diagnose_drift.py` itself remains live (planned Section-C pre-commit inconsistency localizer).

Distinct from the live tooling that stays in place: `validation/{conformance,conformance_loop,pellet_validate,pellet_corpus_check,pellet_mutation_test,llm_repair,export_corpus_deposit,orphan_audit,normalize_case_ttl,diagnose_drift,anchor_orphan_classes}.py` and `tools/{refresh_entity_extraction,sync_ontology_to_db,verify_paper_claims,verify_paper_sparql_claims,build_nspe_ontology,populate_entity_embeddings}.py` (see `proethica/.claude/plans/code-review-cleanup-2026-06.md` for the verification record).
