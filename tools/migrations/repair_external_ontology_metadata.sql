-- External-ontology metadata repairs from the 2026-07-02 validity review.
-- Idempotent. Companion to rebuild_relations_subset.py (which rebuilds the RO
-- row's CONTENT and sets its base_uri + stub flag in one transaction).

BEGIN;

-- 1. base_uri columns that disagree with the actual content/entity namespaces.
--    The mismatched value breaks base_uri + fragment URI construction
--    (web/ontology_routes/helpers.py). Values confirmed from ontology_entities.
UPDATE ontologies SET base_uri = 'http://proethica.org/ontology/asce#'
WHERE name = 'ASCE Code of Ethics' AND base_uri <> 'http://proethica.org/ontology/asce#';

UPDATE ontologies SET base_uri = 'http://proethica.org/ontology/asme#'
WHERE name = 'ASME Code of Ethics' AND base_uri <> 'http://proethica.org/ontology/asme#';

UPDATE ontologies SET base_uri = 'http://proethica.org/ontology/ieee#'
WHERE name = 'IEEE Code of Ethics' AND base_uri <> 'http://proethica.org/ontology/ieee#';

UPDATE ontologies SET base_uri = 'http://proethica.org/vocab/ifc-roles#'
WHERE name = 'ifc-roles' AND base_uri <> 'http://proethica.org/vocab/ifc-roles#';

-- 2. Mark the curated-subset / fragment ontologies as stubs (metadata.stub=true)
--    so the UI can distinguish a hosted subset from a full upstream artifact.
--    Orthogonal to ontology_type (a stub can be any layer), so it lives in the
--    metadata JSONB rather than overloading the type. The re-sync path preserves
--    unknown metadata keys, so this survives normal reloads.
--      iao                                -- curated 4-class IAO subset
--      proethica-foundation               -- curated BFO/IAO/RO subset for the reasoner
--      Information Artifact Ontology 2020  -- stale 12-term IAO fragment (superseded by iao)
--    ('Relations Ontology 2015' is handled by rebuild_relations_subset.py.)
UPDATE ontologies
SET metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{stub}', 'true'::jsonb)
WHERE name IN ('iao', 'proethica-foundation', 'Information Artifact Ontology 2020')
  AND COALESCE(metadata->>'stub', 'false') <> 'true';

COMMIT;
