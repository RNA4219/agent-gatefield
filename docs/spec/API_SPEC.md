# API Specification

This document specifies the API contracts for the agent-gatefield system. All APIs follow Python-style signatures with explicit type annotations.

## Contract Levels

| Level | Description |
|---|---|
| P0 | Required for MVP. Failure to implement blocks MVP release. |
| P1 | Required for production enforce. Must be implemented before block enforce. |
| P2 | Enhancement. Implementation timing is flexible. |

---

## 1. Harness Adapter API

**Module**: `src/adapters/harness.py`

**Contract Level**: P0 (all methods)

### 1.1 Base Class: HarnessAdapter

```python
class HarnessAdapter(ABC):
    """
    Base adapter for harness integration.
    Implements the contract from requirements AGF-REQ-001.
    """
```

#### subscribe_events()

```python
@abstractmethod
def subscribe_events(self) -> None
```

**Description**: Subscribe to run lifecycle events from the harness.

**Contract**: P0 - Run lifecycle events

**Events to Subscribe**:
| Event Type | Description |
|---|---|
| `run_started` | Run execution begins |
| `step_started` | Individual step begins |
| `tool_call_requested` | Tool execution requested |
| `artifact_emitted` | Artifact produced |
| `static_gate_completed` | Static gate finished |
| `run_completed` | Run finished successfully |
| `run_failed` | Run terminated with error |

**Parameters**: None

**Returns**: None

**Errors**:
| Error | Condition |
|---|---|
| `ConnectionError` | Cannot connect to harness event stream |
| `TimeoutError` | Subscription handshake exceeds timeout |

**Example**:
```python
adapter = GenericHarnessAdapter()
adapter.subscribe_events()
# Now listening for all run lifecycle events
```

---

#### pause_run()

```python
@abstractmethod
def pause_run(self, run_id: str) -> str
```

**Description**: Pause a run and return checkpoint reference for later resume.

**Contract**: P0 - Pause/resume

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `run_id` | `str` | Yes | UUID format | Run to pause |

**Returns**: `str` - Checkpoint reference URI (format: `checkpoint://{run_id}/cp/{checkpoint_id}`)

**Errors**:
| Error | Condition |
|---|---|
| `RunNotFoundError` | Run ID does not exist |
| `RunAlreadyPausedError` | Run is already paused |
| `HarnessPauseError` | Harness cannot pause the run |

**Example**:
```python
checkpoint_ref = adapter.pause_run("run-abc123")
# checkpoint_ref = "checkpoint://run-abc123/cp/cp-001"
```

**Fallback**: If harness cannot pause, hold decision is treated as block (fail closed).

---

#### resume_run()

```python
@abstractmethod
def resume_run(self, run_id: str, checkpoint_ref: str) -> None
```

**Description**: Resume a paused run from specified checkpoint.

**Contract**: P0 - Pause/resume

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `run_id` | `str` | Yes | UUID format | Run to resume |
| `checkpoint_ref` | `str` | Yes | URI format | Checkpoint from pause_run() |

**Returns**: None

**Errors**:
| Error | Condition |
|---|---|
| `CheckpointNotFoundError` | Checkpoint reference invalid |
| `RunNotPausedError` | Run is not in paused state |
| `CheckpointExpiredError` | Checkpoint TTL exceeded |

**Example**:
```python
adapter.resume_run("run-abc123", "checkpoint://run-abc123/cp/cp-001")
# Run continues from checkpoint state
```

---

#### check_tool_policy()

```python
@abstractmethod
def check_tool_policy(self, tool_call: Dict) -> str
```

**Description**: Check tool call against policy before execution.

**Contract**: P0 - Tool policy hook

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `tool_call` | `Dict` | Yes | See schema | Tool call request |

**tool_call Schema**:
```json
{
  "tool_name": "string (required)",
  "tool_args": "dict (optional)",
  "risk_level": "string: low|medium|high|critical",
  "permission_scope": "string: read|write|admin",
  "target_resource": "string (optional)"
}
```

**Returns**: `str` - Policy decision: `deny` | `hold` | `allow`

**Decision Logic**:
| Return | Condition |
|---|---|
| `deny` | Tool matches deny patterns (e.g., `rm -rf /`, `DROP DATABASE`) |
| `hold` | High privilege tool with risk indicators |
| `allow` | Tool passes all policy checks |

**Errors**:
| Error | Condition |
|---|---|
| `InvalidToolCallError` | Missing required fields in tool_call |
| `PolicyCheckError` | Policy engine unavailable |

**Example**:
```python
decision = adapter.check_tool_policy({
    "tool_name": "bash",
    "tool_args": {"command": "rm -rf /tmp/build"},
    "risk_level": "high"
})
# decision = "deny" (matches rm -rf pattern)
```

---

#### get_artifact_snapshot()

```python
@abstractmethod
def get_artifact_snapshot(self, run_id: str) -> ArtifactSnapshot
```

**Description**: Get artifact metadata for state encoding.

**Contract**: P0 - Artifact snapshot

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `run_id` | `str` | Yes | UUID format | Run ID |

**Returns**: `ArtifactSnapshot`

```python
@dataclass
class ArtifactSnapshot:
    run_id: str              # UUID
    artifact_id: str         # UUID
    hash: str                # SHA256 hash
    diff: Optional[str]      # Diff content (redacted)
    source_step: str         # Step that produced artifact
    commit: Optional[str]    # Git commit hash
    branch: Optional[str]    # Git branch name
```

**Errors**:
| Error | Condition |
|---|---|
| `ArtifactNotFoundError` | No artifact for run |
| `HarnessUnavailableError` | Cannot fetch from harness |

**Example**:
```python
snapshot = adapter.get_artifact_snapshot("run-abc123")
print(snapshot.hash)  # "sha256:abc123..."
```

---

#### ingest_static_gate_result()

```python
@abstractmethod
def ingest_static_gate_result(self, result: Dict) -> None
```

**Description**: Import static gate results from CI/scanners.

**Contract**: P0 - Static gate result ingest

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `result` | `Dict` | Yes | See schema | Static gate result |

**result Schema**:
```json
{
  "run_id": "string (required)",
  "gate_name": "string: lint|typecheck|test|sast|secret|license",
  "severity": "string: pass|warn|fail|critical",
  "status": "string: pass|fail",
  "evidence_ref": "string (optional)",
  "details": "dict (optional)"
}
```

**Returns**: None

**Errors**:
| Error | Condition |
|---|---|
| `InvalidGateResultError` | Missing required fields |
| `DuplicateGateResultError` | Result already ingested for run |

**Example**:
```python
adapter.ingest_static_gate_result({
    "run_id": "run-abc123",
    "gate_name": "sast",
    "severity": "critical",
    "status": "fail",
    "evidence_ref": "sast://semgrep/sql-injection"
})
```

---

#### get_trace_context()

```python
@abstractmethod
def get_trace_context(self, run_id: str) -> Dict
```

**Description**: Get trace context for correlation.

**Contract**: P0 - Trace correlation

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `run_id` | `str` | Yes | UUID format | Run ID |

**Returns**: `Dict`

```json
{
  "trace_id": "string (OTel format)",
  "span_id": "string (OTel format)",
  "parent_span_id": "string (optional)",
  "trace_state": "string (optional)"
}
```

**Errors**:
| Error | Condition |
|---|---|
| `TraceNotFoundError` | No trace for run |
| `HarnessUnavailableError` | Cannot fetch trace context |

