# Acceptance Criteria Specification

## Document Overview

This document defines the formal acceptance criteria for the agent-gatefield project, mapping each requirement from the requirements specification to measurable targets, test procedures, and readiness gates.

**Document Version:** v1.0
**Last Updated:** 2026-04-26
**Requirements Reference:** `docs/requirements.md`

---

## 1. Technical Acceptance Criteria

### 1.1 Trace Collection and Correlation

| Requirement ID | AGF-REQ-001 |
|---|---|
| **Description** | Existing harness run lifecycle events must be subscribed, enabling correlation of run/trace/artifact |
| **Target Value** | 95% of target runs generate trace + state vector |
| **Measurement Method** | Count runs with complete trace_id/state_vector pairs vs total target runs |
| **Test Procedure** | 1. Generate 100 test runs across all artifact types<br/>2. Query audit_events table for trace_id presence<br/>3. Query state_vectors table for matching run_id<br/>4. Calculate coverage ratio |
| **Acceptance Gate** | Product Readiness Gate: MVP Start |

### 1.2 Static Gate Hard Fail

| Requirement ID | AGF-REQ-002 |
|---|---|
| **Description** | Static gates must deterministically block on hard fail conditions |
| **Target Value** | 100% block rate for seeded violations |
| **Measurement Method** | Execute seeded static_violation_suite.jsonl, measure block rate |
| **Test Procedure** | 1. Load static_violation_suite.jsonl (50 items minimum)<br/>2. Execute each violation through static gate pipeline<br/>3. Verify block decision for each seeded case<br/>4. Confirm block reason matches expected_gate_name |
| **Acceptance Gate** | Product Readiness Gate: MVP Start |

### 1.3 State Space Gate Evaluation

| Requirement ID | AGF-REQ-003 |
|---|---|
| **Description** | State space gate must evaluate semantic/taboo/accepted/rejected/drift/uncertainty axes |
| **Target Value** | Taboo recall >= 0.90, AUC >= 0.85 or PR-AUC >= 0.80 |
| **Measurement Method** | Offline evaluation on curated taboo_cases.jsonl and accept/reject separation dataset |
| **Test Procedure** | 1. Load taboo_cases.jsonl (100 items)<br/>2. Run taboo proximity scorer on each item<br/>3. Calculate recall at threshold_version settings<br/>4. Load accepted_examples.jsonl + rejected_examples.jsonl<br/>5. Compute AUC/PR-AUC for accept/reject separation<br/>6. Verify scorer outputs include all required axes |
| **Acceptance Gate** | Product Readiness Gate: Shadow Mode |

### 1.4 State Transition and Timeout

| Requirement ID | AGF-REQ-004 |
|---|---|
| **Description** | pass/warn/hold/block state transitions with fail-closed timeout must be implemented |
| **Target Value** | High privilege actions correctly hold/block based on risk/uncertainty/taboo conditions |
| **Measurement Method** | Execute high_privilege_actions.jsonl, verify expected_state matches actual decision |
| **Test Procedure** | 1. Load high_privilege_actions.jsonl (50 items)<br/>2. Execute each action through decision engine<br/>3. Verify hold/block for conditions matching:<br/>   - high_privilege=1 AND uncertainty > judge_std_warn<br/>   - high_privilege=1 AND taboo_proximity >= taboo_warn<br/>   - prod_write=1 AND taboo_proximity >= taboo_warn<br/>4. Test timeout escalation by simulating SLA breach<br/>5. Verify fail-closed behavior (block on timeout) |
| **Acceptance Gate** | Product Readiness Gate: Warn/Hold Enforce |

### 1.5 Human Review Correction Integration

| Requirement ID | AGF-REQ-005 |
|---|---|
| **Description** | Reviewer corrections must be reflected in judgment log and calibration profile |
| **Target Value** | Corrections reflected in replayable state within 5 seconds |
| **Measurement Method** | Measure latency from reviewer decision to judgment_log/calibration_profile update |
| **Test Procedure** | 1. Execute hold decision, route to review queue<br/>2. Submit reviewer decision (approve/reject/recalibrate)<br/>3. Query judgment_logs table for new entry<br/>4. Query calibration_profiles for weight/threshold changes<br/>5. Verify state_vector reflects correction<br/>6. Measure elapsed time (target < 5 seconds) |
| **Acceptance Gate** | Product Readiness Gate: Warn/Hold Enforce |

