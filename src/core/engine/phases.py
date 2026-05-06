"""
Decision Engine Scoring Phases

Extracted scoring execution and state determination logic from DecisionEngine.
"""

from typing import Dict, List, Tuple, Any
from dataclasses import dataclass

from src.scorers import (
    ConstitutionAlignmentScorer,
    TabooProximityScorer,
    AcceptSimilarityScorer,
    RejectSimilarityScorer,
    DirectionScorer,
    DriftScorer,
    AnomalyScorer,
    UncertaintyScorer,
    ScorerResult,
)
from src.core.types import GateState
from src.core.constants import (
    THRESHOLD_TABOO_WARN, THRESHOLD_TABOO_BLOCK,
    THRESHOLD_REJECT_WARN, THRESHOLD_REJECT_BLOCK,
    THRESHOLD_JUDGE_STD_WARN, THRESHOLD_JUDGE_STD_BLOCK,
    THRESHOLD_TOOL_FAILURE_WARN, THRESHOLD_TOOL_FAILURE_BLOCK,
    THRESHOLD_DIRECTION_BLOCK, THRESHOLD_DIRECTION_WARN,
    THRESHOLD_ANOMALY_BLOCK, THRESHOLD_ANOMALY_WARN, THRESHOLD_ANOMALY_SELF_CORRECT,
    THRESHOLD_COMPOSITE_WARN,
)
from src.core.hard_overrides import check_hard_override_ho02
from .helpers import compute_centroid


# State determination rules (declarative - uses constants)
STATE_RULES = {
    'block': [
        {'scorer': 'taboo_proximity', 'threshold': THRESHOLD_TABOO_BLOCK, 'action': 'process_correction'},
        {'scorer': 'reject_similarity', 'threshold': THRESHOLD_REJECT_BLOCK, 'action': 'artifact_correction'},
        {'scorer': 'anomaly', 'threshold': THRESHOLD_ANOMALY_BLOCK, 'action': 'process_correction'},
        {'field': 'tool_error_rate', 'threshold': THRESHOLD_TOOL_FAILURE_BLOCK, 'action': 'process_correction'},
    ],
    'hold': [
        {'scorer': 'taboo_proximity', 'threshold': THRESHOLD_TABOO_WARN, 'action': 'human_review'},
        {'scorer': 'reject_similarity', 'threshold': THRESHOLD_REJECT_WARN, 'action': 'human_review'},
        {'scorer': 'anomaly', 'threshold': THRESHOLD_ANOMALY_WARN, 'action': 'human_review'},
        {'scorer': 'uncertainty', 'threshold': THRESHOLD_JUDGE_STD_BLOCK, 'action': 'human_review'},
        {'scorer': 'direction', 'threshold': THRESHOLD_DIRECTION_BLOCK, 'action': 'human_review', 'op': 'le'},
        {'field': 'tool_error_rate', 'threshold': THRESHOLD_TOOL_FAILURE_WARN, 'action': 'human_review'},
    ],
    'warn': [
        {'composite': True, 'threshold': THRESHOLD_COMPOSITE_WARN, 'action': 'self_correction'},
        {'scorer': 'anomaly', 'threshold': THRESHOLD_ANOMALY_SELF_CORRECT, 'action': 'self_correction'},
        {'scorer': 'uncertainty', 'threshold': THRESHOLD_JUDGE_STD_WARN, 'action': 'self_correction'},
        {'scorer': 'direction', 'threshold': THRESHOLD_DIRECTION_WARN, 'action': 'self_correction', 'op': 'lt'},
    ],
}


