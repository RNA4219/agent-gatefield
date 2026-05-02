"""
Calibration utility functions.

Helper functions for EWMA calculations and uncertainty scoring.
"""


def calculate_ewma(current_value: float, old_ewma: float, alpha: float = 0.1) -> float:
    """
    Calculate Exponentially Weighted Moving Average.

    Used for drift score calculation.

    Args:
        current_value: Current observation
        old_ewma: Previous EWMA value
        alpha: Smoothing factor (default 0.1)

    Returns:
        Updated EWMA value
    """
    return alpha * current_value + (1 - alpha) * old_ewma


def calculate_uncertainty_score(
    judge_std: float,
    self_confidence: float,
    tool_error_rate: float,
    evidence_gap: float
) -> float:
    """
    Calculate uncertainty score from components.

    Formula: uncertainty = 0.25 * norm_judge_std
                       + 0.25 * (1 - self_confidence)
                       + 0.25 * tool_error_rate
                       + 0.25 * evidence_gap

    All components should be normalized to [0, 1].

    Args:
        judge_std: Judge standard deviation (normalized)
        self_confidence: Self-confidence score (0-1)
        tool_error_rate: Tool error rate (0-1)
        evidence_gap: Evidence gap score (0-1)

    Returns:
        Combined uncertainty score
    """
    return (
        0.25 * judge_std +
        0.25 * (1 - self_confidence) +
        0.25 * tool_error_rate +
        0.25 * evidence_gap
    )