**Example**:
```python
context = adapter.get_trace_context("run-abc123")
print(context["trace_id"])  # "otel-trace-id-123"
```

---

### 1.2 Data Classes

#### RunEvent

```python
@dataclass
class RunEvent:
    run_id: str                      # UUID
    trace_id: str                    # OTel trace ID
    event_type: str                  # See subscribe_events table
    timestamp: str                   # RFC3339 format
    actor: str                       # agent|tool|reviewer|system
    artifact_ref: Optional[str]      # artifact:// URI
    checkpoint_ref: Optional[str]    # checkpoint:// URI
    payload_ref: Optional[str]       # blob:// URI (redacted or hashed)
```

**Requirement**: AGF-REQ-009 - All events must have trace_id/span_id.

---

#### ArtifactSnapshot

See `get_artifact_snapshot()` return type.

---

### 1.3 Adapter Implementations

| Adapter Class | Target Harness | Special Features |
|---|---|---|
| `GenericHarnessAdapter` | Generic Python harness | Standard OTel tracing |
| `OpenAIAgentsSDKAdapter` | OpenAI Agents SDK | Guardrails, human review, checkpointing |
| `ClaudeCodeAdapter` | Claude Code CLI | PreToolUse/PostToolUse hooks |

---

### 1.4 Harness Registry

```python
class HarnessRegistry:
    adapters: Dict[str, HarnessAdapter] = {}

    def register(self, name: str, adapter: HarnessAdapter) -> None
    def get(self, name: str) -> Optional[HarnessAdapter]
    def detect_harness(self) -> str  # Auto-detect from environment
```

---

## 2. Decision Engine API

**Module**: `src/core/engine.py`

**Contract Level**: P0 (evaluate, apply_hard_overrides), P1 (state transitions)

### 2.1 DecisionEngine Class

```python
class DecisionEngine:
    """State space gate decision engine."""
    
    def __init__(self, config: Dict)
```

**Config Schema**:
```yaml
thresholds:
  taboo_warn: 0.80
  taboo_block: 0.88
  anomaly_warn_percentile: 95
  anomaly_block_percentile: 99
  judge_std_warn: 0.15
  judge_std_block: 0.25

hard_overrides:
  block_if_secret_found: true
  block_if_prod_write_and_taboo_warn: true
  hold_if_high_privilege_and_uncertain: true

scorers:
  constitution_alignment:
    weight: 0.20
  taboo_proximity:
    weight: 0.30
  # ... see Scorers section
```

---

#### evaluate()

```python
def evaluate(self, state_vector: dict) -> dict
```

**Description**: Evaluate state vector and return gate decision.

**Contract**: P0 - Core decision logic (AGF-REQ-003, AGF-REQ-004)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `state_vector` | `dict` | Yes | See State Encoder | Composite state vector |

**Returns**: `dict`

```python
{
    "decision": "pass" | "warn" | "hold" | "block",
    "composite_score": float,         # Weighted score (0.0-1.0)
    "factors": [                      # Top contributing factors
        {"name": "taboo_proximity", "value": 0.85, "weight": 0.30},
        {"name": "anomaly_score", "value": 0.92, "weight": 0.10}
    ],
    "exemplar_refs": [                # Top 5 nearest exemplars (AGF-REQ-003)
        {"doc_id": "taboo-001", "axis": "taboo", "similarity": 0.85},
        {"doc_id": "accepted-023", "axis": "accepted", "similarity": 0.78}
    ],
    "action": str,                    # Recommended action
    "threshold_version": str,         # Config hash for reproducibility
    "static_gate_summary": dict       # Static gate results summary
}
```

**State Transitions** (AGF-REQ-004):
| Input Condition | Decision | Action |
|---|---|---|
| Static hard fail | `block` | Stop run, create correction action |
| Hard override triggered | `block` | Apply override rule |
| High privilege + risk/uncertainty | `hold` | Pause run, enqueue review |
| Composite > warn threshold | `warn` | Self-correction loop (max 2) |
| Composite < warn threshold | `pass` | Continue workflow |

**Errors**:
| Error | Condition |
|---|---|
| `InvalidStateVectorError` | Missing required fields |
| `ScorerUnavailableError` | Scorer calculation failed |
| `KBUnavailableError` | Cannot retrieve judgment KB |

**Example**:
```python
engine = DecisionEngine(config)
result = engine.evaluate(state_vector)

if result["decision"] == "block":
    print(f"Blocked due to: {result['factors'][0]['name']}")
```

---

#### apply_hard_overrides()

```python
def apply_hard_overrides(self, state_vector: dict) -> str | None
```

**Description**: Apply hard override rules before composite scoring.

**Contract**: P0 - Override rules (AGF-REQ-002)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `state_vector` | `dict` | Yes | - | State vector to check |

**Returns**: `str | None` - Override decision (`block`, `hold`) or `None`

**Hard Override Rules**:
| Rule | Condition | Return |
|---|---|---|
| `block_if_secret_found` | `rule_violation.secret > 0` | `block` |
| `block_if_prod_write_and_taboo_warn` | `risk.prod_write == 1` and taboo > warn threshold | `block` |
| `hold_if_high_privilege_and_uncertain` | High privilege tool and `uncertainty.judge_std > warn` | `hold` |

**Priority**: Hard override > Tool policy > Data protection > Reviewer > Composite

**Example**:
```python
override = engine.apply_hard_overrides(state_vector)
if override == "block":
    # Immediate block, skip composite evaluation
    return {"decision": "block", "reason": "secret_found"}
```

---

### 2.2 State Transition Logic

**State Flow**:
```
pass → warn → hold → block
         ↑      |
         |      v
         └── self-correction (max 2)
```

**Transition Rules**:
| Current | Condition | Next | Max Retries |
|---|---|---|---|
| `pass` | composite > warn | `warn` | - |
| `warn` | self-correction succeeds | `pass` | 2 |
| `warn` | self-correction fails 2x | `hold` | - |
| `warn` | same reason 3x | `hold` | - |
| `hold` | reviewer approves | `pass` | - |
| `hold` | reviewer rejects | `block` | - |
| `hold` | SLA timeout | `block` | fail closed |

---

## 3. State Encoder API

**Module**: `src/encoder/state_encoder.py`

**Contract Level**: P0

### 3.1 StateEncoder Class

```python
class StateEncoder:
    """Encode artifacts, traces, and rules into composite state vectors."""
    
    def __init__(self, embedding_config: dict)
```

**embedding_config Schema**:
```yaml
provider: local
model: local-hash-embedding-v1
dimensions: 1536  # or 3072, or reduced via dimensions param
```

---

#### encode()

```python
def encode(self, artifact: dict, trace: dict, rule_results: dict) -> dict
```

**Description**: Generate composite state vector from inputs.

**Contract**: P0 - State vector generation (AGF-REQ-001)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `artifact` | `dict` | Yes | See schema | Artifact information |
| `trace` | `dict` | Yes | See schema | Execution trace |
| `rule_results` | `dict` | Yes | See schema | Static gate results |

**artifact Schema**:
```json
{
  "run_id": "uuid (required)",
  "artifact_id": "uuid (required)",
  "hash": "sha256 (required)",
  "diff": "string (optional, redacted)",
  "type": "code_patch|document_diff|tool_execution_plan|pr_proposal",
  "repo": "string",
  "env": "local|ci|staging|production_shadow|production_enforce"
}
```

