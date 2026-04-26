"""
Dataclasses for the review queue system.

Review items, actions, SLA status, and escalation configuration.
Spec reference: docs/spec/DATA_TYPES_SPEC.md Section 6 (ReviewItem) and Section 7 (ReviewAction)
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .constants import SEVERITY_PRIORITY, ReviewDecision, Severity


@dataclass
class SLAStatus:
    """SLA tracking for a review item (backward compatibility view)."""
    ack_deadline: Optional[datetime] = None
    decision_deadline: Optional[datetime] = None
    acked_at: Optional[datetime] = None
    ack_expired: bool = False
    decision_expired: bool = False
    escalation_sent: bool = False  # ACK timeout escalation
    decision_escalation_sent: bool = False  # Decision timeout escalation


@dataclass
class ReviewItem:
    """
    A single item in the review queue.

    Spec: DATA_TYPES_SPEC.md Section 6 (ReviewItem)
    """
    # Required fields (no defaults) - must come first
    decision_id: str
    run_id: str
    state: str  # pass, warn, hold, block
    composite_score: float
    severity: str  # critical, high, medium, low
    top_factors: List[str]
    artifact_ref: str
    trace_ref: str
    created_at: datetime

    # Schema version for replay reproducibility (AGF-REQ-007)
    schema_version: str = "1.0.0"

    # Review identifier (separate from decision_id)
    review_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Exemplar references (Top 5 exemplar document IDs)
    exemplar_refs: List[str] = field(default_factory=list)

    # Optional fields with defaults
    checkpoint_ref: Optional[str] = None
    assigned_to: Optional[str] = None
    taken_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    # Flattened SLA fields (spec-compliant)
    sla_deadline: Optional[datetime] = None  # SLA decision deadline
    sla_ack_deadline: Optional[datetime] = None  # SLA ACK deadline

    # SLA tracking (backward compatibility view)
    sla_status: SLAStatus = field(default_factory=SLAStatus)

    # For pairwise comparison
    pair_id: Optional[str] = None  # Links to paired item in pairwise mode
    pair_position: Optional[str] = None  # "A" or "B" in comparison

    # Repeated hold tracking for severity escalation
    hold_count: int = 0
    original_severity: Optional[str] = None  # Before escalation

    # Correction tracking
    correction_attempts: int = 0

    def get_severity_enum(self) -> Severity:
        """Get severity as enum."""
        return Severity(self.severity)

    def get_priority(self) -> int:
        """Get priority value for ordering."""
        return SEVERITY_PRIORITY.get(self.get_severity_enum(), 0)

    def is_sla_expired(self) -> Tuple[bool, bool]:
        """
        Check if SLA has expired.

        Uses flattened sla_deadline/sla_ack_deadline fields if available,
        falls back to sla_status for backward compatibility.

        Returns:
            Tuple of (ack_expired, decision_expired)
        """
        now = datetime.now(timezone.utc)

        ack_expired = False
        decision_expired = False

        # Use flattened fields first (spec-compliant)
        ack_deadline = self.sla_ack_deadline or self.sla_status.ack_deadline
        decision_deadline = self.sla_deadline or self.sla_status.decision_deadline

        if ack_deadline and not self.sla_status.acked_at:
            ack_expired = now > ack_deadline

        if decision_deadline and not self.resolved_at:
            decision_expired = now > decision_deadline

        return ack_expired, decision_expired

    def sync_sla_fields(self) -> None:
        """
        Sync flattened SLA fields with sla_status for backward compatibility.

        Call this after setting sla_deadline/sla_ack_deadline to ensure
        sla_status is also populated.
        """
        if self.sla_deadline:
            self.sla_status.decision_deadline = self.sla_deadline
        if self.sla_ack_deadline:
            self.sla_status.ack_deadline = self.sla_ack_deadline


@dataclass
class ReviewAction:
    """
    Record of a review action taken on an item.

    Spec: DATA_TYPES_SPEC.md Section 7 (ReviewAction)
    """
    # Required fields (no defaults) - must come first
    decision_id: str
    reviewer: str
    created_at: datetime

    # Schema version for replay reproducibility (AGF-REQ-007)
    schema_version: str = "1.0.0"

    # Unique identifiers
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    review_id: str = ""  # Links to ReviewItem.review_id
    run_id: str = ""  # Run identifier

    # Action type (spec-compliant name, values from ReviewDecision enum)
    # Values: approve, reject, recalibrate, request_artifact_correction,
    #         request_process_correction, request_prompt_correction, add_judgment_note
    action_type: str = ""  # Maps to ReviewDecision.value

    # Backward compatibility: decision field (deprecated, use action_type)
    decision: Optional[ReviewDecision] = None

    # Comment (reviewer rationale)
    comment: str = ""

    # Correction details (renamed from correction_json)
    correction: Optional[Dict] = None  # spec-compliant name
    correction_json: Optional[Dict] = None  # backward compatibility alias

    # Calibration change (for recalibrate action)
    calibration_change: Optional[Dict] = None

    # Judgment note (for add_judgment_note action)
    judgment_note: Optional[str] = None

    # Decision state changes
    previous_decision: Optional[str] = None  # Decision before action (pass, warn, hold, block)
    new_decision: Optional[str] = None  # Decision after action

    # Trace correlation (OTel trace_id)
    trace_id: str = ""

    # SLA tracking
    sla_compliant: bool = True
    judgment_log_promoted: bool = False

    def get_action_type_value(self) -> str:
        """
        Get action_type value, falling back to decision enum if needed.

        Returns the action_type string value for spec compliance.
        """
        if self.action_type:
            return self.action_type
        if self.decision:
            return self.decision.value
        return ""

    def sync_fields(self) -> None:
        """
        Sync action_type with decision for backward compatibility.

        Call this after setting action_type to ensure decision is also populated.
        """
        if self.action_type and not self.decision:
            # Map action_type string back to ReviewDecision enum
            try:
                self.decision = ReviewDecision(self.action_type)
            except ValueError:
                pass  # Unknown action_type, leave decision as None

        # Sync correction fields
        if self.correction and not self.correction_json:
            self.correction_json = self.correction
        if self.correction_json and not self.correction:
            self.correction = self.correction_json


@dataclass
class EscalationConfig:
    """Configuration for escalation routing."""
    pager_duty_integration_key: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    email_recipients: Optional[List[str]] = None
    on_call_backup_reviewer: Optional[str] = None
    security_team_contact: Optional[str] = None