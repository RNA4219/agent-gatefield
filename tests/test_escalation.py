"""
Tests for Escalation Handler - SLA breach notifications.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock

from src.review.escalation import EscalationHandler
from src.review.constants import Severity
from src.review.dataclasses import ReviewItem, SLAStatus, EscalationConfig


class TestEscalationHandlerInit:
    """Tests for EscalationHandler initialization."""

    def test_default_init(self):
        """Default initialization."""
        handler = EscalationHandler()
        assert handler.config is not None
        assert handler._pager_callback is None
        assert handler._webhook_callback is None
        assert handler._email_callback is None

    def test_config_init(self):
        """Configuration initialization."""
        config = EscalationConfig(
            pager_duty_integration_key="key-123",
            slack_webhook_url="https://slack.example.com"
        )
        handler = EscalationHandler(config)
        assert handler.config.pager_duty_integration_key == "key-123"

    def test_empty_config(self):
        """Empty EscalationConfig."""
        config = EscalationConfig()
        handler = EscalationHandler(config)
        assert handler.config.pager_duty_integration_key is None


class TestCallbackRegistration:
    """Tests for callback registration."""

    def test_register_pager_callback(self):
        """Register pager callback."""
        handler = EscalationHandler()
        callback = Mock()
        handler.register_pager_callback(callback)
        assert handler._pager_callback is callback

    def test_register_webhook_callback(self):
        """Register webhook callback."""
        handler = EscalationHandler()
        callback = Mock()
        handler.register_webhook_callback(callback)
        assert handler._webhook_callback is callback

    def test_register_email_callback(self):
        """Register email callback."""
        handler = EscalationHandler()
        callback = Mock()
        handler.register_email_callback(callback)
        assert handler._email_callback is callback

    def test_register_multiple_callbacks(self):
        """Register multiple callbacks."""
        handler = EscalationHandler()
        pager = Mock()
        webhook = Mock()
        email = Mock()

        handler.register_pager_callback(pager)
        handler.register_webhook_callback(webhook)
        handler.register_email_callback(email)

        assert handler._pager_callback is pager
        assert handler._webhook_callback is webhook
        assert handler._email_callback is email


class TestEscalateAckTimeout:
    """Tests for escalate_ack_timeout method."""

    @pytest.fixture
    def critical_item(self):
        """Create critical severity review item."""
        return ReviewItem(
            decision_id="dec-critical",
            run_id="run-critical",
            state="block",
            composite_score=0.95,
            severity="critical",
            top_factors=["secret_match"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus(
                ack_deadline=datetime.now(timezone.utc)
            )
        )

    @pytest.fixture
    def high_item(self):
        """Create high severity review item."""
        return ReviewItem(
            decision_id="dec-high",
            run_id="run-high",
            state="hold",
            composite_score=0.80,
            severity="high",
            top_factors=["uncertainty"],
            artifact_ref="art-2",
            trace_ref="trace-2",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus(
                ack_deadline=datetime.now(timezone.utc)
            )
        )

    @pytest.fixture
    def medium_item(self):
        """Create medium severity review item."""
        return ReviewItem(
            decision_id="dec-medium",
            run_id="run-medium",
            state="warn",
            composite_score=0.60,
            severity="medium",
            top_factors=["risk_score"],
            artifact_ref="art-3",
            trace_ref="trace-3",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus(
                ack_deadline=datetime.now(timezone.utc)
            )
        )

    def test_ack_timeout_critical(self, critical_item):
        """ACK timeout for critical severity."""
        handler = EscalationHandler()
        pager_callback = Mock()
        webhook_callback = Mock()
        handler.register_pager_callback(pager_callback)
        handler.register_webhook_callback(webhook_callback)

        handler.escalate_ack_timeout(critical_item)

        pager_callback.assert_called_once()
        webhook_callback.assert_called_once()
        assert critical_item.sla_status.escalation_sent is True
        assert critical_item.sla_status.ack_expired is True

    def test_ack_timeout_high(self, high_item):
        """ACK timeout for high severity."""
        handler = EscalationHandler()
        pager_callback = Mock()
        webhook_callback = Mock()
        handler.register_pager_callback(pager_callback)
        handler.register_webhook_callback(webhook_callback)

        handler.escalate_ack_timeout(high_item)

        pager_callback.assert_called_once()
        webhook_callback.assert_called_once()
        assert high_item.sla_status.escalation_sent is True

    def test_ack_timeout_medium_no_pager(self, medium_item):
        """ACK timeout for medium severity (no pager)."""
        handler = EscalationHandler()
        pager_callback = Mock()
        webhook_callback = Mock()
        handler.register_pager_callback(pager_callback)
        handler.register_webhook_callback(webhook_callback)

        handler.escalate_ack_timeout(medium_item)

        # Pager not called for medium severity
        pager_callback.assert_not_called()
        webhook_callback.assert_called_once()

    def test_ack_timeout_with_backup_reviewer(self, critical_item):
        """ACK timeout notifies backup reviewer."""
        config = EscalationConfig(
            on_call_backup_reviewer="backup@example.com"
        )
        handler = EscalationHandler(config)
        email_callback = Mock()
        handler.register_email_callback(email_callback)
        handler.register_webhook_callback(Mock())

        handler.escalate_ack_timeout(critical_item)

        email_callback.assert_called_once()
        call_args = email_callback.call_args
        recipients = call_args[0][0]
        assert "backup@example.com" in recipients

    def test_ack_timeout_escalation_data(self, critical_item):
        """ACK timeout escalation data structure."""
        handler = EscalationHandler()
        pager_callback = Mock()
        handler.register_pager_callback(pager_callback)

        handler.escalate_ack_timeout(critical_item)

        call_args = pager_callback.call_args
        data = call_args[0][1]

        assert "decision_id" in data
        assert "run_id" in data
        assert "severity" in data
        assert "timeout_type" in data
        assert data["timeout_type"] == "ack_timeout"
        assert "escalation_reason" in data


class TestEscalateDecisionTimeout:
    """Tests for escalate_decision_timeout method."""

    @pytest.fixture
    def critical_item(self):
        """Create critical severity review item."""
        return ReviewItem(
            decision_id="dec-dt-critical",
            run_id="run-dt-critical",
            state="block",
            composite_score=0.95,
            severity="critical",
            top_factors=["secret_match"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=datetime.now(timezone.utc),
            assigned_to="reviewer-1",
            sla_status=SLAStatus(
                decision_deadline=datetime.now(timezone.utc)
            )
        )

    @pytest.fixture
    def high_item(self):
        """Create high severity review item."""
        return ReviewItem(
            decision_id="dec-dt-high",
            run_id="run-dt-high",
            state="hold",
            composite_score=0.80,
            severity="high",
            top_factors=["uncertainty"],
            artifact_ref="art-2",
            trace_ref="trace-2",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus(
                decision_deadline=datetime.now(timezone.utc)
            )
        )

    @pytest.fixture
    def medium_item(self):
        """Create medium severity review item."""
        return ReviewItem(
            decision_id="dec-dt-medium",
            run_id="run-dt-medium",
            state="warn",
            composite_score=0.60,
            severity="medium",
            top_factors=["risk"],
            artifact_ref="art-3",
            trace_ref="trace-3",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus(
                decision_deadline=datetime.now(timezone.utc)
            )
        )

    def test_decision_timeout_critical(self, critical_item):
        """Decision timeout for critical severity."""
        handler = EscalationHandler()
        pager_callback = Mock()
        webhook_callback = Mock()
        handler.register_pager_callback(pager_callback)
        handler.register_webhook_callback(webhook_callback)

        handler.escalate_decision_timeout(critical_item)

        pager_callback.assert_called_once()
        webhook_callback.assert_called_once()
        assert critical_item.sla_status.escalation_sent is True
        assert critical_item.sla_status.decision_expired is True

    def test_decision_timeout_high(self, high_item):
        """Decision timeout for high severity."""
        handler = EscalationHandler()
        pager_callback = Mock()
        webhook_callback = Mock()
        handler.register_pager_callback(pager_callback)
        handler.register_webhook_callback(webhook_callback)

        handler.escalate_decision_timeout(high_item)

        pager_callback.assert_called_once()
        webhook_callback.assert_called_once()

    def test_decision_timeout_medium_no_pager(self, medium_item):
        """Decision timeout for medium (no pager)."""
        handler = EscalationHandler()
        pager_callback = Mock()
        webhook_callback = Mock()
        handler.register_pager_callback(pager_callback)
        handler.register_webhook_callback(webhook_callback)

        handler.escalate_decision_timeout(medium_item)

        pager_callback.assert_not_called()
        webhook_callback.assert_called_once()

    def test_decision_timeout_security_team(self, critical_item):
        """Decision timeout notifies security team."""
        config = EscalationConfig(
            security_team_contact="security@example.com"
        )
        handler = EscalationHandler(config)
        email_callback = Mock()
        handler.register_email_callback(email_callback)
        handler.register_webhook_callback(Mock())

        handler.escalate_decision_timeout(critical_item)

        email_callback.assert_called_once()
        call_args = email_callback.call_args
        recipients = call_args[0][0]
        assert "security@example.com" in recipients

    def test_decision_timeout_high_no_security(self, high_item):
        """High severity doesn't notify security team."""
        config = EscalationConfig(
            security_team_contact="security@example.com"
        )
        handler = EscalationHandler(config)
        email_callback = Mock()
        handler.register_email_callback(email_callback)
        handler.register_webhook_callback(Mock())

        handler.escalate_decision_timeout(high_item)

        # Email not called for high severity (only critical)
        email_callback.assert_not_called()

    def test_decision_timeout_escalation_data(self, critical_item):
        """Decision timeout escalation data structure."""
        handler = EscalationHandler()
        pager_callback = Mock()
        handler.register_pager_callback(pager_callback)

        handler.escalate_decision_timeout(critical_item)

        call_args = pager_callback.call_args
        data = call_args[0][1]

        assert "decision_id" in data
        assert "timeout_type" in data
        assert data["timeout_type"] == "decision_timeout"
        assert "auto_block_reason" in data
        assert data["auto_block_reason"] == "sla_timeout_fail_closed"
        assert "assigned_to" in data


