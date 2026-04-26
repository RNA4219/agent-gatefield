# Agent Gatefield

Agent Gatefield は、AI エージェントの成果物をそのまま通す前に、危ない兆候や品質のズレを検知して `pass` / `hold` / `block` に振り分けるゲートです。

一言でいうと、AI エージェント用の「品質保証と安全確認の関所」です。

## まず何をするものか

AI エージェントは、コード変更、設計文書、ツール実行計画、PR 提案などを自動で作ります。Agent Gatefield はそれらを受け取り、次の観点で判定します。

| 観点 | 見ているもの | 例 |
|---|---|---|
| 静的ゲート | 決定論的に分かる危険 | lint 失敗、型エラー、secret 混入、危険コマンド |
| 状態空間ゲート | 文脈上の危険やズレ | 設計憲法との不一致、禁忌例への近さ、過去の却下例との類似 |
| 人間レビュー | 自動で決めきれないもの | 高権限操作、不確実性が高い変更、判断根拠が薄い変更 |

判定結果は主に 3 種類です。

| 判定 | 意味 | 次にすること |
|---|---|---|
| `pass` | 通してよい | 後続処理へ進める |
| `hold` | 人間確認が必要 | review queue に積む |
| `block` | 止めるべき | 修正または運用判断が必要 |

`hold` や `block` は失敗ではありません。危険や不確実性を検知して止められている状態です。

## 全体像

```
AI エージェントの実行
        |
        v
Trace / Artifact / Static gate result
        |
        v
StateEncoder
  - 実行内容を状態ベクトルに変換
  - BGE-M3 で意味ベクトル化
        |
        v
DecisionEngine
  - 静的ゲート
  - 8 種類の scorer
  - hard override
        |
        v
DecisionPacket
  - pass / hold / block
  - score
  - 理由
  - audit 用 metadata
```

この README では、まず動かすために必要なことだけを説明します。詳細仕様は `docs/` 配下に分けています。

## 現在の状態

MVP は完成扱いです。

| 項目 | 状態 |
|---|---|
| Decision Engine | 実装済み |
| State Encoder | 実装済み |
| BGE-M3 local embedding | 実装済み |
| llama.cpp runtime adapter | 実装済み |
| Qdrant vector store | 実装済み |
| pgvector vector store | 実装済み |
| bge-reranker-v2-m3 reranker | 実装済み |
| Static gates | 実装済み |
| Human review queue / SLA | 実装済み |
| HTTP adapter | 実装済み |
| CLI | 実装済み |
| Tests | `1435 passed, 11 skipped` を確認済み |
| Coverage | 80% 目標で妥協 |

検収時点の主な確認結果:

```text
uv run --offline --no-sync python -m pytest tests -q
1435 passed, 11 skipped

uv run --offline --no-sync python scripts/offline_eval.py --dataset all --dataset-dir datasets
Overall: PASS / Passed: 6 / Failed: 0

uv run --offline --no-sync python -m cli.gate_cli config validate -f config\gate-config.yaml
Configuration is valid
```

BGE-M3 / llama.cpp の実機経路も確認済みです。

```text
BAAI/bge-m3 1024 1024 success llama.cpp
```

## 最短で動かす

このプロジェクトは Python パッケージです。普段の検証は `uv` を使う前提にしています。

```powershell
cd C:\Users\ryo-n\Codex_dev\agent-gatefield

# 設定ファイルが正しいか確認
uv run --offline --no-sync python -m cli.gate_cli config validate -f config\gate-config.yaml

# サンプル run を評価する
uv run --offline --no-sync python -m cli.gate_cli dry-run --run-id local-retrieval-check --json

# テストを回す
uv run --offline --no-sync python -m pytest tests -q
```

`dry-run` は判定が `hold` や `block` の場合、非 0 終了になることがあります。JSON が出ていて `decision` が読めるなら、CLI が壊れているわけではありません。

例:

```json
{
  "decision": "hold",
  "action": {
    "action_type": "human_review"
  }
}
```

これは「人間確認に回す」という正常な判定です。

## 初回モデル準備

既定の semantic embedding は `BAAI/bge-m3` です。BGE-M3 の dense embedding は 1024 次元です。

重要な点:

- 初回だけモデルダウンロードが必要です。
- ネットワークなし、モデルなしの状態では BGE-M3 実モデル推論はできません。
- ただし、自動テストは fallback によりモデルなしでも通るようにしています。
- fallback は意味検索としては使わず、テストや degraded mode 用です。

