# Data Types Specification

This document specifies the complete JSON schemas and data type definitions for the agent-gatefield system. All schemas are version-locked and must maintain backward compatibility as specified in AGF-REQ-007 (Replay reproducibility 99%+).

## Schema Versioning

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | 2026-04-26 | Initial specification from requirements.md frozen state |

**Versioning Rules**:
- All data types must include a `schema_version` field for replay reproducibility
- Schema changes require threshold_version and policy_version updates
- Append-only versioning for judgment_embeddings (valid_from/valid_to)
- State vectors are immutable after run completion

---

## 1. State Vector

The composite state vector is the canonical representation of a run's artifacts, traces, rules, risk, history, and uncertainty. It follows the multi-dimensional encoding approach specified in AGF-REQ-001.

### 1.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://agent-gatefield.example/schemas/state-vector-v1.0.0.json",
  "title": "StateVector",
  "description": "Composite state vector for gate evaluation",
  "type": "object",
  "required": [
    "schema_version",
    "run_id",
    "artifact_id",
    "semantic",
    "rule_violation",
    "test_evidence",
    "risk",
    "historical_decision",
    "uncertainty",
    "context",
    "trajectory",
    "created_at"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "1.0.0",
      "description": "Schema version for replay reproducibility"
    },
    "run_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique run identifier"
    },
    "artifact_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique artifact identifier"
    },
    "semantic": {
      "$ref": "#/definitions/SemanticVector",
      "description": "Dense semantic embedding for meaning comparison"
    },
    "rule_violation": {
      "$ref": "#/definitions/RuleViolationVector",
      "description": "Sparse severity vector from static gates"
    },
    "test_evidence": {
      "$ref": "#/definitions/TestEvidenceVector",
      "description": "Numeric evidence from test execution"
    },
    "risk": {
      "$ref": "#/definitions/RiskVector",
      "description": "Numeric/categorical risk context"
    },
    "historical_decision": {
      "$ref": "#/definitions/HistoricalDecisionVector",
      "description": "Similarity to historical judgments"
    },
    "uncertainty": {
      "$ref": "#/definitions/UncertaintyVector",
      "description": "Confidence and variance metrics"
    },
    "context": {
      "$ref": "#/definitions/ContextMetadata",
      "description": "Metadata for filtering and policy scope"
    },
    "trajectory": {
      "$ref": "#/definitions/TrajectoryFeatures",
      "description": "Sequential features for drift/anomaly detection"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "State vector creation timestamp (RFC3339)"
    },
    "encoder_version": {
      "type": "string",
      "description": "Encoder implementation version",
      "default": "encoder-v1.0.0"
    },
    "intermediate": {
      "type": "boolean",
      "description": "True if mid-run intermediate vector",
      "default": false
    }
  },
  "additionalProperties": false,
  "definitions": {
    "SemanticVector": {
      "type": "object",
      "required": ["provider", "model", "dims", "vector_ref"],
      "properties": {
        "provider": {
          "type": "string",
          "enum": ["local", "openai", "openai-compatible", "mock"],
          "description": "Embedding provider. local is the default and requires no external API key."
        },
        "model": {
          "type": "string",
          "enum": ["local-hash-embedding-v1", "text-embedding-3-small", "text-embedding-3-large", "custom"],
          "description": "Embedding model identifier"
        },
        "dims": {
          "type": "integer",
          "minimum": 256,
          "maximum": 3072,
          "description": "Vector dimension count"
        },
        "vector_ref": {
          "type": "string",
          "pattern": "^vec://[a-f0-9]{64}$",
          "description": "URI reference to stored vector (SHA256 hash)"
        },
        "content_hash": {
          "type": "string",
          "pattern": "^sha256:[a-f0-9]{64}$",
          "description": "Content hash for deduplication"
        }
      },
      "additionalProperties": false
    },
    "RuleViolationVector": {
      "type": "object",
      "required": [],
      "properties": {
        "secret": {
          "type": "integer",
          "minimum": 0,
          "description": "Secret/credential detection count (OWASP LLM05)"
        },
        "sast_high": {
          "type": "integer",
          "minimum": 0,
          "description": "High severity SAST findings (OWASP LLM06)"
        },
        "sast_medium": {
          "type": "integer",
          "minimum": 0,
          "description": "Medium severity SAST findings"
        },
        "sast_low": {
          "type": "integer",
          "minimum": 0,
          "description": "Low severity SAST findings"
        },
        "license_unknown": {
          "type": "integer",
          "minimum": 0,
          "description": "Unknown/unapproved license count"
        },
        "license_forbidden": {
          "type": "integer",
          "minimum": 0,
          "description": "Forbidden license count"
        },
        "lint_error": {
          "type": "integer",
          "minimum": 0,
          "description": "Lint error count"
        },
        "lint_warning": {
          "type": "integer",
          "minimum": 0,
          "description": "Lint warning count"
        },
        "type_error": {
          "type": "integer",
          "minimum": 0,
          "description": "Type check error count"
        },
        "tool_policy_deny": {
          "type": "integer",
          "minimum": 0,
          "description": "Tool policy deny count (OWASP LLM06)"
        }
      },
      "additionalProperties": {
        "type": "integer",
        "minimum": 0
      }
    },
    "TestEvidenceVector": {
      "type": "object",
      "required": [],
      "properties": {
        "unit_pass_rate": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Unit test pass rate (0.0-1.0)"
        },
        "changed_modules_tested": {
          "type": "integer",
          "minimum": 0,
          "description": "Count of changed modules with tests"
        },
        "coverage_delta": {
          "type": "number",
          "minimum": -1.0,
          "maximum": 1.0,
          "description": "Coverage change vs baseline"
        },
        "integration_pass_rate": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Integration test pass rate"
        },
        "new_tests_added": {
          "type": "integer",
          "minimum": 0,
          "description": "New test cases added"
        }
      },
      "additionalProperties": {
        "type": "number"
      }
    },
    "RiskVector": {
      "type": "object",
      "required": [],
      "properties": {
        "prod_write": {
          "type": "integer",
          "enum": [0, 1],
          "description": "Production write access flag"
        },
        "pii_level": {
          "type": "integer",
          "enum": [0, 1, 2, 3],
          "description": "PII exposure level (0=none, 3=high)"
        },
        "network_egress": {
          "type": "integer",
          "enum": [0, 1],
          "description": "External network access flag"
        },
        "permission_level": {
          "type": "string",
          "enum": ["read", "write", "admin"],
          "description": "Permission scope level"
        },
        "data_classification": {
          "type": "string",
          "enum": ["public", "internal", "confidential", "pii-sensitive", "restricted"],
          "description": "Data classification per data protection policy"
        },
        "service_criticality": {
          "type": "string",
          "enum": ["low", "medium", "high", "critical"],
          "description": "Service importance level"
        },
        "env": {
          "type": "string",
          "enum": ["local", "ci", "staging", "production_shadow", "production_enforce"],
          "description": "Execution environment"
        }
      },
      "additionalProperties": false
    },
    "HistoricalDecisionVector": {
      "type": "object",
      "required": [],
      "properties": {
        "accept_sim": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Max cosine similarity to accepted centroid"
        },
        "reject_sim": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Max cosine similarity to rejected centroid"
        },
        "judgment_log_sim": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Max cosine similarity to judgment log"
        },
        "constitution_sim": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Cosine similarity to constitution centroid"
        },
        "taboo_max_sim": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Max cosine similarity to taboo corpus"
        },
        "nearest_doc_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "format": "uuid"
          },
          "maxItems": 10,
          "description": "Top 10 nearest document IDs from KB"
        }
      },
      "additionalProperties": false
    },
    "UncertaintyVector": {
      "type": "object",
      "required": [],
      "properties": {
        "judge_std": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Standard deviation across evaluator scores"
        },
        "tool_error_rate": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Tool execution failure rate"
        },
        "self_confidence": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Model self-reported confidence"
        },
        "evidence_missing": {
          "type": "integer",
          "enum": [0, 1],
          "description": "Flag for missing required evidence"
        },
        "kb_coverage": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "KB coverage for this artifact type"
        }
      },
      "additionalProperties": false
    },
    "ContextMetadata": {
      "type": "object",
      "required": ["repo", "artifact_type"],
      "properties": {
        "repo": {
          "type": "string",
          "minLength": 1,
          "description": "Repository or service identifier"
        },
        "artifact_type": {
          "type": "string",
          "enum": ["code_patch", "document_diff", "tool_execution_plan", "pr_proposal"],
          "description": "Artifact type classification"
        },
        "env": {
          "type": "string",
          "enum": ["local", "ci", "staging", "production_shadow", "production_enforce"],
          "description": "Execution environment"
        },
        "branch": {
          "type": "string",
          "description": "Git branch name"
        },
        "commit": {
          "type": "string",
          "pattern": "^[a-f0-9]{40}$",
          "description": "Git commit SHA"
        },
        "author": {
          "type": "string",
          "description": "Artifact author (hashed if PII)"
        },
        "service": {
          "type": "string",
          "description": "Target service identifier"
        },
        "module": {
          "type": "string",
          "description": "Target module path"
        }
      },
      "additionalProperties": {
        "type": "string"
      }
    },
    "TrajectoryFeatures": {
      "type": "object",
      "required": [],
      "properties": {
        "delta_semantic": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Semantic change vs previous step"
        },
        "tool_calls": {
          "type": "integer",
          "minimum": 0,
          "description": "Total tool call count"
        },
        "branch_count": {
          "type": "integer",
          "minimum": 0,
          "description": "Decision branch count"
        },
        "step_index": {
          "type": "integer",
          "minimum": 0,
          "description": "Step position in sequence"
        },
        "retry_count": {
          "type": "integer",
          "minimum": 0,
          "description": "Retry/loop iteration count"
        },
        "ewma_drift": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "EWMA drift from accepted baseline"
        }
      },
      "additionalProperties": {
        "type": "number"
      }
    }
  }
}
```

### 1.2 Field Descriptions and Constraints

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `schema_version` | string | Yes | Must be "1.0.0" | Schema version for replay reproducibility |
| `run_id` | uuid | Yes | UUID format | Unique run identifier |
| `artifact_id` | uuid | Yes | UUID format | Unique artifact identifier |
| `semantic` | object | Yes | See SemanticVector | Dense vector for semantic similarity |
| `rule_violation` | object | Yes | Non-negative integers | Static gate severity counts |
| `test_evidence` | object | Yes | 0.0-1.0 or integers | Test execution evidence |
| `risk` | object | Yes | See RiskVector | Context-dependent risk weighting |
| `historical_decision` | object | Yes | 0.0-1.0 | Similarity to historical KB |
| `uncertainty` | object | Yes | 0.0-1.0 | Confidence and variance metrics |
| `context` | object | Yes | See ContextMetadata | Metadata for filtering/scoping |
| `trajectory` | object | Yes | See TrajectoryFeatures | Sequential drift/anomaly features |
| `created_at` | datetime | Yes | RFC3339 | Creation timestamp |
| `encoder_version` | string | No | Default: encoder-v1.0.0 | Encoder implementation version |
| `intermediate` | boolean | No | Default: false | Mid-run intermediate flag |

### 1.3 Semantic Vector Component Details

| Component | Model | Dimensions | Use Case | Cost Estimate |
|---|---|---|---|---|
| Default | local-hash-embedding-v1 | 1536 | Local-first gate scoring | Local CPU/storage only |
| High-precision | local-hash-embedding-v1 | 3072 | Wider local vector space | Local CPU/storage only |
| Reduced | local-hash-embedding-v1 | Custom (384-1536) | Storage optimization | Local CPU/storage only |
| Optional external | text-embedding-3-large | 1536/3072 | Explicit OpenAI-compatible provider | Provider pricing |

**Storage Cost (Monthly)**:
- 100k items @ 1536d: ~0.67 GB raw
- 1M items @ 1536d: ~6.68 GB raw
- 10M items @ 1536d: ~66.76 GB raw

### 1.4 Example Instance

```json
{
  "schema_version": "1.0.0",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "artifact_id": "660e8400-e29b-41d4-a716-446655440001",
  "semantic": {
    "provider": "local",
    "model": "local-hash-embedding-v1",
    "dims": 1536,
    "vector_ref": "vec://a1b2c3d4e5f6...",
    "content_hash": "sha256:abc123def456..."
  },
  "rule_violation": {
    "secret": 0,
    "sast_high": 1,
    "sast_medium": 2,
    "license_unknown": 0,
    "lint_error": 0,
    "tool_policy_deny": 0
  },
  "test_evidence": {
    "unit_pass_rate": 0.97,
    "changed_modules_tested": 4,
    "coverage_delta": 0.02,
    "new_tests_added": 2
  },
  "risk": {
    "prod_write": 0,
    "pii_level": 1,
    "network_egress": 1,
    "permission_level": "write",
    "data_classification": "internal",
    "service_criticality": "medium",
    "env": "staging"
  },
  "historical_decision": {
    "accept_sim": 0.84,
    "reject_sim": 0.31,
    "judgment_log_sim": 0.66,
    "constitution_sim": 0.72,
    "taboo_max_sim": 0.12,
    "nearest_doc_ids": [
      "accepted-001",
      "accepted-023",
      "judgment-log-042"
    ]
  },
  "uncertainty": {
    "judge_std": 0.08,
    "tool_error_rate": 0.02,
    "self_confidence": 0.74,
    "evidence_missing": 0,
    "kb_coverage": 0.85
  },
  "context": {
    "repo": "service-a",
    "artifact_type": "code_patch",
    "env": "staging",
    "branch": "feature/new-auth",
    "commit": "a1b2c3d4e5f6789012345678901234567890abcd",
    "module": "auth/login"
  },
  "trajectory": {
    "delta_semantic": 0.07,
    "tool_calls": 9,
    "branch_count": 2,
    "step_index": 3,
    "retry_count": 0,
    "ewma_drift": 0.05
  },
  "created_at": "2026-04-26T10:30:00Z",
  "encoder_version": "encoder-v1.0.0",
  "intermediate": false
}
```

### 1.5 Version Compatibility Notes

- **v1.0.0**: Initial frozen schema for MVP
- Backward compatibility: All v1.x schemas must accept v1.0.0 instances
- Forward compatibility: New optional fields may be added, required fields cannot change
- Replay reproducibility: Same schema_version + threshold_version must produce identical decisions (AGF-REQ-007)

---

## 2. Trace Event

Trace events represent run lifecycle events from the harness. All events must have OTel-compatible trace_id/span_id for correlation (AGF-REQ-009).

### 2.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://agent-gatefield.example/schemas/trace-event-v1.0.0.json",
  "title": "TraceEvent",
  "description": "Run lifecycle event from harness",
  "type": "object",
  "required": [
    "schema_version",
    "run_id",
    "trace_id",
    "span_id",
    "event_type",
    "timestamp",
    "actor"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "1.0.0",
      "description": "Schema version"
    },
    "run_id": {
      "type": "string",
      "format": "uuid",
      "description": "Run identifier"
    },
    "trace_id": {
      "type": "string",
      "pattern": "^[a-f0-9]{32}$",
      "description": "OTel trace ID (32 hex chars)"
    },
    "span_id": {
      "type": "string",
      "pattern": "^[a-f0-9]{16}$",
      "description": "OTel span ID (16 hex chars)"
    },
    "parent_span_id": {
      "type": "string",
      "pattern": "^[a-f0-9]{16}$",
      "description": "Parent span ID for hierarchy"
    },
    "event_type": {
      "type": "string",
      "enum": [
        "run_started",
        "step_started",
        "tool_call_requested",
        "tool_call_completed",
        "artifact_emitted",
        "static_gate_completed",
        "gate_decision",
        "run_completed",
        "run_failed",
        "run_paused",
        "run_resumed"
      ],
      "description": "Event type from harness lifecycle"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "Event timestamp (RFC3339)"
    },
    "actor": {
      "type": "string",
      "enum": ["agent", "tool", "reviewer", "system", "user"],
      "description": "Event actor type"
    },
    "artifact_ref": {
      "type": "string",
      "pattern": "^artifact://",
      "description": "Artifact URI reference"
    },
    "checkpoint_ref": {
      "type": "string",
      "pattern": "^checkpoint://",
      "description": "Checkpoint URI reference"
    },
    "policy_version": {
      "type": "string",
      "description": "Active policy version"
    },
    "payload_ref": {
      "type": "string",
      "pattern": "^blob://",
      "description": "Blob reference (redacted or hashed)"
    },
    "payload_hash": {
      "type": "string",
      "pattern": "^sha256:[a-f0-9]{64}$",
      "description": "Payload content hash"
    },
    "data_classification": {
      "type": "string",
      "enum": ["public", "internal", "confidential", "pii-sensitive", "restricted"],
      "description": "Data classification per protection policy"
    },
    "redaction_status": {
      "type": "string",
      "enum": ["none", "partial", "full", "failed"],
      "description": "Redaction applied status"
    },
    "retention_class": {
      "type": "string",
      "enum": ["audit", "ops", "pii-sensitive", "ephemeral"],
      "description": "Retention policy class"
    },
    "metadata": {
      "type": "object",
      "additionalProperties": {
        "type": ["string", "number", "boolean"]
      },
      "description": "Additional event metadata"
    }
  },
  "additionalProperties": false
}
```

