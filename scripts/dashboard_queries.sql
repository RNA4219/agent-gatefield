-- Monitoring Dashboard Queries for agent-gatefield
-- Run with: psql -d gatefield -f scripts/dashboard_queries.sql
-- Or via CLI: python -m cli.gate_cli review list --stats

-- ============================================================================
-- Volume Metrics
-- ============================================================================

-- Runs processed (last 24 hours)
SELECT COUNT(*) as runs_24h FROM gate_decisions
WHERE created_at > NOW() - INTERVAL '1 day';

-- Decisions by state (last 24 hours)
SELECT state, COUNT(*), ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as pct
FROM gate_decisions
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY state ORDER BY COUNT(*) DESC;

-- Artifacts by type
SELECT context_json->>'artifact_type' as artifact_type, COUNT(*)
FROM state_vectors
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY context_json->>'artifact_type'
ORDER BY COUNT(*) DESC;

-- ============================================================================
-- Quality Metrics
-- ============================================================================

-- Taboo detection rate (from taboo_proximity > 0.80)
SELECT
    COUNT(CASE WHEN factors_json->>'taboo_proximity' > '0.80' THEN 1 END) as taboo_flagged,
    COUNT(*) as total,
    ROUND(COUNT(CASE WHEN factors_json->>'taboo_proximity' > '0.80' THEN 1 END) * 100.0 / COUNT(*), 2) as taboo_rate
FROM gate_decisions
WHERE created_at > NOW() - INTERVAL '1 day';

-- Top blocking reasons
SELECT
    reasons_json->>'top_factor' as reason,
    COUNT(*) as count,
    ROUND(AVG(composite_score), 4) as avg_score
FROM gate_decisions
WHERE state IN ('block', 'hold')
AND created_at > NOW() - INTERVAL '7 days'
GROUP BY reasons_json->>'top_factor'
ORDER BY COUNT(*) DESC LIMIT 10;

-- Hard override triggers
SELECT hard_override, COUNT(*)
FROM gate_decisions
WHERE hard_override IS NOT NULL
AND created_at > NOW() - INTERVAL '7 days'
GROUP BY hard_override ORDER BY COUNT(*) DESC;

-- ============================================================================
-- Latency Metrics
-- ============================================================================

-- Gate evaluation latency (from audit_events)
SELECT
    event_type,
    COUNT(*),
    ROUND(AVG(EXTRACT(EPOCH FROM (created_at - LAG(created_at) OVER (PARTITION BY run_id ORDER BY created_at)))), 2) as avg_latency_sec
FROM audit_events
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY event_type;

-- Review queue latency (pending items by age)
SELECT
    CASE
        WHEN created_at > NOW() - INTERVAL '15 minutes' THEN '< 15min'
        WHEN created_at > NOW() - INTERVAL '1 hour' THEN '15min-1h'
        WHEN created_at > NOW() - INTERVAL '4 hours' THEN '1h-4h'
        ELSE '> 4h'
    END as age_bucket,
    COUNT(*)
FROM human_reviews
WHERE previous_decision IS NULL OR previous_decision = ''
GROUP BY age_bucket ORDER BY age_bucket;

-- ============================================================================
-- Health Metrics
-- ============================================================================

-- State vector coverage (vs gate_decisions)
SELECT
    COUNT(DISTINCT sv.run_id) as with_vectors,
    COUNT(DISTINCT gd.run_id) as total_runs,
    ROUND(COUNT(DISTINCT sv.run_id) * 100.0 / COUNT(DISTINCT gd.run_id), 2) as coverage_pct
FROM gate_decisions gd
LEFT JOIN state_vectors sv ON gd.run_id = sv.run_id
WHERE gd.created_at > NOW() - INTERVAL '1 day';

-- Embedding worker status (latest embeddings)
SELECT
    model,
    dims,
    COUNT(*) as active_embeddings,
    MAX(created_at) as last_embedding_time
FROM judgment_embeddings
WHERE valid_to IS NULL
GROUP BY model, dims;

-- Judgment KB size by axis
SELECT
    axis_type,
    COUNT(*) as documents,
    COUNT(CASE WHEN je.embed_id IS NOT NULL THEN 1 END) as with_embeddings
FROM judgment_documents jd
LEFT JOIN judgment_embeddings je ON jd.doc_id = je.doc_id AND je.valid_to IS NULL
WHERE jd.status = 'active'
GROUP BY axis_type ORDER BY axis_type;

-- ============================================================================
-- SLA Metrics
-- ============================================================================

-- SLA breaches by severity
SELECT
    severity,
    COUNT(CASE WHEN created_at < NOW() - INTERVAL '15 minutes' AND previous_decision IS NULL THEN 1 END) as critical_ack_breach,
    COUNT(CASE WHEN created_at < NOW() - INTERVAL '1 hour' AND previous_decision IS NULL THEN 1 END) as high_ack_breach
FROM human_reviews
WHERE previous_decision IS NULL OR previous_decision = ''
GROUP BY severity;

-- Review resolution rate
SELECT
    DATE(created_at) as date,
    COUNT(CASE WHEN previous_decision IS NOT NULL AND previous_decision != '' THEN 1 END) as resolved,
    COUNT(CASE WHEN previous_decision IS NULL OR previous_decision = '' THEN 1 END) as pending
FROM human_reviews
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at) ORDER BY DATE(created_at);

-- ============================================================================
-- Threshold Version Tracking
-- ============================================================================

-- Decisions by threshold version
SELECT threshold_version, state, COUNT(*)
FROM gate_decisions
GROUP BY threshold_version, state ORDER BY threshold_version, state;

-- Threshold version history
SELECT version_name, locked_at, locked_by
FROM threshold_versions
ORDER BY locked_at DESC;

-- ============================================================================
-- Alert Conditions (for monitoring)
-- ============================================================================

-- Coverage drop alert (< 90%)
SELECT 'COVERAGE_DROP' as alert_type, COUNT(*) as alert_count
FROM (
    SELECT COUNT(DISTINCT sv.run_id) * 100.0 / COUNT(DISTINCT gd.run_id) as coverage
    FROM gate_decisions gd
    LEFT JOIN state_vectors sv ON gd.run_id = sv.run_id
    WHERE gd.created_at > NOW() - INTERVAL '1 day'
) t WHERE coverage < 90;

-- Queue backlog alert (critical > 5 for > 15 min)
SELECT 'QUEUE_BACKLOG' as alert_type, COUNT(*) as critical_pending
FROM human_reviews
WHERE (previous_decision IS NULL OR previous_decision = '')
AND created_at < NOW() - INTERVAL '15 minutes';

-- Embedding worker down alert (no new embeddings in 5 min - check last_embedding_time)
SELECT 'EMBEDDING_WORKER_DOWN' as alert_type, MAX(created_at) as last_embedding
FROM judgment_embeddings
WHERE created_at > NOW() - INTERVAL '1 hour';