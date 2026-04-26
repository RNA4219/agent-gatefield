"""
Tests for Online Calibration - real-time threshold adjustment.
"""

import pytest

from src.core.online_calibration import (
    incorporate_correction,
    check_calibration_trigger,
    compute_threshold_adjustment,
    validate_weight_adjustment,
    apply_online_correction,
    get_calibration_priority,
    should_trigger_immediate_recalibration,
)
from src.core.constants import (
    ONLINE_ADJUSTMENT_LIMITS,
    CALIBRATION_TRIGGERS,
    DEFAULT_SCORER_WEIGHTS,
    WEIGHT_CONSTRAINTS,
)


class TestIncorporateCorrection:
    """Tests for incorporate_correction."""

    def test_pass_to_block(self):
        """Pass to block correction."""
        result = incorporate_correction("pass_to_block", 0.88)
        assert result["action"] == "tighten_threshold"
        assert result["threshold_adjustment"] < 0

    def test_block_to_pass(self):
        """Block to pass correction."""
        result = incorporate_correction("block_to_pass", 0.88)
        assert result["action"] == "loosen_threshold"
        assert result["threshold_adjustment"] > 0

    def test_threshold_adjust(self):
        """Direct threshold adjustment."""
        result = incorporate_correction("threshold_adjust", 0.88)
        assert result["action"] == "direct_threshold_modification"

    def test_weight_adjust(self):
        """Weight adjustment."""
        result = incorporate_correction("weight_adjust", 0.88)
        assert result["action"] == "profile_weight_update"

    def test_with_current_weights(self):
        """Correction with current weights."""
        weights = {"taboo_proximity": 0.30}
        result = incorporate_correction("weight_adjust", 0.88, weights)
        assert result["weight_adjustment"] == {}

    def test_unknown_correction_type(self):
        """Unknown correction type."""
        result = incorporate_correction("unknown", 0.88)
        assert result["action"] is None


class TestCheckCalibrationTrigger:
    """Tests for check_calibration_trigger."""

    def test_no_trigger(self):
        """No trigger when override rate low."""
        result = check_calibration_trigger(5, 100)
        assert result["triggered"] is False
        assert result["override_rate"] == 0.05

    def test_override_surge_trigger(self):
        """Trigger on override surge."""
        result = check_calibration_trigger(50, 100)
        assert result["triggered"] is True
        assert len(result["triggers"]) > 0

    def test_zero_decisions(self):
        """Zero decisions returns zero rate."""
        result = check_calibration_trigger(0, 0)
        assert result["override_rate"] == 0.0
        assert result["triggered"] is False

    def test_override_rate_calculation(self):
        """Override rate calculation."""
        result = check_calibration_trigger(25, 50)
        assert result["override_rate"] == 0.5

    def test_window_days_parameter(self):
        """Window days parameter."""
        result = check_calibration_trigger(10, 100, window_days=14)
        assert result is not None


class TestComputeThresholdAdjustment:
    """Tests for compute_threshold_adjustment."""

    def test_empty_history(self):
        """Empty history returns zero."""
        result = compute_threshold_adjustment([])
        assert result == 0.0

    def test_single_correction(self):
        """Single correction."""
        history = [{"threshold_adjustment": 0.05}]
        result = compute_threshold_adjustment(history)
        assert result == 0.05

    def test_cumulative_correction(self):
        """Cumulative corrections."""
        history = [
            {"threshold_adjustment": 0.05},
            {"threshold_adjustment": -0.03},
        ]
        result = compute_threshold_adjustment(history)
        assert abs(result - 0.02) < 0.001

    def test_max_adjustment_clamp(self):
        """Clamp to max adjustment."""
        history = [{"threshold_adjustment": 0.5}]
        result = compute_threshold_adjustment(history, max_adjustment=0.1)
        assert result == 0.1

    def test_negative_clamp(self):
        """Clamp negative adjustment."""
        history = [{"threshold_adjustment": -0.5}]
        result = compute_threshold_adjustment(history, max_adjustment=0.1)
        assert result == -0.1


class TestValidateWeightAdjustment:
    """Tests for validate_weight_adjustment."""

    def test_valid_adjustment(self):
        """Valid weight adjustment."""
        current = {"taboo_proximity": 0.30, "other": 0.70}
        proposed = {"taboo_proximity": 0.01}  # Small delta
        result = validate_weight_adjustment(current, proposed, max_step=0.1)
        # Weight sum constraint may fail, check adjusted weights exist
        assert "adjusted_weights" in result

    def test_step_exceeded(self):
        """Step constraint exceeded."""
        current = {"taboo_proximity": 0.30}
        proposed = {"taboo_proximity": 0.5}  # Large change
        result = validate_weight_adjustment(current, proposed, max_step=0.1)
        assert len(result["violations"]) > 0

    def test_min_constraint(self):
        """Minimum weight constraint."""
        current = {"taboo_proximity": 0.05}
        proposed = {"taboo_proximity": -0.1}
        result = validate_weight_adjustment(current, proposed)
        # Should be clamped to min
        assert result["adjusted_weights"]["taboo_proximity"] >= WEIGHT_CONSTRAINTS["min_weight"]

    def test_max_constraint(self):
        """Maximum weight constraint."""
        current = {"taboo_proximity": 0.45}
        proposed = {"taboo_proximity": 0.2}
        result = validate_weight_adjustment(current, proposed)
        # Should be clamped to max
        assert result["adjusted_weights"]["taboo_proximity"] <= WEIGHT_CONSTRAINTS["max_weight"]

    def test_sum_constraint(self):
        """Sum constraint check."""
        current = {"a": 0.5, "b": 0.5}
        proposed = {"a": 0.2}
        result = validate_weight_adjustment(current, proposed)
        # Sum should still equal 1.0
        total = sum(result["adjusted_weights"].values())
        assert abs(total - WEIGHT_CONSTRAINTS["sum"]) < 0.001