### 2.2 Event Type Definitions

| Event Type | Description | Required Fields | Trigger |
|---|---|---|---|
| `run_started` | Run execution begins | run_id, trace_id, actor | Harness start |
| `step_started` | Individual step begins | run_id, span_id, step_id | Step execution |
| `tool_call_requested` | Tool execution requested | run_id, tool_name, payload_hash | Tool invoke |
| `tool_call_completed` | Tool execution finished | run_id, tool_name, result_hash | Tool return |
| `artifact_emitted` | Artifact produced | run_id, artifact_ref | Artifact output |
| `static_gate_completed` | Static gate finished | run_id, gate_name, status | Gate result |
| `gate_decision` | Gate decision made | run_id, decision, threshold_version | Decision |
| `run_completed` | Run finished successfully | run_id, trace_id | Success end |
| `run_failed` | Run terminated with error | run_id, error_type | Failure end |
| `run_paused` | Run paused for review | run_id, checkpoint_ref | Hold decision |
| `run_resumed` | Run resumed from checkpoint | run_id, checkpoint_ref | Review approve |

### 2.3 Actor Types

| Actor | Description | Events |
|---|---|---|
| `agent` | AI agent action | run_started, step_started, artifact_emitted |
| `tool` | Tool execution | tool_call_requested, tool_call_completed |
| `reviewer` | Human reviewer action | gate_decision (override), run_resumed |
| `system` | System/gate action | static_gate_completed, run_failed |
| `user` | External user trigger | run_started (user-initiated) |