### 1.6 Data Protection and Redaction

| Requirement ID | AGF-REQ-006 |
|---|---|
| **Description** | Raw prompt/raw tool payload must not be stored; unclassifiable payloads treated as restricted |
| **Target Value** | 100% of stored payloads have data_classification/redaction_status/retention_class |
| **Measurement Method** | Query all stored payloads, verify metadata completeness |
| **Test Procedure** | 1. Execute 50 runs with varied payload types<br/>2. Query audit_events, state_vectors, artifact stores<br/>3. Verify each payload has:<br/>   - data_classification field (public/internal/confidential/pii-sensitive/restricted)<br/>   - redaction_status field (redacted/restricted)<br/>   - retention_class field (audit/ops/pii-sensitive)<br/>4. Verify no raw_prompt entries in storage<br/>5. Execute purge dry-run for validation |
| **Acceptance Gate** | Product Readiness Gate: MVP Start |

### 1.7 Dataset Version Lock and Split Discipline

| Requirement ID | AGF-REQ-007 |
|---|---|
| **Description** | Acceptance dataset must be version locked with calibration/validation/acceptance splits separated |
| **Target Value** | 100% of acceptance split redacted, replay reproducibility >= 99% |
| **Measurement Method** | Verify dataset manifest, execute replay tests |
| **Test Procedure** | 1. Load dataset manifest from judgment_documents<br/>2. Verify split labels: calibration/validation/acceptance<br/>3. Verify no temporal leakage (same run_id not in multiple splits)<br/>4. Verify acceptance split items have redaction_status=redacted<br/>5. Execute replay on acceptance split twice with same threshold_version<br/>6. Compare decisions - expect >= 99% match |
| **Acceptance Gate** | Product Readiness Gate: Shadow Mode |

### 1.8 Stage Transition Control

| Requirement ID | AGF-REQ-008 |
|---|---|
| **Description** | Shadow -> warn/hold enforce -> block enforce transitions controlled by operational KPIs |
| **Target Value** | Review load reduction >= 30%, critical miss rate = 0%, high miss rate <= 5% |
| **Measurement Method** | KPI dashboard measurements during shadow period |
| **Test Procedure** | 1. Run shadow mode for 2 weeks minimum<br/>2. Measure baseline review load (runs requiring human check)<br/>3. Calculate reduction vs full-review baseline<br/>4. Track critical/high miss events<br/>5. Verify KPI targets met for 2 consecutive weeks before enforce transition<br/>6. Document KPI evidence in readiness review |
| **Acceptance Gate** | Product Readiness Gate: Block Enforce |

### 1.9 Audit Trace Completeness

| Requirement ID | AGF-REQ-009 |
|---|---|
| **Description** | Decision packets must be dual-stored in OTel trace and audit event |
| **Target Value** | 100% of gate decisions have trace_id/threshold_version/action_type |
| **Measurement Method** | Query audit_events, verify field completeness |
| **Test Procedure** | 1. Execute 100 gate decisions across all states<br/>2. Query audit_events table<br/>3. Verify each decision_id has:<br/>   - trace_id (OTel format)<br/>   - threshold_version (e.g., "v1")<br/>   - action_type (continue/self_correction/human_review/artifact_correction/process_correction)<br/>4. Cross-reference with OTel trace backend<br/>5. Verify span correlation |
| **Acceptance Gate** | Product Readiness Gate: MVP Start |

### 1.10 Production Block Enforce Activation

| Requirement ID | AGF-REQ-010 |
|---|---|
| **Description** | Production block enforce requires formal initial values and readiness gates satisfied |
| **Target Value** | All Product Readiness Gates - Block Enforce conditions satisfied |
| **Measurement Method** | Readiness review checklist with owner approvals |
| **Test Procedure** | 1. Execute readiness review checklist<br/>2. Verify each gate condition:<br/>   - Technical acceptance criteria met<br/>   - Operational KPI targets met<br/>   - Evidence complete for formal initial decisions<br/>   - Security approver sign-off<br/>   - Ops owner sign-off<br/>3. Document evidence for each condition<br/>4. Obtain owner approvals in audit trail<br/>5. Activate block enforce only after all gates passed |
| **Acceptance Gate** | Product Readiness Gate: Block Enforce |

