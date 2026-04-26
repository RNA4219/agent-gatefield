"""
Tests for SLA Handler - Timeout Handling and Deadline Management.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

from src.core.sla_handler import (
    SLAHandler,
    calculate_sla_deadlines,
    check_sla_timeout,
    handle_sla_timeout,
)


class TestSLAHandlerInit:
    """Tests for SLAHandler initialization."""

    def test_default_init(self):
        """Default initialization."""
        handler = SLAHandler()
        assert handler.critical_ack_minutes == 15
        assert handler.critical_decision_minutes == 60
        assert handler.high_ack_minutes == 60
        assert handler.high_decision_minutes == 240

    def test_custom_init(self):
        """Custom initialization."""
        handler = SLAHandler(
            critical_ack_minutes=30,
            critical_decision_minutes=120,
            high_ack_minutes=90,
            high_decision_minutes=360
        )
        assert handler.critical_ack_minutes == 30
        assert handler.critical_decision_minutes == 120


class TestCalculateDeadlines:
    """Tests for calculate_deadlines."""

    def test_critical_severity(self):
        """Calculate deadlines for critical."""
        handler = SLAHandler()
        created = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        deadlines = handler.calculate_deadlines('critical', created)

        assert deadlines['sla_ack_deadline'] == created + timedelta(minutes=15)
        assert deadlines['sla_decision_deadline'] == created + timedelta(minutes=60)

    def test_high_severity(self):
        """Calculate deadlines for high."""
        handler = SLAHandler()
        created = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        deadlines = handler.calculate_deadlines('high', created)

        assert deadlines['sla_ack_deadline'] == created + timedelta(minutes=60)
        assert deadlines['sla_decision_deadline'] == created + timedelta(minutes=240)

    def test_medium_severity(self):
        """Calculate deadlines for medium (business day)."""
        handler = SLAHandler()
        created = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)  # Monday
        deadlines = handler.calculate_deadlines('medium', created)

        # Medium: same business day for ACK, next business day for decision
        assert deadlines['sla_ack_deadline'] is not None
        assert deadlines['sla_decision_deadline'] is not None

    def test_low_severity(self):
        """Calculate deadlines for low (no SLA)."""
        handler = SLAHandler()
        deadlines = handler.calculate_deadlines('low')

        assert deadlines['sla_ack_deadline'] is None
        assert deadlines['sla_decision_deadline'] is None

    def test_default_created_at(self):
        """Default created_at uses now."""
        handler = SLAHandler()
        deadlines = handler.calculate_deadlines('critical')
        assert deadlines['sla_ack_deadline'] is not None


class TestCheckTimeout:
    """Tests for check_timeout."""

    def test_no_timeout_critical(self):
        """No timeout when within deadline."""
        handler = SLAHandler()
        created = datetime.now(timezone.utc) - timedelta(minutes=5)
        ack_taken = datetime.now(timezone.utc)

        timeout, type_ = handler.check_timeout('critical', created, ack_taken)
        assert timeout is False
        assert type_ is None

    def test_ack_timeout_critical(self):
        """ACK timeout for critical."""
        handler = SLAHandler()
        created = datetime.now(timezone.utc) - timedelta(minutes=20)  # > 15 min
        ack_taken = None

        timeout, type_ = handler.check_timeout('critical', created, ack_taken)
        assert timeout is True
        assert type_ == 'ack_timeout'

    def test_decision_timeout_critical(self):
        """Decision timeout for critical."""
        handler = SLAHandler()
        created = datetime.now(timezone.utc) - timedelta(minutes=70)  # > 60 min
        ack_taken = datetime.now(timezone.utc) - timedelta(minutes=50)

        timeout, type_ = handler.check_timeout('critical', created, ack_taken)
        assert timeout is True
        assert type_ == 'decision_timeout'

    def test_ack_timeout_high(self):
        """ACK timeout for high."""
        handler = SLAHandler()
        created = datetime.now(timezone.utc) - timedelta(minutes=70)  # > 60 min
        ack_taken = None

        timeout, type_ = handler.check_timeout('high', created, ack_taken)
        assert timeout is True
        assert type_ == 'ack_timeout'

    def test_no_timeout_medium_low(self):
        """No timeout check for medium/low."""
        handler = SLAHandler()
        created = datetime.now(timezone.utc) - timedelta(hours=10)

        timeout, type_ = handler.check_timeout('medium', created)
        assert timeout is False

        timeout, type_ = handler.check_timeout('low', created)
        assert timeout is False


class TestGetNextBusinessDay:
    """Tests for _get_next_business_day."""

    def test_monday_stays_monday(self):
        """Monday + 0 days stays Monday."""
        handler = SLAHandler()
        monday = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)  # Monday
        result = handler._get_next_business_day(monday, 0)
        assert result.weekday() == 0  # Monday

    def test_skip_saturday(self):
        """Friday + 1 goes to Monday (skip Saturday)."""
        handler = SLAHandler()
        friday = datetime(2024, 1, 5, 10, 0, 0, tzinfo=timezone.utc)  # Friday
        result = handler._get_next_business_day(friday, 1)
        assert result.weekday() == 0  # Monday

    def test_skip_sunday(self):
        """Friday + 2 goes to Monday (skip Saturday, Sunday)."""
        handler = SLAHandler()
        friday = datetime(2024, 1, 5, 10, 0, 0, tzinfo=timezone.utc)  # Friday
        result = handler._get_next_business_day(friday, 2)
        assert result.weekday() == 0  # Monday

    def test_multiple_days(self):
        """Add multiple business days."""
        handler = SLAHandler()
        monday = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        result = handler._get_next_business_day(monday, 5)
        # Mon + 5 = Sat, skips Sat+Sun = Monday
        assert result.weekday() == 0


class TestHandleTimeout:
    """Tests for handle_timeout."""

    def test_handle_timeout_fail_closed(self):
        """Handle timeout creates BLOCK decision."""
        handler = SLAHandler()

        mock_gate_state = Mock()
        mock_gate_state.BLOCK = 'block'

        mock_decision_result = Mock()

        result = handler.handle_timeout(
            decision_id='dec-1',
            timeout_type='ack_timeout',
            sla_deadline=datetime.now(timezone.utc),
            escalation_target='oncall',
            gate_state_cls=mock_gate_state,
            decision_result_cls=mock_decision_result,
            threshold_version='v1'
        )

        # Should call decision_result_cls with BLOCK
        mock_decision_result.assert_called_once()
        call_kwargs = mock_decision_result.call_args[1]
        assert call_kwargs['decision'] == 'block'
        assert call_kwargs['hard_override_reason'] == 'sla_timeout_fail_closed'

    def test_handle_decision_timeout(self):
        """Handle decision timeout."""
        handler = SLAHandler()

        mock_gate_state = Mock()
        mock_gate_state.BLOCK = 'block'

        mock_decision_result = Mock()

        result = handler.handle_timeout(
            decision_id='dec-2',
            timeout_type='decision_timeout',
            sla_deadline=datetime.now(timezone.utc),
            escalation_target='manager',
            gate_state_cls=mock_gate_state,
            decision_result_cls=mock_decision_result,
            threshold_version='v1'
        )

        call_kwargs = mock_decision_result.call_args[1]
        assert call_kwargs['transition_reason'] == 'decision_timeout_fail_closed'


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_calculate_sla_deadlines_func(self):
        """calculate_sla_deadlines function."""
        deadlines = calculate_sla_deadlines('critical')
        assert deadlines['sla_ack_deadline'] is not None

    def test_calculate_sla_deadlines_with_handler(self):
        """calculate_sla_deadlines with custom handler."""
        handler = SLAHandler(critical_ack_minutes=30)
        deadlines = calculate_sla_deadlines('critical', sla_handler=handler)
        # Should use custom timeout
        assert deadlines is not None

    def test_check_sla_timeout_func(self):
        """check_sla_timeout function."""
        created = datetime.now(timezone.utc) - timedelta(minutes=20)
        timeout, type_ = check_sla_timeout('critical', created)
        assert timeout is True

    def test_check_sla_timeout_no_timeout(self):
        """check_sla_timeout when no timeout."""
        created = datetime.now(timezone.utc)
        timeout, type_ = check_sla_timeout('critical', created)
        assert timeout is False

    def test_handle_sla_timeout_func(self):
        """handle_sla_timeout function."""
        mock_gate_state = Mock()
        mock_gate_state.BLOCK = 'block'
        mock_decision_result = Mock()

        result = handle_sla_timeout(
            decision_id='dec-1',
            timeout_type='ack_timeout',
            sla_deadline=datetime.now(timezone.utc),
            escalation_target='oncall',
            gate_state_cls=mock_gate_state,
            decision_result_cls=mock_decision_result,
            threshold_version='v1'
        )

        mock_decision_result.assert_called_once()


class TestSLAHandlerIntegration:
    """Integration-like tests."""

    def test_full_workflow(self):
        """Full SLA workflow."""
        handler = SLAHandler()
        created = datetime.now(timezone.utc)

        # Calculate deadlines
        deadlines = handler.calculate_deadlines('critical', created)
        assert deadlines['sla_ack_deadline'] > created

        # Check timeout (should be False initially)
        timeout, type_ = handler.check_timeout('critical', created)
        assert timeout is False

        # Simulate time passing (ACK timeout)
        old_created = created - timedelta(minutes=20)
        timeout, type_ = handler.check_timeout('critical', old_created)
        assert timeout is True
        assert type_ == 'ack_timeout'

    def test_severity_hierarchy(self):
        """SLA deadlines follow severity hierarchy."""
        handler = SLAHandler()
        created = datetime.now(timezone.utc)

        critical_dl = handler.calculate_deadlines('critical', created)
        high_dl = handler.calculate_deadlines('high', created)

        # Critical has tighter deadlines than high
        assert critical_dl['sla_ack_deadline'] < high_dl['sla_ack_deadline']
        assert critical_dl['sla_decision_deadline'] < high_dl['sla_decision_deadline']