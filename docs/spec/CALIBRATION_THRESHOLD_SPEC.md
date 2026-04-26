# Calibration and Threshold Specification

## Overview

This document specifies the calibration methodology and threshold configuration for the agent-gatefield state space gate system. Thresholds are derived from accepted/rejected distributions rather than fixed values, enabling project-specific adaptation while maintaining safety boundaries.

---

## 1. Scorer Weights

### 1.1 Default Weights

The composite score is calculated as a weighted sum of individual scorer outputs. Default weights are defined in `src/scorers/__init__.py`:

| Scorer | Weight | Role |
|---|---|---|
| Constitution Alignment | 0.20 | Measures alignment with design principles |
| Taboo Proximity | 0.30 | Detects proximity to forbidden patterns |
| Accept Similarity | 0.10 | Positive signal: similarity to accepted examples |
| Reject Similarity | 0.15 | Negative signal: similarity to rejected examples |
| Drift | 0.10 | Deviation from accepted trajectory baseline |
| Anomaly | 0.10 | Out-of-distribution detection |
| Uncertainty | 0.05 | Combined uncertainty factors |

**Total: 1.00 (normalized)**

### 1.2 Weight Adjustment

Weights can be adjusted through configuration:

```yaml
state_space_gate:
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
```

### 1.3 Weight Ranges and Constraints

| Constraint | Description |
|---|---|
| Min weight | 0.05 (minimum meaningful contribution) |
| Max weight | 0.50 (prevent single scorer dominance) |
| Sum | Must equal 1.00 |
| Taboo weight | Minimum 0.25 for safety-critical projects |
| Uncertainty weight | Fixed at 0.05 to ensure escalation path |

**Formula for weighted score:**

```
weighted_score_i = score_i × weight_i
composite_score = Σ(weighted_score_i) for all scorers
```

---

## 2. Threshold Types

### 2.1 Threshold Categories

| Type | Purpose | Effect |
|---|---|---|
| Warn | Early warning signal | Triggers self-correction loop (max 2 iterations) |
| Block | Hard boundary | Stops run, requires human intervention |
| Percentile-based | Distribution-derived | Computed from accepted/rejected corpus |

### 2.2 Threshold Direction by Scorer

| Scorer | Direction | Higher Score Meaning |
|---|---|---|
| Constitution Alignment | Safe-side | Higher = better (threshold on lower bound) |
| Taboo Proximity | Risk-side | Higher = riskier (threshold on upper bound) |
| Accept Similarity | Safe-side | Higher = better (supplementary, not pass criterion) |
| Reject Similarity | Risk-side | Higher = riskier (threshold on upper bound) |
| Drift | Risk-side | Higher = more deviation (threshold on upper bound) |
| Anomaly | Risk-side | Higher = more anomalous (threshold on upper bound) |
| Uncertainty | Risk-side | Higher = less confidence (threshold on upper bound) |

### 2.3 Hard Override Thresholds

Certain conditions bypass composite scoring:

| Condition | Threshold | Effect |
|---|---|---|
| Secret detected | `secret > 0` | Immediate block |
| Tool policy deny | `tool_policy = deny` | Immediate block |
| Production write + taboo warn | `prod_write=1 AND taboo > warn_threshold` | Hold |
| High privilege + uncertain | `high_privilege=1 AND uncertainty > warn` | Hold |

---

## 3. Bootstrap Thresholds

### 3.1 Initial Threshold Values

The following thresholds are the formal initial values for production deployment:

| Signal | Warn Threshold | Block Threshold | Design Principle |
|---|---|---|---|
| Taboo proximity | Accepted P95 or 0.80 | Accepted P99 or 0.88 | Recalibrate per project |
| Negative similarity | 0.75 | 0.85 | Auxiliary until reject corpus sufficient |
| Drift score | Accepted P95 | Accepted P99 | Separate distribution per step sequence |
| Mahalanobis | Accepted P95 | Accepted P99 | Assumes accepted group covariance |
| Anomaly percentile | Top 5% | Top 1% | Contamination is calibration parameter |
| Judge stddev | 0.15 | 0.25 | Assumes multiple evaluators |
| Tool failure rate | 0.10 | 0.25 | Window-based for long runs |

