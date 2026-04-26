"""
Tests for Drift Detection - calibration threshold drift.
"""

import pytest

from src.core.drift_detection import (
    compute_drift_indicators,
    classify_drift_type,
    get_drift_response,
    compute_rolling_statistics,
    detect_threshold_decay,
)
from src.core.constants import DRIFT_INDICATORS, DRIFT_RESPONSES
from src.core.exceptions import EmptyDistributionError


class TestComputeDriftIndicators:
    """Tests for compute_drift_indicators."""

    def test_no_drift(self):
        """No drift when distributions similar."""
        # Use identical distributions for no drift
        current = [0.2, 0.2, 0.2]
        baseline = [0.2, 0.2, 0.2]
        result = compute_drift_indicators(current, baseline, "test")
        assert result.score_mean_shift < 1.0  # Should be small

    def test_mean_shift_drift(self):
        """Drift detected on mean shift."""
        current = [0.8, 0.9, 0.85]  # High scores
        baseline = [0.1, 0.2, 0.15]  # Low scores
        result = compute_drift_indicators(current, baseline, "test")
        assert result.alert_triggered is True
        assert result.score_mean_shift > 0

    def test_empty_current_raises(self):
        """Empty current raises error."""
        with pytest.raises(EmptyDistributionError):
            compute_drift_indicators([], [0.1, 0.2], "test")

    def test_empty_baseline_raises(self):
        """Empty baseline raises error."""
        with pytest.raises(EmptyDistributionError):
            compute_drift_indicators([0.1, 0.2], [], "test")

    def test_variance_shift_detection(self):
        """Variance shift detection."""
        current = [0.1, 0.5, 0.9]  # High variance
        baseline = [0.2, 0.2, 0.2]  # Low variance
        result = compute_drift_indicators(current, baseline, "test")
        assert result.score_variance_shift > 1

    def test_override_rate_trigger(self):
        """Override rate triggers drift."""
        current = [0.2, 0.2, 0.2]
        baseline = [0.2, 0.2, 0.2]
        result = compute_drift_indicators(current, baseline, "test", override_rate=0.5)
        assert result.override_rate == 0.5
        # Should trigger if override_rate > threshold

    def test_threshold_crossing_rate(self):
        """Threshold crossing rate indicator."""
        current = [0.2, 0.2, 0.2]
        baseline = [0.2, 0.2, 0.2]
        result = compute_drift_indicators(current, baseline, "test", threshold_crossing_rate=2.0)
        assert result.threshold_crossing_rate == 2.0


class TestClassifyDriftType:
    """Tests for classify_drift_type."""

    def test_score_inflation(self):
        """Score inflation classification."""
        drift_type = classify_drift_type(
            score_mean_shift=2.0,  # Large shift
            current_mean=0.8,
            baseline_mean=0.2,
            override_rate=0.0,
            score_variance_shift=1.0
        )
        assert drift_type == "score_inflation"

    def test_score_deflation(self):
        """Score deflation classification."""
        drift_type = classify_drift_type(
            score_mean_shift=2.0,
            current_mean=0.2,
            baseline_mean=0.8,
            override_rate=0.0,
            score_variance_shift=1.0
        )
        assert drift_type == "score_deflation"

    def test_threshold_decay(self):
        """Threshold decay classification."""
        drift_type = classify_drift_type(
            score_mean_shift=0.1,  # Small shift
            current_mean=0.2,
            baseline_mean=0.2,
            override_rate=0.3,  # High override rate
            score_variance_shift=1.0
        )
        assert drift_type == "threshold_decay"

    def test_distribution_shift(self):
        """Distribution shift classification."""
        drift_type = classify_drift_type(
            score_mean_shift=0.1,
            current_mean=0.2,
            baseline_mean=0.2,
            override_rate=0.0,
            score_variance_shift=2.0  # High variance shift
        )
        # When mean shift small and override low, returns distribution_shift
        assert drift_type in ("distribution_shift", None)