### 2.4 Example Instance

```json
{
  "schema_version": "1.0.0",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "trace_id": "a1b2c3d4e5f6789012345678901234ab",
  "span_id": "1234567890abcdef",
  "parent_span_id": "abcdef1234567890",
  "event_type": "tool_call_requested",
  "timestamp": "2026-04-26T10:30:00Z",
  "actor": "agent",
  "artifact_ref": null,
  "checkpoint_ref": null,
  "policy_version": "gate-policy-v1",
  "payload_ref": "blob://redacted-abc123",
  "payload_hash": "sha256:def456abc789...",
  "data_classification": "internal",
  "redaction_status": "partial",
  "retention_class": "ops",
  "metadata": {
    "tool_name": "bash",
    "tool_args_hash": "sha256:tool-args-hash",
    "risk_level": "high"
  }
}
```

### 2.5 Harness API Contract (Minimum I/O)

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

**Contract Requirements (AGF-REQ-001)**:
- All events must have trace_id/span_id
- Payload is hash/redacted reference, not full content
- Unclassified payload is treated as `restricted`

---

## 3. Decision Packet

The decision packet is the output from the gate evaluation containing the final decision, contributing factors, exemplars, and action recommendations.

### 3.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://agent-gatefield.example/schemas/decision-packet-v1.0.0.json",
  "title": "DecisionPacket",
  "description": "Gate decision output with explanation",
  "type": "object",
  "required": [
    "schema_version",
    "decision_id",
    "run_id",
    "artifact_id",
    "decision",
    "composite_score",
    "factors",
    "exemplar_refs",
    "action",
    "threshold_version",
    "policy_version",
    "static_gate_summary",
    "created_at"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "1.0.0",
      "description": "Schema version"
    },
    "decision_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique decision identifier"
    },
    "run_id": {
      "type": "string",
      "format": "uuid",
      "description": "Run identifier"
    },
    "artifact_id": {
      "type": "string",
      "format": "uuid",
      "description": "Artifact identifier"
    },
    "decision": {
      "type": "string",
      "enum": ["pass", "warn", "hold", "block"],
      "description": "Gate decision state"
    },
    "composite_score": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Weighted composite score"
    },
    "factors": {
      "type": "array",
      "minItems": 1,
      "maxItems": 10,
      "items": {
        "$ref": "#/definitions/ScoreFactor"
      },
      "description": "Top contributing factors (sorted by contribution)"
    },
    "exemplar_refs": {
      "type": "array",
      "minItems": 0,
      "maxItems": 5,
      "items": {
        "$ref": "#/definitions/ExemplarRef"
      },
      "description": "Top 5 nearest exemplars from KB (AGF-REQ-003)"
    },
    "action": {
      "$ref": "#/definitions/ActionRecommendation",
      "description": "Recommended action"
    },
    "threshold_version": {
      "type": "string",
      "pattern": "^sha256:[a-f0-9]{64}$",
      "description": "Threshold config hash for reproducibility"
    },
    "policy_version": {
      "type": "string",
      "description": "Policy version identifier"
    },
    "artifact_ref": {
      "type": ["object", "null"],
      "description": "Artifact URI plus diff_hash for downstream approval binding"
    },
    "diff_hash": {
      "type": "string",
      "description": "Artifact diff hash mirrored at top level for adapter compatibility"
    },
    "static_gate_summary": {
      "$ref": "#/definitions/StaticGateSummary",
      "description": "Summary of static gate results"
    },
    "hard_override": {
      "type": "string",
      "enum": ["secret_found", "prod_write_taboo", "tool_policy_deny", "high_privilege_uncertain"],
      "description": "Hard override rule triggered (if any)"
    },
    "self_correction_count": {
      "type": "integer",
      "minimum": 0,
      "maximum": 2,
      "description": "Self-correction attempts (max 2)"
    },
    "review_override": {
      "$ref": "#/definitions/ReviewOverride",
      "description": "Human review override (if applicable)"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "Decision timestamp"
    },
    "trace_id": {
      "type": "string",
      "pattern": "^[a-f0-9]{32}$",
      "description": "OTel trace ID for correlation"
    },
    "state_vector_ref": {
      "type": "string",
      "pattern": "^state://",
      "description": "Reference to full state vector"
    }
  },
  "additionalProperties": false,
  "definitions": {
    "ScoreFactor": {
      "type": "object",
      "required": ["name", "value", "weight", "contribution"],
      "properties": {
        "name": {
          "type": "string",
          "enum": [
            "constitution_alignment",
            "taboo_proximity",
            "accept_similarity",
            "reject_similarity",
            "direction_score",
            "drift_score",
            "anomaly_score",
            "uncertainty_score",
            "rule_violation",
            "test_evidence"
          ],
          "description": "Factor name"
        },
        "value": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Raw factor value"
        },
        "weight": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Factor weight in composite"
        },
        "contribution": {
          "type": "number",
          "description": "Weighted contribution to score"
        },
        "threshold": {
          "type": "number",
          "description": "Threshold value for this factor"
        },
        "threshold_type": {
          "type": "string",
          "enum": ["warn", "block"],
          "description": "Threshold type exceeded (if applicable)"
        }
      },
      "additionalProperties": false
    },
    "ExemplarRef": {
      "type": "object",
      "required": ["doc_id", "axis_type", "similarity"],
      "properties": {
        "doc_id": {
          "type": "string",
          "format": "uuid",
          "description": "Document ID from KB"
        },
        "axis_type": {
          "type": "string",
          "enum": ["constitution", "taboo", "accepted", "rejected", "judgment_log"],
          "description": "Judgment axis"
        },
        "similarity": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "description": "Cosine similarity"
        },
        "version": {
          "type": "string",
          "description": "Document version"
        },
        "text_excerpt": {
          "type": "string",
          "maxLength": 500,
          "description": "Short excerpt (redacted if needed)"
        }
      },
      "additionalProperties": false
    },
    "ActionRecommendation": {
      "type": "object",
      "required": ["action_type"],
      "properties": {
        "action_type": {
          "type": "string",
          "enum": [
            "continue",
            "self_correct",
            "hold_for_review",
            "block",
            "artifact_correction",
            "process_correction",
            "prompt_correction"
          ],
          "description": "Recommended action type"
        },
        "correction_target": {
          "type": "string",
          "description": "Target for correction (if applicable)"
        },
        "correction_details": {
          "type": "object",
          "description": "Specific correction instructions"
        },
        "checkpoint_ref": {
          "type": "string",
          "pattern": "^checkpoint://",
          "description": "Checkpoint for resume (if hold)"
        }
      },
      "additionalProperties": false
    },
    "StaticGateSummary": {
      "type": "object",
      "required": ["gates_executed", "all_passed"],
      "properties": {
        "gates_executed": {
          "type": "array",
          "items": {
            "type": "string"
          },
          "description": "Static gates that ran"
        },
        "all_passed": {
          "type": "boolean",
          "description": "All gates passed"
        },
        "hard_failures": {
          "type": "array",
          "items": {
            "$ref": "#/definitions/StaticGateFailure"
          },
          "description": "Hard fail gates"
        },
        "warnings": {
          "type": "array",
          "items": {
            "$ref": "#/definitions/StaticGateWarning"
          },
          "description": "Warning gates"
        }
      },
      "additionalProperties": false
    },
    "StaticGateFailure": {
      "type": "object",
      "required": ["gate_name", "severity", "evidence_ref"],
      "properties": {
        "gate_name": {
          "type": "string",
          "description": "Gate name"
        },
        "severity": {
          "type": "string",
          "enum": ["high", "critical"],
          "description": "Failure severity"
        },
        "evidence_ref": {
          "type": "string",
          "description": "Evidence reference URI"
        },
        "rule_id": {
          "type": "string",
          "description": "Specific rule violated"
        }
      },
      "additionalProperties": false
    },
    "StaticGateWarning": {
      "type": "object",
      "required": ["gate_name", "count"],
      "properties": {
        "gate_name": {
          "type": "string",
          "description": "Gate name"
        },
        "count": {
          "type": "integer",
          "description": "Warning count"
        }
      },
      "additionalProperties": false
    },
    "ReviewOverride": {
      "type": "object",
      "required": ["reviewer", "original_decision", "override_decision", "comment"],
      "properties": {
        "reviewer": {
          "type": "string",
          "description": "Reviewer identifier"
        },
        "original_decision": {
          "type": "string",
          "enum": ["pass", "warn", "hold", "block"],
          "description": "Decision before override"
        },
        "override_decision": {
          "type": "string",
          "enum": ["pass", "warn", "hold", "block"],
          "description": "Decision after override"
        },
        "comment": {
          "type": "string",
          "maxLength": 1000,
          "description": "Reviewer comment (redacted)"
        },
        "correction": {
          "$ref": "#/definitions/CorrectionAction",
          "description": "Correction action (if applicable)"
        },
        "reviewed_at": {
          "type": "string",
          "format": "date-time",
          "description": "Review timestamp"
        }
      },
      "additionalProperties": false
    },
    "CorrectionAction": {
      "type": "object",
      "required": ["correction_type", "target"],
      "properties": {
        "correction_type": {
          "type": "string",
          "enum": ["artifact", "process", "prompt"],
          "description": "Correction type"
        },
        "target": {
          "type": "string",
          "description": "Correction target"
        },
        "details": {
          "type": "object",
          "description": "Correction details"
        }
      },
      "additionalProperties": false
    }
  }
}
```

### 3.2 Decision States and Transitions

| State | Description | Transition Conditions |
|---|---|---|
| `pass` | Continue workflow | Composite score below warn threshold |
| `warn` | Self-correction required | Composite score exceeds warn threshold |
| `hold` | Human review required | High privilege + risk, or self-correction failed |
| `block` | Stop workflow | Hard fail, hard override, or reviewer reject |

**State Transition Priority**: hard_override > tool_policy > data_protection > reviewer_decision > composite_score > self_correction

### 3.3 Example Instance

```json
{
  "schema_version": "1.0.0",
  "decision_id": "770e8400-e29b-41d4-a716-446655440002",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "artifact_id": "660e8400-e29b-41d4-a716-446655440001",
  "decision": "hold",
  "composite_score": 0.72,
  "factors": [
    {
      "name": "taboo_proximity",
      "value": 0.85,
      "weight": 0.30,
      "contribution": 0.255,
      "threshold": 0.80,
      "threshold_type": "warn"
    },
    {
      "name": "uncertainty_score",
      "value": 0.18,
      "weight": 0.05,
      "contribution": 0.009
    },
    {
      "name": "constitution_alignment",
      "value": 0.72,
      "weight": 0.20,
      "contribution": 0.144
    }
  ],
  "exemplar_refs": [
    {
      "doc_id": "taboo-001",
      "axis_type": "taboo",
      "similarity": 0.85,
      "version": "v1",
      "text_excerpt": "Unvalidated SQL input pattern..."
    },
    {
      "doc_id": "accepted-023",
      "axis_type": "accepted",
      "similarity": 0.78
    }
  ],
  "action": {
    "action_type": "hold_for_review",
    "checkpoint_ref": "checkpoint://run-abc/cp-001"
  },
  "threshold_version": "sha256:threshold-config-hash",
  "policy_version": "gate-policy-v1",
  "static_gate_summary": {
    "gates_executed": ["lint", "typecheck", "sast", "secret_scan"],
    "all_passed": true,
    "hard_failures": [],
    "warnings": [
      {"gate_name": "lint", "count": 2}
    ]
  },
  "hard_override": null,
  "self_correction_count": 0,
  "created_at": "2026-04-26T10:30:00Z",
  "trace_id": "a1b2c3d4e5f6789012345678901234ab",
  "state_vector_ref": "state://550e8400..."
}
```

---

## 4. Judgment Document

Judgment documents are KB entries for constitution, taboo, accepted examples, rejected examples, and judgment logs.

### 4.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://agent-gatefield.example/schemas/judgment-document-v1.0.0.json",
  "title": "JudgmentDocument",
  "description": "Knowledge base document for judgment axis",
  "type": "object",
  "required": [
    "schema_version",
    "doc_id",
    "axis_type",
    "text",
    "source_type",
    "status",
    "created_at"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "1.0.0",
      "description": "Schema version"
    },
    "doc_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique document identifier"
    },
    "axis_type": {
      "type": "string",
      "enum": ["constitution", "taboo", "accepted", "rejected", "judgment_log"],
      "description": "Judgment axis classification"
    },
    "text": {
      "type": "string",
      "minLength": 10,
      "description": "Document content (redacted if needed)"
    },
    "source_type": {
      "type": "string",
      "enum": ["manual", "incident", "review", "golden", "postmortem", "promoted"],
      "description": "Document source origin"
    },
    "version": {
      "type": "string",
      "description": "Document version",
      "default": "v1"
    },
    "labels": {
      "type": "object",
      "additionalProperties": {
        "type": ["string", "number", "boolean"]
      },
      "description": "Arbitrary labels/tags"
    },
    "scope": {
      "type": "string",
      "description": "Applicability scope (repo/service)"
    },
    "status": {
      "type": "string",
      "enum": ["active", "deprecated", "pending_review"],
      "description": "Document status"
    },
    "redaction_status": {
      "type": "string",
      "enum": ["none", "partial", "full"],
      "description": "Redaction applied status"
    },
    "content_hash": {
      "type": "string",
      "pattern": "^sha256:[a-f0-9]{64}$",
      "description": "Content hash for versioning"
    },
    "embedding_ref": {
      "type": "string",
      "pattern": "^embed://",
      "description": "Reference to embedding"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "Creation timestamp"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "description": "Last update timestamp"
    },
    "created_by": {
      "type": "string",
      "description": "Creator identifier"
    },
    "reviewer": {
      "type": "string",
      "description": "Reviewer identifier (if from review)"
    },
    "run_id": {
      "type": "string",
      "format": "uuid",
      "description": "Originating run ID (if promoted)"
    },
    "decision": {
      "type": "string",
      "enum": ["pass", "warn", "hold", "block"],
      "description": "Original decision (for judgment_log)"
    },
    "rationale": {
      "type": "string",
      "description": "Decision rationale (for judgment_log)"
    },
    "risk_class": {
      "type": "string",
      "enum": ["low", "medium", "high", "critical"],
      "description": "Risk classification (for taboo)"
    }
  },
  "additionalProperties": false
}
```

