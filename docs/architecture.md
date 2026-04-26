# Architecture Overview

## Control Flow

```
Agent Run Start
    → Trace and Artifact Capture
    → Static Gates (hard fail → Block)
    → State Encoder
    → Retrieve Judgment KB (constitution/taboo/accepted/rejected/logs)
    → Scorers (alignment/taboo/drift/anomaly/uncertainty)
    → Dynamic Boundary
        → pass: Continue Workflow
        → warn: Self-Correction → loop
        → hold: Human Review Queue
        → block: Correction Action
    → Audit Log
```

## Data Model

### Core Tables (pgvector)

| Table | Purpose |
|-------|---------|
| `judgment_documents` | 設計憲法、禁忌、採用例、却下例、判断ログ本文 |
| `judgment_embeddings` | Embeddings with versioning (append-only) |
| `state_vectors` | Run単位の複合状態ベクトル |
| `static_gate_results` | 静的ゲート結果 (immutable) |
| `gate_decisions` | 判定結果とアクション |
| `human_reviews` | 人間レビューとcorrection |
| `calibration_profiles` | Team/repo単位の閾値設定 |
| `audit_events` | OTelマッピング対象の監査ログ |

### State Vector Components

```json
{
  "run_id": "uuid",
  "artifact_id": "uuid",
  "semantic": {"model": "...", "dims": 1536, "vector_ref": "..."},
  "rule_violation": {"secret": 0, "sast_high": 1},
  "test_evidence": {"unit_pass_rate": 0.97},
  "risk": {"prod_write": 0, "pii_level": 1},
  "historical_decision": {"accept_sim": 0.84, "reject_sim": 0.31},
  "uncertainty": {"judge_std": 0.08, "self_confidence": 0.74},
  "context": {"repo": "...", "artifact_type": "code_patch"},
  "trajectory": {"delta_semantic": 0.07, "tool_calls": 9}
}
```

## Scorers

| Scorer | Formula | Purpose |
|--------|---------|---------|
| Constitution alignment | `cosine(semantic, constitution_centroid)` | 設計原則整合性 |
| Taboo proximity | `max cosine(semantic, taboo_topk)` | 禁忌接近度 |
| Positive similarity | `max cosine(semantic, accepted_topk)` | 採用例類似度 |
| Negative similarity | `max cosine(semantic, rejected_topk)` | 却下例類似度 |
| Drift score | `1 - cosine(current, ewma_accepted)` | 軌道逸脱 |
| Anomaly score | Isolation Forest / Mahalanobis | 分布外検出 |
| Uncertainty score | evaluator variance + self uncertainty | 判定信頼度 |

## Harness Contract

| Contract | Required | Description |
|----------|----------|-------------|
| Run lifecycle events | P0 | run_started, step_started, tool_call_requested, artifact_emitted... |
| Pause / resume | P0 | hold時に停止、review後にcheckpointから再開 |
| Tool policy hook | P0 | tool call前のdeny/hold/allow |
| Artifact snapshot | P0 | hash, diff, step, commit取得 |
| Static gate result ingest | P0 | CI/scanner結果取り込み |
| Trace correlation | P0 | trace_id/span_id/run_id付与 |

## State Transitions

| Current | Condition | Next | Action |
|---------|-----------|------|--------|
| any | static hard fail / secret / tool deny | block | stop run and create correction action |
| any | high privilege + risk/uncertainty/taboo warning | hold | pause run and enqueue review |
| pass | composite score exceeds warn threshold | warn | self-correct up to 2 times |
| warn | self-correction succeeds | pass | resume workflow |
| warn | self-correction fails twice or repeats | hold | enqueue review |
| hold | reviewer approves | pass | resume from checkpoint |
| hold | reviewer rejects or SLA expires | block | fail closed |
| pass | late hard fail arrives | block | invalidate affected artifact |

Priority order: hard override > tool policy > data protection policy > reviewer decision > composite score > self-correction result.

## Product Readiness Gates

| Gate | Requirement |
|------|-------------|
| MVP start | harness contract reviewed, data protection approved, dataset label policy defined, reviewer owners assigned |
| Shadow mode | 95%+ state vector coverage, audit completeness, no raw payload mis-storage |
| Warn/hold enforce | review queue connected, SLA dashboard active, correction writeback verified |
| Block enforce | operational KPI met, replay reproducibility 99%+, critical miss rate 0%, evidence complete for formal initial decisions |

## Data Protection Boundary

Raw prompt and raw tool payload storage is disabled by default. Payloads must be classified before persistence; unknown classification is treated as `restricted`. Restricted and PII-sensitive payloads use redacted references, content hashes, and scoped metadata only.
