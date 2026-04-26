"""
SLA Handler - Timeout Handling and Deadline Management

RUNBOOK 6.1 and STATE_TRANSITION_SPEC 2.5, 6.3 compliant SLA handling.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple

from src.core.audit import log_sla_timeout


class SLAHandler:
    """
    Handles SLA timeout calculations and fail-closed logic.

    Implements RUNBOOK 6.1 and STATE_TRANSITION_SPEC 6.3 SLA requirements.
    """

    # SLA timeout targets (RUNBOOK 6.1, STATE_TRANSITION_SPEC 6.3)
    SLA_CRITICAL_ACK_MINUTES = 15
    SLA_CRITICAL_DECISION_MINUTES = 60
    SLA_HIGH_ACK_MINUTES = 60
    SLA_HIGH_DECISION_MINUTES = 240  # 4 hours

    def __init__(
        self,
        critical_ack_minutes: int = None,
        critical_decision_minutes: int = None,
        high_ack_minutes: int = None,
        high_decision_minutes: int = None
    ):
        """
        Initialize SLA handler with optional custom timeouts.

        Args:
            critical_ack_minutes: ACK deadline for critical severity (default 15)
            critical_decision_minutes: Decision deadline for critical (default 60)
            high_ack_minutes: ACK deadline for high severity (default 60)
            high_decision_minutes: Decision deadline for high (default 240)
        """
        self.critical_ack_minutes = critical_ack_minutes or self.SLA_CRITICAL_ACK_MINUTES
        self.critical_decision_minutes = critical_decision_minutes or self.SLA_CRITICAL_DECISION_MINUTES
        self.high_ack_minutes = high_ack_minutes or self.SLA_HIGH_ACK_MINUTES
        self.high_decision_minutes = high_decision_minutes or self.SLA_HIGH_DECISION_MINUTES

    def calculate_deadlines(
        self,
        severity: str,
        created_at: datetime = None
    ) -> Dict[str, Optional[datetime]]:
        """
        Calculate SLA ACK and decision deadlines based on severity.

        Args:
            severity: One of 'critical', 'high', 'medium', 'low'
            created_at: Start time for deadline calculation (default: now)

        Returns:
            Dict with 'sla_ack_deadline' and 'sla_decision_deadline' keys
        """
        if created_at is None:
            created_at = datetime.now(timezone.utc)

        deadlines = {}

        if severity == 'critical':
            deadlines['sla_ack_deadline'] = created_at + timedelta(minutes=self.critical_ack_minutes)
            deadlines['sla_decision_deadline'] = created_at + timedelta(minutes=self.critical_decision_minutes)
        elif severity == 'high':
            deadlines['sla_ack_deadline'] = created_at + timedelta(minutes=self.high_ack_minutes)
            deadlines['sla_decision_deadline'] = created_at + timedelta(minutes=self.high_decision_minutes)
        elif severity == 'medium':
            # Same business day for ACK, next business day for decision
            deadlines['sla_ack_deadline'] = self._get_next_business_day(created_at, 0)
            deadlines['sla_decision_deadline'] = self._get_next_business_day(created_at, 1)
        else:  # low
            deadlines['sla_ack_deadline'] = None  # No ACK required
            deadlines['sla_decision_deadline'] = None  # Backlog

        return deadlines

    def check_timeout(
        self,
        severity: str,
        review_created_at: datetime,
        ack_taken_at: datetime = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if SLA timeout has been exceeded.

        Args:
            severity: One of 'critical', 'high', 'medium', 'low'
            review_created_at: When the review was created
            ack_taken_at: When ACK was taken (None if not yet acknowledged)

        Returns:
            Tuple of (timeout_exceeded: bool, timeout_type: str or None)
            timeout_type is 'ack_timeout' or 'decision_timeout' if exceeded
        """
        now = datetime.now(timezone.utc)

        if severity == 'critical':
            ack_deadline = review_created_at + timedelta(minutes=self.critical_ack_minutes)
            decision_deadline = review_created_at + timedelta(minutes=self.critical_decision_minutes)

            # Check ACK timeout
            if ack_taken_at is None and now > ack_deadline:
                return True, 'ack_timeout'

            # Check decision timeout (only if ACK was taken)
            if ack_taken_at is not None and now > decision_deadline:
                return True, 'decision_timeout'

        elif severity == 'high':
            ack_deadline = review_created_at + timedelta(minutes=self.high_ack_minutes)
            decision_deadline = review_created_at + timedelta(minutes=self.high_decision_minutes)

            if ack_taken_at is None and now > ack_deadline:
                return True, 'ack_timeout'

            if ack_taken_at is not None and now > decision_deadline:
                return True, 'decision_timeout'

        return False, None

    def handle_timeout(
        self,
        decision_id: str,
        timeout_type: str,
        sla_deadline: datetime,
        escalation_target: str,
        gate_state_cls,
        decision_result_cls,
        threshold_version: str
    ) -> 'DecisionResult':
        """
        Handle SLA timeout by failing closed (STATE_TRANSITION_SPEC T25, T26).

        Creates a BLOCK decision with timeout escalation details.

        Args:
            decision_id: ID of the decision that timed out
            timeout_type: 'ack_timeout' or 'decision_timeout'
            sla_deadline: The deadline that was exceeded
            escalation_target: Who to escalate to
            gate_state_cls: GateState enum class
            decision_result_cls: DecisionResult dataclass
            threshold_version: Current threshold version

        Returns:
            DecisionResult with BLOCK decision
        """
        result = decision_result_cls(
            decision=gate_state_cls.BLOCK,
            composite_score=1.0,
            scorer_results=[],
            factors=['SLA timeout exceeded - fail closed'],
            exemplar_refs=[],
            action_type='process_correction',
            threshold_version=threshold_version,
            hard_override_reason='sla_timeout_fail_closed',
            transition_reason=f'{timeout_type}_fail_closed',
            created_at=datetime.now(timezone.utc)
        )

        # Log timeout event
        log_sla_timeout(
            decision_id=decision_id,
            timeout_type=timeout_type,
            sla_deadline=sla_deadline,
            escalation_target=escalation_target
        )

        return result

    def _get_next_business_day(self, from_date: datetime, days_offset: int) -> datetime:
        """
        Calculate next business day (excluding weekends).

        Args:
            from_date: Starting date
            days_offset: Number of days to add

        Returns:
            Datetime of the next business day
        """
        result = from_date + timedelta(days=days_offset)
        # Skip weekends
        while result.weekday() >= 5:  # Saturday = 5, Sunday = 6
            result += timedelta(days=1)
        return result


