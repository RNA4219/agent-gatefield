"""
Tests for Pairwise Comparison Mode - A/B comparison logic.
"""

import pytest
from datetime import datetime, timezone

from src.review.pairwise import PairwiseQueue, get_pairwise_decisions
from src.review.constants import ReviewDecision, Severity
from src.review.dataclasses import ReviewItem, SLAStatus


class TestPairwiseQueueInit:
    """Tests for PairwiseQueue initialization."""

    def test_default_init(self):
        """Default initialization."""
        queue = PairwiseQueue()
        assert queue.pairs == {}

    def test_pairs_dict_type(self):
        """Pairs dict is correct type."""
        queue = PairwiseQueue()
        assert isinstance(queue.pairs, dict)


class TestCreatePair:
    """Tests for create_pair method."""

    @pytest.fixture
    def item_a(self):
        """Create first item."""
        return ReviewItem(
            decision_id="dec-a",
            run_id="run-1",
            state="hold",
            composite_score=0.75,
            severity="high",
            top_factors=["uncertainty"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc)
        )

    @pytest.fixture
    def item_b(self):
        """Create second item."""
        return ReviewItem(
            decision_id="dec-b",
            run_id="run-1",
            state="warn",
            composite_score=0.60,
            severity="medium",
            top_factors=["risk"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc)
        )

    def test_create_pair_basic(self, item_a, item_b):
        """Create basic pair."""
        queue = PairwiseQueue()
        pair_id = queue.create_pair(item_a, item_b)

        assert pair_id is not None
        assert pair_id in queue.pairs

    def test_create_pair_sets_pair_id(self, item_a, item_b):
        """Create pair sets pair_id on items."""
        queue = PairwiseQueue()
        pair_id = queue.create_pair(item_a, item_b)

        assert item_a.pair_id == pair_id
        assert item_b.pair_id == pair_id

    def test_create_pair_sets_position(self, item_a, item_b):
        """Create pair sets position on items."""
        queue = PairwiseQueue()
        queue.create_pair(item_a, item_b)

        assert item_a.pair_position == "A"
        assert item_b.pair_position == "B"

    def test_create_pair_stores_ids(self, item_a, item_b):
        """Create pair stores decision_ids."""
        queue = PairwiseQueue()
        queue.create_pair(item_a, item_b)

        stored_ids = queue.pairs[item_a.pair_id]
        assert stored_ids == (item_a.decision_id, item_b.decision_id)

    def test_create_pair_multiple(self, item_a, item_b):
        """Create multiple pairs."""
        queue = PairwiseQueue()
        id1 = queue.create_pair(item_a, item_b)

        item_c = ReviewItem(
            decision_id="dec-c",
            run_id="run-2",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-c",
            trace_ref="trace-c",
            created_at=datetime.now(timezone.utc)
        )
        item_d = ReviewItem(
            decision_id="dec-d",
            run_id="run-2",
            state="pass",
            composite_score=0.50,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-d",
            trace_ref="trace-d",
            created_at=datetime.now(timezone.utc)
        )
        id2 = queue.create_pair(item_c, item_d)

        assert id1 != id2
        assert len(queue.pairs) == 2


class TestGetEffectiveSeverity:
    """Tests for get_effective_severity method."""

    def test_higher_critical(self):
        """Critical is highest."""
        item_a = ReviewItem(
            decision_id="dec-a",
            run_id="run-1",
            state="block",
            composite_score=0.95,
            severity="critical",
            top_factors=["secret"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc)
        )
        item_b = ReviewItem(
            decision_id="dec-b",
            run_id="run-1",
            state="hold",
            composite_score=0.80,
            severity="high",
            top_factors=["risk"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc)
        )

        queue = PairwiseQueue()
        severity = queue.get_effective_severity(item_a, item_b)
        assert severity == Severity.CRITICAL

    def test_higher_high(self):
        """High beats medium."""
        item_a = ReviewItem(
            decision_id="dec-a",
            run_id="run-1",
            state="hold",
            composite_score=0.80,
            severity="high",
            top_factors=["risk"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc)
        )
        item_b = ReviewItem(
            decision_id="dec-b",
            run_id="run-1",
            state="warn",
            composite_score=0.60,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc)
        )

        queue = PairwiseQueue()
        severity = queue.get_effective_severity(item_a, item_b)
        assert severity == Severity.HIGH

    def test_equal_severity(self):
        """Equal severity returns first."""
        item_a = ReviewItem(
            decision_id="dec-a",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc)
        )
        item_b = ReviewItem(
            decision_id="dec-b",
            run_id="run-1",
            state="warn",
            composite_score=0.65,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc)
        )

        queue = PairwiseQueue()
        severity = queue.get_effective_severity(item_a, item_b)
        assert severity == Severity.MEDIUM


