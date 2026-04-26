# Integration Specification

This document specifies all integration points for the agent-gatefield system. Each integration follows the contract levels defined in requirements.md and API_SPEC.md.

## Contract Levels

| Level | Description | Failure Handling |
|---|---|---|
| P0 | Required for MVP. Must be functional for shadow mode. | Fail-closed: Block operation if unavailable |
| P1 | Required for production enforce. Must be functional before block enforce. | Fail-safe: Degraded operation with logging |
| P2 | Enhancement. Flexible implementation timing. | Optional: Log warning, continue operation |

---

## 1. Harness Contract Integration

**Integration Type**: P0

**Reference**: AGF-REQ-001 (Harness lifecycle event subscription)

### 1.1 Contract Summary

| Contract | Level | Content | Failure Handling |
|---|---|---|---|
| Run lifecycle events | P0 | Subscribe to 7 event types | Trace adapter must be added if unavailable |
| Pause/resume | P0 | Pause run, return checkpoint ref | Hold degrades to block if unavailable |
| Tool policy hook | P0 | Pre-tool deny/hold/allow | High privilege tools become MVP-excluded if unavailable |
| Artifact snapshot | P0 | Get artifact hash, diff, step, commit | Run excluded from state vector generation |
| Static gate result ingest | P0 | Import CI/scanner results | Static gate adapter must be added |
| Trace correlation | P0 | trace_id/span_id/run_id on all events | Audit completeness acceptance fails |
| Reviewer callback | P1 | approve/reject/recalibrate to run state | Dashboard reference-only, CLI resume fallback |
| Replay | P1 | Re-evaluate with threshold/policy version | Required for acceptance before enforce |
| Policy versioning | P1 | Version all configs with run | Config hash stored in audit log as fallback |

### 1.2 Harness API Minimal I/O Contract

```json
{
  "run_id": "uuid",
  "trace_id": "otel-trace-id",
  "event_type": "tool_call_requested",
  "timestamp": "RFC3339",
  "actor": "agent|tool|reviewer|system",
  "artifact_ref": "artifact://...",
  "checkpoint_ref": "checkpoint://...",
  "policy_version": "gate-policy-v1",
  "payload_ref": "blob://redacted-or-hashed"
}
```

**Data Protection Rule**: Adapter passes hash/redacted payload/scoped reference only. Unprocessed raw payloads are excluded.

### 1.3 Failure Handling Matrix

| Failure Condition | Fallback Action | Audit Requirement |
|---|---|---|
| Event stream disconnect | Reconnect with exponential backoff (max 5 retries, 30s total) | Log disconnection event with timestamp |
| Pause API unavailable | Convert hold to block, store reason | Record `pause_unavailable` in decision packet |
| Resume API timeout | Mark run as `manual_resume_required`, notify ops | Store `resume_timeout` with checkpoint_ref |
| Tool policy check fails | Default to hold for high-privilege, allow for low-privilege | Log `policy_check_failed` with tool_name |
| Artifact snapshot empty | Exclude run from gate evaluation | Log `artifact_snapshot_missing` |
| Static gate result timeout | Continue with incomplete results, mark `partial_static_gates` | Store `static_gate_timeout` with gate_name |
| Trace correlation missing | Generate synthetic trace_id, mark `synthetic_trace` | Store `synthetic_trace_generated` flag |

### 1.4 Configuration Requirements

```yaml
harness:
  implementation: python-adapter
  trace_backend: otel
  checkpointing: true
  retry_policy:
    max_retries: 5
    backoff_multiplier: 2
    max_backoff_seconds: 30
  timeout_seconds:
    pause: 10
    resume: 15
    snapshot: 5
    event_ack: 3
  fallback_policy:
    pause_unavailable: block
    resume_timeout: manual_resume_required
    tool_policy_fail_high_privilege: hold
    tool_policy_fail_low_privilege: allow
```

### 1.5 Testing Requirements

| Test Case | Expected Behavior | Pass Criteria |
|---|---|---|
| Event subscription succeeds | All 7 event types received | 95%+ coverage in 5-minute window |
| Pause/resume roundtrip | Checkpoint ref returned, resume restores state | State identical after resume |
| Tool policy deny | Tool execution blocked, reason recorded | Block decision logged |
| Tool policy hold | Review queue entry created | Queue entry exists |
| Artifact snapshot retrieval | Hash, diff, commit, branch populated | All fields non-null for valid artifact |
| Static gate ingest | Results stored in static_gate_results table | Queryable within 5 seconds |
| Trace correlation | trace_id links all events for run | 100% events have valid trace_id |
| Event stream failure | Retry succeeds or fallback applied | No silent failures |

---

## 2. Harness Adapter Implementation Guide

### 2.1 OpenAI Agents SDK Adapter

**Integration Type**: P0

**SDK Features Used**: Guardrails, Human Review, Tracing, Checkpointing

#### Implementation Points

| Feature | SDK Method | Adapter Implementation |
|---|---|---|
| Event subscription | SDK tracing spans | OTel exporter callback or SDK callbacks |
| Pause run | Human review guardrail | Trigger guardrail, return checkpoint from SDK |
| Resume run | Post-reviewer decision | Call SDK resume with reviewer decision |
| Tool policy check | Guardrails API | Register guardrail with deny/hold/allow logic |
| Artifact snapshot | Extract from trace spans | Parse spans for artifact data |
| Static gate ingest | Custom span | Create span with gate_result attributes |
| Trace context | OTel trace_id/span_id | Extract from SDK tracing context |

#### OpenAI SDK Integration Code Pattern

```python
from openai import OpenAI
from openai.types.agents import Guardrail, HumanReview

class OpenAIAgentsSDKAdapter(HarnessAdapter):
    def __init__(self, client: OpenAI, agent_id: str):
        self.client = client
        self.agent_id = agent_id
        self._tracer = None  # OTel tracer from SDK
    
    def subscribe_events(self) -> None:
        # SDK provides OTel-compatible tracing
        # Configure OTel exporter to capture spans
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        
        provider = TracerProvider()
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=self.trace_endpoint))
        )
        # SDK automatically uses this tracer
    
    def pause_run(self, run_id: str) -> str:
        # Use SDK's human review guardrail
        # Trigger via guardrail configuration
        checkpoint = f"checkpoint://{run_id}/sdk/{self.agent_id}"
        return checkpoint
    
    def check_tool_policy(self, tool_call: Dict) -> str:
        # SDK guardrails support pre-tool execution checks
        tool_name = tool_call.get('tool_name', '')
        
        # Register guardrail rule for tool policy
        for deny_pattern in self.deny_patterns:
            if deny_pattern in tool_name:
                return "deny"
        
        # High privilege tools require human review
        if tool_name in self.high_privilege_tools:
            return "hold"
        
        return "allow"
```

#### Error Handling

| SDK Error | Handling |
|---|---|
| Guardrail timeout | Default to deny, log timeout |
| Human review timeout | Fail-closed per SLA table |
| Tracing exporter failure | Fallback to in-memory buffer, batch retry |
| API rate limit | Exponential backoff, max 3 retries |

---

### 2.2 Claude Code CLI Adapter

**Integration Type**: P0

**CLI Features Used**: Hooks (PreToolUse, PostToolUse, Notification, Stop)

#### Implementation Points

