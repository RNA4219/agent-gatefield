"""
Drift detection for calibration thresholds.

This module implements:
- Drift indicator computation
- Drift type classification
- Drift response recommendations
- Baseline distribution comparison
"""

from typing import Dict, Optional
import math

from .constants import (
    DRIFT_INDICATORS,
    DRIFT_RESPONSES,
)
from .dataclasses import DriftIndicators
from .exceptions import EmptyDistributionError


def compute_drift_indicators(
    current_scores: list,
    baseline_scores: list,
    axis: str,
    override_rate: float = 0.0,
    threshold_crossing_rate: float = 1.0
) -> DriftIndicators:
    """
    Compute drift indicators comparing current to baseline distribution.

    Calculates:
    - Score mean shift: |mu_current - mu_baseline| / sigma_baseline
    - Score variance shift: sigma_current / sigma_baseline
    - Threshold crossing rate ratio
    - Override rate

    Args:
        current_scores: Recent score distribution
        baseline_scores: Calibration baseline distribution
        axis: Scorer axis name
        override_rate: Current override rate
        threshold_crossing_rate: Ratio of current/baseline crossing rates

    Returns:
        DriftIndicators with computed metrics and alert status

    Raises:
        ValueError: If either score list is empty
    """
    if not current_scores or not baseline_scores:
        raise EmptyDistributionError("current or baseline")

    # Compute baseline statistics
    baseline_mean = sum(baseline_scores) / len(baseline_scores)
    baseline_var = sum((s - baseline_mean) ** 2 for s in baseline_scores) / len(baseline_scores)
    baseline_std = math.sqrt(baseline_var) if baseline_var > 0 else 1e-10

    # Compute current statistics
    current_mean = sum(current_scores) / len(current_scores)
    current_var = sum((s - current_mean) ** 2 for s in current_scores) / len(current_scores)
    current_std = math.sqrt(current_var) if current_var > 0 else 1e-10

    # Compute drift indicators
    score_mean_shift = abs(current_mean - baseline_mean) / baseline_std
    score_variance_shift = current_std / baseline_std if baseline_std > 0 else float('inf')

    # Determine if alert should be triggered
    alert_triggered = (
        score_mean_shift > DRIFT_INDICATORS["score_mean_shift"] or
        score_variance_shift > DRIFT_INDICATORS["score_variance_shift_high"] or
        score_variance_shift < DRIFT_INDICATORS["score_variance_shift_low"] or
        threshold_crossing_rate > DRIFT_INDICATORS["threshold_crossing_rate"] or
        override_rate > DRIFT_INDICATORS["override_rate"]
    )

    # Determine drift type
    drift_type = None
    if alert_triggered:
        drift_type = classify_drift_type(
            score_mean_shift,
            current_mean,
            baseline_mean,
            override_rate,
            score_variance_shift
        )

    return DriftIndicators(
        score_mean_shift=score_mean_shift,
        score_variance_shift=score_variance_shift,
        threshold_crossing_rate=threshold_crossing_rate,
        override_rate=override_rate,
        alert_triggered=alert_triggered,
        drift_type=drift_type
    )


def classify_drift_type(
    score_mean_shift: float,
    current_mean: float,
    baseline_mean: float,
    override_rate: float,
    score_variance_shift: float
) -> Optional[str]:
    """
    Classify the type of drift based on indicators.

    Drift types:
    - score_inflation: Mean has increased significantly
    - score_deflation: Mean has decreased significantly
    - threshold_decay: Override rate is high
    - distribution_shift: Variance or other changes

    Args:
        score_mean_shift: Normalized mean shift value
        current_mean: Current distribution mean
        baseline_mean: Baseline distribution mean
        override_rate: Override rate
        score_variance_shift: Variance ratio

    Returns:
        Drift type string or None if no significant drift
    """
    if score_mean_shift > DRIFT_INDICATORS["score_mean_shift"]:
        return "score_inflation" if current_mean > baseline_mean else "score_deflation"
    elif override_rate > DRIFT_INDICATORS["override_rate"]:
        return "threshold_decay"
    else:
        return "distribution_shift"


def get_drift_response(drift_type: str) -> str:
    """
    Get recommended response for a drift type.

    Args:
        drift_type: Type of drift detected

    Returns:
        Recommended response action
    """
    return DRIFT_RESPONSES.get(drift_type, "Investigate and recalibrate")


def compute_rolling_statistics(
    scores: list,
    window_size: Optional[int] = None
) -> Dict[str, float]:
    """
    Compute rolling statistics for a score distribution.

    Args:
        scores: List of scores
        window_size: Optional window size for rolling calculation

    Returns:
        Dictionary with mean, std, min, max, count
    """
    if not scores:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "count": 0}

    if window_size and len(scores) > window_size:
        scores = scores[-window_size:]

    n = len(scores)
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / n
    std = math.sqrt(variance) if variance > 0 else 0.0

    return {
        "mean": mean,
        "std": std,
        "min": min(scores),
        "max": max(scores),
        "count": n
    }


def detect_threshold_decay(
    override_rate: float,
    override_history: list,
    window_days: int = 7
) -> Dict[str, any]:
    """
    Detect if thresholds are decaying based on override patterns.

    Args:
        override_rate: Current override rate
        override_history: List of historical override rates
        window_days: Number of days in the analysis window

    Returns:
        Dictionary with decay status and recommendations
    """
    is_decaying = override_rate > DRIFT_INDICATORS["override_rate"]

    trend = "stable"
    if len(override_history) >= 3:
        recent_avg = sum(override_history[-3:]) / 3
        older_avg = sum(override_history[:-3]) / len(override_history[:-3]) if len(override_history) > 3 else recent_avg

        if recent_avg > older_avg * 1.2:
            trend = "increasing"
        elif recent_avg < older_avg * 0.8:
            trend = "decreasing"

    return {
        "is_decaying": is_decaying,
        "override_rate": override_rate,
        "threshold": DRIFT_INDICATORS["override_rate"],
        "trend": trend,
        "recommendation": get_drift_response("threshold_decay") if is_decaying else None
    }