"""
Engine helper functions.

Utility functions extracted from DecisionEngine for maintainability.
"""

from typing import Dict, List, Optional
from src.core.types import ScoreFactor, ExemplarRef
from src.scorers.base import ScorerResult
from src.core.constants import (
    THRESHOLD_TABOO_BLOCK, THRESHOLD_TABOO_WARN,
    THRESHOLD_REJECT_BLOCK, THRESHOLD_REJECT_WARN,
    THRESHOLD_JUDGE_STD_BLOCK, THRESHOLD_JUDGE_STD_WARN,
)


def compute_centroid(embeddings: List[List[float]]) -> List[float]:
    """
    Compute centroid of embeddings.

    Args:
        embeddings: List of embedding vectors

    Returns:
        Centroid vector
    """
    if not embeddings:
        return []

    n = len(embeddings)
    dims = len(embeddings[0])
    centroid = [sum(e[i] for e in embeddings) / n for i in range(dims)]
    return centroid


def build_score_factors(
    scorer_results: List[ScorerResult],
    n: int = 3
) -> List[ScoreFactor]:
    """
    Build ScoreFactor objects from scorer results.

    Args:
        scorer_results: Individual scorer results
        n: Number of top factors to return

    Returns:
        List of ScoreFactor objects sorted by contribution
    """
    # Sort by weighted_score (contribution) descending
    sorted_results = sorted(
        scorer_results,
        key=lambda r: r.weighted_score,
        reverse=True
    )[:n]

    factors = []
    for r in sorted_results:
        threshold = None
        threshold_type = None

        threshold_map = {
            'taboo_proximity': (THRESHOLD_TABOO_BLOCK, THRESHOLD_TABOO_WARN),
            'reject_similarity': (THRESHOLD_REJECT_BLOCK, THRESHOLD_REJECT_WARN),
            'uncertainty': (THRESHOLD_JUDGE_STD_BLOCK, THRESHOLD_JUDGE_STD_WARN),
        }

        if r.name in threshold_map:
            block_thresh, warn_thresh = threshold_map[r.name]
            if r.score >= block_thresh:
                threshold = block_thresh
                threshold_type = 'block'
            elif r.score >= warn_thresh:
                threshold = warn_thresh
                threshold_type = 'warn'

        factors.append(ScoreFactor(
            name=r.name,
            value=r.score,
            weight=r.weight,
            contribution=r.weighted_score,
            threshold=threshold,
            threshold_type=threshold_type
        ))

    return factors


def build_exemplar_refs(
    scorer_results: List[ScorerResult],
    max_refs: int = 5
) -> List[ExemplarRef]:
    """
    Build ExemplarRef objects from scorer results.

    Args:
        scorer_results: Individual scorer results
        max_refs: Maximum number of refs to return

    Returns:
        List of ExemplarRef objects
    """
    refs = []

    # Collect exemplar refs from all scorers
    for r in scorer_results:
        if hasattr(r, 'top_exemplar_refs') and r.top_exemplar_refs:
            for exemplar in r.top_exemplar_refs:
                # exemplar can be string or dict depending on scorer implementation
                if isinstance(exemplar, dict):
                    refs.append(ExemplarRef(
                        doc_id=exemplar.get('doc_id', ''),
                        axis_type=exemplar.get('axis_type', r.name.replace('_proximity', '').replace('_similarity', '')),
                        similarity=exemplar.get('similarity', 0.0),
                        version=exemplar.get('version'),
                        text_excerpt=exemplar.get('text_excerpt')
                    ))
                elif isinstance(exemplar, str):
                    # Legacy string format - parse basic info
                    refs.append(ExemplarRef(
                        doc_id=exemplar,
                        axis_type=r.name.replace('_proximity', '').replace('_similarity', ''),
                        similarity=0.0
                    ))

    # Sort by similarity descending and limit
    refs = sorted(refs, key=lambda x: x.similarity, reverse=True)[:max_refs]

    return refs


def build_static_gate_summary(state_vector: Dict, gate_summary_rules: List[Dict]) -> Dict:
    """
    Build static_gate_summary using declarative GATE_SUMMARY_RULES.

    Args:
        state_vector: Composite state vector
        gate_summary_rules: Declarative rules for gate summary

    Returns:
        Dict with gates_executed, all_passed, hard_failures, warnings
    """
    rule_violation = state_vector.get('rule_violation', {})
    explicit_results = state_vector.get('static_gate_results') or state_vector.get('rule_results') or {}
    gates_executed = []
    hard_failures = []
    warnings = []

    for gate_name, result in explicit_results.items():
        if gate_name not in gates_executed:
            gates_executed.append(gate_name)
        if not isinstance(result, dict):
            continue
        status = str(result.get('status', '')).lower()
        count = int(result.get('count', 0) or 0)
        severity = str(result.get('severity', '')).lower()
        if status in {'fail', 'failed', 'error', 'deny', 'block'} or severity in {'critical', 'high'} and count > 0:
            hard_failures.append({
                'gate_name': gate_name,
                'severity': severity or 'high',
                'evidence_ref': result.get('evidence_ref', f"{gate_name}://detected"),
                'rule_id': result.get('rule_id', gate_name)
            })
        elif status in {'warn', 'warning'} or count > 0:
            warnings.append({'gate_name': gate_name, 'count': count or 1})

    for rule in gate_summary_rules:
        field = rule['field']
        value = rule_violation.get(field, 0)

        if value > 0:
            if rule['gate'] not in gates_executed:
                gates_executed.append(rule['gate'])

            if rule.get('type') == 'hard':
                failure = {
                    'gate_name': rule['gate'],
                    'severity': rule.get('severity', 'high'),
                    'evidence_ref': f"{rule['gate']}://detected",
                    'rule_id': rule.get('rule_id', field)
                }
                if failure not in hard_failures:
                    hard_failures.append(failure)
            elif rule.get('type') == 'warning':
                warnings.append({'gate_name': rule['gate'], 'count': value})

    return {
        'gates_executed': gates_executed,
        'all_passed': len(hard_failures) == 0,
        'hard_failures': hard_failures,
        'warnings': warnings
    }