sentence-transformers で直接確認する場合:

```powershell
uv run python -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('BAAI/bge-m3'); print(m.get_sentence_embedding_dimension())"
```

期待値:

```text
1024
```

llama.cpp で使う場合は、BGE-M3 の GGUF が必要です。検収では `gpustack/bge-m3-GGUF` の `bge-m3-Q4_K_M.gguf` を使いました。

```powershell
llama-server `
  --embedding `
  --host 127.0.0.1 `
  --port 8080 `
  --hf-repo gpustack/bge-m3-GGUF `
  --hf-file bge-m3-Q4_K_M.gguf `
  -c 2048
```

別のポートで起動する場合:

```powershell
$env:LLAMA_CPP_HOST="127.0.0.1"
$env:LLAMA_CPP_PORT="18080"
```

## 主要設定

主な設定ファイルは [config/gate-config.yaml](config/gate-config.yaml) です。

特に見るべき箇所は `state_space_gate` です。

```yaml
state_space_gate:
  enabled: true
  mode: enforce_warn_hold
  semantic_embedding:
    provider: local
    runtime: llama.cpp
    model: BAAI/bge-m3
    dimensions: 1024
    fallback_model: local-hash-embedding-v1
  reranker:
    enabled: true
    model: BAAI/bge-reranker-v2-m3
  vector_store:
    backend: qdrant
    collection: gatefield_judgments
    dense_dimensions: 1024
```

`mode` の意味:

| mode | 意味 |
|---|---|
| `shadow` | 判定は記録するが止めない |
| `enforce_warn_hold` | 危険度に応じて warning / hold する |
| `enforce_block` | block 条件に該当したら止める |

今の既定は `enforce_warn_hold` です。

## CLI の使い方

よく使うコマンドだけを載せます。

```powershell
# ヘルプ
uv run python -m cli.gate_cli --help

# 設定検証
uv run python -m cli.gate_cli config validate -f config\gate-config.yaml

# 閾値を見る
uv run python -m cli.gate_cli config thresholds -f config\gate-config.yaml

# サンプル評価
uv run python -m cli.gate_cli dry-run --run-id test-001 --json

# artifact を採点
uv run python -m cli.gate_cli score --run-id test-001 --artifact artifact.json

# 人間レビュー一覧
uv run python -m cli.gate_cli review list --stats

# Knowledge Base にデータを入れる
uv run python -m cli.gate_cli kb import --axis taboo --file datasets\taboo_cases.jsonl

# Knowledge Base を検索する
uv run python -m cli.gate_cli kb search --axis taboo --text "dangerous command"

# offline 評価
uv run python scripts\offline_eval.py --dataset all --dataset-dir datasets
```

## HTTP API

`agent-state-gate` など外部制御面から接続するための HTTP surface があります。

起動:

```powershell
uv run agent-gatefield-api
```

health check:

```powershell
curl http://127.0.0.1:8080/v1/health
```

主な endpoint:

| Endpoint | 用途 |
|---|---|
| `GET /v1/health` | health check |
| `POST /v1/evaluate` | DecisionPacket を作る |
| `POST /v1/review/items` | human review に積む |
| `GET /v1/decisions/{decision_id}` | 判定結果を取得 |
| `GET /v1/state-vectors/{run_id}` | 状態ベクトルを取得 |
| `GET /v1/audit/{run_id}` | audit event を取得 |

## 依存サービス

用途によって必要なものが変わります。

| 用途 | 必要なもの | 備考 |
|---|---|---|
| unit test | Python 依存のみ | モデルなしでも fallback で通す |
| BGE-M3 実推論 | BGE-M3 モデル | 初回ダウンロードが必要 |
| llama.cpp 実推論 | `llama-server` と GGUF | 既定 runtime |
| Qdrant 検証 | Qdrant または in-memory Qdrant | local retrieval profile |
| pgvector 検証 | PostgreSQL + pgvector | 永続 DB profile |

Docker で PostgreSQL + pgvector を起動する場合:

```powershell
docker compose up -d
docker compose logs postgres --tail 20
```

Qdrant はこの `docker-compose.yml` には含まれていません。Qdrant を実プロセスで使う場合は別途起動してください。テストでは in-memory / mock / fallback 経路も使います。

## 環境変数

