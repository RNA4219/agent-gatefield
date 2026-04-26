"""
SLA (Service Level Agreement) handler for the review queue.

Provides deadline calculation and timeout checking for review items.
Spec reference: docs/RUNBOOK.md Section 6.1, docs/STATE_TRANSITION_SPEC.md T25, T26
"""

from datetime import datetime, timezone
from typing import Optional

from .constants import SLA_TARGETS, SLAType, Severity
from .dataclasses import ReviewItem


def calculate_sla_deadlines(item: ReviewItem) -> None:
    """
    Calculate SLA deadlines based on item severity.

    Sets ack_deadline and decision_deadline on the item's sla_status
    and also on the flattened sla_ack_deadline/sla_deadline fields
    for spec compliance.

    Spec: DATA_TYPES_SPEC.md Section 6 (ReviewItem sla_deadline/sla_ack_deadline)

    Args:
        item: ReviewItem to calculate deadlines for (modified in place)
    """
    severity = item.get_severity_enum()
    targets = SLA_TARGETS[severity]

    now = datetime.now(timezone.utc)

    if targets[SLAType.ACK]:
        ack_deadline = now + targets[SLAType.ACK]
        item.sla_status.ack_deadline = ack_deadline
        item.sla_ack_deadline = ack_deadline  # Flattened field (spec-compliant)

    if targets[SLAType.DECISION]:
        decision_deadline = now + targets[SLAType.DECISION]
        item.sla_status.decision_deadline = decision_deadline
        item.sla_deadline = decision_deadline  # Flattened field (spec-compliant)


def check_sla_compliance(item: ReviewItem, resolved_at: datetime) -> bool:
    """
    Check if resolution was within SLA.

    Args:
        item: ReviewItem to check
        resolved_at: Timestamp when item was resolved

    Returns:
        True if compliant with SLA, False otherwise
    """
    # ACK compliance
    if item.sla_status.ack_deadline and item.taken_at:
        if item.taken_at > item.sla_status.ack_deadline:
            return False

    # Decision compliance
    if item.sla_status.decision_deadline:
        if resolved_at > item.sla_status.decision_deadline:
            return False

    return True


def get_sla_status_summary(item: ReviewItem) -> dict:
    """
    Get a summary of SLA status for an item.

    Args:
        item: ReviewItem to summarize

    Returns:
        Dictionary with SLA status details
    """
    ack_expired, decision_expired = item.is_sla_expired()
    severity = item.get_severity_enum()
    targets = SLA_TARGETS[severity]

    now = datetime.now(timezone.utc)

    def format_remaining(deadline: Optional[datetime]) -> Optional[int]:
        """Get remaining minutes until deadline."""
        if deadline is None:
            return None
        remaining = int((deadline - now).total_seconds() / 60)
        return max(0, remaining)

    return {
        "decision_id": item.decision_id,
        "severity": item.severity,
        "ack_deadline": item.sla_status.ack_deadline.isoformat() if item.sla_status.ack_deadline else None,
        "decision_deadline": item.sla_status.decision_deadline.isoformat() if item.sla_status.decision_deadline else None,
        "acked_at": item.sla_status.acked_at.isoformat() if item.sla_status.acked_at else None,
        "ack_expired": ack_expired,
        "decision_expired": decision_expired,
        "ack_remaining_minutes": format_remaining(item.sla_status.ack_deadline),
        "decision_remaining_minutes": format_remaining(item.sla_status.decision_deadline),
        "ack_target_minutes": targets[SLAType.ACK].total_seconds() / 60 if targets[SLAType.ACK] else None,
        "decision_target_minutes": targets[SLAType.DECISION].total_seconds() / 60 if targets[SLAType.DECISION] else None,
    }


def get_elapsed_minutes(created_at: datetime) -> int:
    """
    Calculate minutes elapsed since creation.

    Args:
        created_at: Creation timestamp

    Returns:
        Number of minutes elapsed
    """
    return int((datetime.now(timezone.utc) - created_at).total_seconds() / 60)