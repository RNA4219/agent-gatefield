# Runbook - State Space Gate System

This runbook provides operational guidance for running, monitoring, and troubleshooting the agent-gatefield system.

## Implementation Status (2026-04-26)

| Component | File | Status |
|-----------|------|--------|
| Decision Engine | `src/core/engine.py` | **Implemented** (complexity: 48) |
| 8 Scorers | `src/scorers/__init__.py` | **Implemented** |
| VectorStore + JudgmentKB | `src/vector_store/__init__.py` | **Implemented** |
| StateEncoder | `src/encoder/state_encoder.py` | **Implemented** |
| EmbeddingWorker | `src/encoder/embedding_worker.py` | **Implemented** (complexity: 52) |
| Static Gates (7 adapters) | `src/gates/static/__init__.py` | **Implemented** |
| Calibration Pipeline | `src/core/calibration.py` | **Implemented** |
| Replay Engine | `src/core/replay.py` | **Implemented** |
| Review Queue | `src/review/queue.py` | **Implemented** (complexity: 44) |
| Harness Adapters | `src/adapters/harness.py` | **Implemented** |
| HTTP Adapter Surface | `src/api/http_app.py` | **Implemented** |
| CLI (8 commands) | `cli/gate_cli.py` | **Implemented** |
| Health Monitor | `scripts/monitor_health.py` | **Implemented** |
| Dashboard Queries | `scripts/dashboard_queries.sql` | **Implemented** |
| **Local Retrieval Stack** | | |
| LocalEmbedder (BGE-M3) | `src/encoder/local_embedder.py` | **Implemented** |
| Reranker (bge-reranker-v2-m3) | `src/encoder/local_embedder.py` | **Implemented** |
| QdrantVectorStore | `src/vector_store/qdrant_store.py` | **Implemented** |
| QdrantJudgmentKB | `src/vector_store/qdrant_kb.py` | **Implemented** |

**Implementation Metrics:**
- NotImplementedError: 0 (all resolved)
- TODO items: 0 (all resolved)
- Tests: 1014/1014 passed (100%)
- Coverage: 77% (target: 90%)
- Python files: 72
- Test files: 24
- Mock cleanup: @patch 154→0, Mock() 157→0 (100% reduction)
- Complexity reduction: 215→165 (23% reduction)
- Completion: 85%

**Coverage Improvements:**
| Module | Before | After | Tests Added |
|--------|--------|-------|-------------|
| threshold_versioning | 40% | 100% | 23 |
| replay | 0% | 79% | 18 |
| rerank | 37% | 66% | 33 |
| encoder/utils | 40% | 100% | 11 |
| core/sla_handler | 21% | 93% | 25 |
| qdrant_store | 41% | 65% | 29 |
| scorers/base | 59% | 98% | 21 |
| vector_store/__init__ | 53% | 100% | 17 |
| embedding_worker | 33% | 41% | 27 |
| online_calibration | 26% | 97% | 35 |
| drift_detection | 57% | 100% | 30 |
| claude_adapter | 30% | 98% | 31 |
| openai_adapter | 39% | 98% | 31 |
| langgraph_adapter | 48% | 97% | 31 |

**Technical Debt Status:**
| File | Before | After | Status |
|------|--------|-------|--------|
| `embedding_worker.py` | 52 | 33 | warn (was block) |
| `engine.py` | 48 | 38 | warn (was block) |
| `queue.py` | 44 | 31 | pass (was block) |
| `calibration.py` | 36 | 29 | pass (was warn) |
| `store.py` | 35 | 34 | pass (was warn) |

**Type Annotations:**
- 38 functions missing return type annotations (warn)

**Production Status:**
- PostgreSQL 17 + pgvector v0.7.4: Running
- Judgment KB: Populated (constitution:16, taboo:22, accepted:15, rejected:13)
- Mode: `enforce_warn_hold` (ready for Shadow → Enforce transition)
- **Local Retrieval Stack: BGE-M3 + pgvector default / optional Qdrant + bge-reranker-v2-m3 implemented**

## Quick Reference

