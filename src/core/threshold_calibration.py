"""
Threshold calibration methods for percentile-based threshold calculation.

This module implements:
- Percentile-based threshold calculation (P95/P99)
- Taboo threshold calibration
- Drift threshold calibration
- Anomaly percentile calibration
- Constitution alignment threshold calibration
"""

from typing import Dict, Optional

from .constants import (
    MIN_SAMPLE_SIZES,
    DEFAULT_THRESHOLDS,
    PERCENTILE_DEFAULTS,
)
from .dataclasses import CalibrationResult
from .exceptions import InsufficientSamplesError


def calibrate_taboo_threshold(
    accepted_scores: list,
    rejected_scores: Optional[list] = None,
    percentile: int = 95
) -> CalibrationResult:
    """
    Set taboo threshold based on accepted distribution percentile.

    For risk-side scorers like taboo, higher scores are riskier.
    The threshold is set at the percentile of accepted distribution.

    Args:
        accepted_scores: List of scores from accepted samples
        rejected_scores: Optional list of scores from rejected samples (unused)
        percentile: Percentile to use for threshold (default 95)

    Returns:
        CalibrationResult with new threshold value

    Raises:
        ValueError: If insufficient samples provided
    """
    if len(accepted_scores) < MIN_SAMPLE_SIZES["taboo"]["accepted"]:
        raise InsufficientSamplesError(
            "taboo", len(accepted_scores), MIN_SAMPLE_SIZES["taboo"]["accepted"]
        )

    sorted_accepted = sorted(accepted_scores)
    idx = int(len(sorted_accepted) * percentile / 100)
    idx = min(idx, len(sorted_accepted) - 1)
    threshold = sorted_accepted[idx]

    return CalibrationResult(
        axis="taboo",
        old_threshold=0.0,
        new_threshold=threshold,
        sample_size=len(accepted_scores),
        metric_name=f"accepted_p{percentile}",
        metric_value=threshold
    )


def calibrate_drift_threshold(
    accepted_drift_scores: list,
    warn_percentile: int = 95,
    block_percentile: int = 99
) -> Dict[str, CalibrationResult]:
    """
    Calibrate drift thresholds from accepted distribution.

    Returns warn and block thresholds as separate results.

    Args:
        accepted_drift_scores: List of drift scores from accepted samples
        warn_percentile: Percentile for warn threshold (default 95)
        block_percentile: Percentile for block threshold (default 99)

    Returns:
        Dictionary with 'warn' and 'block' CalibrationResult entries

    Raises:
        ValueError: If insufficient samples provided
    """
    if len(accepted_drift_scores) < MIN_SAMPLE_SIZES["drift"]["accepted"]:
        raise InsufficientSamplesError(
            "drift", len(accepted_drift_scores), MIN_SAMPLE_SIZES["drift"]["accepted"]
        )

    sorted_scores = sorted(accepted_drift_scores)
    n = len(sorted_scores)

    warn_idx = int(n * warn_percentile / 100)
    warn_idx = min(warn_idx, n - 1)

    block_idx = int(n * block_percentile / 100)
    block_idx = min(block_idx, n - 1)

    warn_result = CalibrationResult(
        axis="drift",
        old_threshold=0.0,
        new_threshold=sorted_scores[warn_idx],
        sample_size=n,
        metric_name=f"accepted_p{warn_percentile}",
        metric_value=sorted_scores[warn_idx]
    )

    block_result = CalibrationResult(
        axis="drift",
        old_threshold=0.0,
        new_threshold=sorted_scores[block_idx],
        sample_size=n,
        metric_name=f"accepted_p{block_percentile}",
        metric_value=sorted_scores[block_idx]
    )

    return {"warn": warn_result, "block": block_result}


