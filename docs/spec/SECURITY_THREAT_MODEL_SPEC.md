# Security Threat Model Specification

## OWASP LLM Top 10 Mapping

| OWASP ID | Risk | Gate Mitigation | Residual Risk |
|---|---|---|---|
| **LLM01** | Prompt Injection | Input validation, taboo corpus, tool policy, human hold | Medium - novel injection patterns |
| **LLM02** | Sensitive Data Disclosure | Secret scan gate, PII redaction, classification policy | Low - if redaction enforced |
| **LLM03** | Supply Chain | SBOM/license gate, dependency validation | Medium - transitive deps |
| **LLM04** | Data Poisoning | Signed KB ingest, content hash validation, dual checks | Medium - requires monitoring |
| **LLM05** | Improper Output Handling | Output sanitizer, high privilege hold, rate limiting | Low - if sanitization complete |
| **LLM06** | Excessive Agency | Tool policy gate, risk weighting, high privilege hold | Low - hard override blocks |
| **LLM07** | System Prompt Leakage | System prompt protection, taboo corpus, input validation | Medium - indirect leakage |
| **LLM08** | Vector/Embedding Weaknesses | Metadata filtering, signed ingest, version control, dual checks | Medium - requires validation |
| **LLM09** | Misinformation | Constitution alignment scorer, drift detection, uncertainty escalation | Medium - subjective |
| **LLM10** | Unbounded Consumption | Resource budget gate, rate control, loop limits | Low - hard limits |

---

## Threat Actors

| Actor | Motivation | Capability | Target |
|---|---|---|---|
| Malicious User | Bypass gates, exfiltrate data | High (internal access) | Gate decisions, KB |
| External Attacker | Prompt injection, data theft | Medium (via crafted inputs) | Model, outputs |
| Insider | Sabotage, override decisions | High (admin access) | Thresholds, KB |
| Compromised Agent | Execute malicious actions | High (via agent compromise) | Tools, production |

---

## Attack Vectors

### AV-01: Prompt Injection via Artifact

```
Attack: Embed malicious prompt in artifact text
  ↓
Target: Model processing artifact
  ↓
Impact: Override gate decision, bypass tool policy
  ↓
Mitigation: Input validation, taboo corpus, human hold
```

### AV-02: Tool Policy Bypass

```
Attack: Disguise dangerous tool call as benign
  ↓
Target: Tool policy gate
  ↓
Impact: Execute rm -rf, database drop, etc.
  ↓
Mitigation: Hard override (tool_policy_deny), risk weighting
```

### AV-03: KB Poisoning

```
Attack: Insert malicious judgment document
  ↓
Target: Judgment KB embeddings
  ↓
Impact: Shift thresholds, accept dangerous artifacts
  ↓
Mitigation: Signed ingest, content hash, dual checks
```

### AV-04: Threshold Manipulation

```
Attack: Modify calibration profile
  ↓
Target: calibration_profiles table
  ↓
Impact: Lower thresholds, bypass gates
  ↓
Mitigation: Version control, audit logging, reviewer approval
```

### AV-05: SLA Timeout Abuse

```
Attack: Delay review to trigger timeout
  ↓
Target: Review queue SLA
  ↓
Impact: Auto-block legitimate artifacts
  ↓
Mitigation: Fail-closed, escalation routing, backup reviewer
```

---

## Trust Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│  TRUST LEVEL 0: External Input                               │
│  - User prompts, artifacts, tool outputs                     │
│  - NO TRUST: Validate all inputs                             │
└────────────────────────────┬────────────────────────────────┘
                             │ Input Validation Gate
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  TRUST LEVEL 1: Processed Input                              │
│  - Sanitized artifacts, validated tool calls                 │
│  - LIMITED TRUST: Still subject to semantic analysis         │
└────────────────────────────┬────────────────────────────────┘
                             │ Static Gates + State Encoder
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  TRUST LEVEL 2: Internal State                               │
│  - State vectors, scorer results                             │
│  - MODERATE TRUST: Validated by scorers                      │
└────────────────────────────┬────────────────────────────────┘
                             │ Decision Engine
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  TRUST LEVEL 3: Gate Decision                                │
│  - PASS/WARN/HOLD/BLOCK decisions                            │
│  - HIGH TRUST: But still logged, reviewable                  │
└────────────────────────────┬────────────────────────────────┘
                             │ Human Review (if HOLD)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  TRUST LEVEL 4: Approved Output                              │