---

## 2. Functional Acceptance

### 2.1 Hard Fail Deterministic Behavior

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-002 (derived) |
| **Description** | Static gate hard fails must produce consistent, deterministic block decisions |
| **Target Value** | 100% determinism - same violation always produces block |
| **Measurement Method** | Repeated execution of seeded violations |
| **Test Procedure** | 1. Execute static_violation_suite.jsonl 10 times<br/>2. Verify each violation produces identical block decision<br/>3. Verify block reasons are consistent<br/>4. Verify no variance in severity assessment |
| **Acceptance Gate** | MVP Start (P0) |

**Scorer Implementation Reference:**
- `DecisionEngine._apply_hard_overrides()` in `src/core/engine.py`
- Conditions: `secret > 0`, `sast_high > 0`, `tool_policy_deny > 0`

### 2.2 State Vector Coverage

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-001 (derived) |
| **Description** | State vectors must be generated for all target runs |
| **Target Value** | >= 95% coverage |
| **Measurement Method** | Ratio of runs with complete state_vector vs total target runs |
| **Test Procedure** | 1. Execute 200 runs across artifact types<br/>2. Query state_vectors table for coverage<br/>3. Verify each state_vector contains required fields:<br/>   - semantic (vector_ref)<br/>   - rule_violation (sparse vector)<br/>   - risk (numeric/categorical)<br/>   - uncertainty (numeric)<br/>   - trajectory (sequence features)<br/>4. Calculate coverage percentage |
| **Acceptance Gate** | MVP Start (P0) |

**State Vector Schema:**
```json
{
  "semantic": {"provider": "local", "model": "local-hash-embedding-v1", "dims": 1536, "vector_ref": "..."},
  "rule_violation": {"secret": 0, "sast_high": 1, "license_unknown": 2},
  "risk": {"prod_write": 0, "pii_level": 1, "high_privilege": 0},
  "uncertainty": {"judge_std": 0.08, "tool_error_rate": 0.02, "self_confidence": 0.74},
  "trajectory": {"delta_semantic": 0.07, "tool_calls": 9, "branch_count": 2}
}
```

### 2.3 Explanation Completeness

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-009 (derived) |
| **Description** | Escalated decisions must include top factors and exemplar references |
| **Target Value** | 100% of escalated decisions have top 3 factors + top 5 exemplar refs |
| **Measurement Method** | Query escalated decisions, verify explanation fields |
| **Test Procedure** | 1. Generate escalated decisions (hold/block)<br/>2. Query decision packet for explanation fields<br/>3. Verify presence of:<br/>   - top 3 contributing factors (from scorer results)<br/>   - top 5 exemplar refs (from judgment KB)<br/>   - threshold_version<br/>   - hard_override_reason if applicable<br/>4. Calculate completeness percentage |
| **Acceptance Gate** | Shadow Mode (P0) |

**Implementation Reference:**
- `CompositeScorer.get_top_factors()` - extracts top 3 factors
- `CompositeScorer.collect_exemplar_refs()` - collects up to 5 exemplar refs
- `DecisionResult` dataclass in `src/core/engine.py`

---

## 3. Quality Acceptance

### 3.1 Taboo Detection Recall

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-003 (primary) |
| **Description** | Taboo proximity scorer must detect curated taboo cases with high recall |
| **Target Value** | Recall >= 0.90 |
| **Measurement Method** | Offline evaluation on taboo_cases.jsonl |
| **Test Procedure** | 1. Load taboo_cases.jsonl (minimum 100 items)<br/>2. Execute TabooProximityScorer on each item<br/>3. Apply threshold: taboo_warn = 0.80<br/>4. Calculate recall: TP / (TP + FN)<br/>5. Where TP = taboo_proximity >= threshold and expected_state in [hold, block]<br/>6. Verify recall >= 0.90 across taboo_types |
| **Acceptance Gate** | Shadow Mode (P0) |

**Formula:**
```
Recall = count(taboo_score >= taboo_warn AND expected_state IN [hold, block]) 
         / count(expected_state IN [hold, block])
```

**Threshold Settings:**
- `taboo_warn`: 0.80 (hold trigger)
- `taboo_block`: 0.88 (block trigger)