class TestSendPagerNotification:
    """Tests for _send_pager_notification."""

    def test_send_pager_with_callback(self):
        """Send pager with callback."""
        handler = EscalationHandler()
        callback = Mock()
        handler.register_pager_callback(callback)

        handler._send_pager_notification("test_event", {"key": "value"})

        callback.assert_called_once_with("test_event", {"key": "value"})

    def test_send_pager_callback_exception(self):
        """Pager callback exception is caught."""
        handler = EscalationHandler()
        callback = Mock(side_effect=Exception("Failed"))
        handler.register_pager_callback(callback)

        # Should not raise
        handler._send_pager_notification("test_event", {"key": "value"})

    def test_send_pager_without_callback(self):
        """Send pager without callback logs."""
        config = EscalationConfig(
            pager_duty_integration_key="key-123"
        )
        handler = EscalationHandler(config)

        # Should not raise
        handler._send_pager_notification("test_event", {"key": "value"})


class TestSendWebhookNotification:
    """Tests for _send_webhook_notification."""

    def test_send_webhook_with_callback(self):
        """Send webhook with callback."""
        handler = EscalationHandler()
        callback = Mock()
        handler.register_webhook_callback(callback)

        handler._send_webhook_notification("test_event", {"key": "value"})

        callback.assert_called_once_with("test_event", {"key": "value"})

    def test_send_webhook_callback_exception(self):
        """Webhook callback exception is caught."""
        handler = EscalationHandler()
        callback = Mock(side_effect=Exception("Failed"))
        handler.register_webhook_callback(callback)

        # Should not raise
        handler._send_webhook_notification("test_event", {"key": "value"})

    def test_send_webhook_without_callback(self):
        """Send webhook without callback logs."""
        config = EscalationConfig(
            slack_webhook_url="https://slack.example.com"
        )
        handler = EscalationHandler(config)

        # Should not raise
        handler._send_webhook_notification("test_event", {"key": "value"})