class TestIsPairAvailable:
    """Tests for is_pair_available method."""

    @pytest.fixture
    def available_item_a(self):
        """Create available item A."""
        return ReviewItem(
            decision_id="dec-avail-a",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc),
            assigned_to=None
        )

    @pytest.fixture
    def available_item_b(self):
        """Create available item B."""
        return ReviewItem(
            decision_id="dec-avail-b",
            run_id="run-1",
            state="warn",
            composite_score=0.60,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc),
            assigned_to=None
        )

    @pytest.fixture
    def assigned_item(self):
        """Create assigned item."""
        return ReviewItem(
            decision_id="dec-assigned",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-c",
            trace_ref="trace-c",
            created_at=datetime.now(timezone.utc),
            assigned_to="reviewer-1"
        )

    def test_both_available(self, available_item_a, available_item_b):
        """Both items available."""
        queue = PairwiseQueue()
        queue.create_pair(available_item_a, available_item_b)

        pair_ids = (available_item_a.decision_id, available_item_b.decision_id)
        items = [available_item_a, available_item_b]

        assert queue.is_pair_available(pair_ids, items) is True

    def test_one_assigned(self, available_item_a, assigned_item):
        """One item assigned."""
        queue = PairwiseQueue()
        queue.create_pair(available_item_a, assigned_item)

        pair_ids = (available_item_a.decision_id, assigned_item.decision_id)
        items = [available_item_a, assigned_item]

        assert queue.is_pair_available(pair_ids, items) is False

    def test_both_assigned(self):
        """Both items assigned."""
        item_a = ReviewItem(
            decision_id="dec-a",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc),
            assigned_to="rev-1"
        )
        item_b = ReviewItem(
            decision_id="dec-b",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc),
            assigned_to="rev-2"
        )

        queue = PairwiseQueue()
        queue.create_pair(item_a, item_b)

        pair_ids = (item_a.decision_id, item_b.decision_id)
        items = [item_a, item_b]

        assert queue.is_pair_available(pair_ids, items) is False

    def test_item_not_in_list(self, available_item_a, available_item_b):
        """Item not in list returns False."""
        queue = PairwiseQueue()
        queue.create_pair(available_item_a, available_item_b)

        pair_ids = (available_item_a.decision_id, available_item_b.decision_id)
        items = [available_item_a]  # Missing item_b

        assert queue.is_pair_available(pair_ids, items) is False


class TestGetAvailablePairs:
    """Tests for get_available_pairs method."""

    def test_no_pairs(self):
        """No pairs returns empty."""
        queue = PairwiseQueue()
        assert queue.get_available_pairs([]) == []

    def test_all_available(self):
        """All pairs available."""
        queue = PairwiseQueue()

        item_a = ReviewItem(
            decision_id="dec-a",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc)
        )
        item_b = ReviewItem(
            decision_id="dec-b",
            run_id="run-1",
            state="warn",
            composite_score=0.60,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc)
        )

        queue.create_pair(item_a, item_b)

        available = queue.get_available_pairs([item_a, item_b])
        assert len(available) == 1

    def test_some_assigned(self):
        """Some pairs not available."""
        queue = PairwiseQueue()

        # Available pair
        item_a = ReviewItem(
            decision_id="dec-a",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc)
        )
        item_b = ReviewItem(
            decision_id="dec-b",
            run_id="run-1",
            state="warn",
            composite_score=0.60,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc)
        )
        queue.create_pair(item_a, item_b)

        # Assigned pair
        item_c = ReviewItem(
            decision_id="dec-c",
            run_id="run-2",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-c",
            trace_ref="trace-c",
            created_at=datetime.now(timezone.utc),
            assigned_to="rev-1"
        )
        item_d = ReviewItem(
            decision_id="dec-d",
            run_id="run-2",
            state="warn",
            composite_score=0.60,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-d",
            trace_ref="trace-d",
            created_at=datetime.now(timezone.utc)
        )
        queue.create_pair(item_c, item_d)

        items = [item_a, item_b, item_c, item_d]
        available = queue.get_available_pairs(items)

        # Only first pair available
        assert len(available) == 1


