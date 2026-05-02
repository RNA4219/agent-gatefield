---
intent_id: DOC-LEGACY
owner: infrastructure
status: active
last_reviewed_at: 2026-05-02
next_review_due: 2026-06-02
---

# Technical Debt Register

code-to-gate 分析で検出された技術的債務の記録と対応計画。

## 検出日: 2026-05-02

## 1. LARGE_MODULE - モジュール肥大化

### 1.1 src/core/engine.py → engine/ package (分割済み: 2026-05-02)

**分割後**:
| Module | 行数 | 内容 |
|---|---|---|
| engine/decision_engine.py | 798 | DecisionEngine class |
| engine/helpers.py | 191 | Helper functions (centroid, score_factors) |

**判定**: 進行中 - decision_engine.py still above 500 lines
**次段階**: Extract scoring phases to separate module

### 1.2 src/core/calibration.py → calibration/ package (分割済み: 2026-05-02)

**分割後**:
| Module | 行数 | 内容 |
|---|---|---|
| calibration/pipeline.py | 945 | CalibrationPipeline class |
| calibration/helpers.py | 54 | EWMA, uncertainty helpers |

**判定**: 進行中 - pipeline.py still above 500 lines
**次段階**: Consider further decomposition

### 1.3 src/encoder/embedding_worker.py (867 lines)

**現状**: Embedding worker with multi-provider support.

**分割計画**:
| 新モジュール | 内容 | 行数見積 |
|---|---|---|
| `embedding_worker/providers.py` | Provider-specific implementations | ~350 |
| `embedding_worker/batching.py` | Batch processing logic | ~200 |
| `embedding_worker/cache.py` | Embedding cache management | ~200 |
| `embedding_worker/__init__.py` | Worker class, public API | ~100 |

**優先度**: Low (Q3)

### 1.4 cli/gate_cli.py (801 lines)

**現状**: CLI consolidates 10+ subcommands in single entry.

**分割計画**:
| 新モジュール | 内容 | 行数見積 |
|---|---|---|
| `cli/commands/evaluate.py` | Evaluate command | ~150 |
| `cli/commands/calibrate.py` | Calibrate command | ~150 |
| `cli/commands/export.py` | Export command | ~100 |
| `cli/commands/visualize.py` | Visualize command | ~100 |
| `cli/main.py` | Entry point, argparse | ~150 |

**優先度**: Low (Q3)

### 1.5 src/review/queue.py (769 lines)

**現状**: Review queue handling 5 priority levels with persistence.

**分割計画**:
| 新モジュール | 内容 | 行数見積 |
|---|---|---|
| `queue/priority_handlers.py` | Priority-specific handlers | ~250 |
| `queue/persistence.py` | Queue persistence logic | ~200 |
| `queue/dispatch.py` | Queue dispatch logic | ~200 |
| `queue/__init__.py` | Queue class, public API | ~100 |

**優先度**: Low (Q3)

## 2. RAW_SQL - 妥当性確認済み

### 2.1 src/vector_store/qdrant_store.py

**判定**: False Positive
- Qdrant filter DSL construction, not SQL
- Vector database uses filter objects, not SQL queries

**対応**: 抑制設定 `.ctg/suppressions.yaml` で false positive 記録

## 3. TRY_CATCH_SWALLOW - 妥当性確認済み

### 3.1 htmlcov/coverage_html_cb_188fc9a4.js

**判定**: Generated file
- pytest-cov HTML report, not source code

**対応**: `htmlcov/` added to DEFAULT_IGNORED_DIRS in code-to-gate

## 4. 定期再評価

次回 code-to-gate 実行: 2026-06-02 (月次)

```bash
code-to-gate scan . --out .qh
code-to-gate analyze . --from .qh --out .qh --policy .ctg/policy.yaml
```