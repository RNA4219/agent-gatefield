# Test Specification

This document specifies the complete testing strategy for the agent-gatefield system, mapping each AGF-REQ ID to specific test cases across multiple test layers. All tests must achieve specified coverage targets and pass acceptance criteria before production block enforce.

## Document Version

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | 2026-04-26 | Initial specification from requirements.md frozen state |

---

## 1. Test Layers Overview

The agent-gatefield system employs eight distinct test layers, each serving a specific validation purpose.

### 1.1 Layer Definitions

| Layer | Purpose | Execution Frequency | Environment |
|---|---|---|---|
| **Unit** | Individual component correctness | Every commit | Local / CI |
| **Contract** | Interface/schema compatibility | Every PR | CI |
| **Integration** | End-to-end flow validation | Every merge | CI / Staging |
| **Replay** | Reproducibility verification | Threshold change, weekly | CI / Staging |
| **Offline Eval** | Model/gate quality metrics | Dataset update, release | CI |
| **Online Shadow** | Production behavior observation | Continuous | Production Shadow |
| **Security** | OWASP LLM Top 10 validation | Every release, periodic audit | CI / Staging |
| **Data Protection** | PII/retention/compliance checks | Every release, periodic audit | CI / Staging |

### 1.2 Layer Dependencies

```mermaid
flowchart TD
    A[Unit Tests] --> B[Contract Tests]
    B --> C[Integration Tests]
    C --> D[Replay Tests]
    D --> E[Offline Eval]
    E --> F[Online Shadow]
    F --> G[Security Tests]
    F --> H[Data Protection Tests]
    
    E --> I[Acceptance Gate]
    G --> I
    H --> I
    I --> J[Block Enforce Enabled]
```

---

## 2. Test Matrix

### 2.1 Component vs Test Layer Matrix

| Component | Unit | Contract | Integration | Replay | Offline Eval | Online Shadow | Security | Data Protection |
|---|---|---|---|---|---|---|---|---|
| Trace Adapter | Required | Required | Required | - | - | Required | Required | Required |
| State Encoder | Required | Required | Required | Required | Required | Required | - | Required |
| Static Gate Adapters | Required | Required | Required | - | Required | Required | Required | Required |
| Scorers | Required | - | Required | Required | Required | Required | - | - |
| Composite Decision Engine | Required | - | Required | Required | Required | Required | Required | - |
| Hard Override Engine | Required | - | Required | Required | Required | Required | Required | Required |
| Self-Correction Loop | Required | - | Required | - | - | Required | - | - |
| Review Queue | Required | Required | Required | Required | - | Required | Required | Required |
| Judgment KB | Required | Required | Required | Required | Required | Required | Required | Required |
| Vector Store (pgvector) | Required | Required | Required | - | Required | Required | Required | Required |
| Audit Logger | Required | Required | Required | Required | - | Required | Required | Required |
| Dashboard API | Required | Required | Required | - | - | Required | - | Required |
| CLI Commands | Required | Required | Required | - | - | - | - | - |
| Redaction Pipeline | Required | Required | Required | - | - | - | Required | Required |
| Calibration Profile Manager | Required | Required | Required | Required | Required | - | - | Required |

### 2.2 Requirement vs Test Layer Mapping

| AGF-REQ ID | Unit | Contract | Integration | Replay | Offline Eval | Online Shadow | Security | Data Protection |
|---|---|---|---|---|---|---|---|---|
| AGF-REQ-001 | Required | Required | Required | Required | - | Required | Required | Required |
| AGF-REQ-002 | Required | Required | Required | Required | Required | Required | Required | Required |
| AGF-REQ-003 | Required | - | Required | Required | Required | Required | Required | - |
| AGF-REQ-004 | Required | - | Required | Required | - | Required | Required | - |
| AGF-REQ-005 | Required | Required | Required | Required | - | Required | - | Required |
| AGF-REQ-006 | Required | Required | Required | - | - | Required | Required | Required |
| AGF-REQ-007 | Required | Required | Required | Required | Required | - | - | Required |
| AGF-REQ-008 | - | - | Required | - | Required | Required | - | - |
| AGF-REQ-009 | Required | Required | Required | Required | - | Required | Required | Required |
| AGF-REQ-010 | Required | Required | Required | Required | Required | Required | Required | Required |

---

## 3. Unit Test Requirements

### 3.1 Coverage Targets

| Component | Target Coverage | Critical Paths | Notes |
|---|---|---|---|
| State Encoder | 90% | encode_state, validate_vector, embedding_ref | Must include all vector components |
| Scorers | 95% | Each scorer compute method | All 7 scorers required |
| Composite Decision Engine | 95% | determine_state, compute_composite | All state transitions |
| Hard Override Engine | 100% | All 5 override rules | Zero tolerance for override bugs |
| Self-Correction Loop | 90% | loop execution, loop exhaustion, persistent factor | Max 2 loops logic |
| Review Queue | 85% | enqueue, take, resolve, SLA timeout | All reviewer actions |
| Audit Logger | 90% | log_decision, log_review, OTel mapping | Required fields validation |
| Redaction Pipeline | 100% | All redaction patterns, classification | Zero tolerance for PII leaks |
| Calibration Profile Manager | 85% | load, update, threshold change, history | Reproducibility logic |

**Overall Unit Coverage Target: 90% minimum**

### 3.2 Testable Components and Unit Test Cases

#### 3.2.1 State Encoder (AGF-REQ-001)

| Test ID | Test Case | Input | Expected Output | Coverage |
|---|---|---|---|---|
| UT-ENC-001 | encode_state_vector produces valid schema | Sample run_id, artifact_id | Valid StateVector with all required fields | encode_state |
| UT-ENC-002 | semantic vector reference valid | Text content | vec:// reference with SHA256 hash | semantic embedding |
| UT-ENC-003 | rule_violation vector aggregation | Multiple static gate results | Aggregated counts per violation type | rule_violation |
| UT-ENC-004 | test_evidence vector computation | Test results | pass_rate, coverage_delta computed | test_evidence |
| UT-ENC-005 | risk vector determination | Context metadata | prod_write, pii_level determined | risk |
| UT-ENC-006 | historical_decision similarity | KB lookup results | accept_sim, reject_sim, taboo_max_sim | historical_decision |
| UT-ENC-007 | uncertainty vector computation | Model output, evaluator variance | judge_std, self_confidence computed | uncertainty |
| UT-ENC-008 | trajectory features computation | Step history | delta_semantic, tool_calls, ewma_drift | trajectory |
| UT-ENC-009 | schema_version enforcement | Any state vector | "1.0.0" schema version | schema version |
| UT-ENC-010 | intermediate flag handling | Mid-run state | intermediate=true, valid fields | intermediate |
| UT-ENC-011 | encoder_version tracking | Any encoding | encoder_version populated | version tracking |

