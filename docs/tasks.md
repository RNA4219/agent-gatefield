# Implementation Tasks

## P0 Tasks (MVP Essential)

| Task | Est. Effort | Skills Required |
|------|-------------|-----------------|
| 既存ハーネス連携契約の確定 | 2-4 person-days | Platform, Backend |
| データ保護 / redaction / retention policy 確定 | 3-5 person-days | Security, Legal, Platform |
| Trace / audit event schema 定義 | 3-5 person-days | Platform, Observability |
| Static gate adapters 実装 | 5-8 person-days | CI/CD, AppSec |
| Judgment KB スキーマと versioning | 4-6 person-days | Backend, Data Modeling |
| Embedding worker / re-embed job | 3-5 person-days | Backend, ML Infra |
| pgvector 導入と索引設計 | 4-7 person-days | DB, Backend |
| State encoder 実装 | 5-8 person-days | Backend, ML |
| 判定器群実装 | 6-10 person-days | ML, Backend |
| Composite decision engine | 4-6 person-days | Backend |

**MVP Total**: ~58-103 person-days (assuming existing harness has trace/checkpoint/policy hook)

If the existing harness lacks trace, checkpoint, or policy hook support, add 10-20 person-days before enforce planning.

## P1 Tasks

| Task | Est. Effort | Skills Required |
|------|-------------|-----------------|
| Explanation API / dashboard | 6-10 person-days | Frontend, Backend |
| Human review queue / corrections | 4-6 person-days | Backend, Ops |
| Calibration pipeline / offline eval | 5-8 person-days | ML, QA |
| Alert routing / webhook / pager | 2-4 person-days | SRE |
| Replay / resume / rollback hooks | 3-5 person-days | Platform |
| 評価データセット作成 / ラベル裁定 | 5-10 person-days | QA, Security, Repo Owner |
| 運用 KPI dashboard / baseline 計測 | 3-6 person-days | Ops, Data, Frontend |
| 参考文献リスト化 / 承認版整形 | 1-2 person-days | Product, Security |

## P2 Tasks

| Task | Est. Effort | Skills Required |
|------|-------------|-----------------|
| YAML config / CLI / runbook | 3-5 person-days | DevEx |
| Long-term active learning loop | 8-15 person-days | ML, Data, Ops |

## Milestones

| Phase | Target | Success Criteria |
|-------|--------|-----------------|
| Short-term | Trace収集、静的ゲート統合、shadow scoring | 95%+ runs with trace + state vector |
| Medium-term | Review queue, composite score, calibration | warn/hold/block in review workflow |
| Long-term | Active learning, per-team policy, auto-recalibration | Corrections reflected to gate boundaries |

## Test Layers

| Layer | Content | Pass Condition |
|-------|---------|---------------|
| Unit | encoder, distance calc, threshold resolver | deterministic |
| Contract | trace schema, decision packet, dashboard API | backward compatible |
| Integration | CI → static gates → state scoring → review queue → audit | end-to-end |
| Replay | Past traces reproducibility | threshold version explainable |
| Offline eval | AUC, recall, precision on datasets | acceptance criteria met |
| Online shadow | Production mirror traffic | KPI met before enforce |
| Security | prompt injection, tool misuse, secret leakage | block/hold as expected |
| Data protection | redaction, classification, retention, purge | no raw payload mis-storage |
| Ops KPI | queue latency, decision latency, review load reduction | MVP targets met |