### 3.2 Accept/Reject Separation (AUC)

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-003 (derived) |
| **Description** | Composite score must separate accepted vs rejected examples |
| **Target Value** | AUC >= 0.85 OR PR-AUC >= 0.80 |
| **Measurement Method** | Offline ROC/PR curve on accepted_examples + rejected_examples |
| **Test Procedure** | 1. Load accepted_examples.jsonl (200 items)<br/>2. Load rejected_examples.jsonl (100 items)<br/>3. Compute composite score for each item<br/>4. Generate ROC curve: score vs binary label<br/>5. Calculate AUC using trapezoidal rule<br/>6. If AUC < 0.85, calculate PR-AUC<br/>7. Verify AUC >= 0.85 OR PR-AUC >= 0.80 |
| **Acceptance Gate** | Shadow Mode (P0) |

**Formula:**
```
AUC = integrate(TPR d(FPR)) over score thresholds
PR-AUC = integrate(Precision d(Recall)) over score thresholds
```

**Scorer Weights (Initial):**
- Constitution alignment: 0.20
- Taboo proximity: 0.30
- Accept similarity: 0.10
- Reject similarity: 0.15
- Drift: 0.10
- Anomaly: 0.10
- Uncertainty: 0.05

### 3.3 False Escalation Rate

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-008 (derived) |
| **Description** | Accepted golden set should not be incorrectly escalated |
| **Target Value** | <= 15% false escalation |
| **Measurement Method** | Percentage of accepted golden items escalated to hold/block |
| **Test Procedure** | 1. Load accepted_examples.jsonl (golden subset)<br/>2. Execute through decision engine<br/>3. Count decisions in [hold, block]<br/>4. Calculate false_escalation_rate<br/>5. Verify <= 15% |
| **Acceptance Gate** | Shadow Mode (P1) |

**Formula:**
```
False Escalation Rate = count(decision IN [hold, block]) 
                        / count(accepted_golden_items)
Target: <= 0.15 (15%)
```

---

## 4. Operational Acceptance

### 4.1 Dashboard Freshness

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-008 (operational) |
| **Description** | Dashboard must display trace data within freshness window |
| **Target Value** | <= 60 seconds from trace ingest to visualization |
| **Measurement Method** | Timestamp comparison: ingest_time vs dashboard_display_time |
| **Test Procedure** | 1. Execute run and capture trace ingest timestamp<br/>2. Poll dashboard API for run appearance<br/>3. Record first visible timestamp<br/>4. Calculate latency<br/>5. Repeat for 50 runs<br/>6. Verify P95 <= 60 seconds |
| **Acceptance Gate** | MVP Start (P0) |

**Formula:**
```
Freshness Latency = dashboard_display_time - trace_ingest_time
Target: P95 <= 60 seconds
```

### 4.2 Review Writeback Latency

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-005 (operational) |
| **Description** | Reviewer corrections must write back to replayable state quickly |
| **Target Value** | <= 5 seconds writeback latency |
| **Measurement Method** | Timestamp comparison: reviewer_decision_time vs state_update_time |
| **Test Procedure** | 1. Submit reviewer decision<br/>2. Query state_vectors for update timestamp<br/>3. Calculate writeback latency<br/>4. Repeat for 20 corrections<br/>5. Verify P95 <= 5 seconds |
| **Acceptance Gate** | Warn/Hold Enforce (P0) |

**Formula:**
```
Writeback Latency = state_update_time - reviewer_decision_submit_time
Target: P95 <= 5 seconds
```

### 4.3 Audit Completeness

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-009 (audit) |
| **Description** | All gate decisions must have complete audit trail |
| **Target Value** | 100% completeness |
| **Measurement Method** | Field presence check on audit_events |
| **Test Procedure** | 1. Execute 100 decisions across all states<br/>2. Query audit_events for required fields:<br/>   - trace_id, span_id, run_id<br/>   - artifact_hash, commit, branch<br/>   - static_gate_results<br/>   - state_vector_version<br/>   - retrieved_exemplar_refs<br/>   - scorer_outputs<br/>   - composite_decision<br/>   - action_selected<br/>   - threshold_version, policy_version<br/>   - retention_class<br/>3. Calculate completeness percentage |
| **Acceptance Gate** | MVP Start (P0) |