### 4.2 Axis Types and Contents

| Axis Type | Content Examples | Source Types | Required Labels |
|---|---|---|---|
| `constitution` | Design principles, ADRs, conventions | manual, golden | quality_axis |
| `taboo` | Forbidden patterns, injection examples, dangerous ops | incident, manual | risk_class, taboo_type |
| `accepted` | Merged PRs, approved artifacts, golden traces | golden, promoted | quality_axis, reviewer |
| `rejected` | Rejected PRs, abort examples, corrections | review, incident | reason_code, expected_state |
| `judgment_log` | Human decisions, corrections, rationale | review, promoted | decision, rationale |

### 4.3 Example Instance (Taboo Document)

```json
{
  "schema_version": "1.0.0",
  "doc_id": "880e8400-e29b-41d4-a716-446655440003",
  "axis_type": "taboo",
  "text": "Unvalidated SQL string concatenation in query construction. Pattern: SELECT * FROM users WHERE id = '${user_input}'",
  "source_type": "incident",
  "version": "v1",
  "labels": {
    "taboo_type": "sql_injection",
    "owasp_category": "LLM06",
    "cwe": "CWE-89"
  },
  "scope": "all",
  "status": "active",
  "redaction_status": "partial",
  "content_hash": "sha256:abc123...",
  "embedding_ref": "embed://880e8400...",
  "created_at": "2026-01-15T08:00:00Z",
  "created_by": "security-team",
  "risk_class": "critical"
}
```

### 4.4 Example Instance (Accepted Document)

```json
{
  "schema_version": "1.0.0",
  "doc_id": "990e8400-e29b-41d4-a716-446655440004",
  "axis_type": "accepted",
  "text": "Parameterized query implementation for user lookup. Uses prepared statements with bound parameters.",
  "source_type": "golden",
  "version": "v1",
  "labels": {
    "quality_axis": "security",
    "artifact_type": "code_patch",
    "module": "auth/login"
  },
  "scope": "service-a",
  "status": "active",
  "redaction_status": "none",
  "content_hash": "sha256:def456...",
  "embedding_ref": "embed://990e8400...",
  "created_at": "2026-02-20T14:00:00Z",
  "created_by": "repo-owner",
  "reviewer": "security-lead"
}
```

---

## 5. Gate Result (Static)

Static gate results from CI/scanners. Immutable after ingestion.