#### 3.2.2 Scorers (AGF-REQ-003)

| Test ID | Test Case | Input | Expected Output | Coverage |
|---|---|---|---|---|
| UT-SCR-001 | constitution_alignment cosine calculation | Semantic vector, constitution centroid | 0.0-1.0 score | constitution_alignment |
| UT-SCR-002 | taboo_proximity max cosine | Semantic vector, taboo top-k | Max similarity to taboo docs | taboo_proximity |
| UT-SCR-003 | accept_similarity max cosine | Semantic vector, accepted top-k | Max similarity to accepted docs | accept_similarity |
| UT-SCR-004 | reject_similarity max cosine | Semantic vector, rejected top-k | Max similarity to rejected docs | reject_similarity |
| UT-SCR-005 | direction_score calculation | Current semantic, direction vector | Positive/negative direction | direction_score |
| UT-SCR-006 | drift_score EWMA calculation | Current, EWMA accepted | 1 - cosine(current, ewma) | drift_score |
| UT-SCR-007 | anomaly_score Isolation Forest | Trajectory features | Percentile score | anomaly_score |
| UT-SCR-008 | anomaly_score Mahalanobis | Multivariate state | Distance score | anomaly_score |
| UT-SCR-009 | uncertainty_score aggregation | Multiple uncertainty factors | Weighted aggregation | uncertainty_score |
| UT-SCR-010 | weight application | Raw score, weight | Weighted contribution | weight application |
| UT-SCR-011 | threshold comparison | Score, threshold | Exceeded/not exceeded flag | threshold comparison |

#### 3.2.3 Composite Decision Engine (AGF-REQ-004)

| Test ID | Test Case | Input | Expected Output | Coverage |
|---|---|---|---|---|
| UT-DEC-001 | compute_composite aggregation | All scorer results | Weighted sum 0.0-1.0 | composite computation |
| UT-DEC-002 | determine_state pass condition | Composite < 0.70, no thresholds exceeded | State: pass | pass determination |
| UT-DEC-003 | determine_state warn condition | Composite >= 0.70 | State: warn | warn determination |
| UT-DEC-004 | determine_state hold condition | Taboo >= warn threshold | State: hold | hold determination |
| UT-DEC-005 | determine_state block condition | Taboo >= block threshold | State: block | block determination |
| UT-DEC-006 | state priority ordering | Multiple threshold hits | Most conservative state | priority ordering |
| UT-DEC-007 | factors ranking | All scorer results | Top 3 factors sorted | factors ranking |
| UT-DEC-008 | exemplar selection | KB lookup results | Top 5 exemplar refs | exemplar selection |
| UT-DEC-009 | action_type determination | Final state | action_type: continue/hold/block | action selection |
| UT-DEC-010 | threshold_version inclusion | Any decision | threshold_version populated | reproducibility |

#### 3.2.4 Hard Override Engine (AGF-REQ-002, AGF-REQ-004)

| Test ID | Test Case | Input | Expected Output | Coverage |
|---|---|---|---|---|
| UT-HOV-001 | block_if_secret_found | rule_violation.secret > 0 | BLOCK, artifact_correction | HO01 |
| UT-HOV-002 | block_if_prod_write_and_taboo_warn | prod_write=1, taboo>=0.80 | BLOCK, process_correction | HO02 |
| UT-HOV-003 | hold_if_high_privilege_and_uncertain | high_privilege=1, judge_std>0.15 | HOLD, process_correction | HO03 |
| UT-HOV-004 | static_gate_sast_high | rule_violation.sast_high > 0 | BLOCK, artifact_correction | HO04 |
| UT-HOV-005 | tool_policy_deny | rule_violation.tool_policy_deny > 0 | BLOCK, process_correction | HO05 |
| UT-HOV-006 | override evaluation order | Multiple triggers | Correct priority order | priority |
| UT-HOV-007 | override bypass composite | Override triggered | No scorer execution | bypass |
| UT-HOV-008 | hard_override_reason field | Override triggered | Reason populated in decision | audit |

#### 3.2.5 Self-Correction Loop (AGF-REQ-004)

| Test ID | Test Case | Input | Expected Output | Coverage |
|---|---|---|---|---|
| UT-SCL-001 | self-correction initiation | WARN state, top_factors | Correction action generated | loop start |
| UT-SCL-002 | loop count tracking | Loop execution | self_correction_count incremented | loop tracking |
| UT-SCL-003 | loop exhaustion at max=2 | 2 failed corrections | Transition to HOLD | loop exhaustion |
| UT-SCL-004 | correction success | After correction, score < threshold | Transition to PASS | success |
| UT-SCL-005 | persistent factor tracking | Same top factor across runs | repeated_warn_count tracked | persistence |
| UT-SCL-006 | persistent factor escalation | Same factor 3 consecutive runs | Transition to HOLD | escalation |
| UT-SCL-007 | correction type selection | Top factor type | Correct correction_type | type selection |
| UT-SCL-008 | correction audit | Any correction | before_score, after_score logged | audit |

#### 3.2.6 Review Queue (AGF-REQ-004, AGF-REQ-005)

| Test ID | Test Case | Input | Expected Output | Coverage |
|---|---|---|---|---|
| UT-REV-001 | enqueue review item | HOLD decision | ReviewItem with SLA deadlines | enqueue |
| UT-REV-002 | severity assignment | Critical condition | severity: critical, 15min ACK | severity |
| UT-REV-003 | take review item | Reviewer request | assigned_to, taken_at populated | take |
| UT-REV-004 | approve resolution | approve action | State: pass, resume from checkpoint | approve |
| UT-REV-005 | reject resolution | reject action | State: block, correction created | reject |
| UT-REV-006 | request_correction resolution | request_correction action | State: warn, correction triggered | correction request |
| UT-REV-007 | recalibrate resolution | recalibrate action | Profile updated, re-evaluate | recalibrate |
| UT-REV-008 | SLA ACK timeout | Time exceeds deadline | BLOCK (fail closed) | SLA timeout |
| UT-REV-009 | SLA decision timeout | Time exceeds deadline | BLOCK (fail closed) | SLA timeout |
| UT-REV-010 | judgment_note promotion | add_judgment_note with promote | KB entry created | KB promotion |

#### 3.2.7 Audit Logger (AGF-REQ-009)