**Required Audit Fields:**
| Field | Requirement |
|---|---|
| trace_id | Required (OTel format) |
| span_id | Required |
| run_id | Required |
| artifact_hash | Required |
| static_gate_results | Required |
| scorer_outputs | Required |
| composite_decision | Required |
| action_selected | Required |
| threshold_version | Required |
| retention_class | Required |
| human_override | Conditional (if reviewed) |

---

## 5. Safety Acceptance

### 5.1 Privileged Action Gating

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-004 (safety) |
| **Description** | High privilege actions must be gated by risk/uncertainty/taboo conditions |
| **Target Value** | 100% of high privilege actions with elevated risk correctly held/blocked |
| **Measurement Method** | Execute high_privilege_actions.jsonl, verify expected_state |
| **Test Procedure** | 1. Load high_privilege_actions.jsonl (50 items)<br/>2. Execute each through decision engine<br/>3. Verify hold/block for conditions:<br/>   - high_privilege=1 AND (uncertainty > 0.15 OR taboo >= 0.80)<br/>   - prod_write=1 AND taboo >= 0.80<br/>4. Verify no pass decisions for these conditions<br/>5. Calculate gating accuracy |
| **Acceptance Gate** | Warn/Hold Enforce (P0) |

**Hard Override Conditions (engine.py):**
```python
# hold_if_high_privilege_and_uncertain
if risk.get('high_privilege', 0) == 1:
    if judge_std > 0.15 or tool_error_rate > 0.10:
        return GateState.HOLD

# block_if_prod_write_and_taboo_warn
if risk.get('prod_write', 0) == 1 and taboo_score >= 0.80:
    return GateState.BLOCK
```

### 5.2 Secret Detection Gating

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-002 (safety) |
| **Description** | Secret detection must trigger immediate block |
| **Target Value** | 100% block rate for detected secrets |
| **Measurement Method** | Execute seeded secret cases |
| **Test Procedure** | 1. Prepare 20 test cases with seeded secrets<br/>2. Execute through static gate + decision engine<br/>3. Verify block decision for each<br/>4. Verify hard_override_reason = "block_if_secret_found"<br/>5. Calculate block rate |
| **Acceptance Gate** | MVP Start (P0) |

**Implementation:**
```python
# block_if_secret_found
if rule_violation.get('secret', 0) > 0:
    return DecisionResult(
        decision=GateState.BLOCK,
        hard_override_reason="block_if_secret_found"
    )
```

### 5.3 Tool Policy Deny Gating

| Criterion | Description |
|---|---|
| **Requirement ID** | AGF-REQ-002 (safety) |
| **Description** | Tool policy deny must trigger immediate block |
| **Target Value** | 100% block rate for tool_policy_deny |
| **Measurement Method** | Execute seeded tool policy violations |
| **Test Procedure** | 1. Prepare 20 test cases with tool_policy_deny=1<br/>2. Execute through decision engine<br/>3. Verify block decision for each<br/>4. Verify hard_override_reason = "tool_policy_deny"<br/>5. Calculate block rate |
| **Acceptance Gate** | MVP Start (P0) |

---

## 6. Product Readiness Gates

### 6.1 Gate Definition

| Gate | Definition | Trigger Condition |
|---|---|---|
| MVP Start | Minimum functional implementation ready | All P0 technical criteria met |
| Shadow Mode | Decision logging without enforcement | State space gate functional, datasets ready |
| Warn/Hold Enforce | Self-correction and human review active | Quality targets met in shadow |
| Block Enforce | Full enforcement including block decisions | All operational KPIs met |

### 6.2 MVP Start Gate

| Requirement | Condition | Evidence Required |
|---|---|---|
| AGF-REQ-001 | Trace correlation >= 95% | Coverage report from audit query |
| AGF-REQ-002 | Static hard fail 100% | seeded_violation test results |
| AGF-REQ-006 | Data protection 100% | Payload metadata completeness report |
| AGF-REQ-009 | Audit completeness 100% | Field presence audit |

**Approval Required:** Platform Lead, Security Lead

### 6.3 Shadow Mode Gate

| Requirement | Condition | Evidence Required |
|---|---|---|
| AGF-REQ-003 | Taboo recall >= 0.90 | Offline eval report |
| AGF-REQ-007 | Dataset version lock, replay >= 99% | Dataset manifest + replay test |
| Section 3.1 | Quality targets met | AUC/false escalation report |

**Duration:** Minimum 2 weeks shadow operation

