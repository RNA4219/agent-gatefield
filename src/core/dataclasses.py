"""
Data classes for calibration module.

This module contains all dataclasses used by the calibration system:
- CalibrationResult: Result of a calibration operation
- ThresholdVersion: Version identifier for threshold configuration
- DriftIndicators: Drift detection indicators for a scorer axis
- MahalanobisParams: Parameters for Mahalanobis distance calculation
- CalibrationProfile: Complete calibration profile configuration
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from .exceptions import InvalidVersionStringError


@dataclass
class CalibrationResult:
    """
    Result of a calibration operation.

    Attributes:
        axis: The scorer axis that was calibrated
        old_threshold: Previous threshold value
        new_threshold: New threshold value after calibration
        sample_size: Number of samples used for calibration
        metric_name: Name of the metric used (e.g., 'accepted_p95')
        metric_value: Value of the metric
    """
    axis: str
    old_threshold: float
    new_threshold: float
    sample_size: int
    metric_name: str
    metric_value: float


@dataclass
class ThresholdVersion:
    """
    Version identifier for threshold configuration.

    Version format: threshold-v{major}.{minor}-{timestamp}

    Attributes:
        major: Major version number (breaking changes)
        minor: Minor version number (non-breaking changes)
        timestamp: When this version was created
    """
    major: int
    minor: int
    timestamp: datetime

    def __str__(self) -> str:
        """Return formatted version string."""
        return f"threshold-v{self.major}.{self.minor}-{self.timestamp.strftime('%Y%m%d')}"

    @classmethod
    def parse(cls, version_str: str) -> "ThresholdVersion":
        """
        Parse version string like 'threshold-v1.0-20250115'.

        Args:
            version_str: Version string to parse

        Returns:
            ThresholdVersion instance

        Raises:
            ValueError: If version string format is invalid
        """
        parts = version_str.split("-")
        if len(parts) != 3 or not parts[0] == "threshold":
            raise InvalidVersionStringError(version_str)
        major_minor = parts[1].lstrip("v").split(".")
        major = int(major_minor[0])
        minor = int(major_minor[1]) if len(major_minor) > 1 else 0
        timestamp = datetime.strptime(parts[2], "%Y%m%d")
        return cls(major=major, minor=minor, timestamp=timestamp)


@dataclass
class DriftIndicators:
    """
    Drift detection indicators for a scorer axis.

    Attributes:
        score_mean_shift: |mu_current - mu_baseline| / sigma_baseline
        score_variance_shift: sigma_current / sigma_baseline
        threshold_crossing_rate: Ratio of current/baseline crossing rates
        override_rate: Current override rate
        alert_triggered: Whether drift alert is triggered
        drift_type: Type of drift detected if alert triggered
    """
    score_mean_shift: float = 0.0
    score_variance_shift: float = 1.0
    threshold_crossing_rate: float = 1.0
    override_rate: float = 0.0
    alert_triggered: bool = False
    drift_type: Optional[str] = None


@dataclass
class MahalanobisParams:
    """
    Parameters for Mahalanobis distance calculation.

    Formula: d_mahal = sqrt((x - mu)^T * Sigma^-1 * (x - mu))

    Attributes:
        mean: Mean vector of the feature distribution
        covariance_inverse: Inverse of covariance matrix
        warn_distance: Warning threshold distance
        block_distance: Blocking threshold distance
        regularization_lambda: Regularization parameter for numerical stability
    """
    mean: List[float]
    covariance_inverse: List[List[float]]
    warn_distance: Optional[float] = None
    block_distance: Optional[float] = None
    regularization_lambda: float = 1e-6

    def to_dict(self) -> Dict:
        """Serialize parameters to dictionary."""
        return {
            "mean": self.mean,
            "covariance_inverse": self.covariance_inverse,
            "warn_distance": self.warn_distance,
            "block_distance": self.block_distance,
            "regularization_lambda": self.regularization_lambda,
        }


@dataclass
class CalibrationProfile:
    """
    Complete calibration profile configuration.

    Attributes:
        profile_id: Unique identifier for this profile
        scope: Scope of application ('repo', 'project', 'global')
        threshold_version: Current threshold version
        weights: Scorer weights for composite score calculation
        warn_thresholds: Warning thresholds for each axis
        block_thresholds: Blocking thresholds for each axis
        anomaly_detector_config: Configuration for anomaly detector
        mahalanobis_params: Mahalanobis distance parameters
        calibration_metrics: Performance metrics from calibration
        updated_at: Last update timestamp
    """
    profile_id: str
    scope: str
    threshold_version: ThresholdVersion
    weights: Dict[str, float] = field(default_factory=dict)
    warn_thresholds: Dict[str, Optional[float]] = field(default_factory=dict)
    block_thresholds: Dict[str, Optional[float]] = field(default_factory=dict)
    anomaly_detector_config: Dict[str, Any] = field(default_factory=dict)
    mahalanobis_params: Optional[MahalanobisParams] = None
    calibration_metrics: Dict[str, float] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Serialize profile to dictionary for storage."""
        return {
            "profile_id": self.profile_id,
            "scope": self.scope,
            "threshold_version": str(self.threshold_version),
            "weights": self.weights,
            "warn_thresholds": self.warn_thresholds,
            "block_thresholds": self.block_thresholds,
            "anomaly_detector": self.anomaly_detector_config,
            "mahalanobis_params": self.mahalanobis_params.to_dict() if self.mahalanobis_params else None,
            "calibration_metrics": self.calibration_metrics,
            "updated_at": self.updated_at.isoformat(),
        }