| Test ID | Test Case | Input | Expected Output | Coverage |
|---|---|---|---|---|
| UT-AUD-001 | log_decision trace_id | Any decision | trace_id populated (32 hex chars) | trace correlation |
| UT-AUD-002 | log_decision threshold_version | Any decision | threshold_version populated | reproducibility |
| UT-AUD-003 | log_decision action_type | Any decision | action_type populated | action tracking |
| UT-AUD-004 | log_review reviewer fields | Review action | reviewer_id, decision_time | review audit |
| UT-AUD-005 | retention_class assignment | Event classification | Correct retention_class | retention |
| UT-AUD-006 | OTel span_id format | Any event | 16 hex chars | OTel format |
| UT-AUD-007 | payload_hash format | Any payload | sha256:64-hex-chars | hash format |
| UT-AUD-008 | expires_at calculation | Event with retention | Correct expiration | expiration |

#### 3.2.8 Redaction Pipeline (AGF-REQ-006)

| Test ID | Test Case | Input | Expected Output | Coverage |
|---|---|---|---|---|
| UT-RED-001 | API key redaction | "api_key: sk-xxxxx" | api_key: [REDACTED] | secret redaction |
| UT-RED-002 | password redaction | "password: secretpass" | password: [REDACTED] | credential redaction |
| UT-RED-003 | email redaction | "user@example.com" | [EMAIL_REDACTED] | PII redaction |
| UT-RED-004 | phone redaction | "Phone: 123-456-7890" | [PHONE_REDACTED] | PII redaction |
| UT-RED-005 | URL redaction | "https://internal.com/api" | [URL_REDACTED] | URL redaction |
| UT-RED-006 | DB connection string redaction | "postgres://user:pass@host" | [DB_CONN_REDACTED] | DB redaction |
| UT-RED-007 | classification assignment | Unknown payload | data_classification: restricted | default classification |
| UT-RED-008 | redaction_status field | Any redacted payload | redaction_status: partial/full | status tracking |
| UT-RED-009 | content_hash_before/after | Redacted payload | Both hashes present | version tracking |
| UT-RED-010 | restricted payload handling | Restricted classification | No storage, hash only | restricted handling |

#### 3.2.9 Judgment KB (AGF-REQ-003)

| Test ID | Test Case | Input | Expected Output | Coverage |
|---|---|---|---|---|
| UT-KB-001 | insert document | JudgmentDocument | doc_id, embedding_ref created | insert |
| UT-KB-002 | append-only versioning | Update existing doc | New version, old marked valid_to | versioning |
| UT-KB-003 | logical deletion | Delete request | status: deprecated, not removed | logical delete |
| UT-KB-004 | axis_type filtering | Query by axis | Only matching axis docs | axis filtering |
| UT-KB-005 | scope filtering | Query by scope | Only matching scope docs | scope filtering |
| UT-KB-006 | embedding dual-write | Model change | Both old and new embeddings | dual-write |
| UT-KB-007 | content_hash deduplication | Duplicate content | Same content_hash, deduped | deduplication |

#### 3.2.10 Calibration Profile Manager (AGF-REQ-005)

| Test ID | Test Case | Input | Expected Output | Coverage |
|---|---|---|---|---|
| UT-CAL-001 | load profile | Scope request | Correct profile for scope | profile load |
| UT-CAL-002 | update threshold | Threshold change request | threshold updated, history logged | threshold update |
| UT-CAL-003 | update weight | Weight change request | weight updated, weights sum=1.0 | weight update |
| UT-CAL-004 | calibration history | Any change | CalibrationEvent logged | history tracking |
| UT-CAL-005 | version tracking | Profile update | version incremented | version tracking |
| UT-CAL-006 | threshold_version computation | Profile content | SHA256 hash | threshold_version |

---

## 4. Contract Tests

Contract tests validate schema compatibility and API contracts between components.

### 4.1 Schema Validation Tests

| Test ID | Schema | Validation Points | Requirement |
|---|---|---|---|
| CT-SCH-001 | StateVector | Required fields, type constraints, enum values | AGF-REQ-001 |
| CT-SCH-002 | TraceEvent | OTel trace_id/span_id format, event_type enum | AGF-REQ-009 |
| CT-SCH-003 | DecisionPacket | decision enum, factors array, exemplar_refs | AGF-REQ-003 |
| CT-SCH-004 | JudgmentDocument | axis_type enum, status enum, versioning | AGF-REQ-007 |
| CT-SCH-005 | StaticGateResult | gate_name enum, status enum, immutable | AGF-REQ-002 |
| CT-SCH-006 | ReviewItem | severity enum, SLA deadlines, resolution | AGF-REQ-004 |
| CT-SCH-007 | ReviewAction | action_type enum, previous/new decision | AGF-REQ-005 |
| CT-SCH-008 | AuditEvent | OTel mapping, retention_class enum | AGF-REQ-009 |
| CT-SCH-009 | CalibrationProfile | weights sum=1.0, threshold ranges | AGF-REQ-005 |
| CT-SCH-010 | gate-config.yaml | YAML schema validation, field constraints | AGF-REQ-010 |

### 4.2 API Contract Tests

| Test ID | API | Contract Points | Requirement |
|---|---|---|---|
| CT-API-001 | Harness Adapter API | Event types, trace_id, payload_ref format | AGF-REQ-001 |
| CT-API-002 | State Encoder API | Input: run_id/artifact, Output: StateVector | AGF-REQ-001 |
| CT-API-003 | Scorers API | Input: StateVector, Output: ScorerResults | AGF-REQ-003 |
| CT-API-004 | Decision Engine API | Input: Scorers/StateVector, Output: DecisionPacket | AGF-REQ-004 |
| CT-API-005 | Review Queue API | enqueue/take/resolve contracts | AGF-REQ-004 |
| CT-API-006 | KB Query API | axis_type filter, top-k retrieval, similarity | AGF-REQ-003 |
| CT-API-007 | Vector Store API | insert/query/delete, distance metric | AGF-REQ-003 |
| CT-API-008 | Audit Log API | log_decision/log_review, required fields | AGF-REQ-009 |
| CT-API-009 | Dashboard API | List/detail/compare endpoints | AGF-REQ-009 |
| CT-API-010 | CLI API | Exit codes, output format | AGF-REQ-010 |

### 4.3 Backward Compatibility Tests

| Test ID | Component | Compatibility Check | Requirement |
|---|---|---|---|
| CT-BC-001 | StateVector schema | v1.x accepts v1.0.0 instances | AGF-REQ-007 |
| CT-BC-002 | DecisionPacket schema | v1.x accepts v1.0.0 instances | AGF-REQ-007 |
| CT-BC-003 | Calibration Profile | Threshold changes preserve old values in history | AGF-REQ-005 |
| CT-BC-004 | Judgment KB | New embedding dims compatible with old queries | AGF-REQ-007 |