**trace Schema**:
```json
{
  "tool_calls": "int",
  "tool_errors": "int",
  "branches": "int",
  "test_results": {
    "pass_rate": "float",
    "modules_tested": "int"
  }
}
```

**rule_results Schema**:
```json
{
  "secret_scan": {"count": "int", "types": "list"},
  "sast": {"high_count": "int", "medium_count": "int"},
  "license": {"unknown_count": "int"},
  "lint": {"errors": "int", "warnings": "int"}
}
```

**Returns**: `dict` - State vector

```json
{
  "run_id": "uuid",
  "artifact_id": "uuid",
  "semantic": {
    "provider": "local",
    "model": "local-hash-embedding-v1",
    "dims": 1536,
    "vector_ref": "vec://..."
  },
  "rule_violation": {
    "secret": 0,
    "sast_high": 1,
    "sast_medium": 2,
    "license_unknown": 0
  },
  "test_evidence": {
    "unit_pass_rate": 0.97,
    "changed_modules_tested": 4
  },
  "risk": {
    "prod_write": 0,
    "pii_level": 1,
    "network_egress": 1
  },
  "historical_decision": {
    "accept_sim": 0.84,
    "reject_sim": 0.31,
    "judgment_log_sim": 0.66
  },
  "uncertainty": {
    "judge_std": 0.08,
    "tool_error_rate": 0.02,
    "self_confidence": 0.74
  },
  "context": {
    "repo": "service-a",
    "artifact_type": "code_patch",
    "env": "staging"
  },
  "trajectory": {
    "delta_semantic": 0.07,
    "tool_calls": 9,
    "branch_count": 2
  }
}
```

**Errors**:
| Error | Condition |
|---|---|
| `InvalidArtifactError` | Missing required fields |
| `EmbeddingError` | Configured embedding provider unavailable |
| `ClassificationError` | Cannot classify data protection |

**Example**:
```python
encoder = StateEncoder({"provider": "local", "model": "local-hash-embedding-v1", "dimensions": 1536})
state = encoder.encode(artifact, trace, rule_results)
```

---

### 3.2 Sub-Encoder Methods

#### _encode_semantic()

```python
def _encode_semantic(self, artifact: dict) -> dict
```

**Description**: Generate semantic embedding from artifact.

**Returns**:
```json
{
  "provider": "local",
  "model": "local-hash-embedding-v1",
  "dims": 1536,
  "vector_ref": "vec://sha256-hash"
}
```

---

#### _encode_rule_violation()

```python
def _encode_rule_violation(self, rule_results: dict) -> dict
```

**Description**: Encode static gate results as sparse severity vector.

**Returns**:
```json
{
  "secret": int,
  "sast_high": int,
  "sast_medium": int,
  "license_unknown": int
}
```

---

#### _encode_test_evidence()

```python
def _encode_test_evidence(self, trace: dict) -> dict
```

**Description**: Encode test coverage metrics.

**Returns**:
```json
{
  "unit_pass_rate": float,
  "changed_modules_tested": int
}
```

---

#### _encode_risk()

```python
def _encode_risk(self, artifact: dict) -> dict
```

**Description**: Encode risk context from artifact metadata.

**Returns**:
```json
{
  "prod_write": 0|1,
  "pii_level": 0|1|2|3,
  "network_egress": 0|1
}
```

---

#### _encode_uncertainty()

```python
def _encode_uncertainty(self, trace: dict) -> dict
```

**Description**: Encode uncertainty metrics.

**Returns**:
```json
{
  "judge_std": float,
  "tool_error_rate": float,
  "self_confidence": float
}
```

---

#### _encode_context()

```python
def _encode_context(self, artifact: dict) -> dict
```

**Description**: Encode metadata for filtering.

**Returns**:
```json
{
  "repo": str,
  "artifact_type": str,
  "env": str
}
```

---

#### _encode_trajectory()

```python
def _encode_trajectory(self, trace: dict) -> dict
```

**Description**: Encode trajectory features for drift/anomaly.

**Returns**:
```json
{
  "delta_semantic": float,
  "tool_calls": int,
  "branch_count": int
}
```

---

## 4. Vector Store API

**Module**: `src/vector_store/__init__.py`

**Contract Level**: P0 (search, insert, centroid), P1 (deprecate, state vectors)

### 4.1 VectorStore Class

```python
class VectorStore:
    """pgvector client for judgment knowledge base."""
    
    def __init__(self, connection_string: str)
```

---

#### search_similar()

```python
def search_similar(
    self,
    query_vector: list[float],
    axis_type: str,
    limit: int = 10
) -> list[SearchResult]
```

**Description**: Similarity search using cosine distance.

**Contract**: P0 - KB retrieval (AGF-REQ-003)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `query_vector` | `list[float]` | Yes | dims match config | Query embedding |
| `axis_type` | `str` | Yes | See axis types | Judgment axis to search |
| `limit` | `int` | No | 1-100, default 10 | Max results |

**axis_type Values**:
| Value | Description |
|---|---|
| `constitution` | Design principles |
| `taboo` | Forbidden patterns |
| `accepted` | Accepted examples |
| `rejected` | Rejected examples |
| `judgment_log` | Historical decisions |

**Returns**: `list[SearchResult]`

```python
@dataclass
class SearchResult:
    doc_id: str           # Document ID
    similarity: float     # Cosine similarity (0-1)
    axis_type: str        # Judgment axis
    text: str             # Document content (redacted if needed)
```

**Errors**:
| Error | Condition |
|---|---|
| `VectorDimensionMismatchError` | Query dims != stored dims |
| `InvalidAxisTypeError` | Unknown axis type |
| `DatabaseConnectionError` | pgvector unavailable |

**Example**:
```python
results = vs.search_similar(query_vector, "taboo", limit=5)
for r in results:
    print(f"Similarity: {r.similarity}, Doc: {r.doc_id}")
```

---

#### insert_embedding()

```python
def insert_embedding(
    self,
    doc_id: str,
    model: str,
    dims: int,
    embedding: list[float],
    content_hash: str
) -> str
```

**Description**: Insert new embedding (append-only versioning).

**Contract**: P0 - KB storage

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `doc_id` | `str` | Yes | UUID | Document reference |
| `model` | `str` | Yes | Embedding model name | Model used |
| `dims` | `int` | Yes | 1536/3072/custom | Vector dimensions |
| `embedding` | `list[float]` | Yes | len == dims | Vector data |
| `content_hash` | `str` | Yes | SHA256 | Content hash for dedup |

**Returns**: `str` - Embedding ID

**Versioning**: Append-only. Previous embedding valid_to is set on deprecation.

**Errors**:
| Error | Condition |
|---|---|
| `DuplicateEmbeddingError` | Same content_hash exists |
| `DimensionMismatchError` | dims != len(embedding) |
| `DatabaseInsertError` | Insert failed |

**Example**:
```python
embed_id = vs.insert_embedding(
    doc_id="taboo-001",
    model="local-hash-embedding-v1",
    dims=1536,
    embedding=[0.1, 0.2, ...],
    content_hash="sha256:abc..."
)
```

---

#### deprecate_embedding()

```python
def deprecate_embedding(self, doc_id: str) -> None
```

**Description**: Mark old embedding as deprecated by setting valid_to.

