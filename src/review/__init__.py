"""
Review queue package for human review workflow.

Provides review queue management with SLA handling, escalation routing,
pairwise comparison mode, and judgment log promotion.

Main entry point: ReviewQueue class from queue.py

Usage:
    from review import ReviewQueue, ReviewItem, ReviewDecision

    queue = ReviewQueue()
    queue.enqueue(item)
    item = queue.take(severity="critical")
    action = queue.resolve(item.decision_id, "reviewer", ReviewDecision.APPROVE, "OK")
"""

# Main entry point
from .queue import ReviewQueue

# Core types - backward compatibility imports
from .constants import (
    ReviewDecision,
    QueueMode,
    Severity,
    SLAType,
    SLA_TARGETS,
    SEVERITY_PRIORITY,
)
from .dataclasses import (
    SLAStatus,
    ReviewItem,
    ReviewAction,
    EscalationConfig,
)
from .escalation import EscalationHandler
from .promotion import JudgmentLogPromoter

__all__ = [
    # Main class
    "ReviewQueue",
    # Enums
    "ReviewDecision",
    "QueueMode",
    "Severity",
    "SLAType",
    # Constants
    "SLA_TARGETS",
    "SEVERITY_PRIORITY",
    # Dataclasses
    "SLAStatus",
    "ReviewItem",
    "ReviewAction",
    "EscalationConfig",
    # Handlers
    "EscalationHandler",
    "JudgmentLogPromoter",
]