### 3.2 Contamination Rate for Anomaly Detection

| Method | Default Contamination | Range |
|---|---|---|
| Isolation Forest | 0.01 (1%) | 0.005 - 0.02 |
| Mahalanobis | N/A (distance-based) | Threshold from percentile |

### 3.3 Threshold Priority

When both percentile-based and fixed thresholds are specified:

```
effective_threshold = min(percentile_threshold, fixed_threshold)  # for risk-side
effective_threshold = max(percentile_threshold, fixed_threshold)  # for safe-side
```

For taboo (risk-side): Use the more conservative (lower) threshold.

---

## 4. Calibration Procedure

### 4.1 Offline Calibration Flow

```
1. Collect accepted/rejected distributions from shadow mode
2. Compute score distributions for each scorer
3. Derive percentile-based thresholds:
   - Warn: P95 of accepted distribution (risk-side)
   - Block: P99 of accepted distribution (risk-side)
4. Validate on calibration split
5. Confirm on validation split
6. Lock thresholds for acceptance testing
```

### 4.2 Taboo Threshold Calibration

From `src/core/calibration.py`:

```python
def calibrate_taboo_threshold(
    self,
    accepted_scores: List[float],
    rejected_scores: List[float],
    percentile: int = 95
) -> CalibrationResult:
    # Sort accepted scores
    sorted_accepted = sorted(accepted_scores)
    idx = int(len(sorted_accepted) * percentile / 100)
    threshold = sorted_accepted[idx] if idx < len(sorted_accepted) else sorted_accepted[-1]

    return CalibrationResult(
        axis="taboo",
        old_threshold=0.0,
        new_threshold=threshold,
        sample_size=len(accepted_scores),
        metric_name="accepted_p95",
        metric_value=threshold
    )
```

**Formula:**

```
threshold = sorted_accepted[n × percentile / 100]
```

Where `n` is the number of accepted samples.

### 4.3 Anomaly Percentile Calibration

```python
def calibrate_anomaly_percentile(
    self,
    anomaly_scores: List[float],
    warn_percentile: int = 95,
    block_percentile: int = 99
) -> Dict:
    sorted_scores = sorted(anomaly_scores)
    n = len(sorted_scores)

    warn_idx = int(n * warn_percentile / 100)
    block_idx = int(n * block_percentile / 100)

    return {
        "warn_threshold": sorted_scores[warn_idx],
        "block_threshold": sorted_scores[block_idx]
    }
```

### 4.4 Calibration Metrics

```python
def compute_metrics(
    self,
    predictions: List[str],
    labels: List[str]
) -> Dict:
    tp = count(p="block", l="block")
    fp = count(p="block", l="pass")
    tn = count(p="pass", l="pass")
    fn = count(p="pass", l="block")

    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    f1 = 2 × precision × recall / (precision + recall)

    return {"precision", "recall", "f1", "tp", "fp", "tn", "fn"}
```

### 4.5 Minimum Sample Sizes

| Threshold Type | Minimum Accepted Samples | Minimum Rejected Samples |
|---|---|---|
| Taboo | 100 | 50 (optional) |
| Drift | 50 sequences | 20 drift sequences |
| Anomaly | 200 | N/A (contamination estimate) |
| Accept/Reject separation | 200 accepted | 100 rejected |

---

## 5. Threshold Versioning

### 5.1 Version Schema

Each threshold configuration has a version identifier:

```
threshold_version: "threshold-v{major}.{minor}-{timestamp}"
```

Example: `threshold-v1.0-20250115`