**Contract**: P1 - Model migration

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `doc_id` | `str` | Yes | UUID | Document to deprecate |

**Returns**: None

**Behavior**: Sets `valid_to = NOW()` on current active embedding for doc.

**Errors**:
| Error | Condition |
|---|---|
| `EmbeddingNotFoundError` | No active embedding for doc |
| `AlreadyDeprecatedError` | Embedding already has valid_to |

---

#### get_active_embeddings()

```python
def get_active_embeddings(self, axis_type: str) -> list[dict]
```

**Description**: Get all active embeddings for an axis.

**Contract**: P1 - Centroid calculation

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `axis_type` | `str` | Yes | See axis types | Axis to query |

**Returns**: `list[dict]`

```json
[
  {
    "doc_id": "str",
    "model": "str",
    "dims": "int",
    "content_hash": "str",
    "valid_from": "datetime",
    "valid_to": null
  }
]
```

---

#### insert_state_vector()

```python
def insert_state_vector(self, state_vector: dict) -> None
```

**Description**: Store state vector for a run.

**Contract**: P0 - State persistence (AGF-REQ-001)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `state_vector` | `dict` | Yes | See encode() | Full state vector |

**Returns**: None

---

#### get_centroid()

```python
def get_centroid(self, axis_type: str) -> list[float]
```

**Description**: Calculate centroid for an axis.

**Contract**: P0 - Constitution alignment scoring

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `axis_type` | `str` | Yes | `constitution` | Axis for centroid |

**Returns**: `list[float]` - Average vector of axis embeddings

**SQL Logic**:
```sql
SELECT AVG(embedding) FROM judgment_embeddings 
WHERE axis_type = $1 AND valid_to IS NULL
```

**Errors**:
| Error | Condition |
|---|---|
| `EmptyAxisError` | No embeddings for axis |
| `DimensionMismatchError` | Embeddings have different dims |

---

### 4.2 JudgmentKB Class

```python
class JudgmentKB:
    """Judgment knowledge base manager."""
    
    def __init__(self, vector_store: VectorStore)
```

---

#### import_document()

```python
def import_document(
    self,
    axis_type: str,
    text: str,
    source_type: str = 'manual',
    scope: str = None,
    labels: dict = None
) -> str
```

**Description**: Import new judgment document.

**Contract**: P1 - KB management

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `axis_type` | `str` | Yes | See axis types | Target axis |
| `text` | `str` | Yes | Redacted if needed | Document content |
| `source_type` | `str` | No | `manual\|incident\|review` | Source type |
| `scope` | `str` | No | repo/service scope | Applicability |
| `labels` | `dict` | No | Arbitrary | Additional labels |

**Returns**: `str` - Document ID

---

#### promote_from_run()

```python
def promote_from_run(
    self,
    run_id: str,
    axis_type: str = 'judgment_log',
    decision: str = None,
    comment: str = None
) -> str
```

**Description**: Promote run outcome to judgment log.

**Contract**: P1 - Human correction feedback (AGF-REQ-005)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `run_id` | `str` | Yes | UUID | Run to promote |
| `axis_type` | `str` | No | Default `judgment_log` | Target axis |
| `decision` | `str` | No | pass/block | Original decision |
| `comment` | `str` | No | Redacted | Reviewer comment |

**Returns**: `str` - Document ID

---

#### get_taboo_topk()

```python
def get_taboo_topk(self, query_vector: list[float], k: int = 5) -> list[SearchResult]
```

**Description**: Get top-k taboo examples.

**Returns**: `list[SearchResult]` - Most similar taboo items

---

#### get_accepted_topk()

```python
def get_accepted_topk(self, query_vector: list[float], k: int = 5) -> list[SearchResult]
```

**Description**: Get top-k accepted examples.

**Returns**: `list[SearchResult]` - Most similar accepted items

---

#### get_rejected_topk()

```python
def get_rejected_topk(self, query_vector: list[float], k: int = 5) -> list[SearchResult]
```

**Description**: Get top-k rejected examples.

**Returns**: `list[SearchResult]` - Most similar rejected items

---

#### get_constitution_centroid()

```python
def get_constitution_centroid(self) -> list[float]
```

**Description**: Get constitution centroid for alignment scoring.

**Returns**: `list[float]` - Centroid vector

---

## 5. Review Queue API

**Module**: `src/review/queue.py`

**Contract Level**: P1 (all methods)

### 5.1 ReviewQueue Class

```python
class ReviewQueue:
    """Human review queue manager."""
```

---

#### enqueue()

```python
def enqueue(self, item: ReviewItem) -> None
```

**Description**: Add item to review queue.

**Contract**: P1 - Human review queue (AGF-REQ-004)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `item` | `ReviewItem` | Yes | See schema | Review item |

**ReviewItem Schema**:
```python
@dataclass
class ReviewItem:
    decision_id: str                    # UUID
    run_id: str                         # UUID
    state: str                          # pass|warn|hold|block
    composite_score: float              # 0.0-1.0
    severity: str                       # critical|high|medium|low
    top_factors: List[str]              # Top contributing factors
    exemplar_refs: List[str]            # Top 5 exemplars
    artifact_ref: str                   # artifact:// URI
    trace_ref: str                      # trace:// URI
    created_at: datetime                # Enqueue timestamp
    assigned_to: Optional[str]          # Reviewer assignment
    taken_at: Optional[datetime]        # Take timestamp
```

**Returns**: None

**SLA**:
| Severity | ACK Time | Decision Time |
|---|---|---|
| Critical | 15 min | 60 min |
| High | 60 min | 240 min |
| Medium | Same business day | Next business day |
| Low | N/A | backlog |

**Errors**:
| Error | Condition |
|---|---|
| `DuplicateItemError` | decision_id already in queue |
| `QueueCapacityError` | Queue exceeds capacity |

---

#### take()

```python
def take(self, severity: str = None, reviewer: str = None) -> Optional[ReviewItem]
```

**Description**: Take an item from queue.

**Contract**: P1 - Review workflow

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `severity` | `str` | No | critical\|high\|medium\|low | Filter by severity |
| `reviewer` | `str` | No | - | Assign to reviewer |

**Returns**: `Optional[ReviewItem]` - Next item or None if empty

**Selection Logic**:
1. Filter by severity (if specified)
2. Sort by created_at (oldest first)
3. Set assigned_to and taken_at
4. Return item

**Example**:
```python
item = queue.take(severity="critical", reviewer="john.doe")
if item:
    print(f"Reviewing {item.decision_id}")
```

---

#### resolve()

```python
def resolve(
    self,
    decision_id: str,
    reviewer: str,
    decision: ReviewDecision,
    comment: str,
    correction: Dict = None
) -> None
```

**Description**: Resolve a review.

**Contract**: P1 - Review resolution (AGF-REQ-005)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `decision_id` | `str` | Yes | UUID | Item to resolve |
| `reviewer` | `str` | Yes | - | Reviewer ID |
| `decision` | `ReviewDecision` | Yes | See enum | Decision |
| `comment` | `str` | Yes | Redacted | Review comment |
| `correction` | `Dict` | No | See schema | Correction data |

**ReviewDecision Enum**:
| Value | Description |
|---|---|
| `APPROVE` | Accept run, resume from checkpoint |
| `REJECT` | Block run, create correction action |
| `RECALIBRATE` | Adjust weights/thresholds |
| `REQUEST_ARTIFACT_CORRECTION` | Request artifact modification |
| `REQUEST_PROCESS_CORRECTION` | Request process adjustment |
| `ADD_JUDGMENT_NOTE` | Add note without changing decision |

