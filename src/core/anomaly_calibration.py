"""
Anomaly detection calibration methods.

This module implements:
- Isolation Forest calibration
- Mahalanobis distance calibration
- Feature normalization utilities
"""

from typing import Dict, List, Optional
import math

from .constants import (
    ISOLATION_FOREST_DEFAULTS,
    CONTAMINATION_BY_ENV,
    ANOMALY_FEATURES,
    FEATURE_NORMALIZATION,
    MIN_SAMPLE_SIZES,
)
from .dataclasses import MahalanobisParams
from .exceptions import CalibrationError, MatrixSingularError


def calibrate_isolation_forest(
    anomaly_scores: List[float],
    environment: str = "staging"
) -> Dict:
    """
    Calibrate Isolation Forest contamination rate.

    Environment affects the contamination rate:
    - development: 0.02 (tolerant)
    - staging: 0.01 (standard)
    - production: 0.005 (conservative)

    Args:
        anomaly_scores: List of anomaly scores from samples
        environment: Environment type ('development', 'staging', 'production')

    Returns:
        Dictionary with Isolation Forest configuration
    """
    contamination = CONTAMINATION_BY_ENV.get(environment, 0.01)

    # Calculate empirical contamination from scores
    sorted_scores = sorted(anomaly_scores)
    n = len(sorted_scores)

    # Validate contamination is within range
    min_cont, max_cont = ISOLATION_FOREST_DEFAULTS["contamination_range"]
    contamination = max(min_cont, min(max_cont, contamination))

    return {
        "contamination": contamination,
        "n_estimators": ISOLATION_FOREST_DEFAULTS["n_estimators"],
        "max_samples": ISOLATION_FOREST_DEFAULTS["max_samples"],
        "environment": environment,
        "sample_size": n,
    }


def calibrate_mahalanobis(
    accepted_features: List[List[float]],
    warn_percentile: int = 95,
    block_percentile: int = 99,
    regularization_lambda: float = 1e-6
) -> MahalanobisParams:
    """
    Calibrate Mahalanobis distance thresholds from accepted corpus.

    Formula: d_mahal = sqrt((x - mu)^T * Sigma^-1 * (x - mu))

    Args:
        accepted_features: List of feature vectors from accepted samples
        warn_percentile: Percentile for warn threshold
        block_percentile: Percentile for block threshold
        regularization_lambda: Regularization for numerical stability

    Returns:
        MahalanobisParams with mean, inverse covariance, and thresholds

    Raises:
        ValueError: If no features provided
    """
    if not accepted_features:
        raise CalibrationError("No accepted features provided")

    n = len(accepted_features)
    dim = len(accepted_features[0])

    # Compute mean
    mean = [sum(f[i] for f in accepted_features) / n for i in range(dim)]

    # Compute covariance matrix
    covariance = [[0.0] * dim for _ in range(dim)]
    for f in accepted_features:
        diff = [f[i] - mean[i] for i in range(dim)]
        for i in range(dim):
            for j in range(dim):
                covariance[i][j] += diff[i] * diff[j] / (n - 1)

    # Add regularization for numerical stability
    for i in range(dim):
        covariance[i][i] += regularization_lambda

    # Compute inverse using Gauss-Jordan elimination
    cov_inv = matrix_inverse(covariance)

    # Compute distances for accepted set
    distances = []
    for f in accepted_features:
        d = mahalanobis_distance(f, mean, cov_inv)
        distances.append(d)

    # Set thresholds from percentile
    sorted_distances = sorted(distances)
    warn_idx = int(n * warn_percentile / 100)
    warn_idx = min(warn_idx, n - 1)

    block_idx = int(n * block_percentile / 100)
    block_idx = min(block_idx, n - 1)

    return MahalanobisParams(
        mean=mean,
        covariance_inverse=cov_inv,
        warn_distance=sorted_distances[warn_idx],
        block_distance=sorted_distances[block_idx],
        regularization_lambda=regularization_lambda
    )


def matrix_inverse(matrix: List[List[float]]) -> List[List[float]]:
    """
    Compute matrix inverse using Gauss-Jordan elimination.

    Args:
        matrix: Square matrix to invert

    Returns:
        Inverse of the input matrix

    Raises:
        ValueError: If matrix is singular
    """
    n = len(matrix)
    # Create augmented matrix [A|I]
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]

    for i in range(n):
        # Find pivot
        max_row = i
        for k in range(i + 1, n):
            if abs(aug[k][i]) > abs(aug[max_row][i]):
                max_row = k
        aug[i], aug[max_row] = aug[max_row], aug[i]

        if abs(aug[i][i]) < 1e-10:
            raise MatrixSingularError("Matrix is singular and cannot be inverted")

        # Scale pivot row
        pivot = aug[i][i]
        for j in range(2 * n):
            aug[i][j] /= pivot

        # Eliminate other rows
        for k in range(n):
            if k != i:
                factor = aug[k][i]
                for j in range(2 * n):
                    aug[k][j] -= factor * aug[i][j]

    # Extract inverse
    return [row[n:] for row in aug]


def mahalanobis_distance(
    x: List[float],
    mean: List[float],
    cov_inv: List[List[float]]
) -> float:
    """
    Compute Mahalanobis distance.

    Args:
        x: Feature vector
        mean: Mean vector
        cov_inv: Inverse covariance matrix

    Returns:
        Mahalanobis distance value
    """
    diff = [xi - mi for xi, mi in zip(x, mean)]
    n = len(diff)

    # Compute diff^T * cov_inv * diff
    result = 0.0
    for i in range(n):
        for j in range(n):
            result += diff[i] * cov_inv[i][j] * diff[j]

    return math.sqrt(result)


def normalize_feature(feature_name: str, value: float) -> float:
    """
    Normalize a feature value according to feature normalization rules.

    Args:
        feature_name: Name of the feature to normalize
        value: Raw feature value

    Returns:
        Normalized feature value in [0, 1] range
    """
    if feature_name in FEATURE_NORMALIZATION:
        return FEATURE_NORMALIZATION[feature_name](value)
    return value


def normalize_feature_vector(
    features: Dict[str, float],
    feature_names: Optional[List[str]] = None
) -> List[float]:
    """
    Normalize a feature vector for anomaly detection.

    Args:
        features: Dictionary of feature name -> value
        feature_names: Optional list of feature names to use (default: ANOMALY_FEATURES)

    Returns:
        List of normalized feature values
    """
    if feature_names is None:
        feature_names = ANOMALY_FEATURES

    return [normalize_feature(name, features.get(name, 0.0)) for name in feature_names]


def compute_anomaly_score(distance: float) -> float:
    """
    Normalize Mahalanobis distance to anomaly score in [0, 1].

    Args:
        distance: Raw Mahalanobis distance

    Returns:
        Normalized anomaly score
    """
    return min(distance / 10.0, 1.0)


def validate_anomaly_features(
    features: List[List[float]],
    expected_dim: Optional[int] = None
) -> bool:
    """
    Validate that feature vectors have consistent dimensions.

    Args:
        features: List of feature vectors
        expected_dim: Expected dimension (optional, derived from first vector)

    Returns:
        True if valid

    Raises:
        ValueError: If dimensions are inconsistent
    """
    if not features:
        raise CalibrationError("No features provided")

    dim = len(features[0])
    if expected_dim is None:
        expected_dim = dim

    for i, f in enumerate(features):
        if len(f) != expected_dim:
            raise CalibrationError(
                f"Feature vector {i} has dimension {len(f)}, expected {expected_dim}"
            )

    return True


def get_anomaly_config_for_environment(environment: str) -> Dict:
    """
    Get anomaly detector configuration for specified environment.

    Args:
        environment: Environment type

    Returns:
        Configuration dictionary
    """
    return {
        "type": "isolation_forest",
        "contamination": CONTAMINATION_BY_ENV.get(environment, 0.01),
        "n_estimators": ISOLATION_FOREST_DEFAULTS["n_estimators"],
        "max_samples": ISOLATION_FOREST_DEFAULTS["max_samples"],
        "feature_set": ANOMALY_FEATURES.copy()
    }