# Agent Instructions - Implement Local Retrieval Stack

## 目的

agent-gatefield の semantic retrieval を、仕様だけでなく実装として BGE-M3 / bge-reranker-v2-m3 / Qdrant / llama.cpp へ移行してください。RUNBOOK の `Local Retrieval Stack Decision` と `8.1 Embedding Model Migration` を正本として扱い、`local-hash-embedding-v1` 既定の暫定実装を製品既定から外してください。

参照正本:

- `docs/RUNBOOK.md`
- `docs/requirements.md`
- `docs/spec/API_SPEC.md`
- `docs/spec/INTEGRATION_SPEC.md`
- `docs/spec/DATA_TYPES_SPEC.md`

## 採用する構成

```yaml
embedding:
  provider: local
  runtime: llama.cpp
  model: BAAI/bge-m3
  dimensions: 1024
  fallback_model: local-hash-embedding-v1

reranker:
  enabled: true
  provider: local
  runtime: llama.cpp
  model: BAAI/bge-reranker-v2-m3
  top_k_input: 50
  top_k_output: 10

vector_store:
  backend: qdrant
  collection: gatefield_judgments
  distance: cosine
  dense_dimensions: 1024

runtime_profiles:
  default: llama.cpp
  dev_optional: ollama
  desktop_optional: lm_studio
  scale_optional: vllm
```

## 実装方針

1. `local-hash-embedding-v1` は fallback / unit test fixture に降格してください。製品既定値として使わないでください。
2. `EmbeddingWorker` は provider / runtime / model / dimensions を設定から受け取り、BGE-M3 1024d を標準の semantic embedding としてください。
3. 外部 API キーなしで起動・テスト・offline eval が通る状態を維持してください。`OPENAI_API_KEY` は必須にしないでください。
4. reranker 層を追加し、初期既定は `BAAI/bge-reranker-v2-m3` としてください。Qwen3-Reranker 0.6B-4B は設定上の代替候補に留めてください。
5. vector store は Qdrant を本番既定にしてください。LanceDB / SQLite+vec は dev / edge profile の代替として仕様に残してください。
6. runtime は llama.cpp を本番既定にしてください。Ollama / LM Studio は開発利便性、vLLM は GPU scale profile として扱ってください。
7. 既存の pgvector 実装は一気に削除せず、移行互換または fallback として扱ってください。不要化する場合も別タスクに分けてください。

## 着手順

1. 仕様の整合を先に直す。
   - `config/gate-config.yaml`、`.env.example`、README、RUNBOOK、requirements、spec、schema contract の既定値を BGE-M3 / 1024d / Qdrant / llama.cpp に揃える。
   - `local-hash-embedding-v1` は `fallback_model` または `mock/fallback` としてのみ記載する。
2. runtime abstraction を追加する。
   - 直接 llama.cpp 固定の実装にせず、`runtime` 設定を受ける小さな adapter を作る。
   - 初期実装は `llama.cpp` と `fallback` を必須、Ollama / LM Studio / vLLM は設定型と placeholder でよい。
3. BGE-M3 embedding 経路を実装する。
   - `EmbeddingWorker` が `BAAI/bge-m3` / `dimensions=1024` を返す契約にする。
   - 実モデルが未配置または runtime が起動していない場合は、明示的に fallback へ落とし、ログと status に fallback reason を残す。
   - fallback はリリース既定ではなく degraded mode として扱う。
4. Qdrant backend を追加する。
   - 既存 `VectorStore` API を壊さず、backend selection で `qdrant` を選べるようにする。
   - collection payload は少なくとも `axis`, `dataset_version`, `redaction_status`, `model`, `dims`, `content_hash`, `doc_id`, `source` を保持する。
   - Qdrant 未起動時は mock/fallback mode を明示し、テストは offline で通るようにする。
5. reranker 層を追加する。
   - `bge-reranker-v2-m3` を既定名として設定し、vector search の候補を rerank する interface を作る。
   - runtime 未配置時は deterministic fallback reranker でテスト可能にする。
   - decision explanation / exemplar refs に reranker score を含める。
6. テストを更新する。
   - default config が BGE-M3 / 1024d であること。
   - `OPENAI_API_KEY` 未設定で embedding / rerank / config validate / offline eval が通ること。
   - Qdrant backend が payload contract を満たすこと。
   - fallback 使用時に status / reason が出ること。
7. 最後に検収コマンドを実行し、結果を完了報告へ貼る。

## 実装上の許容判断