class TestRemovePair:
    """Tests for remove_pair method."""

    def test_remove_existing_pair(self):
        """Remove existing pair."""
        queue = PairwiseQueue()

        item_a = ReviewItem(
            decision_id="dec-a",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc)
        )
        item_b = ReviewItem(
            decision_id="dec-b",
            run_id="run-1",
            state="warn",
            composite_score=0.60,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc)
        )

        pair_id = queue.create_pair(item_a, item_b)
        removed = queue.remove_pair(pair_id)

        assert removed == (item_a.decision_id, item_b.decision_id)
        assert pair_id not in queue.pairs

    def test_remove_nonexistent_pair(self):
        """Remove nonexistent pair returns None."""
        queue = PairwiseQueue()
        removed = queue.remove_pair("nonexistent-id")
        assert removed is None


class TestCleanupPair:
    """Tests for cleanup_pair method."""

    def test_cleanup_pair(self):
        """Cleanup pair (no-op)."""
        queue = PairwiseQueue()

        item_a = ReviewItem(
            decision_id="dec-a",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc)
        )
        item_b = ReviewItem(
            decision_id="dec-b",
            run_id="run-1",
            state="warn",
            composite_score=0.60,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc)
        )

        pair_id = queue.create_pair(item_a, item_b)
        queue.cleanup_pair(pair_id, item_a.decision_id)

        # Pair still exists (cleanup is no-op)
        assert pair_id in queue.pairs


class TestGetPairItems:
    """Tests for get_pair_items method."""

    def test_get_pair_items_success(self):
        """Get both items of pair."""
        queue = PairwiseQueue()

        item_a = ReviewItem(
            decision_id="dec-a",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc)
        )
        item_b = ReviewItem(
            decision_id="dec-b",
            run_id="run-1",
            state="warn",
            composite_score=0.60,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc)
        )

        pair_id = queue.create_pair(item_a, item_b)
        found_a, found_b = queue.get_pair_items(pair_id, [item_a, item_b])

        assert found_a is item_a
        assert found_b is item_b

    def test_get_pair_items_not_found(self):
        """Get items for nonexistent pair."""
        queue = PairwiseQueue()
        found_a, found_b = queue.get_pair_items("nonexistent", [])

        assert found_a is None
        assert found_b is None

    def test_get_pair_items_partial(self):
        """Get items when one missing from list."""
        queue = PairwiseQueue()

        item_a = ReviewItem(
            decision_id="dec-a",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-a",
            trace_ref="trace-a",
            created_at=datetime.now(timezone.utc)
        )
        item_b = ReviewItem(
            decision_id="dec-b",
            run_id="run-1",
            state="warn",
            composite_score=0.60,
            severity="low",
            top_factors=["test"],
            artifact_ref="art-b",
            trace_ref="trace-b",
            created_at=datetime.now(timezone.utc)
        )

        pair_id = queue.create_pair(item_a, item_b)
        found_a, found_b = queue.get_pair_items(pair_id, [item_a])  # Missing item_b

        assert found_a is item_a
        assert found_b is None


