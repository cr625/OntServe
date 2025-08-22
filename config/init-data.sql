-- OntServe Initial Data
-- Basic configuration and sample data for development and testing
--
-- This file is automatically run after schema.sql during Docker initialization

-- Insert additional system configuration
INSERT INTO system_config (key, value, description) VALUES
('extraction_confidence_threshold', '0.6', 'Minimum confidence score for auto-approval of extracted concepts'),
('max_concepts_per_extraction', '100', 'Maximum number of concepts that can be extracted in a single session'),
('enable_audit_logging', 'true', 'Enable comprehensive audit logging for all changes'),
('concept_approval_timeout_hours', '168', 'Hours after which unreviewed concepts are flagged for attention')
ON CONFLICT (key) DO NOTHING;

-- Create sample professional domains for testing (if they don't exist)
INSERT INTO domains (name, display_name, namespace_uri, description, metadata) VALUES
('medical-ethics', 'Medical Ethics', 'http://proethica.org/ontology/medical-ethics#', 
 'Professional medical ethics domain for healthcare professionals',
 '{"version": "1.0", "created_by": "system", "specialty": "healthcare"}'),
('legal-ethics', 'Legal Ethics', 'http://proethica.org/ontology/legal-ethics#',
 'Professional legal ethics domain for legal practitioners', 
 '{"version": "1.0", "created_by": "system", "specialty": "law"}'),
('business-ethics', 'Business Ethics', 'http://proethica.org/ontology/business-ethics#',
 'Professional business ethics domain for corporate environments',
 '{"version": "1.0", "created_by": "system", "specialty": "business"}')
ON CONFLICT (name) DO NOTHING;

-- Sample approved concepts for the engineering-ethics domain (for testing)
DO $$
DECLARE
    eng_domain_id INTEGER;
BEGIN
    -- Get the engineering-ethics domain ID
    SELECT id INTO eng_domain_id FROM domains WHERE name = 'engineering-ethics';
    
    IF eng_domain_id IS NOT NULL THEN
        -- Insert sample approved concepts
        INSERT INTO concepts (
            domain_id, uri, label, semantic_label, primary_type, description, 
            status, confidence_score, created_by, approved_by, approved_at
        ) VALUES
        (eng_domain_id, 
         'http://proethica.org/ontology/engineering-ethics#PublicSafetyPrinciple',
         'Public Safety Principle (Principle)',
         'Public Safety Principle',
         'Principle',
         'The fundamental principle that engineers must hold paramount the safety, health, and welfare of the public',
         'approved',
         0.95,
         'system',
         'system',
         CURRENT_TIMESTAMP),
         
        (eng_domain_id,
         'http://proethica.org/ontology/engineering-ethics#ProfessionalEngineerRole',
         'Professional Engineer Role (Role)',
         'Professional Engineer Role', 
         'Role',
         'A licensed professional engineer with legal authority to practice engineering',
         'approved',
         0.98,
         'system',
         'system',
         CURRENT_TIMESTAMP),
         
        (eng_domain_id,
         'http://proethica.org/ontology/engineering-ethics#TechnicalCompetenceObligation',
         'Technical Competence Obligation (Obligation)',
         'Technical Competence Obligation',
         'Obligation', 
         'The obligation for engineers to perform services only in areas of their competence',
         'approved',
         0.92,
         'system',
         'system',
         CURRENT_TIMESTAMP),
         
        (eng_domain_id,
         'http://proethica.org/ontology/engineering-ethics#StructuralIntegrityState',
         'Structural Integrity State (State)',
         'Structural Integrity State',
         'State',
         'The state of a structure being sound and capable of withstanding intended loads',
         'approved',
         0.89,
         'system',
         'system', 
         CURRENT_TIMESTAMP),
         
        (eng_domain_id,
         'http://proethica.org/ontology/engineering-ethics#QualityAssuranceCapability',
         'Quality Assurance Capability (Capability)',
         'Quality Assurance Capability',
         'Capability',
         'The capability to ensure that engineering work meets specified quality standards',
         'approved',
         0.87,
         'system',
         'system',
         CURRENT_TIMESTAMP)
        ON CONFLICT (uri) DO NOTHING;
        
        -- Insert a sample candidate concept
        INSERT INTO concepts (
            domain_id, uri, label, semantic_label, primary_type, description,
            status, confidence_score, extraction_method, source_document, 
            llm_reasoning, created_by, needs_review
        ) VALUES
        (eng_domain_id,
         'http://proethica.org/ontology/engineering-ethics#CodeOfEthicsResource',
         'Code of Ethics Resource (Resource)',
         'Code of Ethics Resource',
         'Resource',
         'A documented set of ethical guidelines and standards for professional engineers',
         'candidate',
         0.83,
         'llm_extraction',
         'NSPE Code of Ethics',
         'This concept was extracted as it represents a fundamental resource referenced throughout professional engineering ethics guidelines.',
         'proethica-extractor',
         true)
        ON CONFLICT (uri) DO NOTHING;
    END IF;
END $$;

-- Create sample concept relationships
DO $$
DECLARE
    safety_principle_id INTEGER;
    engineer_role_id INTEGER;
    competence_obligation_id INTEGER;
BEGIN
    -- Get concept IDs
    SELECT id INTO safety_principle_id FROM concepts 
    WHERE uri = 'http://proethica.org/ontology/engineering-ethics#PublicSafetyPrinciple';
    
    SELECT id INTO engineer_role_id FROM concepts 
    WHERE uri = 'http://proethica.org/ontology/engineering-ethics#ProfessionalEngineerRole';
    
    SELECT id INTO competence_obligation_id FROM concepts 
    WHERE uri = 'http://proethica.org/ontology/engineering-ethics#TechnicalCompetenceObligation';
    
    -- Create relationships if concepts exist
    IF safety_principle_id IS NOT NULL AND engineer_role_id IS NOT NULL THEN
        INSERT INTO concept_relationships (
            subject_concept_id, predicate, object_concept_id, 
            confidence_score, status, created_by, approved_by, approved_at
        ) VALUES
        (engineer_role_id, 'adheresToPrinciple', safety_principle_id,
         0.95, 'approved', 'system', 'system', CURRENT_TIMESTAMP)
        ON CONFLICT (subject_concept_id, predicate, object_concept_id) DO NOTHING;
    END IF;
    
    IF engineer_role_id IS NOT NULL AND competence_obligation_id IS NOT NULL THEN
        INSERT INTO concept_relationships (
            subject_concept_id, predicate, object_concept_id,
            confidence_score, status, created_by, approved_by, approved_at
        ) VALUES
        (engineer_role_id, 'hasObligation', competence_obligation_id,
         0.92, 'approved', 'system', 'system', CURRENT_TIMESTAMP)
        ON CONFLICT (subject_concept_id, predicate, object_concept_id) DO NOTHING;
    END IF;
END $$;

-- Create sample RDF triples for approved concepts
DO $$
DECLARE
    concept_record RECORD;
BEGIN
    FOR concept_record IN 
        SELECT id, uri, label, description, primary_type 
        FROM concepts 
        WHERE status = 'approved'
    LOOP
        -- Insert basic RDF triples for each approved concept
        INSERT INTO concept_triples (
            concept_id, subject, predicate, object_literal, is_literal,
            subject_label, predicate_label, object_label
        ) VALUES
        -- rdfs:label triple
        (concept_record.id, concept_record.uri, 'http://www.w3.org/2000/01/rdf-schema#label',
         concept_record.label, true, concept_record.label, 'label', concept_record.label),
        -- rdfs:comment triple  
        (concept_record.id, concept_record.uri, 'http://www.w3.org/2000/01/rdf-schema#comment',
         concept_record.description, true, concept_record.label, 'comment', concept_record.description),
        -- rdf:type triple
        (concept_record.id, concept_record.uri, 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type',
         'http://proethica.org/ontology#' || concept_record.primary_type, false,
         concept_record.label, 'type', concept_record.primary_type)
        ON CONFLICT DO NOTHING;
    END LOOP;
END $$;

-- Analyze tables for better performance
ANALYZE domains;
ANALYZE ontologies; 
ANALYZE ontology_versions;
ANALYZE concepts;
ANALYZE concept_versions;
ANALYZE concept_relationships;
ANALYZE concept_triples;
ANALYZE candidate_metadata;
ANALYZE approval_workflows;

-- Final status message
DO $$
BEGIN
    RAISE NOTICE 'OntServe database initialization complete';
    RAISE NOTICE 'Schema version: 1.0.0';
    RAISE NOTICE 'Sample data loaded for engineering-ethics domain';
    RAISE NOTICE 'Ready for production use';
END $$;