| Component | Location | Status Check |
|-----------|----------|--------------|
| PostgreSQL + pgvector | `src/vector_store/schema.sql` | `psql -d gatefield -c "SELECT * FROM judgment_documents LIMIT 1"` |
| Decision Engine | `src/core/engine.py` | `python -c "from src.core.engine import DecisionEngine"` |
| Review Queue | `src/review/queue.py` | `python -c "from src.review.queue import ReviewQueue"` |
| Embedding Worker | `src/encoder/embedding_worker.py` | Check worker logs |
| Static Gate Runner | `src/gates/static/__init__.py` | `python -c "from src.gates.static import StaticGateRunner"` |
| agent-state-gate HTTP surface | `src/api/http_app.py` | `agent-gatefield-api` then `curl http://127.0.0.1:8080/v1/health` |

## Local Retrieval Stack Decision

agent-gatefield の semantic retrieval は、外部生成 AI API に依存しない local-first 構成を正式要件とする。`local-hash-embedding-v1` は fallback / test 用に降格し、製品既定は次の構成へ移行する。

| Layer | Default | Alternatives | Notes |
|---|---|---|---|
| Embedding | BGE-M3 | none for MVP | dense 1024d を既定。将来 sparse / multi-vector は拡張扱い |
| Reranker | bge-reranker-v2-m3 | Qwen3-Reranker 0.6B-4B | 初期リリースは軽量・多言語の bge-reranker-v2-m3 を優先 |
| Vector DB | PostgreSQL/pgvector | Qdrant, LanceDB, SQLite+vec | `agent-state-gate` 統合の既定は pgvector。Qdrant は local retrieval profile |
| Runtime | llama.cpp | Ollama, LM Studio, vLLM | 本番既定は llama.cpp。vLLM は GPU scale profile |

Canonical config:

```yaml
state_space_gate:
  semantic_embedding:
    provider: local
    runtime: llama.cpp
    model: BAAI/bge-m3
    dimensions: 1024
    fallback_model: local-hash-embedding-v1

  reranker:
    enabled: true
    provider: local
    runtime: llama.cpp
    model: BAAI/bge-reranker-v2-m3
    top_k_input: 50
    top_k_output: 10

  vector_store:
    backend: pgvector
    distance: cosine
    dense_dimensions: 1024
    collection: gatefield_judgments

runtime_profiles:
  default: llama.cpp
  dev_optional: ollama
  desktop_optional: lm_studio
  scale_optional: vllm
```

Acceptance checks:

- `OPENAI_API_KEY` 未設定で embedding / reranking / KB search が動作する。
- BGE-M3 dense vector は 1024 dimensions で保存される。
- Qdrant collection は model / dims / axis / dataset_version / redaction_status を payload として保持する。
- Reranker が有効な場合、vector top-k の候補を rerank し、説明に reranker score と exemplar refs を含める。
- `local-hash-embedding-v1` は deterministic fallback と unit test fixture の用途に限定する。

Implementation handoff:

- BGE-M3 / reranker / Qdrant / runtime 連携を実装するエージェントへの作業指示は `docs/AGENT_INSTRUCTIONS_LOCAL_RETRIEVAL.md` を使用する。

---

## 1. System Startup

### 1.1 Database Setup

```bash
# Create database
psql -c "CREATE DATABASE gatefield;"

# Enable pgvector extension and create schema
psql -d gatefield -f src/vector_store/schema.sql

# Verify tables exist
psql -d gatefield -c "\dt"
```

Expected tables:
- `judgment_documents`
- `judgment_embeddings`
- `state_vectors`
- `static_gate_results`
- `gate_decisions`
- `human_reviews`
- `calibration_profiles`
- `audit_events`

### 1.2 Configuration Validation

```bash
# Validate configuration file
harness gate config validate -f config/gate-config.yaml

# Show current config for a scope
harness gate config show --scope service-a
```

### 1.3 Initial Knowledge Base Import

```bash
# Import judgment documents for each axis
harness gate kb import --axis constitution --file datasets/constitution_cases.jsonl
harness gate kb import --axis taboo --file datasets/taboo_cases.jsonl
harness gate kb import --axis accepted --file datasets/accepted_examples.jsonl
harness gate kb import --axis rejected --file datasets/rejected_examples.jsonl
```

### 1.4 Calibration Run

