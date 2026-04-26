# Changelog

## 2026-04-27

### Changed

- `src/core/types.py` / `src/core/engine.py` / `src/core/hard_overrides.py`: DecisionPacket に `artifact_ref` と `diff_hash` を保持し、agent-state-gate 側の approval binding と整合させた
- `src/api/http_app.py`: fallback semantic vector を `BAAI/bge-m3` / 1024d に同期
- `docs/spec/DATA_TYPES_SPEC.md` / `tests/test_state_gate_alignment.py` / `tests/test_schema_contract.py`: DecisionPacket と state vector contract の回帰検証を更新

### Verification

- `tests/test_state_gate_alignment.py`, `tests/test_schema_contract.py`, `tests/test_engine.py` が pass
- `config/gate-config.yaml` の validate が pass

## 2026-04-26

### Changed

- 仕様書検収を実施し、`docs/requirements.md` の `Production Requirements Frozen` と `docs/spec/` 配下の仕様群の整合を確認。
- `config/gate-config.yaml` の cost guardrail キーを `cost_guardrails` に統一し、`docs/spec/DATA_TYPES_SPEC.md` の設定スキーマと一致させた。
- `docs/spec/PERFORMANCE_SPEC.md` の scalability test matrix から `TBD` を削除し、正式な acceptance P99 条件へ置き換えた。
- `docs/spec/ACCEPTANCE_CRITERIA_SPEC.md` の block enforce 検収手順を、`data protection approved` から `formal initial decisions` の証跡完備へ更新。
- `docs/spec/DATA_TYPES_SPEC.md` の readiness gate フィールドを `formal_initial_decisions_evidence` に更新し、要件定義の正式初期値方針に揃えた。
- `docs/spec/*.md` の Markdown 表区切り行と表セル内の縦棒を修正し、仕様書レビュー時の表崩れを解消。

### Verification

- `Pending`、`unspecified`、`TBD`、`Production Gate Pending`、`MVP Definition Frozen` の残存を仕様書・設定・要件文書に対して検索。
- cost guardrail、readiness gate、performance acceptance matrix の主要不整合を解消。
- `docs/spec/*.md` の表列数を簡易チェックし、不整合がないことを確認。
