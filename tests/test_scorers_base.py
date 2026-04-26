"""
Tests for scorers/base.py - BaseScorer and ScorerResult.
"""

import pytest

from src.scorers.base import BaseScorer, ScorerResult


class TestScorerResult:
    """Tests for ScorerResult dataclass."""

    def test_scorer_result_creation(self):
        """ScorerResult basic creation."""
        result = ScorerResult(
            name="test_scorer",
            score=0.85,
            weight=0.30,
            weighted_score=0.255,
            top_exemplar_refs=["doc-1", "doc-2"],
            explanation="High similarity match"
        )
        assert result.name == "test_scorer"
        assert result.score == 0.85
        assert result.weight == 0.30
        assert result.weighted_score == 0.255
        assert result.top_exemplar_refs == ["doc-1", "doc-2"]

    def test_scorer_result_empty_refs(self):
        """ScorerResult with empty refs."""
        result = ScorerResult(
            name="test",
            score=0.5,
            weight=0.2,
            weighted_score=0.1,
            top_exemplar_refs=[],
            explanation="No matches"
        )
        assert result.top_exemplar_refs == []


class ConcreteScorer(BaseScorer):
    """Concrete scorer for testing."""

    def score(self, value: float) -> ScorerResult:
        if not self._validate_inputs(value):
            return self._create_empty_result("Missing input")
        return ScorerResult(
            name=self.name,
            score=value,
            weight=self.weight,
            weighted_score=value * self.weight,
            top_exemplar_refs=[],
            explanation=f"Score: {value}"
        )


class TestBaseScorer:
    """Tests for BaseScorer."""

    def test_init(self):
        """BaseScorer initializes correctly."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        assert scorer.weight == 0.25
        assert scorer.name == "test"

    def test_validate_inputs_all_present(self):
        """Validate inputs when all present."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        assert scorer._validate_inputs("text", [1, 2], {"key": "value"}) is True

    def test_validate_inputs_none_value(self):
        """Validate inputs with None."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        assert scorer._validate_inputs(None) is False
        assert scorer._validate_inputs("text", None) is False

    def test_validate_inputs_empty_list(self):
        """Validate inputs with empty list."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        assert scorer._validate_inputs([]) is False

    def test_validate_inputs_empty_dict(self):
        """Validate inputs with empty dict."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        assert scorer._validate_inputs({}) is False

    def test_validate_inputs_empty_string(self):
        """Validate inputs with empty string."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        assert scorer._validate_inputs("") is False

    def test_validate_inputs_non_empty_string(self):
        """Validate inputs with non-empty string."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        assert scorer._validate_inputs("text") is True

    def test_validate_inputs_number(self):
        """Validate inputs with number (non-truthy check)."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        # Numbers are not iterable, so they pass the check
        assert scorer._validate_inputs(0) is True  # 0 is not None, not empty container
        assert scorer._validate_inputs(0.0) is True

    def test_create_empty_result(self):
        """Create empty result."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        result = scorer._create_empty_result("Missing input")
        assert result.score == 0.0
        assert result.weighted_score == 0.0
        assert result.top_exemplar_refs == []
        assert result.explanation == "Missing input"

    def test_get_top_refs_basic(self):
        """Get top refs from documents."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        docs = [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}, {"doc_id": "doc-3"}]
        refs = scorer._get_top_refs(docs, [0, 1, 2])
        assert refs == ["doc-1", "doc-2", "doc-3"]

    def test_get_top_refs_with_max(self):
        """Get top refs with max limit."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        docs = [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}, {"doc_id": "doc-3"}]
        refs = scorer._get_top_refs(docs, [0, 1, 2], max_refs=2)
        assert refs == ["doc-1", "doc-2"]

    def test_get_top_refs_empty_docs(self):
        """Get top refs with empty docs."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        refs = scorer._get_top_refs(None, [0, 1])
        assert refs == []

    def test_get_top_refs_no_doc_id(self):
        """Get top refs when doc_id missing."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        docs = [{"text": "no id"}, {"doc_id": "doc-2"}]
        refs = scorer._get_top_refs(docs, [0, 1])
        assert refs == ["doc-2"]  # Only doc with id

    def test_get_top_refs_out_of_bounds(self):
        """Get top refs with out-of-bounds indices."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        docs = [{"doc_id": "doc-1"}]
        refs = scorer._get_top_refs(docs, [0, 1, 2])  # 1, 2 out of bounds
        assert refs == ["doc-1"]

    def test_format_explanation_basic(self):
        """Format explanation basic."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        explanation = scorer._format_explanation("Score", 0.85)
        assert "Score" in explanation
        assert "0.85" in explanation

    def test_format_explanation_with_details(self):
        """Format explanation with details."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        explanation = scorer._format_explanation("Score", 0.85, details=["match", "similarity"])
        assert "match" in explanation
        assert "similarity" in explanation

    def test_abstract_method_required(self):
        """Abstract method must be implemented."""
        # Cannot instantiate BaseScorer directly
        with pytest.raises(TypeError):
            BaseScorer(weight=0.25, name="test")


class TestConcreteScorerIntegration:
    """Integration tests for ConcreteScorer."""

    def test_score_with_valid_input(self):
        """Score with valid input."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        result = scorer.score(0.75)
        assert result.score == 0.75
        assert result.weighted_score == 0.1875

    def test_score_with_invalid_input(self):
        """Score with invalid input."""
        scorer = ConcreteScorer(weight=0.25, name="test")
        result = scorer.score(None)
        assert result.score == 0.0
        assert result.explanation == "Missing input"