---

## 5. Integration Tests

Integration tests validate end-to-end flows across multiple components.

### 5.1 End-to-End Flow Tests

| Test ID | Flow | Components Involved | Expected Outcome | Requirement |
|---|---|---|---|---|
| IT-E2E-001 | Run lifecycle trace collection | Trace Adapter, Audit Logger | All events logged with trace_id | AGF-REQ-001 |
| IT-E2E-002 | Static gate hard fail flow | Static Gate Adapter, Hard Override, Decision Engine | BLOCK decision, audit logged | AGF-REQ-002 |
| IT-E2E-003 | State space gate evaluation | State Encoder, KB, Scorers, Decision Engine | DecisionPacket with factors/exemplars | AGF-REQ-003 |
| IT-E2E-004 | Self-correction loop flow | Decision Engine, Self-Correction, State Encoder | PASS after correction or HOLD after exhaustion | AGF-REQ-004 |
| IT-E2E-005 | Human review flow | Review Queue, Harness Pause/Resume, Decision Engine | Resume or BLOCK based on reviewer action | AGF-REQ-004 |
| IT-E2E-006 | Correction writeback flow | Review Action, Calibration Profile, Judgment KB | KB updated, profile history logged | AGF-REQ-005 |
| IT-E2E-007 | Data protection flow | Redaction Pipeline, Storage, Audit Logger | No raw payload stored, hashes only | AGF-REQ-006 |
| IT-E2E-008 | Replay evaluation flow | Replay Engine, Threshold/Policy Version, Decision Engine | Same decision as original | AGF-REQ-007 |
| IT-E2E-009 | Audit completeness flow | All components, Audit Logger | 100% decisions have trace_id/threshold_version | AGF-REQ-009 |

### 5.2 Harness Integration Tests

| Test ID | Test Case | Expected Behavior | Requirement |
|---|---|---|---|
| IT-HAR-001 | Run lifecycle events subscription | All events received, trace_id correlation | AGF-REQ-001 |
| IT-HAR-002 | Pause/resume with checkpoint | Run paused, checkpoint preserved, resume works | AGF-REQ-001 |
| IT-HAR-003 | Tool policy hook integration | Deny/hold/allow returned before tool execution | AGF-REQ-002 |
| IT-HAR-004 | Artifact snapshot retrieval | Hash, diff, step, commit available | AGF-REQ-001 |
| IT-HAR-005 | Static gate result ingest | Status, severity, evidence_ref ingested | AGF-REQ-002 |
| IT-HAR-006 | Trace correlation across events | trace_id/span_id consistent | AGF-REQ-009 |

### 5.3 Database Integration Tests

| Test ID | Test Case | Expected Behavior | Requirement |
|---|---|---|---|
| IT-DB-001 | State vector storage | Stored with all components, retrievable | AGF-REQ-001 |
| IT-DB-002 | Decision packet storage | Stored with threshold_version, retrievable | AGF-REQ-009 |
| IT-DB-003 | Judgment KB vector search | HNSW/cosine search returns top-k | AGF-REQ-003 |
| IT-DB-004 | Calibration profile versioning | History preserved, current version active | AGF-REQ-005 |
| IT-DB-005 | Audit event retention | Correct retention_class, expires_at | AGF-REQ-009 |
| IT-DB-006 | Purge by run_id | All related records deleted | AGF-REQ-006 |

---

## 6. Replay Tests

Replay tests verify reproducibility of past decisions with specific threshold/policy versions.

### 6.1 Replay Test Cases

| Test ID | Test Case | Replay Parameters | Expected Outcome | Requirement |
|---|---|---|---|---|
| RT-001 | Decision reproducibility | Same threshold_version, policy_version | Identical decision | AGF-REQ-007 |
| RT-002 | Threshold change comparison | Different threshold versions | Difference explained by threshold change | AGF-REQ-007 |
| RT-003 | Policy change comparison | Different policy versions | Difference explained by policy change | AGF-REQ-007 |
| RT-004 | Dataset version replay | Specific dataset version | KB docs from that version used | AGF-REQ-007 |
| RT-005 | Historical correction replay | Correction event, threshold at that time | Correction correctly applied | AGF-REQ-005 |
| RT-006 | Full run replay | Full run history, checkpoint | Complete decision sequence reproduced | AGF-REQ-007 |
| RT-007 | Cross-version state encoding | Old encoder_version | State vector compatible | AGF-REQ-007 |
| RT-008 | Embedding model version | Old embedding model version | Similarity computed with old vectors | AGF-REQ-007 |

### 6.2 Replay Coverage Target

| Metric | Target | Measurement Method |
|---|---|---|
| Replay reproducibility | 99%+ | Count matching decisions / total decisions |
| Threshold change explanation | 100% | All differences have threshold_version diff |
| Policy change explanation | 100% | All differences have policy_version diff |

---

## 7. Offline Evaluation Tests

Offline evaluation tests measure gate quality against curated datasets.

### 7.1 Dataset Requirements

| Dataset | Min Items | Labels | Purpose | Requirement |
|---|---|---|---|---|
| static_violation_suite.jsonl | 50 | gate_name, severity, expected_state | Hard fail reproducibility | AGF-REQ-002 |
| taboo_cases.jsonl | 100 | taboo_type, expected_state, rationale | Taboo recall | AGF-REQ-003 |
| accepted_examples.jsonl | 200 | accepted, quality_axis, reviewer | False escalation | AGF-REQ-003 |
| rejected_examples.jsonl | 100 | rejected, reason_code, expected_state | Accept/reject separation | AGF-REQ-003 |
| judgment_logs.jsonl | 100 | decision, correction_type, rationale | Explanation/recalibration | AGF-REQ-005 |
| drift_sequences.jsonl | 50 sequences | normal_step, drift_step, expected_state | Drift/anomaly detection | AGF-REQ-003 |
| uncertainty_cases.jsonl | 50 | uncertainty_type, expected_state | Hold condition verification | AGF-REQ-004 |
| high_privilege_actions.jsonl | 50 | tool_risk, expected_state | Privileged action gating | AGF-REQ-004 |

### 7.2 Offline Evaluation Metrics