│  - Final artifacts, deployed changes                         │
│  - FULL TRUST: After human approval or auto-pass             │
└─────────────────────────────────────────────────────────────┘
```

---

## Attack Trees

### AT-01: Bypass Gate Decision

```
Goal: Get dangerous artifact past gate
│
├─ OR-1: Manipulate artifact content
│   ├─ AND-1a: Embed prompt injection
│   │   ├─ Hide in code comment
│   │   └─ Hide in docstring
│   └─ AND-1b: Avoid taboo corpus detection
│       ├─ Use novel injection pattern
│       └─ Split injection across multiple steps
│
├─ OR-2: Manipulate KB
│   ├─ AND-2a: Insert poisoned judgment doc
│   │   ├─ Gain write access to KB
│   │   └─ Create accepted example with injection
│   └─ AND-2b: Shift thresholds
│       ├─ Modify calibration profile
│       └─ Trigger recalibration with poisoned data
│
├─ OR-3: Exploit timing
│   ├─ AND-3a: Trigger SLA timeout
│   │   ├─ Flood review queue
│   │   └─ Delay ACK/response
│   └─ AND-3b: Race condition
│       ├─ Submit before gate enabled
│       └─ Modify during shadow mode
│
├─ OR-4: Compromise reviewer
│   ├─ AND-4a: Social engineering
│   └─ AND-4b: Credential theft
```

### AT-02: Data Exfiltration

```
Goal: Extract secrets/data via gate system
│
├─ OR-1: Via artifact
│   ├─ AND-1a: Include secret in artifact
│   │   ├─ Secret scan bypass (novel format)
│   │   └─ Encoding obfuscation
│   └─ AND-1b: Extract via approved output
│       ├─ Pass gate with embedded data
│       └─ Retrieve from deployed artifact
│
├─ OR-2: Via KB query
│   ├─ AND-2a: Query judgment_docs
│   │   ├─ Gain read access
│   │   └─ Extract sensitive judgments
│   └─ AND-2b: Via embedding similarity
│       ├─ Craft query vector
│       └─ Extract similar sensitive docs
│
├─ OR-3: Via audit logs
│   ├─ AND-3a: Access audit_events
│   │   ├─ Gain DB access
│   │   └─ Query raw payloads (if not redacted)
│   └─ AND-3b: Export JSONL
│       ├─ Gain export access
│       └─ Download audit export
```

---

## STRIDE Analysis

### S - Spoofing

| Component | Threat | Mitigation |
|---|---|---|
| Reviewer identity | Fake reviewer approval | Authentication, audit logging |
| KB document source | Fake judgment doc source | Signed ingest, source_type validation |
| Threshold version | Fake version string | Hash verification, immutable versions |

### T - Tampering

| Component | Threat | Mitigation |
|---|---|---|
| State vector | Modify score | Audit logging, version locking |
| Threshold config | Lower thresholds | Version control, reviewer approval |
| KB embedding | Poison corpus | Content hash, dual checks |
| Audit log | Delete evidence | Immutable logs, retention policy |

### R - Repudiation

| Component | Threat | Mitigation |
|---|---|---|
| Review action | Claim no action | Audit logging with timestamps |
| Gate decision | Claim wrong decision | Full audit trail, trace_id |
| Correction | Claim no correction | Correction tracking, judgment log |

### I - Information Disclosure

| Component | Threat | Mitigation |
|---|---|---|
| Raw prompt | Leak sensitive data | Redaction, classification |
| Artifact body | Leak secrets | Secret scan, PII redaction |
| KB content | Leak judgment reasons | Access control, scope filtering |
| Threshold values | Leak security posture | Access control |

### D - Denial of Service

| Component | Threat | Mitigation |
|---|---|---|
| Embedding API | Rate limit exhaustion | Budget management, caching |
| Review queue | Flood queue | Queue limits, severity filtering |
| DB storage | Fill storage | Retention policy, TTL |
| SLA timer | Delay all reviews | Fail-closed, auto-block |

### E - Elevation of Privilege

| Component | Threat | Mitigation |
|---|---|---|
| Tool execution | Execute dangerous tools | Tool policy gate, hard override |
| KB write | Insert malicious docs | Access control, signed ingest |
| Calibration | Modify thresholds | Role-based access, approval required |
| Review approval | Approve dangerous artifact | SLA tracking, escalation |

---

## Risk Assessment Matrix

| Threat ID | Severity | Likelihood | Impact | Risk Level |
|---|---|---|---|---|
| AV-01 Prompt Injection | High | Medium | Critical | **High** |
| AV-02 Tool Bypass | Critical | Low | Critical | **High** |
| AV-03 KB Poisoning | High | Low | High | **Medium** |
| AV-04 Threshold Manipulation | High | Low | High | **Medium** |
| AV-05 SLA Abuse | Medium | Low | Medium | **Low** |
| LLM01 Injection | High | Medium | Critical | **High** |
| LLM06 Excessive Agency | Critical | Low | Critical | **High** |
| LLM08 Vector Weakness | High | Medium | High | **Medium** |

---

## Incident Response

### IR-01: Secret Leak Detected

```
Detection: Secret scan gate fires, or post-deploy discovery
│
├─ Phase 1: Containment (immediate)
│   ├─ Block artifact
│   ├─ Revoke secret (API key rotation)
│   ├─ Quarantine affected runs
│   └─ Notify security team
│
├─ Phase 2: Eradication (within 1 hour)
│   ├─ Identify scope (all affected artifacts)
│   ├─ Purge from audit logs (if raw stored)
│   ├─ Re-embed affected KB docs
│   └─ Update secret scan patterns
│
├─ Phase 3: Recovery (within 4 hours)
│   ├─ Rotate all potentially exposed secrets
│   ├─ Re-validate affected decisions
│   ├─ Clear review queue backlog
│   └─ Resume normal operations
│
└─ Phase 4: Post-incident (within 24 hours)
    ├─ Root cause analysis
    ├─ Update taboo corpus
    ├─ Add to judgment_log
    └─ Threshold review
