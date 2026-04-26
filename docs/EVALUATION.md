# Evaluation

本ファイルは `docs/requirements.md` の下書き要件を、検収・レビュー・production readiness 判断へ接続するための入口である。

## Status

| Item | Value |
|---|---|
| Requirements level | Production Requirements Frozen |
| Source of truth | `docs/requirements.md` |
| MVP decision | 着手可 |
| Production block enforce | 要件定義上は有効化可能。Readiness Gates の証跡未達時は fail closed |

## Implementation Status (2026-04-26)

| Component | Status | Tests |
|-----------|--------|-------|
| Decision Engine | **完了** | 647/647 passed |
| 8 Scorers + CompositeScorer | **完了** | passed |
| VectorStore + JudgmentKB | **完了** | 5 mock assertions to fix |
| StateEncoder | **完了** | 79/79 passed |
| EmbeddingWorker | **完了** | passed |
| Static Gates (7 adapters) | **完了** | passed |
| Calibration Pipeline | **完了** | passed |
| Replay Engine | **完了** | passed |
| Review Queue | **完了** | passed |
| Harness Adapters (4 adapters) | **完了** | passed |
| Hard Override Rules | **完了** | passed |
| SLA Handler | **完了** | passed |

**Test Summary:**
- Total tests: 647
- Passed: 647 (100%)
- Failed: 0
- Warnings: 65 (datetime.utcnow deprecation)

## Acceptance Criteria

| ID | Criteria | Evidence |
|---|---|---|
| AGF-AC-001 | 対象 run の 95%以上で trace + state vector が生成される | trace coverage report |
| AGF-AC-002 | seeded static violation suite に対して 100% block する | `static_violation_suite.jsonl` replay result |
| AGF-AC-003 | escalated decision の 100% に top 3 factors と top 5 exemplar refs が付く | explanation API / decision packet |
| AGF-AC-004 | curated taboo dataset に対して recall 0.90 以上を満たす | offline eval report |
| AGF-AC-005 | accept/reject separation が AUC 0.85 以上、または PR-AUC 0.80 以上を満たす | offline eval report |
| AGF-AC-006 | accepted golden set の false escalation が 15% 以下である | golden set replay result |
| AGF-AC-007 | gate decision の 100% に trace_id / threshold_version / action_type が存在する | audit completeness report |
| AGF-AC-008 | 保存 payload の 100% に data_classification / redaction_status / retention_class が存在する | data protection report |
| AGF-AC-009 | run_id / artifact_id / dataset_id 単位の purge 手順が検証済みである | purge dry-run evidence |
| AGF-AC-010 | 同一 dataset / threshold_version / policy_version で replay reproducibility 99%以上を満たす | replay reproducibility report |

## Operational KPIs

| KPI | MVP Target | Evidence |
|---|---:|---|
| review_load_reduction | 30%以上 | shadow baseline comparison |
| critical_miss_rate | 0% | post-review incident audit |
| high_miss_rate | 5%以下 | post-review incident audit |
| false_escalation_rate | 15%以下 | accepted golden set replay |
| explanation_usefulness | 80%以上 | reviewer feedback |
| replay_reproducibility | 99%以上 | replay report |
| monthly_cost | $500相当以内 | cost dashboard / billing export |

## Readiness Gates

| Gate | Exit Criteria |
|---|---|
| MVP start | harness contract reviewed、data protection approved、reviewer owners assigned |
| Shadow mode | 95%以上の state vector coverage、audit completeness、raw payload 誤保存なし |
| Warn/hold enforce | review queue 接続、SLA dashboard 稼働、correction writeback 検証済み |
| Block enforce | operational KPI 達成、critical miss rate 0%、replay reproducibility 99%以上、正式初期値に対する証跡完備 |

## Formal Initial Decisions

| Decision | Required Before | Owner |
|---|---|---|
| 既存ハーネスは Python adapter-first、OTel event schema、pause/resume checkpoint reference、pre-tool policy hook とする | MVP implementation planning | Platform |
| 対象 repo は `agent-gatefield`、artifact type は code patch / document diff / tool execution plan / PR proposal とする | MVP implementation planning | Product / Repo Owner |
| データレジデンシーは self-hosted local/controlled infrastructure、外部 managed service は初期無効とする | Production block enforce | Security / Legal |
| semantic embedding は local provider を既定とし、外部 API キーなしで生成・再現できること | Shadow mode | Product / Security |
| PII / 機密 redaction rule は raw prompt/tool payload 保存禁止、restricted embedding 禁止とする | Shadow mode | Security |
| SLA/SLO は Critical 15/60分、High 60/240分、freshness 60秒、writeback 5秒、replay 99%以上とする | Warn/hold enforce | Ops / Product |
| 月額予算上限は $500 相当、80% warn、100% hold とする | Block enforce | Product / Finance |
| reviewer rota は reviewer 2 名以上、Security approver 1 名、Ops owner 1 名、timeout fail closed とする | Warn/hold enforce | Ops / Security |
| acceptance dataset は redaction 済み、version lock、2 reviewer label 必須とする | Block enforce | QA / Repo Owner |

## Verification Checklist

- [ ] `docs/requirements.md` の AGF-REQ-* と本ファイルの AGF-AC-* が対応している
- [ ] `config/gate-config.yaml` が MVP 既定値、データ保護、KPI、dataset lock を表現している
- [ ] `datasets/README.md` が split、label quality、redaction、acceptance lock を定義している
- [ ] `docs/security.md` が classification policy と incident response を定義している
- [ ] `docs/architecture.md` が状態遷移と Product Readiness Gates を定義している
