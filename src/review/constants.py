"""
Constants and enums for the review queue system.

SLA targets, severity priorities, and decision types for human review workflow.
Spec reference: docs/RUNBOOK.md Section 6.1
"""

from datetime import timedelta
from enum import Enum
from typing import Dict, Optional


class ReviewDecision(Enum):
    """Decision types for review resolution."""
    APPROVE = "approve"
    REJECT = "reject"
    RECALIBRATE = "recalibrate"
    REQUEST_ARTIFACT_CORRECTION = "request_artifact_correction"
    REQUEST_PROCESS_CORRECTION = "request_process_correction"
    REQUEST_PROMPT_CORRECTION = "request_prompt_correction"
    ADD_JUDGMENT_NOTE = "add_judgment_note"


class QueueMode(Enum):
    """Queue operation modes."""
    STANDARD = "standard"
    PAIRWISE = "pairwise"  # A/B comparison mode


class Severity(Enum):
    """Review item severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SLAType(Enum):
    """SLA types for deadline tracking."""
    ACK = "ack"
    DECISION = "decision"


# SLA targets per severity (from RUNBOOK.md Section 6.1)
# Maps Severity -> SLAType -> timedelta (or None for no timeout)
SLA_TARGETS: Dict[Severity, Dict[SLAType, Optional[timedelta]]] = {
    Severity.CRITICAL: {
        SLAType.ACK: timedelta(minutes=15),
        SLAType.DECISION: timedelta(minutes=60),
    },
    Severity.HIGH: {
        SLAType.ACK: timedelta(minutes=60),
        SLAType.DECISION: timedelta(minutes=240),  # 4 hours
    },
    Severity.MEDIUM: {
        SLAType.ACK: timedelta(hours=8),  # Same business day
        SLAType.DECISION: timedelta(hours=24),  # Next business day
    },
    Severity.LOW: {
        SLAType.ACK: None,  # No ACK required
        SLAType.DECISION: None,  # Backlog, no timeout
    },
}

# Priority ordering for severity (higher number = higher priority)
SEVERITY_PRIORITY: Dict[Severity, int] = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
}