### 5.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://agent-gatefield.example/schemas/static-gate-result-v1.0.0.json",
  "title": "StaticGateResult",
  "description": "Static gate execution result",
  "type": "object",
  "required": [
    "schema_version",
    "gate_result_id",
    "run_id",
    "gate_name",
    "status",
    "created_at"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "1.0.0",
      "description": "Schema version"
    },
    "gate_result_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique result identifier"
    },
    "run_id": {
      "type": "string",
      "format": "uuid",
      "description": "Run identifier"
    },
    "gate_name": {
      "type": "string",
      "enum": ["lint", "typecheck", "tests", "sast", "secret_scan", "license_scan", "tool_policy"],
      "description": "Static gate name"
    },
    "status": {
      "type": "string",
      "enum": ["pass", "warn", "fail", "critical", "unavailable"],
      "description": "Gate execution status"
    },
    "severity": {
      "type": "string",
      "enum": ["low", "medium", "high", "critical"],
      "description": "Issue severity (if fail/warn)"
    },
    "count": {
      "type": "integer",
      "minimum": 0,
      "description": "Issue count"
    },
    "evidence_ref": {
      "type": "string",
      "description": "Evidence reference URI"
    },
    "details": {
      "type": "object",
      "description": "Gate-specific details"
    },
    "scanner": {
      "type": "string",
      "description": "Scanner/engine name"
    },
    "rule_ids": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Specific rules violated"
    },
    "engine_version": {
      "type": "string",
      "description": "Scanner engine version"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "Result timestamp"
    },
    "immutable": {
      "type": "boolean",
      "const": true,
      "description": "Result is immutable"
    }
  },
  "additionalProperties": false
}
```

### 5.2 Gate Types and Severities

| Gate Name | Engine | Hard Fail Condition | Warn Condition |
|---|---|---|---|
| `lint` | flake8, eslint | error > 0 | warning > 0 |
| `typecheck` | mypy, tsc | error > 0 | - |
| `tests` | pytest, jest | pass_rate < 1.0 | coverage < threshold |
| `sast` | semgrep, codeql | high/critical > 0 | medium > 0 |
| `secret_scan` | trivy | any found | - |
| `license_scan` | trivy | forbidden > 0 | unknown > 0 |
| `tool_policy` | policy engine | deny > 0 | - |

### 5.3 Example Instance

```json
{
  "schema_version": "1.0.0",
  "gate_result_id": "aa0e8400-e29b-41d4-a716-446655440005",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "gate_name": "sast",
  "status": "fail",
  "severity": "high",
  "count": 1,
  "evidence_ref": "sast://semgrep/sql-injection",
  "details": {
    "findings": [
      {
        "rule_id": "sql-injection",
        "file": "auth/login.py",
        "line": 42,
        "message": "Unvalidated SQL string concatenation"
      }
    ]
  },
  "scanner": "semgrep",
  "rule_ids": ["sql-injection"],
  "engine_version": "semgrep-1.50.0",
  "created_at": "2026-04-26T10:25:00Z",
  "immutable": true
}
```

---

## 6. Review Item

Review queue item for human review workflow.

### 6.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://agent-gatefield.example/schemas/review-item-v1.0.0.json",
  "title": "ReviewItem",
  "description": "Human review queue item",
  "type": "object",
  "required": [
    "schema_version",
    "review_id",
    "decision_id",
    "run_id",
    "state",
    "composite_score",
    "severity",
    "top_factors",
    "artifact_ref",
    "trace_ref",
    "created_at"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "1.0.0",
      "description": "Schema version"
    },
    "review_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique review identifier"
    },
    "decision_id": {
      "type": "string",
      "format": "uuid",
      "description": "Decision identifier"
    },
    "run_id": {
      "type": "string",
      "format": "uuid",
      "description": "Run identifier"
    },
    "state": {
      "type": "string",
      "enum": ["pass", "warn", "hold", "block"],
      "description": "Gate state"
    },
    "composite_score": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Composite score"
    },
    "severity": {
      "type": "string",
      "enum": ["critical", "high", "medium", "low"],
      "description": "Review severity"
    },
    "top_factors": {
      "type": "array",
      "minItems": 1,
      "maxItems": 5,
      "items": {
        "type": "string"
      },
      "description": "Top contributing factor names"
    },
    "exemplar_refs": {
      "type": "array",
      "maxItems": 5,
      "items": {
        "type": "string",
        "format": "uuid"
      },
      "description": "Top 5 exemplar document IDs"
    },
    "artifact_ref": {
      "type": "string",
      "pattern": "^artifact://",
      "description": "Artifact URI reference"
    },
    "trace_ref": {
      "type": "string",
      "pattern": "^trace://",
      "description": "Trace URI reference"
    },
    "checkpoint_ref": {
      "type": "string",
      "pattern": "^checkpoint://",
      "description": "Checkpoint for resume"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "Enqueue timestamp"
    },
    "assigned_to": {
      "type": "string",
      "description": "Assigned reviewer"
    },
    "taken_at": {
      "type": "string",
      "format": "date-time",
      "description": "Take timestamp"
    },
    "sla_deadline": {
      "type": "string",
      "format": "date-time",
      "description": "SLA decision deadline"
    },
    "sla_ack_deadline": {
      "type": "string",
      "format": "date-time",
      "description": "SLA ACK deadline"
    },
    "resolved_at": {
      "type": "string",
      "format": "date-time",
      "description": "Resolution timestamp"
    },
    "resolution": {
      "$ref": "#/definitions/Resolution"
    }
  },
  "additionalProperties": false,
  "definitions": {
    "Resolution": {
      "type": "object",
      "required": ["decision", "reviewer", "comment"],
      "properties": {
        "decision": {
          "type": "string",
          "enum": ["approve", "reject", "recalibrate", "request_artifact_correction", "request_process_correction", "add_judgment_note"],
          "description": "Review decision"
        },
        "reviewer": {
          "type": "string",
          "description": "Reviewer identifier"
        },
        "comment": {
          "type": "string",
          "maxLength": 1000,
          "description": "Review comment"
        },
        "correction": {
          "type": "object",
          "description": "Correction details (if applicable)"
        }
      },
      "additionalProperties": false
    }
  }
}
```

### 6.2 Severity and SLA

| Severity | ACK Deadline | Decision Deadline | Example Conditions |
|---|---|---|---|
| `critical` | 15 minutes | 60 minutes | Hard fail, secret found, prod_write + taboo |
| `high` | 60 minutes | 240 minutes | Drift/block, judge conflict, high privilege |
| `medium` | Same business day | Next business day | Warn ongoing, cost spike |
| `low` | N/A | Backlog | Learning notes, minor reviewer notes |

### 6.3 Example Instance

```json
{
  "schema_version": "1.0.0",
  "review_id": "bb0e8400-e29b-41d4-a716-446655440006",
  "decision_id": "770e8400-e29b-41d4-a716-446655440002",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "state": "hold",
  "composite_score": 0.72,
  "severity": "high",
  "top_factors": ["taboo_proximity", "uncertainty_score"],
  "exemplar_refs": ["taboo-001", "accepted-023"],
  "artifact_ref": "artifact://660e8400...",
  "trace_ref": "trace://550e8400...",
  "checkpoint_ref": "checkpoint://550e8400/cp-001",
  "created_at": "2026-04-26T10:30:00Z",
  "assigned_to": null,
  "taken_at": null,
  "sla_deadline": "2026-04-26T14:30:00Z",
  "sla_ack_deadline": "2026-04-26T11:30:00Z",
  "resolved_at": null,
  "resolution": null
}
```

---

## 7. Review Action

Reviewer action/resolution for a review item.