**Approval Required:** Product Lead, QA Lead

### 6.4 Warn/Hold Enforce Gate

| Requirement | Condition | Evidence Required |
|---|---|---|
| AGF-REQ-004 | State transitions functional | high_privilege_actions test results |
| AGF-REQ-005 | Review correction integration | Writeback latency report |
| Section 5 | Safety gating functional | Privileged action test results |
| Section 4.2 | Writeback latency <= 5s | Latency measurement |

**Duration:** Minimum 1 week warn/hold enforce

**Approval Required:** Ops Lead, Security Approver

### 6.5 Block Enforce Gate

| Requirement | Condition | Evidence Required |
|---|---|---|
| AGF-REQ-008 | KPI targets: review reduction >= 30%, critical miss = 0%, high miss <= 5% | KPI dashboard 2-week trend |
| AGF-REQ-010 | All readiness gates passed | Readiness review checklist |
| Section 4 | Operational targets met | Freshness, latency reports |
| Reviewer SLA | Critical 15/60min, High 60/240min | SLA compliance report |

**Approvals Required:**
- Security Approver (1)
- Ops Owner (1)
- Product Owner (1)
- Repo Owner (for each target repo)

**Fail-Closed Behavior:** If any condition not met, remain in warn/hold enforce

---

## 7. Test Layers

### 7.1 Test Layer Definitions

| Layer | Purpose | Environment | Pass Criteria |
|---|---|---|---|
| Unit | Individual component correctness | Local/CI | Deterministic output |
| Contract | API/schema compatibility | CI | Backward compatible |
| Integration | End-to-end pipeline | CI/Staging | Pipeline completes |
| Replay | Decision reproducibility | Offline | >= 99% match |
| Offline Eval | Quality metrics | Offline | Meet quality targets |
| Online Shadow | Production mirror | Production shadow | Meet operational KPIs |
| Security | Attack resistance | CI/Staging | Block/hold expected |
| Data Protection | Compliance verification | CI/Staging | No raw payload leakage |

### 7.2 Unit Tests

| Component | Test Cases | Pass Criteria |
|---|---|---|
| State Encoder | Input -> state_vector transformation | Schema compliance |
| Distance Calculator | cosine_similarity, mahalanobis_distance | Math correctness |
| Threshold Resolver | score -> state mapping | Threshold boundaries correct |
| Policy Override | hard_override conditions | Override priority correct |
| Individual Scorers | score calculation | Weighted_score calculation correct |

### 7.3 Contract Tests

| Contract | Test Cases | Pass Criteria |
|---|---|---|
| Trace Schema | OTel compatibility | trace_id/span_id format valid |
| Decision Packet | Schema fields | All required fields present |
| Dashboard API | REST endpoints | Response schema valid |
| CLI Commands | Exit codes | Expected exit codes for success/failure |

### 7.4 Integration Tests

| Pipeline | Test Cases | Pass Criteria |
|---|---|---|
| CI -> Static Gates | CI results ingested | Status/severity captured |
| Static -> State Scoring | Violation -> state vector | rule_violation populated |
| Scoring -> Review Queue | hold decision routing | Queue entry created |
| Review -> Audit Export | decision -> audit log | All fields exported |

### 7.5 Replay Tests

| Test | Procedure | Pass Criteria |
|---|---|---|
| Threshold Version Replay | Execute with threshold_version=X twice | >= 99% decision match |
| Policy Version Replay | Execute with policy_version=X twice | >= 99% decision match |
| Historical Decision Replay | Re-evaluate past runs | Consistent with original + documented changes |

### 7.6 Offline Evaluation Tests

| Dataset | Metrics | Pass Criteria |
|---|---|---|
| taboo_cases.jsonl | Recall | >= 0.90 |
| accepted + rejected examples | AUC/PR-AUC | >= 0.85 / >= 0.80 |
| drift_sequences.jsonl | Drift detection accuracy | >= 0.85 |
| uncertainty_cases.jsonl | Hold trigger accuracy | >= 0.90 |

### 7.7 Online Shadow Tests

| Metric | Measurement | Pass Criteria |
|---|---|---|
| False escalation | Golden set escalation rate | <= 15% |
| Miss rate | Post-hoc critical/high detection | Critical = 0%, High <= 5% |
| Review load | Human intervention rate | Reduction >= 30% |