```bash
# Run initial calibration with evaluation dataset
harness gate calibrate --dataset datasets/gates_v1.jsonl

# Optional: update specific profile
harness gate calibrate --dataset datasets/gates_v1.jsonl --profile service-a-staging
```

---

### 1.5 agent-state-gate Adapter Surface

`agent-state-gate` から `GatefieldAdapter` で接続する場合は、HTTP surface を起動する。

```bash
agent-gatefield-api
```

既定では `127.0.0.1:8080` で起動し、以下の `/v1/*` endpoint を公開する。

| Endpoint | Purpose |
|---|---|
| `GET /v1/health` | adapter health check |
| `POST /v1/evaluate` | artifact / trace / rule_results から DecisionPacket を生成 |
| `POST /v1/review/items` | Human Review Queue に review item を追加 |
| `GET /v1/decisions/{decision_id}` | DecisionPacket 取得 |
| `GET /v1/state-vectors/{run_id}` | StateVector 取得 |
| `GET /v1/audit/{run_id}` | audit events export |

ローカル contract 確認:

```bash
curl http://127.0.0.1:8080/v1/health
```

---

## 2. Shadow Mode Operation

Shadow mode records gate decisions without blocking the workflow. Use this for 2-4 weeks before enabling enforce mode.

### 2.1 Enable Shadow Mode

In `config/gate-config.yaml`:
```yaml
state_space_gate:
  enabled: true
  mode: shadow  # Records decisions, does not block
```

### 2.2 Shadow Mode Metrics to Monitor

| Metric | Target | Check Method |
|--------|--------|--------------|
| State vector coverage | 95%+ | Query `state_vectors` table count vs. run count |
| Audit completeness | 100% | Query `audit_events` for missing `trace_id` |
| Raw payload mis-storage | 0 | Data protection report check |
| Taboo recall estimate | 0.90+ | Run offline eval on taboo dataset |
| False escalation rate | 15% max | Replay accepted golden set |

### 2.3 Shadow Mode Dashboard Queries

```sql
-- Coverage by artifact type
SELECT context_json->>'artifact_type', COUNT(*) 
FROM state_vectors 
GROUP BY context_json->>'artifact_type';

-- Decision distribution
SELECT state, COUNT(*) 
FROM gate_decisions 
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY state;

-- Top blocking reasons
SELECT reasons_json->>'top_factor', COUNT(*) 
FROM gate_decisions 
WHERE state = 'block'
GROUP BY reasons_json->>'top_factor'
ORDER BY COUNT(*) DESC LIMIT 10;

-- Review queue backlog
SELECT severity, COUNT(*) 
FROM human_reviews 
WHERE decision IS NULL
GROUP BY severity;
```

### 2.4 Shadow Mode Exit Criteria

Before transitioning to enforce mode, verify:

- [ ] 95%+ state vector coverage achieved
- [ ] Audit completeness verified (100% have trace_id, threshold_version)
- [ ] No raw payload mis-storage incidents
- [ ] Taboo recall 0.90+ on curated dataset
- [ ] Accept/reject separation AUC 0.85+ or PR-AUC 0.80+
- [ ] False escalation rate 15% or below
- [ ] Review queue latency within SLA targets

---

## 3. Enforce Mode Transition

### 3.1 Warn/Hold Enforce

Enable self-correction and human review without full blocking:

```yaml
state_space_gate:
  enabled: true
  mode: enforce_warn_hold  # Enables self-correction and review queue
  thresholds:
    bootstrap:
      taboo_warn: 0.80
      taboo_block: 0.88  # Only used for hard overrides in this mode
```

### 3.2 Block Enforce

Full enforcement with blocking capability. Requires all readiness gates passed:

```yaml
state_space_gate:
  enabled: true
  mode: enforce_block  # Full enforcement
```

**Prerequisites for block enforce:**
- All shadow/warn/hold metrics achieved
- Review queue connected and SLA dashboard active
- Correction writeback verified
- Replay reproducibility 99%+
- Critical miss rate 0%
- Production readiness gates approved (see docs/EVALUATION.md)

---

## 4. Monitoring Dashboards

### 4.1 Key Metrics to Display