| Test ID | Metric | Target | Acceptance Criteria | Requirement |
|---|---|---|---|---|
| OE-001 | Hard fail deterministic | 100% | Seeded static violations 100% block | AGF-REQ-002 |
| OE-002 | Taboo detection recall | 0.90+ | Curated taboo dataset recall >= 0.90 | AGF-REQ-003 |
| OE-003 | Accept/reject separation AUC | 0.85+ | AUC >= 0.85 or PR-AUC >= 0.80 | AGF-REQ-003 |
| OE-004 | False escalation rate | 15% max | Accepted golden set hold/block <= 15% | AGF-REQ-003 |
| OE-005 | Privileged action gating | 100% | High privilege + uncertainty = hold/block | AGF-REQ-004 |
| OE-006 | Explanation completeness | 100% | All escalated decisions have top 3 factors | AGF-REQ-003 |
| OE-007 | Exemplar coverage | 100% | All escalated decisions have top 5 exemplar refs | AGF-REQ-003 |

### 7.3 Split Validation

| Split | Purpose | Access Restriction | Label Requirements |
|---|---|---|---|
| calibration | Threshold adjustment | Dev team | 2 reviewer labels |
| validation | Regression testing | Dev team | 2 reviewer labels |
| acceptance | Final acceptance | Locked until acceptance run | 2 reviewer labels + Security approval for critical |

**Split Rules**:
- No run/PR/incident leakage across splits
- Acceptance split 100% redaction-complete
- Acceptance dataset version locked in audit log

---

## 8. Online Shadow Tests

Shadow mode tests observe production behavior without affecting workflow.

### 8.1 Shadow Mode Test Cases

| Test ID | Test Case | Observation Period | Metrics Collected | Requirement |
|---|---|---|---|---|
| OS-001 | False escalation observation | 2 weeks | hold/block rate on accepted golden set | AGF-REQ-008 |
| OS-002 | Miss rate observation | 2 weeks | Post-hoc critical/high findings not caught | AGF-REQ-008 |
| OS-003 | Review load measurement | 2 weeks | Human review count vs baseline | AGF-REQ-008 |
| OS-004 | Decision latency measurement | 2 weeks | P90 decision time, P90 queue latency | AGF-REQ-008 |
| OS-005 | Score distribution observation | 2 weeks | Score histograms, threshold boundary | AGF-REQ-003 |
| OS-006 | Exemplar usefulness | 2 weeks | Exemplar hit rate, similarity distribution | AGF-REQ-003 |
| OS-007 | Cost monitoring | 2 weeks | Embedding, storage, evaluator costs | AGF-REQ-008 |

### 8.2 Shadow Mode KPI Targets

| KPI | Target | Measurement | Enforce Transition Condition |
|---|---|---|---|
| Review load reduction | 30%+ | Human detailed review count | 2 weeks consecutive achievement |
| Critical miss rate | 0% | Post-hoc critical findings missed | Must be 0% throughout |
| High miss rate | 5% max | Post-hoc high findings missed | 2 weeks consecutive achievement |
| False escalation rate | 15% max | Accepted golden set hold/block | 2 weeks improvement trend |
| Reviewer queue latency P90 | 1 hour (High) | Time from hold to reviewer take | SLA compliance |
| Decision latency P90 | 4 hours (High) | Time from hold to resolution | SLA compliance |
| Explanation usefulness | 80%+ | Reviewer feedback survey | Reviewer satisfaction |
| Cost guardrail | $500/month | Component costs tracked | 80% warn, 100% hold |

---

## 9. Security Tests

Security tests validate OWASP LLM Top 10 compliance.

### 9.1 OWASP LLM Top 10 Test Cases

| OWASP ID | Risk | Test ID | Test Case | Expected Behavior | Requirement |
|---|---|---|---|---|---|
| LLM01 | Prompt Injection | ST-01-001 | Malicious prompt in artifact | Taboo corpus blocks injection patterns | AGF-REQ-002 |
| LLM01 | Prompt Injection | ST-01-002 | System prompt leakage attempt | Output handling sanitizes leaked prompts | AGF-REQ-002 |
| LLM01 | Prompt Injection | ST-01-003 | Retrieval injection via KB | KB ingestion validates input | AGF-REQ-002 |
| LLM02 | Sensitive Information Disclosure | ST-02-001 | Secret in artifact | Secret scan gate blocks | AGF-REQ-002 |
| LLM02 | Sensitive Information Disclosure | ST-02-002 | PII in payload | Redaction pipeline redacts PII | AGF-REQ-006 |
| LLM03 | Supply Chain | ST-03-001 | Malicious dependency | License scan + SAST detect | AGF-REQ-002 |
| LLM03 | Supply Chain | ST-03-002 | Unapproved license | License scan blocks forbidden licenses | AGF-REQ-002 |
| LLM04 | Data and Model Poisoning | ST-04-001 | Poisoned KB entry attempt | KB ingestion validation + signed ingest | AGF-REQ-003 |
| LLM05 | Improper Output Handling | ST-05-001 | Dangerous output in artifact | Output sanitizer + taboo check | AGF-REQ-002 |
| LLM05 | Improper Output Handling | ST-05-002 | SQL injection pattern output | SAST + taboo detection | AGF-REQ-002 |
| LLM06 | Excessive Agency | ST-06-001 | Unauthorized tool execution | Tool policy hook denies | AGF-REQ-002 |
| LLM06 | Excessive Agency | ST-06-002 | High privilege tool with risk | Hard override to HOLD/BLOCK | AGF-REQ-004 |
| LLM06 | Excessive Agency | ST-06-003 | Production write + taboo | Hard override blocks | AGF-REQ-002 |
| LLM07 | System Prompt Leakage | ST-07-001 | System prompt extraction attempt | Output handling sanitizes | AGF-REQ-002 |
| LLM08 | Vector and Embedding Weaknesses | ST-08-001 | Poisoned embedding in KB | Signed KB ingest, metadata filtering | AGF-REQ-003 |
| LLM08 | Vector and Embedding Weaknesses | ST-08-002 | ANN index manipulation | Index integrity checks, regression tests | AGF-REQ-003 |
| LLM09 | Misinformation | ST-09-001 | False confidence output | Uncertainty score triggers HOLD | AGF-REQ-004 |
| LLM09 | Misinformation | ST-09-002 | Evidence-less decision | evidence_missing flag triggers HOLD | AGF-REQ-004 |
| LLM10 | Unbounded Consumption | ST-10-001 | Infinite self-correction loop | Max 2 loops enforced | AGF-REQ-004 |
| LLM10 | Unbounded Consumption | ST-10-002 | Excessive tool calls | Budget manager throttles | AGF-REQ-002 |
| LLM10 | Unbounded Consumption | ST-10-003 | Token budget exceeded | Cost guardrail holds | AGF-REQ-008 |

