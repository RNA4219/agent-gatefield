"""
Drift Scorer.

Measures trajectory drift from accepted baseline.
"""

from typing import List, Optional

from src.core.distance import cosine_similarity
from .base import BaseScorer, ScorerResult


class DriftScorer(BaseScorer):
    """
    Trajectory drift scorer.

    Measures deviation from the accepted trajectory baseline.
    Higher score = more drift = more risky.
    """

    def __init__(self, weight: float = 0.10):
        """
        Initialize DriftScorer.

        Args:
            weight: Weight for this scorer in composite calculation (default: 0.10)
        """
        super().__init__(weight=weight, name="drift")

    def score(
        self,
        current_vector: List[float],
        ewma_accepted: Optional[List[float]] = None,
        historical_accepted_vectors: Optional[List[List[float]]] = None
    ) -> ScorerResult:
        """
        Calculate drift score from accepted trajectory.

        Args:
            current_vector: Current semantic vector
            ewma_accepted: Exponentially weighted moving average of accepted vectors
            historical_accepted_vectors: Optional list of historical accepted vectors
                (used to compute centroid if ewma_accepted not provided)

        Returns:
            ScorerResult with drift score (1 - cosine similarity to baseline)
        """
        if not self._validate_inputs(current_vector):
            return self._create_empty_result("Missing current vector")

        # Get or compute baseline
        baseline = self._get_baseline(ewma_accepted, historical_accepted_vectors)
        if baseline is None:
            return self._create_empty_result("No accepted trajectory baseline available")

        sim = cosine_similarity(current_vector, baseline)
        drift_score = 1.0 - sim  # Higher drift = more deviation
        weighted = drift_score * self.weight

        return ScorerResult(
            name=self.name,
            score=drift_score,
            weight=self.weight,
            weighted_score=weighted,
            top_exemplar_refs=[],
            explanation=(
                f"Drift score: {drift_score:.4f} "
                f"(deviation from accepted trajectory baseline, similarity={sim:.4f})"
            )
        )

    def _get_baseline(
        self,
        ewma_accepted: Optional[List[float]],
        historical_vectors: Optional[List[List[float]]]
    ) -> Optional[List[float]]:
        """
        Get or compute the accepted baseline.

        Args:
            ewma_accepted: EWMA of accepted vectors (preferred)
            historical_vectors: Historical accepted vectors (fallback for centroid)

        Returns:
            Baseline vector, or None if unavailable
        """
        if ewma_accepted:
            return ewma_accepted

        if historical_vectors:
            return self._compute_centroid(historical_vectors)

        return None

    def _compute_centroid(self, vectors: List[List[float]]) -> List[float]:
        """
        Compute centroid of a list of vectors.

        Args:
            vectors: List of vectors

        Returns:
            Centroid vector
        """
        n = len(vectors)
        dims = len(vectors[0])
        return [sum(v[i] for v in vectors) / n for i in range(dims)]