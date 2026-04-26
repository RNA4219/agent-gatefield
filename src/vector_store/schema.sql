-- Database Schema for State Space Gate System
-- PostgreSQL + pgvector
-- Version: 1.0.0
--
-- Run: psql -d gatefield -f schema.sql
-- Or via Docker: mounted at /docker-entrypoint-initdb.d/

-- Enable pgvector extension (redundant with init-extensions.sql, but safe)
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Judgment Documents (constitution, taboo, accepted, rejected, logs)
-- ============================================================================
CREATE TABLE IF NOT EXISTS judgment_documents (
    doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    axis_type VARCHAR(50) NOT NULL CHECK (axis_type IN ('constitution', 'taboo', 'accepted', 'rejected', 'judgment_log')),
    text TEXT NOT NULL,
    source_type VARCHAR(50) DEFAULT 'manual' CHECK (source_type IN ('manual', 'run_promoted', 'import')),
    version INTEGER NOT NULL DEFAULT 1,
    labels JSONB DEFAULT '{}',
    scope VARCHAR(100),  -- repo, team, service
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'deprecated', 'deleted')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Ensure active documents have unique axis+scope combination
    CONSTRAINT unique_active_doc UNIQUE (axis_type, scope, text) WHERE status = 'active'
);

-- ============================================================================
-- Judgment Embeddings (append-only versioning)
-- ============================================================================
CREATE TABLE IF NOT EXISTS judgment_embeddings (
    embed_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id UUID NOT NULL REFERENCES judgment_documents(doc_id) ON DELETE CASCADE,
    model VARCHAR(100) NOT NULL DEFAULT 'local-hash-embedding-v1',
    dims INTEGER NOT NULL DEFAULT 1536 CHECK (dims IN (1536, 3072)),
    embedding vector(1536),
    content_hash VARCHAR(64),  -- SHA256 of text content
    valid_from TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    valid_to TIMESTAMP WITH TIME ZONE NULL,  -- NULL means current version
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Basic indexes (HNSW indexes created in init-extensions.sql)
CREATE INDEX IF NOT EXISTS idx_embed_doc ON judgment_embeddings(doc_id);
CREATE INDEX IF NOT EXISTS idx_embed_valid ON judgment_embeddings(valid_from, valid_to) WHERE valid_to IS NULL;

-- ============================================================================
-- State Vectors per Run (immutable, stored for replay)
-- ============================================================================
CREATE TABLE IF NOT EXISTS state_vectors (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id UUID,
    semantic_embedding vector(1536),
    rule_json JSONB DEFAULT '{}',
    test_json JSONB DEFAULT '{}',
    risk_json JSONB DEFAULT '{}',
    history_json JSONB DEFAULT '{}',
    uncertainty_json JSONB DEFAULT '{}',
    context_json JSONB DEFAULT '{}',
    trajectory_json JSONB DEFAULT '{}',
    decision VARCHAR(20),  -- pass, warn, hold, block (final decision)
    scorer_results JSONB DEFAULT '{}',
    thresholds JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- Static Gate Results (immutable, per-run)
-- ============================================================================
CREATE TABLE IF NOT EXISTS static_gate_results (
    gate_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES state_vectors(run_id) ON DELETE CASCADE,
    gate_name VARCHAR(50) NOT NULL CHECK (gate_name IN ('lint', 'typecheck', 'tests', 'sast', 'secret_scan', 'license_scan', 'tool_policy')),
    severity VARCHAR(20) CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('pass', 'fail', 'warn')),
    evidence_ref TEXT,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gate_run ON static_gate_results(run_id);
CREATE INDEX IF NOT EXISTS idx_gate_failures ON static_gate_results(gate_name) WHERE status = 'fail';

-- ============================================================================
-- Gate Decisions (immutable audit trail)
-- ============================================================================
CREATE TABLE IF NOT EXISTS gate_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES state_vectors(run_id) ON DELETE CASCADE,
    composite_score FLOAT CHECK (composite_score >= 0 AND composite_score <= 1),
    state VARCHAR(20) NOT NULL CHECK (state IN ('pass', 'warn', 'hold', 'block')),
    reasons_json JSONB DEFAULT '{}',
    factors_json JSONB DEFAULT '{}',
    exemplar_refs_json JSONB DEFAULT '{}',
    action_type VARCHAR(50) CHECK (action_type IN ('continue', 'artifact_correction', 'process_correction', 'prompt_correction', 'human_review', 'hold_for_review')),
    threshold_version VARCHAR(50) DEFAULT 'v1',
    hard_override VARCHAR(50),  -- secret_found, prod_write_taboo, sast_high, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decision_run ON gate_decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_decision_state ON gate_decisions(state, created_at);

-- ============================================================================
-- Human Reviews (immutable audit trail)
-- ============================================================================
CREATE TABLE IF NOT EXISTS human_reviews (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID NOT NULL REFERENCES gate_decisions(decision_id) ON DELETE CASCADE,
    run_id UUID REFERENCES state_vectors(run_id),
    reviewer VARCHAR(100) NOT NULL,
    action_type VARCHAR(50) NOT NULL CHECK (action_type IN ('approve', 'reject', 'recalibrate', 'request_artifact_correction', 'request_process_correction', 'request_prompt_correction', 'add_judgment_note')),
    previous_decision VARCHAR(20),
    new_decision VARCHAR(20),
    comment TEXT,
    correction_json JSONB DEFAULT '{}',
    sla_compliant BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_decision ON human_reviews(decision_id);
CREATE INDEX IF NOT EXISTS idx_review_run ON human_reviews(run_id);
CREATE INDEX IF NOT EXISTS idx_reviewer ON human_reviews(reviewer, created_at);

-- ============================================================================
-- Threshold Version History (immutable, for replay)
-- ============================================================================
CREATE TABLE IF NOT EXISTS threshold_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_name VARCHAR(50) NOT NULL UNIQUE,
    thresholds_json JSONB NOT NULL,
    weights_json JSONB NOT NULL,
    hard_overrides_json JSONB DEFAULT '{}',
    locked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    locked_by VARCHAR(100)
);

-- Insert default threshold version
INSERT INTO threshold_versions (version_name, thresholds_json, weights_json, hard_overrides_json)
VALUES (
    'v1',
    '{"taboo_warn": 0.80, "taboo_block": 0.88, "reject_warn": 0.75, "reject_block": 0.85, "judge_std_warn": 0.15, "judge_std_block": 0.25, "tool_failure_warn": 0.10, "tool_failure_block": 0.25, "direction_block": -0.50, "anomaly_warn_percentile": 95, "anomaly_block_percentile": 99}'::jsonb,
    '{"constitution_alignment": 0.20, "taboo_proximity": 0.30, "accept_similarity": 0.10, "reject_similarity": 0.15, "direction": 0.05, "drift": 0.05, "anomaly": 0.10, "uncertainty": 0.05}'::jsonb,
    '{"block_if_secret_found": true, "block_if_prod_write_and_taboo_warn": true, "hold_if_high_privilege_and_uncertain": true}'::jsonb
) ON CONFLICT (version_name) DO NOTHING;

-- ============================================================================
-- Calibration Profiles (per team/repo/service)
-- ============================================================================
CREATE TABLE IF NOT EXISTS calibration_profiles (
    profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope VARCHAR(100) NOT NULL UNIQUE,
    weights_json JSONB DEFAULT '{}',
    warn_thresholds_json JSONB DEFAULT '{}',
    block_thresholds_json JSONB DEFAULT '{}',
    anomaly_detector_config JSONB DEFAULT '{}',
    drift_indicators_json JSONB DEFAULT '{}',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- Audit Events (OTel compatible, retention managed)
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id VARCHAR(64),
    span_id VARCHAR(64),
    run_id UUID,
    event_type VARCHAR(50) NOT NULL,
    actor VARCHAR(50),
    payload_hash VARCHAR(64),
    payload_ref TEXT,
    retention_class VARCHAR(20) DEFAULT 'audit' CHECK (retention_class IN ('audit', 'ops', 'pii_sensitive', 'traces')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Retention policy indexes (for cleanup jobs)
CREATE INDEX IF NOT EXISTS idx_audit_retention ON audit_events(retention_class, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_events(trace_id) WHERE trace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_events(run_id) WHERE run_id IS NOT NULL;

-- ============================================================================
-- Similarity Search Function
-- ============================================================================
CREATE OR REPLACE FUNCTION search_similar(
    query_vector vector(1536),
    axis_filter VARCHAR(50),
    limit_count INTEGER DEFAULT 10
) RETURNS TABLE (
    doc_id UUID,
    similarity FLOAT,
    axis_type VARCHAR(50),
    text TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        jd.doc_id,
        1 - (je.embedding <=> query_vector) as similarity,
        jd.axis_type,
        jd.text
    FROM judgment_embeddings je
    JOIN judgment_documents jd ON je.doc_id = jd.doc_id
    WHERE jd.axis_type = axis_filter
      AND jd.status = 'active'
      AND je.valid_to IS NULL
    ORDER BY je.embedding <=> query_vector
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql STABLE;

-- ============================================================================
-- Search with full metadata
-- ============================================================================
CREATE OR REPLACE FUNCTION search_similar_full(
    query_vector vector(1536),
    axis_filter VARCHAR(50),
    limit_count INTEGER DEFAULT 10
) RETURNS TABLE (
    doc_id UUID,
    similarity FLOAT,
    axis_type VARCHAR(50),
    text TEXT,
    labels JSONB,
    scope VARCHAR(100),
    version INTEGER,
    source_type VARCHAR(50)
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        jd.doc_id,
        1 - (je.embedding <=> query_vector) as similarity,
        jd.axis_type,
        jd.text,
        jd.labels,
        jd.scope,
        jd.version,
        jd.source_type
    FROM judgment_embeddings je
    JOIN judgment_documents jd ON je.doc_id = jd.doc_id
    WHERE jd.axis_type = axis_filter
      AND jd.status = 'active'
      AND je.valid_to IS NULL
    ORDER BY je.embedding <=> query_vector
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql STABLE;

-- ============================================================================
-- Get threshold version function
-- ============================================================================
CREATE OR REPLACE FUNCTION get_threshold_version(
    version_name VARCHAR(50)
) RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'version_name', version_name,
        'thresholds', thresholds_json,
        'weights', weights_json,
        'hard_overrides', hard_overrides_json
    ) INTO result
    FROM threshold_versions
    WHERE version_name = get_threshold_version.version_name;

    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE;

-- ============================================================================
-- Grant permissions
-- ============================================================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO gatefield;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO gatefield;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO gatefield;

-- Log schema creation
DO $$
BEGIN
    RAISE NOTICE 'Schema creation completed: judgment_documents, judgment_embeddings, state_vectors, gate_decisions, human_reviews, threshold_versions';
END
$$;
