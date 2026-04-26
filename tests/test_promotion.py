"""
Tests for Judgment Log Promotion - review item promotion to knowledge base.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock

from src.review.promotion import JudgmentLogPromoter
from src.review.constants import ReviewDecision
from src.review.dataclasses import ReviewItem, ReviewAction, SLAStatus


class TestJudgmentLogPromoterInit:
    """Tests for JudgmentLogPromoter initialization."""

    def test_default_init(self):
        """Default initialization."""
        promoter = JudgmentLogPromoter()
        assert promoter._promote_callback is None

    def test_callback_registration(self):
        """Callback can be registered."""
        promoter = JudgmentLogPromoter()
        callback = Mock()
        promoter.register_promote_callback(callback)
        assert promoter._promote_callback is callback


class TestPromoteToJudgmentLog:
    """Tests for promote_to_judgment_log method."""

    @pytest.fixture
    def review_item(self):
        """Create a test review item."""
        return ReviewItem(
            decision_id="dec-1",
            run_id="run-1",
            state="block",
            composite_score=0.95,
            severity="high",
            top_factors=["taboo_match"],
            artifact_ref="art-1",
            trace_ref="trace-1",
            created_at=datetime.now(timezone.utc),
            exemplar_refs=["ex-1", "ex-2"]
        )

    @pytest.fixture
    def approve_action(self):
        """Create an approve action."""
        return ReviewAction(
            decision_id="dec-1",
            reviewer="reviewer-1",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.APPROVE,
            comment="Approved after review"
        )

    @pytest.fixture
    def reject_action(self):
        """Create a reject action."""
        return ReviewAction(
            decision_id="dec-1",
            reviewer="reviewer-1",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.REJECT,
            comment="Rejected"
        )

    @pytest.fixture
    def judgment_note_action(self):
        """Create a judgment note action."""
        return ReviewAction(
            decision_id="dec-1",
            reviewer="reviewer-1",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.ADD_JUDGMENT_NOTE,
            judgment_note="Important pattern"
        )

    @pytest.fixture
    def recalibrate_action(self):
        """Create a recalibrate action (not promoted)."""
        return ReviewAction(
            decision_id="dec-1",
            reviewer="reviewer-1",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.RECALIBRATE
        )

    def test_promote_approve(self, review_item, approve_action):
        """Promote approve action."""
        promoter = JudgmentLogPromoter()
        result = promoter.promote_to_judgment_log(review_item, approve_action)
        assert result is True
        assert approve_action.judgment_log_promoted is True

    def test_promote_reject(self, review_item, reject_action):
        """Promote reject action."""
        promoter = JudgmentLogPromoter()
        result = promoter.promote_to_judgment_log(review_item, reject_action)
        assert result is True
        assert reject_action.judgment_log_promoted is True

    def test_promote_judgment_note(self, review_item, judgment_note_action):
        """Promote judgment note action."""
        promoter = JudgmentLogPromoter()
        result = promoter.promote_to_judgment_log(review_item, judgment_note_action)
        assert result is True
        assert judgment_note_action.judgment_log_promoted is True

    def test_no_promote_recalibrate(self, review_item, recalibrate_action):
        """Recalibrate action not promoted."""
        promoter = JudgmentLogPromoter()
        result = promoter.promote_to_judgment_log(review_item, recalibrate_action)
        assert result is False

    def test_promote_with_callback(self, review_item, approve_action):
        """Promote with registered callback."""
        promoter = JudgmentLogPromoter()
        callback = Mock()
        promoter.register_promote_callback(callback)

        result = promoter.promote_to_judgment_log(review_item, approve_action)
        assert result is True
        callback.assert_called_once()

    def test_callback_failure_returns_false(self, review_item, approve_action):
        """Callback failure returns False."""
        promoter = JudgmentLogPromoter()
        callback = Mock(side_effect=Exception("Failed"))
        promoter.register_promote_callback(callback)

        result = promoter.promote_to_judgment_log(review_item, approve_action)
        assert result is False

    def test_promotion_data_structure(self, review_item, approve_action):
        """Promotion data has correct structure."""
        promoter = JudgmentLogPromoter()
        callback = Mock()
        promoter.register_promote_callback(callback)

        promoter.promote_to_judgment_log(review_item, approve_action)

        call_args = callback.call_args
        promotion_data = call_args[0][1]  # Second argument is data dict

        assert "decision_id" in promotion_data
        assert "run_id" in promotion_data
        assert "review_id" in promotion_data
        assert "original_state" in promotion_data
        assert "composite_score" in promotion_data
        assert "reviewer_decision" in promotion_data
        assert "promoted_at" in promotion_data

    def test_promote_with_correction(self, review_item):
        """Promote with correction data."""
        action = ReviewAction(
            decision_id="dec-1",
            reviewer="reviewer-1",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.APPROVE,
            correction={"threshold_adjustment": 0.05}
        )

        promoter = JudgmentLogPromoter()
        callback = Mock()
        promoter.register_promote_callback(callback)

        result = promoter.promote_to_judgment_log(review_item, action)
        assert result is True

        call_args = callback.call_args
        promotion_data = call_args[0][1]
        assert promotion_data["correction"] is not None

    def test_promote_with_action_type_only(self, review_item):
        """Promote with action_type string instead of decision enum."""
        action = ReviewAction(
            decision_id="dec-1",
            reviewer="reviewer-1",
            created_at=datetime.now(timezone.utc),
            action_type="approve",
            decision=None
        )

        promoter = JudgmentLogPromoter()
        result = promoter.promote_to_judgment_log(review_item, action)
        assert result is True

    def test_promote_with_invalid_action_type(self, review_item):
        """Invalid action_type returns False."""
        action = ReviewAction(
            decision_id="dec-1",
            reviewer="reviewer-1",
            created_at=datetime.now(timezone.utc),
            action_type="invalid_action",
            decision=None
        )

        promoter = JudgmentLogPromoter()
        result = promoter.promote_to_judgment_log(review_item, action)
        assert result is False

    def test_promote_empty_decision_returns_false(self, review_item):
        """Empty decision and action_type returns False."""
        action = ReviewAction(
            decision_id="dec-1",
            reviewer="reviewer-1",
            created_at=datetime.now(timezone.utc),
            decision=None,
            action_type=""
        )

        promoter = JudgmentLogPromoter()
        result = promoter.promote_to_judgment_log(review_item, action)
        assert result is False


class TestShouldPromote:
    """Tests for should_promote method."""

    def test_should_promote_approve(self):
        """Approve should be promoted."""
        action = ReviewAction(
            decision_id="dec-1",
            reviewer="rev-1",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.APPROVE
        )
        promoter = JudgmentLogPromoter()
        assert promoter.should_promote(action) is True

    def test_should_promote_reject(self):
        """Reject should be promoted."""
        action = ReviewAction(
            decision_id="dec-1",
            reviewer="rev-1",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.REJECT
        )
        promoter = JudgmentLogPromoter()
        assert promoter.should_promote(action) is True

    def test_should_promote_judgment_note(self):
        """Judgment note should be promoted."""
        action = ReviewAction(
            decision_id="dec-1",
            reviewer="rev-1",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.ADD_JUDGMENT_NOTE
        )
        promoter = JudgmentLogPromoter()
        assert promoter.should_promote(action) is True

    def test_should_not_promote_recalibrate(self):
        """Recalibrate should not be promoted."""
        action = ReviewAction(
            decision_id="dec-1",
            reviewer="rev-1",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.RECALIBRATE
        )
        promoter = JudgmentLogPromoter()
        assert promoter.should_promote(action) is False

    def test_should_not_promote_artifact_correction(self):
        """Artifact correction should not be promoted."""
        action = ReviewAction(
            decision_id="dec-1",
            reviewer="rev-1",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.REQUEST_ARTIFACT_CORRECTION
        )
        promoter = JudgmentLogPromoter()
        assert promoter.should_promote(action) is False

    def test_should_promote_with_action_type(self):
        """Should promote with action_type string."""
        action = ReviewAction(
            decision_id="dec-1",
            reviewer="rev-1",
            created_at=datetime.now(timezone.utc),
            action_type="approve",
            decision=None
        )
        promoter = JudgmentLogPromoter()
        assert promoter.should_promote(action) is True

    def test_should_not_promote_invalid_action_type(self):
        """Invalid action_type should not promote."""
        action = ReviewAction(
            decision_id="dec-1",
            reviewer="rev-1",
            created_at=datetime.now(timezone.utc),
            action_type="unknown",
            decision=None
        )
        promoter = JudgmentLogPromoter()
        assert promoter.should_promote(action) is False


class TestCreatePromotionData:
    """Tests for create_promotion_data method."""

    @pytest.fixture
    def review_item(self):
        """Create test review item."""
        return ReviewItem(
            decision_id="dec-create",
            run_id="run-create",
            state="warn",
            composite_score=0.75,
            severity="medium",
            top_factors=["uncertainty"],
            artifact_ref="art-create",
            trace_ref="trace-create",
            created_at=datetime.now(timezone.utc),
            exemplar_refs=["ex-a"]
        )

    @pytest.fixture
    def action(self):
        """Create test action."""
        return ReviewAction(
            decision_id="dec-create",
            reviewer="rev-create",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.APPROVE,
            comment="Looks good",
            previous_decision="warn",
            new_decision="pass"
        )

    def test_create_promotion_data_basic(self, review_item, action):
        """Create basic promotion data."""
        promoter = JudgmentLogPromoter()
        data = promoter.create_promotion_data(review_item, action)

        assert data["decision_id"] == "dec-create"
        assert data["run_id"] == "run-create"
        assert data["review_id"] is not None
        assert data["original_state"] == "warn"
        assert data["composite_score"] == 0.75

    def test_create_promotion_data_reviewer(self, review_item, action):
        """Promotion data includes reviewer."""
        promoter = JudgmentLogPromoter()
        data = promoter.create_promotion_data(review_item, action)

        assert data["reviewer_id"] == "rev-create"
        assert data["reviewer_comment"] == "Looks good"

    def test_create_promotion_data_decision(self, review_item, action):
        """Promotion data includes decision."""
        promoter = JudgmentLogPromoter()
        data = promoter.create_promotion_data(review_item, action)

        assert data["reviewer_decision"] == "approve"

    def test_create_promotion_data_state_changes(self, review_item, action):
        """Promotion data includes state changes."""
        promoter = JudgmentLogPromoter()
        data = promoter.create_promotion_data(review_item, action)

        assert data["previous_decision"] == "warn"
        assert data["new_decision"] == "pass"

    def test_create_promotion_data_with_correction(self, review_item):
        """Promotion data includes correction."""
        action = ReviewAction(
            decision_id="dec-create",
            reviewer="rev-create",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.APPROVE,
            correction={"threshold": 0.05}
        )

        promoter = JudgmentLogPromoter()
        data = promoter.create_promotion_data(review_item, action)

        assert data["correction"] is not None
        assert data["correction_json"] is not None

    def test_create_promotion_data_correction_json_fallback(self, review_item):
        """Promotion data uses correction_json fallback."""
        action = ReviewAction(
            decision_id="dec-create",
            reviewer="rev-create",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.APPROVE,
            correction_json={"threshold": 0.05}
        )

        promoter = JudgmentLogPromoter()
        data = promoter.create_promotion_data(review_item, action)

        assert data["correction"] is not None

    def test_create_promotion_data_has_timestamp(self, review_item, action):
        """Promotion data has timestamp."""
        promoter = JudgmentLogPromoter()
        data = promoter.create_promotion_data(review_item, action)

        assert "promoted_at" in data
        assert data["promoted_at"] is not None

    def test_create_promotion_data_exemplar_refs(self, review_item, action):
        """Promotion data includes exemplar refs."""
        promoter = JudgmentLogPromoter()
        data = promoter.create_promotion_data(review_item, action)

        assert data["exemplar_refs"] == ["ex-a"]

    def test_create_promotion_data_with_action_type(self, review_item):
        """Promotion data with action_type string."""
        action = ReviewAction(
            decision_id="dec-create",
            reviewer="rev-create",
            created_at=datetime.now(timezone.utc),
            action_type="reject",
            decision=None
        )

        promoter = JudgmentLogPromoter()
        data = promoter.create_promotion_data(review_item, action)

        assert data["reviewer_decision"] == "reject"

    def test_create_promotion_data_invalid_action_type(self, review_item):
        """Promotion data with invalid action_type uses action_type string."""
        action = ReviewAction(
            decision_id="dec-create",
            reviewer="rev-create",
            created_at=datetime.now(timezone.utc),
            action_type="unknown",
            decision=None
        )

        promoter = JudgmentLogPromoter()
        data = promoter.create_promotion_data(review_item, action)

        assert data["reviewer_decision"] == "unknown"


class TestPromotionIntegration:
    """Integration-like tests."""

    def test_full_promotion_workflow(self):
        """Full promotion workflow."""
        item = ReviewItem(
            decision_id="dec-full",
            run_id="run-full",
            state="block",
            composite_score=0.90,
            severity="critical",
            top_factors=["secret_found"],
            artifact_ref="art-full",
            trace_ref="trace-full",
            created_at=datetime.now(timezone.utc)
        )

        action = ReviewAction(
            decision_id="dec-full",
            reviewer="rev-full",
            created_at=datetime.now(timezone.utc),
            decision=ReviewDecision.ADD_JUDGMENT_NOTE,
            judgment_note="This is a recurring pattern"
        )

        promoter = JudgmentLogPromoter()
        callback = Mock()
        promoter.register_promote_callback(callback)

        # Check should promote
        assert promoter.should_promote(action) is True

        # Promote
        result = promoter.promote_to_judgment_log(item, action)
        assert result is True

        # Verify callback called
        callback.assert_called_once()

        # Verify action marked
        assert action.judgment_log_promoted is True