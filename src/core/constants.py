"""
Calibration constants for agent-gatefield state space gate system.

This module contains all constants related to:
- Scorer weight defaults and constraints
- Threshold defaults and percentile settings
- Anomaly detection configuration
- Drift detection thresholds
- Migration validation criteria
- Online calibration limits and triggers
"""

from typing import Dict, List, Any, Callable, Optional


# =============================================================================
# Scorer Weight Constants (Section 1.1)
# =============================================================================

# Default weights for composite score calculation
DEFAULT_SCORER_WEIGHTS: Dict[str, float] = {
    "constitution_alignment": 0.20,  # Measures alignment with design principles
    "taboo_proximity": 0.30,         # Detects proximity to forbidden patterns
    "accept_similarity": 0.10,      # Positive signal: similarity to accepted examples
    "reject_similarity": 0.15,      # Negative signal: similarity to rejected examples
    "drift": 0.10,                  # Deviation from accepted trajectory baseline
    "anomaly": 0.10,                # Out-of-distribution detection
    "uncertainty": 0.05,            # Combined uncertainty factors
}

# Weight constraints
WEIGHT_CONSTRAINTS: Dict[str, float] = {
    "min_weight": 0.05,              # Minimum meaningful contribution
    "max_weight": 0.50,              # Prevent single scorer dominance
    "sum": 1.00,                     # Must sum to 1.00
    "taboo_min_weight": 0.25,        # Minimum for safety-critical projects
    "uncertainty_fixed": 0.05,       # Fixed to ensure escalation path
}


# =============================================================================
# Threshold Constants (Section 3.1)
# =============================================================================

# Initial threshold values for production deployment
DEFAULT_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    # Risk-side thresholds (higher = riskier)
    "taboo": {"warn": 0.80, "block": 0.88},
    "reject_similarity": {"warn": 0.75, "block": 0.85},
    "drift": {"warn": None, "block": None},  # Percentile-based
    "anomaly_percentile": {"warn": 95, "block": 99},
    "mahalanobis": {"warn": None, "block": None},  # Percentile-based
    "judge_std": {"warn": 0.15, "block": 0.25},
    "tool_failure": {"warn": 0.10, "block": 0.25},
    # Safe-side thresholds (lower = riskier)
    "constitution_alignment": {"warn_percentile": 5, "block_percentile": 1},
    # Additional thresholds used by engine
    "direction": {"block": -0.50, "warn": -0.20},
}

# Flat threshold constants for direct access
THRESHOLD_TABOO_WARN = 0.80
THRESHOLD_TABOO_BLOCK = 0.88
THRESHOLD_REJECT_WARN = 0.75
THRESHOLD_REJECT_BLOCK = 0.85
THRESHOLD_JUDGE_STD_WARN = 0.15
THRESHOLD_JUDGE_STD_BLOCK = 0.25
THRESHOLD_TOOL_FAILURE_WARN = 0.10
THRESHOLD_TOOL_FAILURE_BLOCK = 0.25
THRESHOLD_DIRECTION_BLOCK = -0.50
THRESHOLD_DIRECTION_WARN = -0.20
THRESHOLD_ANOMALY_BLOCK = 0.99
THRESHOLD_ANOMALY_WARN = 0.95
THRESHOLD_ANOMALY_SELF_CORRECT = 0.90
THRESHOLD_COMPOSITE_WARN = 0.70

# Percentile defaults
PERCENTILE_DEFAULTS: Dict[str, int] = {
    "warn": 95,
    "block": 99,
}

# Minimum sample sizes for calibration (Section 4.5)
MIN_SAMPLE_SIZES: Dict[str, Dict[str, Optional[int]]] = {
    "taboo": {"accepted": 100, "rejected": 50},
    "drift": {"accepted": 50, "rejected": 20},
    "anomaly": {"accepted": 200, "rejected": None},
    "accept_reject_separation": {"accepted": 200, "rejected": 100},
}


# =============================================================================
# Anomaly Detection Constants (Section 8)
# =============================================================================

# Isolation Forest defaults
ISOLATION_FOREST_DEFAULTS: Dict[str, Any] = {
    "contamination": 0.01,
    "contamination_range": (0.005, 0.02),
    "n_estimators": 100,
    "n_estimators_range": (50, 200),
    "max_samples": "auto",
    "max_samples_range": (256, 1024),
}

# Contamination by environment
CONTAMINATION_BY_ENV: Dict[str, float] = {
    "development": 0.02,   # Tolerant
    "staging": 0.01,       # Standard
    "production": 0.005,   # Conservative
}

# Feature set for anomaly detection
ANOMALY_FEATURES: List[str] = ["delta_semantic", "tool_calls", "branch_count", "step_count", "error_rate"]

# Feature normalization functions
FEATURE_NORMALIZATION: Dict[str, Callable[[float], float]] = {
    "delta_semantic": lambda v: min(abs(v) / 10.0, 1.0),
    "tool_calls": lambda v: min(v / 20.0, 1.0),
    "branch_count": lambda v: min(v / 5.0, 1.0),
    "step_count": lambda v: min(v / 50.0, 1.0),
    "error_rate": lambda v: v,  # Already normalized
}


# =============================================================================
# Drift Detection Constants (Section 9)
# =============================================================================

# Drift indicator thresholds
DRIFT_INDICATORS: Dict[str, float] = {
    "score_mean_shift": 0.5,       # |mu_current - mu_baseline| / sigma_baseline
    "score_variance_shift_high": 1.5,  # sigma_current / sigma_baseline
    "score_variance_shift_low": 0.67,
    "threshold_crossing_rate": 1.2,
    "override_rate": 0.05,
}