### 5.2 Version Components

| Component | Description | Change Trigger |
|---|---|---|
| Major | Breaking change | New scorer added, weight restructure |
| Minor | Calibration update | Threshold value adjustment |
| Timestamp | Calibration date | Each calibration run |

### 5.3 Version Storage

Threshold versions are stored in `calibration_profiles` table:

```sql
calibration_profiles:
  profile_id: uuid
  scope: string  -- team / repo / service
  weights_json: jsonb
  warn_thresholds: jsonb
  block_thresholds: jsonb
  detector_ref: string
  updated_at: timestamp
```

### 5.4 Version Migration

When threshold version changes:

1. Save old version to `calibration_history`
2. Run replay evaluation on acceptance dataset
3. Compare metrics (precision, recall, F1)
4. If metrics degrade > 5%, require manual approval
5. Update active profile

**Migration validation criteria:**

| Metric | Allowed Change |
|---|---|
| Precision | -5% maximum |
| Recall (taboo) | -3% maximum |
| F1 | -5% maximum |
| False escalation | +5% maximum |

---

## 6. Replay Calibration

### 6.1 Replay Purpose

Replay calibration validates threshold changes against historical data:

- Verify new thresholds reproduce expected decisions
- Detect threshold drift
- Validate correction incorporation

### 6.2 Replay Command

```bash
harness gate replay --run-id RUN123 --threshold-version threshold-v1.0-20250115
```

### 6.3 Replay Procedure

```
1. Load historical run with state vector
2. Apply specified threshold_version
3. Re-compute scorer outputs (if scorer changed)
4. Re-apply composite decision logic
5. Compare replay decision to original decision
6. Record divergence with explanation
```

### 6.4 Replay Reproducibility Requirement

**Acceptance criterion: 99% identical decisions**

Divergence handling:

| Divergence Type | Action |
|---|---|
| Pass → Block | Requires Security review |
| Block → Pass | Requires justification + 2 approvers |
| Warn → Hold | Acceptable if within calibration tolerance |
| Hold → Pass | Requires reviewer confirmation |

### 6.5 Batch Replay for Threshold Validation

```bash
harness gate replay-batch --dataset acceptance_split.jsonl \
  --threshold-version threshold-v1.1-20250201 \
  --compare-with threshold-v1.0-20250115
```

Output includes divergence report and metric comparison.

---

## 7. Online Calibration

### 7.1 Correction-Driven Calibration

Human corrections feed into calibration:

| Correction Type | Calibration Effect |
|---|---|
| Pass → Block override | Add to rejected corpus, tighten thresholds |
| Block → Pass override | Add to accepted corpus, loosen thresholds |
| Threshold adjustment request | Direct threshold modification |
| Weight adjustment request | Profile weight update |

### 7.2 Correction Incorporation Flow

```
1. Reviewer decision recorded in human_reviews table
2. If override, artifact promoted to judgment_log axis
3. Periodic batch: re-embed promoted items
4. Trigger recalibration if:
   - Override count > threshold (e.g., 10 overrides)
   - Override rate > 5% in 7 days
   - Critical miss detected
5. Run offline calibration with new corpus
6. Validate, version, and deploy
```

### 7.3 Online Adjustment Limits

| Parameter | Max Adjustment | Adjustment Window |
|---|---|---|
| Threshold step | ±0.05 | Per correction batch |
| Weight step | ±0.02 | Per calibration cycle |
| Contamination | ±0.005 | Per anomaly recalibration |

### 7.4 Automatic Calibration Triggers

| Trigger | Condition | Action |
|---|---|---|
| Override surge | Override rate > 5% in 7 days | Schedule recalibration |
| Critical miss | Post-hoc critical found | Emergency threshold review |
| KPI degradation | Review load reduction < 20% | Analyze and adjust |
| Drift detection | Score distribution shift > 10% | Trigger drift recalibration |

---