| Feature | CLI Hook | Adapter Implementation |
|---|---|---|
| Event subscription | All hooks | Parse hook JSON input/output |
| Pause run | Not directly supported | Use hold pattern via PreToolUse denial |
| Resume run | Manual CLI intervention | Store checkpoint, wait for CLI resume command |
| Tool policy check | PreToolUse hook | Return JSON with `deny`/`allow` decision |
| Artifact snapshot | PostToolUse hook output | Parse tool output for artifact data |
| Static gate ingest | Custom span via log file | Write structured JSON to log file |
| Trace context | Session ID as trace_id | Extract from CLI environment |

#### Claude Code Hook Configuration

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": {
          "toolName": "*"
        },
        "hooks": [
          {
            "type": "command",
            "command": "python -m agent_gatefield.hooks.tool_policy_check",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": {
          "toolName": "Write|Edit|Bash"
        },
        "hooks": [
          {
            "type": "command",
            "command": "python -m agent_gatefield.hooks.artifact_capture",
            "timeout": 10
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": {},
        "hooks": [
          {
            "type": "command",
            "command": "python -m agent_gatefield.hooks.event_logger"
          }
        ]
      }
    ]
  }
}
```

#### Hook Input/Output Schema

**PreToolUse Hook Input**:
```json
{
  "session_id": "uuid",
  "tool_name": "Bash",
  "tool_input": {
    "command": "rm -rf /"
  },
  "timestamp": "RFC3339"
}
```

**PreToolUse Hook Output** (to deny):
```json
{
  "decision": "deny",
  "reason": "Dangerous command pattern detected: rm -rf /"
}
```

#### Error Handling

| Hook Error | Handling |
|---|---|
| Hook timeout | Default to deny for PreToolUse, continue for others |
| Hook script crash | Log error, default behavior |
| Session ID missing | Generate synthetic trace_id, mark synthetic |
| Hook output malformed | Log warning, default to allow |

---

### 2.3 LangGraph Adapter

**Integration Type**: P0

**LangGraph Features Used**: Persistence, Interrupt, Checkpointer, Tracing

#### Implementation Points

| Feature | LangGraph Feature | Adapter Implementation |
|---|---|---|
| Event subscription | Tracing (LangSmith compatible) | Configure LangSmith tracer or OTel exporter |
| Pause run | `interrupt()` API | Call interrupt with checkpoint config |
| Resume run | Resume from checkpoint | Load checkpoint, call `invoke()` with resume config |
| Tool policy check | Pre-execution node | Add policy check node before tool node |
| Artifact snapshot | State snapshot | Extract from graph state after artifact node |
| Static gate ingest | Custom node | Add static gate node with results storage |
| Trace context | LangSmith trace_id | Extract from run context |

#### LangGraph Integration Code Pattern

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, interrupt

class LangGraphAdapter(HarnessAdapter):
    def __init__(self, graph: StateGraph, checkpointer: MemorySaver):
        self.graph = graph
        self.checkpointer = checkpointer
    
    def subscribe_events(self) -> None:
        # LangGraph uses LangSmith tracing by default
        # Configure OTel exporter for custom backend
        from langsmith import Client
        self.langsmith_client = Client()
        # Subscribe to run events via LangSmith API
    
    def pause_run(self, run_id: str) -> str:
        # LangGraph interrupt creates checkpoint automatically
        config = {"configurable": {"thread_id": run_id}}
        checkpoint = self.checkpointer.get(config)
        if checkpoint:
            return f"checkpoint://{run_id}/langgraph/{checkpoint.id}"
        
        # Force interrupt if no checkpoint
        interrupt("Human review required")
        return f"checkpoint://{run_id}/langgraph/interrupted"
    
    def resume_run(self, run_id: str, checkpoint_ref: str) -> None:
        config = {"configurable": {"thread_id": run_id}}
        # Load checkpoint state
        checkpoint_state = self.checkpointer.get(config)
        # Resume graph execution
        self.graph.invoke(None, config=config)
```

#### Error Handling

| LangGraph Error | Handling |
|---|---|
| Checkpoint not found | Log error, create new checkpoint |
| Resume state mismatch | Log warning, continue with partial state |
| Interrupt timeout | Fail-closed, mark `interrupt_timeout` |
| LangSmith API error | Fallback to local tracing |

---

### 2.4 Generic Harness Adapter

**Integration Type**: P0

**Use Case**: Harnesses without standard SDK integration

#### Implementation Pattern

```python
class GenericHarnessAdapter(HarnessAdapter):
    """
    Generic adapter for harnesses with standard hooks.
    Requires implementation of all P0 contracts.
    """
    
    def __init__(self, config: Dict):
        self.event_queue = []
        self.checkpoint_store = {}
        self.deny_patterns = config.get('deny_patterns', [])
        self.harness_api_base = config.get('api_base')
    
    def subscribe_events(self) -> None:
        # Generic implementation: webhook or polling
        # Expected events from harness:
        # - run_started, step_started, tool_call_requested,
        # - artifact_emitted, static_gate_completed,
        # - run_completed, run_failed
        
        # Implementation depends on harness capabilities:
        # Option 1: Webhook registration
        # Option 2: Polling API
        # Option 3: File-based event log
        pass
    
    def pause_run(self, run_id: str) -> str:
        # Call harness pause API if available
        # Fallback: create synthetic checkpoint
        checkpoint = f"checkpoint://{run_id}/cp/current"
        self.checkpoint_store[run_id] = {
            "checkpoint_ref": checkpoint,
            "paused_at": datetime.now().isoformat()
        }
        return checkpoint
    
    def check_tool_policy(self, tool_call: Dict) -> str:
        # Check against deny patterns
        tool_input = str(tool_call.get('input', ''))
        for pattern in self.deny_patterns:
            if pattern in tool_input:
                return "deny"
        
        # Default: allow (should be overridden for high-privilege tools)
        return "allow"
```

---

## 3. Static Gate Integration

**Integration Type**: P0

**Reference**: AGF-REQ-002 (Static gate hard fail block)

### 3.1 Static Gate Types and Integration Points

| Gate Type | Engine | Integration Method | Priority |
|---|---|---|---|
| Lint/Type | Existing CI | Parse CI output, extract errors | Highest |
| Tests | Test runner | Parse test result XML/JSON | Highest |
| SAST | Semgrep/CodeQL | API or result file ingest | High |
| Secret Scan | Trivy | Trivy JSON output | High |
| License Scan | Trivy | Trivy JSON output | Medium |
| Tool Policy | Custom hook | Direct hook invocation | Highest |

### 3.2 CI/CD Pipeline Integration Points

```yaml
# Example GitHub Actions integration
name: Agent Gate Field

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  static-gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      # Static gate results collection
      - name: Run Semgrep
        uses: semgrep/semgrep-action@v1
        with:
          config: >-
            p/security-audit
            p/secrets
            p/owasp-top-ten
        continue-on-error: true
        
      - name: Run Trivy (Secret + License)
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'json'
          output: 'trivy-results.json'
          severity: 'CRITICAL,HIGH'
        continue-on-error: true
      
      - name: Ingest Static Gate Results
        run: |
          python -m agent_gatefield.ingest_static_gates \
            --run-id ${{ github.run_id }} \
            --semgrep-output semgrep-results.json \
            --trivy-output trivy-results.json \
            --ci-system github-actions
      
      # Gate evaluation
      - name: Evaluate Gates
        run: |
          python -m agent_gatefield.evaluate \
            --run-id ${{ github.run_id }} \
            --artifact-path . \
            --mode shadow
```

