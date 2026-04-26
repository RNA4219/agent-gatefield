-- Initialize pgvector extension
-- This script runs after schema.sql during container initialization

-- Ensure pgvector extension is installed
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify extension version
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

-- Create HNSW indexes for faster similarity search
-- These are created after tables exist (from schema.sql)

-- HNSW index for judgment_embeddings (1536 dimensions, cosine distance)
CREATE INDEX IF NOT EXISTS idx_judgment_embeddings_hnsw
ON judgment_embeddings USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- HNSW index for state_vectors (1536 dimensions, cosine distance)
CREATE INDEX IF NOT EXISTS idx_state_vectors_hnsw
ON state_vectors USING hnsw (semantic_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Create additional indexes for common queries

-- Index on judgment_documents for axis_type filtering
CREATE INDEX IF NOT EXISTS idx_judgment_documents_axis_type
ON judgment_documents (axis_type, status);

-- Index on judgment_documents for scope filtering
CREATE INDEX IF NOT EXISTS idx_judgment_documents_scope
ON judgment_documents (scope) WHERE scope IS NOT NULL;

-- Index on gate_decisions for run_id lookup
CREATE INDEX IF NOT EXISTS idx_gate_decisions_run_id
ON gate_decisions (run_id);

-- Index on static_gate_results for run_id lookup
CREATE INDEX IF NOT EXISTS idx_static_gate_results_run_id
ON static_gate_results (run_id);

-- Index on audit_events for trace_id lookup
CREATE INDEX IF NOT EXISTS idx_audit_events_trace_id
ON audit_events (trace_id);

-- Index on audit_events for retention_class
CREATE INDEX IF NOT EXISTS idx_audit_events_retention
ON audit_events (retention_class, created_at);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO gatefield;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO gatefield;

-- Log initialization completion
DO $$
BEGIN
    RAISE NOTICE 'pgvector initialization completed successfully';
END
$$;