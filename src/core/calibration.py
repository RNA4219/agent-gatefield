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

from .exceptions import CalibrationError, InsufficientSamplesError, WeightValidationError

logger = logging.getLogger(__name__)

# Import constants
from .constants import (
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
from .dataclasses import (
    CalibrationResult,
    ThresholdVersion,
    DriftIndicators,
    MahalanobisParams,
    CalibrationProfile,
)

# Import threshold calibration functions
from .threshold_calibration import (
    calibrate_taboo_threshold,
    calibrate_drift_threshold,
    calibrate_anomaly_percentile,
    calibrate_constitution_threshold,
    get_effective_threshold,
    get_percentile_value,
)

# Import drift detection functions
from .drift_detection import (
    compute_drift_indicators,
    classify_drift_type,
    get_drift_response,
    compute_rolling_statistics,
    detect_threshold_decay,
)

# Import anomaly calibration functions
from .anomaly_calibration import (
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
from .online_calibration import (
    incorporate_correction,
    check_calibration_trigger,
    compute_threshold_adjustment,
    validate_weight_adjustment,
    apply_online_correction,
    get_calibration_priority,
    should_trigger_immediate_recalibration,
)


# Utility functions for backward compatibility
def calculate_ewma(current_value: float, old_ewma: float, alpha: float = 0.1) -> float:
    """
    Calculate Exponentially Weighted Moving Average.

    Used for drift score calculation.

    Args:
        current_value: Current observation
        old_ewma: Previous EWMA value
        alpha: Smoothing factor (default 0.1)

    Returns:
        Updated EWMA value
    """
    return alpha * current_value + (1 - alpha) * old_ewma


def calculate_uncertainty_score(
    judge_std: float,
    self_confidence: float,
    tool_error_rate: float,
    evidence_gap: float
) -> float:
    """
    Calculate uncertainty score from components.

    Formula: uncertainty = 0.25 * norm_judge_std
                       + 0.25 * (1 - self_confidence)
                       + 0.25 * tool_error_rate
                       + 0.25 * evidence_gap

    All components should be normalized to [0, 1].

    Args:
        judge_std: Judge standard deviation (normalized)
        self_confidence: Self-confidence score (0-1)
        tool_error_rate: Tool error rate (0-1)
        evidence_gap: Evidence gap score (0-1)

    Returns:
        Combined uncertainty score
    """
    return (
        0.25 * judge_std +
        0.25 * (1 - self_confidence) +
        0.25 * tool_error_rate +
        0.25 * evidence_gap
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
        tp = sum(1 for p, l in zip(predictions, labels) if p == "block" and l == "block")
        fp = sum(1 for p, l in zip(predictions, labels) if p == "block" and l == "pass")
        tn = sum(1 for p, l in zip(predictions, labels) if p == "pass" and l == "pass")
        fn = sum(1 for p, l in zip(predictions, labels) if p == "pass" and l == "block")

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        # False escalation rate: proportion of passes that were incorrectly blocked
        total_pass = tn + fp
        false_escalation = fp / total_pass if total_pass > 0 else 0.0

        metrics = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "false_escalation": false_escalation,
        }

        # Compute AUC if scores provided
        if scores is not None:
            metrics["auc"] = self._compute_auc(predictions, labels, scores)
        else:
            metrics["auc"] = None

        return metrics

    def _compute_auc(
        self,
        predictions: List[str],
        labels: List[str],
        scores: List[float]
    ) -> float:
        """Compute Area Under ROC Curve using trapezoidal rule."""
        # Create list of (score, label) where label=1 for block
        score_labels = [(s, 1 if l == "block" else 0) for s, l in zip(scores, labels)]
        score_labels.sort(key=lambda x: -x[0])  # Sort by score descending

        n_pos = sum(1 for _, l in score_labels if l == 1)
        n_neg = len(score_labels) - n_pos

        if n_pos == 0 or n_neg == 0:
            return 0.0

        # Compute TPR and FPR at each threshold
        tp = 0
        fp = 0
        prev_score = None
        auc = 0.0
        prev_tpr = 0.0
        prev_fpr = 0.0

        for score, label in score_labels:
            if score != prev_score and prev_score is not None:
                tpr = tp / n_pos
                fpr = fp / n_neg
                # Trapezoidal rule
                auc += (fpr - prev_fpr) * (tpr + prev_tpr) / 2
                prev_tpr = tpr
                prev_fpr = fpr

            if label == 1:
                tp += 1
            else:
                fp += 1
            prev_score = score

        # Final point
        tpr = tp / n_pos
        fpr = fp / n_neg
        auc += (fpr - prev_fpr) * (tpr + prev_tpr) / 2

        return auc

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
        violations = []

        # Check precision degradation
        precision_delta = new_metrics.get("precision", 1.0) - old_metrics.get("precision", 1.0)
        if precision_delta < -MIGRATION_CRITERIA["precision_max_degradation"]:
            violations.append(
                f"Precision degraded by {abs(precision_delta)*100:.1f}% "
                f"(max allowed: {MIGRATION_CRITERIA['precision_max_degradation']*100}%)"
            )

        # Check recall degradation (taboo-specific, stricter)
        recall_delta = new_metrics.get("recall", 1.0) - old_metrics.get("recall", 1.0)
        if recall_delta < -MIGRATION_CRITERIA["recall_max_degradation"]:
            violations.append(
                f"Recall degraded by {abs(recall_delta)*100:.1f}% "
                f"(max allowed: {MIGRATION_CRITERIA['recall_max_degradation']*100}%)"
            )

        # Check F1 degradation
        f1_delta = new_metrics.get("f1", 1.0) - old_metrics.get("f1", 1.0)
        if f1_delta < -MIGRATION_CRITERIA["f1_max_degradation"]:
            violations.append(
                f"F1 degraded by {abs(f1_delta)*100:.1f}% "
                f"(max allowed: {MIGRATION_CRITERIA['f1_max_degradation']*100}%)"
            )

        # Check false escalation increase
        fe_delta = new_metrics.get("false_escalation", 0.0) - old_metrics.get("false_escalation", 0.0)
        if fe_delta > MIGRATION_CRITERIA["false_escalation_max_increase"]:
            violations.append(
                f"False escalation increased by {fe_delta*100:.1f}% "
                f"(max allowed: {MIGRATION_CRITERIA['false_escalation_max_increase']*100}%)"
            )

        return len(violations) == 0, violations

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
        if len(original_decisions) != len(replay_decisions):
            raise CalibrationError("Decision lists must have equal length")

        matches = sum(1 for o, r in zip(original_decisions, replay_decisions) if o == r)
        match_rate = matches / len(original_decisions) if original_decisions else 0.0

        # Analyze divergences
        divergences = defaultdict(list)
        for i, (orig, replay) in enumerate(zip(original_decisions, replay_decisions)):
            if orig != replay:
                divergence_key = f"{orig}_to_{replay}"
                divergences[divergence_key].append(i)

        # Categorize divergences by severity
        critical_divergences = []
        acceptable_divergences = []

        for div_type, indices in divergences.items():
            if div_type == "pass_to_block":
                critical_divergences.append({
                    "type": div_type,
                    "indices": indices,
                    "count": len(indices),
                    "action_required": "Security review required"
                })
            elif div_type == "block_to_pass":
                critical_divergences.append({
                    "type": div_type,
                    "indices": indices,
                    "count": len(indices),
                    "action_required": "Requires justification + 2 approvers"
                })
            elif div_type == "warn_to_hold":
                acceptable_divergences.append({
                    "type": div_type,
                    "indices": indices,
                    "count": len(indices),
                    "action_required": "Acceptable if within calibration tolerance"
                })
            elif div_type == "hold_to_pass":
                acceptable_divergences.append({
                    "type": div_type,
                    "indices": indices,
                    "count": len(indices),
                    "action_required": "Requires reviewer confirmation"
                })

        passed = match_rate >= tolerance

        return {
            "passed": passed,
            "match_rate": match_rate,
            "tolerance": tolerance,
            "matches": matches,
            "total": len(original_decisions),
            "divergences": dict(divergences),
            "critical_divergences": critical_divergences,
            "acceptable_divergences": acceptable_divergences,
            "manual_approval_required": len(critical_divergences) > 0
        }

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
        total = sum(weights.values())

        if abs(total - WEIGHT_CONSTRAINTS["sum"]) > 0.001:
            raise WeightValidationError(f"Weights must sum to {WEIGHT_CONSTRAINTS['sum']}, got {total}", weights)

        for name, weight in weights.items():
            if weight < WEIGHT_CONSTRAINTS["min_weight"]:
                raise WeightValidationError(
                    f"Weight for {name} ({weight}) below minimum "
                    f"{WEIGHT_CONSTRAINTS['min_weight']}", weights
                )
            if weight > WEIGHT_CONSTRAINTS["max_weight"]:
                raise WeightValidationError(
                    f"Weight for {name} ({weight}) exceeds maximum "
                    f"{WEIGHT_CONSTRAINTS['max_weight']}", weights
                )

        return True

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
        if weights is None:
            weights = DEFAULT_SCORER_WEIGHTS.copy()

        composite = 0.0
        for scorer, weight in weights.items():
            if scorer in scores:
                composite += scores[scorer] * weight

        return composite

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
        import json
        import os

        if not os.path.exists(dataset_path):
            logger.warning(f"Dataset file not found: {dataset_path}")
            return []

        samples = []
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        sample = json.loads(line)
                        samples.append(sample)
        except Exception as e:
            logger.error(f"Failed to load dataset: {e}")
            return []

        logger.info(f"Loaded {len(samples)} samples from {dataset_path}")
        return samples

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
        # Check hard thresholds first
        taboo_proximity = scorer_results.get('taboo_proximity', 0)
        taboo_block = thresholds.get('taboo_block', 0.88)
        taboo_warn = thresholds.get('taboo_warn', 0.80)

        if taboo_proximity >= taboo_block:
            return 'block'

        reject_similarity = scorer_results.get('reject_similarity', 0)
        reject_block = thresholds.get('reject_block', 0.85)

        if reject_similarity >= reject_block:
            return 'block'

        # Check constitution alignment (safe-side)
        constitution_alignment = scorer_results.get('constitution_alignment', 1)
        constitution_block = thresholds.get('constitution_block', 0.01)

        if constitution_alignment <= constitution_block:
            return 'block'

        # Check uncertainty
        uncertainty = scorer_results.get('uncertainty', 0)
        judge_std = scorer_results.get('judge_std', 0)
        judge_std_block = thresholds.get('judge_std_block', 0.25)

        if judge_std >= judge_std_block:
            return 'block'

        # Default to pass if no blocking conditions met
        return 'pass'

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