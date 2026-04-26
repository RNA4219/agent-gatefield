"""
Self-Correction Loop Tracking - Escalation Logic

STATE_TRANSITION_SPEC 5.2, 5.4, 5.5 compliant self-correction tracking.
"""

from typing import List, Tuple


class SelfCorrectionTracker:
    """
    Tracks self-correction loop counts and persistent factor escalation.

    Implements STATE_TRANSITION_SPEC 5.2, 5.4, 5.5 requirements.
    """

    # Self-correction limits (STATE_TRANSITION_SPEC 5.2)
    DEFAULT_MAX_LOOPS = 2
    DEFAULT_PERSISTENT_THRESHOLD = 3  # consecutive runs

    def __init__(
        self,
        max_loops: int = None,
        persistent_threshold: int = None
    ):
        """
        Initialize the self-correction tracker.

        Args:
            max_loops: Maximum self-correction loops before escalation
            persistent_threshold: Consecutive runs for persistent factor detection
        """
        self.max_loops = max_loops or self.DEFAULT_MAX_LOOPS
        self.persistent_threshold = persistent_threshold or self.DEFAULT_PERSISTENT_THRESHOLD

    def track_iteration(
        self,
        current_count: int,
        top_factors: List[str]
    ) -> Tuple[bool, List[str]]:
        """
        Track self-correction iteration and determine if escalation needed.

        Args:
            current_count: Current self-correction count
            top_factors: Top factors from current evaluation

        Returns:
            Tuple of (should_escalate_to_hold, persistent_factors)
        """
        new_count = current_count + 1

        # Check if max loops exceeded (STATE_TRANSITION_SPEC 5.4)
        if new_count >= self.max_loops:
            return True, top_factors  # Escalate to HOLD

        return False, []  # Continue self-correction

    def check_persistent_factor(
        self,
        factor_history: List[List[str]]
    ) -> bool:
        """
        Check if same top factor persists for N consecutive runs.

        STATE_TRANSITION_SPEC 5.5: If the same top factor persists for
        3 consecutive runs, escalate to HOLD.

        Args:
            factor_history: List of top factors from recent runs

        Returns:
            True if persistent factor detected, False otherwise
        """
        if len(factor_history) < self.persistent_threshold:
            return False

        # Check last N runs for persistent factor
        recent_runs = factor_history[-self.persistent_threshold:]

        # Find common factors across all recent runs
        if recent_runs[0]:
            first_factor = recent_runs[0][0]
            for run_factors in recent_runs[1:]:
                if not run_factors or run_factors[0] != first_factor:
                    return False
            return True  # Same top factor in all recent runs

        return False

    def should_escalate(
        self,
        current_count: int,
        top_factors: List[str],
        factor_history: List[List[str]] = None
    ) -> Tuple[bool, str]:
        """
        Determine if escalation to HOLD is needed.

        Combines max loop check and persistent factor check.

        Args:
            current_count: Current self-correction count
            top_factors: Top factors from current evaluation
            factor_history: Optional history of recent top factors

        Returns:
            Tuple of (should_escalate, reason)
        """
        # Check max loops
        should_escalate, _ = self.track_iteration(current_count, top_factors)
        if should_escalate:
            return True, 'max_self_correction_loops_exceeded'

        # Check persistent factors
        if factor_history is not None:
            if self.check_persistent_factor(factor_history):
                return True, 'persistent_factor_detected'

        return False, ''


def track_self_correction(
    current_count: int,
    top_factors: List[str],
    max_loops: int = 2
) -> Tuple[bool, List[str]]:
    """
    Convenience function for self-correction tracking.

    Args:
        current_count: Current self-correction count
        top_factors: Top factors from current evaluation
        max_loops: Maximum loops before escalation (default 2)

    Returns:
        Tuple of (should_escalate_to_hold, persistent_factors)
    """
    tracker = SelfCorrectionTracker(max_loops=max_loops)
    return tracker.track_iteration(current_count, top_factors)


def check_persistent_factor_escalation(
    factor_history: List[List[str]],
    threshold: int = 3
) -> bool:
    """
    Convenience function for persistent factor check.

    Args:
        factor_history: List of top factors from recent runs
        threshold: Consecutive runs threshold (default 3)

    Returns:
        True if persistent factor detected
    """
    tracker = SelfCorrectionTracker(persistent_threshold=threshold)
    return tracker.check_persistent_factor(factor_history)