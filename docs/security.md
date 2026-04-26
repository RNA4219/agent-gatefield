# Security Design - OWASP LLM Top 10

本プロジェクトのセキュリティ設計は OWASP 2025 LLM Top 10 を脅威分類として採用。

## 主要リスクと対策

| Risk | Description | Gate Countermeasure |
|------|-------------|---------------------|
| **LLM01** Prompt Injection | 入力がモデルを騙す | input validation, taboo corpus, tool policy, human hold |
| **LLM05** Improper Output Handling | 出力が危険な処理を誘発 | output sanitizer, 高権限ツールhold |
| **LLM06** Excessive Agency | エージェントが過剰権限行使 | static tool policy + risk weighting + high privilege hold |
| **LLM08** Vector/Embedding Weaknesses | embedding/ANNの脆弱性 | metadata filtering, signed KB ingest, dual checks |
| **LLM10** Unbounded Consumption | リソース無制限消費 | budget manager, rate control, loop上限 |

## Layered Safeguards

Anthropic推奨の多層防御:

1. **Input validation**: prompt injection pattern検出
2. **Static gates**: SAST, secret scan, tool policy
3. **State space gates**: taboo proximity, drift, anomaly
4. **Human hold**: 高リスク/高不確実性時の介入
5. **Output handling**: sanitizer, rate limiting

## Hard Overrides

以下は状態空間判定をバイパスして強制block/hold:

```yaml
hard_overrides:
  block_if_secret_found: true
  block_if_prod_write_and_taboo_warn: true
  hold_if_high_privilege_and_uncertain: true
```

## Data Protection

| Data | Handling |
|------|----------|
| Raw prompt/artifact | Redaction後保存、PII判定不能時は保存禁止 |
| Embeddings | Signed ingest, version管理 |
| Human corrections | 365日保存、監査対象 |
| Trace metadata | 180日保存後purge |

## Classification Policy

| Class | Raw Storage | Embedding | Notes |
|-------|-------------|-----------|-------|
| public | allowed after scan | allowed | public artifacts only |
| internal | allowed after redaction | allowed | default non-sensitive work data |
| confidential | redacted reference only by default | conditional | requires owner approval |
| pii-sensitive | prohibited | prohibited unless explicitly redacted | fail closed |
| restricted | prohibited | prohibited | default for unknown classification |

Unknown classification is treated as `restricted`. External managed services require data residency, retention, purge API, and audit export review before use.

## Incident Response

Secret or PII mis-storage triggers immediate revoke, purge, re-embedding, audit annotation, and reviewer notification. Affected dataset versions must be invalidated until revalidated.

## Audit Trail

全decision packetはOTel trace + audit eventとして二重化:

```json
{
  "trace_id": "...",
  "span_id": "...",
  "run_id": "...",
  "artifact_hash": "...",
  "static_gate_results": [...],
  "scorer_outputs": {...},
  "composite_decision": "block",
  "human_override": {...},
  "threshold_version": "..."
}
```