### 7.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://agent-gatefield.example/schemas/review-action-v1.0.0.json",
  "title": "ReviewAction",
  "description": "Reviewer action on a review item",
  "type": "object",
  "required": [
    "schema_version",
    "action_id",
    "review_id",
    "decision_id",
    "reviewer",
    "action_type",
    "created_at"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "1.0.0",
      "description": "Schema version"
    },
    "action_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique action identifier"
    },
    "review_id": {
      "type": "string",
      "format": "uuid",
      "description": "Review item identifier"
    },
    "decision_id": {
      "type": "string",
      "format": "uuid",
      "description": "Decision identifier"
    },
    "run_id": {
      "type": "string",
      "format": "uuid",
      "description": "Run identifier"
    },
    "reviewer": {
      "type": "string",
      "description": "Reviewer identifier"
    },
    "action_type": {
      "type": "string",
      "enum": [
        "approve",
        "reject",
        "recalibrate",
        "request_artifact_correction",
        "request_process_correction",
        "request_prompt_correction",
        "add_judgment_note"
      ],
      "description": "Action type"
    },
    "comment": {
      "type": "string",
      "maxLength": 1000,
      "description": "Review comment (redacted)"
    },
    "correction": {
      "$ref": "#/definitions/CorrectionDetails"
    },
    "calibration_change": {
      "$ref": "#/definitions/CalibrationChange"
    },
    "judgment_note": {
      "$ref": "#/definitions/JudgmentNote"
    },
    "previous_decision": {
      "type": "string",
      "enum": ["pass", "warn", "hold", "block"],
      "description": "Decision before action"
    },
    "new_decision": {
      "type": "string",
      "enum": ["pass", "warn", "hold", "block"],
      "description": "Decision after action"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "Action timestamp"
    },
    "trace_id": {
      "type": "string",
      "pattern": "^[a-f0-9]{32}$",
      "description": "OTel trace ID"
    }
  },
  "additionalProperties": false,
  "definitions": {
    "CorrectionDetails": {
      "type": "object",
      "required": ["correction_type", "target"],
      "properties": {
        "correction_type": {
          "type": "string",
          "enum": ["artifact", "process", "prompt"],
          "description": "Correction type"
        },
        "target": {
          "type": "string",
          "description": "Correction target"
        },
        "details": {
          "type": "object",
          "description": "Specific correction instructions"
        },
        "priority": {
          "type": "string",
          "enum": ["low", "medium", "high"],
          "description": "Correction priority"
        }
      },
      "additionalProperties": false
    },
    "CalibrationChange": {
      "type": "object",
      "required": ["axis", "old_threshold", "new_threshold"],
      "properties": {
        "axis": {
          "type": "string",
          "description": "Affected axis"
        },
        "old_threshold": {
          "type": "number",
          "description": "Previous threshold"
        },
        "new_threshold": {
          "type": "number",
          "description": "New threshold"
        },
        "reason": {
          "type": "string",
          "description": "Change reason"
        }
      },
      "additionalProperties": false
    },
    "JudgmentNote": {
      "type": "object",
      "required": ["text"],
      "properties": {
        "text": {
          "type": "string",
          "maxLength": 500,
          "description": "Note text"
        },
        "promote_to_kb": {
          "type": "boolean",
          "description": "Whether to promote to KB",
          "default": false
        }
      },
      "additionalProperties": false
    }
  }
}
```

### 7.2 Action Types and Effects

| Action Type | Decision Change | Post-Action |
|---|---|---|
| `approve` | hold → pass | Resume from checkpoint |
| `reject` | hold → block | Create correction action |
| `recalibrate` | No change | Update calibration profile |
| `request_artifact_correction` | hold → warn | Trigger artifact correction |
| `request_process_correction` | hold → warn | Trigger process correction |
| `request_prompt_correction` | hold → warn | Trigger prompt correction |
| `add_judgment_note` | No change | Promote to judgment_log (optional) |

### 7.3 Example Instance

```json
{
  "schema_version": "1.0.0",
  "action_id": "cc0e8400-e29b-41d4-a716-446655440007",
  "review_id": "bb0e8400-e29b-41d4-a716-446655440006",
  "decision_id": "770e8400-e29b-41d4-a716-446655440002",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "reviewer": "john.doe",
  "action_type": "approve",
  "comment": "Reviewed SQL pattern, input is validated via prepared statement in parent module.",
  "previous_decision": "hold",
  "new_decision": "pass",
  "created_at": "2026-04-26T11:00:00Z",
  "trace_id": "a1b2c3d4e5f6789012345678901234ab"
}
```

---

## 8. Audit Event

OTel-compatible audit event for compliance and traceability (AGF-REQ-009).

### 8.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://agent-gatefield.example/schemas/audit-event-v1.0.0.json",
  "title": "AuditEvent",
  "description": "OTel-compatible audit event",
  "type": "object",
  "required": [
    "schema_version",
    "event_id",
    "trace_id",
    "span_id",
    "run_id",
    "event_type",
    "actor",
    "payload_hash",
    "retention_class",
    "created_at"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "1.0.0",
      "description": "Schema version"
    },
    "event_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique event identifier"
    },
    "trace_id": {
      "type": "string",
      "pattern": "^[a-f0-9]{32}$",
      "description": "OTel trace ID (32 hex chars)"
    },
    "span_id": {
      "type": "string",
      "pattern": "^[a-f0-9]{16}$",
      "description": "OTel span ID (16 hex chars)"
    },
    "run_id": {
      "type": "string",
      "format": "uuid",
      "description": "Run identifier"
    },
    "event_type": {
      "type": "string",
      "enum": [
        "gate_decision",
        "human_review",
        "correction",
        "static_gate_result",
        "run_lifecycle",
        "threshold_change",
        "policy_change",
        "kb_update"
      ],
      "description": "Audit event type"
    },
    "actor": {
      "type": "string",
      "enum": ["agent", "tool", "reviewer", "system", "admin"],
      "description": "Event actor"
    },
    "payload_hash": {
      "type": "string",
      "pattern": "^sha256:[a-f0-9]{64}$",
      "description": "Payload content hash"
    },
    "payload_ref": {
      "type": "string",
      "pattern": "^blob://",
      "description": "Blob reference (if stored)"
    },
    "payload": {
      "type": "object",
      "description": "Inline payload (redacted)"
    },
    "retention_class": {
      "type": "string",
      "enum": ["audit", "ops", "pii-sensitive", "restricted"],
      "description": "Retention policy class"
    },
    "data_classification": {
      "type": "string",
      "enum": ["public", "internal", "confidential", "pii-sensitive", "restricted"],
      "description": "Data classification"
    },
    "threshold_version": {
      "type": "string",
      "description": "Threshold version (for gate_decision)"
    },
    "policy_version": {
      "type": "string",
      "description": "Policy version"
    },
    "action_type": {
      "type": "string",
      "description": "Action type (for gate_decision, correction)"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "Event timestamp"
    },
    "expires_at": {
      "type": "string",
      "format": "date-time",
      "description": "Expiration timestamp (based on retention)"
    }
  },
  "additionalProperties": false
}
```

### 8.2 OTel Mapping

| Audit Field | OTel Attribute | OTel Log Record Field |
|---|---|---|
| `trace_id` | `traceId` | `traceId` |
| `span_id` | `spanId` | `spanId` |
| `run_id` | `run_id` | `attributes.run_id` |
| `event_type` | `event_type` | `attributes.event_type` |
| `actor` | `actor` | `attributes.actor` |
| `payload_hash` | `payload_hash` | `attributes.payload_hash` |
| `retention_class` | `retention_class` | `attributes.retention_class` |
| `created_at` | - | `timeUnixNano` |

### 8.3 Retention Classes

| Class | Duration | Content Restrictions |
|---|---|---|
| `audit` | 365 days | Full decision details, no raw prompts |
| `ops` | 90 days | Operational metrics, redacted |
| `pii-sensitive` | 30 days | Redacted only, hash references |
| `restricted` | 0 days (no storage) | Hash only, no payload |

### 8.4 Example Instance

```json
{
  "schema_version": "1.0.0",
  "event_id": "dd0e8400-e29b-41d4-a716-446655440008",
  "trace_id": "a1b2c3d4e5f6789012345678901234ab",
  "span_id": "1234567890abcdef",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "gate_decision",
  "actor": "system",
  "payload_hash": "sha256:decision-packet-hash",
  "payload_ref": "blob://decision-770e8400",
  "payload": {
    "decision": "hold",
    "composite_score": 0.72,
    "top_factors": ["taboo_proximity"]
  },
  "retention_class": "audit",
  "data_classification": "internal",
  "threshold_version": "sha256:threshold-v1",
  "policy_version": "gate-policy-v1",
  "action_type": "hold_for_review",
  "created_at": "2026-04-26T10:30:00Z",
  "expires_at": "2027-04-26T10:30:00Z"
}
```

---

## 9. Calibration Profile

Threshold and weight configuration for a scope (team/repo/service).