def calculate_sla_deadlines(
    severity: str,
    created_at: datetime = None,
    sla_handler: SLAHandler = None
) -> Dict[str, Optional[datetime]]:
    """
    Convenience function for calculating SLA deadlines.

    Args:
        severity: One of 'critical', 'high', 'medium', 'low'
        created_at: Start time (default: now)
        sla_handler: Optional SLAHandler instance (default: new instance)

    Returns:
        Dict with deadline information
    """
    if sla_handler is None:
        sla_handler = SLAHandler()
    return sla_handler.calculate_deadlines(severity, created_at)


def check_sla_timeout(
    severity: str,
    review_created_at: datetime,
    ack_taken_at: datetime = None,
    sla_handler: SLAHandler = None
) -> Tuple[bool, Optional[str]]:
    """
    Convenience function for checking SLA timeout.

    Args:
        severity: One of 'critical', 'high', 'medium', 'low'
        review_created_at: When the review was created
        ack_taken_at: When ACK was taken (None if not acknowledged)
        sla_handler: Optional SLAHandler instance

    Returns:
        Tuple of (timeout_exceeded, timeout_type)
    """
    if sla_handler is None:
        sla_handler = SLAHandler()
    return sla_handler.check_timeout(severity, review_created_at, ack_taken_at)


def handle_sla_timeout(
    decision_id: str,
    timeout_type: str,
    sla_deadline: datetime,
    escalation_target: str,
    gate_state_cls,
    decision_result_cls,
    threshold_version: str,
    sla_handler: SLAHandler = None
) -> 'DecisionResult':
    """
    Convenience function for handling SLA timeout.

    Args:
        decision_id: ID of timed-out decision
        timeout_type: 'ack_timeout' or 'decision_timeout'
        sla_deadline: The exceeded deadline
        escalation_target: Who to escalate to
        gate_state_cls: GateState enum class
        decision_result_cls: DecisionResult dataclass
        threshold_version: Current threshold version
        sla_handler: Optional SLAHandler instance

    Returns:
        DecisionResult with BLOCK decision
    """
    if sla_handler is None:
        sla_handler = SLAHandler()
    return sla_handler.handle_timeout(
        decision_id,
        timeout_type,
        sla_deadline,
        escalation_target,
        gate_state_cls,
        decision_result_cls,
        threshold_version
    )