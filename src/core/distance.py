"""
Cosine similarity and distance calculations
"""

import math
from typing import List

from .exceptions import VectorDimensionMismatchError


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    if len(v1) != len(v2):
        raise VectorDimensionMismatchError(len(v1), len(v2))

    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


def cosine_distance(v1: List[float], v2: List[float]) -> float:
    """Calculate cosine distance (1 - similarity)"""
    return 1.0 - cosine_similarity(v1, v2)


def max_cosine_similarity(query: List[float], vectors: List[List[float]]) -> float:
    """Get max similarity between query and a set of vectors"""
    if not vectors:
        return 0.0
    return max(cosine_similarity(query, v) for v in vectors)


def top_k_similar(
    query: List[float],
    vectors: List[List[float]],
    k: int = 5
) -> List[tuple[int, float]]:
    """Get top-k indices and similarities"""
    similarities = [(i, cosine_similarity(query, v)) for i, v in enumerate(vectors)]
    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:k]


def euclidean_distance(v1: List[float], v2: List[float]) -> float:
    """Calculate Euclidean distance"""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(v1, v2)))


def mahalanobis_distance(
    vector: List[float],
    mean: List[float],
    covariance_inv: List[List[float]]
) -> float:
    """
    Calculate Mahalanobis distance for anomaly detection
    Requires precomputed inverse covariance matrix
    """
    diff = [v - m for v, m in zip(vector, mean)]

    # (x - mu)^T * Cov^-1 * (x - mu)
    n = len(diff)
    result = 0.0
    for i in range(n):
        for j in range(n):
            result += diff[i] * covariance_inv[i][j] * diff[j]

    return math.sqrt(result)