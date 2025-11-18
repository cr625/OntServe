-- Migration: Add Source Text Support for ProEthica Integration
-- Date: 2025-11-17
-- Purpose: Enhance ontology_entities and concept_triples for source text provenance
--
-- Changes:
-- 1. Add source_reference column to ontology_entities for definitional sources
-- 2. Add helper views for querying entities with source text
-- 3. Insert PROV-O namespace configuration
-- 4. Add indexes for performance

-- ===== STEP 1: Enhance ontology_entities for definitional sources =====

-- Add source_reference column for classes (definitional citations)
ALTER TABLE ontology_entities
ADD COLUMN IF NOT EXISTS source_reference TEXT;

COMMENT ON COLUMN ontology_entities.source_reference IS
'Definitional source reference for classes (e.g., "NSPE Code Section I.1"). Use for general concept definitions, not case-specific snippets.';

-- Add index for querying by source
CREATE INDEX IF NOT EXISTS idx_ontology_entities_source
ON ontology_entities(source_reference)
WHERE source_reference IS NOT NULL;

-- ===== STEP 2: Add helper views for source text queries =====

-- View: All entities with source text (both classes and individuals)
CREATE OR REPLACE VIEW entities_with_source_text AS
SELECT
    'class' as entity_storage_type,
    oe.id,
    oe.uri,
    oe.label,
    oe.entity_type,
    oe.source_reference as source_text,
    'definitional' as source_text_type,
    oe.created_at,
    o.name as ontology_name
FROM ontology_entities oe
JOIN ontologies o ON oe.ontology_id = o.id
WHERE oe.source_reference IS NOT NULL

UNION ALL

SELECT
    'individual' as entity_storage_type,
    c.id,
    c.uri,
    c.label,
    c.primary_type as entity_type,
    cm.source_text,
    'case_specific' as source_text_type,
    cm.extraction_timestamp as created_at,
    d.name as ontology_name
FROM concepts c
JOIN candidate_metadata cm ON c.id = cm.concept_id
JOIN domains d ON c.domain_id = d.id
WHERE cm.source_text IS NOT NULL;

COMMENT ON VIEW entities_with_source_text IS
'Unified view of all entities (classes and individuals) with source text provenance';

-- View: Source text statistics by domain
CREATE OR REPLACE VIEW source_text_statistics AS
SELECT
    d.name as domain_name,
    d.display_name,
    COUNT(DISTINCT c.id) as entities_with_source_text,
    COUNT(DISTINCT c.primary_type) as unique_types,
    AVG(LENGTH(cm.source_text)) as avg_source_text_length,
    MIN(cm.extraction_timestamp) as earliest_extraction,
    MAX(cm.extraction_timestamp) as latest_extraction
FROM domains d
LEFT JOIN concepts c ON d.id = c.domain_id
LEFT JOIN candidate_metadata cm ON c.id = cm.concept_id
WHERE cm.source_text IS NOT NULL
GROUP BY d.id, d.name, d.display_name
ORDER BY entities_with_source_text DESC;

COMMENT ON VIEW source_text_statistics IS
'Statistics on source text coverage by professional domain';

-- ===== STEP 3: Add PROV-O namespace configuration =====

-- Insert PROV-O namespace if not exists
INSERT INTO system_config (key, value, description)
VALUES (
    'prov_ontology_namespace',
    '"http://www.w3.org/ns/prov#"',
    'W3C PROV-O namespace for provenance tracking'
)
ON CONFLICT (key) DO NOTHING;

-- Insert ProEthica provenance namespace
INSERT INTO system_config (key, value, description)
VALUES (
    'proethica_provenance_namespace',
    '"http://proethica.org/ontology/provenance/"',
    'ProEthica custom provenance namespace for source text annotations'
)
ON CONFLICT (key) DO NOTHING;

