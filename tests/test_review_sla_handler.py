"""
Tests for Review SLA Handler - deadline calculation and compliance checking.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from src.review.sla_handler import (
    calculate_sla_deadlines,
    check_sla_compliance,
    get_sla_status_summary,
    get_elapsed_minutes,
)
from src.review.constants import SLA_TARGETS, SLAType, Severity
from src.review.dataclasses import ReviewItem, SLAStatus


class TestCalculateSLADeadlines:
    """Tests for calculate_sla_deadlines function."""

    @pytest.fixture
    def critical_item(self):
        """Create critical severity item."""
        return ReviewItem(
            decision_id="dec-critical",
            run_id="run-1",
            state="block",
            composite_score=0.95,
            severity="critical",
            top_factors=["secret"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus()
        )

    @pytest.fixture
    def high_item(self):
        """Create high severity item."""
        return ReviewItem(
            decision_id="dec-high",
            run_id="run-2",
            state="hold",
            composite_score=0.80,
            severity="high",
            top_factors=["risk"],
            artifact_ref="art-2",
            trace_ref="trace-2",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus()
        )

    @pytest.fixture
    def medium_item(self):
        """Create medium severity item."""
        return ReviewItem(
            decision_id="dec-medium",
            run_id="run-3",
            state="warn",
            composite_score=0.60,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-3",
            trace_ref="trace-3",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus()
        )

    @pytest.fixture
    def low_item(self):
        """Create low severity item."""
        return ReviewItem(
            decision_id="dec-low",
            run_id="run-4",
            state="pass",
            composite_score=0.40,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-4",
            trace_ref="trace-4",
            created_at=datetime.now(timezone.utc),
            sla_status=SLAStatus()
        )

    def test_calculate_critical_sla(self, critical_item):
        """Calculate SLA for critical severity."""
        calculate_sla_deadlines(critical_item)

        assert critical_item.sla_status.ack_deadline is not None
        assert critical_item.sla_status.decision_deadline is not None
        assert critical_item.sla_ack_deadline is not None
        assert critical_item.sla_deadline is not None

    def test_calculate_high_sla(self, high_item):
        """Calculate SLA for high severity."""
        calculate_sla_deadlines(high_item)

        assert high_item.sla_status.ack_deadline is not None
        assert high_item.sla_status.decision_deadline is not None

    def test_calculate_medium_sla(self, medium_item):
        """Calculate SLA for medium severity."""
        calculate_sla_deadlines(medium_item)

        assert medium_item.sla_status.ack_deadline is not None
        assert medium_item.sla_status.decision_deadline is not None

    def test_calculate_low_sla(self, low_item):
        """Calculate SLA for low severity (no deadlines)."""
        calculate_sla_deadlines(low_item)

        # Low severity has no ACK deadline
        assert low_item.sla_status.ack_deadline is None
        assert low_item.sla_status.decision_deadline is None

    def test_sla_targets_critical(self, critical_item):
        """SLA targets for critical."""
        calculate_sla_deadlines(critical_item)

        targets = SLA_TARGETS[Severity.CRITICAL]
        assert targets[SLAType.ACK] == timedelta(minutes=15)
        assert targets[SLAType.DECISION] == timedelta(minutes=60)

    def test_sla_targets_high(self, high_item):
        """SLA targets for high."""
        targets = SLA_TARGETS[Severity.HIGH]
        assert targets[SLAType.ACK] == timedelta(minutes=60)
        assert targets[SLAType.DECISION] == timedelta(minutes=240)

    def test_flattened_fields_set(self, critical_item):
        """Flattened SLA fields are set."""
        calculate_sla_deadlines(critical_item)

        # Flattened fields match sla_status fields
        assert critical_item.sla_ack_deadline == critical_item.sla_status.ack_deadline
        assert critical_item.sla_deadline == critical_item.sla_status.decision_deadline


class TestCheckSLACompliance:
    """Tests for check_sla_compliance function."""

    @pytest.fixture
    def compliant_item(self):
        """Create item with compliant SLA."""
        now = datetime.now(timezone.utc)
        return ReviewItem(
            decision_id="dec-compliant",
            run_id="run-1",
            state="block",
            composite_score=0.95,
            severity="critical",
            top_factors=["secret"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=now,
            taken_at=now + timedelta(minutes=5),  # ACK within deadline
            sla_status=SLAStatus(
                ack_deadline=now + timedelta(minutes=15),
                decision_deadline=now + timedelta(minutes=60)
            )
        )

    @pytest.fixture
    def ack_expired_item(self):
        """Create item with ACK expired."""
        now = datetime.now(timezone.utc)
        return ReviewItem(
            decision_id="dec-ack-exp",
            run_id="run-2",
            state="hold",
            composite_score=0.80,
            severity="critical",
            top_factors=["risk"],
            artifact_ref="art-2",
            trace_ref="trace-2",
            created_at=now,
            taken_at=now + timedelta(minutes=20),  # ACK after deadline
            sla_status=SLAStatus(
                ack_deadline=now + timedelta(minutes=15),
                decision_deadline=now + timedelta(minutes=60)
            )
        )

    @pytest.fixture
    def decision_expired_item(self):
        """Create item with decision expired."""
        now = datetime.now(timezone.utc)
        return ReviewItem(
            decision_id="dec-dec-exp",
            run_id="run-3",
            state="hold",
            composite_score=0.80,
            severity="critical",
            top_factors=["risk"],
            artifact_ref="art-3",
            trace_ref="trace-3",
            created_at=now,
            taken_at=now + timedelta(minutes=5),
            sla_status=SLAStatus(
                ack_deadline=now + timedelta(minutes=15),
                decision_deadline=now + timedelta(minutes=30)
            )
        )

    def test_compliant_sla(self, compliant_item):
        """Compliant SLA returns True."""
        resolved_at = datetime.now(timezone.utc) + timedelta(minutes=45)
        result = check_sla_compliance(compliant_item, resolved_at)
        assert result is True

    def test_ack_expired(self, ack_expired_item):
        """ACK expired returns False."""
        resolved_at = datetime.now(timezone.utc) + timedelta(minutes=50)
        result = check_sla_compliance(ack_expired_item, resolved_at)
        assert result is False

    def test_decision_expired(self, decision_expired_item):
        """Decision expired returns False."""
        resolved_at = datetime.now(timezone.utc) + timedelta(minutes=40)
        result = check_sla_compliance(decision_expired_item, resolved_at)
        assert result is False

    def test_no_ack_deadline(self):
        """No ACK deadline skips ACK check."""
        now = datetime.now(timezone.utc)
        item = ReviewItem(
            decision_id="dec-no-ack",
            run_id="run-1",
            state="pass",
            composite_score=0.40,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=now,
            taken_at=now + timedelta(minutes=5),
            sla_status=SLAStatus(ack_deadline=None)
        )

        resolved_at = now + timedelta(minutes=10)
        result = check_sla_compliance(item, resolved_at)
        assert result is True

    def test_no_decision_deadline(self):
        """No decision deadline skips decision check."""
        now = datetime.now(timezone.utc)
        item = ReviewItem(
            decision_id="dec-no-dec",
            run_id="run-1",
            state="pass",
            composite_score=0.40,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=now,
            sla_status=SLAStatus(decision_deadline=None)
        )

        resolved_at = now + timedelta(minutes=100)
        result = check_sla_compliance(item, resolved_at)
        assert result is True

    def test_no_taken_at(self):
        """No taken_at skips ACK check."""
        now = datetime.now(timezone.utc)
        item = ReviewItem(
            decision_id="dec-no-taken",
            run_id="run-1",
            state="hold",
            composite_score=0.80,
            severity="high",
            top_factors=["test"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=now,
            taken_at=None,
            sla_status=SLAStatus(
                ack_deadline=now + timedelta(minutes=60),
                decision_deadline=now + timedelta(minutes=240)
            )
        )

        resolved_at = now + timedelta(minutes=120)
        result = check_sla_compliance(item, resolved_at)
        # ACK check skipped since taken_at is None
        assert result is True


class TestGetSLAStatusSummary:
    """Tests for get_sla_status_summary function."""

    def test_summary_basic(self):
        """Basic SLA status summary."""
        now = datetime.now(timezone.utc)
        item = ReviewItem(
            decision_id="dec-summary",
            run_id="run-1",
            state="hold",
            composite_score=0.80,
            severity="high",
            top_factors=["test"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=now,
            sla_status=SLAStatus(
                ack_deadline=now + timedelta(minutes=60),
                decision_deadline=now + timedelta(minutes=240)
            )
        )

        summary = get_sla_status_summary(item)

        assert summary["decision_id"] == "dec-summary"
        assert summary["severity"] == "high"
        assert summary["ack_deadline"] is not None
        assert summary["decision_deadline"] is not None

    def test_summary_with_acked_at(self):
        """Summary includes acked_at."""
        now = datetime.now(timezone.utc)
        item = ReviewItem(
            decision_id="dec-acked",
            run_id="run-1",
            state="hold",
            composite_score=0.80,
            severity="high",
            top_factors=["test"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=now,
            sla_status=SLAStatus(
                ack_deadline=now + timedelta(minutes=60),
                decision_deadline=now + timedelta(minutes=240),
                acked_at=now + timedelta(minutes=10)
            )
        )

        summary = get_sla_status_summary(item)
        assert summary["acked_at"] is not None

    def test_summary_target_minutes(self):
        """Summary includes target minutes."""
        now = datetime.now(timezone.utc)
        item = ReviewItem(
            decision_id="dec-target",
            run_id="run-1",
            state="block",
            composite_score=0.95,
            severity="critical",
            top_factors=["secret"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=now,
            sla_status=SLAStatus(
                ack_deadline=now + timedelta(minutes=15),
                decision_deadline=now + timedelta(minutes=60)
            )
        )

        summary = get_sla_status_summary(item)
        assert summary["ack_target_minutes"] == 15.0
        assert summary["decision_target_minutes"] == 60.0

    def test_summary_low_severity(self):
        """Summary for low severity (no deadlines)."""
        now = datetime.now(timezone.utc)
        item = ReviewItem(
            decision_id="dec-low",
            run_id="run-1",
            state="pass",
            composite_score=0.40,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=now,
            sla_status=SLAStatus()
        )

        summary = get_sla_status_summary(item)
        assert summary["ack_target_minutes"] is None
        assert summary["decision_target_minutes"] is None

    def test_summary_remaining_minutes(self):
        """Summary includes remaining minutes."""
        now = datetime.now(timezone.utc)
        item = ReviewItem(
            decision_id="dec-remain",
            run_id="run-1",
            state="hold",
            composite_score=0.80,
            severity="high",
            top_factors=["test"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=now,
            sla_status=SLAStatus(
                ack_deadline=now + timedelta(minutes=60),
                decision_deadline=now + timedelta(minutes=240)
            )
        )

        summary = get_sla_status_summary(item)
        # Remaining minutes should be positive
        assert summary["ack_remaining_minutes"] >= 0
        assert summary["decision_remaining_minutes"] >= 0


class TestGetElapsedMinutes:
    """Tests for get_elapsed_minutes function."""

    def test_elapsed_minutes_basic(self):
        """Basic elapsed minutes calculation."""
        created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        elapsed = get_elapsed_minutes(created_at)
        assert elapsed >= 30

    def test_elapsed_minutes_zero(self):
        """Elapsed minutes for recent creation."""
        created_at = datetime.now(timezone.utc)
        elapsed = get_elapsed_minutes(created_at)
        assert elapsed == 0

    def test_elapsed_minutes_hours(self):
        """Elapsed minutes for hours."""
        created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        elapsed = get_elapsed_minutes(created_at)
        assert elapsed >= 120


class TestSLAIntegration:
    """Integration-like tests."""

    def test_full_sla_workflow(self):
        """Full SLA workflow."""
        # Create item
        now = datetime.now(timezone.utc)
        item = ReviewItem(
            decision_id="dec-workflow",
            run_id="run-workflow",
            state="block",
            composite_score=0.95,
            severity="critical",
            top_factors=["secret"],
            artifact_ref="art-workflow",
            trace_ref="trace-workflow",
            created_at=now,
            sla_status=SLAStatus()
        )

        # Calculate deadlines
        calculate_sla_deadlines(item)

        assert item.sla_status.ack_deadline is not None
        assert item.sla_status.decision_deadline is not None

        # Get elapsed time
        elapsed = get_elapsed_minutes(item.created_at)
        assert elapsed >= 0

        # Get summary
        summary = get_sla_status_summary(item)
        assert summary["severity"] == "critical"

        # Simulate ACK
        item.taken_at = now + timedelta(minutes=5)

        # Check compliance (resolved within deadline)
        resolved_at = now + timedelta(minutes=45)
        compliant = check_sla_compliance(item, resolved_at)
        assert compliant is True