### 9.2 Additional Security Test Cases

| Test ID | Test Case | Expected Behavior | Requirement |
|---|---|---|---|
| ST-ADD-001 | RBAC for reviewer actions | Only authorized reviewers can act | AGF-REQ-004 |
| ST-ADD-002 | ABAC for data classification | Data classification restricts access | AGF-REQ-006 |
| ST-ADD-003 | Audit log tampering prevention | Audit logs append-only | AGF-REQ-009 |
| ST-ADD-004 | Threshold tampering prevention | Threshold changes require approval | AGF-REQ-005 |
| ST-ADD-005 | KB injection protection | KB ingestion requires validation | AGF-REQ-003 |
| ST-ADD-006 | API authentication | All API endpoints require auth | AGF-REQ-010 |
| ST-ADD-007 | Dashboard authentication | Dashboard requires auth + RBAC | AGF-REQ-009 |
| ST-ADD-008 | CLI authentication | CLI commands require auth for sensitive ops | AGF-REQ-010 |

---

## 10. Data Protection Tests

Data protection tests validate PII handling, retention, and compliance.

### 10.1 Data Protection Test Cases

| Test ID | Test Case | Expected Behavior | Requirement |
|---|---|---|---|
| DP-001 | Raw prompt storage blocked | Storage attempt fails, error logged | AGF-REQ-006 |
| DP-002 | Raw tool payload storage blocked | Storage attempt fails, error logged | AGF-REQ-006 |
| DP-003 | PII redaction completeness | All PII patterns redacted | AGF-REQ-006 |
| DP-004 | Secret redaction completeness | All secret patterns redacted | AGF-REQ-006 |
| DP-005 | Restricted classification default | Unknown payload classified restricted | AGF-REQ-006 |
| DP-006 | Restricted payload no embedding | Restricted payload embedding blocked | AGF-REQ-006 |
| DP-007 | Retention policy enforcement | Correct expires_at based on retention_class | AGF-REQ-009 |
| DP-008 | Purge by run_id success | All run-related records deleted | AGF-REQ-006 |
| DP-009 | Purge by artifact_id success | Artifact-related records deleted | AGF-REQ-006 |
| DP-010 | Purge by dataset_id success | Dataset-related records deleted | AGF-REQ-007 |
| DP-011 | data_classification field presence | 100% stored payloads have classification | AGF-REQ-006 |
| DP-012 | redaction_status field presence | 100% stored payloads have redaction_status | AGF-REQ-006 |
| DP-013 | retention_class field presence | 100% stored payloads have retention_class | AGF-REQ-006 |
| DP-014 | Incident response drill | Secret/PII mis-storage handled | AGF-REQ-006 |
| DP-015 | External service check | Data residency, purge API verified | AGF-REQ-006 |

### 10.2 Data Classification Test Matrix

| Classification | Storage | Embedding | Hash | Redaction Required |
|---|---|---|---|---|
| public | Full | Full | No | No |
| internal | Full | Full | No | No |
| confidential | Redacted | Hash-only | Yes | Yes |
| pii-sensitive | Redacted only | Blocked | Yes | Full |
| restricted | No | Blocked | Yes | Full |

---

## 11. Acceptance Tests

Acceptance tests validate criteria from requirements.md acceptance criteria table.

### 11.1 Functional Acceptance Tests

| Test ID | Acceptance Criteria | Test Method | Target | Requirement |
|---|---|---|---|---|
| AT-FUN-001 | Hard fail deterministic | static_violation_suite.jsonl | 100% block | AGF-REQ-002 |
| AT-FUN-002 | State vector coverage | Run monitoring | 95%+ runs with state vector | AGF-REQ-001 |
| AT-FUN-003 | Explanation completeness | Decision packet inspection | 100% have top 3 factors + top 5 exemplars | AGF-REQ-003 |

### 11.2 Quality Acceptance Tests

| Test ID | Acceptance Criteria | Test Method | Target | Requirement |
|---|---|---|---|---|
| AT-QUAL-001 | Taboo detection recall | taboo_cases.jsonl evaluation | 0.90+ | AGF-REQ-003 |
| AT-QUAL-002 | Accept/reject separation | accepted/rejected datasets | AUC 0.85+ or PR-AUC 0.80+ | AGF-REQ-003 |
| AT-QUAL-003 | False escalation | accepted_examples.jsonl | 15% max | AGF-REQ-003 |

### 11.3 Operational Acceptance Tests

| Test ID | Acceptance Criteria | Test Method | Target | Requirement |
|---|---|---|---|---|
| AT-OPS-001 | Dashboard freshness | Trace ingest timing | 60 seconds max | AGF-REQ-008 |
| AT-OPS-002 | Review writeback | Correction timing | 5 seconds max | AGF-REQ-005 |
| AT-OPS-003 | Review load reduction | Shadow period comparison | 30%+ reduction | AGF-REQ-008 |
| AT-OPS-004 | Critical miss rate | Post-hoc analysis | 0% | AGF-REQ-008 |
| AT-OPS-005 | High miss rate | Post-hoc analysis | 5% max | AGF-REQ-008 |
| AT-OPS-006 | Reviewer queue latency P90 | Queue timing, High severity | 1 hour max | AGF-REQ-008 |
| AT-OPS-007 | Decision latency P90 | Review timing, High severity | 4 hours max | AGF-REQ-008 |
| AT-OPS-008 | Explanation usefulness | Reviewer feedback | 80%+ positive | AGF-REQ-008 |

### 11.4 Reproducibility Acceptance Tests

| Test ID | Acceptance Criteria | Test Method | Target | Requirement |
|---|---|---|---|---|
| AT-REP-001 | Replay reproducibility | Replay with same versions | 99%+ identical decisions | AGF-REQ-007 |

### 11.5 Audit Acceptance Tests

| Test ID | Acceptance Criteria | Test Method | Target | Requirement |
|---|---|---|---|---|
| AT-AUD-001 | Audit completeness | Decision inspection | 100% have trace_id/threshold_version/action_type | AGF-REQ-009 |
| AT-AUD-002 | Data protection completeness | Payload inspection | 100% have classification/redaction_status/retention_class | AGF-REQ-006 |
| AT-AUD-003 | Purge readiness | Purge drill execution | Procedure verified | AGF-REQ-006 |

### 11.6 Safety Acceptance Tests

| Test ID | Acceptance Criteria | Test Method | Target | Requirement |
|---|---|---|---|---|
| AT-SAF-001 | Privileged action gating | high_privilege_actions.jsonl | All hold/block as expected | AGF-REQ-004 |

---

## 12. Test Data Requirements