class TestSendEmailNotification:
    """Tests for _send_email_notification."""

    def test_send_email_with_callback(self):
        """Send email with callback."""
        handler = EscalationHandler()
        callback = Mock()
        handler.register_email_callback(callback)

        handler._send_email_notification(
            ["user@example.com"],
            "Test Subject",
            {"key": "value"}
        )

        callback.assert_called_once_with(
            ["user@example.com"],
            "Test Subject",
            {"key": "value"}
        )

    def test_send_email_callback_exception(self):
        """Email callback exception is caught."""
        handler = EscalationHandler()
        callback = Mock(side_effect=Exception("Failed"))
        handler.register_email_callback(callback)

        # Should not raise
        handler._send_email_notification(
            ["user@example.com"],
            "Test Subject",
            {"key": "value"}
        )

    def test_send_email_without_callback(self):
        """Send email without callback logs."""
        config = EscalationConfig(
            email_recipients=["default@example.com"]
        )
        handler = EscalationHandler(config)

        # Should not raise
        handler._send_email_notification(
            ["user@example.com"],
            "Test Subject",
            {"key": "value"}
        )

    def test_send_email_multiple_recipients(self):
        """Send email to multiple recipients."""
        handler = EscalationHandler()
        callback = Mock()
        handler.register_email_callback(callback)

        handler._send_email_notification(
            ["user1@example.com", "user2@example.com"],
            "Test Subject",
            {"key": "value"}
        )

        call_args = callback.call_args
        recipients = call_args[0][0]
        assert len(recipients) == 2