`.env.example` をコピーして必要に応じて変更します。

```powershell
Copy-Item .env.example .env
```

代表的な設定:

```env
EMBEDDING_PROVIDER=local
EMBEDDING_RUNTIME=llama.cpp
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSIONS=1024
EMBEDDING_FALLBACK_MODEL=local-hash-embedding-v1

RERANKER_ENABLED=true
RERANKER_MODEL=BAAI/bge-reranker-v2-m3

VECTOR_STORE_BACKEND=qdrant
QDRANT_COLLECTION=gatefield_judgments
QDRANT_HOST=localhost
QDRANT_PORT=6333

DATABASE_URL=postgresql://gatefield:gatefield_prod_password@localhost:5432/gatefield
THRESHOLD_VERSION=v1
ENV_MODE=development
```

OpenAI API key は既定では不要です。

## ディレクトリ構成

```text
agent-gatefield/
├── cli/                 # CLI entrypoint
├── config/              # gate-config.yaml
├── datasets/            # offline eval 用 JSONL
├── docs/                # 仕様、運用、検収資料
├── scripts/             # setup / eval / monitoring scripts
├── src/
│   ├── adapters/        # harness adapter
│   ├── api/             # HTTP API
│   ├── audit/           # audit logging
│   ├── core/            # DecisionEngine / calibration / replay / SLA
│   ├── encoder/         # StateEncoder / EmbeddingWorker / runtime adapter
│   ├── gates/           # static gates
│   ├── review/          # human review queue
│   ├── scorers/         # state-space scorers
│   └── vector_store/    # pgvector / Qdrant / KB
└── tests/               # automated tests
```

最初に読むなら、以下の順がおすすめです。

1. この README
2. [docs/RUNBOOK.md](docs/RUNBOOK.md)
3. [docs/EVALUATION.md](docs/EVALUATION.md)
4. [docs/architecture.md](docs/architecture.md)
5. [docs/spec/API_SPEC.md](docs/spec/API_SPEC.md)

## 用語

| 用語 | 意味 |
|---|---|
| artifact | エージェントが作った成果物。コード差分、文書、実行計画など |
| trace | エージェント実行中のイベント履歴 |
| state vector | artifact と trace を判定しやすい形に変換した状態 |
| scorer | state vector の一部を採点する部品 |
| hard override | secret 検出など、score に関係なく止めるルール |
| DecisionPacket | 最終判定、score、理由、audit 情報を含む結果 |
| Judgment KB | 憲法、禁忌例、採用例、却下例を入れる知識ベース |
| fallback embedding | モデルが使えないときの deterministic hash vector |

## よくあるつまずき

### `dry-run` が exit 1 になる

`decision: hold` や `decision: block` の場合は非 0 終了になることがあります。JSON が出ていれば、判定処理自体は動いています。

### ネットワークなしで BGE-M3 が動かない

正常です。初回のモデルダウンロードにはネットワークが必要です。モデル取得後はローカルキャッシュから使えます。

### モデルなしでもテストが通るのはなぜか

テストでは実モデルを必須にせず、fallback embedding を使えるようにしています。これは CI や offline 検収を安定させるためです。本番品質の意味検索には BGE-M3 を使ってください。

### Qdrant が起動していない

Qdrant 実プロセスが必要な検証では起動してください。一方、unit test は in-memory / mock / fallback で通るようにしています。

### Coverage が 100% ではない

現在は 80% 目標で妥協しています。実モデル、vector DB、HTTP、CLI、review flow が絡むため、数字だけを追うと brittle なテストが増えます。受入では、主要リスクの実測と contract test を優先しています。

## 参照ドキュメント

| ファイル | 目的 |
|---|---|
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | 運用手順 |
| [docs/EVALUATION.md](docs/EVALUATION.md) | 検収条件、KPI、readiness gate |
| [docs/architecture.md](docs/architecture.md) | アーキテクチャ概要 |
| [docs/security.md](docs/security.md) | security / OWASP LLM Top 10 対応 |
| [docs/spec/API_SPEC.md](docs/spec/API_SPEC.md) | API 詳細 |
| [docs/spec/DATA_TYPES_SPEC.md](docs/spec/DATA_TYPES_SPEC.md) | データ型詳細 |
| [src/vector_store/schema.sql](src/vector_store/schema.sql) | pgvector schema |

## License

MIT License. See [LICENSE](LICENSE).