## 8. Anomaly Detection Calibration

### 8.1 Isolation Forest Configuration

From `src/scorers/__init__.py`:

```python
class AnomalyScorer:
    def __init__(self, weight: float = 0.10, contamination: float = 0.01):
        self.weight = weight
        self.contamination = contamination
```

**Parameters:**

| Parameter | Default | Range | Description |
|---|---|---|---|
| contamination | 0.01 | 0.005 - 0.02 | Expected anomaly proportion |
| n_estimators | 100 | 50 - 200 | Number of trees |
| max_samples | 'auto' | 256 - 1024 | Samples per tree |

**Contamination calibration formula:**

```
contamination = anomaly_count / total_count
```

Recommended values:

| Environment | Contamination |
|---|---|
| Development | 0.02 (tolerant) |
| Staging | 0.01 (standard) |
| Production | 0.005 (conservative) |

### 8.2 Mahalanobis Distance Calibration

Mahalanobis distance requires covariance estimation from accepted corpus:

**Formula:**

```
d_mahal = sqrt((x - μ)^T × Σ^{-1} × (x - μ))
```

Where:
- `x`: Feature vector (delta_semantic, tool_calls, branch_count, step_count, error_rate)
- `μ`: Mean of accepted feature vectors
- `Σ`: Covariance matrix of accepted feature vectors

**Calibration procedure:**

```python
def calibrate_mahalanobis(accepted_features: List[List[float]]) -> Tuple:
    # Compute mean
    μ = mean(accepted_features, axis=0)

    # Compute covariance
    Σ = covariance(accepted_features)

    # Compute inverse (with regularization)
    Σ_inv = inverse(Σ + λI)  # λ for numerical stability

    # Compute distances for accepted set
    distances = [mahalanobis(f, μ, Σ_inv) for f in accepted_features]

    # Set thresholds from percentile
    warn_threshold = percentile(distances, 95)
    block_threshold = percentile(distances, 99)

    return μ, Σ_inv, warn_threshold, block_threshold
```

### 8.3 Feature Set for Anomaly Detection

| Feature | Source | Normalization |
|---|---|---|
| delta_semantic | Cosine distance between steps | min(abs(v) / 10, 1.0) |
| tool_calls | Step tool invocation count | min(v / 20, 1.0) |
| branch_count | Execution branch count | min(v / 5, 1.0) |
| step_count | Total steps in run | min(v / 50, 1.0) |
| error_rate | Tool/API error proportion | v (already normalized) |

### 8.4 Dual Anomaly Detection Strategy

| System | Method | Target Features | Use Case |
|---|---|---|---|
| Primary | Mahalanobis | semantic + risk + history + uncertainty | Dense representation anomaly |
| Secondary | Isolation Forest | trajectory + tool/use + rule delta | Sequence pattern anomaly |

---

## 9. Threshold Drift Detection

### 9.1 Distribution Drift Indicators

| Indicator | Formula | Alert Threshold |
|---|---|---|
| Score mean shift | `abs(μ_current - μ_baseline) / σ_baseline` | > 0.5 |
| Score variance shift | `σ_current / σ_baseline` | > 1.5 or < 0.67 |
| Threshold crossing rate | `cross_rate_current / cross_rate_baseline` | > 1.2 |
| Override rate | `overrides / total_decisions` | > 5% |

### 9.2 Drift Detection Procedure

```
1. Maintain baseline distribution from calibration
2. Compute rolling statistics on recent decisions (7-day window)
3. Compare current to baseline using indicators above
4. Alert if any indicator exceeds threshold
5. Recommend recalibration if drift confirmed
```

### 9.3 Drift Types and Responses

| Drift Type | Cause | Response |
|---|---|---|
| Score inflation | Model/embedding change | Re-embed corpus, recalibrate |
| Score deflation | Judgment KB growth | Add new exemplars, recalibrate |
| Threshold decay | Process/prompt changes | Review and adjust thresholds |
| Distribution shift | New artifact types | Extend KB, create new profile |