| Category | Metrics |
|----------|---------|
| Volume | Runs processed, artifacts evaluated, decisions per hour |
| Quality | Taboo detection rate, false escalation rate, accept/reject separation |
| Latency | Gate evaluation time, review queue latency, decision latency |
| Health | State vector coverage, embedding worker status, DB connection pool |

### 4.2 Alert Thresholds

| Alert | Condition | Severity |
|-------|-----------|----------|
| Coverage Drop | State vector coverage < 90% | High |
| Queue Backlog | Critical reviews pending > 5 for > 15 min | Critical |
| High Miss | High miss rate > 5% | High |
| Critical Miss | Any critical miss detected | Critical |
| False Escalation Spike | False escalation > 20% for 1 hour | Medium |
| Embedding Worker Down | Worker heartbeat missing > 5 min | High |
| DB Connection Exhaustion | Connection pool > 80% used | Medium |

### 4.3 Log Monitoring

Key log patterns to watch:

```
# Successful gate pass
[GATE] run_id=... decision=pass score=0.45 factors=["accept_similarity_high"]

# Warning with self-correction
[GATE] run_id=... decision=warn score=0.72 factors=["taboo_proximity_warn"] correction_loop=1

# Hold for review
[GATE] run_id=... decision=hold score=0.85 factors=["high_privilege_uncertain"] queue_severity=high

# Block
[GATE] run_id=... decision=block score=0.92 factors=["secret_found"] hard_override=true

# Review resolution
[REVIEW] decision_id=... reviewer=... action=approve comment="..."
```

---

## 5. Troubleshooting Common Issues

### 5.1 Low State Vector Coverage

**Symptoms:** Coverage < 95%, missing state vectors for runs

**Causes:**
- Embedding worker not processing
- Harness adapter not emitting events
- Database connection issues

**Resolution:**
```bash
# Check embedding worker status
harness gate config show --scope embedding_worker

# Check recent runs without state vectors
psql -d gatefield -c "
SELECT run_id FROM audit_events 
WHERE event_type = 'run_completed' 
AND run_id NOT IN (SELECT run_id FROM state_vectors)
LIMIT 10;
"

# Verify harness adapter subscription
# Check adapter logs for event processing
```

### 5.2 High False Escalation Rate

**Symptoms:** Accepted golden set triggering hold/block frequently

**Causes:**
- Thresholds too conservative
- Judgment KB not aligned with current quality standards
- Embedding model drift

**Resolution:**
```bash
# Review calibration profile
harness gate config show --scope calibration

# Recalibrate with updated dataset
harness gate calibrate --dataset datasets/updated_golden.jsonl

# Import additional accepted examples
harness gate kb import --axis accepted --file datasets/new_accepted.jsonl
```

### 5.3 Review Queue Backlog

**Symptoms:** Reviews pending beyond SLA, queue growing

**Causes:**
- Insufficient reviewers
- High severity items taking too long
- Reviewer notification delays

**Resolution:**
```bash
# Check queue stats
harness gate review take --severity critical  # Check if items available

# Query backlog by severity
psql -d gatefield -c "
SELECT severity, COUNT(*), MIN(created_at) as oldest
FROM human_reviews WHERE decision IS NULL
GROUP BY severity;
"

# Escalate oldest items
# Contact on-call reviewer for critical/high backlog
```

### 5.4 Embedding Quality Issues

**Symptoms:** Poor similarity scores, unexpected decisions

**Causes:**
- Embedding model version mismatch
- Corpus contamination
- Dimension mismatch
- Runtime backend mismatch
- Reranker disabled unexpectedly

**Resolution:**
```bash
# Check embedding model config
grep "semantic_embedding" config/gate-config.yaml

# Check selected runtime / vector backend / reranker
grep -E "runtime|reranker|vector_store|model|dimensions" config/gate-config.yaml

# Verify embedding dimensions match
psql -d gatefield -c "
SELECT model, dims, COUNT(*) FROM judgment_embeddings 
WHERE valid_to IS NULL GROUP BY model, dims;
"

# Re-embed if model changed
# Use dual-write period for migration
```

For Qdrant-backed deployments, also verify collection vector size and payload indexes:

```bash
# Example when using Qdrant local API
curl http://localhost:6333/collections/gatefield_judgments
```

### 5.5 Threshold Drift

**Symptoms:** Decisions inconsistent with historical patterns