class TestFindItem:
    """Tests for _find_item helper method."""

    def test_find_existing_item(self):
        """Find existing item."""
        queue = PairwiseQueue()

        item = ReviewItem(
            decision_id="dec-find",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-find",
            trace_ref="trace-find",
            created_at=datetime.now(timezone.utc)
        )

        found = queue._find_item("dec-find", [item])
        assert found is item

    def test_find_nonexistent_item(self):
        """Find nonexistent item."""
        queue = PairwiseQueue()

        item = ReviewItem(
            decision_id="dec-find",
            run_id="run-1",
            state="hold",
            composite_score=0.70,
            severity="medium",
            top_factors=["test"],
            artifact_ref="art-find",
            trace_ref="trace-find",
            created_at=datetime.now(timezone.utc)
        )

        found = queue._find_item("nonexistent", [item])
        assert found is None

    def test_find_in_multiple_items(self):
        """Find item in list of multiple."""
        queue = PairwiseQueue()

        items = [
            ReviewItem(
                decision_id=f"dec-{i}",
                run_id="run-1",
                state="hold",
                composite_score=0.70,
                severity="medium",
                top_factors=["test"],
                artifact_ref=f"art-{i}",
                trace_ref=f"trace-{i}",
                created_at=datetime.now(timezone.utc)
            )
            for i in range(5)
        ]

        found = queue._find_item("dec-3", items)
        assert found.decision_id == "dec-3"


class TestGetPairwiseDecisions:
    """Tests for get_pairwise_decisions function."""

    def test_select_a(self):
        """Select A."""
        dec_a, dec_b = get_pairwise_decisions("A")
        assert dec_a == ReviewDecision.APPROVE
        assert dec_b == ReviewDecision.REJECT

    def test_select_b(self):
        """Select B."""
        dec_a, dec_b = get_pairwise_decisions("B")
        assert dec_a == ReviewDecision.REJECT
        assert dec_b == ReviewDecision.APPROVE

    def test_select_both(self):
        """Select both."""
        dec_a, dec_b = get_pairwise_decisions("both")
        assert dec_a == ReviewDecision.APPROVE
        assert dec_b == ReviewDecision.APPROVE

    def test_select_none(self):
        """Select none."""
        dec_a, dec_b = get_pairwise_decisions("none")
        assert dec_a == ReviewDecision.REJECT
        assert dec_b == ReviewDecision.REJECT

    def test_unknown_selection(self):
        """Unknown selection defaults to reject both."""
        dec_a, dec_b = get_pairwise_decisions("unknown")
        assert dec_a == ReviewDecision.REJECT
        assert dec_b == ReviewDecision.REJECT

    def test_empty_selection(self):
        """Empty selection defaults to reject both."""
        dec_a, dec_b = get_pairwise_decisions("")
        assert dec_a == ReviewDecision.REJECT
        assert dec_b == ReviewDecision.REJECT


class TestPairwiseIntegration:
    """Integration-like tests."""

    def test_full_pair_workflow(self):
        """Full pairwise comparison workflow."""
        queue = PairwiseQueue()

        # Create items
        item_a = ReviewItem(
            decision_id="dec-int-a",
            run_id="run-int",
            state="hold",
            composite_score=0.75,
            severity="high",
            top_factors=["option_a"],
            artifact_ref="art-int-a",
            trace_ref="trace-int",
            created_at=datetime.now(timezone.utc)
        )
        item_b = ReviewItem(
            decision_id="dec-int-b",
            run_id="run-int",
            state="hold",
            composite_score=0.80,
            severity="critical",
            top_factors=["option_b"],
            artifact_ref="art-int-b",
            trace_ref="trace-int",
            created_at=datetime.now(timezone.utc)
        )

        # Create pair
        pair_id = queue.create_pair(item_a, item_b)

        # Check effective severity (should be critical)
        severity = queue.get_effective_severity(item_a, item_b)
        assert severity == Severity.CRITICAL

        # Get available pairs
        items = [item_a, item_b]
        available = queue.get_available_pairs(items)
        assert len(available) == 1

        # Get pair items
        found_a, found_b = queue.get_pair_items(pair_id, items)
        assert found_a.decision_id == "dec-int-a"
        assert found_b.decision_id == "dec-int-b"

        # Make selection (choose A)
        dec_a, dec_b = get_pairwise_decisions("A")
        assert dec_a == ReviewDecision.APPROVE
        assert dec_b == ReviewDecision.REJECT

        # Cleanup
        queue.cleanup_pair(pair_id, item_a.decision_id)
        assert pair_id in queue.pairs  # Still exists

        # Remove
        queue.remove_pair(pair_id)
        assert pair_id not in queue.pairs