### 9.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://agent-gatefield.example/schemas/calibration-profile-v1.0.0.json",
  "title": "CalibrationProfile",
  "description": "Threshold and weight configuration",
  "type": "object",
  "required": [
    "schema_version",
    "profile_id",
    "scope",
    "weights",
    "thresholds",
    "created_at",
    "updated_at"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "1.0.0",
      "description": "Schema version"
    },
    "profile_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique profile identifier"
    },
    "scope": {
      "type": "string",
      "description": "Profile scope (repo/service/team)"
    },
    "weights": {
      "type": "object",
      "required": [],
      "properties": {
        "constitution_alignment": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "default": 0.20
        },
        "taboo_proximity": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "default": 0.30
        },
        "accept_similarity": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "default": 0.10
        },
        "reject_similarity": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "default": 0.15
        },
        "drift": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "default": 0.10
        },
        "anomaly": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "default": 0.10
        },
        "uncertainty": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "default": 0.05
        }
      },
      "additionalProperties": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0
      },
      "description": "Scorer weights (must sum to 1.0)"
    },
    "thresholds": {
      "type": "object",
      "required": [],
      "properties": {
        "taboo_warn": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "default": 0.80,
          "description": "Taboo proximity warn threshold"
        },
        "taboo_block": {
          "type": "number",
          "minimum": 0.0,
          "maximum": 1.0,
          "default": 0.88,
          "description": "Taboo proximity block threshold"
        },
        "negative_similarity_warn": {
          "type": "number",
          "default": 0.75
        },
        "negative_similarity_block": {
          "type": "number",
          "default": 0.85
        },
        "drift_warn": {
          "type": "number",
          "default": 0.15
        },
        "drift_block": {
          "type": "number",
          "default": 0.25
        },
        "anomaly_warn_percentile": {
          "type": "integer",
          "minimum": 90,
          "maximum": 99,
          "default": 95,
          "description": "Anomaly warn percentile"
        },
        "anomaly_block_percentile": {
          "type": "integer",
          "minimum": 95,
          "maximum": 99,
          "default": 99,
          "description": "Anomaly block percentile"
        },
        "judge_std_warn": {
          "type": "number",
          "default": 0.15,
          "description": "Judge disagreement warn threshold"
        },
        "judge_std_block": {
          "type": "number",
          "default": 0.25,
          "description": "Judge disagreement block threshold"
        },
        "tool_failure_rate_warn": {
          "type": "number",
          "default": 0.10
        },
        "tool_failure_rate_block": {
          "type": "number",
          "default": 0.25
        }
      },
      "additionalProperties": {
        "type": "number"
      },
      "description": "Decision thresholds"
    },
    "hard_overrides": {
      "type": "object",
      "required": [],
      "properties": {
        "block_if_secret_found": {
          "type": "boolean",
          "default": true
        },
        "block_if_prod_write_and_taboo_warn": {
          "type": "boolean",
          "default": true
        },
        "hold_if_high_privilege_and_uncertain": {
          "type": "boolean",
          "default": true
        }
      },
      "additionalProperties": {
        "type": "boolean"
      },
      "description": "Hard override rules"
    },
    "detector_ref": {
      "type": "string",
      "description": "Anomaly detector reference"
    },
    "calibration_history": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/CalibrationEvent"
      },
      "description": "Calibration change history"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "Creation timestamp"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "description": "Last update timestamp"
    },
    "updated_by": {
      "type": "string",
      "description": "Last updater"
    },
    "version": {
      "type": "string",
      "description": "Profile version"
    }
  },
  "additionalProperties": false,
  "definitions": {
    "CalibrationEvent": {
      "type": "object",
      "required": ["timestamp", "change_type", "old_value", "new_value", "reason"],
      "properties": {
        "timestamp": {
          "type": "string",
          "format": "date-time"
        },
        "change_type": {
          "type": "string",
          "enum": ["threshold_adjustment", "weight_adjustment", "override_change"]
        },
        "field": {
          "type": "string"
        },
        "old_value": {
          "type": ["number", "boolean"]
        },
        "new_value": {
          "type": ["number", "boolean"]
        },
        "reason": {
          "type": "string"
        },
        "reviewer": {
          "type": "string"
        }
      },
      "additionalProperties": false
    }
  }
}
```

### 9.2 Threshold Calibration Sources

| Threshold | Calibration Source | Method |
|---|---|---|
| `taboo_warn` | Accepted distribution P95 | Offline calibration |
| `taboo_block` | Accepted distribution P99 | Offline calibration |
| `anomaly_warn_percentile` | Contamination estimate | Isolation Forest |
| `anomaly_block_percentile` | Contamination estimate | Isolation Forest |
| `judge_std_warn` | Evaluator disagreement distribution | Offline eval |
| `drift_warn` | EWMA accepted baseline | Online monitoring |

### 9.3 Example Instance

```json
{
  "schema_version": "1.0.0",
  "profile_id": "ee0e8400-e29b-41d4-a716-446655440009",
  "scope": "service-a",
  "weights": {
    "constitution_alignment": 0.20,
    "taboo_proximity": 0.30,
    "accept_similarity": 0.10,
    "reject_similarity": 0.15,
    "drift": 0.10,
    "anomaly": 0.10,
    "uncertainty": 0.05
  },
  "thresholds": {
    "taboo_warn": 0.80,
    "taboo_block": 0.88,
    "negative_similarity_warn": 0.75,
    "negative_similarity_block": 0.85,
    "drift_warn": 0.15,
    "drift_block": 0.25,
    "anomaly_warn_percentile": 95,
    "anomaly_block_percentile": 99,
    "judge_std_warn": 0.15,
    "judge_std_block": 0.25,
    "tool_failure_rate_warn": 0.10,
    "tool_failure_rate_block": 0.25
  },
  "hard_overrides": {
    "block_if_secret_found": true,
    "block_if_prod_write_and_taboo_warn": true,
    "hold_if_high_privilege_and_uncertain": true
  },
  "detector_ref": "isolation-forest-v1",
  "calibration_history": [
    {
      "timestamp": "2026-03-01T00:00:00Z",
      "change_type": "threshold_adjustment",
      "field": "taboo_warn",
      "old_value": 0.75,
      "new_value": 0.80,
      "reason": "Adjusted based on shadow mode observations",
      "reviewer": "security-lead"
    }
  ],
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-03-01T00:00:00Z",
  "updated_by": "security-lead",
  "version": "v2"
}
```

---

## 10. Config YAML Schema

Complete configuration schema for gate-config.yaml.

### 10.1 YAML Schema Structure

```yaml
# gate-config.yaml - Complete schema
$schema: https://agent-gatefield.example/schemas/gate-config-v1.0.0.json

# Project metadata
project: string (required)              # Project/service identifier
environment: string (required)          # local|ci|staging|production_shadow|production_enforce

# Harness integration
harness:
  implementation: string (required)     # python-adapter|openai-sdk|claude-code
  trace_backend: string (default: otel) # otel|custom
  checkpointing: boolean (default: true) # Pause/resume support

# Static gates configuration
static_gates:
  lint:
    enabled: boolean (default: true)
    severity: string (default: high)    # high|medium|low
    engine: string (optional)           # flake8|eslint|custom
  typecheck:
    enabled: boolean (default: true)
    severity: string (default: high)
    engine: string (optional)           # mypy|tsc|custom
  tests:
    enabled: boolean (default: true)
    min_pass_rate: number (default: 1.0, range: 0.0-1.0)
    min_coverage: number (optional)
  sast:
    enabled: boolean (default: true)
    engine: string (default: semgrep)   # semgrep|codeql|custom
    rulesets: array (optional)          # List of ruleset names
    severity_threshold: string (default: high)
  codeql:
    enabled: boolean (default: true)
    queries: array (optional)
  secret_scan:
    enabled: boolean (default: true)
    engine: string (default: trivy)
  license_scan:
    enabled: boolean (default: true)
    engine: string (default: trivy)
    forbidden_licenses: array (optional)
    unknown_license_policy: string (default: review)
  tool_policy:
    enabled: boolean (default: true)
    mode: string (default: deny_on_match) # deny_on_match|warn_on_match
    deny_patterns: array (required)      # Regex patterns for dangerous tools
    hold_patterns: array (optional)      # Patterns requiring review
    allowed_tools: array (optional)      # Whitelisted tools

# State space gate configuration
state_space_gate:
  enabled: boolean (default: true)
  
  semantic_embedding:
    provider: string (default: local)
    model: string (default: local-hash-embedding-v1)
    dimensions: integer (default: 1536, range: 256-3072)
    api_key_ref: string (optional)       # Required only for external providers
    
  axes:
    constitution: boolean (default: true)
    taboo: boolean (default: true)
    accepted_examples: boolean (default: true)
    rejected_examples: boolean (default: true)
    judgment_logs: boolean (default: true)
    uncertainty: boolean (default: true)
    
  vector_store:
    backend: string (default: pgvector)  # pgvector|milvus|custom
    connection_string: string (optional) # DB connection string
    index: string (default: hnsw)        # hnsw|ivfflat
    distance: string (default: cosine)   # cosine|l2|inner_product
    list_size: integer (optional)        # HNSW/IVF parameter
    probes: integer (optional)           # Search probes
    
  scorers:
    constitution_alignment:
      weight: number (default: 0.20, range: 0.0-1.0)
    taboo_proximity:
      weight: number (default: 0.30)
    accept_similarity:
      weight: number (default: 0.10)
    reject_similarity:
      weight: number (default: 0.15)
    drift:
      weight: number (default: 0.10)
    anomaly:
      weight: number (default: 0.10)
    uncertainty:
      weight: number (default: 0.05)
    
  thresholds:
    taboo_warn: number (default: 0.80, range: 0.0-1.0)
    taboo_block: number (default: 0.88)
    anomaly_warn_percentile: integer (default: 95, range: 90-99)
    anomaly_block_percentile: integer (default: 99)
    judge_std_warn: number (default: 0.15)
    judge_std_block: number (default: 0.25)
    
  hard_overrides:
    block_if_secret_found: boolean (default: true)
    block_if_prod_write_and_taboo_warn: boolean (default: true)
    hold_if_high_privilege_and_uncertain: boolean (default: true)

# Action configuration
actions:
  artifact_correction: boolean (default: true)
  process_correction: boolean (default: true)
  prompt_correction: boolean (default: true)
  max_self_correction_loops: integer (default: 2, range: 0-5)