```

### IR-02: PII Mis-Storage

```
Detection: Audit review, data classification check
│
├─ Phase 1: Containment (immediate)
│   ├─ Mark affected data as restricted
│   ├─ Disable raw storage
│   ├─ Block further writes
│   └─ Notify DPO/Legal
│
├─ Phase 2: Eradication (within 2 hours)
│   ├─ Identify all affected rows
│   ├─ Purge raw payload columns
│   ├─ Invalidate affected embeddings
│   ├─ Re-classify affected datasets
│   └─ Audit trail annotation
│
├─ Phase 3: Recovery (within 24 hours)
│   ├─ Re-process affected runs with redaction
│   ├─ Re-embed with sanitized content
│   ├─ Validate data protection policy
│   └─ Resume with strict redaction
│
└─ Phase 4: Post-incident (within 48 hours)
    ├─ Review redaction policy
    ├─ Update classification rules
    ├─ Add to judgment_log
    └─ External audit if required
```

### IR-03: Prompt Injection Successful

```
Detection: Unusual gate decisions, anomaly detection
│
├─ Phase 1: Containment (immediate)
│   ├─ Block affected run
│   ├─ Quarantine decision
│   ├─ Revoke any approved artifacts
│   └─ Notify security team
│
├─ Phase 2: Eradication (within 4 hours)
│   ├─ Identify injection pattern
│   ├─ Add to taboo corpus
│   ├─ Re-evaluate similar artifacts
│   ├─ Review affected thresholds
│   └─ Update input validation rules
│
├─ Phase 3: Recovery (within 8 hours)
│   ├─ Re-process quarantined decisions
│   ├─ Re-validate affected KB entries
│   ├─ Clear false approvals
│   └─ Resume with enhanced validation
│
└─ Phase 4: Post-incident (within 48 hours)
    ├─ Analyze injection technique
    ├─ Update constitution corpus
    ├─ Enhance taboo patterns
    └─ Recalibrate if needed
```

---

## Security Acceptance Criteria

| Criterion | Requirement | Verification |
|---|---|---|
| SAC-01 | All OWASP LLM Top 10 mitigations implemented | Threat model review |
| SAC-02 | Hard override blocks on secret/tool deny | Unit test 100% coverage |
| SAC-03 | PII/secret raw storage disabled by default | Config validation |
| SAC-04 | All inputs validated before processing | Contract test |
| SAC-05 | All decisions logged with trace_id | Audit completeness test |
| SAC-06 | SLA fail-closed on timeout | Integration test |
| SAC-07 | Threshold changes require approval | RBAC test |
| SAC-08 | KB ingest signed and validated | Poisoning test |
| SAC-09 | Escalation routing functional | Escalation test |
| SAC-10 | No single point of privilege bypass | STRIDE review |