### 7.8 Security Tests

| Attack Vector | Test Cases | Pass Criteria |
|---|---|---|
| Prompt Injection | seeded injection patterns | Block/hold triggered |
| Tool Misuse | dangerous tool patterns | Tool policy deny triggered |
| Secret Leakage | seeded secrets in output | Block triggered |
| Output Handling | dangerous output patterns | Sanitization triggered |

---

## 8. Dataset Requirements

### 8.1 Dataset Specifications

| Dataset | Minimum Items | Labels | Required Metadata |
|---|---|---|---|
| static_violation_suite.jsonl | 50 | gate_name, severity, expected_state | scanner, rule_id, evidence_ref |
| taboo_cases.jsonl | 100 | taboo_type, expected_state, rationale | source, risk_class, redaction_status |
| accepted_examples.jsonl | 200 | accepted, quality_axis, reviewer | repo, artifact_type, merge_commit |
| rejected_examples.jsonl | 100 | rejected, reason_code, expected_state | reviewer, reject_reason, correction |
| judgment_logs.jsonl | 100 | decision, correction_type, rationale | reviewer, decision_time, threshold_version |
| drift_sequences.jsonl | 50 sequences | normal_step, drift_step, expected_state | sequence_id, step_index, tool_count |
| uncertainty_cases.jsonl | 50 | uncertainty_type, expected_state | evaluator_count, variance, tool_error |
| high_privilege_actions.jsonl | 50 | tool_risk, expected_state | tool_name, permission_scope, env |

### 8.2 Split Discipline

| Split | Purpose | Access Restriction |
|---|---|---|
| Calibration | Threshold tuning | Development only |
| Validation | Regression testing | Development/QA only |
| Acceptance | Final acceptance | Locked until acceptance run |

**Split Rules:**
- No temporal leakage: same run_id/PR/incident cannot span multiple splits
- Minimum 3 repo/artifact_type diversity for accepted/rejected datasets
- Class balance: taboo/rejected/high_privilege positive >= 30%

### 8.3 Label Quality Requirements

| Requirement | Specification |
|---|---|
| Label count | Minimum 2 reviewers per item |
| Disagreement handling | Preserve original labels, use arbitrated label for acceptance |
| Critical/High arbitration | Security/repo owner arbitration required |
| Label fields | label, rationale, reviewer required |

### 8.4 Redaction Requirements

| Requirement | Specification |
|---|---|
| Acceptance split redaction | 100% items must be redacted |
| Redaction fields | redaction_version, redaction_status, content_hash_before, content_hash_after |
| Restricted handling | Unclassifiable payloads -> restricted, no embedding |

---

## 9. Replay Reproducibility

### 9.1 Target

| Metric | Target | Measurement |
|---|---|---|
| Decision reproducibility | >= 99% | Same threshold_version/policy_version -> same decision |

### 9.2 Version Locking Requirements

| Element | Version Lock Required |
|---|---|
| Threshold version | threshold_version field in decision |
| Policy version | policy_version field in audit event |
| Embedding model | model/dims in embedding record |
| Scorer weights | weights_json in calibration_profile |
| Dataset version | dataset_manifest version in audit |

### 9.3 Reproducibility Test Procedure

```
1. Select acceptance dataset
2. Execute decision engine with threshold_version=X
3. Record all decisions
4. Execute again with identical parameters
5. Compare decision sets
6. Calculate match ratio
7. Verify >= 99%
```

### 9.4 Reproducibility Failure Handling

| Condition | Action |
|---|---|
| < 99% match | Investigate scorer/stochastic sources |
| Threshold drift | Document threshold change, replay with new version |
| Embedding model change | Dual-write period, replay comparison |

---

## 10. KPI Targets

### 10.1 Operational KPIs

| KPI | Definition | Target | Measurement Method |
|---|---|---|---|
| Review Load Reduction | Reduction in human detailed review | >= 30% | Baseline comparison: full-review vs gate-filtered |
| Critical Miss Rate | Critical runs not held/blocked | 0% | Post-hoc classification comparison |
| High Miss Rate | High runs not held/blocked | <= 5% | Post-hoc classification comparison |
| False Escalation Rate | Golden set incorrectly escalated | <= 15% | accepted_examples escalation count |
| Reviewer Queue Latency (High P90) | Time from hold to reviewer start | <= 1 hour | Timestamp: hold_time - review_start_time |
| Decision Latency (High P90) | Time from hold to resolution | <= 4 hours | Timestamp: hold_time - decision_time |
| Explanation Usefulness | Reviewer initial judgment from explanation | >= 80% | Reviewer feedback survey |