# Human review configuration
human_review:
  queue_backend: string (default: annotation_queue) # annotation_queue|database
  dashboard: string (default: required)             # required|optional|disabled
  pairwise_mode: boolean (default: false)           # Enable pairwise queue
  
  sla:
    critical_ack_minutes: integer (default: 15)
    critical_decision_minutes: integer (default: 60)
    high_ack_minutes: integer (default: 60)
    high_decision_minutes: integer (default: 240)
    medium_ack_hours: integer (optional)
    medium_decision_hours: integer (optional)
    
  reviewers:
    min_count: integer (default: 2)
    security_approver_required: boolean (default: true)
    ops_owner_required: boolean (default: true)
    
  escalation:
    enabled: boolean (default: true)
    timeout_action: string (default: block)  # block|warn
    notify_on_timeout: boolean (default: true)

# Data protection configuration
data_protection:
  classification:
    levels: array (default: [public, internal, confidential, pii-sensitive, restricted])
    default_if_unknown: string (default: restricted)
    
  raw_prompt_storage: boolean (default: false)
  raw_tool_payload_storage: boolean (default: false)
  
  redaction:
    required_before_persist: boolean (default: true)
    version: string (default: redaction-policy-v1)
    patterns: array (optional)           # Additional redaction patterns
    
  external_managed_service:
    allowed: boolean (default: false)
    required_checks: array (default: [data_residency, retention, purge_api, audit_export])

# Audit configuration
audit:
  enabled: boolean (default: true)
  
  retention_days:
    audit: integer (default: 365)
    traces: integer (default: 180)
    redacted_artifacts: integer (default: 90)
    raw_prompts: integer (default: 0)    # Forbidden
    ephemeral_vectors: integer (default: 30)
    
  export:
    formats: array (default: [otlp, jsonl])
    siem_integration: string (optional)
    
  completeness_check:
    enabled: boolean (default: true)
    required_fields: array (default: [trace_id, threshold_version, action_type])

# Cost guardrails
cost_guardrails:
  monthly_budget_usd: number (default: 500)
  warn_threshold_percent: number (default: 80)
  hold_threshold_percent: number (default: 100)
  
  components:
    embeddings: boolean (default: true)
    vector_storage: boolean (default: true)
    evaluators: boolean (default: true)
    tool_calls: boolean (default: true)
    audit_storage: boolean (default: true)

# KPI configuration
kpi:
  dashboard_freshness_seconds: integer (default: 60)
  review_writeback_seconds: integer (default: 5)
  
  targets:
    review_load_reduction_percent: number (default: 30)
    critical_miss_rate: number (default: 0)
    high_miss_rate_percent: number (default: 5)
    false_escalation_rate_percent: number (default: 15)
    explanation_usefulness_percent: number (default: 80)
    replay_reproducibility_percent: number (default: 99)

# Enforce mode configuration
enforce_mode:
  shadow_duration_days: integer (default: 14)
  warn_hold_duration_days: integer (default: 7)
  
  readiness_gates:
    technical_acceptance: boolean (required)
    operational_kpi: boolean (required)
    formal_initial_decisions_evidence: boolean (required)
    security_approval: boolean (required)
```

### 10.2 Complete Example Configuration

```yaml
project: service-a
environment: staging

harness:
  implementation: python-adapter
  trace_backend: otel
  checkpointing: true

static_gates:
  lint:
    enabled: true
    severity: high
  typecheck:
    enabled: true
    severity: high
  tests:
    enabled: true
    min_pass_rate: 1.0
  sast:
    enabled: true
    engine: semgrep
    rulesets:
      - defaults
      - custom/org-security
  codeql:
    enabled: true
  secret_scan:
    enabled: true
    engine: trivy
  license_scan:
    enabled: true
    engine: trivy
  tool_policy:
    enabled: true
    mode: deny_on_match
    deny_patterns:
      - "rm -rf /"
      - "DROP DATABASE"
      - "kubectl delete --all"

state_space_gate:
  enabled: true
  semantic_embedding:
    provider: local
    model: local-hash-embedding-v1
    dimensions: 1536
  axes:
    constitution: true
    taboo: true
    accepted_examples: true
    rejected_examples: true
    judgment_logs: true
    uncertainty: true
  vector_store:
    backend: pgvector
    index: hnsw
    distance: cosine
  scorers:
    constitution_alignment:
      weight: 0.20
    taboo_proximity:
      weight: 0.30
    accept_similarity:
      weight: 0.10
    reject_similarity:
      weight: 0.15
    drift:
      weight: 0.10
    anomaly:
      weight: 0.10
    uncertainty:
      weight: 0.05
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

actions:
  artifact_correction: true
  process_correction: true
  prompt_correction: true
  max_self_correction_loops: 2

human_review:
  queue_backend: annotation_queue
  dashboard: required
  sla:
    critical_ack_minutes: 15
    critical_decision_minutes: 60
    high_ack_minutes: 60
    high_decision_minutes: 240

data_protection:
  classification:
    levels:
      - public
      - internal
      - confidential
      - pii-sensitive
      - restricted
    default_if_unknown: restricted
  raw_prompt_storage: false
  raw_tool_payload_storage: false
  redaction:
    required_before_persist: true
    version: redaction-policy-v1
  external_managed_service:
    allowed: false
    required_checks:
      - data_residency
      - retention
      - purge_api
      - audit_export

audit:
  enabled: true
  retention_days:
    audit: 365
    traces: 180
    redacted_artifacts: 90
    raw_prompts: 0
  export:
    - otlp
    - jsonl

cost_guardrails:
  monthly_budget_usd: 500
  warn_threshold_percent: 80
  hold_threshold_percent: 100

kpi:
  dashboard_freshness_seconds: 60
  review_writeback_seconds: 5
  targets:
    review_load_reduction_percent: 30
    critical_miss_rate: 0
    high_miss_rate_percent: 5
    false_escalation_rate_percent: 15
    explanation_usefulness_percent: 80
    replay_reproducibility_percent: 99

enforce_mode:
  shadow_duration_days: 14
  warn_hold_duration_days: 7
  readiness_gates:
    technical_acceptance: true
    operational_kpi: true
    formal_initial_decisions_evidence: true
    security_approval: true
```

### 10.3 Configuration Field Constraints

| Field | Type | Default | Constraints | Required |
|---|---|---|---|---|
| `project` | string | - | Non-empty | Yes |
| `environment` | string | - | Enum values | Yes |
| `harness.implementation` | string | - | python-adapter, openai-sdk, claude-code | Yes |
| `state_space_gate.scorers.*.weight` | number | 0.05-0.30 | 0.0-1.0, sum=1.0 | No |
| `state_space_gate.thresholds.taboo_*` | number | 0.80/0.88 | 0.0-1.0, warn < block | No |
| `human_review.sla.*_minutes` | integer | 15-240 | Positive | No |
| `audit.retention_days.audit` | integer | 365 | Positive | No |
| `cost_guardrails.monthly_budget_usd` | number | 500 | Positive | No |

---

## Appendix A: Data Classification Levels

| Level | Description | Storage Policy | Embedding Policy |
|---|---|---|---|
| `public` | Publicly accessible data | Full storage allowed | Full embedding allowed |
| `internal` | Internal organization data | Full storage allowed | Full embedding allowed |
| `confidential` | Sensitive business data | Redacted storage | Hash-only embedding |
| `pii-sensitive` | Contains PII | Redacted only | Hash-only, no embedding |
| `restricted` | Highly sensitive/unknown | No storage | No embedding, hash only |

---

## Appendix B: Retention Policy Summary

| Data Type | Retention Class | Duration | Notes |
|---|---|---|---|
| Decision/audit log | `audit` | 365 days | Required for compliance |
| Trace metadata | `ops` | 180 days | Operational use only |
| Raw prompt | - | 0 days | Storage forbidden |
| Redacted artifact body | `ops` | 90 days | After redaction |
| Human correction log | `audit` | 365 days | Required for reproducibility |
| Ephemeral intermediate vectors | `ephemeral` | 30 days | Temporary state |
| Golden/rejected datasets | `audit` | Until explicit delete | Version locked |

---

## Appendix C: Acceptance Criteria Mapping

| Data Type | Requirement | Acceptance Criteria |
|---|---|---|
| State Vector | AGF-REQ-001 | 95%+ coverage for target runs |
| Trace Event | AGF-REQ-009 | 100% trace_id coverage |
| Decision Packet | AGF-REQ-003 | Top 5 exemplars + top 3 factors required |
| Judgment Document | AGF-REQ-007 | Dataset version locked |
| Review Item | AGF-REQ-004 | SLA deadlines required for critical/high |
| Audit Event | AGF-REQ-009 | OTel compatible, 100% threshold_version |
| Calibration Profile | AGF-REQ-005 | Correction replayable to profile |

---

## Appendix D: JSON Schema Validation

All data types must be validated against their JSON schemas before storage:

1. **Schema version check**: Validate `schema_version` matches expected
2. **Required field check**: All required fields must be present
3. **Type check**: Field types must match schema definitions
4. **Enum check**: Enum values must be from defined set
5. **Range check**: Numeric values must be within constraints
6. **Format check**: UUID, datetime, hash formats must be valid

Validation errors result in `InvalidDataError` with field-level detail.

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | 2026-04-26 | Initial specification from requirements.md frozen state |