- ネットワークが使えない環境では、BGE-M3 実モデルの取得や Qdrant 起動を必須検証にしないでください。その場合でも、設定・adapter・contract・fallback・テストは実装してください。
- llama.cpp の embedding / reranker HTTP 仕様が環境で確定できない場合は、adapter の境界を作り、実リクエスト部分を最小実装または明示 TODO ではなく `NotConfigured` / `RuntimeUnavailable` として扱ってください。
- 依存追加は optional extras に分けてください。例: `qdrant`, `local-runtime`, `reranker`。
- offline test はモデルファイルなしで通ることを優先してください。ただし本番 config は BGE-M3 を向いている必要があります。

## 変更対象

優先して更新するファイル:

- `config/gate-config.yaml`
- `.env.example`
- `src/encoder/embedding_worker.py`
- `src/encoder/state_encoder.py`
- `src/encoder/` 配下の runtime adapter 追加
- `src/vector_store/`
- `src/scorers/` または `src/rerank/` の新規 module
- `cli/gate_cli.py`
- `tests/`
- `docs/RUNBOOK.md`
- `docs/requirements.md`
- `docs/spec/*.md`
- `README.md`

## 受入条件

- `config/gate-config.yaml` の既定が BGE-M3 / bge-reranker-v2-m3 / Qdrant / llama.cpp になっている。
- `OPENAI_API_KEY` 未設定でテストが通る。
- BGE-M3 dense embedding の次元は 1024 として扱われる。
- Qdrant collection 設計に `axis`, `dataset_version`, `redaction_status`, `model`, `dims`, `content_hash` の payload が含まれる。
- reranker 有効時、vector search の top-k 候補を rerank し、decision explanation に reranker score と exemplar refs を含める。
- runtime 未配置時は degraded fallback として動き、fallback reason がログまたは結果に出る。
- restricted / pii-sensitive payload は embedding 化しない既存ポリシーを維持する。
- offline eval が PASS する。
- README / RUNBOOK / spec / tests のモデル名・次元数・必須 env var が矛盾しない。

## 検収コマンド

Windows PowerShell:

```powershell
$env:UV_CACHE_DIR='C:\Users\ryo-n\Codex_dev\agent-gatefield\.uv-cache'
uv run --offline --no-sync python -m pytest tests
uv run --offline --no-sync python scripts\offline_eval.py --dataset all --dataset-dir datasets
uv run --offline --no-sync python -m cli.gate_cli config validate -f config\gate-config.yaml
uv run --offline --no-sync python -m cli.gate_cli dry-run --run-id local-retrieval-check --json
```

追加の contract checks:

```powershell
uv run --offline --no-sync python -c "from src.encoder.state_encoder import StateEncoder; e=StateEncoder({'provider':'local','runtime':'llama.cpp','model':'BAAI/bge-m3','dimensions':1024}); s=e._encode_semantic({'text':'local retrieval check'}); print(s['model'], s['dims'], len(s.get('vector', [])), s.get('status'))"
uv run --offline --no-sync python -c "import yaml; c=yaml.safe_load(open('config/gate-config.yaml', encoding='utf-8')); print(c['state_space_gate']['semantic_embedding']); print(c['state_space_gate'].get('reranker')); print(c['state_space_gate'].get('vector_store'))"
```

補足:

- `dry-run --json` は gate decision が `hold` / `block` の場合に非 0 終了になることがあります。JSON 出力が成功しているか、シリアライズエラーではないかを分けて判断してください。
- 依存追加が必要な場合は、まず `pyproject.toml` の optional extras を検討してください。ネットワーク取得が必要な検証は、ユーザー承認を得てから実行してください。
- Qdrant やモデル runtime の実プロセス起動ができない場合でも、adapter contract と degraded fallback の自動テストを必ず残してください。

## 非目標

- 生成 AI 本体を agent-gatefield 内に組み込まないでください。
- OpenAI API を必須化しないでください。
- pgvector 既存テストを破壊する削除リファクタを同時に行わないでください。
- Qwen3-Reranker / vLLM を初期既定にしないでください。
- データセットの label / redaction / reviewer shape を緩めないでください。
- 実モデル未取得を理由に BGE-M3 既定値を `local-hash-embedding-v1` へ戻さないでください。
- 既存の 647 tests を減らして検収を通さないでください。

## 完了報告に含める内容

- 変更した主要ファイル
- 採用した runtime / model / vector backend
- 旧 `local-hash-embedding-v1` の扱い
- 検収コマンドと結果
- 残リスク、特にモデルファイル入手・量子化形式・Qdrant 起動手順が未確定の場合の扱い