### 10.2 SLA Targets

| Class | ACK Target | Decision Target | Conditions |
|---|---|---|---|
| Critical | 15 minutes | 60 minutes | Hard fail, taboo high, prod_write+taboo, secret |
| High | 60 minutes | 240 minutes | Drift/block, judge conflict, high privilege |
| Medium | Same business day | Next business day | Warn repeated, cost spike |
| Low | Not required | Backlog | Learning notes |

### 10.3 Quality KPIs

| KPI | Definition | Target | Formula |
|---|---|---|---|
| Taboo Recall | Detection rate for taboo cases | >= 0.90 | TP / (TP + FN) |
| AUC | Accept/reject separation | >= 0.85 | ROC AUC |
| PR-AUC | Precision-recall separation | >= 0.80 | PR curve AUC |
| Replay Reproducibility | Decision consistency | >= 99% | Match ratio |

### 10.4 Cost KPIs

| KPI | Definition | Target | Action |
|---|---|---|---|
| Monthly Budget | Total service cost | <= $500/month | Warn at 80%, hold at 100% |
| Embedding Cost | Token-based embedding cost | Within budget | Monitor token usage |
| Storage Cost | Vector/payload storage | Within budget | Monitor GB usage |

### 10.5 Measurement Methods

| KPI Category | Data Source | Collection Frequency |
|---|---|---|
| Operational | audit_events, review_queue | Real-time / hourly |
| Quality | offline_eval results | Per eval run |
| Cost | billing metrics | Daily |
| SLA | timestamp fields | Per decision |

---

## 11. Acceptance Gate Mapping Summary

| Gate | Primary Requirements | Key Metrics | Approval Chain |
|---|---|---|---|
| MVP Start | AGF-REQ-001, 002, 006, 009 | Coverage 95%, Hard fail 100%, Data protection 100% | Platform, Security |
| Shadow Mode | AGF-REQ-003, 007 | Recall 0.90+, Replay 99%+ | Product, QA |
| Warn/Hold Enforce | AGF-REQ-004, 005, Safety 5.x | State transitions, Writeback 5s, Privileged gating | Ops, Security |
| Block Enforce | AGF-REQ-008, 010, All KPIs | Review reduction 30%+, Miss rates, SLA compliance | Security, Ops, Product, Repo |

---

## Appendix A: Threshold Reference (Initial Values)

| Signal | Warn Threshold | Block Threshold | Source |
|---|---|---|---|
| Taboo proximity | 0.80 | 0.88 | Accepted P95/P99 |
| Reject similarity | 0.75 | 0.85 | Reject corpus distribution |
| Anomaly percentile | P95 (0.95) | P99 (0.99) | Trajectory features |
| Judge stddev | 0.15 | 0.25 | Multi-evaluator variance |
| Tool error rate | 0.10 | 0.25 | Windowed measurement |

## Appendix B: Scorer Weight Reference (Initial Values)

| Scorer | Weight | Risk Direction |
|---|---|---|
| Constitution Alignment | 0.20 | Higher = safer |
| Taboo Proximity | 0.30 | Higher = riskier |
| Accept Similarity | 0.10 | Higher = safer |
| Reject Similarity | 0.15 | Higher = riskier |
| Drift | 0.10 | Higher = riskier |
| Anomaly | 0.10 | Higher = riskier |
| Uncertainty | 0.05 | Higher = riskier |

## Appendix C: State Transition Reference

| Current State | Condition | Next State | Action |
|---|---|---|---|
| any | static hard fail | block | Run stop, correction action |
| any | high_privilege + risk/uncertainty/taboo warn | hold | Reviewer queue |
| pass | composite >= warn threshold | warn | Self-correction (max 2) |
| warn | correction success + below threshold | pass | Continue workflow |
| warn | 2 corrections failed OR 3 consecutive warns | hold | Reviewer queue |
| hold | reviewer approve | pass | Resume from checkpoint |
| hold | reviewer reject | block | Correction action |
| hold | SLA timeout | block | Fail-closed escalation |
