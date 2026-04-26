"""
Encoder utilities - Shared functions for embedding operations.
"""

import random
from typing import List


def generate_mock_embedding(dims: int, seed: int = 42, distribution: str = "gauss") -> List[float]:
    """
    Generate deterministic mock embedding for testing without API.

    Args:
        dims: Number of dimensions for the embedding vector
        seed: Random seed for deterministic output (default: 42)
        distribution: Distribution type - "gauss" or "uniform" (default: "gauss")

    Returns:
        List of floats representing a mock embedding vector
    """
    random.seed(seed)
    if distribution == "gauss":
        return [random.gauss(0, 0.1) for _ in range(dims)]
    else:
        return [random.random() for _ in range(dims)]


__all__ = ['generate_mock_embedding']