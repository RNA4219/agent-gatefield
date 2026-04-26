# Bird's Eye View - Agent Gatefield

A one-page architecture summary for quick understanding of the state space gate system.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AGENT HARNESS (Control Plane)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Agent    │  │ Tool     │  │ Model    │  │ Trace    │  │ Check-   │      │
│  │ Loop     │──│ Routing  │──│ Calls    │──│ Export   │──│ pointer  │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │ Events (run_started, tool_call, ...)
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STATE SPACE GATE SYSTEM                              │
│                                                                              │
│  ┌─────────────┐                                                            │
│  │ Harness     │◄─── Subscribe to lifecycle events                          │
│  │ Adapter     │     (P0 contract)                                          │
│  └──────┬──────┘                                                            │
│         │                                                                    │
│         ▼                                                                    │
│  ┌─────────────┐     ┌─────────────────┐                                    │
│  │ Static      │────▶│ Hard Override   │──▶ BLOCK (if secret, SAST, deny)  │
│  │ Gates       │     │ Rules           │                                    │
│  │ (lint, SAST,│     └─────────────────┘                                    │
│  │  secret...) │                                                            │
│  └──────┬──────┘                                                            │
│         │ pass                                                               │
│         ▼                                                                    │
│  ┌─────────────┐                                                            │
│  │ State       │◄─── Encode artifact, trace, rules, risk, uncertainty       │
│  │ Encoder     │                                                            │
│  └──────┬──────┘                                                            │
│         │                                                                    │
│         ▼                                                                    │
│  ┌─────────────┐     ┌─────────────────┐                                    │
│  │ Retrieve    │────▶│ Judgment KB     │                                    │
│  │ from KB     │     │ (pgvector)      │                                    │
│  └──────┬──────┘     │  - Constitution │                                    │
│         │            │  - Taboo        │                                    │
│         │            │  - Accepted     │                                    │
│         │            │  - Rejected     │                                    │
│         │            │  - Judgment Log │                                    │
│         ▼            └─────────────────┘                                    │
│  ┌─────────────┐                                                            │
│  │ Scorers     │◄─── Alignment, Taboo, Accept, Reject, Drift, Anomaly,      │
│  │ (weighted)  │     Uncertainty                                           │
│  └──────┬──────┘                                                            │
│         │                                                                    │
│         ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │              DYNAMIC BOUNDARY (Decision Engine)          │                │
│  │                                                          │                │
│  │  composite_score = Σ(weight_i × scorer_i)               │                │
│  │                                                          │                │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐        │                │
│  │  │  PASS  │  │  WARN  │  │  HOLD  │  │ BLOCK  │        │                │
│  │  └────┬───┘  └────┬───┘  └────┬───┘  └────┬───┘        │                │
│  │       │          │          │          │                │                │
│  │       ▼          ▼          ▼          ▼                │                │
│  │  Continue   Self-Correct  Review    Correction          │                │
│  │  Workflow   (max 2x)      Queue     Action              │                │
│  └─────────────────────────────────────────────────────────┘                │
│                                                                              │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HUMAN REVIEW QUEUE                                 │
│                                                                              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                    │
│  │ Dashboard   │────▶│ Reviewer    │────▶│ Correction  │                    │
│  │ (SLA,       │     │ Decision    │     │ Writeback   │                    │
│  │  alerts)    │     │             │     │             │                    │
│  └─────────────┘     └──────┬──────┘     └──────┬──────┘                    │
│                             │                   │                            │
│                             ▼                   ▼                            │
│                      approve/reject     Update KB + Calibration              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AUDIT & STORAGE                                 │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PostgreSQL + pgvector                                                │   │
│  │                                                                      │   │
│  │ Tables:                                                              │   │
│  │  - judgment_documents    (KB content)                               │   │
│  │  - judgment_embeddings   (vectors, versioned)                       │   │
│  │  - state_vectors         (per-run composite state)                  │   │
│  │  - static_gate_results   (immutable)                                │   │
│  │  - gate_decisions        (pass/warn/hold/block)                     │   │
│  │  - human_reviews         (reviewer actions)                         │   │
│  │  - calibration_profiles  (thresholds per scope)                     │   │
│  │  - audit_events          (OTel-compatible)                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Export: OTLP (OpenTelemetry), JSONL                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Flows

### Gate Decision Flow

