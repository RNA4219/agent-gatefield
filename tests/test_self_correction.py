"""
Tests for Self-Correction Loop Tracking - escalation logic.
"""

import pytest

from src.core.self_correction import (
    SelfCorrectionTracker,
    track_self_correction,
    check_persistent_factor_escalation,
)


class TestSelfCorrectionTrackerInit:
    """Tests for SelfCorrectionTracker initialization."""

    def test_default_init(self):
        tracker = SelfCorrectionTracker()
        assert tracker.max_loops == 2
        assert tracker.persistent_threshold == 3

    def test_custom_max_loops(self):
        tracker = SelfCorrectionTracker(max_loops=5)
        assert tracker.max_loops == 5
        assert tracker.persistent_threshold == 3

    def test_custom_persistent_threshold(self):
        tracker = SelfCorrectionTracker(persistent_threshold=5)
        assert tracker.max_loops == 2
        assert tracker.persistent_threshold == 5

    def test_custom_both(self):
        tracker = SelfCorrectionTracker(max_loops=3, persistent_threshold=4)
        assert tracker.max_loops == 3
        assert tracker.persistent_threshold == 4


class TestTrackIteration:
    """Tests for track_iteration method."""

    def test_first_iteration_no_escalate(self):
        tracker = SelfCorrectionTracker()
        should_escalate, factors = tracker.track_iteration(0, ["uncertainty"])
        assert should_escalate is False
        assert factors == []

    def test_second_iteration_escalates(self):
        tracker = SelfCorrectionTracker()
        # current_count=1 -> new_count=2, 2 >= 2 True
        should_escalate, factors = tracker.track_iteration(1, ["risk"])
        assert should_escalate is True
        assert factors == ["risk"]

    def test_max_loops_escalate(self):
        tracker = SelfCorrectionTracker()
        should_escalate, factors = tracker.track_iteration(2, ["taboo"])
        assert should_escalate is True
        assert factors == ["taboo"]

    def test_exceeds_max_loops(self):
        tracker = SelfCorrectionTracker()
        should_escalate, factors = tracker.track_iteration(5, ["secret"])
        assert should_escalate is True

    def test_custom_max_loops_threshold(self):
        tracker = SelfCorrectionTracker(max_loops=3)
        # current_count=1 -> new_count=2, 2 >= 3 False
        should_escalate, _ = tracker.track_iteration(1, ["test"])
        assert should_escalate is False
        # current_count=2 -> new_count=3, 3 >= 3 True
        should_escalate, factors = tracker.track_iteration(2, ["test"])
        assert should_escalate is True

    def test_empty_factors(self):
        tracker = SelfCorrectionTracker()
        should_escalate, factors = tracker.track_iteration(2, [])
        assert should_escalate is True
        assert factors == []

    def test_multiple_factors(self):
        tracker = SelfCorrectionTracker()
        should_escalate, factors = tracker.track_iteration(2, ["risk", "uncertainty"])
        assert should_escalate is True
        assert factors == ["risk", "uncertainty"]


class TestCheckPersistentFactor:
    """Tests for check_persistent_factor method."""

    def test_no_history(self):
        tracker = SelfCorrectionTracker()
        result = tracker.check_persistent_factor([])
        assert result is False

    def test_short_history(self):
        tracker = SelfCorrectionTracker()
        history = [["risk"]]
        result = tracker.check_persistent_factor(history)
        assert result is False

    def test_two_runs_history(self):
        tracker = SelfCorrectionTracker()
        history = [["risk"], ["risk"]]
        result = tracker.check_persistent_factor(history)
        assert result is False

    def test_three_same_factor(self):
        tracker = SelfCorrectionTracker()
        history = [["risk"], ["risk"], ["risk"]]
        result = tracker.check_persistent_factor(history)
        assert result is True

    def test_different_factors(self):
        tracker = SelfCorrectionTracker()
        history = [["risk"], ["uncertainty"], ["risk"]]
        result = tracker.check_persistent_factor(history)
        assert result is False

    def test_mixed_factors(self):
        tracker = SelfCorrectionTracker()
        history = [["risk", "test"], ["risk", "other"], ["risk", "another"]]
        result = tracker.check_persistent_factor(history)
        assert result is True

    def test_empty_factors_in_run(self):
        tracker = SelfCorrectionTracker()
        history = [["risk"], ["risk"], []]
        result = tracker.check_persistent_factor(history)
        assert result is False

    def test_custom_threshold(self):
        tracker = SelfCorrectionTracker(persistent_threshold=4)
        history = [["risk"], ["risk"], ["risk"]]
        result = tracker.check_persistent_factor(history)
        assert result is False
        history = [["risk"], ["risk"], ["risk"], ["risk"]]
        result = tracker.check_persistent_factor(history)
        assert result is True

    def test_longer_history(self):
        tracker = SelfCorrectionTracker()
        history = [["old"], ["old"], ["old"], ["risk"], ["risk"], ["risk"]]
        result = tracker.check_persistent_factor(history)
        assert result is True

    def test_factor_changes_in_history(self):
        tracker = SelfCorrectionTracker()
        history = [["a"], ["a"], ["a"], ["b"], ["b"], ["b"]]
        result = tracker.check_persistent_factor(history)
        assert result is True