**Causes:**
- Model/engine changes affecting scores
- Judgment KB changes without threshold recalibration
- Production environment changes

**Resolution:**
```bash
# Check threshold version
harness gate config show --scope thresholds

# Replay historical runs to detect drift
harness gate replay --run-id HISTORICAL_RUN --threshold-version v1

# Compare decision distributions
psql -d gatefield -c "
SELECT threshold_version, state, COUNT(*) 
FROM gate_decisions 
GROUP BY threshold_version, state;
"
```

---

## 6. SLA Response Procedures

### 6.1 SLA Targets

| Severity | ACK Target | Decision Target | Timeout Action |
|----------|------------|-----------------|----------------|
| Critical | 15 minutes | 60 minutes | Fail closed, escalate |
| High | 60 minutes | 4 hours | Fail closed, escalate |
| Medium | Same business day | Next business day | Queue remains |
| Low | No ACK required | Backlog | No timeout |

### 6.2 Critical Response Procedure

1. **ACK (within 15 min):**
   - Reviewer takes item: `harness gate review take --severity critical --reviewer YOUR_NAME`
   - Read trace and explanation: `harness gate explain --decision-id DEC_ID`
   - Check top factors and exemplars

2. **Decision (within 60 min):**
   - Approve/Reject/Recalibrate: `harness gate review resolve --decision-id DEC_ID --action approve --comment "..."`
   - If reject, specify correction type

3. **Timeout Escalation:**
   - If ACK not received in 15 min: page on-call backup
   - If decision not received in 60 min: fail closed (block), notify stakeholder

### 6.3 High Response Procedure

Similar to Critical but with 1 hour ACK and 4 hour decision window.

---

## 7. Incident Response

### 7.1 Secret Leak Detected

**Immediate Actions:**
1. Block the run immediately (hard override triggers automatically)
2. Identify affected artifacts and runs:
```sql
SELECT run_id, artifact_id FROM state_vectors 
WHERE rule_json->>'secret' > 0 
AND created_at > NOW() - INTERVAL '24 hours';
```
3. Notify security team
4. Revoke exposed credentials
5. Mark affected datasets for re-validation

**Post-Incident:**
- Add to taboo corpus
- Update judgment logs with incident details
- Review calibration for similar patterns

### 7.2 PII Mis-storage Detected

**Immediate Actions:**
1. Identify affected records:
```sql
SELECT * FROM audit_events 
WHERE retention_class = 'pii_sensitive' 
AND created_at > NOW() - INTERVAL '7 days';
```
2. Execute purge:
```sql
-- Use purge procedure (must be pre-verified)
DELETE FROM audit_events WHERE event_id IN (...);
-- Invalidate affected embeddings
UPDATE judgment_embeddings SET valid_to = NOW() WHERE doc_id IN (...);
```
3. Notify security/legal
4. Annotate audit trail with purge reason

**Post-Incident:**
- Review redaction policy
- Update classification rules
- Re-validate dataset versions affected

### 7.3 Gate Decision Dispute

**Procedure:**
1. Replay the decision: `harness gate replay --run-id RUN_ID --threshold-version VERSION`
2. Compare with historical similar cases
3. If discrepancy:
   - Reviewer can recalibrate: `harness gate review resolve --action recalibrate`
   - Add to judgment log: `harness gate kb promote --from-run RUN_ID --axis judgment_log`
4. Document in audit trail

---

## 8. Maintenance Procedures

### 8.1 Embedding Model Migration

When upgrading embedding model:

```yaml
# Dual-write configuration
state_space_gate:
  semantic_embedding:
    provider: local
    runtime: llama.cpp
    model: BAAI/bge-m3  # New production model
    dimensions: 1024
    legacy_model: local-hash-embedding-v1  # Old fallback model during migration
    legacy_dimensions: 1536
    dual_write_days: 14

  reranker:
    enabled: true
    model: BAAI/bge-reranker-v2-m3

  vector_store:
    backend: pgvector
    collection: gatefield_judgments
```

