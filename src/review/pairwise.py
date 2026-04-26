"""
Pairwise comparison mode for the review queue.

Handles A/B comparison logic for reviewing alternative solutions or approaches.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .constants import QueueMode, ReviewDecision, SEVERITY_PRIORITY, Severity
from .dataclasses import ReviewAction, ReviewItem


class PairwiseQueue:
    """
    Manages pairwise A/B comparison logic for the review queue.

    Used when comparing alternative solutions or approaches.
    """

    def __init__(self):
        """Initialize pairwise queue with empty pairs dict."""
        self.pairs: Dict[str, Tuple[str, str]] = {}  # pair_id -> (item_id_A, item_id_B)

    def create_pair(self, item_a: ReviewItem, item_b: ReviewItem) -> str:
        """
        Create a pairwise comparison pair from two items.

        Links both items with a pair_id and sets their positions.

        Args:
            item_a: First item in comparison (position "A")
            item_b: Second item in comparison (position "B")

        Returns:
            pair_id for tracking the pair
        """
        pair_id = str(uuid.uuid4())

        item_a.pair_id = pair_id
        item_a.pair_position = "A"
        item_b.pair_id = pair_id
        item_b.pair_position = "B"

        self.pairs[pair_id] = (item_a.decision_id, item_b.decision_id)

        return pair_id

    def get_effective_severity(self, item_a: ReviewItem, item_b: ReviewItem) -> Severity:
        """
        Get the effective (higher) severity for a pair.

        Uses the higher severity of the two items for SLA calculation.

        Args:
            item_a: First item
            item_b: Second item

        Returns:
            The higher severity enum value
        """
        severity_a = item_a.get_severity_enum()
        severity_b = item_b.get_severity_enum()
        return severity_a if SEVERITY_PRIORITY[severity_a] >= SEVERITY_PRIORITY[severity_b] else severity_b

    def is_pair_available(self, pair_ids: Tuple[str, str], items: List[ReviewItem]) -> bool:
        """
        Check if both items in pair are available for review.

        Args:
            pair_ids: Tuple of (item_id_a, item_id_b)
            items: List of all items to search

        Returns:
            True if both items exist and are unassigned
        """
        item_a = self._find_item(pair_ids[0], items)
        item_b = self._find_item(pair_ids[1], items)
        return item_a is not None and item_b is not None and not item_a.assigned_to and not item_b.assigned_to

    def get_available_pairs(self, items: List[ReviewItem]) -> List[Tuple[str, str]]:
        """
        Get all available pairs for review.

        Args:
            items: List of all items in queue

        Returns:
            List of available pair tuples
        """
        return [p for p in self.pairs.values() if self.is_pair_available(p, items)]

    def remove_pair(self, pair_id: str) -> Optional[Tuple[str, str]]:
        """
        Remove a pair from tracking.

        Args:
            pair_id: ID of pair to remove

        Returns:
            The removed pair tuple, or None if not found
        """
        return self.pairs.pop(pair_id, None)

    def cleanup_pair(self, pair_id: str, resolved_id: str) -> None:
        """
        Clean up pair after one item resolved.

        Note: Currently keeps pair reference. Full cleanup should be done
        on complete resolution via remove_pair.

        Args:
            pair_id: ID of the pair
            resolved_id: ID of the resolved item
        """
        # Keep pair reference for now, clean up on full resolution
        pass

    def get_pair_items(self, pair_id: str, items: List[ReviewItem]) -> Tuple[Optional[ReviewItem], Optional[ReviewItem]]:
        """
        Get both items of a pair.

        Args:
            pair_id: ID of the pair
            items: List of all items in queue

        Returns:
            Tuple of (item_a, item_b) or (None, None) if not found
        """
        if pair_id not in self.pairs:
            return None, None

        id_a, id_b = self.pairs[pair_id]
        item_a = self._find_item(id_a, items)
        item_b = self._find_item(id_b, items)

        return item_a, item_b

    def _find_item(self, decision_id: str, items: List[ReviewItem]) -> Optional[ReviewItem]:
        """Find item by decision_id in item list."""
        for item in items:
            if item.decision_id == decision_id:
                return item
        return None


def get_pairwise_decisions(selected_position: str) -> Tuple[ReviewDecision, ReviewDecision]:
    """
    Get decisions for both items based on selection.

    Args:
        selected_position: One of "A", "B", "both", or "none"

    Returns:
        Tuple of (decision_for_a, decision_for_b)
    """
    decisions = {
        "A": (ReviewDecision.APPROVE, ReviewDecision.REJECT),
        "B": (ReviewDecision.REJECT, ReviewDecision.APPROVE),
        "both": (ReviewDecision.APPROVE, ReviewDecision.APPROVE),
        "none": (ReviewDecision.REJECT, ReviewDecision.REJECT),
    }
    return decisions.get(selected_position, (ReviewDecision.REJECT, ReviewDecision.REJECT))