def run_all_scorers(
    scorers: Dict[str, Any],
    state_vector: Dict,
    kb_embeddings: Dict,
    historical_baseline: Dict
) -> List[ScorerResult]:
    """
    Execute all scorers and collect results.

    Args:
        scorers: Dict of scorer instances
        state_vector: Composite state vector
        kb_embeddings: Knowledge base embeddings
        historical_baseline: Historical baseline data

    Returns:
        List of ScorerResult objects
    """
    results = []

    # Extract semantic vector
    semantic = state_vector.get('semantic', {})
    semantic_vector = semantic.get('vector', [])

    # Prepare KB data
    if kb_embeddings:
        constitution_embeddings = kb_embeddings.get('constitution', [])
        taboo_embeddings = kb_embeddings.get('taboo', [])
        accepted_embeddings = kb_embeddings.get('accepted', [])
        rejected_embeddings = kb_embeddings.get('rejected', [])
        constitution_docs = kb_embeddings.get('constitution_docs', [])
        taboo_docs = kb_embeddings.get('taboo_docs', [])
        accepted_docs = kb_embeddings.get('accepted_docs', [])
        rejected_docs = kb_embeddings.get('rejected_docs', [])
    else:
        constitution_embeddings = taboo_embeddings = accepted_embeddings = rejected_embeddings = []
        constitution_docs = taboo_docs = accepted_docs = rejected_docs = []

    # Constitution alignment
    if constitution_embeddings:
        centroid = compute_centroid(constitution_embeddings)
        results.append(
            scorers['constitution_alignment'].score(
                semantic_vector, centroid, constitution_docs
            )
        )
    else:
        results.append(ScorerResult(
            name="constitution_alignment",
            score=0.5,
            weight=scorers['constitution_alignment'].weight,
            weighted_score=0.5 * scorers['constitution_alignment'].weight,
            top_exemplar_refs=[],
            explanation="No constitution embeddings available"
        ))

    # Taboo proximity
    results.append(
        scorers['taboo_proximity'].score(
            semantic_vector, taboo_embeddings, taboo_docs
        )
    )

    # Accept similarity
    results.append(
        scorers['accept_similarity'].score(
            semantic_vector, accepted_embeddings, accepted_docs
        )
    )

    # Reject similarity
    results.append(
        scorers['reject_similarity'].score(
            semantic_vector, rejected_embeddings, rejected_docs
        )
    )

    # Direction score: cosine(delta_semantic, accepted_centroid - rejected_centroid)
    trajectory = state_vector.get('trajectory', {})
    delta_semantic = trajectory.get('delta_semantic_vector', [])
    if delta_semantic and accepted_embeddings and rejected_embeddings:
        accepted_centroid = compute_centroid(accepted_embeddings)
        rejected_centroid = compute_centroid(rejected_embeddings)
        results.append(
            scorers['direction'].score(
                delta_semantic, accepted_centroid, rejected_centroid
            )
        )
    else:
        results.append(ScorerResult(
            name="direction",
            score=0.0,
            weight=scorers['direction'].weight,
            weighted_score=0.0,
            top_exemplar_refs=[],
            explanation="No delta_semantic_vector available for direction scoring"
        ))

    # Drift
    ewma = None
    historical_vectors = None
    if historical_baseline:
        ewma = historical_baseline.get('ewma_accepted')
        historical_vectors = historical_baseline.get('accepted_vectors')
    results.append(
        scorers['drift'].score(
            semantic_vector, ewma, historical_vectors
        )
    )

    # Anomaly
    trajectory = state_vector.get('trajectory', {})
    feature_mean = historical_baseline.get('feature_mean') if historical_baseline else None
    feature_cov_inv = historical_baseline.get('feature_cov_inv') if historical_baseline else None
    results.append(
        scorers['anomaly'].score(
            trajectory, feature_mean, feature_cov_inv
        )
    )

    # Uncertainty
    uncertainty = state_vector.get('uncertainty', {})
    results.append(
        scorers['uncertainty'].score(
            judge_std=uncertainty.get('judge_std', 0),
            self_confidence=uncertainty.get('self_confidence', 0),
            tool_error_rate=uncertainty.get('tool_error_rate', 0),
            evidence_gap=uncertainty.get('evidence_gap', 0)
        )
    )

    return results


def determine_gate_state(
    composite_score: float,
    scorer_results: List[ScorerResult],
    state_vector: Dict,
    thresholds: Dict,
    hard_overrides_config: Dict,
    threshold_version: str,
    policy_version: str,
    GateState_cls: Any,
    DecisionResult_cls: Any
) -> Tuple[GateState, str]:
    """
    Determine gate state based on composite score and thresholds.
    Uses declarative STATE_RULES for maintainability.
    """
    uncertainty = state_vector.get('uncertainty', {})
    tool_error_rate = uncertainty.get('tool_error_rate', 0.0)

    # Extract scorer scores into dict
    scores = {r.name: r.score for r in scorer_results}
    taboo_score = scores.get('taboo_proximity', 0.0)

    # Check HO02 after scorers (requires taboo_score)
    ho02_result = check_hard_override_ho02(
        state_vector=state_vector,
        thresholds=thresholds,
        hard_overrides_config=hard_overrides_config,
        threshold_version=threshold_version,
        policy_version=policy_version,
        gate_state_cls=GateState_cls,
        decision_result_cls=DecisionResult_cls,
        taboo_score=taboo_score
    )
    if ho02_result:
        return GateState_cls.BLOCK, "process_correction"

    # Apply declarative rules
    for state_name, rules in STATE_RULES.items():
        for rule in rules:
            if matches_rule(rule, scores, composite_score, tool_error_rate, thresholds):
                gate_state = GateState_cls[state_name.upper()]
                return gate_state, rule['action']

    return GateState_cls.PASS, "continue"


def matches_rule(
    rule: Dict,
    scores: Dict,
    composite: float,
    tool_error: float,
    thresholds: Dict
) -> bool:
    """Check if a single rule matches."""
    threshold = rule['threshold']
    op = rule.get('op', 'ge')

    # Get threshold value from config if string key
    if isinstance(threshold, str):
        threshold = thresholds.get(threshold, 0.0)

    # Check composite score rule
    if rule.get('composite'):
        return composite >= threshold

    # Check field-based rule
    if rule.get('field') == 'tool_error_rate':
        return tool_error >= threshold

    # Check scorer-based rule
    scorer_name = rule.get('scorer')
    if scorer_name:
        score = scores.get(scorer_name, 0.0)
        if op == 'le':
            return score <= threshold
        elif op == 'lt':
            return score < threshold
        return score >= threshold

    return False


__all__ = [
    "STATE_RULES",
    "run_all_scorers",
    "determine_gate_state",
    "matches_rule",
]