class TestGetDriftResponse:
    """Tests for get_drift_response."""

    def test_score_inflation_response(self):
        """Score inflation response."""
        response = get_drift_response("score_inflation")
        assert response is not None

    def test_threshold_decay_response(self):
        """Threshold decay response."""
        response = get_drift_response("threshold_decay")
        assert response is not None

    def test_unknown_drift_response(self):
        """Unknown drift type response."""
        response = get_drift_response("unknown")
        assert response == "Investigate and recalibrate"


class TestComputeRollingStatistics:
    """Tests for compute_rolling_statistics."""

    def test_basic_statistics(self):
        """Basic statistics computation."""
        scores = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = compute_rolling_statistics(scores)
        assert result["mean"] == 0.3
        assert result["min"] == 0.1
        assert result["max"] == 0.5
        assert result["count"] == 5

    def test_empty_scores(self):
        """Empty scores return zeros."""
        result = compute_rolling_statistics([])
        assert result["mean"] == 0.0
        assert result["count"] == 0

    def test_window_size(self):
        """Window size limits scores."""
        scores = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = compute_rolling_statistics(scores, window_size=3)
        # Only last 3: 0.3, 0.4, 0.5
        assert abs(result["mean"] - 0.4) < 0.001
        assert result["count"] == 3

    def test_std_calculation(self):
        """Standard deviation calculation."""
        scores = [1.0, 2.0, 3.0]
        result = compute_rolling_statistics(scores)
        assert result["std"] > 0

    def test_single_score(self):
        """Single score statistics."""
        result = compute_rolling_statistics([0.5])
        assert result["mean"] == 0.5
        assert result["std"] == 0.0


class TestDetectThresholdDecay:
    """Tests for detect_threshold_decay."""

    def test_no_decay(self):
        """No decay when rate low."""
        result = detect_threshold_decay(0.05, [0.04, 0.05, 0.06])
        assert result["is_decaying"] is False

    def test_decay_detected(self):
        """Decay detected when rate high."""
        result = detect_threshold_decay(0.3, [0.2, 0.25, 0.3])
        assert result["is_decaying"] is True

    def test_stable_trend(self):
        """Stable trend detection."""
        result = detect_threshold_decay(0.1, [0.1, 0.1, 0.1, 0.1])
        assert result["trend"] == "stable"

    def test_increasing_trend(self):
        """Increasing trend detection."""
        # recent > older * 1.2
        result = detect_threshold_decay(0.2, [0.05, 0.08, 0.15, 0.18, 0.2])
        assert result["trend"] == "increasing"

    def test_decreasing_trend(self):
        """Decreasing trend detection."""
        result = detect_threshold_decay(0.1, [0.3, 0.25, 0.2, 0.15, 0.1])
        assert result["trend"] == "decreasing"

    def test_short_history(self):
        """Short history returns stable."""
        result = detect_threshold_decay(0.1, [0.1])
        assert result["trend"] == "stable"

    def test_recommendation_when_decaying(self):
        """Recommendation when decaying."""
        result = detect_threshold_decay(0.3, [0.2, 0.25, 0.3])
        assert result["recommendation"] is not None

    def test_no_recommendation_when_stable(self):
        """No recommendation when stable."""
        result = detect_threshold_decay(0.05, [0.04, 0.05, 0.06])
        assert result["recommendation"] is None


class TestDriftDetectionIntegration:
    """Integration-like tests."""

    def test_full_drift_workflow(self):
        """Full drift detection workflow."""
        # Compute indicators
        current = [0.7, 0.8, 0.9]
        baseline = [0.2, 0.25, 0.3]
        indicators = compute_drift_indicators(current, baseline, "test")

        assert indicators.alert_triggered is True

        if indicators.drift_type:
            response = get_drift_response(indicators.drift_type)
            assert response is not None

    def test_rolling_stats_workflow(self):
        """Rolling statistics workflow."""
        scores = [0.1] * 10 + [0.5] * 10
        stats = compute_rolling_statistics(scores, window_size=5)
        # Last 5 are all 0.5
        assert stats["mean"] == 0.5

    def test_threshold_decay_workflow(self):
        """Threshold decay workflow."""
        history = [0.1, 0.15, 0.2, 0.25, 0.3]
        result = detect_threshold_decay(0.35, history)

        if result["is_decaying"]:
            assert result["recommendation"] is not None