# Drift response types
DRIFT_RESPONSES: Dict[str, str] = {
    "score_inflation": "Re-embed corpus, recalibrate",
    "score_deflation": "Add new exemplars, recalibrate",
    "threshold_decay": "Review and adjust thresholds",
    "distribution_shift": "Extend KB, create new profile",
}


# =============================================================================
# Migration and Version Constants (Section 5)
# =============================================================================

# Migration validation criteria
MIGRATION_CRITERIA: Dict[str, float] = {
    "precision_max_degradation": 0.05,    # -5% maximum
    "recall_max_degradation": 0.03,       # -3% maximum (taboo)
    "f1_max_degradation": 0.05,           # -5% maximum
    "false_escalation_max_increase": 0.05,  # +5% maximum
}

# Reproducibility requirement
REPRODUCIBILITY_TARGET: float = 0.99  # 99% identical decisions


# =============================================================================
# Online Calibration Constants (Section 7)
# =============================================================================

# Online adjustment limits
ONLINE_ADJUSTMENT_LIMITS: Dict[str, float] = {
    "threshold_step": 0.05,      # Max adjustment per correction batch
    "weight_step": 0.02,        # Max adjustment per calibration cycle
    "contamination_step": 0.005,  # Max adjustment per anomaly recalibration
}

# Automatic calibration triggers
CALIBRATION_TRIGGERS: Dict[str, Any] = {
    "override_surge_rate": 0.05,    # Override rate > 5% in 7 days
    "override_surge_window_days": 7,
    "critical_miss_priority": "P0",
    "override_surge_priority": "P1",
    "drift_detection_priority": "P1",
    "scheduled_maintenance_priority": "P2",
}


# =============================================================================
# SLA Constants (AGF-REQ-008)
# =============================================================================

# SLA timeout targets by severity (minutes)
SLA_TARGETS: Dict[str, Dict[str, int]] = {
    "critical": {"ack": 15, "decision": 60},
    "high": {"ack": 60, "decision": 240},
    "medium": {"ack": None, "decision": None},  # Same business day
    "low": {"ack": None, "decision": None},     # Backlog
}

# SLA escalation thresholds
SLA_ESCALATION: Dict[str, Any] = {
    "ack_warning_ratio": 0.75,  # Warn at 75% of SLA
    "decision_warning_ratio": 0.75,
    "fail_closed": True,        # Block on timeout
}


# =============================================================================
# Gate State Constants (AGF-REQ-004)
# =============================================================================

# Valid gate states
GATE_STATES: List[str] = ["pass", "warn", "hold", "block"]

# State transition rules
STATE_TRANSITIONS: Dict[str, Dict[str, Any]] = {
    "pass": {"next": ["warn", "hold", "block"], "action": "continue"},
    "warn": {"next": ["pass", "hold", "block"], "action": "self_correction", "max_loops": 2},
    "hold": {"next": ["pass", "block"], "action": "human_review"},
    "block": {"next": [], "action": "correction_required"},
}

# Hard override identifiers
HARD_OVERRIDE_IDS: Dict[str, str] = {
    "HO01": "secret_found",
    "HO02": "prod_write_taboo",
    "HO03": "high_privilege_uncertain",
    "HO04": "sast_high",
    "HO05": "tool_policy_deny",
}


# =============================================================================
# Action Type Constants
# =============================================================================

# Valid action types
ACTION_TYPES: List[str] = [
    "continue",
    "self_correction",
    "hold_for_review",
    "artifact_correction",
    "process_correction",
]

# Action mapping by state
ACTION_BY_STATE: Dict[str, str] = {
    "pass": "continue",
    "warn": "self_correction",
    "hold": "hold_for_review",
    "block": "artifact_correction",
}


# =============================================================================
# Severity Constants
# =============================================================================

# Valid severity levels
SEVERITY_LEVELS: List[str] = ["critical", "high", "medium", "low"]

# Severity priority (higher = more urgent)
SEVERITY_PRIORITY: Dict[str, int] = {
    "critical": 100,
    "high": 75,
    "medium": 50,
    "low": 25,
}


# =============================================================================
# Data Classification Constants (AGF-REQ-006)
# =============================================================================

# Valid data classifications
DATA_CLASSIFICATIONS: List[str] = [
    "public",
    "internal",
    "confidential",
    "pii-sensitive",
    "restricted",
]

# Retention classes
RETENTION_CLASSES: List[str] = ["audit", "ops", "pii-sensitive"]

# Redaction status
REDACTION_STATUS: List[str] = ["full", "partial", "none"]


# =============================================================================
# Schema Version Constants (AGF-REQ-007)
# =============================================================================

SCHEMA_VERSION: str = "1.0.0"
ENCODER_VERSION: str = "encoder-v1.0.0"


# =============================================================================
# KPI Target Constants (AGF-REQ-008)
# =============================================================================

KPI_TARGETS: Dict[str, float] = {
    "review_load_reduction": 0.30,  # 30%+ reduction
    "critical_miss_rate": 0.0,      # 0% (zero tolerance)
    "high_miss_rate": 0.05,         # 5% max
    "false_escalation_rate": 0.15,  # 15% max
    "replay_reproducibility": 0.99, # 99%+
    "taboo_recall": 0.90,           # 90%+
    "auc": 0.85,                    # 0.85+
    "pr_auc": 0.80,                 # 0.80+ (alternative)
}