```
1. Run starts → Harness emits event
2. Adapter captures trace + artifact
3. Static gates run (lint, SAST, secret scan, tool policy)
   └── Hard fail? → BLOCK (stop, explain)
4. State Encoder builds composite vector
   └── semantic + rule_violation + test_evidence + risk + uncertainty + context + trajectory
5. Retrieve similar items from Judgment KB (pgvector)
6. Scorers compute: alignment, taboo proximity, accept/reject similarity, drift, anomaly, uncertainty
7. Apply hard overrides (secret found, prod_write+taboo, high_privilege+uncertain)
8. Composite decision:
   └── PASS → Continue workflow
   └── WARN → Self-correct (max 2 loops), then HOLD if unresolved
   └── HOLD → Enqueue for human review
   └── BLOCK → Correction action, audit log
9. Write audit event (trace_id, span_id, decision, reasons)
```

### Human Review Flow

```
1. Decision HOLD → ReviewQueue.enqueue(item)
2. Dashboard shows pending items with severity, factors, exemplars
3. Reviewer takes item (ACK within SLA)
4. Reviewer reads explanation + trace context
5. Reviewer resolves:
   └── APPROVE → Resume from checkpoint
   └── REJECT → Create correction action
   └── RECALIBRATE → Update weights/thresholds
   └── REQUEST_CORRECTION → Trigger artifact/process/prompt correction
6. Correction writeback to Judgment KB + Calibration profile
7. Audit trail updated
```

### Correction Flow

```
1. Artifact correction: regenerate, sanitize dangerous output, add tests
2. Process correction: add scans, restrict tools, rollback checkpoint, handoff to specialist
3. Prompt correction: update system prompt, few-shot examples, tool schema, retrieval filters
4. Re-evaluate with updated state
```

---

## Data Model Summary

| Table | Key Fields | Purpose |
|-------|------------|---------|
| `judgment_documents` | `doc_id`, `axis_type`, `text`, `version`, `status` | KB content (constitution, taboo, accepted, rejected, logs) |
| `judgment_embeddings` | `embed_id`, `doc_id`, `embedding` (vector), `valid_from/to` | Versioned embeddings (append-only) |
| `state_vectors` | `run_id`, `semantic_embedding`, `*_json` fields | Composite state per run |
| `static_gate_results` | `gate_name`, `severity`, `status`, `evidence_ref` | Immutable gate results |
| `gate_decisions` | `state`, `composite_score`, `reasons_json`, `threshold_version` | Decision record |
| `human_reviews` | `decision`, `comment`, `correction_json` | Reviewer actions |
| `calibration_profiles` | `scope`, `weights_json`, `*_thresholds` | Per-scope settings |
| `audit_events` | `trace_id`, `span_id`, `event_type`, `retention_class` | OTel-compatible audit |

---

## State Vector Components

```json
{
  "run_id": "uuid",
  "artifact_id": "uuid",
  "semantic": {"provider": "local", "model": "local-hash-embedding-v1", "dims": 1536, "vector_ref": "..."},
  "rule_violation": {"secret": 0, "sast_high": 1},
  "test_evidence": {"unit_pass_rate": 0.97},
  "risk": {"prod_write": 0, "pii_level": 1},
  "historical_decision": {"accept_sim": 0.84, "reject_sim": 0.31},
  "uncertainty": {"judge_std": 0.08, "self_confidence": 0.74},
  "context": {"repo": "...", "artifact_type": "code_patch"},
  "trajectory": {"delta_semantic": 0.07, "tool_calls": 9}
}
```

---

## Scorers and Weights (Default)

| Scorer | Weight | Formula | Purpose |
|--------|--------|---------|---------|
| Constitution alignment | 0.20 | `cosine(semantic, constitution_centroid)` | Design principle fit |
| Taboo proximity | 0.30 | `max cosine(semantic, taboo_topk)` | Forbidden approach |
| Accept similarity | 0.10 | `max cosine(semantic, accepted_topk)` | Good pattern match |
| Reject similarity | 0.15 | `max cosine(semantic, rejected_topk)` | Bad pattern match |
| Drift | 0.10 | `1 - cosine(current, ewma_accepted)` | Trajectory deviation |
| Anomaly | 0.10 | Isolation Forest / Mahalanobis | Outlier detection |
| Uncertainty | 0.05 | evaluator variance + self uncertainty | Confidence signal |

---

## State Transitions

| Current | Condition | Next | Action |
|---------|-----------|------|--------|
| any | static hard fail / secret / tool deny | block | stop run, create correction |
| any | high privilege + risk/uncertainty/taboo warning | hold | pause, enqueue review |
| pass | composite score exceeds warn threshold | warn | self-correct (max 2x) |
| warn | self-correction succeeds | pass | resume workflow |
| warn | self-correction fails twice | hold | enqueue review |
| hold | reviewer approves | pass | resume from checkpoint |
| hold | reviewer rejects / SLA expires | block | fail closed |

**Priority:** hard override > tool policy > data protection policy > reviewer decision > composite score > self-correction result