class TestShouldEscalate:
    """Tests for should_escalate method."""

    def test_no_escalate(self):
        tracker = SelfCorrectionTracker()
        should, reason = tracker.should_escalate(0, ["test"])
        assert should is False
        assert reason == ""

    def test_escalate_max_loops(self):
        tracker = SelfCorrectionTracker()
        should, reason = tracker.should_escalate(2, ["test"])
        assert should is True
        assert reason == "max_self_correction_loops_exceeded"

    def test_escalate_persistent_factor(self):
        tracker = SelfCorrectionTracker()
        history = [["risk"], ["risk"], ["risk"]]
        should, reason = tracker.should_escalate(0, ["risk"], history)
        assert should is True
        assert reason == "persistent_factor_detected"

    def test_max_loops_priority(self):
        tracker = SelfCorrectionTracker()
        history = [["a"], ["a"], ["a"]]
        should, reason = tracker.should_escalate(2, ["test"], history)
        assert should is True
        assert reason == "max_self_correction_loops_exceeded"

    def test_no_history(self):
        tracker = SelfCorrectionTracker()
        # current_count=0 -> new_count=1, 1 >= 2 False (no escalate)
        should, reason = tracker.should_escalate(0, ["test"], None)
        assert should is False
        assert reason == ""

    def test_empty_history(self):
        tracker = SelfCorrectionTracker()
        # current_count=0 -> new_count=1, 1 >= 2 False (no escalate)
        should, reason = tracker.should_escalate(0, ["test"], [])
        assert should is False
        assert reason == ""

    def test_combined_checks(self):
        tracker = SelfCorrectionTracker()
        history = [["risk"], ["risk"], ["risk"]]
        # current_count=0 -> new_count=1, 1 >= 2 False, but persistent factor True
        should, reason = tracker.should_escalate(0, ["risk"], history)
        assert should is True
        assert reason == "persistent_factor_detected"


class TestTrackSelfCorrection:
    """Tests for track_self_correction convenience function."""

    def test_default_max_loops(self):
        should, factors = track_self_correction(0, ["test"])
        assert should is False
        should, factors = track_self_correction(2, ["test"])
        assert should is True

    def test_custom_max_loops(self):
        # current_count=2 -> new_count=3, 3 >= 4 False
        should, factors = track_self_correction(2, ["test"], max_loops=4)
        assert should is False
        # current_count=3 -> new_count=4, 4 >= 4 True
        should, factors = track_self_correction(3, ["test"], max_loops=4)
        assert should is True

    def test_returns_factors_on_escalate(self):
        should, factors = track_self_correction(2, ["risk", "uncertainty"])
        assert should is True
        assert factors == ["risk", "uncertainty"]


class TestCheckPersistentFactorEscalation:
    """Tests for check_persistent_factor_escalation convenience function."""

    def test_default_threshold(self):
        result = check_persistent_factor_escalation([["a"], ["a"], ["a"]])
        assert result is True

    def test_below_threshold(self):
        result = check_persistent_factor_escalation([["a"], ["a"]])
        assert result is False

    def test_custom_threshold(self):
        result = check_persistent_factor_escalation([["a"], ["a"], ["a"], ["a"]], threshold=4)
        assert result is True

    def test_different_factors(self):
        result = check_persistent_factor_escalation([["a"], ["b"], ["a"]])
        assert result is False


class TestSelfCorrectionIntegration:
    """Integration-like tests."""

    def test_full_correction_workflow(self):
        tracker = SelfCorrectionTracker(max_loops=3, persistent_threshold=3)
        should, reason = tracker.should_escalate(0, ["risk"])
        assert should is False
        should, reason = tracker.should_escalate(1, ["risk"])
        assert should is False
        should, reason = tracker.should_escalate(2, ["risk"])
        assert should is True
        assert reason == "max_self_correction_loops_exceeded"

    def test_persistent_factor_workflow(self):
        tracker = SelfCorrectionTracker()
        history = []
        for i in range(3):
            history.append(["risk"])
            should, reason = tracker.should_escalate(0, ["risk"], history)
            if i < 2:
                assert should is False
            else:
                assert should is True
                assert reason == "persistent_factor_detected"

    def test_max_loops_vs_persistent(self):
        tracker = SelfCorrectionTracker()
        history = [["risk"], ["risk"], ["risk"]]
        should, reason = tracker.should_escalate(2, ["risk"], history)
        assert should is True
        assert reason == "max_self_correction_loops_exceeded"
