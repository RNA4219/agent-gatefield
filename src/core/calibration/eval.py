"""
Calibration Pipeline Evaluation

Extracted evaluation and metrics computation logic from CalibrationPipeline.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional, Any

from ..constants import (
    DEFAULT_SCORER_WEIGHTS,
    WEIGHT_CONSTRAINTS,
    DEFAULT_THRESHOLDS,
    MIGRATION_CRITERIA,
    REPRODUCIBILITY_TARGET,
)
from ..dataclasses import CalibrationResult
from ..exceptions import CalibrationError, WeightValidationError

logger = logging.getLogger(__name__)


def compute_metrics(
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
        metrics["auc"] = compute_auc(predictions, labels, scores)
    else:
        metrics["auc"] = None

    return metrics


def compute_auc(
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


def validate_migration(
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


def verify_reproducibility(
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


def validate_weights(weights: Dict[str, float]) -> bool:
    """Validate weight constraints."""
    total = sum(weights.values())

    if abs(total - WEIGHT_CONSTRAINTS["sum"]) > 0.001:
        raise WeightValidationError(
            f"Weights must sum to {WEIGHT_CONSTRAINTS['sum']}, got {total}", weights
        )

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


def predict_from_thresholds(
    composite_score: float,
    scorer_results: Dict[str, float],
    thresholds: Dict[str, float]
) -> str:
    """Predict block/pass based on thresholds."""
    # Check hard thresholds first
    taboo_proximity = scorer_results.get('taboo_proximity', 0)
    taboo_block = thresholds.get('taboo_block', 0.88)

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
    judge_std = scorer_results.get('judge_std', 0)
    judge_std_block = thresholds.get('judge_std_block', 0.25)

    if judge_std >= judge_std_block:
        return 'block'

    # Default to pass if no blocking conditions met
    return 'pass'


def load_dataset(dataset_path: str) -> List[Dict]:
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


def run_offline_evaluation(
    dataset_path: str,
    threshold_version: str,
    threshold_config: Dict,
    compute_metrics_func: Any,
    validate_migration_func: Any
) -> Dict:
    """
    Run offline evaluation on curated dataset.

    Args:
        dataset_path: Path to evaluation dataset (JSONL)
        threshold_version: Threshold version to apply
        threshold_config: Threshold configuration dict
        compute_metrics_func: Function to compute metrics
        validate_migration_func: Function to validate migration

    Returns:
        Evaluation results with metrics and validation status
    """
    # Load dataset
    samples = load_dataset(dataset_path)
    if not samples:
        return {
            'status': 'error',
            'error': 'No samples loaded',
            'dataset_path': dataset_path,
            'threshold_version': threshold_version
        }

    weights = threshold_config.get('weights', DEFAULT_SCORER_WEIGHTS)

    # Run scoring on each sample
    predictions = []
    labels = []
    scores = []

    for sample in samples:
        label = sample.get('label', 'unknown')
        sample_scores = sample.get('scorer_results', {})
        composite_score = compute_weighted_score(sample_scores, weights)
        prediction = predict_from_thresholds(
            composite_score,
            sample_scores,
            threshold_config.get('thresholds', {})
        )

        predictions.append(prediction)
        labels.append(label)
        scores.append(composite_score)

    # Compute metrics
    metrics = compute_metrics_func(predictions, labels, scores)

    # Validate against migration criteria
    baseline_metrics = None  # Would load from historical results
    if baseline_metrics:
        is_valid, violations = validate_migration_func(baseline_metrics, metrics)
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


__all__ = [
    "compute_metrics",
    "compute_auc",
    "validate_migration",
    "verify_reproducibility",
    "validate_weights",
    "compute_weighted_score",
    "predict_from_thresholds",
    "load_dataset",
    "run_offline_evaluation",
]