### 3.3 Static Gate Result Schema

```json
{
  "gate_result_id": "uuid",
  "run_id": "uuid",
  "gate_name": "semgrep",
  "engine": "semgrep",
  "severity": "high",
  "status": "fail",
  "rule_id": "sql-injection",
  "evidence_ref": "file://src/db.py:45",
  "message": "Potential SQL injection vulnerability",
  "raw_output_ref": "blob://semgrep-raw-output",
  "timestamp": "RFC3339"
}
```

### 3.4 Failure Handling

| Static Gate Status | Action |
|---|---|
| Pass | Continue to state space gate |
| Fail (Critical/High) | Immediate block, no state space evaluation |
| Fail (Medium/Low) | Continue with warn flag |
| Timeout | Continue with partial results, log timeout |
| Unavailable | Degraded to hold if high-privilege action, continue otherwise |

### 3.5 Testing Requirements

| Test Case | Expected Behavior |
|---|---|
| Seeded secret in artifact | Block with secret_scan gate evidence |
| Seeded SQL injection | Block with SAST gate evidence |
| Test failure | Block with test gate evidence |
| License violation (forbidden) | Block with license gate evidence |
| All gates pass | Continue to state space gate |
| Gate timeout | Log timeout, continue with partial results |

---

## 4. Vector Store Integration

**Integration Type**: P0

**Reference**: AGF-REQ-003 (Semantic/taboo/accepted/rejected scoring)

### 4.1 PostgreSQL/pgvector Setup