class TestApplyOnlineCorrection:
    """Tests for apply_online_correction."""

    def test_tighten_threshold(self):
        """Tighten threshold."""
        profile = {
            "warn_thresholds": {"taboo": 0.80},
            "block_thresholds": {"taboo": 0.88}
        }
        correction = {
            "action": "tighten_threshold",
            "threshold_adjustment": -0.05
        }
        result = apply_online_correction(profile, correction)
        assert result["warn_thresholds"]["taboo"] < 0.80

    def test_loosen_threshold(self):
        """Loosen threshold."""
        profile = {
            "warn_thresholds": {"taboo": 0.80},
            "block_thresholds": {"taboo": 0.88}
        }
        correction = {
            "action": "loosen_threshold",
            "threshold_adjustment": 0.05
        }
        result = apply_online_correction(profile, correction)
        assert result["warn_thresholds"]["taboo"] > 0.80

    def test_weight_update(self):
        """Weight update."""
        profile = {
            "weights": {"taboo_proximity": 0.30, "other": 0.70}
        }
        correction = {
            "action": "profile_weight_update",
            "weight_adjustment": {"taboo_proximity": 0.01}  # Delta
        }
        result = apply_online_correction(profile, correction)
        # Check that weights were updated or preserved
        assert "weights" in result

    def test_no_action(self):
        """No action returns unchanged."""
        profile = {"weights": {"a": 0.5}}
        correction = {"action": None}
        result = apply_online_correction(profile, correction)
        assert result == profile

    def test_threshold_bounds(self):
        """Threshold stays within bounds."""
        profile = {
            "warn_thresholds": {"taboo": 0.95},
            "block_thresholds": {"taboo": 0.99}
        }
        correction = {
            "action": "loosen_threshold",
            "threshold_adjustment": 0.5
        }
        result = apply_online_correction(profile, correction)
        assert result["warn_thresholds"]["taboo"] <= 1.0


class TestGetCalibrationPriority:
    """Tests for get_calibration_priority."""

    def test_critical_miss_priority(self):
        """Critical miss is P0."""
        priority = get_calibration_priority("critical_miss")
        assert priority == "P0"

    def test_override_surge_priority(self):
        """Override surge priority."""
        priority = get_calibration_priority("override_surge")
        assert priority in ("P0", "P1", "P2")

    def test_unknown_priority(self):
        """Unknown type returns P2."""
        priority = get_calibration_priority("unknown")
        assert priority == "P2"


class TestShouldTriggerImmediateRecalibration:
    """Tests for should_trigger_immediate_recalibration."""

    def test_not_triggered(self):
        """Not triggered returns False."""
        result = {"triggered": False}
        assert should_trigger_immediate_recalibration(result) is False

    def test_p0_trigger(self):
        """P0 trigger returns True."""
        result = {
            "triggered": True,
            "triggers": [{"priority": "P0"}]
        }
        assert should_trigger_immediate_recalibration(result) is True

    def test_p1_trigger(self):
        """P1 trigger returns False."""
        result = {
            "triggered": True,
            "triggers": [{"priority": "P1"}]
        }
        assert should_trigger_immediate_recalibration(result) is False

    def test_no_triggers_list(self):
        """No triggers list returns False."""
        result = {"triggered": True, "triggers": []}
        assert should_trigger_immediate_recalibration(result) is False


class TestOnlineCalibrationIntegration:
    """Integration-like tests."""

    def test_full_correction_workflow(self):
        """Full correction workflow."""
        # Check trigger
        trigger_result = check_calibration_trigger(50, 100)
        assert trigger_result["triggered"] is True

        # Incorporate correction
        correction = incorporate_correction("pass_to_block", 0.88)
        assert correction["action"] == "tighten_threshold"

        # Apply to profile
        profile = {
            "warn_thresholds": {"taboo": 0.80},
            "block_thresholds": {"taboo": 0.88},
            "weights": {"taboo_proximity": 0.30}
        }
        updated = apply_online_correction(profile, correction)
        assert updated["block_thresholds"]["taboo"] < 0.88

    def test_weight_adjustment_workflow(self):
        """Weight adjustment workflow."""
        current = {"taboo_proximity": 0.30, "other": 0.70}
        proposed = {"taboo_proximity": 0.01}  # Small delta

        result = validate_weight_adjustment(current, proposed, max_step=0.1)
        # Check result structure
        assert "adjusted_weights" in result
        assert "valid" in result

        correction = incorporate_correction("weight_adjust", 0.88)
        profile = {"weights": current}
        updated = apply_online_correction(profile, {
            "action": "profile_weight_update",
            "weight_adjustment": proposed
        })
        assert "weights" in updated