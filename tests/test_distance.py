"""
Unit tests for distance calculations
"""

import pytest
import math
from src.core.distance import (
    cosine_similarity,
    cosine_distance,
    max_cosine_similarity,
    top_k_similar,
    euclidean_distance,
    mahalanobis_distance
)
from src.core.exceptions import VectorDimensionMismatchError


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert cosine_similarity(v, v) == 1.0

    def test_zero_vectors(self):
        assert cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0
        assert cosine_similarity([0, 0, 0], [0, 0, 0]) == 0.0

    def test_orthogonal_vectors(self):
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        assert cosine_similarity(v1, v2) == 0.0

    def test_opposite_vectors(self):
        v1 = [1.0, 2.0, 3.0]
        v2 = [-1.0, -2.0, -3.0]
        assert cosine_similarity(v1, v2) == -1.0

    def test_different_dimensions_raises(self):
        with pytest.raises(VectorDimensionMismatchError):
            cosine_similarity([1, 2], [1, 2, 3])


class TestCosineDistance:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert cosine_distance(v, v) == 0.0

    def test_opposite_vectors(self):
        v1 = [1.0, 2.0, 3.0]
        v2 = [-1.0, -2.0, -3.0]
        assert cosine_distance(v1, v2) == 2.0


class TestMaxCosineSimilarity:
    def test_empty_vectors(self):
        assert max_cosine_similarity([1, 2], []) == 0.0

    def test_single_vector(self):
        query = [1.0, 0.0]
        vectors = [[1.0, 0.0]]
        assert max_cosine_similarity(query, vectors) == 1.0

    def test_multiple_vectors(self):
        query = [1.0, 0.0]
        vectors = [[0.5, 0.5], [1.0, 0.0], [0.0, 1.0]]
        # Should be 1.0 from identical vector
        assert max_cosine_similarity(query, vectors) == 1.0


class TestTopKSimilar:
    def test_top_2(self):
        query = [1.0, 0.0]
        vectors = [[0.5, 0.5], [1.0, 0.0], [0.0, 1.0], [0.8, 0.2]]
        result = top_k_similar(query, vectors, k=2)
        # Should be index 1 (1.0) and index 3 (~0.8)
        assert len(result) == 2
        assert result[0][0] == 1  # index of identical vector
        assert result[0][1] == 1.0  # similarity


class TestEuclideanDistance:
    def test_identical_vectors(self):
        assert euclidean_distance([1, 2, 3], [1, 2, 3]) == 0.0

    def test_simple_case(self):
        assert euclidean_distance([0, 0], [3, 4]) == 5.0


class TestMahalanobisDistance:
    def test_identity_covariance(self):
        # Identity matrix inverse
        cov_inv = [[1, 0], [0, 1]]
        mean = [0, 0]
        vector = [3, 4]
        # Should equal Euclidean distance when covariance is identity
        assert math.isclose(
            mahalanobis_distance(vector, mean, cov_inv),
            euclidean_distance(vector, mean),
            rel_tol=1e-5
        )