#### Database Schema

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Judgment documents table
CREATE TABLE judgment_documents (
    doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    axis_type VARCHAR(50) NOT NULL,  -- constitution, taboo, accepted, rejected, judgment_log
    text TEXT NOT NULL,
    source_type VARCHAR(50),  -- manual, run_promotion, calibration
    version VARCHAR(50) NOT NULL,
    labels JSONB DEFAULT '{}',
    scope VARCHAR(100),  -- repo, service, team filter
    status VARCHAR(20) DEFAULT 'active',  -- active, deprecated
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Judgment embeddings table (append-only versioning)
CREATE TABLE judgment_embeddings (
    embed_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id UUID REFERENCES judgment_documents(doc_id),
    model VARCHAR(100) NOT NULL,  -- text-embedding-3-large
    dims INTEGER NOT NULL,  -- 1536 or 3072
    embedding vector(1536),  -- Adjust based on dims
    content_hash VARCHAR(64) NOT NULL,
    valid_from TIMESTAMP DEFAULT NOW(),
    valid_to TIMESTAMP NULL,  -- NULL means active
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create HNSW index for cosine similarity
CREATE INDEX judgment_embeddings_hnsw_idx ON judgment_embeddings 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- State vectors table
CREATE TABLE state_vectors (
    run_id UUID PRIMARY KEY,
    artifact_id UUID,
    semantic_embedding vector(1536),
    rule_json JSONB,
    test_json JSONB,
    risk_json JSONB,
    history_json JSONB,
    uncertainty_json JSONB,
    context_json JSONB,
    trajectory_json JSONB,
    encoder_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Static gate results table
CREATE TABLE static_gate_results (
    gate_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES state_vectors(run_id),
    gate_name VARCHAR(50) NOT NULL,
    engine VARCHAR(50),
    severity VARCHAR(20),
    status VARCHAR(20) NOT NULL,
    rule_id VARCHAR(100),
    evidence_ref TEXT,
    raw_output_ref TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Gate decisions table
CREATE TABLE gate_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES state_vectors(run_id),
    composite_score FLOAT,
    state VARCHAR(20) NOT NULL,  -- pass, warn, hold, block
    reasons_json JSONB,
    action_type VARCHAR(50),
    threshold_version VARCHAR(50) NOT NULL,
    policy_version VARCHAR(50),
    hard_override_reason VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Human reviews table
CREATE TABLE human_reviews (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID REFERENCES gate_decisions(decision_id),
    reviewer VARCHAR(100) NOT NULL,
    decision VARCHAR(20) NOT NULL,  -- approve, reject, recalibrate, correction
    comment TEXT,
    correction_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Calibration profiles table
CREATE TABLE calibration_profiles (
    profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope VARCHAR(100),
    weights_json JSONB NOT NULL,
    warn_thresholds JSONB NOT NULL,
    block_thresholds JSONB NOT NULL,
    detector_ref VARCHAR(100),
    threshold_version VARCHAR(50) NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 4.2 Connection Pooling Configuration

```yaml
vector_store:
  backend: pgvector
  connection_pool:
    min_size: 5
    max_size: 20
    max_overflow: 10
    pool_timeout_seconds: 30
    idle_timeout_seconds: 300
    recycle_seconds: 1800
  
  connection_string: "postgresql://user:pass@host:5432/gatefield"
  
  ssl:
    mode: require
    cert_path: /path/to/cert
  
  retry:
    max_retries: 3
    backoff_ms: 100
    retry_on_errors:
      - "ConnectionError"
      - "OperationalError"
```

### 4.3 Index Configuration

| Index Type | Table | Columns | Parameters |
|---|---|---|---|
| HNSW | judgment_embeddings | embedding | m=16, ef_construction=64 |
| B-tree | judgment_documents | axis_type, status | Standard |
| B-tree | judgment_embeddings | doc_id, valid_to | Standard |
| GIN | judgment_documents | labels | JSONB ops |
| B-tree | gate_decisions | run_id, state | Standard |
| B-tree | static_gate_results | run_id, gate_name | Standard |

### 4.4 Vector Search Functions

```sql
-- Cosine similarity search
CREATE OR REPLACE FUNCTION search_similar(
    query_vector vector(1536),
    axis_type VARCHAR(50),
    limit_count INTEGER DEFAULT 10
) RETURNS TABLE (
    doc_id UUID,
    similarity FLOAT,
    text TEXT,
    labels JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        jd.doc_id,
        1 - (je.embedding <=> query_vector) AS similarity,
        jd.text,
        jd.labels
    FROM judgment_embeddings je
    JOIN judgment_documents jd ON je.doc_id = jd.doc_id
    WHERE jd.axis_type = axis_type
      AND jd.status = 'active'
      AND je.valid_to IS NULL
    ORDER BY je.embedding <=> query_vector
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- Centroid calculation
CREATE OR REPLACE FUNCTION get_centroid(
    axis_type VARCHAR(50)
) RETURNS vector(1536) AS $$
DECLARE
    centroid vector(1536);
BEGIN
    SELECT AVG(embedding) INTO centroid
    FROM judgment_embeddings je
    JOIN judgment_documents jd ON je.doc_id = jd.doc_id
    WHERE jd.axis_type = axis_type
      AND jd.status = 'active'
      AND je.valid_to IS NULL;
    
    RETURN centroid;
END;
$$ LANGUAGE plpgsql;
```

### 4.5 Error Handling

| Error Condition | Handling |
|---|---|
| Connection pool exhausted | Wait with timeout, fallback to in-memory cache |
| Query timeout (>5s) | Reduce limit, retry with simpler query |
| Index corruption | Log error, rebuild index in background |
| Embedding dimension mismatch | Reject embedding, log dimension mismatch |
| Invalid vector format | Log error, skip record |

### 4.6 Testing Requirements

| Test Case | Expected Behavior |
|---|---|
| Insert embedding | Embedding stored with valid_from, NULL valid_to |
| Similarity search | Returns top-k with cosine distance |
| Centroid calculation | Returns average vector for axis |
| Deprecate embedding | valid_to set to NOW() |
| Connection pool stress | No connection leaks, graceful handling |
| Index rebuild | Query performance restored |

---

## 5. Embedding Service Integration

**Integration Type**: P0

**Reference**: AGF-REQ-003 (Semantic embedding for judgment KB)

### 5.1 Local Embedding Integration

#### API Configuration

```yaml
embedding_service:
  provider: local
  model: local-hash-embedding-v1
  dimensions: 1536

  batching:
    max_batch_size: 100
    batch_timeout_ms: 500
```

#### Integration Code Pattern

```python
import hashlib
import math
import re
from typing import List, Dict

class EmbeddingService:
    def __init__(self, config: Dict):
        self.provider = config.get('provider', 'local')
        self.model = config.get('model', 'local-hash-embedding-v1')
        self.dimensions = config.get('dimensions', 1536)
        self.batch_size = config.get('batch_size', 100)
    
    def embed_single(self, text: str) -> List[float]:
        """Generate local deterministic embedding for single text"""
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"\w+|[^\s\w]", text.lower())
        for position, token in enumerate(tokens):
            digest = hashlib.sha256(f"{self.model}:{position}:{token}".encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector
    
    def embed_batch(self, texts: List[str]) -> Dict[str, List[float]]:
        """Generate embeddings for batch of texts"""
        results = {}
        
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            
            for text in batch:
                results[text] = self.embed_single(text)
        
        return results
    
    def _compute_hash(self, text: str) -> str:
        """Compute content hash for deduplication"""
        return hashlib.sha256(text.encode()).hexdigest()[:64]
```

### 5.2 Retry Logic

```python
import tenacity

class EmbeddingServiceWithRetry:
    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
        retry=tenacity.retry_if_exception_type(Exception),
        before_sleep=tenacity.before_sleep_log(logger, logging.WARNING)
    )
    def embed_with_retry(self, text: str) -> List[float]:
        try:
            return self.embed_single(text)
        except Exception as e:
            self.logger.warning(f"Embedding retry: {e}")
            raise
```

### 5.3 Cost Management

#### Cost Tracking Schema

```sql
CREATE TABLE embedding_costs (
    cost_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    model VARCHAR(100),
    tokens_used INTEGER,
    cost_usd FLOAT,
    budget_monthly_usd FLOAT DEFAULT 500.0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Monthly budget check function
CREATE OR REPLACE FUNCTION check_budget() RETURNS VARCHAR AS $$
DECLARE
    current_month_cost FLOAT;
    budget_limit FLOAT;
BEGIN
    SELECT SUM(cost_usd) INTO current_month_cost
    FROM embedding_costs
    WHERE date >= date_trunc('month', NOW());
    
    budget_limit := (SELECT budget_monthly_usd FROM embedding_costs LIMIT 1);
    
    IF current_month_cost >= budget_limit THEN
        RETURN 'hold';
    ELSIF current_month_cost >= budget_limit * 0.8 THEN
        RETURN 'warn';
    ELSE
        RETURN 'ok';
    END IF;
END;
$$ LANGUAGE plpgsql;
```

#### Cost Alert Thresholds

| Budget Level | Action |
|---|---|
| 80% reached | Log warning, continue embedding |
| 100% reached | Hold new embedding jobs, alert ops |
| Budget reset | Resume embedding at start of new month |

### 5.4 Embedding Model Migration (P2)

#### Dual-Write Strategy

```python
class EmbeddingMigration:
    """
    Dual-write embedding migration for model/dimension changes.
    Phase 1: Generate new embeddings, keep old active.
    Phase 2: Validate new embeddings.
    Phase 3: Deprecate old embeddings (set valid_to).
    Phase 4: Recalibrate thresholds with new model.
    """
    
    def migrate_axis(self, axis_type: str, new_model: str, new_dims: int):
        # Phase 1: Dual-write
        docs = self.vector_store.get_active_embeddings(axis_type)
        for doc in docs:
            new_embedding = self.new_service.embed_single(doc['text'])
            self.vector_store.insert_embedding(
                doc_id=doc['doc_id'],
                model=new_model,
                dims=new_dims,
                embedding=new_embedding,
                content_hash=doc['content_hash']
            )
        
        # Phase 2: Validation (compare centroids, check distribution)
        old_centroid = self.old_service.get_centroid(axis_type)
        new_centroid = self.new_service.get_centroid(axis_type)
        similarity = cosine_similarity(old_centroid, new_centroid)
        
        if similarity < 0.95:
            raise MigrationValidationError("Centroid similarity below threshold")
        
        # Phase 3: Deprecate old
        self.vector_store.deprecate_embeddings(axis_type, self.old_model)
        
        # Phase 4: Recalibrate thresholds
        self.calibration.recalibrate(axis_type, new_model)
```

### 5.5 Error Handling

| Error Condition | Handling |
|---|---|
| API rate limit | Exponential backoff, queue requests |
| API timeout | Retry 3 times, fallback to cache |
| API error (4xx) | Log error, skip batch item |
| API error (5xx) | Retry with backoff |
| Dimension mismatch | Reject embedding, log error |
| Budget exceeded | Queue jobs for next month |

### 5.6 Testing Requirements

| Test Case | Expected Behavior |
|---|---|
| Single embedding | Vector returned with correct dimensions |
| Batch embedding | All vectors returned, correct batch handling |
| API timeout | Retry succeeds or queued |
| Rate limit | Backoff succeeds or queued |
| Budget warn threshold | Warning logged |
| Budget hold threshold | New jobs queued |
| Model migration | Dual-write succeeds, old deprecated |

---

## 6. Trace Integration

**Integration Type**: P0

**Reference**: AGF-REQ-009 (OTel trace correlation)

### 6.1 OpenTelemetry Setup

#### OTel Configuration

```yaml
tracing:
  provider: opentelemetry
  service_name: agent-gatefield
  
  exporter:
    type: otlp
    endpoint: http://otel-collector:4317
    protocol: grpc
    timeout_ms: 5000
    
  sampler:
    type: parent_based
    root_sampler: always_on
    
  resource_attributes:
    service.namespace: gatefield
    service.version: 1.0.0
    deployment.environment: staging
    
  propagation:
    format: w3c_trace_context
```

#### OTel SDK Initialization

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

def init_tracing(config: Dict):
    resource = Resource.create({
        "service.name": config.get('service_name', 'agent-gatefield'),
        "service.namespace": config.get('service_namespace', 'gatefield'),
        "deployment.environment": config.get('environment', 'staging')
    })
    
    provider = TracerProvider(resource=resource)
    
    exporter = OTLPSpanExporter(
        endpoint=config.get('endpoint', 'http://otel-collector:4317'),
        timeout=config.get('timeout_ms', 5000) / 1000
    )
    
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)
    
    return trace.get_tracer(config.get('service_name'))

tracer = init_tracing(config)
```

### 6.2 Span Creation Patterns

#### Run Lifecycle Spans

```python
def create_run_span(run_id: str, parent_context: Dict = None):
    """Create span for run lifecycle"""
    with tracer.start_as_current_span(
        "agent_run",
        attributes={
            "run.id": run_id,
            "run.type": "agent_execution",
            "gate.version": get_threshold_version()
        }
    ) as span:
        # Store trace_id in context
        trace_id = format(span.context.trace_id, '032x')
        span_id = format(span.context.span_id, '016x')
        
        return {
            "trace_id": trace_id,
            "span_id": span_id,
            "run_id": run_id
        }

def create_tool_call_span(run_id: str, tool_name: str, parent_span):
    """Create span for tool execution"""
    with tracer.start_as_current_span(
        "tool_call",
        parent=parent_span,
        attributes={
            "run.id": run_id,
            "tool.name": tool_name,
            "tool.policy_checked": True,
            "tool.policy_result": "allow"
        }
    ) as span:
        return span

def create_gate_evaluation_span(run_id: str, state_vector: Dict):
    """Create span for gate evaluation"""
    with tracer.start_as_current_span(
        "gate_evaluation",
        attributes={
            "run.id": run_id,
            "gate.state": state_vector.get('state'),
            "gate.composite_score": state_vector.get('composite_score'),
            "gate.threshold_version": state_vector.get('threshold_version')
        }
    ) as span:
        # Add scorer results as events
        for scorer in state_vector.get('scorer_results', []):
            span.add_event(
                f"scorer.{scorer['name']}",
                attributes={
                    "score": scorer['score'],
                    "weight": scorer['weight']
                }
            )
        return span
```

### 6.3 Correlation IDs

#### Trace ID Propagation

```python
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextPropagator

def inject_trace_context(trace_id: str, span_id: str) -> Dict:
    """Inject trace context for downstream services"""
    propagator = TraceContextPropagator()
    
    # Create context from trace_id/span_id
    context = Context()
    carrier = {}
    propagator.inject(carrier, context=context)
    
    return {
        "traceparent": carrier.get('traceparent'),
        "trace_id": trace_id,
        "span_id": span_id
    }

def extract_trace_context(carrier: Dict) -> Context:
    """Extract trace context from incoming request"""
    propagator = TraceContextPropagator()
    return propagator.extract(carrier)
```

### 6.4 Trace Event Schema

```json
{
  "trace_id": "0123456789abcdef0123456789abcdef",
  "span_id": "0123456789abcdef",
  "parent_span_id": "abcdef0123456789",
  "operation_name": "gate_evaluation",
  "start_time": "2026-04-26T10:00:00Z",
  "end_time": "2026-04-26T10:00:05Z",
  "duration_ms": 5000,
  "attributes": {
    "run.id": "run-abc123",
    "gate.state": "hold",
    "gate.composite_score": 0.85,
    "gate.threshold_version": "v1.2.0"
  },
  "events": [
    {
      "name": "scorer.taboo_proximity",
      "timestamp": "2026-04-26T10:00:01Z",
      "attributes": {
        "score": 0.82,
        "weight": 0.30
      }
    }
  ],
  "status": {
    "code": "OK",
    "message": ""
  }
}
```

### 6.5 Error Handling

| Error Condition | Handling |
|---|---|
| OTel collector unavailable | Fallback to in-memory buffer, batch export retry |
| Export timeout | Reduce batch size, retry |
| Trace context missing | Generate synthetic trace_id |
| Span creation error | Log warning, continue without span |

### 6.6 Testing Requirements

| Test Case | Expected Behavior |
|---|---|
| Run span creation | trace_id, span_id returned |
| Span attribute propagation | All required attributes present |
| Trace context injection | Valid traceparent header |
| Trace context extraction | Context restored correctly |
| Export to collector | Spans visible in collector |
| Collector unavailable | Buffer spans, retry succeeds |

---

## 7. Dashboard Integration

**Integration Type**: P1

**Reference**: Human review dashboard requirements (AGF-REQ-004)

### 7.1 Grafana Dashboard Configuration

#### Data Sources

```yaml
dashboard:
  grafana:
    url: http://grafana:3000
    datasource:
      postgres:
        type: postgres
        host: postgres:5432
        database: gatefield
        user: grafana_reader
        ssl_mode: require
        
      prometheus:
        type: prometheus
        url: http://prometheus:9090
        
      otel:
        type: jaeger
        url: http://jaeger:16686
```

#### Dashboard Panels

| Panel | Data Source | Query | Refresh |
|---|---|---|---|
| Run Queue Status | PostgreSQL | `SELECT state, COUNT(*) FROM gate_decisions WHERE created_at > NOW() - INTERVAL '1 hour'` | 10s |
| Severity Distribution | PostgreSQL | `SELECT severity, COUNT(*) FROM human_reviews WHERE status = 'pending'` | 10s |
| Gate Decision Timeline | PostgreSQL | `SELECT created_at, state FROM gate_decisions ORDER BY created_at DESC LIMIT 100` | 30s |
| Composite Score Distribution | PostgreSQL | `SELECT composite_score, state FROM gate_decisions` | 1m |
| Scorer Heatmap | PostgreSQL | `SELECT scorer_name, AVG(score) FROM scorer_results` | 1m |
| Reviewer Latency P90 | Prometheus | `histogram_quantile(0.9, reviewer_latency_bucket)` | 30s |
| Cost Budget Status | PostgreSQL | `SELECT SUM(cost_usd) FROM embedding_costs WHERE date >= date_trunc('month', NOW())` | 1m |
| Trace Drill-down | Jaeger | Link to Jaeger UI with trace_id | Manual |

### 7.2 Custom Dashboard API

#### Dashboard Data Endpoints

```python
from fastapi import FastAPI, Depends
from typing import List, Dict

app = FastAPI()

@app.get("/api/dashboard/queue")
def get_queue_status() -> Dict:
    """Get review queue statistics"""
    return {
        "total_pending": db.query("SELECT COUNT(*) FROM human_reviews WHERE status = 'pending'"),
        "by_severity": {
            "critical": db.query("SELECT COUNT(*) FROM human_reviews WHERE severity = 'critical'"),
            "high": db.query("SELECT COUNT(*) FROM human_reviews WHERE severity = 'high'"),
            "medium": db.query("SELECT COUNT(*) FROM human_reviews WHERE severity = 'medium'"),
            "low": db.query("SELECT COUNT(*) FROM human_reviews WHERE severity = 'low'")
        },
        "oldest_pending_age_seconds": db.query("SELECT EXTRACT(EPOCH FROM NOW() - MIN(created_at)) FROM human_reviews WHERE status = 'pending'")
    }

@app.get("/api/dashboard/run/{run_id}")
def get_run_details(run_id: str) -> Dict:
    """Get detailed run information"""
    decision = db.get_gate_decision(run_id)
    state_vector = db.get_state_vector(run_id)
    reviews = db.get_human_reviews(run_id)
    
    return {
        "run_id": run_id,
        "decision": decision,
        "state_vector": state_vector,
        "human_reviews": reviews,
        "trace_ref": f"http://jaeger:16686/trace/{decision['trace_id']}"
    }

@app.get("/api/dashboard/kpis")
def get_operational_kpis() -> Dict:
    """Get operational KPI metrics"""
    return {
        "review_load_reduction": calculate_review_load_reduction(),
        "critical_miss_rate": calculate_critical_miss_rate(),
        "high_miss_rate": calculate_high_miss_rate(),
        "false_escalation_rate": calculate_false_escalation_rate(),
        "reviewer_queue_latency_p90": calculate_latency_p90(),
        "decision_latency_p90": calculate_decision_latency_p90(),
        "explanation_usefulness": get_explanation_usefulness_score(),
        "replay_reproducibility": calculate_replay_reproducibility()
    }
```

### 7.3 Dashboard Requirements

| Requirement | Implementation |
|---|---|
| Run list view | Table with gate state, score, severity, service, branch, artifact type |
| Main explanation | Top 3 factors, top 5 exemplars, static gate summary, evaluator disagreements |
| Trace drill-down | Link to Jaeger/OTel UI with trace_id |
| Comparison view | Parent vs child run, accepted vs current artifact, pre vs post correction |
| Reviewer actions | Approve/reject/request correction/recalibrate buttons |
| Queue mode | Single-run and pairwise queue view |
| Export | JSON/CSV/SIEM export buttons |
| Freshness | 60-second update requirement |

### 7.4 Error Handling

| Error Condition | Handling |
|---|---|
| Database query timeout | Return cached data, log timeout |
| Data source unavailable | Show error banner, fallback to cached data |
| API rate limit | Throttle requests, queue updates |

### 7.5 Testing Requirements

| Test Case | Expected Behavior |
|---|---|
| Queue status query | Correct counts returned within 5s |
| Run details query | Full decision, state_vector, reviews returned |
| KPI query | All 9 KPI values returned |
| Dashboard refresh | Data updated within 60s of DB change |
| Export to JSON | Valid JSON file generated |

---

## 8. Alert Integration

**Integration Type**: P1

**Reference**: Human review SLA requirements

### 8.1 PagerDuty Integration

#### Configuration

```yaml
alerts:
  pagerduty:
    enabled: true
    service_key: "PAGERDUTY_SERVICE_KEY"
    
    routing:
      critical:
        severity: critical
        service: "gatefield-critical"
        escalation_policy: "engineering-oncall"
        
      high:
        severity: high
        service: "gatefield-high"
        escalation_policy: "engineering-secondary"
```

#### Integration Code

```python
import requests
from typing import Dict

class PagerDutyAlert:
    def __init__(self, service_key: str):
        self.service_key = service_key
        self.api_url = "https://events.pagerduty.com/v2/enqueue"
    
    def trigger(
        self,
        incident_key: str,
        severity: str,
        summary: str,
        details: Dict
    ) -> Dict:
        """Trigger PagerDuty incident"""
        payload = {
            "routing_key": self.service_key,
            "event_action": "trigger",
            "dedup_key": incident_key,
            "severity": severity,
            "summary": summary,
            "source": "agent-gatefield",
            "custom_details": details
        }
        
        response = requests.post(
            self.api_url,
            json=payload,
            timeout=10
        )
        
        return response.json()
    
    def resolve(self, incident_key: str) -> Dict:
        """Resolve PagerDuty incident"""
        payload = {
            "routing_key": self.service_key,
            "event_action": "resolve",
            "dedup_key": incident_key
        }
        
        response = requests.post(
            self.api_url,
            json=payload,
            timeout=10
        )
        
        return response.json()
```

### 8.2 Slack Integration

#### Configuration

```yaml
alerts:
  slack:
    enabled: true
    webhook_url: "https://hooks.slack.com/services/T00/B00/XXX"
    channel: "#gatefield-alerts"
    
    routing:
      critical:
        channel: "#gatefield-critical"
        mention: "@oncall-engineering"
        
      high:
        channel: "#gatefield-high"
        mention: "@engineering-team"
        
      medium:
        channel: "#gatefield-alerts"
        
      budget_warn:
        channel: "#finance-alerts"
```

#### Integration Code

```python
import requests
from typing import Dict

class SlackAlert:
    def __init__(self, webhook_url: str, channel: str):
        self.webhook_url = webhook_url
        self.channel = channel
    
    def send(
        self,
        severity: str,
        title: str,
        message: str,
        details: Dict,
        mention: str = None
    ) -> Dict:
        """Send Slack alert"""
        color_map = {
            "critical": "#FF0000",
            "high": "#FF6600",
            "medium": "#FFCC00",
            "low": "#00CC00"
        }
        
        text = f"{mention + ' ' if mention else ''}{title}"
        
        payload = {
            "channel": self.channel,
            "text": text,
            "attachments": [
                {
                    "color": color_map.get(severity, "#00CC00"),
                    "title": title,
                    "text": message,
                    "fields": [
                        {"title": k, "value": str(v), "short": True}
                        for k, v in details.items()
                    ],
                    "footer": "agent-gatefield",
                    "ts": int(datetime.now().timestamp())
                }
            ]
        }
        
        response = requests.post(
            self.webhook_url,
            json=payload,
            timeout=10
        )
        
        return response.json()
```

### 8.3 Webhook Integration

#### Generic Webhook Configuration

```yaml
alerts:
  webhooks:
    - name: siem_forwarder
      url: https://siem.example.com/api/events
      headers:
        Authorization: "Bearer TOKEN"
      events:
        - gate_decision_block
        - gate_decision_hold
        - human_review_action
        
    - name: ops_dashboard
      url: https://ops.example.com/api/gatefield
      events:
        - queue_threshold_exceeded
        - sla_breach
```

#### Webhook Payload Schema

```json
{
  "event_type": "gate_decision_block",
  "timestamp": "RFC3339",
  "source": "agent-gatefield",
  "severity": "critical",
  "data": {
    "run_id": "uuid",
    "trace_id": "otel-trace-id",
    "decision_id": "uuid",
    "composite_score": 0.95,
    "state": "block",
    "top_factors": ["Secret detected", "Taboo proximity high"],
    "threshold_version": "v1.2.0",
    "policy_version": "gate-policy-v1"
  },
  "metadata": {
    "environment": "staging",
    "service": "agent-gatefield",
    "version": "1.0.0"
  }
}
```

### 8.4 Alert Routing Rules

| Event Type | Severity | Primary Channel | Secondary Channel | Escalation |
|---|---|---|---|---|
| gate_decision_block | Critical | PagerDuty | Slack (mention) | 15-min ACK |
| gate_decision_hold (Critical) | Critical | PagerDuty | Slack (mention) | 15-min ACK |
| gate_decision_hold (High) | High | Slack (mention) | - | 60-min ACK |
| queue_threshold_exceeded | High | Slack | PagerDuty (if >5min) | Auto-escalate |
| sla_breach | High | PagerDuty | Slack (mention) | Immediate |
| budget_warn | Medium | Slack | - | None |
| budget_hold | High | PagerDuty | Slack | 60-min ACK |
| static_gate_fail | Critical | PagerDuty | Slack | 15-min ACK |

### 8.5 Error Handling

| Error Condition | Handling |
|---|---|
| PagerDuty API error | Retry 3 times, log error, fallback to Slack |
| Slack API error | Retry 3 times, log error |
| Webhook timeout | Queue for retry, log timeout |
| Alert rate exceeded | Throttle alerts, aggregate similar events |

### 8.6 Testing Requirements

| Test Case | Expected Behavior |
|---|---|
| Critical alert triggered | PagerDuty incident created |
| Alert resolved | PagerDuty incident resolved |
| Slack alert sent | Message posted to channel |
| Webhook event sent | Event received by endpoint |
| Rate limit applied | Similar alerts aggregated |

---

## 9. Audit Export Integration

**Integration Type**: P0

**Reference**: AGF-REQ-009 (Audit event dual-storage)

### 9.1 OTLP Exporter Configuration

```yaml
audit:
  enabled: true
  
  otlp_export:
    endpoint: http://otel-collector:4318
    protocol: http
    headers:
      X-API-Key: "OTEL_API_KEY"
    
    batch:
      max_batch_size: 100
      export_interval_ms: 5000
      max_queue_size: 1000
    
    retry:
      max_retries: 5
      backoff_ms: 100
```

### 9.2 JSONL File Output

#### Configuration

```yaml
audit:
  jsonl_export:
    enabled: true
    output_dir: /var/log/gatefield/audit
    rotation:
      max_file_size_mb: 100
      max_files: 30
      compress_after_days: 7
    flush_interval_seconds: 5
```

#### JSONL Output Implementation

```python
import json
import os
from datetime import datetime
from pathlib import Path

class JSONLAuditExporter:
    def __init__(self, config: Dict):
        self.output_dir = Path(config.get('output_dir', '/var/log/gatefield/audit'))
        self.max_file_size = config.get('max_file_size_mb', 100) * 1024 * 1024
        self.max_files = config.get('max_files', 30)
        self.buffer = []
        self.flush_interval = config.get('flush_interval_seconds', 5)
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export_event(self, event: Dict) -> None:
        """Export audit event to JSONL"""
        line = json.dumps({
            "trace_id": event.get('trace_id'),
            "span_id": event.get('span_id'),
            "run_id": event.get('run_id'),
            "event_type": event.get('event_type'),
            "actor": event.get('actor'),
            "payload_hash": event.get('payload_hash'),
            "retention_class": event.get('retention_class'),
            "created_at": datetime.now().isoformat(),
            "schema_version": "1.0.0"
        })
        
        self.buffer.append(line)
        
        if len(self.buffer) >= 100:
            self.flush()
    
    def flush(self) -> None:
        """Flush buffer to file"""
        if not self.buffer:
            return
        
        filename = f"audit-{datetime.now().strftime('%Y%m%d')}.jsonl"
        filepath = self.output_dir / filename
        
        # Check file size, rotate if needed
        if filepath.exists() and filepath.stat().st_size > self.max_file_size:
            self.rotate_file(filepath)
        
        with open(filepath, 'a') as f:
            f.write('\n'.join(self.buffer) + '\n')
        
        self.buffer = []
    
    def rotate_file(self, filepath: Path) -> None:
        """Rotate audit file"""
        timestamp = datetime.now().strftime('%H%M%S')
        rotated = filepath.with_suffix(f'.{timestamp}.jsonl')
        filepath.rename(rotated)
        
        # Compress old files
        # Clean up files beyond max_files
        self.cleanup_old_files()
```

### 9.3 SIEM Integration

#### SIEM Forwarding Configuration

```yaml
audit:
  siem_export:
    enabled: true
    provider: splunk  # or elastic, qradar, etc.
    
    splunk:
      url: https://splunk.example.com:8088
      token: "SPLUNK_HEC_TOKEN"
      index: "security_events"
      source: "agent-gatefield"
      sourcetype: "gatefield_audit"
      
    batch:
      max_batch_size: 50
      export_interval_seconds: 10
```

#### Splunk HEC Integration

```python
import requests
import json
from typing import List, Dict

class SplunkExporter:
    def __init__(self, config: Dict):
        self.url = config.get('url')
        self.token = config.get('token')
        self.index = config.get('index', 'security_events')
        self.source = config.get('source', 'agent-gatefield')
        self.sourcetype = config.get('sourcetype', 'gatefield_audit')
    
    def export_batch(self, events: List[Dict]) -> Dict:
        """Export batch of events to Splunk HEC"""
        payload = []
        
        for event in events:
            payload.append({
                "time": int(datetime.now().timestamp()),
                "host": "agent-gatefield",
                "source": self.source,
                "sourcetype": self.sourcetype,
                "index": self.index,
                "event": event
            })
        
        headers = {
            "Authorization": f"Splunk {self.token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{self.url}/services/collector/event",
            headers=headers,
            data=json.dumps(payload),
            timeout=30
        )
        
        return response.json()
```

### 9.4 Audit Event Schema

```json
{
  "event_id": "uuid",
  "trace_id": "otel-trace-id",
  "span_id": "span-id",
  "run_id": "run-uuid",
  "event_type": "gate_decision",
  "actor": "gate_engine",
  "payload": {
    "decision": "block",
    "composite_score": 0.95,
    "threshold_version": "v1.2.0",
    "policy_version": "gate-policy-v1",
    "artifact_hash": "sha256:...",
    "static_gate_results": [...],
    "state_vector_version": "encoder-v1.0",
    "retrieved_exemplar_refs": ["doc-id-1", "doc-id-2"],
    "scorer_outputs": [...],
    "action_selected": "artifact_correction",
    "human_override": null
  },
  "payload_hash": "sha256:...",
  "retention_class": "audit",
  "created_at": "RFC3339",
  "schema_version": "1.0.0"
}
```

### 9.5 Retention Policy

| Data Type | Retention Days | Storage |
|---|---|---|
| Decision/audit log | 365 | JSONL + OTLP + Database |
| Trace metadata | 180 | OTLP + Database |
| Raw prompt | 0 (prohibited) | None |
| Redacted artifact body | 90 | Database (redacted only) |
| Human correction log | 365 | Database + JSONL |
| Ephemeral intermediate vectors | 30 | Database (optional) |
| Golden/rejected datasets | Indefinite (explicit delete) | Database |

### 9.6 Error Handling

| Error Condition | Handling |
|---|---|
| OTLP exporter unavailable | Fallback to JSONL local storage, batch retry |
| JSONL write error | Retry with smaller batch, log error |
| SIEM API error | Queue for retry, log error |
| File rotation failure | Log error, continue with current file |
| Storage full | Alert ops, oldest files cleanup |

### 9.7 Testing Requirements

| Test Case | Expected Behavior |
|---|---|
| OTLP export | Events visible in collector |
| JSONL export | Valid JSONL file created |
| File rotation | New file created on size limit |
| SIEM export | Events visible in SIEM |
| Retention cleanup | Old files deleted after retention period |
| Schema validation | All required fields present |

---

## 10. External Dependencies

### 10.1 PostgreSQL/pgvector

**Dependency Type**: P0 (Critical)

#### Requirements

| Requirement | Specification |
|---|---|
| Version | PostgreSQL 15+ with pgvector 0.5+ |
| Connection | Connection pooling (5-20 connections) |
| Storage | Minimum 10GB, expandable to 100GB+ |
| SSL | Required for all connections |
| Backup | Daily backup, 30-day retention |
| HA | Recommended: Primary-replica with automatic failover |

#### Configuration

```yaml
postgres:
  host: postgres-primary.internal
  port: 5432
  database: gatefield
  user: gatefield_app
  
  ssl:
    mode: require
    cert: /etc/ssl/certs/postgres-client.pem
    
  pool:
    min_size: 5
    max_size: 20
    
  backup:
    schedule: daily
    retention_days: 30
    target: s3://backup-bucket/postgres/
```

#### Health Check

```python
def postgres_health_check() -> Dict:
    """Check PostgreSQL health"""
    checks = {
        "connection": check_connection(),
        "pgvector_extension": check_extension("vector"),
        "tables_exist": check_tables(),
        "indexes_valid": check_indexes(),
        "replication_lag": check_replication_lag() if ha_enabled else None
    }
    
    return {
        "status": "healthy" if all(checks.values()) else "degraded",
        "checks": checks
    }
```

#### Failure Handling

| Failure | Action |
|---|---|
| Connection refused | Retry with backoff, alert ops after 30s |
| Extension missing | Block startup, alert ops immediately |
| Table missing | Block startup, alert ops immediately |
| Index corruption | Log error, rebuild index in background |
| Replica lag > 30s | Alert ops, continue with primary |

---

### 10.2 Embedding Provider

**Dependency Type**: P0 (Local provider), P2 (Optional external provider)

#### Requirements

| Requirement | Specification |
|---|---|
| Default provider | local |
| Default model | local-hash-embedding-v1 (1536d) |
| Network dependency | None for default local provider |
| External provider | Optional OpenAI-compatible provider |
| Budget | $500/month limit across storage, compute, and optional provider calls |

#### Configuration

```yaml
embedding_service:
  provider: local
  model: local-hash-embedding-v1
  dimensions: 1536

  optional_openai_compatible:
    enabled: false
    api_key: "${OPENAI_API_KEY}"
    base_url: https://api.openai.com/v1
    model: text-embedding-3-large
```

#### Failure Handling

| Failure | Action |
|---|---|
| Local provider unavailable | Block startup, alert ops immediately |
| Optional external API key invalid | Disable external provider or block startup when explicitly required |
| Rate limit exceeded | Queue requests, exponential backoff |
| Timeout | Retry 3 times, queue if still failing |
| Budget exceeded | Queue embeddings, alert ops |
| Model deprecated | Log warning, plan migration |

---

### 10.3 Monitoring Stack

**Dependency Type**: P1 (Required for enforce)

#### Components

| Component | Purpose | Port |
|---|---|---|
| OpenTelemetry Collector | Trace collection | 4317 (gRPC), 4318 (HTTP) |
| Prometheus | Metrics collection | 9090 |
| Grafana | Dashboard visualization | 3000 |
| Jaeger | Trace UI | 16686 |
| PagerDuty | Alert routing | API |
| Slack | Alert notifications | Webhook |

#### Configuration

```yaml
monitoring:
  otel_collector:
    endpoint: http://otel-collector:4317
    protocol: grpc
    
  prometheus:
    endpoint: http://prometheus:9090
    scrape_interval_seconds: 15
    
  grafana:
    endpoint: http://grafana:3000
    dashboards_path: /etc/grafana/dashboards
    
  jaeger:
    endpoint: http://jaeger:16686
```

#### Health Check

```python
def monitoring_health_check() -> Dict:
    """Check monitoring stack health"""
    checks = {
        "otel_collector": check_otel_collector(),
        "prometheus": check_prometheus(),
        "grafana": check_grafana(),
        "jaeger": check_jaeger()
    }
    
    return {
        "status": "healthy" if all(checks.values()) else "degraded",
        "checks": checks
    }
```

#### Failure Handling

| Failure | Action |
|---|---|
| OTel collector down | Fallback to in-memory buffer |
| Prometheus down | Continue without metrics collection |
| Grafana down | Dashboard unavailable, continue operation |
| Jaeger down | Trace UI unavailable, traces still collected |
| PagerDuty API error | Fallback to Slack alerts |

---

### 10.4 Secret Management

**Dependency Type**: P0 (Critical)

#### Secrets Required

| Secret | Purpose | Storage |
|---|---|---|
| OpenAI API Key | Optional external embedding provider only | Environment variable / Vault |
| PostgreSQL Password | Database connection | Environment variable / Vault |
| PagerDuty Service Key | Alert routing | Environment variable / Vault |
| Slack Webhook URL | Alert notifications | Environment variable / Vault |
| SIEM API Token | Audit export | Environment variable / Vault |
| SSL Certificates | Database connections | File system / Vault |

#### Configuration

```yaml
secrets:
  provider: vault  # or env, aws_secrets_manager, gcp_secret_manager
  
  vault:
    url: https://vault.internal:8200
    path: secret/data/gatefield
    role_id: "${VAULT_ROLE_ID}"
    secret_id: "${VAULT_SECRET_ID}"
    
  rotation:
    enabled: true
    interval_days: 90
```

#### Failure Handling

| Failure | Action |
|---|---|
| Vault unavailable | Fallback to environment variables |
| Secret missing | Block startup, alert ops |
| Secret rotation failed | Alert ops, continue with current secret |

---

### 10.5 Dependency Health Matrix

| Dependency | Startup Required | Runtime Required | Degraded Mode | Fail-Closed |
|---|---|---|---|---|
| PostgreSQL | Yes | Yes | No | Yes |
| pgvector | Yes | Yes | No | Yes |
| OpenAI API | Yes | Yes | Queue embeddings | No (queue) |
| OTel Collector | No | Yes | In-memory buffer | No |
| Prometheus | No | No | Skip metrics | No |
| Grafana | No | No | Dashboard unavailable | No |
| PagerDuty | No | Yes | Slack fallback | No |
| Slack | No | No | Log alerts | No |
| SIEM | No | No | Local storage only | No |
| Vault | No | No | Env fallback | No |

---

## Appendix A: Integration Checklist

### Pre-MVP (Shadow Mode) Requirements

- [ ] PostgreSQL/pgvector installed and configured
- [ ] Connection pool configured and tested
- [ ] HNSW index created and validated
- [ ] OpenAI API key configured and tested
- [ ] Embedding service health check passing
- [ ] OTel collector running and receiving traces
- [ ] Harness adapter contract tests passing
- [ ] Static gate adapters implemented
- [ ] Audit JSONL export working
- [ ] Basic dashboard data available

### Pre-Enforce Requirements

- [ ] Grafana dashboards configured
- [ ] Prometheus metrics collection active
- [ ] Jaeger trace UI accessible
- [ ] PagerDuty integration configured
- [ ] Slack integration configured
- [ ] SIEM integration configured (if required)
- [ ] Human review queue functional
- [ ] Reviewer SLA monitoring active
- [ ] Cost budget alerts configured
- [ ] Replay engine functional

---

## Appendix B: Integration Test Matrix

| Integration | Unit Test | Contract Test | Integration Test | End-to-End Test |
|---|---|---|---|---|
| Harness Adapter | Yes | Yes | Yes | Yes |
| Static Gates | Yes | Yes | Yes | Yes |
| Vector Store | Yes | Yes | Yes | Yes |
| Embedding Service | Yes | No | Yes | Yes |
| Tracing | Yes | Yes | Yes | Yes |
| Dashboard | No | Yes | Yes | Yes |
| Alerts | Yes | Yes | Yes | No (mock) |
| Audit Export | Yes | Yes | Yes | Yes |
| PostgreSQL | No | Yes | Yes | Yes |
| OpenAI API | Yes | No | Yes | Yes |

---

**Document Version**: 1.0.0

**Last Updated**: 2026-04-26

**Owner**: Platform Team

**Review Status**: Draft for MVP review