def calibrate_anomaly_percentile(
    anomaly_scores: list,
    warn_percentile: int = 95,
    block_percentile: int = 99
) -> Dict:
    """
    Set anomaly thresholds from contamination estimate.

    Uses percentile approach for Isolation Forest or other anomaly detectors.

    Args:
        anomaly_scores: List of anomaly scores from accepted samples
        warn_percentile: Percentile for warn threshold (default 95)
        block_percentile: Percentile for block threshold (default 99)

    Returns:
        Dictionary with threshold values and metadata

    Raises:
        ValueError: If insufficient samples provided
    """
    if len(anomaly_scores) < MIN_SAMPLE_SIZES["anomaly"]["accepted"]:
        raise InsufficientSamplesError(
            "anomaly", len(anomaly_scores), MIN_SAMPLE_SIZES["anomaly"]["accepted"]
        )

    sorted_scores = sorted(anomaly_scores)
    n = len(sorted_scores)

    warn_idx = int(n * warn_percentile / 100)
    warn_idx = min(warn_idx, n - 1)

    block_idx = int(n * block_percentile / 100)
    block_idx = min(block_idx, n - 1)

    return {
        "warn_threshold": sorted_scores[warn_idx],
        "block_threshold": sorted_scores[block_idx],
        "warn_percentile": warn_percentile,
        "block_percentile": block_percentile,
        "sample_size": n
    }


def calibrate_constitution_threshold(
    accepted_scores: list,
    warn_percentile: int = 5,
    block_percentile: int = 1
) -> Dict[str, CalibrationResult]:
    """
    Calibrate constitution alignment threshold (safe-side scorer).

    For safe-side scorers, lower scores are riskier.
    The threshold is set on the lower bound of accepted distribution.

    Args:
        accepted_scores: List of constitution alignment scores from accepted samples
        warn_percentile: Percentile for warn threshold (default 5, lower bound)
        block_percentile: Percentile for block threshold (default 1, lower bound)

    Returns:
        Dictionary with 'warn' and 'block' CalibrationResult entries
    """
    sorted_scores = sorted(accepted_scores)
    n = len(sorted_scores)

    warn_idx = int(n * warn_percentile / 100)
    warn_idx = max(0, min(warn_idx, n - 1))

    block_idx = int(n * block_percentile / 100)
    block_idx = max(0, min(block_idx, n - 1))

    return {
        "warn": CalibrationResult(
            axis="constitution_alignment",
            old_threshold=0.0,
            new_threshold=sorted_scores[warn_idx],
            sample_size=n,
            metric_name=f"accepted_p{warn_percentile}",
            metric_value=sorted_scores[warn_idx]
        ),
        "block": CalibrationResult(
            axis="constitution_alignment",
            old_threshold=0.0,
            new_threshold=sorted_scores[block_idx],
            sample_size=n,
            metric_name=f"accepted_p{block_percentile}",
            metric_value=sorted_scores[block_idx]
        )
    }


def get_percentile_value(scores: list, percentile: int) -> float:
    """
    Get value at specified percentile from sorted scores.

    Args:
        scores: List of scores (will be sorted)
        percentile: Percentile to retrieve (0-100)

    Returns:
        Value at the specified percentile
    """
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    idx = int(n * percentile / 100)
    idx = max(0, min(idx, n - 1))
    return sorted_scores[idx]


def get_effective_threshold(
    percentile_threshold: Optional[float],
    fixed_threshold: Optional[float],
    is_risk_side: bool = True
) -> Optional[float]:
    """
    Get effective threshold combining percentile and fixed thresholds.

    For risk-side (higher = riskier): use min(percentile, fixed)
    For safe-side (lower = riskier): use max(percentile, fixed)

    Args:
        percentile_threshold: Threshold from percentile calculation
        fixed_threshold: Fixed threshold value
        is_risk_side: True for risk-side scorers, False for safe-side

    Returns:
        Effective threshold value, or None if both inputs are None
    """
    if percentile_threshold is None and fixed_threshold is None:
        return None

    if percentile_threshold is None:
        return fixed_threshold
    if fixed_threshold is None:
        return percentile_threshold

    if is_risk_side:
        return min(percentile_threshold, fixed_threshold)
    else:
        return max(percentile_threshold, fixed_threshold)