**Steps:**
1. Enable dual-write period for old and new embeddings.
2. Start local runtime profile (`llama.cpp` by default) and verify BGE-M3 health.
3. Create or migrate pgvector storage with `dense_dimensions: 1024`; if using the optional Qdrant local profile, create the Qdrant collection with the same dimensions.
4. Re-embed judgment documents with BGE-M3.
5. Enable bge-reranker-v2-m3 for top-k reranking.
6. Recalibrate thresholds with new embeddings and reranker scores.
7. Validate with acceptance dataset and offline eval.
8. Disable legacy model after replay reproducibility reaches 99%+ and no critical miss is observed.

### 8.2 Knowledge Base Update

```bash
# Import new judgment documents
harness gate kb import --axis taboo --file datasets/new_taboo.jsonl

# Promote reviewed run to judgment log
harness gate kb promote --from-run RUN_ID --axis judgment_log

# Deprecate outdated documents
psql -d gatefield -c "
UPDATE judgment_documents SET status = 'deprecated' 
WHERE doc_id = '...' AND version = 1;
"
```

### 8.3 Threshold Recalibration

```bash
# Run calibration with updated dataset
harness gate calibrate --dataset datasets/calibration_v2.jsonl

# Validate with acceptance dataset before applying
harness gate replay --run-id SAMPLE_RUN --threshold-version NEW_VERSION

# Apply if validation passes
```

### 8.4 Database Maintenance

```sql
-- Vacuum and analyze
VACUUM ANALYZE judgment_embeddings;
VACUUM ANALYZE state_vectors;

-- Rebuild HNSW index if performance degraded
DROP INDEX idx_embed_hnsw;
CREATE INDEX idx_embed_hnsw ON judgment_embeddings 
USING hnsw (embedding vector_cosine_ops);

-- Retention cleanup (per policy)
DELETE FROM audit_events 
WHERE created_at < NOW() - INTERVAL '365 days' 
AND retention_class = 'audit';
```

---

## 9. CLI Reference

### Decision Operations

```bash
# Dry-run evaluation (shadow mode testing)
harness gate dry-run --run-id RUN123

# Score an artifact
harness gate score --run-id RUN123 --artifact ./patch.diff --json

# Explain a decision
harness gate explain --decision-id DEC456
```

### Review Operations

```bash
# Take a review item by severity
harness gate review take --severity critical --reviewer reviewer_name

# Resolve a review
harness gate review resolve --decision-id DEC456 \
    --action approve \
    --comment "Within acceptable boundaries"

# Available actions: approve, reject, recalibrate, request_correction
```

### Knowledge Base Operations

```bash
# Import judgment documents
harness gate kb import --axis taboo --file taboo_cases.yaml

# Promote run result to judgment log
harness gate kb promote --from-run RUN123 --axis judgment_log
```

### Calibration and Replay

```bash
# Run calibration
harness gate calibrate --dataset datasets/gates_v1.jsonl

# Replay a run with specific threshold version
harness gate replay --run-id RUN123 --threshold-version v2

# Replay from checkpoint
harness gate replay --run-id RUN123 --from-checkpoint CP789
```

### Configuration

```bash
# Validate configuration
harness gate config validate -f gate-config.yaml

# Show configuration for scope
harness gate config show --scope service-a
```

---

## 10. Exit Codes

| Code | Name | Description |
|------|------|-------------|
| 0 | SUCCESS | Operation completed successfully |
| 1 | VALIDATION_ERROR | Input validation failed |
| 2 | GATE_BLOCK | Gate decision is block |
| 3 | GATE_HOLD | Gate decision is hold |
| 4 | CONFIG_ERROR | Configuration error |
| 5 | INFRA_ERROR | Infrastructure error (DB, API) |

---

## 11. Contact and Escalation

| Issue Type | Primary Contact | Escalation |
|------------|-----------------|------------|
| Critical review timeout | On-call reviewer | Security team lead |
| System availability | Platform team | SRE on-call |
| Data protection incident | Security team | Legal/Compliance |
| Threshold calibration | ML team | Product owner |
| Harness integration | Platform team | Harness vendor support |

---

## 12. Related Documents

- `docs/requirements.md` - Full requirements specification
- `docs/architecture.md` - Architecture design
- `docs/EVALUATION.md` - Acceptance criteria and readiness gates
- `docs/security.md` - Security design and incident response
- `docs/BIRDEYE.md` - Quick architecture summary
- `config/gate-config.yaml` - Configuration reference
