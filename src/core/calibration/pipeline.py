"""
Calibration pipeline orchestrator for agent-gatefield state space gate system.

This module provides the main CalibrationPipeline class that coordinates:
- Threshold calibration operations
- Drift detection and response
- Anomaly detection calibration
- Online calibration triggers
- Reproducibility verification
- Profile management

All implementation details are in the submodules:
- constants.py: All configuration constants
- dataclasses.py: Data classes for results and configurations
- threshold_calibration.py: Threshold calculation methods
- drift_detection.py: Drift indicator computation
- anomaly_calibration.py: Isolation Forest and Mahalanobis
- online_calibration.py: Correction incorporation and triggers
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timezone
from collections import defaultdict

from ..exceptions import CalibrationError, InsufficientSamplesError, WeightValidationError

logger = logging.getLogger(__name__)

# Import helpers
from .helpers import calculate_ewma, calculate_uncertainty_score
from .eval import (
    compute_metrics,
    compute_auc,
    validate_migration,
    verify_reproducibility,
    validate_weights,
    compute_weighted_score,
    predict_from_thresholds,
    load_dataset,
    run_offline_evaluation,
)

# Import constants
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

# Import data classes
from ..dataclasses import (
    CalibrationResult,
    ThresholdVersion,
    DriftIndicators,
    MahalanobisParams,
    CalibrationProfile,
)

# Import threshold calibration functions
from ..threshold_calibration import (
    calibrate_taboo_threshold,
    calibrate_drift_threshold,
    calibrate_anomaly_percentile,
    calibrate_constitution_threshold,
    get_effective_threshold,
    get_percentile_value,
)

# Import drift detection functions
from ..drift_detection import (
    compute_drift_indicators,
    classify_drift_type,
    get_drift_response,
    compute_rolling_statistics,
    detect_threshold_decay,
)

# Import anomaly calibration functions
from ..anomaly_calibration import (
    calibrate_isolation_forest,
    calibrate_mahalanobis,
    matrix_inverse,
    mahalanobis_distance,
    normalize_feature,
    normalize_feature_vector,
    compute_anomaly_score,
    validate_anomaly_features,
    get_anomaly_config_for_environment,
)

# Import online calibration functions
from ..online_calibration import (
    incorporate_correction,
    check_calibration_trigger,
    compute_threshold_adjustment,
    validate_weight_adjustment,
    apply_online_correction,
    get_calibration_priority,
    should_trigger_immediate_recalibration,
)


class CalibrationPipeline:
    """
    Threshold calibration pipeline orchestrator.

    Implements the calibration methodology specified in CALIBRATION_THRESHOLD_SPEC.md.
    Coordinates all calibration operations across the submodules.
    """

    def __init__(self, profile_id: str, scope: str = "repo"):
        """
        Initialize calibration pipeline.

        Args:
            profile_id: Unique identifier for this calibration profile
            scope: Scope of application ('repo', 'project', 'global')
        """
        self.profile_id = profile_id
        self.scope = scope
        self.results: List[CalibrationResult] = []
        self.drift_indicators: Dict[str, DriftIndicators] = {}
        self._baseline_distributions: Dict[str, Dict] = {}

    # =========================================================================
    # Percentile-Based Threshold Calculation (Section 3)
    # =========================================================================

    def calibrate_taboo_threshold(
        self,
        accepted_scores: List[float],
        rejected_scores: Optional[List[float]] = None,
        percentile: int = 95
    ) -> CalibrationResult:
        """
        Set taboo threshold based on accepted distribution percentile.

        For risk-side scorers like taboo, higher scores are riskier.
        The threshold is set at the percentile of accepted distribution.

        Args:
            accepted_scores: List of scores from accepted samples
            rejected_scores: Optional list of rejected scores (unused)
            percentile: Percentile to use for threshold

        Returns:
            CalibrationResult with new threshold
        """
        result = calibrate_taboo_threshold(accepted_scores, rejected_scores, percentile)
        self.results.append(result)
        return result

    def calibrate_drift_threshold(
        self,
        accepted_drift_scores: List[float],
        warn_percentile: int = 95,
        block_percentile: int = 99
    ) -> Dict[str, CalibrationResult]:
        """
        Calibrate drift thresholds from accepted distribution.

        Returns warn and block thresholds as separate results.

        Args:
            accepted_drift_scores: List of drift scores from accepted samples
            warn_percentile: Percentile for warn threshold
            block_percentile: Percentile for block threshold

        Returns:
            Dictionary with 'warn' and 'block' CalibrationResult entries
        """
        results = calibrate_drift_threshold(accepted_drift_scores, warn_percentile, block_percentile)
        self.results.extend([results["warn"], results["block"]])
        return results

    def calibrate_anomaly_percentile(
        self,
        anomaly_scores: List[float],
        warn_percentile: int = 95,
        block_percentile: int = 99
    ) -> Dict:
        """
        Set anomaly thresholds from contamination estimate.

        Uses percentile approach for Isolation Forest or other anomaly detectors.

        Args:
            anomaly_scores: List of anomaly scores
            warn_percentile: Percentile for warn threshold
            block_percentile: Percentile for block threshold

        Returns:
            Dictionary with threshold values and metadata
        """
        return calibrate_anomaly_percentile(anomaly_scores, warn_percentile, block_percentile)

    def calibrate_constitution_threshold(
        self,
        accepted_scores: List[float],
        warn_percentile: int = 5,
        block_percentile: int = 1
    ) -> Dict[str, CalibrationResult]:
        """
        Calibrate constitution alignment threshold (safe-side scorer).

        For safe-side scorers, lower scores are riskier.
        The threshold is set on the lower bound of accepted distribution.

        Args:
            accepted_scores: List of constitution alignment scores
            warn_percentile: Percentile for warn threshold (lower bound)
            block_percentile: Percentile for block threshold (lower bound)

        Returns:
            Dictionary with 'warn' and 'block' CalibrationResult entries
        """
        results = calibrate_constitution_threshold(accepted_scores, warn_percentile, block_percentile)
        self.results.extend([results["warn"], results["block"]])
        return results

    # =========================================================================
    # Anomaly Detection Calibration (Section 8)
    # =========================================================================

    def calibrate_isolation_forest(
        self,
        anomaly_scores: List[float],
        environment: str = "staging"
    ) -> Dict:
        """
        Calibrate Isolation Forest contamination rate.

        Environment affects the contamination rate.

        Args:
            anomaly_scores: List of anomaly scores
            environment: Environment type

        Returns:
            Dictionary with Isolation Forest configuration
        """
        return calibrate_isolation_forest(anomaly_scores, environment)

    def calibrate_mahalanobis(
        self,
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
        """
        return calibrate_mahalanobis(
            accepted_features, warn_percentile, block_percentile, regularization_lambda
        )

    def compute_anomaly_score(self, distance: float) -> float:
        """Normalize Mahalanobis distance to anomaly score in [0, 1]."""
        return compute_anomaly_score(distance)

    # Private helper methods for backward compatibility (used by tests)
    def _matrix_inverse(self, matrix: List[List[float]]) -> List[List[float]]:
        """
        Compute matrix inverse using Gauss-Jordan elimination.

        Args:
            matrix: Square matrix to invert

        Returns:
            Inverse of the input matrix

        Raises:
            ValueError: If matrix is singular
        """
        return matrix_inverse(matrix)

    def _mahalanobis_distance(
        self,
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
        return mahalanobis_distance(x, mean, cov_inv)

    # =========================================================================
    # Metrics Computation (Section 4.4)
    # =========================================================================

    def compute_metrics(
        self,
        predictions: List[str],
        labels: List[str],
        scores: Optional[List[float]] = None
    ) -> Dict:
        """
        Compute precision, recall, F1, AUC, and additional calibration metrics.

        Args:
            predictions: List of "block" or "pass" predictions
            labels: List of "block" or "pass" ground truth
            scores: Optional list of prediction confidence scores for AUC

        Returns:
            Dictionary with precision, recall, f1, tp, fp, tn, fn, auc, false_escalation
        """
        return compute_metrics(predictions, labels, scores)

    # =========================================================================
    # Threshold Versioning (Section 5)
    # =========================================================================

    def generate_threshold_version(
        self,
        major: int = 1,
        minor: int = 0,
        is_breaking_change: bool = False
    ) -> ThresholdVersion:
        """
        Generate a new threshold version identifier.

        Version format: threshold-v{major}.{minor}-{timestamp}

        Args:
            major: Major version number
            minor: Minor version number
            is_breaking_change: If True, indicates a breaking change
        """
        return ThresholdVersion(
            major=major,
            minor=minor,
            timestamp=datetime.now(timezone.utc)
        )

    def validate_migration(
        self,
        old_metrics: Dict[str, float],
        new_metrics: Dict[str, float]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that migration meets degradation criteria.

        Returns (is_valid, list_of_violations).
        """
        return validate_migration(old_metrics, new_metrics)

    # =========================================================================
    # Drift Detection (Section 9)
    # =========================================================================

    def compute_drift_indicators(
        self,
        current_scores: List[float],
        baseline_scores: List[float],
        axis: str,
        override_rate: float = 0.0,
        threshold_crossing_rate: float = 1.0
    ) -> DriftIndicators:
        """
        Compute drift indicators comparing current to baseline distribution.

        Args:
            current_scores: Recent score distribution
            baseline_scores: Calibration baseline distribution
            axis: Scorer axis name
            override_rate: Current override rate
            threshold_crossing_rate: Ratio of current/baseline crossing rates
        """
        indicators = compute_drift_indicators(
            current_scores, baseline_scores, axis, override_rate, threshold_crossing_rate
        )
        self.drift_indicators[axis] = indicators
        return indicators

    def get_drift_response(self, drift_type: str) -> str:
        """Get recommended response for a drift type."""
        return get_drift_response(drift_type)

    # =========================================================================
    # Online Calibration (Section 7)
    # =========================================================================

    def incorporate_correction(
        self,
        correction_type: str,
        current_threshold: float,
        current_weights: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Process a human correction and compute adjustment.

        Args:
            correction_type: "pass_to_block", "block_to_pass", "threshold_adjust", "weight_adjust"
            current_threshold: Current threshold value
            current_weights: Current scorer weights

        Returns:
            Dictionary with recommended adjustments
        """
        return incorporate_correction(correction_type, current_threshold, current_weights)

    def check_calibration_trigger(
        self,
        override_count: int,
        total_decisions: int,
        window_days: int = 7
    ) -> Dict[str, Any]:
        """
        Check if automatic calibration should be triggered.

        Args:
            override_count: Number of overrides in window
            total_decisions: Total decisions in window
            window_days: Days in the window

        Returns:
            Dictionary with trigger status and recommended action
        """
        return check_calibration_trigger(override_count, total_decisions, window_days)

    # =========================================================================
    # Reproducibility Verification (Section 6.4)
    # =========================================================================

    def verify_reproducibility(
        self,
        original_decisions: List[str],
        replay_decisions: List[str],
        tolerance: float = REPRODUCIBILITY_TARGET
    ) -> Dict[str, Any]:
        """
        Verify replay achieves 99% identical decisions.

        Args:
            original_decisions: Original gate decisions
            replay_decisions: Decisions from replay with new thresholds
            tolerance: Required match rate (default 99%)

        Returns:
            Dictionary with reproducibility metrics and divergence details
        """
        return verify_reproducibility(original_decisions, replay_decisions, tolerance)

    # =========================================================================
    # Profile Management
    # =========================================================================

    def create_profile(
        self,
        weights: Optional[Dict[str, float]] = None,
        version: Optional[ThresholdVersion] = None
    ) -> CalibrationProfile:
        """
        Create a new calibration profile.

        Args:
            weights: Custom weights (defaults to DEFAULT_SCORER_WEIGHTS)
            version: Custom version (defaults to new version)
        """
        if weights is None:
            weights = DEFAULT_SCORER_WEIGHTS.copy()

        # Validate weights
        self._validate_weights(weights)

        if version is None:
            version = self.generate_threshold_version()

        return CalibrationProfile(
            profile_id=self.profile_id,
            scope=self.scope,
            threshold_version=version,
            weights=weights,
            anomaly_detector_config=get_anomaly_config_for_environment("staging")
        )

    def _validate_weights(self, weights: Dict[str, float]) -> bool:
        """Validate weight constraints."""
        return validate_weights(weights)

    def compute_weighted_score(
        self,
        scores: Dict[str, float],
        weights: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Compute composite weighted score.

        Formula: weighted_score_i = score_i * weight_i
                 composite_score = sum(weighted_score_i)
        """
        return compute_weighted_score(scores, weights)

    def get_effective_threshold(
        self,
        percentile_threshold: Optional[float],
        fixed_threshold: Optional[float],
        is_risk_side: bool = True
    ) -> Optional[float]:
        """
        Get effective threshold combining percentile and fixed thresholds.

        For risk-side (higher = riskier): use min(percentile, fixed)
        For safe-side (lower = riskier): use max(percentile, fixed)
        """
        return get_effective_threshold(percentile_threshold, fixed_threshold, is_risk_side)

    def run_offline_eval(
        self,
        dataset_path: str,
        threshold_version: str
    ) -> Dict:
        """
        Run offline evaluation on curated dataset.

        Process:
        1. Load dataset from path (JSONL format)
        2. Apply threshold_version to each sample
        3. Run scoring on each sample
        4. Compute precision, recall, F1, AUC metrics
        5. Validate against migration criteria

        Args:
            dataset_path: Path to evaluation dataset (JSONL)
            threshold_version: Threshold version to apply

        Returns:
            Evaluation results with metrics and validation status
        """
        import json
        import os

        # Step 1: Load dataset
        samples = self._load_dataset(dataset_path)
        if not samples:
            logger.warning(f"No samples loaded from {dataset_path}")
            return {
                'status': 'error',
                'error': 'No samples loaded',
                'dataset_path': dataset_path,
                'threshold_version': threshold_version
            }

        # Step 2: Load threshold config
        threshold_config = self._load_threshold_config_for_version(threshold_version)
        weights = threshold_config.get('weights', DEFAULT_SCORER_WEIGHTS)

        # Step 3: Run scoring on each sample
        predictions = []
        labels = []
        scores = []

        for sample in samples:
            # Get ground truth label
            label = sample.get('label', 'unknown')

            # Get scorer results from sample or compute
            sample_scores = sample.get('scorer_results', {})

            # Compute composite score
            composite_score = self.compute_weighted_score(sample_scores, weights)

            # Determine prediction based on thresholds
            prediction = self._predict_from_thresholds(
                composite_score,
                sample_scores,
                threshold_config.get('thresholds', {})
            )

            predictions.append(prediction)
            labels.append(label)
            scores.append(composite_score)

        # Step 4: Compute metrics
        metrics = self.compute_metrics(predictions, labels, scores)

        # Step 5: Validate against migration criteria
        baseline_metrics = self._get_baseline_metrics(threshold_version)
        if baseline_metrics:
            is_valid, violations = self.validate_migration(baseline_metrics, metrics)
        else:
            is_valid = True
            violations = []

        return {
            'status': 'completed',
            'dataset_path': dataset_path,
            'threshold_version': threshold_version,
            'total_samples': len(samples),
            'metrics': metrics,
            'validation': {
                'passed': is_valid,
                'violations': violations
            },
            'prediction_distribution': {
                'block': sum(1 for p in predictions if p == 'block'),
                'pass': sum(1 for p in predictions if p == 'pass')
            },
            'label_distribution': {
                'block': sum(1 for l in labels if l == 'block'),
                'pass': sum(1 for l in labels if l == 'pass')
            },
            'eval_timestamp': datetime.now(timezone.utc).isoformat()
        }

    def _load_dataset(self, dataset_path: str) -> List[Dict]:
        """Load evaluation dataset from JSONL file."""
        return load_dataset(dataset_path)

    def _load_threshold_config_for_version(self, threshold_version: str) -> Dict:
        """Load threshold configuration for specified version."""
        # Default to current configuration
        return {
            'thresholds': DEFAULT_THRESHOLDS,
            'weights': DEFAULT_SCORER_WEIGHTS
        }

    def _predict_from_thresholds(
        self,
        composite_score: float,
        scorer_results: Dict[str, float],
        thresholds: Dict[str, float]
    ) -> str:
        """Predict block/pass based on thresholds."""
        return predict_from_thresholds(composite_score, scorer_results, thresholds)

    def _get_baseline_metrics(self, threshold_version: str) -> Optional[Dict]:
        """Get baseline metrics for comparison."""
        # Would load from historical evaluation results
        return None

    def save_profile(self) -> Dict:
        """
        Save calibration profile to database.

        Returns profile data for storage.
        """
        profile = {
            "profile_id": self.profile_id,
            "scope": self.scope,
            "results": [r.__dict__ for r in self.results],
            "drift_indicators": {k: v.__dict__ for k, v in self.drift_indicators.items()},
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        return profile


# Export all public items for backward compatibility
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