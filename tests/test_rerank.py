"""
Tests for Reranker Module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.rerank import (
    RerankerStatus,
    RerankResult,
    SentenceTransformersReranker,
    DeterministicFallbackReranker,
    create_reranker,
    create_reranker_from_config,
    DEFAULT_MODEL,
    DEFAULT_TOP_K_INPUT,
    DEFAULT_TOP_K_OUTPUT,
)


class TestConstants:
    """Tests for reranker constants."""

    def test_default_model(self):
        """Default model is BAAI/bge-reranker-v2-m3."""
        assert DEFAULT_MODEL == "BAAI/bge-reranker-v2-m3"

    def test_default_top_k_values(self):
        """Default top-k values."""
        assert DEFAULT_TOP_K_INPUT == 50
        assert DEFAULT_TOP_K_OUTPUT == 10


class TestRerankResult:
    """Tests for RerankResult dataclass."""

    def test_rerank_result_creation(self):
        """RerankResult basic creation."""
        result = RerankResult(
            candidates=[{'doc_id': '1', 'text': 'test'}],
            model='test-model',
            status=RerankerStatus.SUCCESS
        )
        assert result.status == RerankerStatus.SUCCESS
        assert len(result.candidates) == 1

    def test_rerank_result_with_reason(self):
        """RerankResult with reason."""
        result = RerankResult(
            candidates=[],
            model='fallback',
            status=RerankerStatus.FALLBACK,
            reason='Model not available'
        )
        assert result.reason == 'Model not available'

    def test_rerank_result_default_values(self):
        """RerankResult default provider/runtime."""
        result = RerankResult(
            candidates=[],
            model='test',
            status=RerankerStatus.SUCCESS
        )
        assert result.provider == 'local'
        assert result.runtime == 'sentence_transformers'


class TestRerankerStatus:
    """Tests for RerankerStatus enum."""

    def test_status_values(self):
        """Status enum values."""
        assert RerankerStatus.SUCCESS.value == 'success'
        assert RerankerStatus.FALLBACK.value == 'fallback'
        assert RerankerStatus.UNAVAILABLE.value == 'unavailable'
        assert RerankerStatus.ERROR.value == 'error'


class TestSentenceTransformersReranker:
    """Tests for SentenceTransformersReranker."""

    def test_initialization(self):
        """Reranker initializes correctly."""
        reranker = SentenceTransformersReranker()
        assert reranker.model == DEFAULT_MODEL
        assert reranker.enabled is True
        assert reranker._cross_encoder is None
        assert reranker._initialized is False

    def test_initialization_custom_model(self):
        """Reranker with custom model."""
        reranker = SentenceTransformersReranker(model='custom-model')
        assert reranker.model == 'custom-model'

    def test_initialization_disabled(self):
        """Reranker disabled."""
        reranker = SentenceTransformersReranker(enabled=False)
        assert reranker.enabled is False

    def test_is_available_disabled(self):
        """is_available returns False when disabled."""
        reranker = SentenceTransformersReranker(enabled=False)
        assert reranker.is_available() is False

    def test_rerank_empty_candidates(self):
        """Rerank with empty candidates."""
        reranker = SentenceTransformersReranker()
        result = reranker.rerank('query', [], top_k=10)
        assert result.candidates == []
        assert result.status == RerankerStatus.SUCCESS

    def test_rerank_fallback_when_not_initialized(self):
        """Rerank uses fallback when model not initialized."""
        reranker = SentenceTransformersReranker(enabled=False)
        candidates = [{'doc_id': '1', 'text': 'test', 'similarity': 0.8}]
        result = reranker.rerank('query', candidates, top_k=1)
        assert result.status == RerankerStatus.FALLBACK
        assert result.candidates[0].get('fallback_rerank') is True

    def test_fallback_rerank(self):
        """Fallback rerank uses similarity."""
        reranker = SentenceTransformersReranker()
        candidates = [
            {'doc_id': '1', 'text': 'test1', 'similarity': 0.9},
            {'doc_id': '2', 'text': 'test2', 'similarity': 0.5},
        ]
        result = reranker._fallback_rerank('query', candidates, top_k=2)
        assert result.status == RerankerStatus.FALLBACK
        assert result.candidates[0]['similarity'] == 0.9  # Sorted by similarity

    def test_fallback_rerank_with_reason(self):
        """Fallback rerank with custom reason."""
        reranker = SentenceTransformersReranker()
        result = reranker._fallback_rerank('query', [], reason='Custom error')
        assert result.reason == 'Custom error'

    def test_get_info(self):
        """Get reranker info."""
        reranker = SentenceTransformersReranker(model='test-model')
        info = reranker.get_info()
        assert info['model'] == 'test-model'
        assert info['enabled'] is True
        assert info['provider'] == 'local'
        assert info['runtime'] == 'sentence_transformers'

    def test_get_info_after_init_attempt(self):
        """Get info after initialization attempt."""
        reranker = SentenceTransformersReranker(enabled=False)
        reranker.is_available()  # Triggers init
        info = reranker.get_info()
        assert info['initialized'] is True


class TestDeterministicFallbackReranker:
    """Tests for DeterministicFallbackReranker."""

    def test_initialization(self):
        """Fallback reranker initializes correctly."""
        reranker = DeterministicFallbackReranker()
        assert reranker.model == 'fallback-deterministic'
        assert reranker.enabled is True

    def test_is_available(self):
        """Fallback reranker always available."""
        reranker = DeterministicFallbackReranker()
        assert reranker.is_available() is True

    def test_rerank_empty_candidates(self):
        """Rerank with empty candidates."""
        reranker = DeterministicFallbackReranker()
        result = reranker.rerank('query', [], top_k=10)
        assert result.candidates == []
        assert result.status == RerankerStatus.SUCCESS  # Empty returns SUCCESS

    def test_rerank_with_candidates(self):
        """Rerank uses similarity."""
        reranker = DeterministicFallbackReranker()
        candidates = [
            {'doc_id': '1', 'text': 'test1', 'similarity': 0.7},
            {'doc_id': '2', 'text': 'test2', 'similarity': 0.9},
        ]
        result = reranker.rerank('query', candidates, top_k=2)
        assert result.status == RerankerStatus.FALLBACK
        # Sorted by similarity descending
        assert result.candidates[0]['similarity'] == 0.9

    def test_rerank_top_k(self):
        """Rerank respects top_k."""
        reranker = DeterministicFallbackReranker()
        candidates = [
            {'doc_id': '1', 'text': 'test', 'similarity': 0.5},
            {'doc_id': '2', 'text': 'test', 'similarity': 0.6},
            {'doc_id': '3', 'text': 'test', 'similarity': 0.7},
        ]
        result = reranker.rerank('query', candidates, top_k=2)
        assert len(result.candidates) == 2

    def test_get_info(self):
        """Get fallback reranker info."""
        reranker = DeterministicFallbackReranker()
        info = reranker.get_info()
        assert info['model'] == 'fallback-deterministic'
        assert info['available'] is True
        assert info['semantic'] is False


class TestCreateReranker:
    """Tests for create_reranker function."""

    def test_create_reranker_default(self):
        """Create reranker with defaults."""
        reranker = create_reranker()
        assert isinstance(reranker, SentenceTransformersReranker)
        assert reranker.model == DEFAULT_MODEL

    def test_create_reranker_custom_model(self):
        """Create reranker with custom model."""
        reranker = create_reranker(model='custom-model')
        assert reranker.model == 'custom-model'

    def test_create_reranker_disabled(self):
        """Create disabled reranker."""
        reranker = create_reranker(enabled=False)
        assert reranker.enabled is False

    def test_create_reranker_fallback(self):
        """Create fallback reranker."""
        reranker = create_reranker(use_fallback=True)
        assert isinstance(reranker, DeterministicFallbackReranker)


class TestCreateRerankerFromConfig:
    """Tests for create_reranker_from_config function."""

    def test_create_from_config_default(self):
        """Create from empty config."""
        reranker = create_reranker_from_config({})
        assert isinstance(reranker, SentenceTransformersReranker)

    def test_create_from_config_with_reranker_settings(self):
        """Create from config with reranker settings."""
        config = {
            'state_space_gate': {
                'reranker': {
                    'enabled': True,
                    'model': 'custom-model'
                }
            }
        }
        reranker = create_reranker_from_config(config)
        assert reranker.model == 'custom-model'

    def test_create_from_config_disabled(self):
        """Create disabled reranker from config."""
        config = {
            'state_space_gate': {
                'reranker': {
                    'enabled': False
                }
            }
        }
        reranker = create_reranker_from_config(config)
        assert reranker.enabled is False


class TestRerankSorting:
    """Tests for rerank sorting behavior."""

    def test_fallback_sorts_by_similarity(self):
        """Fallback rerank sorts by similarity descending."""
        reranker = DeterministicFallbackReranker()
        candidates = [
            {'doc_id': 'a', 'text': 'text a', 'similarity': 0.3},
            {'doc_id': 'b', 'text': 'text b', 'similarity': 0.9},
            {'doc_id': 'c', 'text': 'text c', 'similarity': 0.5},
        ]
        result = reranker.rerank('query', candidates, top_k=3)

        # Should be sorted descending
        scores = [c['reranker_score'] for c in result.candidates]
        assert scores == [0.9, 0.5, 0.3]

    def test_reranker_score_added(self):
        """Rerank adds reranker_score to candidates."""
        reranker = DeterministicFallbackReranker()
        candidates = [{'doc_id': '1', 'text': 'test', 'similarity': 0.8}]
        result = reranker.rerank('query', candidates, top_k=1)
        assert 'reranker_score' in result.candidates[0]
        assert result.candidates[0]['reranker_score'] == 0.8


class TestRerankIntegration:
    """Integration-like tests."""

    def test_full_rerank_workflow(self):
        """Full rerank workflow."""
        reranker = DeterministicFallbackReranker()
        candidates = [
            {'doc_id': '1', 'text': 'relevant text', 'similarity': 0.85},
            {'doc_id': '2', 'text': 'less relevant', 'similarity': 0.60},
            {'doc_id': '3', 'text': 'irrelevant', 'similarity': 0.30},
        ]

        result = reranker.rerank('search query', candidates, top_k=2)

        assert len(result.candidates) == 2
        assert result.status == RerankerStatus.FALLBACK
        assert result.candidates[0]['doc_id'] == '1'
        assert result.candidates[1]['doc_id'] == '2'

    def test_rerank_preserves_other_fields(self):
        """Rerank preserves candidate fields."""
        reranker = DeterministicFallbackReranker()
        candidates = [
            {
                'doc_id': '1',
                'text': 'test',
                'similarity': 0.8,
                'axis_type': 'taboo',
                'labels': {'severity': 'high'}
            }
        ]
        result = reranker.rerank('query', candidates, top_k=1)
        assert result.candidates[0]['axis_type'] == 'taboo'
        assert result.candidates[0]['labels'] == {'severity': 'high'}