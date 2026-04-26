"""
Escalation handler for SLA breaches.

Handles notifications via pager, webhook, and email when review items
exceed their SLA deadlines.
Spec reference: docs/STATE_TRANSITION_SPEC.md Section 9.2
"""

import logging
from typing import Callable, Dict, List, Optional

from .constants import Severity
from .dataclasses import EscalationConfig, ReviewItem
from .sla_handler import get_elapsed_minutes

logger = logging.getLogger(__name__)


class EscalationHandler:
    """Handles escalation notifications for SLA breaches."""

    def __init__(self, config: Optional[EscalationConfig] = None):
        """
        Initialize escalation handler.

        Args:
            config: Optional escalation configuration for routing
        """
        self.config = config or EscalationConfig()
        self._pager_callback: Optional[Callable[[str, Dict], None]] = None
        self._webhook_callback: Optional[Callable[[str, Dict], None]] = None
        self._email_callback: Optional[Callable[[List[str], str, Dict], None]] = None

    def register_pager_callback(self, callback: Callable[[str, Dict], None]) -> None:
        """
        Register callback for pager integration (e.g., PagerDuty).

        Args:
            callback: Function taking (event_type: str, data: Dict) -> None
        """
        self._pager_callback = callback

    def register_webhook_callback(self, callback: Callable[[str, Dict], None]) -> None:
        """
        Register callback for webhook integration (e.g., Slack).

        Args:
            callback: Function taking (event_type: str, data: Dict) -> None
        """
        self._webhook_callback = callback

    def register_email_callback(self, callback: Callable[[List[str], str, Dict], None]) -> None:
        """
        Register callback for email notifications.

        Args:
            callback: Function taking (recipients: List[str], subject: str, data: Dict) -> None
        """
        self._email_callback = callback

    def escalate_ack_timeout(self, item: ReviewItem) -> None:
        """
        Escalate when ACK deadline exceeded.

        Sends pager notification for critical/high severity, webhook notification,
        and notifies backup reviewer if configured.

        Args:
            item: ReviewItem that has exceeded ACK deadline
        """
        severity = item.get_severity_enum()

        escalation_data = {
            "decision_id": item.decision_id,
            "run_id": item.run_id,
            "severity": item.severity,
            "timeout_type": "ack_timeout",
            "sla_deadline": item.sla_status.ack_deadline.isoformat() if item.sla_status.ack_deadline else None,
            "elapsed_minutes": get_elapsed_minutes(item.created_at),
            "escalation_reason": "No reviewer ACK within SLA window",
        }

        # Send pager notification for critical/high
        if severity in (Severity.CRITICAL, Severity.HIGH):
            self._send_pager_notification("ack_timeout", escalation_data)

        # Send webhook notification
        self._send_webhook_notification("ack_timeout", escalation_data)

        # Notify backup reviewer
        if self.config.on_call_backup_reviewer:
            self._send_email_notification(
                [self.config.on_call_backup_reviewer],
                f"Review ACK Timeout - {item.severity}",
                escalation_data
            )

        item.sla_status.escalation_sent = True
        item.sla_status.ack_expired = True
        logger.warning(f"ACK timeout escalation for {item.decision_id}: {escalation_data}")

    def escalate_decision_timeout(self, item: ReviewItem) -> None:
        """
        Escalate when decision deadline exceeded - fail closed.

        Sends pager notification for critical/high severity, webhook notification,
        and notifies security team for critical severity. Triggers auto-block.

        Args:
            item: ReviewItem that has exceeded decision deadline
        """
        severity = item.get_severity_enum()

        escalation_data = {
            "decision_id": item.decision_id,
            "run_id": item.run_id,
            "severity": item.severity,
            "timeout_type": "decision_timeout",
            "sla_deadline": item.sla_status.decision_deadline.isoformat() if item.sla_status.decision_deadline else None,
            "elapsed_minutes": get_elapsed_minutes(item.created_at),
            "assigned_to": item.assigned_to,
            "escalation_reason": "No decision within SLA window - failing closed",
            "auto_block_reason": "sla_timeout_fail_closed",
        }

        # Send pager notification for critical/high
        if severity in (Severity.CRITICAL, Severity.HIGH):
            self._send_pager_notification("decision_timeout", escalation_data)

        # Send webhook notification
        self._send_webhook_notification("decision_timeout", escalation_data)

        # Notify security team for critical
        if severity == Severity.CRITICAL and self.config.security_team_contact:
            self._send_email_notification(
                [self.config.security_team_contact],
                f"CRITICAL Review Decision Timeout - Fail Closed",
                escalation_data
            )

        item.sla_status.escalation_sent = True
        item.sla_status.decision_expired = True
        logger.critical(f"Decision timeout escalation (fail closed) for {item.decision_id}: {escalation_data}")

    def _send_pager_notification(self, event_type: str, data: Dict) -> None:
        """
        Send pager notification via registered callback.

        Args:
            event_type: Type of event (e.g., "ack_timeout", "decision_timeout")
            data: Event data dictionary
        """
        if self._pager_callback:
            try:
                self._pager_callback(event_type, data)
            except Exception as e:
                logger.error(f"Pager notification failed: {e}")
        elif self.config.pager_duty_integration_key:
            # Direct PagerDuty API call would go here
            logger.info(f"PagerDuty notification: {event_type} - {data}")

    def _send_webhook_notification(self, event_type: str, data: Dict) -> None:
        """
        Send webhook notification via registered callback.

        Args:
            event_type: Type of event
            data: Event data dictionary
        """
        if self._webhook_callback:
            try:
                self._webhook_callback(event_type, data)
            except Exception as e:
                logger.error(f"Webhook notification failed: {e}")
        elif self.config.slack_webhook_url:
            # Direct Slack webhook call would go here
            logger.info(f"Slack webhook notification: {event_type} - {data}")

    def _send_email_notification(self, recipients: List[str], subject: str, data: Dict) -> None:
        """
        Send email notification via registered callback.

        Args:
            recipients: List of email addresses
            subject: Email subject line
            data: Event data dictionary
        """
        if self._email_callback:
            try:
                self._email_callback(recipients, subject, data)
            except Exception as e:
                logger.error(f"Email notification failed: {e}")
        elif self.config.email_recipients:
            logger.info(f"Email notification to {recipients}: {subject} - {data}")