# Agent Gatefield

Agent Gatefield は、AI エージェントが作った成果物をそのまま通さず、`pass` / `hold` / `block` に振り分ける安全ゲートです。

もっと普通の言葉でいうと、**AI が作った変更を「通してよい」「人間が見るべき」「止めるべき」に分ける仕組み**です。

## 3分でわかる説明

AI エージェントは、コード、設定変更、PR 提案、コマンド実行計画などを自動で作れます。便利ですが、次のような出力もありえます。

| AI が出すかもしれないもの | 何が怖いか | Gatefield の反応 |
|---|---|---|
| 本番 DB を書き換えるコマンド | 影響が大きい | `hold` にして人間確認へ回す |
| secret らしき文字列を含むコード差分 | 漏洩につながる | `block` する |
| テストは通るが設計方針から外れた変更 | 後から保守不能になる | 類似する却下例や設計憲法から危険度を出す |
| 過去に失敗した変更に似た提案 | 同じ事故を繰り返す | `hold` または `block` に寄せる |
| 判断材料が少ない高権限操作 | 自動承認が危ない | `hold` にして reviewer に渡す |

Gatefield は「テストが通ったか」だけを見ません。

**過去の判断、チームの設計方針、危険な操作、曖昧さ、人間が見るべき条件**をまとめて見ます。

そのため、挙動は少し不思議に見えます。単純な if 文ではなく、「この変更は過去の危ない変更に近いか」「チームの憲法から外れていないか」「自信を持って通せるか」をまとめて判断するからです。

## 何を入力して、何が返るのか

入力は、AI エージェントの実行結果です。

| 入力 | 内容 |
|---|---|
| artifact | AI が作った成果物。コード差分、文書、PR 提案、実行計画など |
| trace | AI がどう考え、どのツールを使い、何を試したか |
| static gate result | lint、型チェック、テスト、SAST、secret scan などの結果 |
| context | 対象 repo、環境、本番/開発、権限、操作種別など |

出力は `DecisionPacket` です。

| 出力 | 内容 |
|---|---|
| `decision` | `pass` / `hold` / `block` |
| `composite_score` | 総合的な危険度やズレのスコア |
| `factors` | どの要素が判断に効いたか |
| `action` | 通す、人間レビューへ回す、止めるなど |
| `threshold_version` | どの閾値セットで判断したか |
| `audit metadata` | 後から再現・監査するための情報 |

`hold` や `block` はエラーではありません。危険や不確実性を検知して、ちゃんと止まっている状態です。

## 判断のイメージ

たとえば、AI が次のような変更を作ったとします。

```text
本番環境のユーザーテーブルに対して一括更新を行う migration を追加した。
テストは通っている。
ただし rollback 手順がなく、過去に却下された migration 方針に似ている。
```

普通の CI なら「テストが通ったので OK」に見えるかもしれません。

Gatefield はもう少し広く見ます。

| 観点 | 判断 |
|---|---|
| テスト | 通っている |
| 本番影響 | 大きい |
| rollback | 不足 |
| 過去の却下例 | 似ている |
| 自動で通すべきか | 危ない |

この場合、`pass` ではなく `hold` になりやすいです。

```json
{
  "decision": "hold",
  "action": {
    "action_type": "human_review"
  },
  "factors": [
    {
      "name": "reject_similarity",
      "value": 0.82
    },
    {
      "name": "uncertainty",
      "value": 0.31
    }
  ]
}
```

ここで Gatefield がしているのは、「テストは通ったけれど、この変更は人間が見るべき」と判断することです。

## なぜ効くのか

Gatefield の強みは、AI 出力を単発で見ないことです。

| 仕組み | 役割 |
|---|---|
| Static gates | 明確にダメなものを落とす。secret、SAST、危険コマンドなど |
| Judgment KB | チームの憲法、禁忌例、採用例、却下例を保存する |
| Embedding | 今回の成果物が、過去の例や方針にどれだけ近いかを見る |
| Scorers | 複数の観点で危険度やズレを採点する |
| Hard overrides | secret 検出など、スコアに関係なく止める |
| Human review | 自動で決めきれないものを人間へ渡す |
| Replay | 後から同じ条件で判断を再現する |

つまり Gatefield は、AI エージェントに対する「記憶つきの品質ゲート」です。

過去に危なかったもの、チームが嫌う設計、明確に禁止した操作を、次の判断に使います。

## 全体の流れ

```text
AI エージェントの実行
        |
        v
成果物、実行履歴、静的チェック結果を集める
        |
        v
StateEncoder が判断しやすい形に変換する
        |
        v
Embedding で過去の判断や設計方針との近さを見る
        |
        v
Scorers が複数の観点で採点する
        |
        v
DecisionEngine が pass / hold / block を決める
        |
        v
必要なら human review へ送る
```

この流れを実装しているので、単純なルールベースよりも「なぜそこで止まれるの？」という挙動になります。そこがこのツールの面白いところで、同時に初見で理解しづらいところです。

## 判定の種類

| 判定 | 意味 | 次にすること |
|---|---|---|
| `pass` | 通してよい | 後続処理へ進める |
| `hold` | 自動では決めきれない | 人間レビューへ回す |
| `block` | 止めるべき | 修正または運用判断が必要 |

`hold` は弱い失敗ではありません。AI を安全に使うには、`hold` をきちんと出せることが重要です。

## 現在の状態

この repository は PoC ではなく、MVP として扱える状態です。

| 項目 | 状態 |
|---|---|
| Decision Engine | 実装済み |
| State Encoder | 実装済み |
| Static gates | 実装済み |
| Judgment KB | 実装済み |
| BGE-M3 local embedding | 実装済み |
| llama.cpp runtime adapter | 実装済み |
| Qdrant vector store | 実装済み |
| pgvector vector store | 実装済み |
| bge-reranker-v2-m3 reranker | 実装済み |
| Human review queue / SLA | 実装済み |
| HTTP API | 実装済み |
| CLI | 実装済み |
| Tests | `1435 passed, 11 skipped` を確認済み |
| Coverage | 80% 目標で妥協 |

PoC ではなく MVP と呼べる理由は、アイデアの実証だけでなく、CLI、HTTP API、fallback、検収、README、RUNBOOK まで揃っているためです。

ただし、長期の本番無人運用に入れるには、実データでの reviewer 運用、SLA ダッシュボード、長期 replay、Qdrant/pgvector の運用証跡をさらに積む必要があります。

## 最短で動かす

```powershell
cd C:\Users\ryo-n\Codex_dev\agent-gatefield

# 設定ファイルが正しいか確認
uv run --offline --no-sync python -m cli.gate_cli config validate -f config\gate-config.yaml

# サンプル run を評価する
uv run --offline --no-sync python -m cli.gate_cli dry-run --run-id local-retrieval-check --json

# テストを回す
uv run --offline --no-sync python -m pytest tests -q
```

`dry-run` は `hold` や `block` の場合に非 0 終了になることがあります。JSON が出ていて `decision` が読めるなら、CLI が壊れているわけではありません。

## 検収済みの内容

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

## Local Retrieval Stack

既定の semantic embedding は `BAAI/bge-m3` です。BGE-M3 の dense embedding は 1024 次元です。

重要な点:

- 初回だけモデルダウンロードが必要です。
- ネットワークなし、モデルなしの状態では BGE-M3 実モデル推論はできません。
- 自動テストは fallback によりモデルなしでも通るようにしています。
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

まず見るべき箇所は `state_space_gate` です。

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

## CLI

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

外部制御面から接続するための HTTP API があります。

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
