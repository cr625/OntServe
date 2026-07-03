-- Repair ontology_type / source_system values that were inherited from column
-- defaults by ontology_sync_service auto-creation, plus taxonomy corrections
-- verified in the 2026-07-02 interface review. Idempotent; safe on local and
-- production (the sync service never rewrites these two columns on re-sync).

BEGIN;

-- Per-case extraction ontologies produced by the ProEthica pipeline
UPDATE ontologies SET ontology_type = 'case', source_system = 'proethica'
WHERE name ~ '^proethica-case-[0-9]+$'
  AND (ontology_type <> 'case' OR source_system <> 'proethica');

-- Foundation-tier external vocabularies (same tier as bfo/w3c-prov-o)
UPDATE ontologies SET ontology_type = 'upper', source_system = 'external'
WHERE name IN ('iao', 'Relations Ontology 2015', 'Information Artifact Ontology 2020')
  AND (ontology_type <> 'upper' OR source_system <> 'external');

-- The ProEthica domain layer (PROETHICA_ONTSERVE_INTEGRATION.md maps 'domain'
-- to engineering-ethics; it is ProEthica-generated, not external)
UPDATE ontologies SET ontology_type = 'domain', source_system = 'proethica'
WHERE name = 'engineering-ethics'
  AND (ontology_type <> 'domain' OR source_system <> 'proethica');

-- ISO 16739-1 / buildingSMART IfcRoleEnum crosswalk: external vocabulary
UPDATE ontologies SET source_system = 'external'
WHERE name = 'ifc-roles' AND source_system <> 'external';

-- Curated BFO/IAO/RO upper-term stub built by proethica tooling
UPDATE ontologies SET ontology_type = 'upper', source_system = 'proethica'
WHERE name = 'proethica-foundation'
  AND (ontology_type <> 'upper' OR source_system <> 'proethica');

-- Domain-independent CBR schema: framework/base layer, not the domain layer
UPDATE ontologies SET ontology_type = 'base'
WHERE name = 'proethica-cases' AND ontology_type <> 'base';

COMMIT;