### 9.4 Monitoring Metrics

| Metric | Collection | Alert Window |
|---|---|---|
| Score distribution | Per decision | Rolling 7 days |
| Threshold crossing | Per decision | Rolling 7 days |
| Override rate | Per correction | Rolling 14 days |
| Miss rate | Post-hoc analysis | Rolling 30 days |

---

## 10. Calibration Schedule

### 10.1 Phase-Based Schedule

| Phase | Duration | Threshold Mode | Calibration Activity |
|---|---|---|---|
| Shadow | 2 weeks | Recording only | Collect distributions |
| Warn/Hold Enforce | 1 week | Warn/Hold active | Initial calibration, validate |
| Block Enforce | Ongoing | Full active | Periodic recalibration |

### 10.2 Recalibration Triggers

| Trigger | Priority | Timeframe |
|---|---|---|
| Critical miss detected | P0 | Immediate (within 24 hours) |
| Override surge (>5%) | P1 | Within 7 days |
| Distribution drift (>10%) | P1 | Within 7 days |
| Scheduled maintenance | P2 | Monthly |
| New scorer added | P1 | Before deployment |
| Embedding model change | P1 | Dual-write complete |

### 10.3 Scheduled Recalibration

| Schedule | Activity | Scope |
|---|---|---|
| Weekly | Distribution check | All thresholds |
| Monthly | Full recalibration | All profiles |
| Quarterly | Acceptance re-validation | Acceptance dataset |
| On-demand | Emergency recalibration | Affected axis only |

### 10.4 Calibration Checklist

Before threshold deployment:

| Item | Requirement |
|---|---|
| Sample size | Minimum samples met for all thresholds |
| Validation split | Tested on validation split, metrics recorded |
| Replay test | 99% reproducibility on acceptance split |
| Owner approval | Security + Ops approval documented |
| Version assigned | threshold_version recorded |
| Rollback plan | Previous version preserved |

### 10.5 Calibration Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    CALIBRATION WORKFLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Shadow Mode - 2 weeks]                                         │
│       │                                                          │
│       ▼                                                          │
│  Collect accepted/rejected distributions                         │
│       │                                                          │
│       ▼                                                          │
│  Compute initial thresholds (P95/P99)                            │
│       │                                                          │
│       ▼                                                          │
│  [Initial Calibration]                                           │
│       │                                                          │
│       ├──► Validate on calibration split                         │
│       │                                                          │
│       ├──► Confirm on validation split                           │
│       │                                                          │
│       ▼                                                          │
│  [Warn/Hold Enforce - 1 week]                                    │
│       │                                                          │
│       ▼                                                          │
│  Monitor KPIs                                                    │
│       │                                                          │
│       ├──► KPI met? ─► [Block Enforce]                           │
│       │                                                          │
│       ├──► KPI not met? ─► Extend shadow/warn                    │
│       │                                                          │
│       ▼                                                          │
│  [Ongoing Operation]                                             │
│       │                                                          │
│       ├──► Weekly: Distribution check                            │
│       │                                                          │
│       ├──► Trigger-based: Emergency recalibration                │
│       │                                                          │
│       ├──► Monthly: Full recalibration                           │
│       │                                                          │
│       ▼                                                          │
│  Human corrections → judgment_log → KB update                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix A: Threshold Configuration Schema

