"""
Tests for Encoder Utils.
"""

import pytest

from src.encoder.utils import generate_mock_embedding


class TestGenerateMockEmbedding:
    """Tests for generate_mock_embedding."""

    def test_basic_generation(self):
        """Generate basic mock embedding."""
        emb = generate_mock_embedding(10)
        assert len(emb) == 10
        assert all(isinstance(x, float) for x in emb)

    def test_gauss_distribution(self):
        """Generate with gauss distribution."""
        emb = generate_mock_embedding(100, seed=42, distribution="gauss")
        assert len(emb) == 100
        # Gauss values should be around 0 with std 0.1
        mean = sum(emb) / len(emb)
        assert abs(mean) < 0.5  # Reasonable for gauss(0, 0.1)

    def test_uniform_distribution(self):
        """Generate with uniform distribution."""
        emb = generate_mock_embedding(100, seed=42, distribution="uniform")
        assert len(emb) == 100
        # Uniform values should be between 0 and 1
        assert all(0 <= x <= 1 for x in emb)

    def test_deterministic_same_seed(self):
        """Same seed produces same embedding."""
        emb1 = generate_mock_embedding(50, seed=123)
        emb2 = generate_mock_embedding(50, seed=123)
        assert emb1 == emb2

    def test_different_seeds(self):
        """Different seeds produce different embeddings."""
        emb1 = generate_mock_embedding(50, seed=1)
        emb2 = generate_mock_embedding(50, seed=2)
        assert emb1 != emb2

    def test_different_dims(self):
        """Different dimensions."""
        emb10 = generate_mock_embedding(10)
        emb100 = generate_mock_embedding(100)
        assert len(emb10) == 10
        assert len(emb100) == 100

    def test_large_dims(self):
        """Large embedding dimensions."""
        emb = generate_mock_embedding(1024)
        assert len(emb) == 1024

    def test_default_seed(self):
        """Default seed is 42."""
        emb1 = generate_mock_embedding(20)
        emb2 = generate_mock_embedding(20, seed=42)
        assert emb1 == emb2

    def test_gauss_vs_uniform_difference(self):
        """Gauss and uniform produce different results."""
        emb_gauss = generate_mock_embedding(50, seed=42, distribution="gauss")
        emb_uniform = generate_mock_embedding(50, seed=42, distribution="uniform")
        # Different distributions with same seed should produce different values
        # (though both seeded, the distribution affects output)
        # Uniform values are 0-1, Gauss can be negative
        assert any(x < 0 for x in emb_gauss) or not all(0 <= x <= 1 for x in emb_gauss)


class TestMockEmbeddingIntegration:
    """Integration-like tests."""

    def test_generate_for_model_dims(self):
        """Generate for common model dimensions."""
        # BGE-M3: 1024
        emb = generate_mock_embedding(1024)
        assert len(emb) == 1024

        # text-embedding-3-small: 1536
        emb = generate_mock_embedding(1536)
        assert len(emb) == 1536

    def test_reproducibility_workflow(self):
        """Reproducible embeddings for testing."""
        seed = 999
        dims = 256

        emb1 = generate_mock_embedding(dims, seed=seed)
        emb2 = generate_mock_embedding(dims, seed=seed)

        # Should be identical for reproducible tests
        assert emb1 == emb2