**correction Schema**:
```json
{
  "correction_type": "artifact|process|prompt",
  "target": "string",
  "details": "dict"
}
```

**Returns**: None

**Post-Resolution Actions**:
| Decision | Action |
|---|---|
| `APPROVE` | Resume run from checkpoint |
| `REJECT` | Create correction action, block run |
| `RECALIBRATE` | Update calibration profile |
| `REQUEST_*` | Trigger correction workflow |
| `ADD_JUDGMENT_NOTE` | Promote to judgment_log |

**Errors**:
| Error | Condition |
|---|---|
| `ItemNotFoundError` | decision_id not in queue |
| `UnauthorizedReviewerError` | reviewer not assigned |

---

#### get_pending()

```python
def get_pending(self, severity: str = None) -> List[ReviewItem]
```

**Description**: Get pending items.

**Returns**: `List[ReviewItem]` - All pending items matching filter

---

#### get_stats()

```python
def get_stats(self) -> Dict
```

**Description**: Get queue statistics.

**Returns**:
```json
{
  "total_pending": int,
  "by_severity": {
    "critical": int,
    "high": int,
    "medium": int,
    "low": int
  },
  "total_resolved": int,
  "avg_resolution_time": float,
  "sla_compliance": {
    "critical": float,
    "high": float
  }
}
```

---

## 6. Audit Logger API

**Module**: `src/audit/logger.py`

**Contract Level**: P0 (log_event, log_decision, export), P1 (log_review, log_correction)

### 6.1 AuditLogger Class

```python
class AuditLogger:
    """Audit event logger with OTel compatibility."""
```

---

#### log_event()

```python
def log_event(
    self,
    trace_id: str,
    span_id: str,
    run_id: str,
    event_type: str,
    actor: str,
    payload: Dict = None,
    retention_class: str = "audit"
) -> AuditEvent
```

**Description**: Log an audit event.

**Contract**: P0 - Audit logging (AGF-REQ-009)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `trace_id` | `str` | Yes | OTel format | Trace ID |
| `span_id` | `str` | Yes | OTel format | Span ID |
| `run_id` | `str` | Yes | UUID | Run ID |
| `event_type` | `str` | Yes | See event types | Event type |
| `actor` | `str` | Yes | agent\|tool\|reviewer\|system | Actor |
| `payload` | `Dict` | No | Redacted | Event payload |
| `retention_class` | `str` | No | audit\|ops\|pii-sensitive | Retention class |

**event_type Values**:
| Value | Description |
|---|---|
| `gate_decision` | Gate decision event |
| `human_review` | Review action |
| `correction` | Correction action |
| `static_gate_result` | Static gate result |
| `run_lifecycle` | Run lifecycle event |

**Returns**: `AuditEvent`

```python
@dataclass
class AuditEvent:
    trace_id: str
    span_id: str
    run_id: str
    event_type: str
    actor: str
    payload_hash: str           # SHA256 hash
    payload_ref: Optional[str]  # Blob reference
    retention_class: str
```

**Retention**:
| Class | Duration |
|---|---|
| `audit` | 365 days |
| `ops` | 90 days |
| `pii-sensitive` | 30 days (redacted only) |

---

#### log_decision()

```python
def log_decision(
    self,
    trace_id: str,
    run_id: str,
    decision: Dict
) -> AuditEvent
```

**Description**: Log gate decision.

**Contract**: P0 - Decision audit (AGF-REQ-009)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `trace_id` | `str` | Yes | OTel format | Trace ID |
| `run_id` | `str` | Yes | UUID | Run ID |
| `decision` | `Dict` | Yes | See evaluate() | Decision packet |

**Returns**: `AuditEvent`

**Required Fields in decision**:
- `decision` (pass/warn/hold/block)
- `threshold_version`
- `action_type`
- `factors` (top 3)
- `exemplar_refs` (top 5)

---

#### log_review()

```python
def log_review(
    self,
    trace_id: str,
    run_id: str,
    review: Dict
) -> AuditEvent
```

**Description**: Log human review action.

**Contract**: P1 - Review audit

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `trace_id` | `str` | Yes | OTel format | Trace ID |
| `run_id` | `str` | Yes | UUID | Run ID |
| `review` | `Dict` | Yes | See resolve() | Review action |

**Returns**: `AuditEvent`

---

#### log_correction()

```python
def log_correction(
    self,
    trace_id: str,
    run_id: str,
    correction: Dict
) -> AuditEvent
```

**Description**: Log correction action.

**Contract**: P1 - Correction audit

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `trace_id` | `str` | Yes | OTel format | Trace ID |
| `run_id` | `str` | Yes | UUID | Run ID |
| `correction` | `Dict` | Yes | See resolve() | Correction data |

**Returns**: `AuditEvent`

---

#### export_otlp()

```python
def export_otlp(self) -> list[Dict]
```

**Description**: Export events in OTLP format.

**Contract**: P0 - OTel compatibility (AGF-REQ-009)

**Returns**: `list[Dict]` - OTLP log records

```json
[
  {
    "traceId": "string",
    "spanId": "string",
    "timeUnixNano": "int",
    "attributes": {
      "run_id": "string",
      "event_type": "string",
      "actor": "string",
      "payload_hash": "string",
      "retention_class": "string"
    }
  }
]
```

---

#### export_jsonl()

```python
def export_jsonl(self) -> str
```

**Description**: Export events as JSONL.

**Contract**: P1 - SIEM export

**Returns**: `str` - JSONL string (one event per line)

---

#### get_by_run()

```python
def get_by_run(self, run_id: str) -> list[AuditEvent]
```

**Description**: Get all events for a run.

**Parameters**:
| Name | Type | Required | Description |
|---|---|---|---|
| `run_id` | `str` | Yes | Run ID |

**Returns**: `list[AuditEvent]`

---

## 7. Calibration API

**Module**: `src/core/calibration.py`

**Contract Level**: P1

### 7.1 CalibrationPipeline Class

```python
class CalibrationPipeline:
    """Threshold calibration from accepted/rejected distributions."""
    
    def __init__(self, profile_id: str)
```

---

#### calibrate_taboo_threshold()

```python
def calibrate_taboo_threshold(
    self,
    accepted_scores: List[float],
    rejected_scores: List[float],
    percentile: int = 95
) -> CalibrationResult
```

**Description**: Set taboo threshold based on accepted distribution percentile.

**Contract**: P1 - Threshold calibration (AGF-REQ-005)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `accepted_scores` | `List[float]` | Yes | 0.0-1.0 | Taboo scores for accepted items |
| `rejected_scores` | `List[float]` | Yes | 0.0-1.0 | Taboo scores for rejected items |
| `percentile` | `int` | No | 90-99, default 95 | Percentile for warn |

**Returns**: `CalibrationResult`

```python
@dataclass
class CalibrationResult:
    axis: str               # "taboo"
    old_threshold: float    # Previous threshold
    new_threshold: float    # Calculated threshold
    sample_size: int        # Number of samples
    metric_name: str        # "accepted_p95"
    metric_value: float     # Threshold value
```

---

#### calibrate_anomaly_percentile()

```python
def calibrate_anomaly_percentile(
    self,
    anomaly_scores: List[float],
    warn_percentile: int = 95,
    block_percentile: int = 99
) -> Dict
```