```yaml
thresholds:
  # Risk-side thresholds (higher = riskier)
  taboo_warn: 0.80          # Fixed fallback
  taboo_block: 0.88         # Fixed fallback
  taboo_warn_percentile: 95 # Percentile override
  taboo_block_percentile: 99

  reject_similarity_warn: 0.75
  reject_similarity_block: 0.85

  drift_warn_percentile: 95
  drift_block_percentile: 99

  anomaly_warn_percentile: 95  # Top 5%
  anomaly_block_percentile: 99 # Top 1%

  mahalanobis_warn_percentile: 95
  mahalanobis_block_percentile: 99

  judge_std_warn: 0.15
  judge_std_block: 0.25

  tool_failure_warn: 0.10
  tool_failure_block: 0.25

  # Safe-side thresholds (lower = riskier)
  constitution_alignment_warn_percentile: 5  # Lower 5%
  constitution_alignment_block_percentile: 1 # Lower 1%

hard_overrides:
  block_if_secret_found: true
  block_if_prod_write_and_taboo_warn: true
  hold_if_high_privilege_and_uncertain: true
```

---

## Appendix B: Calibration Profile JSON Schema

```json
{
  "profile_id": "uuid",
  "scope": "repo|team|service",
  "threshold_version": "threshold-v1.0-20250115",
  "weights": {
    "constitution_alignment": 0.20,
    "taboo_proximity": 0.30,
    "accept_similarity": 0.10,
    "reject_similarity": 0.15,
    "drift": 0.10,
    "anomaly": 0.10,
    "uncertainty": 0.05
  },
  "warn_thresholds": {
    "taboo": 0.80,
    "reject_similarity": 0.75,
    "drift": null,
    "anomaly_percentile": 95,
    "mahalanobis": null,
    "judge_std": 0.15,
    "tool_failure": 0.10
  },
  "block_thresholds": {
    "taboo": 0.88,
    "reject_similarity": 0.85,
    "drift": null,
    "anomaly_percentile": 99,
    "mahalanobis": null,
    "judge_std": 0.25,
    "tool_failure": 0.25
  },
  "anomaly_detector": {
    "type": "isolation_forest",
    "contamination": 0.01,
    "n_estimators": 100,
    "feature_set": ["delta_semantic", "tool_calls", "branch_count", "step_count", "error_rate"]
  },
  "mahalanobis_params": {
    "mean": [0.05, 8.0, 1.5, 20.0, 0.02],
    "covariance_inverse": "matrix_ref",
    "warn_distance": null,
    "block_distance": null
  },
  "calibration_metrics": {
    "sample_size": 500,
    "precision": 0.92,
    "recall": 0.91,
    "f1": 0.915,
    "false_escalation": 0.12
  },
  "updated_at": "2025-01-15T10:00:00Z"
}
```

---

## Appendix C: Threshold Calculation Formulas

### C.1 Percentile Threshold

```
threshold_p = sorted_scores[n × p / 100]
```

Where:
- `sorted_scores`: Ascending sorted score array
- `n`: Number of samples
- `p`: Percentile (95 for warn, 99 for block)

### C.2 Composite Score

```
composite = Σ(score_i × weight_i)

For risk-side scorers:  score_i = raw_score_i
For safe-side scorers:  contribution_i = 1 - raw_score_i (if threshold on lower bound)
```

### C.3 Mahalanobis Distance

```
d_mahal(x) = sqrt((x - μ)^T × Σ^{-1} × (x - μ))

anomaly_score = min(d_mahal / 10.0, 1.0)  # Normalized
```

### C.4 Drift Score

```
drift = 1 - cosine(current_vector, ewma_accepted)
```

EWMA update:

```
ewma_new = α × current + (1 - α) × ewma_old
```

Where `α = 0.1` (smoothing factor).

### C.5 Uncertainty Score

```
uncertainty = 0.25 × norm_judge_std
            + 0.25 × (1 - self_confidence)
            + 0.25 × tool_error_rate
            + 0.25 × evidence_gap
```

Each component normalized to [0, 1].

---

## References

- `docs/requirements.md`: Formal initial values and acceptance criteria
- `src/scorers/__init__.py`: Scorer weight defaults and implementation
- `src/core/calibration.py`: Calibration pipeline implementation
- `config/gate-config.yaml`: Configuration schema reference
