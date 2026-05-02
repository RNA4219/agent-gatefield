"""
Calibration module - Threshold calibration pipeline.

This module provides calibration utilities for the state space gate system.
All implementation details are in the submodules:
- helpers.py: EWMA and uncertainty calculations
- pipeline.py: Main CalibrationPipeline class

Backward compatibility: Re-exports all items from parent directory modules.
"""

from .helpers import calculate_ewma, calculate_uncertainty_score
from .pipeline import CalibrationPipeline

# Re-export constants for backward compatibility
from ..constants import (
    DEFAULT_SCORER_WEIGHTS,
    WEIGHT_CONSTRAINTS,
    DEFAULT_THRESHOLDS,
    PERCENTILE_DEFAULTS,
    MIN_SAMPLE_SIZES,
    ISOLATION_FOREST_DEFAULTS,
    CONTAMINATION_BY_ENV,
    ANOMALY_FEATURES,
    FEATURE_NORMALIZATION,
    DRIFT_INDICATORS,
    DRIFT_RESPONSES,
    MIGRATION_CRITERIA,
    REPRODUCIBILITY_TARGET,
    ONLINE_ADJUSTMENT_LIMITS,
    CALIBRATION_TRIGGERS,
)

# Re-export data classes for backward compatibility
from ..dataclasses import (
    CalibrationResult,
    ThresholdVersion,
    DriftIndicators,
    MahalanobisParams,
    CalibrationProfile,
)

# Re-export anomaly functions for backward compatibility
from ..anomaly_calibration import normalize_feature

__all__ = [
    # Constants
    "DEFAULT_SCORER_WEIGHTS",
    "WEIGHT_CONSTRAINTS",
    "DEFAULT_THRESHOLDS",
    "PERCENTILE_DEFAULTS",
    "MIN_SAMPLE_SIZES",
    "ISOLATION_FOREST_DEFAULTS",
    "CONTAMINATION_BY_ENV",
    "ANOMALY_FEATURES",
    "FEATURE_NORMALIZATION",
    "DRIFT_INDICATORS",
    "DRIFT_RESPONSES",
    "MIGRATION_CRITERIA",
    "REPRODUCIBILITY_TARGET",
    "ONLINE_ADJUSTMENT_LIMITS",
    "CALIBRATION_TRIGGERS",
    # Data classes
    "CalibrationResult",
    "ThresholdVersion",
    "DriftIndicators",
    "MahalanobisParams",
    "CalibrationProfile",
    # Main class
    "CalibrationPipeline",
    # Utility functions
    "normalize_feature",
    "calculate_ewma",
    "calculate_uncertainty_score",
]