**Description**: Set anomaly thresholds from contamination estimate.

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `anomaly_scores` | `List[float]` | Yes | 0.0-1.0 | Anomaly scores |
| `warn_percentile` | `int` | No | 90-99, default 95 | Warn percentile |
| `block_percentile` | `int` | No | 95-99, default 99 | Block percentile |

**Returns**: `Dict`

```json
{
  "warn_threshold": float,
  "block_threshold": float
}
```

---

#### compute_metrics()

```python
def compute_metrics(
    self,
    predictions: List[str],
    labels: List[str]
) -> Dict
```

**Description**: Compute precision, recall, F1.

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `predictions` | `List[str]` | Yes | pass\|block | Predicted labels |
| `labels` | `List[str]` | Yes | pass\|block | Ground truth labels |

**Returns**: `Dict`

```json
{
  "precision": float,
  "recall": float,
  "f1": float,
  "tp": int,
  "fp": int,
  "tn": int,
  "fn": int
}
```

---

#### run_offline_eval()

```python
def run_offline_eval(
    self,
    dataset_path: str,
    threshold_version: str
) -> Dict
```

**Description**: Run offline evaluation on curated dataset.

**Contract**: P1 - Offline evaluation (AGF-REQ-007)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `dataset_path` | `str` | Yes | .jsonl file | Dataset path |
| `threshold_version` | `str` | Yes | Version ID | Threshold version |

**Returns**: `Dict` - Metrics and results

**Acceptance Criteria**:
| Metric | Target |
|---|---|
| Taboo recall | 0.90+ |
| AUC | 0.85+ |
| PR-AUC | 0.80+ |

---

#### save_profile()

```python
def save_profile(self) -> Dict
```

**Description**: Save calibration profile to database.

**Returns**: `Dict` - Saved profile

```json
{
  "profile_id": "str",
  "results": [...],
  "updated_at": "datetime"
}
```

---

## 8. Scorers API

**Module**: `src/scorers/__init__.py`

**Contract Level**: P0 (all scorers)

### 8.1 Scorer Classes

Each scorer follows this pattern:

```python
class ScorerNameScorer:
    def __init__(self, weight: float)
    def score(self, ...) -> float
```

---

#### ConstitutionAlignmentScorer

```python
class ConstitutionAlignmentScorer:
    """Design constitution alignment score."""
    
    def __init__(self, weight: float = 0.20)
    
    def score(self, semantic_vector: list, constitution_centroid: list) -> float
```

**Formula**: `cosine(semantic, constitution_centroid)`

**Returns**: `float` - 0.0 to 1.0 (higher = more aligned)

---

#### TabooProximityScorer

```python
class TabooProximityScorer:
    """Taboo proximity score."""
    
    def __init__(self, weight: float = 0.30)
    
    def score(self, semantic_vector: list, taboo_topk: list) -> float
```

**Formula**: `max cosine(semantic, taboo_topk)`

**Returns**: `float` - 0.0 to 1.0 (higher = closer to taboo)

**Thresholds**:
| Level | Threshold |
|---|---|
| Warn | 0.80 (P95) |
| Block | 0.88 (P99) |

---

#### AcceptSimilarityScorer

```python
class AcceptSimilarityScorer:
    """Accepted example similarity score."""
    
    def __init__(self, weight: float = 0.10)
    
    def score(self, semantic_vector: list, accepted_topk: list) -> float
```

**Formula**: `max cosine(semantic, accepted_topk)`

**Returns**: `float` - 0.0 to 1.0 (higher = closer to accepted)

---

#### RejectSimilarityScorer

```python
class RejectSimilarityScorer:
    """Rejected example similarity score."""
    
    def __init__(self, weight: float = 0.15)
    
    def score(self, semantic_vector: list, rejected_topk: list) -> float
```

**Formula**: `max cosine(semantic, rejected_topk)`

**Returns**: `float` - 0.0 to 1.0 (higher = closer to rejected)

---

#### DriftScorer

```python
class DriftScorer:
    """Trajectory drift score."""
    
    def __init__(self, weight: float = 0.10)
    
    def score(self, current_vector: list, ewma_accepted: list) -> float
```

**Formula**: `1 - cosine(current, ewma_accepted)`

**Returns**: `float` - 0.0 to 1.0 (higher = more drift)

---

#### AnomalyScorer

```python
class AnomalyScorer:
    """Anomaly score (Isolation Forest / Mahalanobis)."""
    
    def __init__(self, weight: float = 0.10)
    
    def score(self, trajectory_features: dict) -> float
```

**Methods**: Isolation Forest for trajectory, Mahalanobis for semantic

**Returns**: `float` - Anomaly percentile (top 5% = warn, top 1% = block)

---

#### UncertaintyScorer

```python
class UncertaintyScorer:
    """Uncertainty score."""
    
    def __init__(self, weight: float = 0.05)
    
    def score(
        self,
        judge_std: float,
        self_confidence: float,
        tool_error_rate: float
    ) -> float
```

**Formula**: `(judge_std + (1 - self_confidence) + tool_error_rate) / 3`

**Returns**: `float` - 0.0 to 1.0 (higher = more uncertain)

---

## 9. Distance API

**Module**: `src/core/distance.py`

**Contract Level**: P0

### 9.1 Functions

#### cosine_similarity()

```python
def cosine_similarity(v1: List[float], v2: List[float]) -> float
```

**Description**: Calculate cosine similarity between two vectors.

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `v1` | `List[float]` | Yes | Same length | First vector |
| `v2` | `List[float]` | Yes | Same length | Second vector |

**Returns**: `float` - -1.0 to 1.0 (1.0 = identical)

**Errors**:
| Error | Condition |
|---|---|
| `ValueError` | Vector lengths differ |

---

#### cosine_distance()

```python
def cosine_distance(v1: List[float], v2: List[float]) -> float
```

**Returns**: `float` - `1 - cosine_similarity`

---

#### max_cosine_similarity()

```python
def max_cosine_similarity(query: List[float], vectors: List[List[float]]) -> float
```

**Returns**: `float` - Maximum similarity between query and vectors

---

#### top_k_similar()

```python
def top_k_similar(
    query: List[float],
    vectors: List[List[float]],
    k: int = 5
) -> List[tuple[int, float]]
```

**Returns**: `List[tuple]` - (index, similarity) pairs sorted by similarity

---

#### euclidean_distance()

```python
def euclidean_distance(v1: List[float], v2: List[float]) -> float
```

---

#### mahalanobis_distance()

```python
def mahalanobis_distance(
    vector: List[float],
    mean: List[float],
    covariance_inv: List[List[float]]
) -> float
```

**Description**: Calculate Mahalanobis distance for anomaly detection.

---

## 10. Replay API

**Module**: `src/core/replay.py`

**Contract Level**: P1

### 10.1 ReplayEngine Class

```python
class ReplayEngine:
    """Replay past runs with specific threshold/policy versions."""
```

---

#### replay_run()

```python
def replay_run(
    self,
    run_id: str,
    threshold_version: str,
    policy_version: str = None
) -> ReplayResult
```

**Description**: Replay historical run with specified versions.

**Contract**: P1 - Replay reproducibility (AGF-REQ-007, AGF-REQ-010)