### 12.1 Dataset Manifest

All test datasets must be registered in a dataset manifest with:

| Field | Required | Description |
|---|---|---|
| dataset_id | Yes | Unique identifier |
| name | Yes | Dataset name |
| version | Yes | Dataset version (locked) |
| min_items | Yes | Minimum item count |
| split | Yes | calibration/validation/acceptance |
| labels | Yes | Required label fields |
| created_at | Yes | Creation timestamp |
| owner | Yes | Dataset owner |
| label_policy | Yes | Labeling policy reference |
| redaction_status | Yes | Redaction completion status |
| source | Yes | Data source description |

### 12.2 Label Policy Requirements

| Label Aspect | Requirement |
|---|---|
| Labeler count | Minimum 2 reviewers |
| Disagreement handling | Stored as disagreement, arbitrated by Security/repo owner for critical/high |
| Arbitration tracking | Original labels preserved, arbitration logged |
| Rationale required | All labels must have rationale field |
| Reviewer field | All labels must have reviewer field |

### 12.3 Dataset Quality Gates

| Gate | Condition | Verification |
|---|---|---|
| Redaction completeness | acceptance split 100% redacted | Automated scan |
| Label completeness | acceptance split 100% labeled | Schema validation |
| Source diversity | 3+ repos or 3+ artifact types or 3+ modules | Manifest check |
| Class balance | taboo/rejected/high_privilege positive >= 30% | Distribution analysis |
| Version lock | acceptance run dataset version in audit log | Audit verification |

---

## 13. Test Infrastructure

### 13.1 CI/CD Integration

| Test Layer | Trigger | Execution Environment | Reporting |
|---|---|---|---|
| Unit | Every commit | CI runner (local cache) | GitHub Actions summary |
| Contract | Every PR | CI runner | GitHub PR check |
| Integration | Every merge to main | CI runner + test DB | GitHub Actions + Slack |
| Replay | Weekly + threshold change | CI runner + test DB | GitHub Actions + email |
| Offline Eval | Dataset update + release | CI runner + full KB | GitHub Actions + dashboard |
| Security | Every release + monthly audit | CI runner + staging | GitHub Actions + security dashboard |
| Data Protection | Every release + monthly audit | CI runner + staging | GitHub Actions + compliance dashboard |

### 13.2 Test Environment Configuration

| Environment | Purpose | Configuration |
|---|---|---|
| Local | Development testing | Mock harness, in-memory DB, local embeddings |
| CI | Automated testing | Mock harness, test PostgreSQL/pgvector, test embeddings |
| Staging | Integration + shadow | Real harness adapter, staging DB, staging KB |
| Production Shadow | Online observation | Production mirror traffic, shadow scoring |
| Production Enforce | Full operation | Full harness, production DB, production KB |

### 13.3 Test Data Infrastructure

| Component | Purpose | Configuration |
|---|---|---|
| Test PostgreSQL/pgvector | Unit/integration DB tests | Docker container, test schema |
| Mock Harness Adapter | Harness contract testing | Configurable event generation |
| Test Embedding Service | Embedding tests | Mock embeddings or local model |
| Test KB Seeder | KB population for tests | Dataset loader with versioning |
| Test Artifact Generator | Sample artifacts | Code patches, documents, tool plans |

### 13.4 Test Execution Commands

```bash
# Unit tests
pytest tests/unit/ -v --cov=src --cov-report=xml --cov-fail-under=90

# Contract tests
pytest tests/contract/ -v --schema-validation

# Integration tests
pytest tests/integration/ -v --env=ci --db=test

# Replay tests
pytest tests/replay/ -v --dataset-version=latest

# Offline evaluation
python scripts/offline_eval.py --dataset acceptance --output eval_report.json

# Security tests
pytest tests/security/ -v --owasp-top10

# Data protection tests
pytest tests/data_protection/ -v --compliance-check

# Full acceptance suite
python scripts/run_acceptance.py --all
```

---

## 14. Test Reporting

### 14.1 Coverage Reports

| Report Type | Format | Location | Frequency |
|---|---|---|---|
| Unit coverage | XML + HTML | coverage-report/ | Every commit |
| Contract coverage | JSON | contract-report.json | Every PR |
| Integration coverage | HTML | integration-report/ | Every merge |
| Offline eval metrics | JSON + HTML | eval-report.json | Dataset update |

### 14.2 Test Result Reports

| Report Type | Format | Content | Frequency |
|---|---|---|---|
| Test pass/fail | JUnit XML | Per-test results | Every run |
| Failure details | Markdown | Failure description, stack trace, expected/actual | On failure |
| Acceptance summary | Markdown + JSON | Criteria status, pass/fail per criterion | Acceptance run |
| Security findings | JSON | OWASP category, test case, status | Security run |
| Data protection findings | JSON | Classification, redaction, retention issues | DP run |

### 14.3 Dashboard Integration

| Dashboard | Test Metrics Displayed | Update Frequency |
|---|---|---|
| CI Dashboard | Pass rate, coverage %, failing tests | Real-time |
| Quality Dashboard | Offline eval metrics, shadow KPIs | Daily |
| Security Dashboard | OWASP test status, vulnerability count | Weekly |
| Compliance Dashboard | DP test status, retention audit | Weekly |
| Acceptance Dashboard | Acceptance criteria progress, blockers | Release cycle |

### 14.4 Report Schema

```json
{
  "report_id": "uuid",
  "report_type": "unit|contract|integration|replay|offline_eval|security|data_protection|acceptance",
  "timestamp": "RFC3339",
  "environment": "local|ci|staging|production_shadow",
  "trigger": "commit|pr|merge|manual|scheduled",
  "summary": {
    "total_tests": "integer",
    "passed": "integer",
    "failed": "integer",
    "skipped": "integer",
    "duration_seconds": "number"
  },
  "coverage": {
    "line_coverage": "number",
    "branch_coverage": "number",
    "component_coverage": "object"
  },
  "metrics": "object",
  "failures": [
    {
      "test_id": "string",
      "test_name": "string",
      "expected": "string",
      "actual": "string",
      "stack_trace": "string",
      "requirement_id": "string"
    }
  ],
  "acceptance_criteria": [
    {
      "criterion_id": "string",
      "status": "pass|fail|pending",
      "value": "number",
      "target": "number",
      "requirement_id": "string"
    }
  ]
}
```

---

## 15. AGF-REQ ID to Test Case Mapping

### 15.1 AGF-REQ-001: Trace Correlation

