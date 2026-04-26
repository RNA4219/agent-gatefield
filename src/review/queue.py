"""
Human Review Queue - Main orchestrator.

Implements review queue management with SLA handling, escalation routing,
pairwise comparison mode, and judgment log promotion.

This module serves as the main entry point, importing from specialized modules.

Spec reference: docs/STATE_TRANSITION_SPEC.md Section 6 (Review Flow)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from src.core.exceptions import ItemNotFoundError, PairNotFoundError

# Import from modular components
from .constants import (
    QueueMode,
    ReviewDecision,
    SEVERITY_PRIORITY,
    Severity,
    SLA_TARGETS,
    SLAType,
)
from .dataclasses import EscalationConfig, ReviewAction, ReviewItem
from .escalation import EscalationHandler
from .pairwise import PairwiseQueue, get_pairwise_decisions
from .promotion import JudgmentLogPromoter
from .sla_handler import calculate_sla_deadlines, check_sla_compliance

try:
    from src.vector_store import VectorStore
except ImportError:
    VectorStore = None

logger = logging.getLogger(__name__)


class ReviewQueue:
    """
    Human review queue manager with SLA handling, escalation,
    pairwise comparison mode, and judgment log promotion.

    This class orchestrates the review workflow by delegating to
    specialized handlers for escalation, promotion, and pairwise logic.

    Spec reference: STATE_TRANSITION_SPEC.md Section 6
    """

    def __init__(
        self,
        escalation_handler: Optional[EscalationHandler] = None,
        judgment_promoter: Optional[JudgmentLogPromoter] = None,
        vector_store: Optional['VectorStore'] = None,
        persistence_path: Optional[str] = None,
    ):
        """
        Initialize review queue.

        Args:
            escalation_handler: Optional custom escalation handler
            judgment_promoter: Optional custom judgment log promoter
            vector_store: Optional VectorStore for database persistence
            persistence_path: Optional file path for JSONL persistence fallback
        """
        self.queue: List[ReviewItem] = []
        self.history: List[ReviewAction] = []
        self.mode: QueueMode = QueueMode.STANDARD

        # Persistence configuration
        self.vector_store = vector_store
        self.persistence_path = persistence_path or os.environ.get(
            'REVIEW_QUEUE_PERSISTENCE_PATH',
            'review_queue_data.jsonl'
        )

        # Pairwise comparison handler
        self._pairwise_queue = PairwiseQueue()

        # Handler instances
        self.escalation_handler = escalation_handler or EscalationHandler()
        self.judgment_promoter = judgment_promoter or JudgmentLogPromoter()

        # Stats tracking
        self._stats = {
            "total_enqueued": 0,
            "total_resolved": 0,
            "total_sla_breaches": 0,
            "total_escalations": 0,
            "total_judgment_promotions": 0,
            "by_severity_enqueued": {s.value: 0 for s in Severity},
            "by_severity_resolved": {s.value: 0 for s in Severity},
            "by_decision": {d.value: 0 for d in ReviewDecision},
        }

        # Load persisted state if available
        self._load_persisted_state()

    def _load_persisted_state(self) -> None:
        """
        Load persisted queue state from storage.

        Stub implementation - can be extended for actual persistence.
        """
        # Stub - no persistence loading in this implementation
        pass

    def _persist_item(self, item: ReviewItem) -> None:
        """
        Persist item to storage.

        Stub implementation - can be extended for actual persistence.
        """
        # Stub - no persistence in this implementation
        pass

    def _persist_action(self, action: ReviewAction) -> None:
        """
        Persist action to storage.

        Stub implementation - can be extended for actual persistence.
        """
        # Stub - no persistence in this implementation
        pass

    def _log_audit_event(
        self,
        action: ReviewAction,
        item: ReviewItem,
        timeout_type: str = None
    ) -> None:
        """
        Log audit event for review actions.

        Stub implementation - can be extended for actual audit logging.
        """
        # Stub - no audit logging in this implementation
        pass

    def _trigger_downstream_action(self, action: ReviewAction, item: ReviewItem) -> None:
        """
        Trigger downstream actions after resolution.

        Stub implementation - can be extended for downstream integrations.
        """
        # Stub - no downstream actions in this implementation
        pass

    def set_mode(self, mode: QueueMode) -> None:
        """
        Set queue mode (standard or pairwise).

        Args:
            mode: QueueMode.STANDARD or QueueMode.PAIRWISE
        """
        self.mode = mode

    def enqueue(self, item: ReviewItem) -> None:
        """
        Add item to review queue with SLA deadline calculation.

        Spec: STATE_TRANSITION_SPEC.md T19-T24 (Review Queue entry)

        Args:
            item: ReviewItem to add to queue
        """
        # Calculate SLA deadlines
        calculate_sla_deadlines(item)

        # Track severity escalation for repeated holds
        self._check_severity_escalation(item)

        self.queue.append(item)

        # Update stats
        self._stats["total_enqueued"] += 1
        self._stats["by_severity_enqueued"][item.severity] += 1

        logger.info(f"Enqueued review item {item.decision_id} severity={item.severity}")
        self._persist_item(item)

    def enqueue_pairwise(
        self,
        item_a: ReviewItem,
        item_b: ReviewItem,
    ) -> str:
        """
        Enqueue two items for pairwise A/B comparison.

        Used when comparing alternative solutions or approaches.

        Args:
            item_a: First item in comparison
            item_b: Second item in comparison

        Returns:
            pair_id for tracking the pair
        """
        # Create pair and link items
        pair_id = self._pairwise_queue.create_pair(item_a, item_b)

        # Use higher severity for SLA
        effective_severity = self._pairwise_queue.get_effective_severity(item_a, item_b)

        # Set SLA based on higher severity
        item_a.severity = effective_severity.value
        item_b.severity = effective_severity.value

        calculate_sla_deadlines(item_a)
        calculate_sla_deadlines(item_b)

        self.queue.append(item_a)
        self.queue.append(item_b)

        self._stats["total_enqueued"] += 2
        self._stats["by_severity_enqueued"][effective_severity.value] += 2

        logger.info(f"Enqueued pairwise pair {pair_id}: {item_a.decision_id} vs {item_b.decision_id}")
        return pair_id

    def take(
        self,
        severity: Optional[str] = None,
        reviewer: Optional[str] = None,
        pair_id: Optional[str] = None,
    ) -> Optional[ReviewItem]:
        """
        Take an item from queue with priority ordering.

        Priority: severity > created_at (oldest first within severity)
        In pairwise mode, both items should be taken together.

        Spec: STATE_TRANSITION_SPEC.md Section 6.2 (Reviewer Takes Item)

        Args:
            severity: Optional severity filter
            reviewer: Optional reviewer ID
            pair_id: Optional pair ID for pairwise mode

        Returns:
            ReviewItem if available, None otherwise
        """
        # Check for SLA timeouts before taking
        self._check_sla_timeouts()

        # Pairwise mode: return both items or None
        if pair_id and pair_id in self._pairwise_queue.pairs:
            return self._take_pair(pair_id, reviewer)

        # Filter candidates
        candidates = self.queue

        if severity:
            candidates = [i for i in candidates if i.severity == severity]

        if pair_id is None and self.mode == QueueMode.PAIRWISE:
            # In pairwise mode without specific pair_id, get first available pair
            available_pairs = self._pairwise_queue.get_available_pairs(self.queue)
            if available_pairs:
                return self._take_pair_by_ids(available_pairs[0], reviewer)

        # Sort by priority (severity first, then created_at)
        candidates.sort(key=lambda i: (-i.get_priority(), i.created_at))

        if not candidates:
            return None

        item = candidates[0]
        item.assigned_to = reviewer
        item.taken_at = datetime.now(timezone.utc)
        item.sla_status.acked_at = datetime.now(timezone.utc)  # Taking counts as ACK

        logger.info(f"Review item {item.decision_id} taken by {reviewer}")
        return item

    def take_pair(self, pair_id: str, reviewer: Optional[str] = None) -> Tuple[Optional[ReviewItem], Optional[ReviewItem]]:
        """
        Take both items of a pairwise comparison.

        Args:
            pair_id: ID of the pair
            reviewer: Optional reviewer ID

        Returns:
            Tuple of (item_a, item_b) or (None, None) if not available
        """
        if pair_id not in self._pairwise_queue.pairs:
            return None, None

        id_a, id_b = self._pairwise_queue.pairs[pair_id]
        item_a = self._take_by_id(id_a, reviewer)
        item_b = self._take_by_id(id_b, reviewer)

        return item_a, item_b

    def resolve(
        self,
        decision_id: str,
        reviewer: str,
        decision: ReviewDecision,
        comment: str,
        correction: Optional[Dict] = None,
    ) -> ReviewAction:
        """
        Resolve a review with SLA compliance tracking and judgment log promotion.

        Spec: STATE_TRANSITION_SPEC.md Section 6.4 (Reviewer Actions)

        Args:
            decision_id: ID of item to resolve
            reviewer: Reviewer ID
            decision: Decision type
            comment: Reviewer comment
            correction: Optional correction data

        Returns:
            ReviewAction record

        Raises:
            ValueError: If item not found in queue
        """
        item = self._find_item(decision_id)
        if not item:
            raise ItemNotFoundError(decision_id)

        now = datetime.now(timezone.utc)

        # Check SLA compliance
        sla_compliant = check_sla_compliance(item, now)

        # Store previous decision state for audit
        previous_decision = item.state

        # Determine new decision state based on action
        new_decision = self._get_new_decision_state(decision, item.state)

        # Create action record with spec-compliant fields
        action = ReviewAction(
            decision_id=decision_id,
            reviewer=reviewer,
            created_at=now,
            # Spec-compliant fields
            action_type=decision.value,
            review_id=item.review_id,
            run_id=item.run_id,
            # Decision state tracking
            previous_decision=previous_decision,
            new_decision=new_decision,
            # Backward compatibility
            decision=decision,
            comment=comment,
            correction=correction,
            correction_json=correction,
            sla_compliant=sla_compliant,
        )

        # Sync fields for backward compatibility
        action.sync_fields()

        # Mark item resolved
        item.resolved_at = now

        # Add to history
        self.history.append(action)

        # Remove from queue
        self.queue = [i for i in self.queue if i.decision_id != decision_id]

        # Handle pairwise pair cleanup
        if item.pair_id:
            self._pairwise_queue.cleanup_pair(item.pair_id, decision_id)

        # Update stats
        self._stats["total_resolved"] += 1
        self._stats["by_severity_resolved"][item.severity] += 1
        self._stats["by_decision"][decision.value] += 1

        if not sla_compliant:
            self._stats["total_sla_breaches"] += 1

        # Judgment log promotion for certain decisions
        if decision in (ReviewDecision.ADD_JUDGMENT_NOTE, ReviewDecision.REJECT):
            if self.judgment_promoter.promote_to_judgment_log(item, action):
                self._stats["total_judgment_promotions"] += 1

        logger.info(
            f"Resolved review {decision_id}: {decision.value} by {reviewer} "
            f"(SLA compliant: {sla_compliant})"
        )

        self._persist_action(action)
        self._trigger_downstream_action(action, item)

        return action

    def resolve_pairwise(
        self,
        pair_id: str,
        reviewer: str,
        selected_position: str,  # "A" or "B" or "both" or "none"
        comment: str,
    ) -> Tuple[ReviewAction, Optional[ReviewAction]]:
        """
        Resolve a pairwise comparison with selection.

        Args:
            pair_id: ID of the pair
            reviewer: Reviewer ID
            selected_position: Selection type ("A", "B", "both", or "none")
            comment: Reviewer comment

        Returns:
            Tuple of (primary_action, secondary_action) if applicable

        Raises:
            ValueError: If pair not found
        """
        if pair_id not in self._pairwise_queue.pairs:
            raise PairNotFoundError(pair_id)

        id_a, id_b = self._pairwise_queue.pairs[pair_id]

        # Get decisions based on selection
        decision_a, decision_b = get_pairwise_decisions(selected_position)

        action_a = self.resolve(id_a, reviewer, decision_a, f"[Pair {pair_id}] {comment}")
        action_b = None

        if decision_b:
            action_b = self.resolve(id_b, reviewer, decision_b, f"[Pair {pair_id}] {comment}")

        # Clean up pair reference
        self._pairwise_queue.remove_pair(pair_id)

        return action_a, action_b

    def get_pending(
        self,
        severity: Optional[str] = None,
        include_sla_status: bool = False,
    ) -> List[ReviewItem]:
        """
        Get pending items optionally with SLA status.

        Args:
            severity: Optional severity filter
            include_sla_status: If True, update SLA status on items

        Returns:
            List of pending ReviewItems sorted by priority
        """
        items = self.queue

        if severity:
            items = [i for i in items if i.severity == severity]

        # Update SLA status if requested
        if include_sla_status:
            for item in items:
                ack_expired, decision_expired = item.is_sla_expired()
                item.sla_status.ack_expired = ack_expired
                item.sla_status.decision_expired = decision_expired

        # Sort by priority
        items.sort(key=lambda i: (-i.get_priority(), i.created_at))

        return items

    def get_stats(self) -> Dict:
        """
        Get comprehensive queue statistics for dashboard.

        Returns stats for:
        - Current queue state
        - SLA compliance
        - Resolution metrics
        - Escalation counts
        """
        pending = self.queue

        # Current pending stats
        pending_by_severity = {s.value: 0 for s in Severity}
        pending_by_state = {"pass": 0, "warn": 0, "hold": 0, "block": 0}
        pending_oldest_by_severity = {}

        for item in pending:
            pending_by_severity[item.severity] += 1
            pending_by_state[item.state] += 1
            if item.severity not in pending_oldest_by_severity or item.created_at < pending_oldest_by_severity[item.severity]:
                pending_oldest_by_severity[item.severity] = item.created_at

        # Calculate pending duration by severity
        pending_duration_by_severity = {}
        now = datetime.now(timezone.utc)
        for severity, oldest in pending_oldest_by_severity.items():
            pending_duration_by_severity[severity] = int((now - oldest).total_seconds() / 60)

        # SLA breach stats
        sla_breaches = {
            "ack": 0,
            "decision": 0,
            "by_severity": {s.value: 0 for s in Severity},
        }

        for item in pending:
            ack_expired, decision_expired = item.is_sla_expired()
            if ack_expired:
                sla_breaches["ack"] += 1
                sla_breaches["by_severity"][item.severity] += 1
            if decision_expired:
                sla_breaches["decision"] += 1
                sla_breaches["by_severity"][item.severity] += 1

        return {
            "queue_mode": self.mode.value,
            "pending": {
                "total": len(pending),
                "by_severity": pending_by_severity,
                "by_state": pending_by_state,
                "oldest_age_minutes_by_severity": pending_duration_by_severity,
            },
            "resolved": {
                "total": self._stats["total_resolved"],
                "by_severity": self._stats["by_severity_resolved"],
                "by_decision": self._stats["by_decision"],
            },
            "sla": {
                "total_breaches": self._stats["total_sla_breaches"],
                "current_breaches": sla_breaches,
                "targets": {
                    s.value: {
                        "ack_minutes": SLA_TARGETS[s][SLAType.ACK].total_seconds() / 60 if SLA_TARGETS[s][SLAType.ACK] else None,
                        "decision_minutes": SLA_TARGETS[s][SLAType.DECISION].total_seconds() / 60 if SLA_TARGETS[s][SLAType.DECISION] else None,
                    }
                    for s in Severity
                },
            },
            "escalations": {
                "total": self._stats["total_escalations"],
            },
            "judgment_promotions": {
                "total": self._stats["total_judgment_promotions"],
            },
            "pairs": {
                "total": len(self._pairwise_queue.pairs),
                "pending": list(self._pairwise_queue.pairs.keys()),
            },
        }

    def check_and_process_sla_timeouts(self) -> List[ReviewItem]:
        """
        Check all pending items for SLA timeouts and process them.

        Returns list of items that were auto-blocked (fail closed).

        Spec: STATE_TRANSITION_SPEC.md T25, T26, Section 9.2
        """
        auto_blocked = []

        for item in self.queue:
            ack_expired, decision_expired = item.is_sla_expired()
            severity = item.get_severity_enum()

            # ACK timeout - fail closed for Critical/High per T25
            if ack_expired and not item.sla_status.escalation_sent:
                self.escalation_handler.escalate_ack_timeout(item)
                self._stats["total_escalations"] += 1

                # T25: ACK timeout for Critical/High severity -> BLOCK (fail closed)
                if severity in (Severity.CRITICAL, Severity.HIGH):
                    auto_blocked.append(item)
                    self._auto_block(item, reason="Auto-blocked: SLA ACK timeout (fail closed)")
                    continue  # Item removed from queue, skip decision check

            # Decision timeout - fail closed for Critical/High per T26
            if decision_expired and not item.sla_status.decision_escalation_sent:
                self.escalation_handler.escalate_decision_timeout(item)
                self._stats["total_escalations"] += 1

                # T26: Decision timeout for Critical/High severity -> BLOCK (fail closed)
                if severity in (Severity.CRITICAL, Severity.HIGH):
                    auto_blocked.append(item)
                    self._auto_block(item, reason="Auto-blocked: SLA decision timeout (fail closed)")

        return auto_blocked

    # -------------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------------

    def _check_severity_escalation(self, item: ReviewItem) -> None:
        """
        Check if severity should be escalated due to repeated holds.

        If an item has been in hold state multiple times, escalate severity.
        """
        # Look for previous items from same run_id with hold state
        previous_holds = [i for i in self.queue if i.run_id == item.run_id and i.state == "hold"]
        item.hold_count = len(previous_holds) + 1
        item.original_severity = item.severity

        # Escalate severity after 2+ holds
        if item.hold_count >= 2:
            if item.severity == "low":
                item.severity = "medium"
            elif item.severity == "medium":
                item.severity = "high"

            # Recalculate SLA for new severity
            calculate_sla_deadlines(item)
            logger.warning(
                f"Severity escalated for {item.decision_id}: "
                f"{item.original_severity} -> {item.severity} (hold_count: {item.hold_count})"
            )

    def _check_sla_timeouts(self) -> None:
        """Check for SLA timeouts and trigger escalation."""
        for item in self.queue:
            ack_expired, decision_expired = item.is_sla_expired()

            if ack_expired and not item.sla_status.escalation_sent:
                self.escalation_handler.escalate_ack_timeout(item)
                self._stats["total_escalations"] += 1

            if decision_expired and not item.sla_status.decision_escalation_sent:
                severity = item.get_severity_enum()
                if severity in (Severity.CRITICAL, Severity.HIGH):
                    self.escalation_handler.escalate_decision_timeout(item)
                    self._stats["total_escalations"] += 1

    def _auto_block(self, item: ReviewItem, reason: str = "SLA timeout - fail closed") -> None:
        """
        Auto-block an item due to SLA timeout (fail closed).

        Spec: STATE_TRANSITION_SPEC.md T25, T26

        Args:
            item: ReviewItem to auto-block
            reason: Reason for auto-block (e.g., "SLA ACK timeout - fail closed")
        """
        now = datetime.now(timezone.utc)

        # Store previous decision state for audit
        previous_decision = item.state

        # Create auto-block action with spec-compliant fields
        action = ReviewAction(
            decision_id=item.decision_id,
            reviewer="system",
            created_at=now,
            # Spec-compliant fields
            action_type=ReviewDecision.REJECT.value,
            review_id=item.review_id,
            run_id=item.run_id,
            # Decision state tracking
            previous_decision=previous_decision,
            new_decision="block",  # Auto-block results in block state
            # Backward compatibility
            decision=ReviewDecision.REJECT,
            comment=reason,
            sla_compliant=False,
        )

        # Sync fields for backward compatibility
        action.sync_fields()

        self.history.append(action)
        self.queue = [i for i in self.queue if i.decision_id != item.decision_id]

        self._stats["total_resolved"] += 1
        self._stats["by_severity_resolved"][item.severity] += 1
        self._stats["by_decision"][ReviewDecision.REJECT.value] += 1
        self._stats["total_sla_breaches"] += 1

        # Audit logging for SLA timeout auto-block per spec T25/T26
        logger.critical(
            f"Auto-blocked {item.decision_id}: decision={ReviewDecision.REJECT.value}, "
            f"reason={reason}, severity={item.severity}"
        )

        self._persist_action(action)
        self._log_audit_event(action, item, timeout_type="sla_timeout")

    # State transition rules: decision -> current_state -> new_state
    STATE_TRANSITIONS = {
        ReviewDecision.APPROVE: {"hold": "pass"},
        ReviewDecision.REJECT: {"hold": "block"},
        ReviewDecision.REQUEST_ARTIFACT_CORRECTION: {"hold": "warn"},
        ReviewDecision.REQUEST_PROCESS_CORRECTION: {"hold": "warn"},
        ReviewDecision.REQUEST_PROMPT_CORRECTION: {"hold": "warn"},
    }

    def _get_new_decision_state(
        self,
        decision: ReviewDecision,
        current_state: str,
    ) -> Optional[str]:
        """Determine new decision state after review action (spec: DATA_TYPES_SPEC.md 7.2)."""
        transitions = self.STATE_TRANSITIONS.get(decision, {})
        return transitions.get(current_state)

    def _find_item(self, decision_id: str) -> Optional[ReviewItem]:
        """Find item by decision_id."""
        for item in self.queue:
            if item.decision_id == decision_id:
                return item
        return None

    def _take_by_id(self, decision_id: str, reviewer: Optional[str]) -> Optional[ReviewItem]:
        """Take specific item by ID."""
        item = self._find_item(decision_id)
        if item and not item.assigned_to:
            item.assigned_to = reviewer
            item.taken_at = datetime.now(timezone.utc)
            item.sla_status.acked_at = datetime.now(timezone.utc)
            return item
        return None

    def _take_pair(self, pair_id: str, reviewer: Optional[str]) -> Optional[ReviewItem]:
        """Take first item of a pair."""
        if pair_id in self._pairwise_queue.pairs:
            id_a, id_b = self._pairwise_queue.pairs[pair_id]
            return self._take_by_id(id_a, reviewer)
        return None

    def _take_pair_by_ids(self, pair_ids: Tuple[str, str], reviewer: Optional[str]) -> Optional[ReviewItem]:
        """Take pair by item IDs."""
        return self._take_by_id(pair_ids[0], reviewer)

    # -------------------------------------------------------------------------
    # Backward compatibility: expose pairs dict directly
    # -------------------------------------------------------------------------

    @property
    def pairs(self) -> Dict[str, Tuple[str, str]]:
        """Expose pairs dict for backward compatibility."""
        return self._pairwise_queue.pairs


# -----------------------------------------------------------------------------
# Backward compatibility: re-export all public classes and types
# -----------------------------------------------------------------------------
__all__ = [
    # Main entry point
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

# Re-export SLAStatus from dataclasses for backward compatibility
from .dataclasses import SLAStatus  # noqa: E402, F401