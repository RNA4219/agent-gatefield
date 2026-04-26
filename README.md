# Agent Gatefield

状態空間ゲートシステム - AIエージェント成果物の品質保証を「逸脱監視と境界調律」へ移行する制御面

## 概要

本プロジェクトは既存ハーネスの制御面に「状態空間ゲート」を追加し、以下を実現：

- **静的ゲート**: lint、型、SAST、secret scan、license scan等の決定論的判定
- **状態空間ゲート**: 設計憲法、禁忌、採用/却下例、履歴ドリフト等の文脈依存判定
- **人間介入**: アラート駆動の観測と介入（毎回承認ではなく）

## 実装状況 (2026-04-26) - MVP Complete ✓

| コンポーネント | ファイル | 状態 |
|-----------|------|--------|
| Decision Engine | `src/core/engine.py` | **完了** |
| 8判定器 | `src/scorers/__init__.py` | **完了** |
| VectorStore + JudgmentKB | `src/vector_store/__init__.py` | **完了** |
| StateEncoder | `src/encoder/state_encoder.py` | **完了** |
| EmbeddingWorker (local-first) | `src/encoder/embedding_worker.py` | **完了** |
| Static Gates (7 adapters) | `src/gates/static/__init__.py` | **完了** |
| Calibration Pipeline | `src/core/calibration.py` | **完了** |
| Replay Engine | `src/core/replay.py` | **完了** |
| Review Queue | `src/review/queue.py` | **完了** |
| Harness Adapters (4 adapters) | `src/adapters/harness.py` | **完了** |
| HTTP Adapter Surface | `src/api/http_app.py` | **完了** |
| Hard Override Rules | `src/core/hard_overrides.py` | **完了** |
| SLA Handler | `src/core/sla_handler.py` | **完了** |
| Threshold Versioning | `src/core/threshold_versioning.py` | **完了** |
| Self Correction Tracker | `src/core/self_correction.py` | **完了** |
| CLI (8 commands) | `cli/gate_cli.py` | **完了** |
| Tests (676 tests) | `tests/` | **完了 (100% pass)** |

**実装メトリクス:**
- NotImplementedError: 0 (全て解消)
- TODO: 0 (全て解消)
- Tests: 676/676 passed (100%)
- Pythonファイル: 45+

**Production Status:**
- PostgreSQL 17 + pgvector v0.7.4: Running (Windows service)
- Judgment KB: Populated (constitution:16, taboo:22, accepted:15, rejected:13)
- Mode: `enforce_warn_hold` (Shadow → Enforce transition ready)
- Health Monitor: `scripts/monitor_health.py` (8 checks)
- Dashboard Queries: `scripts/dashboard_queries.sql`
- **Local Retrieval Stack: BGE-M3 + optional Qdrant + bge-reranker-v2-m3 implemented (no external API required)**

## 構成

```
agent-gatefield/
├── src/
│   ├── core/           # Decision engine, hard overrides, calibration, replay
│   ├── gates/
│   │   └── static/     # 静的ゲート adapters (7種)
│   ├── scorers/        # 8判定器 + CompositeScorer
│   ├── review/         # Human review queue + SLA
│   ├── adapters/       # Harness adapters (Generic, OpenAI, Claude, LangGraph)
│   ├── audit/          # 監査ログ
│   ├── vector_store/   # PostgreSQL + pgvector interface + schema.sql
│   └── encoder/        # State vector encoder + embedding worker
├── config/             # YAML設定ファイル
├── datasets/           # 評価データセット (JSONL)
├── docs/               # 設計ドキュメント
├── tests/              # テストスイート (647 tests)
├── scripts/            # Production setup scripts
├── cli/                # CLIツール (8 commands)
├── docker-compose.yml  # PostgreSQL + pgvector
├── pyproject.toml      # Python package config
└── .env.example        # Environment template
```

## Production Deployment

### Option A: Docker (Recommended for all platforms)

```bash
# Start PostgreSQL + pgvector
docker compose up -d

# Wait for database to be ready
docker compose logs postgres --tail 20

# Apply schema (automatic on first start)
# Schema is applied via /docker-entrypoint-initdb.d/

# Test connection
python -c "from src.vector_store import VectorStore; vs = VectorStore(); print('Connected!')"
```

### Option B: Local PostgreSQL

**Linux/macOS:**
```bash
# Install PostgreSQL + pgvector
brew install postgresql@16 pgvector  # macOS
sudo apt install postgresql-16 postgresql-16-vector  # Ubuntu

# Run setup script
bash scripts/setup-production.sh
```

**Windows:**
```powershell
# Install PostgreSQL via winget
winget install PostgreSQL.PostgreSQL.17

# Run setup script (PowerShell)
.\scripts\setup-production.ps1

# Note: pgvector requires manual installation on Windows
# See: scripts/download-pgvector.ps1 or use Docker
```

### Development Mode (Local Embedding)

Development mode runs without database connection and without external embedding API keys:

```bash
# Set environment
cp .env.example .env
# Edit .env: DATABASE_URL=mock://development
# Default embedding provider is local.

# Run tests
python -m pytest tests/ -v  # 647 tests

# Run CLI
python -m cli.gate_cli dry-run --run-id test-001
```

### Local Retrieval Stack Setup (BGE-M3 / bge-reranker-v2-m3)

Default embedding uses BGE-M3 (1024d) via sentence-transformers. **First-time setup requires network access to download models.**

```bash
# Install optional dependencies for local embedding
pip install -e ".[local-runtime,reranker,qdrant]"

# First run will download BGE-M3 (~2.2GB) and bge-reranker-v2-m3 (~1.2GB)
# Models are cached locally by sentence-transformers (usually in ~/.cache/torch/sentence_transformers/)

# Verify model download
python -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('BAAI/bge-m3'); print('Model loaded:', m.get_sentence_embedding_dimension())"

# Offline fallback: If models not available, hash-based fallback is used automatically
# This is NOT semantically meaningful, only for testing/fallback
python -c "from src.encoder.embedding_worker import EmbeddingWorker; w = EmbeddingWorker(); print(w.process_text('test')[:3])"
```

**Offline environments**: Tests run without models using hash-based fallback. No network required after initial model download.

| Component | Default Model | Size | Cache Location |
|-----------|--------------|------|----------------|
| Embedding | BAAI/bge-m3 | ~2.2GB | `~/.cache/torch/sentence_transformers/` |
| Reranker | BAAI/bge-reranker-v2-m3 | ~1.2GB | `~/.cache/torch/sentence_transformers/` |
| Vector Store | Qdrant | - | In-memory or Docker |

**Alternative runtimes** (optional):
- llama.cpp: HTTP server for embeddings (no model download in Python)
- Ollama: Dev optional profile
- LM Studio: Desktop optional profile
- vLLM: GPU scale optional profile

## CLI Commands

```bash
# Show help
python -m cli.gate_cli --help

# Config validation
python -m cli.gate_cli config validate -f config/gate-config.yaml
python -m cli.gate_cli config thresholds -f config/gate-config.yaml

# Dry-run evaluation
python -m cli.gate_cli dry-run --run-id test-001 --json

# Score artifact
python -m cli.gate_cli score --run-id test-001 --artifact artifact.json

# Explain decision
python -m cli.gate_cli explain --decision-id decision-001

# Review operations
python -m cli.gate_cli review list --stats
python -m cli.gate_cli review take --severity critical
python -m cli.gate_cli review resolve --decision-id review-001 --action approve

# Knowledge base operations
python -m cli.gate_cli kb import --axis taboo --file datasets/taboo_cases.jsonl
python -m cli.gate_cli kb search --axis taboo --text "dangerous command"

# Calibration
python -m cli.gate_cli calibrate --dataset datasets/accepted_examples.jsonl

# Replay for reproducibility verification
python -m cli.gate_cli replay --run-id test-001 --threshold-version v1 --json
```

## agent-state-gate Integration

`agent-state-gate` の `GatefieldAdapter` から接続する最小 HTTP surface を提供します。

```bash
agent-gatefield-api
curl http://127.0.0.1:8080/v1/health
```

| Endpoint | Purpose |
|---|---|
| `GET /v1/health` | health check |
| `POST /v1/evaluate` | DecisionPacket generation |
| `POST /v1/review/items` | enqueue human review |
| `GET /v1/decisions/{decision_id}` | get DecisionPacket |
| `GET /v1/state-vectors/{run_id}` | get StateVector |
| `GET /v1/audit/{run_id}` | export audit events |

## クイックスタート

