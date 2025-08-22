-- OntServe PostgreSQL Database Schema
-- Professional ontology storage with versioning and candidate concept management
-- Compatible with Proethica's requirements
--
-- Created: 2025-08-22
-- Version: 1.0.0

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ===== DOMAIN MANAGEMENT =====

-- Professional domains (replacing Proethica's "worlds" concept)
CREATE TABLE domains (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    namespace_uri TEXT NOT NULL UNIQUE,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for performance
CREATE INDEX idx_domains_name ON domains(name);
CREATE INDEX idx_domains_active ON domains(is_active);

-- ===== ONTOLOGY MANAGEMENT =====

-- Base ontology definitions
CREATE TABLE ontologies (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    domain_id INTEGER REFERENCES domains(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    base_uri TEXT NOT NULL,
    description TEXT,
    is_base BOOLEAN DEFAULT false,
    is_editable BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain_id, name)
);

-- Ontology content versioning
CREATE TABLE ontology_versions (
    id SERIAL PRIMARY KEY,
    ontology_id INTEGER REFERENCES ontologies(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    version_tag VARCHAR(50),
    content TEXT NOT NULL, -- TTL/RDF content
    content_hash VARCHAR(64), -- SHA-256 hash for integrity
    change_summary TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_current BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}',
    UNIQUE(ontology_id, version_number)
);

-- Ontology import relationships
CREATE TABLE ontology_imports (
    id SERIAL PRIMARY KEY,
    importing_ontology_id INTEGER REFERENCES ontologies(id) ON DELETE CASCADE,
    imported_ontology_id INTEGER REFERENCES ontologies(id) ON DELETE CASCADE,
    import_uri TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(importing_ontology_id, imported_ontology_id)
);

-- Indexes for ontology tables
CREATE INDEX idx_ontologies_domain ON ontologies(domain_id);
CREATE INDEX idx_ontology_versions_ontology ON ontology_versions(ontology_id);
CREATE INDEX idx_ontology_versions_current ON ontology_versions(ontology_id, is_current);

-- ===== CONCEPT STORAGE WITH CANDIDATE MANAGEMENT =====

-- Main concepts table (approved and candidate concepts)
CREATE TABLE concepts (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    domain_id INTEGER REFERENCES domains(id) ON DELETE CASCADE,
    ontology_id INTEGER REFERENCES ontologies(id) ON DELETE SET NULL,
    
    -- Core concept identification
    uri TEXT NOT NULL,
    label VARCHAR(255) NOT NULL,
    semantic_label VARCHAR(255), -- Semantic description from LLM extraction
    primary_type VARCHAR(50) NOT NULL, -- Role, Principle, Obligation, State, Resource, Action, Event, Capability, Constraint
    description TEXT,
    
    -- Status and workflow management
    status VARCHAR(20) DEFAULT 'candidate' 
        CHECK (status IN ('candidate', 'approved', 'rejected', 'deprecated', 'under_review')),
    approval_workflow_state VARCHAR(50),
    
    -- Extraction and confidence metadata
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    extraction_method VARCHAR(100), -- e.g., 'llm_extraction', 'manual_entry', 'import'
    source_document TEXT,
    source_context TEXT,
    llm_reasoning TEXT,
    original_llm_type VARCHAR(255), -- Original type before mapping
    
    -- Type mapping metadata (compatible with Proethica's two-tier system)
    type_mapping_confidence FLOAT CHECK (type_mapping_confidence >= 0 AND type_mapping_confidence <= 1),
    mapping_source VARCHAR(50), -- 'exact_match', 'semantic_rules', 'manual', 'historical'
    mapping_justification TEXT,
    needs_type_review BOOLEAN DEFAULT false,
    
    -- Review and approval metadata
    needs_review BOOLEAN DEFAULT false,
    review_notes TEXT,
    review_assigned_to VARCHAR(255),
    
    -- Timestamps and attribution
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    approved_by VARCHAR(255),
    approved_at TIMESTAMP WITH TIME ZONE,
    updated_by VARCHAR(255),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Versioning support
    version_number INTEGER DEFAULT 1,
    parent_concept_id INTEGER REFERENCES concepts(id),
    
    -- Vector embeddings for semantic search (pgvector)
    label_embedding vector(384), -- For sentence transformers
    description_embedding vector(384),
    
    -- Additional flexible metadata
    metadata JSONB DEFAULT '{}'
);

-- Concept version history for full audit trail
CREATE TABLE concept_versions (
    id SERIAL PRIMARY KEY,
    concept_id INTEGER REFERENCES concepts(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    
    -- Snapshot of concept state at this version
    uri TEXT NOT NULL,
    label VARCHAR(255) NOT NULL,
    semantic_label VARCHAR(255),
    primary_type VARCHAR(50) NOT NULL,
    description TEXT,
    status VARCHAR(20),
    metadata JSONB,
    
    -- Change tracking
    changed_fields JSONB, -- Array of field names that changed
    change_reason TEXT,
    changed_by VARCHAR(255),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(concept_id, version_number)
);

-- Concept relationships (semantic connections between concepts)
CREATE TABLE concept_relationships (
    id SERIAL PRIMARY KEY,
    subject_concept_id INTEGER REFERENCES concepts(id) ON DELETE CASCADE,
    predicate VARCHAR(100) NOT NULL, -- hasObligation, adheresToPrinciple, etc.
    object_concept_id INTEGER REFERENCES concepts(id) ON DELETE CASCADE,
    
    -- Relationship metadata
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    status VARCHAR(20) DEFAULT 'candidate' 
        CHECK (status IN ('candidate', 'approved', 'rejected', 'deprecated')),
    
    -- Attribution and approval
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    approved_by VARCHAR(255),
    approved_at TIMESTAMP WITH TIME ZONE,
    
    -- Prevent duplicate relationships
    UNIQUE(subject_concept_id, predicate, object_concept_id)
);

-- Performance indexes for concepts
CREATE INDEX idx_concepts_domain_status ON concepts(domain_id, status);
CREATE INDEX idx_concepts_type_status ON concepts(primary_type, status);
CREATE INDEX idx_concepts_uri ON concepts(uri);
CREATE INDEX idx_concepts_label ON concepts(label);
CREATE INDEX idx_concepts_needs_review ON concepts(needs_review) WHERE needs_review = true;
CREATE INDEX idx_concepts_created_at ON concepts(created_at);

-- Vector similarity search indexes
CREATE INDEX idx_concepts_label_embedding ON concepts USING ivfflat (label_embedding vector_cosine_ops);
CREATE INDEX idx_concepts_description_embedding ON concepts USING ivfflat (description_embedding vector_cosine_ops);

-- ===== RDF TRIPLE STORAGE (Proethica Compatible) =====

-- RDF triples for detailed concept definitions and relationships
-- This maintains compatibility with Proethica's entity_triples structure
CREATE TABLE concept_triples (
    id SERIAL PRIMARY KEY,
    concept_id INTEGER REFERENCES concepts(id) ON DELETE CASCADE,
    
    -- Standard RDF triple components
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_literal TEXT,
    object_uri TEXT,
    is_literal BOOLEAN NOT NULL,
    
    -- Human-readable labels for UI display
    subject_label VARCHAR(255),
    predicate_label VARCHAR(255),
    object_label VARCHAR(255),
    
    -- Graph and context information
    graph VARCHAR(255), -- Named graph identifier
    entity_type VARCHAR(50), -- For polymorphic entity reference
    entity_id INTEGER, -- Reference to specific entity
    
    -- BFO-compliant temporal tracking
    temporal_region_type VARCHAR(255), -- BFO_0000038 (1D) or BFO_0000148 (0D)
    temporal_start TIMESTAMP WITH TIME ZONE,
    temporal_end TIMESTAMP WITH TIME ZONE,
    temporal_relation_type VARCHAR(50), -- precedes, follows, during, etc.
    temporal_relation_to INTEGER REFERENCES concept_triples(id),
    temporal_granularity VARCHAR(50), -- seconds, minutes, days, etc.
    temporal_confidence FLOAT DEFAULT 1.0,
    temporal_context JSONB DEFAULT '{}',
    
    -- Vector embeddings for semantic search
    subject_embedding vector(384),
    predicate_embedding vector(384),
    object_embedding vector(384),
    
    -- Flexible metadata storage
    triple_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for triple queries
CREATE INDEX idx_triples_concept ON concept_triples(concept_id);
CREATE INDEX idx_triples_subject ON concept_triples(subject);
CREATE INDEX idx_triples_predicate ON concept_triples(predicate);
CREATE INDEX idx_triples_subject_predicate ON concept_triples(subject, predicate);
CREATE INDEX idx_triples_temporal_start ON concept_triples(temporal_start);
CREATE INDEX idx_triples_temporal_end ON concept_triples(temporal_end);

-- Vector search indexes for triples
CREATE INDEX idx_triples_subject_embedding ON concept_triples USING ivfflat (subject_embedding vector_cosine_ops);
CREATE INDEX idx_triples_predicate_embedding ON concept_triples USING ivfflat (predicate_embedding vector_cosine_ops);
CREATE INDEX idx_triples_object_embedding ON concept_triples USING ivfflat (object_embedding vector_cosine_ops);

-- ===== CANDIDATE WORKFLOW METADATA =====

-- Additional metadata for candidate concepts extracted from documents
CREATE TABLE candidate_metadata (
    id SERIAL PRIMARY KEY,
    concept_id INTEGER REFERENCES concepts(id) ON DELETE CASCADE,
    
    -- Extraction details
    extraction_session_id VARCHAR(255), -- Group related extractions
    extraction_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    extractor_version VARCHAR(50), -- Version of extraction system
    
    -- Source document details
    source_document_uri TEXT,
    source_document_title TEXT,
    source_document_section TEXT,
    source_text TEXT, -- Actual text that led to extraction
    source_page_number INTEGER,
    source_line_number INTEGER,
    
    -- LLM processing details
    llm_model VARCHAR(100),
    llm_prompt_version VARCHAR(50),
    llm_response_raw TEXT, -- Full LLM response
    llm_confidence FLOAT,
    
    -- Context and relationships found during extraction
    related_concepts TEXT[], -- Array of related concept URIs
    contextual_clues TEXT, -- Additional context from surrounding text
    
    -- Quality metrics
    extraction_quality_score FLOAT,
    requires_human_validation BOOLEAN DEFAULT false,
    validation_notes TEXT,
    
    -- Flexible metadata
    metadata JSONB DEFAULT '{}'
);

-- Index for candidate metadata
CREATE INDEX idx_candidate_metadata_concept ON candidate_metadata(concept_id);
CREATE INDEX idx_candidate_metadata_session ON candidate_metadata(extraction_session_id);

-- ===== APPROVAL WORKFLOWS =====

-- Track approval workflow states and history
CREATE TABLE approval_workflows (
    id SERIAL PRIMARY KEY,
    concept_id INTEGER REFERENCES concepts(id) ON DELETE CASCADE,
    
    -- Workflow details
    workflow_type VARCHAR(50) DEFAULT 'standard', -- standard, expedited, expert_review
    current_state VARCHAR(50) DEFAULT 'submitted',
    previous_state VARCHAR(50),
    
    -- Assignment and routing
    assigned_to VARCHAR(255),
    assigned_at TIMESTAMP WITH TIME ZONE,
    priority INTEGER DEFAULT 3 CHECK (priority BETWEEN 1 AND 5), -- 1=highest, 5=lowest
    
    -- Decision tracking
    decision VARCHAR(50), -- approved, rejected, needs_revision
    decision_reason TEXT,
    decided_by VARCHAR(255),
    decided_at TIMESTAMP WITH TIME ZONE,
    
    -- Workflow metadata
    estimated_completion TIMESTAMP WITH TIME ZONE,
    actual_completion TIMESTAMP WITH TIME ZONE,
    workflow_metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for workflow queries
CREATE INDEX idx_workflows_concept ON approval_workflows(concept_id);
CREATE INDEX idx_workflows_assigned_to ON approval_workflows(assigned_to);
CREATE INDEX idx_workflows_state ON approval_workflows(current_state);

-- ===== SYSTEM CONFIGURATION =====

-- System configuration and metadata
CREATE TABLE system_config (
    key VARCHAR(255) PRIMARY KEY,
    value JSONB,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Audit log for important system events
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(255) NOT NULL,
    record_id INTEGER,
    action VARCHAR(50) NOT NULL, -- INSERT, UPDATE, DELETE
    old_values JSONB,
    new_values JSONB,
    user_id VARCHAR(255),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Index for audit queries
CREATE INDEX idx_audit_log_table_record ON audit_log(table_name, record_id);
CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_log_user ON audit_log(user_id);

-- ===== FUNCTIONS AND TRIGGERS =====

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add updated_at triggers to relevant tables
CREATE TRIGGER update_domains_updated_at BEFORE UPDATE ON domains
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ontologies_updated_at BEFORE UPDATE ON ontologies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_concepts_updated_at BEFORE UPDATE ON concepts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_concept_triples_updated_at BEFORE UPDATE ON concept_triples
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_approval_workflows_updated_at BEFORE UPDATE ON approval_workflows
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_system_config_updated_at BEFORE UPDATE ON system_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===== INITIAL DATA =====

-- Insert default engineering ethics domain
INSERT INTO domains (name, display_name, namespace_uri, description, metadata) VALUES
('engineering-ethics', 'Engineering Ethics', 'http://proethica.org/ontology/engineering-ethics#', 
 'Professional engineering ethics domain for concept extraction and analysis',
 '{"version": "1.0", "created_by": "system", "default_domain": true}');

-- Insert system configuration defaults
INSERT INTO system_config (key, value, description) VALUES
('schema_version', '"1.0.0"', 'Database schema version'),
('concept_types', '["Role", "Principle", "Obligation", "State", "Resource", "Action", "Event", "Capability", "Constraint"]', 'Valid primary concept types'),
('approval_workflow_states', '["submitted", "under_review", "approved", "rejected", "needs_revision"]', 'Valid workflow states'),
('vector_dimensions', '384', 'Vector embedding dimensions for semantic search'),
('default_confidence_threshold', '0.7', 'Default confidence threshold for concept approval');

-- ===== VIEWS FOR COMMON QUERIES =====

-- View for active candidate concepts requiring review
CREATE VIEW candidates_for_review AS
SELECT 
    c.*,
    d.display_name as domain_name,
    cm.source_document_title,
    cm.source_text,
    cm.llm_confidence,
    aw.current_state as workflow_state,
    aw.assigned_to,
    aw.priority
FROM concepts c
JOIN domains d ON c.domain_id = d.id
LEFT JOIN candidate_metadata cm ON c.id = cm.concept_id
LEFT JOIN approval_workflows aw ON c.id = aw.concept_id
WHERE c.status IN ('candidate', 'under_review') 
AND d.is_active = true;

-- View for approved concepts by domain and type
CREATE VIEW approved_concepts_by_domain AS
SELECT 
    d.name as domain_name,
    d.display_name,
    c.primary_type,
    COUNT(*) as concept_count,
    AVG(c.confidence_score) as avg_confidence
FROM concepts c
JOIN domains d ON c.domain_id = d.id
WHERE c.status = 'approved'
AND d.is_active = true
GROUP BY d.name, d.display_name, c.primary_type
ORDER BY d.display_name, c.primary_type;

-- View for concept extraction statistics
CREATE VIEW extraction_statistics AS
SELECT 
    cm.extraction_session_id,
    cm.extractor_version,
    cm.llm_model,
    COUNT(*) as concepts_extracted,
    AVG(cm.llm_confidence) as avg_llm_confidence,
    AVG(c.confidence_score) as avg_final_confidence,
    COUNT(CASE WHEN c.status = 'approved' THEN 1 END) as approved_count,
    COUNT(CASE WHEN c.status = 'rejected' THEN 1 END) as rejected_count,
    MIN(cm.extraction_timestamp) as session_start,
    MAX(cm.extraction_timestamp) as session_end
FROM candidate_metadata cm
JOIN concepts c ON cm.concept_id = c.id
GROUP BY cm.extraction_session_id, cm.extractor_version, cm.llm_model
ORDER BY session_start DESC;

-- ===== COMMENTS FOR DOCUMENTATION =====

COMMENT ON TABLE domains IS 'Professional domains that organize ontologies and concepts';
COMMENT ON TABLE ontologies IS 'Base ontology definitions with metadata and versioning support';
COMMENT ON TABLE concepts IS 'Core concept storage supporting both candidate and approved concepts';
COMMENT ON TABLE concept_versions IS 'Full audit trail of concept changes over time';
COMMENT ON TABLE concept_triples IS 'RDF triple storage compatible with Proethica entity_triples';
COMMENT ON TABLE candidate_metadata IS 'Extended metadata for concepts extracted from documents';
COMMENT ON TABLE approval_workflows IS 'Workflow state tracking for concept approval process';

COMMENT ON COLUMN concepts.semantic_label IS 'Human-readable semantic description from LLM extraction';
COMMENT ON COLUMN concepts.primary_type IS 'One of 8 fundamental ontology types from Proethica classification system';
COMMENT ON COLUMN concepts.label_embedding IS 'Vector embedding for semantic similarity search on concept labels';
COMMENT ON COLUMN concept_triples.temporal_region_type IS 'BFO-compliant temporal region classification';