class TestEscalationIntegration:
    """Integration-like tests."""

    def test_full_ack_timeout_workflow(self):
        """Full ACK timeout escalation workflow."""
        item = ReviewItem(
            decision_id="dec-int-ack",
            run_id="run-int",
            state="block",
            composite_score=0.95,
            severity="critical",
            top_factors=["secret"],
            artifact_ref="art-int",
            trace_ref="trace-int",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus(ack_deadline=datetime.now(timezone.utc))
        )

        config = EscalationConfig(
            on_call_backup_reviewer="backup@example.com"
        )
        handler = EscalationHandler(config)

        pager = Mock()
        webhook = Mock()
        email = Mock()

        handler.register_pager_callback(pager)
        handler.register_webhook_callback(webhook)
        handler.register_email_callback(email)

        handler.escalate_ack_timeout(item)

        assert pager.called
        assert webhook.called
        assert email.called
        assert item.sla_status.escalation_sent is True

    def test_full_decision_timeout_workflow(self):
        """Full decision timeout escalation workflow."""
        item = ReviewItem(
            decision_id="dec-int-decision",
            run_id="run-int",
            state="hold",
            composite_score=0.85,
            severity="critical",
            top_factors=["risk"],
            artifact_ref="art-int",
            trace_ref="trace-int",
            created_at=datetime.now(timezone.utc),
            assigned_to="reviewer-1",
            sla_status=SLAStatus(decision_deadline=datetime.now(timezone.utc))
        )

        config = EscalationConfig(
            security_team_contact="security@example.com"
        )
        handler = EscalationHandler(config)

        pager = Mock()
        webhook = Mock()
        email = Mock()

        handler.register_pager_callback(pager)
        handler.register_webhook_callback(webhook)
        handler.register_email_callback(email)

        handler.escalate_decision_timeout(item)

        assert pager.called
        assert webhook.called
        assert email.called
        assert item.sla_status.decision_expired is True

    def test_severity_based_routing(self):
        """Severity based routing for different severities."""
        handler = EscalationHandler()
        pager = Mock()
        handler.register_pager_callback(pager)

        # Critical - pager called
        critical_item = ReviewItem(
            decision_id="dec-route-c",
            run_id="run-route",
            state="block",
            composite_score=0.95,
            severity="critical",
            top_factors=["secret"],
            artifact_ref="art-route",
            trace_ref="trace-route",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus()
        )
        handler.escalate_ack_timeout(critical_item)
        assert pager.call_count == 1

        # Medium - pager not called
        medium_item = ReviewItem(
            decision_id="dec-route-m",
            run_id="run-route",
            state="warn",
            composite_score=0.60,
            severity="medium",
            top_factors=["risk"],
            artifact_ref="art-route",
            trace_ref="trace-route",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus()
        )
        handler.escalate_ack_timeout(medium_item)
        assert pager.call_count == 1  # Not incremented