---

## Harness Contract (P0)

| Contract | Required | Description |
|----------|----------|-------------|
| Run lifecycle events | P0 | `run_started`, `step_started`, `tool_call_requested`, `artifact_emitted` |
| Pause / resume | P0 | Pause on hold, resume from checkpoint after review |
| Tool policy hook | P0 | Pre-tool-call deny/hold/allow |
| Artifact snapshot | P0 | hash, diff, step, commit/branch |
| Static gate ingest | P0 | CI/scanner results import |
| Trace correlation | P0 | trace_id/span_id/run_id correlation |

---

## Key Interfaces

### CLI (`cli/gate_cli.py`)

```bash
harness gate dry-run --run-id RUN_ID
harness gate score --run-id RUN_ID --artifact PATH
harness gate explain --decision-id DEC_ID
harness gate review take --severity critical
harness gate review resolve --decision-id DEC_ID --action approve
harness gate kb import --axis taboo --file FILE
harness gate calibrate --dataset FILE
harness gate replay --run-id RUN_ID --threshold-version V
harness gate config validate -f gate-config.yaml
```

### Adapter Interface (`src/adapters/harness.py`)

```python
class HarnessAdapter(ABC):
    def subscribe_events() -> None        # P0
    def pause_run(run_id) -> checkpoint   # P0
    def resume_run(run_id, checkpoint)    # P0
    def check_tool_policy(tool_call)      # P0: deny/hold/allow
    def get_artifact_snapshot(run_id)     # P0
    def ingest_static_gate_result(result) # P0
    def get_trace_context(run_id)         # P0
```

### Decision Engine (`src/core/engine.py`)

```python
class DecisionEngine:
    def evaluate(state_vector) -> dict:
        # Returns: {'decision', 'composite_score', 'factors', 'exemplar_refs', 'action'}
    def apply_hard_overrides(state_vector) -> str | None:
        # Returns: 'block' if override triggers
```

---

## Product Readiness Gates

| Gate | Requirement |
|------|-------------|
| MVP start | Harness contract reviewed, data protection approved, reviewer owners assigned |
| Shadow mode | 95%+ state vector coverage, audit complete, no raw payload mis-storage |
| Warn/hold enforce | Review queue connected, SLA dashboard active, correction writeback verified |
| Block enforce | Operational KPI met, replay reproducibility 99%+, critical miss rate 0%, all open decisions resolved |

---

## Operational KPIs

| KPI | Target |
|-----|--------|
| Review load reduction | 30%+ |
| Critical miss rate | 0% |
| High miss rate | 5% max |
| False escalation rate | 15% max |
| Explanation usefulness | 80%+ |
| Replay reproducibility | 99%+ |

---

## Data Protection Summary

| Data Class | Raw Storage | Embedding |
|------------|-------------|-----------|
| public | allowed after scan | allowed |
| internal | allowed after redaction | allowed |
| confidential | redacted reference only | conditional |
| pii-sensitive | prohibited | prohibited unless redacted |
| restricted | prohibited | prohibited |

**Default:** Unknown classification = restricted (fail closed)

**Key Rules:**
- Raw prompt/artifact storage disabled by default
- Redaction required before persistence
- External managed services require: data residency, retention, purge API, audit export review

---

## Quick Reference

### File Locations

| Component | Path |
|-----------|------|
| Config template | `config/gate-config.yaml` |
| DB schema | `src/vector_store/schema.sql` |
| Decision engine | `src/core/engine.py` |
| State encoder | `src/encoder/state_encoder.py` |
| Review queue | `src/review/queue.py` |
| Harness adapters | `src/adapters/harness.py` |
| CLI | `cli/gate_cli.py` |
| Scorers | `src/scorers/` |
| Datasets | `datasets/` |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Validation error |
| 2 | Gate block |
| 3 | Gate hold |
| 4 | Config error |
| 5 | Infrastructure error |

### Key Thresholds (Bootstrap)

| Signal | Warn | Block |
|--------|------|-------|
| Taboo proximity | 0.80 | 0.88 |
| Anomaly percentile | P95 | P99 |
| Judge stddev | 0.15 | 0.25 |

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| `docs/requirements.md` | Full requirements specification |
| `docs/architecture.md` | Detailed architecture design |
| `docs/EVALUATION.md` | Acceptance criteria, readiness gates |
| `docs/security.md` | OWASP LLM Top 10 countermeasures |
| `docs/RUNBOOK.md` | Operational procedures |
| `README.md` | Project overview |

---

## One-Liner Summary

**Static gates handle deterministic checks; state space gates handle context-dependent judgment; humans review only boundary violations.**
