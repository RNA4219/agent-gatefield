"""
Online calibration methods for real-time threshold adjustment.

This module implements:
- Human correction incorporation
- Automatic calibration triggers
- Threshold adjustment limits
- Weight adjustment during calibration cycles
"""

from typing import Dict, List, Optional, Any

from .constants import (
    ONLINE_ADJUSTMENT_LIMITS,
    CALIBRATION_TRIGGERS,
    DEFAULT_SCORER_WEIGHTS,
    WEIGHT_CONSTRAINTS,
)


def incorporate_correction(
    correction_type: str,
    current_threshold: float,
    current_weights: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Process a human correction and compute adjustment.

    Correction types:
    - pass_to_block: Override pass decision to block (threshold too loose)
    - block_to_pass: Override block decision to pass (threshold too tight)
    - threshold_adjust: Direct threshold modification request
    - weight_adjust: Profile weight update request

    Args:
        correction_type: Type of correction being processed
        current_threshold: Current threshold value
        current_weights: Current scorer weights

    Returns:
        Dictionary with recommended adjustments and actions
    """
    result = {
        "correction_type": correction_type,
        "threshold_adjustment": 0.0,
        "weight_adjustment": {},
        "action": None
    }

    if correction_type == "pass_to_block":
        # Override pass -> block means threshold was too loose
        result["threshold_adjustment"] = -ONLINE_ADJUSTMENT_LIMITS["threshold_step"]
        result["action"] = "tighten_threshold"
    elif correction_type == "block_to_pass":
        # Override block -> pass means threshold was too tight
        result["threshold_adjustment"] = ONLINE_ADJUSTMENT_LIMITS["threshold_step"]
        result["action"] = "loosen_threshold"
    elif correction_type == "threshold_adjust":
        result["action"] = "direct_threshold_modification"
    elif correction_type == "weight_adjust":
        result["action"] = "profile_weight_update"

    return result


def check_calibration_trigger(
    override_count: int,
    total_decisions: int,
    window_days: int = 7
) -> Dict[str, Any]:
    """
    Check if automatic calibration should be triggered.

    Triggers:
    - Override surge: Override rate exceeds threshold in window
    - Critical miss: P0 priority blocking failure

    Args:
        override_count: Number of overrides in window
        total_decisions: Total decisions in window
        window_days: Days in the window

    Returns:
        Dictionary with trigger status and recommended action
    """
    override_rate = override_count / total_decisions if total_decisions > 0 else 0.0

    triggers = []

    if override_rate > CALIBRATION_TRIGGERS["override_surge_rate"]:
        triggers.append({
            "type": "override_surge",
            "priority": CALIBRATION_TRIGGERS["override_surge_priority"],
            "message": f"Override rate {override_rate*100:.1f}% exceeds threshold"
        })

    return {
        "triggered": len(triggers) > 0,
        "override_rate": override_rate,
        "triggers": triggers,
        "recommended_action": "schedule_recalibration" if triggers else None
    }


def compute_threshold_adjustment(
    correction_history: List[Dict[str, Any]],
    max_adjustment: Optional[float] = None
) -> float:
    """
    Compute cumulative threshold adjustment from correction history.

    Args:
        correction_history: List of past corrections
        max_adjustment: Maximum allowed adjustment (default: from constants)

    Returns:
        Net threshold adjustment value
    """
    if max_adjustment is None:
        max_adjustment = ONLINE_ADJUSTMENT_LIMITS["threshold_step"]

    total_adjustment = 0.0
    for correction in correction_history:
        adjustment = correction.get("threshold_adjustment", 0.0)
        total_adjustment += adjustment

    # Clamp to maximum adjustment
    total_adjustment = max(-max_adjustment, min(max_adjustment, total_adjustment))

    return total_adjustment


def validate_weight_adjustment(
    current_weights: Dict[str, float],
    proposed_changes: Dict[str, float],
    max_step: Optional[float] = None
) -> Dict[str, Any]:
    """
    Validate proposed weight adjustments against constraints.

    Args:
        current_weights: Current weight configuration
        proposed_changes: Proposed weight changes
        max_step: Maximum step per weight (default: from constants)

    Returns:
        Dictionary with validation result and adjusted weights
    """
    if max_step is None:
        max_step = ONLINE_ADJUSTMENT_LIMITS["weight_step"]

    result = {
        "valid": True,
        "violations": [],
        "adjusted_weights": current_weights.copy()
    }

    new_weights = current_weights.copy()

    for scorer, delta in proposed_changes.items():
        new_value = current_weights.get(scorer, 0.0) + delta

        # Check step constraint
        if abs(delta) > max_step:
            result["violations"].append(
                f"Weight change for {scorer} ({abs(delta)}) exceeds max step ({max_step})"
            )
            new_value = current_weights.get(scorer, 0.0) + max_step if delta > 0 else -max_step

        # Check min/max constraints
        if new_value < WEIGHT_CONSTRAINTS["min_weight"]:
            result["violations"].append(
                f"Weight for {scorer} would be below minimum ({WEIGHT_CONSTRAINTS['min_weight']})"
            )
            new_value = WEIGHT_CONSTRAINTS["min_weight"]

        if new_value > WEIGHT_CONSTRAINTS["max_weight"]:
            result["violations"].append(
                f"Weight for {scorer} would exceed maximum ({WEIGHT_CONSTRAINTS['max_weight']})"
            )
            new_value = WEIGHT_CONSTRAINTS["max_weight"]

        new_weights[scorer] = new_value

    # Check sum constraint
    total = sum(new_weights.values())
    if abs(total - WEIGHT_CONSTRAINTS["sum"]) > 0.001:
        result["violations"].append(
            f"Weights would sum to {total}, expected {WEIGHT_CONSTRAINTS['sum']}"
        )
        result["valid"] = False

    result["adjusted_weights"] = new_weights
    result["valid"] = len(result["violations"]) == 0

    return result


def apply_online_correction(
    profile_data: Dict[str, Any],
    correction: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Apply an online correction to a calibration profile.

    Args:
        profile_data: Current profile configuration
        correction: Correction to apply

    Returns:
        Updated profile data
    """
    updated = profile_data.copy()

    action = correction.get("action")

    if action == "tighten_threshold" or action == "loosen_threshold":
        adjustment = correction.get("threshold_adjustment", 0.0)
        # Apply to relevant thresholds
        for axis in ["taboo", "reject_similarity"]:
            if axis in updated.get("warn_thresholds", {}):
                current = updated["warn_thresholds"][axis]
                if current is not None:
                    updated["warn_thresholds"][axis] = max(0.0, min(1.0, current + adjustment))
            if axis in updated.get("block_thresholds", {}):
                current = updated["block_thresholds"][axis]
                if current is not None:
                    updated["block_thresholds"][axis] = max(0.0, min(1.0, current + adjustment))

    elif action == "profile_weight_update":
        weight_changes = correction.get("weight_adjustment", {})
        validation = validate_weight_adjustment(
            updated.get("weights", DEFAULT_SCORER_WEIGHTS.copy()),
            weight_changes
        )
        if validation["valid"]:
            updated["weights"] = validation["adjusted_weights"]

    return updated


def get_calibration_priority(trigger_type: str) -> str:
    """
    Get priority level for a calibration trigger type.

    Args:
        trigger_type: Type of trigger

    Returns:
        Priority level (P0, P1, P2)
    """
    priority_map = {
        "critical_miss": CALIBRATION_TRIGGERS["critical_miss_priority"],
        "override_surge": CALIBRATION_TRIGGERS["override_surge_priority"],
        "drift_detection": CALIBRATION_TRIGGERS["drift_detection_priority"],
        "scheduled_maintenance": CALIBRATION_TRIGGERS["scheduled_maintenance_priority"],
    }
    return priority_map.get(trigger_type, "P2")


def should_trigger_immediate_recalibration(
    trigger_result: Dict[str, Any]
) -> bool:
    """
    Determine if immediate recalibration is needed based on triggers.

    Args:
        trigger_result: Result from check_calibration_trigger

    Returns:
        True if immediate recalibration recommended
    """
    if not trigger_result.get("triggered"):
        return False

    triggers = trigger_result.get("triggers", [])
    for trigger in triggers:
        if trigger.get("priority") == "P0":
            return True

    return False