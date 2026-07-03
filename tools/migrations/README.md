# Deploy migrations: 2026-07-02 ontology metadata arc

Ordered, idempotent data migrations that accompany the ontology-metadata and
external-ontology cleanup. Run once per environment AFTER the code deploy. The
full runbook (prod ssh commands, preconditions, verification) is in the session
deploy addendum and onto memory `project_ontology-metadata-repair`.

The `.sql` files run against the `ontserve` database; the `.py` files need the
OntServe venv: `cd <ontserve-root> && venv/bin/python tools/migrations/<script>`.

## Run order

1. `repair_ontology_metadata.sql` -- `ontology_type`/`source_system` fixes for rows
   that inherited the `base`/`manual` column defaults (case ontologies, iao,
   ifc-roles, proethica-foundation) plus taxonomy corrections
   (engineering-ethics to domain/proethica, RO/IAO/RO2015 to upper, etc.).

2. `repair_external_ontology_metadata.sql` -- `base_uri` column fixes
   (ASCE/ASME/IEEE, ifc-roles) and `metadata.stub=true` on the curated-subset
   ontologies (iao, proethica-foundation, the RO row).

3. `rebuild_relations_subset.py` -- rebuilds the "Relations Ontology 2015" row as
   an honest five-property RO subset and de-collides its `obo/ro.owl` IRI.

4. `clean_provo_residue.py` -- repoints the w3c-prov-o PROV-O-inverses header off
   the `file://` ingestion leak and re-extracts under the fixed classifier.

## Not scripted here

Retiring the duplicate IAO row ("Information Artifact Ontology 2020") is a manual
`DELETE ... WHERE name=... AND base_uri=...` -- deleted by name+base_uri, never by
row id, because serial ids differ between environments. See the deploy addendum for
the exact statements and the `verify_paper_claims.py` / `README.md` repoint that
must land in the same change.

All four scripts are idempotent (hash/no-op guards), so re-running is safe.
