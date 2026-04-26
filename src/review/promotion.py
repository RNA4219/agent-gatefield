"""
Judgment log promotion handler.

Handles promotion of review items to the judgment log knowledge base
for learning from reviewer decisions.
Spec reference: docs/spec/DATA_TYPES_SPEC.md Section 7 (ReviewAction)
"""

import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from .constants import ReviewDecision
from .dataclasses import ReviewAction, ReviewItem

logger = logging.getLogger(__name__)


class JudgmentLogPromoter:
    """Handles promotion of review items to judgment log knowledge base."""

    def __init__(self):
        """Initialize promoter with optional callback."""
        self._promote_callback: Optional[Callable[[str, Dict], None]] = None

    def register_promote_callback(self, callback: Callable[[str, Dict], None]) -> None:
        """
        Register callback for judgment log promotion.

        Args:
            callback: Function taking (decision_id: str, promotion_data: Dict) -> None
        """
        self._promote_callback = callback

    def promote_to_judgment_log(self, item: ReviewItem, action: ReviewAction) -> bool:
        """
        Promote reviewed item to judgment log knowledge base.

        Called when:
        - Reviewer adds judgment note (ADD_JUDGMENT_NOTE decision)
        - Reviewer approves/rejects with significant insight
        - Correction resolves a recurring pattern

        Args:
            item: ReviewItem being promoted
            action: ReviewAction taken on the item

        Returns:
            True if promotion was successful, False otherwise
        """
        # Use backward-compatible decision field
        decision = action.decision
        if decision is None:
            # Try to get from action_type if decision is not set
            try:
                decision = ReviewDecision(action.action_type)
            except ValueError:
                return False

        if decision not in (
            ReviewDecision.ADD_JUDGMENT_NOTE,
            ReviewDecision.APPROVE,
            ReviewDecision.REJECT,
        ):
            return False

        # Use spec-compliant correction field, fallback to correction_json
        correction = action.correction or action.correction_json

        promotion_data = {
            "decision_id": item.decision_id,
            "review_id": item.review_id,  # Spec-compliant field
            "run_id": item.run_id,
            "original_state": item.state,
            "composite_score": item.composite_score,
            "top_factors": item.top_factors,
            "exemplar_refs": item.exemplar_refs,
            "reviewer_decision": decision.value,  # Use decision.value for backward compat
            "reviewer_comment": action.comment,
            "reviewer_id": action.reviewer,
            "correction": correction,  # Spec-compliant name
            "correction_json": correction,  # Backward compatibility
            "previous_decision": action.previous_decision,  # Spec-compliant field
            "new_decision": action.new_decision,  # Spec-compliant field
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }

        if self._promote_callback:
            try:
                self._promote_callback(item.decision_id, promotion_data)
                action.judgment_log_promoted = True
                logger.info(f"Promoted {item.review_id} to judgment log")
                return True
            except Exception as e:
                logger.error(f"Judgment log promotion failed: {e}")
                return False
        else:
            # Direct KB promotion would go here
            logger.info(f"Judgment log promotion: {promotion_data}")
            action.judgment_log_promoted = True
            return True

    def should_promote(self, action: ReviewAction) -> bool:
        """
        Check if an action should trigger promotion.

        Args:
            action: ReviewAction to check

        Returns:
            True if the action should be promoted
        """
        # Use backward-compatible decision field
        decision = action.decision
        if decision is None:
            try:
                decision = ReviewDecision(action.action_type)
            except ValueError:
                return False

        return decision in (
            ReviewDecision.ADD_JUDGMENT_NOTE,
            ReviewDecision.APPROVE,
            ReviewDecision.REJECT,
        )

    def create_promotion_data(self, item: ReviewItem, action: ReviewAction) -> Dict:
        """
        Create promotion data dictionary without actually promoting.

        Useful for testing or logging.

        Args:
            item: ReviewItem
            action: ReviewAction

        Returns:
            Dictionary with promotion data
        """
        # Use backward-compatible decision field
        decision = action.decision
        if decision is None:
            try:
                decision = ReviewDecision(action.action_type)
            except ValueError:
                decision = None

        # Use spec-compliant correction field, fallback to correction_json
        correction = action.correction or action.correction_json

        return {
            "decision_id": item.decision_id,
            "review_id": item.review_id,  # Spec-compliant field
            "run_id": item.run_id,
            "original_state": item.state,
            "composite_score": item.composite_score,
            "top_factors": item.top_factors,
            "exemplar_refs": item.exemplar_refs,
            "reviewer_decision": decision.value if decision else action.action_type,
            "reviewer_comment": action.comment,
            "reviewer_id": action.reviewer,
            "correction": correction,  # Spec-compliant name
            "correction_json": correction,  # Backward compatibility
            "previous_decision": action.previous_decision,  # Spec-compliant field
            "new_decision": action.new_decision,  # Spec-compliant field
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }