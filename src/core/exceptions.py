"""
Custom exceptions for agent-gatefield gate system.

This module provides specialized exception classes for:
- Gate evaluation errors
- Calibration errors
- Threshold errors
- Drift detection errors
- Versioning errors
"""

from typing import Dict, List, Optional, Any


class GateEvaluationError(Exception):
    """Base exception for gate evaluation errors."""

    def __init__(self, message: str, decision_id: Optional[str] = None):
        super().__init__(message)
        self.decision_id = decision_id


class CalibrationError(Exception):
    """Base exception for calibration errors."""

    def __init__(self, message: str, profile_id: Optional[str] = None):
        super().__init__(message)
        self.profile_id = profile_id


class InsufficientSamplesError(CalibrationError):
    """Raised when sample count is below minimum requirement."""

    def __init__(self, axis: str, actual: int, required: int):
        message = f"Insufficient samples for {axis}: {actual} < {required}"
        super().__init__(message)
        self.axis = axis
        self.actual_count = actual
        self.required_count = required


class WeightValidationError(CalibrationError):
    """Raised when weight constraints are violated."""

    def __init__(self, message: str, weights: Optional[Dict] = None):
        super().__init__(message)
        self.weights = weights


class ThresholdError(Exception):
    """Base exception for threshold errors."""

    def __init__(self, message: str, threshold_name: Optional[str] = None):
        super().__init__(message)
        self.threshold_name = threshold_name


class ThresholdNotFoundError(ThresholdError):
    """Raised when threshold cannot be found for specified version."""

    def __init__(self, version: str):
        message = f"Threshold not found for version: {version}"
        super().__init__(message, version)
        self.version = version


class InvalidThresholdError(ThresholdError):
    """Raised when threshold value is invalid."""

    def __init__(self, threshold_name: str, value: Any, reason: str):
        message = f"Invalid threshold {threshold_name}={value}: {reason}"
        super().__init__(message, threshold_name)
        self.value = value
        self.reason = reason


class DriftDetectionError(Exception):
    """Raised when drift detection fails."""

    def __init__(self, message: str, axis: Optional[str] = None):
        super().__init__(message)
        self.axis = axis


class EmptyDistributionError(DriftDetectionError):
    """Raised when score distribution is empty."""

    def __init__(self, distribution_type: str):
        message = f"{distribution_type} distribution is empty"
        super().__init__(message)
        self.distribution_type = distribution_type


class VectorDimensionMismatchError(Exception):
    """Raised when vector dimensions don't match."""

    def __init__(self, dim1: int, dim2: int):
        message = f"Vector dimension mismatch: {dim1} vs {dim2}"
        super().__init__(message)
        self.dimension1 = dim1
        self.dimension2 = dim2


class MatrixSingularError(Exception):
    """Raised when matrix cannot be inverted."""

    def __init__(self, reason: str = "Matrix is singular"):
        super().__init__(reason)
        self.reason = reason


class VersionError(Exception):
    """Base exception for version-related errors."""

    def __init__(self, message: str, version: Optional[str] = None):
        super().__init__(message)
        self.version = version


class InvalidVersionStringError(VersionError):
    """Raised when version string format is invalid."""

    def __init__(self, version_str: str):
        message = f"Invalid version string: {version_str}"
        super().__init__(message, version_str)


class VersionLockError(VersionError):
    """Raised when version cannot be locked or unlocked."""

    def __init__(self, version: str, reason: str):
        message = f"Version lock error for {version}: {reason}"
        super().__init__(message, version)
        self.reason = reason


class MigrationValidationError(CalibrationError):
    """Raised when threshold migration validation fails."""

    def __init__(self, violations: List[str]):
        message = "Migration validation failed: " + "; ".join(violations)
        super().__init__(message)
        self.violations = violations


class ReproducibilityError(CalibrationError):
    """Raised when reproducibility target is not met."""

    def __init__(self, match_rate: float, target: float):
        message = f"Reproducibility {match_rate*100:.1f}% below target {target*100:.1f}%"
        super().__init__(message)
        self.match_rate = match_rate
        self.target_rate = target


class ReviewQueueError(Exception):
    """Base exception for review queue errors."""

    def __init__(self, message: str, item_id: Optional[str] = None):
        super().__init__(message)
        self.item_id = item_id


class ItemNotFoundError(ReviewQueueError):
    """Raised when review item is not found."""

    def __init__(self, decision_id: str):
        message = f"Item {decision_id} not found in queue"
        super().__init__(message, decision_id)


class PairNotFoundError(ReviewQueueError):
    """Raised when comparison pair is not found."""

    def __init__(self, pair_id: str):
        message = f"Pair {pair_id} not found"
        super().__init__(message, pair_id)