**Parameters**:
| Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `run_id` | `str` | Yes | UUID | Run to replay |
| `threshold_version` | `str` | Yes | Version hash | Threshold version |
| `policy_version` | `str` | No | Version hash | Policy version |

**Returns**: `ReplayResult`

```python
@dataclass
class ReplayResult:
    original_decision: str           # Original gate decision
    replay_decision: str             # Replay gate decision
    threshold_version: str           # Threshold version used
    policy_version: str              # Policy version used
    match: bool                      # Decisions match
    diff_explanation: Optional[str]  # Explanation if mismatch
```

**Acceptance**: 99% reproducibility required.

---

#### verify_reproducibility()

```python
def verify_reproducibility(self, sample_runs: list[str]) -> float
```

**Returns**: `float` - Match rate (target 99%+)

---

#### explain_difference()

```python
def explain_difference(self, original: Dict, replay: Dict) -> str
```

**Returns**: `str` - Explanation for decision difference

---

#### batch_replay()

```python
def batch_replay(
    self,
    run_ids: list[str],
    threshold_version: str
) -> list[ReplayResult]
```

---

## 11. Embedding Worker API

**Module**: `src/encoder/embedding_worker.py`

**Contract Level**: P1

### 11.1 EmbeddingWorker Class

```python
class EmbeddingWorker:
    """Worker for generating embeddings."""
    
    def __init__(
        self,
        provider: str = "local",
        model: str = "local-hash-embedding-v1",
        dims: int = 1536
    )
```

---

#### compute_hash()

```python
def compute_hash(self, text: str) -> str
```

**Returns**: `str` - SHA256 content hash (64 chars)

---

#### create_job()

```python
def create_job(self, doc_id: str, text: str) -> EmbeddingJob
```

**Returns**: `EmbeddingJob`

```python
@dataclass
class EmbeddingJob:
    doc_id: str
    text: str
    model: str
    dims: int
    content_hash: str
    status: str  # pending|processing|completed|failed
```

---

#### process_job()

```python
def process_job(self, job: EmbeddingJob) -> List[float]
```

**Returns**: `List[float]` - Embedding vector

---

#### batch_process()

```python
def batch_process(self, jobs: List[EmbeddingJob]) -> Dict[str, List[float]]
```

**Returns**: `Dict` - {doc_id: embedding}

---

#### re_embed_all()

```python
def re_embed_all(self, axis_type: str, new_model: str, new_dims: int) -> None
```

**Description**: Re-embed all documents with new model (dual-write period).

---

### 11.2 ReEmbedJob Class

```python
class ReEmbedJob:
    """Scheduled job for embedding model migration."""
    
    def __init__(self, axis_type: str, old_model: str, new_model: str)
    
    def execute(self) -> None
```

**Migration Steps**:
1. Generate new embeddings, keep old ones active
2. Validate new embeddings
3. Set valid_to on old embeddings
4. Recalibrate thresholds

---

## 12. CLI API

**Module**: `cli/gate_cli.py`

**Contract Level**: P2

### 12.1 Exit Codes

| Code | Constant | Description |
|---|---|---|
| 0 | `EXIT_SUCCESS` | Success |
| 1 | `EXIT_VALIDATION_ERROR` | Validation error |
| 2 | `EXIT_GATE_BLOCK` | Gate blocked |
| 3 | `EXIT_GATE_HOLD` | Gate held for review |
| 4 | `EXIT_CONFIG_ERROR` | Configuration error |
| 5 | `EXIT_INFRA_ERROR` | Infrastructure error |

---

### 12.2 Commands

#### harness gate dry-run

```bash
harness gate dry-run --run-id RUN_ID [--config CONFIG_FILE]
```

**Description**: Dry-run gate evaluation without blocking.

**Parameters**:
| Option | Required | Default | Description |
|---|---|---|---|
| `--run-id` | Yes | - | Run ID to evaluate |
| `--config` | No | `gate-config.yaml` | Config file path |

**Exit Codes**: 0 (pass), 2 (block), 3 (hold), 4 (config error)

---

#### harness gate score

```bash
harness gate score --run-id RUN_ID --artifact ARTIFACT_FILE [--json]
```

**Description**: Score an artifact.

**Parameters**:
| Option | Required | Default | Description |
|---|---|---|---|
| `--run-id` | Yes | - | Run ID |
| `--artifact` | Yes | - | Artifact file path |
| `--json` | No | false | JSON output |

---

#### harness gate explain

```bash
harness gate explain --decision-id DECISION_ID
```

**Description**: Explain a decision.

**Parameters**:
| Option | Required | Description |
|---|---|---|
| `--decision-id` | Yes | Decision ID to explain |

---

#### harness gate review take

```bash
harness gate review take [--severity SEVERITY] [--reviewer REVIEWER]
```

**Description**: Take a review item from queue.

**Parameters**:
| Option | Required | Values | Description |
|---|---|---|---|
| `--severity` | No | critical/high/medium/low | Filter by severity |
| `--reviewer` | No | - | Reviewer name |

---

#### harness gate review resolve

```bash
harness gate review resolve --decision-id DECISION_ID --action ACTION [--comment COMMENT]
```

**Description**: Resolve a review.

**Parameters**:
| Option | Required | Values | Description |
|---|---|---|---|
| `--decision-id` | Yes | - | Decision ID |
| `--action` | Yes | approve/reject/recalibrate/request_correction | Resolution action |
| `--comment` | No | - | Review comment |

---

#### harness gate kb import

```bash
harness gate kb import --axis AXIS_TYPE --file FILE_PATH
```

**Description**: Import judgment documents.

**Parameters**:
| Option | Required | Values | Description |
|---|---|---|---|
| `--axis` | Yes | constitution/taboo/accepted/rejected/judgment_log | Target axis |
| `--file` | Yes | - | File to import |

---

#### harness gate kb promote

```bash
harness gate kb promote --from-run RUN_ID [--axis AXIS_TYPE]
```

**Description**: Promote run to judgment log.

**Parameters**:
| Option | Required | Default | Description |
|---|---|---|---|
| `--from-run` | Yes | - | Run ID |
| `--axis` | No | judgment_log | Target axis |

---

#### harness gate calibrate

```bash
harness gate calibrate --dataset DATASET_FILE [--profile PROFILE_ID]
```

**Description**: Run calibration.

**Parameters**:
| Option | Required | Description |
|---|---|---|
| `--dataset` | Yes | Dataset file path |
| `--profile` | No | Profile ID to update |

---

#### harness gate replay

```bash
harness gate replay --run-id RUN_ID [--from-checkpoint CHECKPOINT] [--threshold-version VERSION]
```

**Description**: Replay a run.

**Parameters**:
| Option | Required | Description |
|---|---|---|
| `--run-id` | Yes | Run to replay |
| `--from-checkpoint` | No | Checkpoint to start from |
| `--threshold-version` | No | Threshold version to use |

---

#### harness gate config validate

```bash
harness gate config validate -f CONFIG_FILE
```

**Description**: Validate config file.

**Parameters**:
| Option | Required | Description |
|---|---|---|
| `-f, --file` | Yes | Config file to validate |

---

#### harness gate config show

```bash
harness gate config show [--scope SCOPE]
```

**Description**: Show current config.

**Parameters**:
| Option | Required | Description |
|---|---|---|
| `--scope` | No | Scope filter |

---

## 13. HTTP API Endpoints (Optional)