-- Insert common PROV-O predicates for reference
INSERT INTO system_config (key, value, description)
VALUES (
    'prov_predicates',
    '{
        "wasDerivedFrom": "http://www.w3.org/ns/prov#wasDerivedFrom",
        "wasQuotedFrom": "http://www.w3.org/ns/prov#wasQuotedFrom",
        "wasGeneratedBy": "http://www.w3.org/ns/prov#wasGeneratedBy",
        "generatedAtTime": "http://www.w3.org/ns/prov#generatedAtTime",
        "wasAttributedTo": "http://www.w3.org/ns/prov#wasAttributedTo",
        "hadPrimarySource": "http://www.w3.org/ns/prov#hadPrimarySource",
        "value": "http://www.w3.org/ns/prov#value"
    }',
    'Common PROV-O predicates for provenance tracking'
)
ON CONFLICT (key) DO NOTHING;

-- Insert ProEthica custom annotation properties
INSERT INTO system_config (key, value, description)
VALUES (
    'proethica_annotation_properties',
    '{
        "sourceText": "http://proethica.org/ontology/provenance/sourceText",
        "extractedFrom": "http://proethica.org/ontology/provenance/extractedFrom",
        "extractionConfidence": "http://proethica.org/ontology/provenance/extractionConfidence"
    }',
    'ProEthica custom annotation properties for source text provenance'
)
ON CONFLICT (key) DO NOTHING;

-- ===== STEP 4: Add indexes for RDF triple queries =====

-- Index for finding sourceText triples
CREATE INDEX IF NOT EXISTS idx_triples_source_text
ON concept_triples(subject)
WHERE predicate = 'http://proethica.org/ontology/provenance/sourceText';

-- Index for finding PROV-O derivation triples
CREATE INDEX IF NOT EXISTS idx_triples_prov_derived
ON concept_triples(subject)
WHERE predicate = 'http://www.w3.org/ns/prov#wasDerivedFrom';

-- Index for finding PROV-O temporal triples
CREATE INDEX IF NOT EXISTS idx_triples_prov_time
ON concept_triples(subject)
WHERE predicate = 'http://www.w3.org/ns/prov#generatedAtTime';

-- ===== STEP 5: Create helper functions =====

-- Function to get entity source text (class or individual)
CREATE OR REPLACE FUNCTION get_entity_source_text(entity_uri TEXT)
RETURNS TABLE (
    source_text TEXT,
    source_type VARCHAR(20),
    extraction_timestamp TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    -- Try to find in ontology_entities (classes)
    RETURN QUERY
    SELECT
        oe.source_reference as source_text,
        'definitional'::VARCHAR(20) as source_type,
        oe.created_at as extraction_timestamp
    FROM ontology_entities oe
    WHERE oe.uri = entity_uri AND oe.source_reference IS NOT NULL
    LIMIT 1;

    -- If not found, try concepts (individuals)
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT
            cm.source_text,
            'case_specific'::VARCHAR(20) as source_type,
            cm.extraction_timestamp
        FROM concepts c
        JOIN candidate_metadata cm ON c.id = cm.concept_id
        WHERE c.uri = entity_uri AND cm.source_text IS NOT NULL
        LIMIT 1;
    END IF;

    RETURN;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_entity_source_text(TEXT) IS
'Get source text for an entity by URI, checking both classes and individuals';

-- ===== STEP 6: Data validation queries (for testing) =====

-- Query to verify migration completed successfully
DO $$
BEGIN
    RAISE NOTICE 'Migration 001 completed successfully';
    RAISE NOTICE 'Tables updated: ontology_entities';
    RAISE NOTICE 'Views created: entities_with_source_text, source_text_statistics';
    RAISE NOTICE 'Functions created: get_entity_source_text';
    RAISE NOTICE 'Indexes created: 4 new indexes for source text and PROV-O queries';
END $$;

-- Sample queries to test the migration:
--
-- 1. Check for entities with source text:
--    SELECT * FROM entities_with_source_text LIMIT 10;
--
-- 2. Get source text statistics:
--    SELECT * FROM source_text_statistics;
--
-- 3. Get source text for a specific entity:
--    SELECT * FROM get_entity_source_text('http://proethica.org/ontology/intermediate/Engineer');
--
-- 4. Find all sourceText triples:
--    SELECT subject, object_literal
--    FROM concept_triples
--    WHERE predicate = 'http://proethica.org/ontology/provenance/sourceText';
