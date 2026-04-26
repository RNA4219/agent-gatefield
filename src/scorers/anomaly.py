"""
Anomaly Scorer.

Detects anomalies using Mahalanobis distance or Isolation Forest.
"""

from typing import List, Dict, Optional

from src.core.distance import mahalanobis_distance
from .base import BaseScorer, ScorerResult


class AnomalyScorer(BaseScorer):
    """
    Anomaly detection scorer.

    Uses Mahalanobis distance or isolation forest scores to detect anomalies.
    Higher score = more anomalous = more risky.
    """

    # Feature keys to extract from trajectory features
    FEATURE_KEYS = ['delta_semantic', 'tool_calls', 'branch_count', 'step_count', 'error_rate']

    def __init__(self, weight: float = 0.10, contamination: float = 0.01):
        """
        Initialize AnomalyScorer.

        Args:
            weight: Weight for this scorer in composite calculation (default: 0.10)
            contamination: Expected contamination ratio for isolation forest
        """
        super().__init__(weight=weight, name="anomaly")
        self.contamination = contamination

    def score(
        self,
        trajectory_features: Dict,
        feature_mean: Optional[List[float]] = None,
        feature_cov_inv: Optional[List[List[float]]] = None,
        isolation_scores: Optional[List[float]] = None
    ) -> ScorerResult:
        """
        Calculate anomaly score.

        Args:
            trajectory_features: Dict containing feature values for anomaly detection
            feature_mean: Mean vector for Mahalanobis distance
            feature_cov_inv: Inverse covariance matrix for Mahalanobis distance
            isolation_scores: Optional isolation forest scores for percentile ranking

        Returns:
            ScorerResult with anomaly score
        """
        if not self._validate_inputs(trajectory_features):
            return self._create_empty_result("Missing trajectory features")

        feature_values = self._extract_features(trajectory_features)

        anomaly_score, method = self._compute_anomaly_score(
            feature_values, feature_mean, feature_cov_inv, isolation_scores
        )
        weighted = anomaly_score * self.weight

        return ScorerResult(
            name=self.name,
            score=anomaly_score,
            weight=self.weight,
            weighted_score=weighted,
            top_exemplar_refs=[],
            explanation=f"Anomaly score: {anomaly_score:.4f} (method={method}, features={feature_values})"
        )

    def _extract_features(self, trajectory_features: Dict) -> List[float]:
        """
        Extract feature values from trajectory features dict.

        Args:
            trajectory_features: Dict with feature values

        Returns:
            List of feature values in consistent order
        """
        return [
            trajectory_features.get(key, 0.0)
            for key in self.FEATURE_KEYS
        ]

    def _compute_anomaly_score(
        self,
        feature_values: List[float],
        feature_mean: Optional[List[float]],
        feature_cov_inv: Optional[List[List[float]]],
        isolation_scores: Optional[List[float]]
    ) -> tuple:
        """
        Compute anomaly score using available method.

        Priority: Mahalanobis > Isolation Forest > Normalized sum

        Args:
            feature_values: List of feature values
            feature_mean: Mean vector for Mahalanobis
            feature_cov_inv: Inverse covariance for Mahalanobis
            isolation_scores: Isolation forest scores for percentile

        Returns:
            Tuple of (anomaly_score, method_name)
        """
        # Use Mahalanobis if covariance is available and dimensions match
        if feature_mean and feature_cov_inv:
            # Check dimension compatibility
            if self._validate_mahalanobis_dimensions(feature_values, feature_mean, feature_cov_inv):
                try:
                    mahal_dist = mahalanobis_distance(feature_values, feature_mean, feature_cov_inv)
                    # Convert to percentile-style score (higher = more anomalous)
                    anomaly_score = min(mahal_dist / 10.0, 1.0)  # Normalize
                    return anomaly_score, "mahalanobis"
                except Exception:
                    # Fallback to simple sum
                    anomaly_score = sum(abs(v) for v in feature_values) / len(feature_values)
                    return anomaly_score, "feature_sum_fallback"
            else:
                # Dimension mismatch fallback
                anomaly_score = sum(abs(v) for v in feature_values) / len(feature_values)
                return anomaly_score, "feature_sum_fallback"

        # Use percentile from isolation forest scores
        if isolation_scores:
            anomaly_score = self._compute_percentile(feature_values, isolation_scores)
            return anomaly_score, "isolation_forest_percentile"

        # Simple heuristic: normalize features and sum
        normalized = [min(abs(v) / 10.0, 1.0) for v in feature_values]
        anomaly_score = sum(normalized) / len(normalized)
        return anomaly_score, "normalized_sum"

    def _validate_mahalanobis_dimensions(
        self,
        feature_values: List[float],
        feature_mean: List[float],
        feature_cov_inv: List[List[float]]
    ) -> bool:
        """
        Validate dimension compatibility for Mahalanobis distance.

        Args:
            feature_values: Feature vector
            feature_mean: Mean vector
            feature_cov_inv: Inverse covariance matrix

        Returns:
            True if dimensions are compatible, False otherwise
        """
        n_features = len(feature_values)
        n_mean = len(feature_mean)
        n_cov_rows = len(feature_cov_inv)

        # Check that all dimensions match
        if n_features != n_mean or n_cov_rows != n_features:
            return False

        # Check that covariance matrix is square
        for row in feature_cov_inv:
            if len(row) != n_cov_rows:
                return False

        return True

    def _compute_percentile(
        self,
        feature_values: List[float],
        isolation_scores: List[float]
    ) -> float:
        """
        Compute percentile rank of current features in isolation scores.

        Args:
            feature_values: Current feature values
            isolation_scores: Historical isolation forest scores

        Returns:
            Percentile rank (0.0 to 1.0)
        """
        sorted_scores = sorted(isolation_scores)
        current_score = sum(abs(v) for v in feature_values)

        percentile = 0
        for i, s in enumerate(sorted_scores):
            if current_score <= s:
                percentile = (i + 1) / len(sorted_scores)
                break

        return percentile