If an external HTTP API is needed for dashboard integration, `/api/v1/*`
endpoints are recommended. `agent-state-gate` adapter integration uses the
canonical `/v1/*` endpoints listed in Section 13.6.

### 13.1 Decisions

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/evaluate` | Canonical adapter endpoint: evaluate artifact/trace/rule_results |
| `GET` | `/v1/decisions/{decision_id}` | Canonical adapter endpoint: get DecisionPacket |
| `GET` | `/v1/state-vectors/{run_id}` | Canonical adapter endpoint: get StateVector |
| `GET` | `/api/v1/decisions/{decision_id}` | Get decision details |
| `GET` | `/api/v1/decisions` | List decisions with filters |
| `POST` | `/api/v1/decisions/evaluate` | Evaluate state vector |

**GET /api/v1/decisions/{decision_id}**

**Response**:
```json
{
  "decision_id": "uuid",
  "run_id": "uuid",
  "decision": "pass|warn|hold|block",
  "composite_score": 0.85,
  "factors": [...],
  "exemplar_refs": [...],
  "threshold_version": "sha256-hash",
  "created_at": "RFC3339"
}
```

**GET /v1/decisions/{decision_id}**

Returns a DecisionPacket by `decision_id`. This endpoint is the canonical
read path used by `agent-state-gate` `GatefieldAdapter.get_decision_packet()`.

**GET /v1/state-vectors/{run_id}**

Returns the immutable StateVector used for the run. This endpoint is the
canonical read path used by `agent-state-gate`
`GatefieldAdapter.get_state_vector()`.

**GET /api/v1/decisions**

**Query Parameters**:
| Param | Type | Description |
|---|---|---|
| `state` | string | Filter by decision state |
| `severity` | string | Filter by severity |
| `repo` | string | Filter by repo |
| `from` | datetime | Start timestamp |
| `to` | datetime | End timestamp |
| `limit` | int | Max results |

---

### 13.2 Reviews

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/review/items` | Enqueue review item for agent-state-gate adapter |
| `GET` | `/api/v1/reviews/pending` | List pending reviews |
| `POST` | `/api/v1/reviews/take` | Take a review |
| `POST` | `/api/v1/reviews/{decision_id}/resolve` | Resolve review |

---

### 13.3 Knowledge Base

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/kb/{axis}` | List documents for axis |
| `POST` | `/api/v1/kb/{axis}` | Import document |
| `POST` | `/api/v1/kb/promote` | Promote run to KB |

---

### 13.4 Calibration

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/calibration/profiles` | List calibration profiles |
| `POST` | `/api/v1/calibration/run` | Run calibration |
| `GET` | `/api/v1/calibration/metrics` | Get metrics |

---

### 13.5 Audit

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/audit/{run_id}` | Export audit events for agent-state-gate adapter |
| `GET` | `/api/v1/audit/events` | List audit events |
| `GET` | `/api/v1/audit/events/{run_id}` | Events for specific run |
| `GET` | `/api/v1/audit/export` | Export audit log |

---

### 13.6 agent-state-gate Adapter Surface

`agent-state-gate` との統合で使う最小 HTTP surface は `/v1/*` に固定する。
既存の `/api/v1/*` は dashboard / 管理 UI 向けの拡張 surface とし、adapter
契約の正本にはしない。

| Method | Endpoint | Adapter Method | Description |
|---|---|---|---|
| `GET` | `/v1/health` | `health_check()` | `{status: "ok"}` を返す |
| `POST` | `/v1/evaluate` | `evaluate()` | artifact / trace / rule_results から DecisionPacket を返す |
| `POST` | `/v1/review/items` | `enqueue_review()` | ReviewItem を Human Review Queue に追加し `review_id` を返す |
| `GET` | `/v1/decisions/{decision_id}` | `get_decision_packet()` | DecisionPacket を返す |
| `GET` | `/v1/state-vectors/{run_id}` | `get_state_vector()` | 評価済み run の StateVector を返す |
| `GET` | `/v1/audit/{run_id}` | `export_audit()` | `audit_events` 配列を返す |

---

## 14. Error Handling Summary

### 14.1 Error Types

| Error Type | HTTP Equivalent | Description |
|---|---|---|
| `RunNotFoundError` | 404 | Run does not exist |
| `ArtifactNotFoundError` | 404 | Artifact not found |
| `CheckpointNotFoundError` | 404 | Checkpoint invalid |
| `TraceNotFoundError` | 404 | Trace not found |
| `InvalidStateVectorError` | 400 | Malformed state vector |
| `InvalidToolCallError` | 400 | Malformed tool call |
| `InvalidGateResultError` | 400 | Malformed gate result |
| `DuplicateItemError` | 409 | Item already exists |
| `AlreadyDeprecatedError` | 409 | Already deprecated |
| `UnauthorizedReviewerError` | 403 | Reviewer not assigned |
| `HarnessUnavailableError` | 503 | Harness unavailable |
| `DatabaseConnectionError` | 503 | Database unavailable |
| `EmbeddingError` | 503 | Embedding API unavailable |

### 14.2 Error Response Format

```json
{
  "error": {
    "type": "ErrorTypeName",
    "message": "Human-readable message",
    "details": {
      "field": "Additional context"
    }
  },
  "trace_id": "OTel trace ID for debugging"
}
```

---

## 15. Data Protection Requirements

All APIs handling payload data must adhere to:

| Requirement | Implementation |
|---|---|
| Raw prompt storage | Disabled by default |
| Raw tool payload storage | Disabled by default |
| Classification required | All payloads classified before storage |
| Unknown classification | Treated as `restricted` |
| Restricted payload | Hash only, no embedding |
| PII-sensitive payload | Redacted before storage |
| Retention enforcement | Per retention_class |

---

## 16. Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | 2026-04-26 | Initial API specification from requirements.md |

---

## Appendix A: Database Schema Reference

See `docs/architecture.md` for complete database schema:

| Table | Purpose |
|---|---|
| `judgment_documents` | Constitution, taboo, accepted, rejected, judgment logs |
| `judgment_embeddings` | Embeddings with versioning (append-only) |
| `state_vectors` | Run state vectors |
| `static_gate_results` | Static gate results (immutable) |
| `gate_decisions` | Gate decisions |
| `human_reviews` | Human reviews and corrections |
| `calibration_profiles` | Team/repo threshold profiles |
| `audit_events` | OTel-mapped audit events |

---

## Appendix B: Configuration Schema Reference

See `docs/requirements.md` section "Configuration File Example" for complete config schema.

---

## Appendix C: Acceptance Criteria Mapping

| API Method | Requirement | Acceptance Criteria |
|---|---|---|
| `HarnessAdapter.subscribe_events()` | AGF-REQ-001 | 95%+ trace coverage |
| `DecisionEngine.evaluate()` | AGF-REQ-003, AGF-REQ-004 | Taboo recall 0.90+, AUC 0.85+ |
| `StateEncoder.encode()` | AGF-REQ-001 | 95%+ state vector coverage |
| `VectorStore.search_similar()` | AGF-REQ-003 | Top 5 exemplars in explanation |
| `ReviewQueue.resolve()` | AGF-REQ-005 | Correction replayable |
| `AuditLogger.log_decision()` | AGF-REQ-009 | 100% trace_id coverage |
| `CalibrationPipeline.run_offline_eval()` | AGF-REQ-007 | Dataset version locked |
| `ReplayEngine.replay_run()` | AGF-REQ-010 | 99% reproducibility |