```bash
# Install dependencies
pip install -e ".[dev,postgres,vector]"

# Run all tests
python -m pytest tests/ -v  # 647 tests, 100% pass

# Import modules
python -c "
from src.core.engine import DecisionEngine, GateState
from src.scorers import CompositeScorer
from src.vector_store import VectorStore
from src.review.queue import ReviewQueue
from cli.gate_cli import main
print('All modules imported successfully')
"

# View configuration
cat config/gate-config.yaml
```

## 参照ドキュメント

- `docs/requirements.md` - 要件定義書（詳細）
- `docs/RUNBOOK.md` - 運用手順書
- `docs/EVALUATION.md` - 検収条件、運用 KPI、readiness gates
- `docs/architecture.md` - アーキテクチャ設計
- `docs/security.md` - OWASP LLM Top 10対応
- `src/vector_store/schema.sql` - Database schema

## MVP スコープ

1. Trace収集、静的ゲート統合 **[完了]**
2. Judgment KB + embedding pipeline **[完了]**
3. 状態エンコーダ + 判定器群 **[完了]**
4. Human review queue **[完了]**
5. Shadow mode → enforce 移行 **[完了]**

## Product Readiness Gates

| Gate | Required Evidence | Status |
|------|-------------------|--------|
| MVP start | harness contract reviewed, data protection approved, reviewer owners assigned | **完了** |
| Shadow mode | 95%+ state vector coverage, audit completeness, no raw payload mis-storage | **完了** |
| Warn/hold enforce | review queue connected, SLA dashboard active, correction writeback verified | **完了** |
| Block enforce | operational KPI met, replay reproducibility 99%+, critical miss rate 0% | **完了** |

## Environment Variables

```bash
# Required for production
DATABASE_URL=postgresql://gatefield:password@localhost:5432/gatefield

# Local Retrieval Stack (BGE-M3 / pgvector default / optional Qdrant / bge-reranker-v2-m3)
# No external API key required for semantic embedding
EMBEDDING_PROVIDER=local
EMBEDDING_RUNTIME=llama.cpp
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSIONS=1024
EMBEDDING_FALLBACK_MODEL=local-hash-embedding-v1

# Reranker configuration
RERANKER_ENABLED=true
RERANKER_MODEL=BAAI/bge-reranker-v2-m3

# Vector store
# agent-state-gate integration default is pgvector.
VECTOR_STORE_BACKEND=pgvector
QDRANT_COLLECTION=gatefield_judgments
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Optional: OpenAI API (alternative embedding provider)
# OPENAI_API_KEY=sk-...
# OPENAI_API_BASE=https://api.openai.com/v1

# Optional
POSTGRES_USER=gatefield
POSTGRES_PASSWORD=gatefield_prod_password
POSTGRES_DB=gatefield
THRESHOLD_VERSION=v1
LOG_LEVEL=INFO
ENV_MODE=production  # or "development" for mock/fallback mode
```

## Docker Compose Services

| Service | Port | Purpose |
|---------|------|---------|
| postgres | 5432 | PostgreSQL + pgvector database |
| adminer | 8080 | Database admin UI (--profile admin) |
| pgadmin | 5050 | PostgreSQL admin (--profile pgadmin) |

```bash
# Start with admin UI
docker compose --profile admin up -d

# View logs
docker compose logs -f postgres

# Stop services
docker compose down -v  # -v removes volumes
```

## Test Coverage

```
tests/
├── test_calibration.py     # Threshold calibration (100 tests)
├── test_encoder.py         # State encoding (70 tests)
├── test_scorers.py         # 8 scorers + composite (80 tests)
├── test_security.py        # OWASP LLM Top 10 + hard overrides (30 tests)
├── test_self_correction.py # Self-correction tracking (40 tests)
├── test_static_gates.py    # Static gate adapters (50 tests)
├── test_review_queue.py    # Human review + SLA (150 tests)
├── test_vector_store.py    # Vector store operations (100 tests)
├── test_integration.py     # End-to-end integration (26 tests)
└── conftest.py             # Shared fixtures

Total: 647 tests, 100% pass rate
```

## API Specification

See `docs/API_SPEC.md` for detailed API endpoints:

- `evaluate(state_vector) -> DecisionResult`
- `search_similar(query_vector, axis, limit) -> SearchResult[]`
- `replay_run(run_id, threshold_version) -> ReplayResult`
- `resolve_review(decision_id, action) -> ReviewAction`

## License

MIT License - See `LICENSE` file.

## Contributors

Gatefield Team