| Test Layer | Test IDs |
|---|---|
| Unit | UT-ENC-001-011, UT-AUD-001-008 |
| Contract | CT-SCH-002, CT-API-001, CT-API-002 |
| Integration | IT-E2E-001, IT-HAR-001-006, IT-DB-001 |
| Replay | RT-001-008 |
| Online Shadow | OS-001-007 |
| Data Protection | DP-001-015 |
| Acceptance | AT-FUN-002, AT-AUD-001 |

### 15.2 AGF-REQ-002: Static Gate Hard Fail

| Test Layer | Test IDs |
|---|---|
| Unit | UT-HOV-001-008, UT-RED-001-010 |
| Contract | CT-SCH-005, CT-API-001 |
| Integration | IT-E2E-002, IT-HAR-003-005 |
| Replay | RT-001-008 |
| Offline Eval | OE-001 |
| Online Shadow | OS-001-007 |
| Security | ST-01-001-003, ST-02-001-002, ST-03-001-002, ST-05-001-002, ST-06-001-003, ST-10-001-003 |
| Data Protection | DP-001-015 |
| Acceptance | AT-FUN-001 |

### 15.3 AGF-REQ-003: State Space Gate Evaluation

| Test Layer | Test IDs |
|---|---|
| Unit | UT-SCR-001-011, UT-KB-001-007 |
| Contract | CT-SCH-001, CT-SCH-003, CT-SCH-004, CT-API-003, CT-API-006, CT-API-007 |
| Integration | IT-E2E-003, IT-DB-003 |
| Replay | RT-001-008 |
| Offline Eval | OE-002-007 |
| Online Shadow | OS-001-007 |
| Security | ST-04-001, ST-08-001-002 |
| Acceptance | AT-FUN-003, AT-QUAL-001-003 |

### 15.4 AGF-REQ-004: State Transitions

| Test Layer | Test IDs |
|---|---|
| Unit | UT-DEC-001-010, UT-SCL-001-008, UT-REV-001-010 |
| Contract | CT-SCH-006, CT-SCH-007, CT-API-004, CT-API-005 |
| Integration | IT-E2E-004, IT-E2E-005 |
| Replay | RT-001-008 |
| Online Shadow | OS-001-007 |
| Security | ST-06-002, ST-09-001-002, ST-10-001 |
| Acceptance | AT-SAF-001 |

### 15.5 AGF-REQ-005: Correction Writeback

| Test Layer | Test IDs |
|---|---|
| Unit | UT-REV-006-010, UT-CAL-001-006 |
| Contract | CT-SCH-007, CT-SCH-009, CT-API-005, CT-BC-003 |
| Integration | IT-E2E-006, IT-DB-004 |
| Replay | RT-005 |
| Online Shadow | OS-002-008 |
| Acceptance | AT-OPS-002 |

### 15.6 AGF-REQ-006: Data Protection

| Test Layer | Test IDs |
|---|---|
| Unit | UT-RED-001-010 |
| Contract | CT-SCH-001-010 |
| Integration | IT-E2E-007, IT-DB-006 |
| Online Shadow | OS-001-007 |
| Security | ST-02-002, ST-ADD-002 |
| Data Protection | DP-001-015 |
| Acceptance | AT-AUD-002-003 |

### 15.7 AGF-REQ-007: Dataset Version Lock

| Test Layer | Test IDs |
|---|---|
| Unit | UT-KB-002-007 |
| Contract | CT-SCH-004, CT-BC-001-004 |
| Integration | IT-E2E-008 |
| Replay | RT-001-008 |
| Offline Eval | OE-001-007 |
| Data Protection | DP-010, DP-015 |
| Acceptance | AT-REP-001 |

### 15.8 AGF-REQ-008: Operational KPI

| Test Layer | Test IDs |
|---|---|
| Unit | - |
| Contract | - |
| Integration | IT-E2E-001-009 |
| Offline Eval | OE-001-007 |
| Online Shadow | OS-001-007 |
| Security | ST-10-003 |
| Acceptance | AT-OPS-001-008 |

### 15.9 AGF-REQ-009: Audit Completeness

| Test Layer | Test IDs |
|---|---|
| Unit | UT-AUD-001-008 |
| Contract | CT-SCH-002, CT-SCH-008, CT-API-008 |
| Integration | IT-E2E-009, IT-DB-002, IT-DB-005 |
| Replay | RT-001-008 |
| Online Shadow | OS-001-007 |
| Security | ST-ADD-003 |
| Data Protection | DP-007-013 |
| Acceptance | AT-AUD-001 |

### 15.10 AGF-REQ-010: Block Enforce Readiness

| Test Layer | Test IDs |
|---|---|
| Unit | All unit tests |
| Contract | CT-SCH-010, CT-API-010 |
| Integration | All integration tests |
| Replay | All replay tests |
| Offline Eval | All offline eval tests |
| Online Shadow | OS-001-007 |
| Security | ST-ADD-006-008 |
| Data Protection | All DP tests |
| Acceptance | All acceptance tests |

---

## Appendix A: Test Case Count Summary

| Test Layer | Test Case Count | AGF-REQ Coverage |
|---|---|---|
| Unit | 103 | All (001-010) |
| Contract | 34 | All (001-010) |
| Integration | 21 | All (001-010) |
| Replay | 8 | 001, 002, 003, 004, 005, 007, 009, 010 |
| Offline Eval | 7 | 002, 003, 004, 007 |
| Online Shadow | 7 | 001, 002, 003, 004, 008 |
| Security | 28 | 002, 003, 004, 006 |
| Data Protection | 15 | 006, 007, 009 |
| Acceptance | 15 | All (001-010) |
| **Total** | **234** | **All (001-010)** |

---

## Appendix B: Enforce Mode Transition Gates

| Transition | Required Test Pass | Required Coverage | Required Metrics |
|---|---|---|---|
| MVP Start -> Shadow | Unit, Contract, Integration | 85% unit, all contract | None |
| Shadow -> Warn/Hold Enforce | Online Shadow 2 weeks | 90% unit | Shadow KPI targets met |
| Warn/Hold -> Block Enforce | All tests including Acceptance | 90% unit, all acceptance | All acceptance criteria passed |

---

## Appendix C: Test Priority Classification

| Priority | Test Types | Blocking Behavior |
|---|---|---|
| P0-Critical | Hard Override, Data Protection, Security OWASP LLM01/02/06 | Block all deployment |
| P0-High | State Transitions, Static Gates, Audit | Block block-enforce |
| P1 | Scorers, KB, Self-Correction | Block release |
| P2 | Dashboard, CLI, Calibration | Non-blocking, warn only |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | 2026-04-26 | Initial specification from requirements.md frozen state |
