"""
Replay engine - reproducibility verification
"""

import json
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime, timezone

try:
    from src.vector_store import VectorStore, JudgmentKB
    from src.scorers import CompositeScorer
    from src.core.engine import DecisionEngine
except ImportError:
    VectorStore = None
    JudgmentKB = None
    CompositeScorer = None
    DecisionEngine = None

logger = logging.getLogger(__name__)


@dataclass
class ReplayResult:
    original_decision: str
    replay_decision: str
    threshold_version: str
    policy_version: str
    match: bool
    diff_explanation: Optional[str]
    original_scores: Optional[Dict] = None
    replay_scores: Optional[Dict] = None
    original_state_vector: Optional[Dict] = None
    run_id: Optional[str] = None


class ReplayEngine:
    """
    Replay past runs with specific threshold/policy versions
    Requirement: 99% reproducibility
    """

    def __init__(self, vector_store: 'VectorStore' = None, engine: 'DecisionEngine' = None):
        self.vector_store = vector_store
        self.engine = engine
        self.results: List[ReplayResult] = []
        self._historical_configs: Dict[str, Dict] = {}

    def replay_run(
        self,
        run_id: str,
        threshold_version: str,
        policy_version: str = None
    ) -> ReplayResult:
        """
        Replay a historical run with specified versions.

        Process:
        1. Load historical state vector from storage
        2. Load historical threshold/policy config for version
        3. Re-run scorers with historical weights
        4. Compare original vs replay decision
        5. Explain any differences

        Args:
            run_id: Unique identifier of historical run
            threshold_version: Threshold version to replay with
            policy_version: Optional policy version

        Returns:
            ReplayResult with comparison details
        """
        # Step 1: Load historical state vector
        original_state_vector = self._load_state_vector(run_id)
        if not original_state_vector:
            logger.warning(f"No state vector found for run_id={run_id}")
            return ReplayResult(
                original_decision="unknown",
                replay_decision="unknown",
                threshold_version=threshold_version,
                policy_version=policy_version or "default",
                match=False,
                diff_explanation="State vector not found",
                run_id=run_id
            )

        # Step 2: Load threshold config for version
        threshold_config = self._load_threshold_config(threshold_version)
        if not threshold_config:
            logger.warning(f"Threshold config not found for version={threshold_version}")
            threshold_config = self._get_default_thresholds()

        # Step 3: Get original decision
        original_decision = original_state_vector.get('decision', 'unknown')
        original_scores = original_state_vector.get('scorer_results', {})

        # Step 4: Re-run scoring with historical config
        if self.engine:
            # Convert flat weights to nested format for scorers
            flat_weights = threshold_config.get('weights', {})
            nested_weights = {k: {'weight': v} for k, v in flat_weights.items()} if flat_weights else {}

            # Create engine config from historical thresholds
            replay_config = {
                'thresholds': threshold_config.get('thresholds', {}),
                'state_space_gate': {
                    'scorers': nested_weights,
                    'thresholds': threshold_config.get('thresholds', {}),
                    'hard_overrides': threshold_config.get('hard_overrides', {})
                },
                'hard_overrides': threshold_config.get('hard_overrides', {})
            }
            replay_engine = DecisionEngine(replay_config)

            # Re-run evaluation (static_gate_results should be in state_vector)
            replay_result = replay_engine.evaluate(
                state_vector=original_state_vector
            )

            # Extract decision and scores from result
            if isinstance(replay_result, dict):
                replay_decision = replay_result.get('decision', 'unknown')
                scorer_list = replay_result.get('scorer_results', [])
                replay_scores = {r.get('name'): r.get('score') for r in scorer_list} if scorer_list else {}
            else:
                # DecisionResult object
                replay_decision = replay_result.decision
                replay_scores = {r.name: r.score for r in replay_result.scorer_results} if replay_result.scorer_results else {}

        else:
            # Mock replay for testing without engine
            replay_decision = original_decision
            replay_scores = original_scores

        # Step 5: Compare decisions
        match = original_decision == replay_decision

        # Step 6: Explain difference if mismatch
        diff_explanation = None
        if not match:
            diff_explanation = self.explain_difference(
                {'decision': original_decision, 'scores': original_scores, 'thresholds': original_state_vector.get('thresholds', {})},
                {'decision': replay_decision, 'scores': replay_scores, 'thresholds': threshold_config}
            )

        result = ReplayResult(
            original_decision=original_decision,
            replay_decision=replay_decision,
            threshold_version=threshold_version,
            policy_version=policy_version or "default",
            match=match,
            diff_explanation=diff_explanation,
            original_scores=original_scores,
            replay_scores=replay_scores,
            original_state_vector=original_state_vector,
            run_id=run_id
        )

        self.results.append(result)
        return result

    def _load_state_vector(self, run_id: str) -> Optional[Dict]:
        """Load historical state vector from storage."""
        if self.vector_store:
            try:
                return self.vector_store.get_state_vector_by_run_id(run_id)
            except Exception as e:
                logger.error(f"Failed to load state vector for {run_id}: {e}")
                return None

        # Mock for testing without storage
        return {
            'run_id': run_id,
            'decision': 'pass',
            'scorer_results': {
                'constitution_alignment': 0.85,
                'taboo_proximity': 0.12,
                'accept_similarity': 0.75,
                'reject_similarity': 0.20,
                'direction': 0.10,
                'drift': 0.05,
                'anomaly': 0.08,
                'uncertainty': 0.10
            },
            'thresholds': {
                'taboo_block': 0.88,
                'taboo_warn': 0.80
            }
        }

    def _load_threshold_config(self, threshold_version: str) -> Optional[Dict]:
        """Load threshold configuration for specific version."""
        # Check cached configs
        if threshold_version in self._historical_configs:
            return self._historical_configs[threshold_version]

        if self.vector_store:
            try:
                config = self.vector_store.get_threshold_version(threshold_version)
                if config:
                    self._historical_configs[threshold_version] = config
                    return config
            except Exception as e:
                logger.error(f"Failed to load threshold config for {threshold_version}: {e}")

        return None

    def _get_default_thresholds(self) -> Dict:
        """Get default threshold configuration."""
        return {
            'thresholds': {
                'taboo_warn': 0.80,
                'taboo_block': 0.88,
                'reject_warn': 0.75,
                'reject_block': 0.85,
                'anomaly_warn_percentile': 95,
                'anomaly_block_percentile': 99,
                'judge_std_warn': 0.15,
                'judge_std_block': 0.25,
                'tool_failure_warn': 0.10,
                'tool_failure_block': 0.25,
                'direction_block': -0.50
            },
            'weights': {
                'constitution_alignment': 0.20,
                'taboo_proximity': 0.30,
                'accept_similarity': 0.10,
                'reject_similarity': 0.15,
                'direction': 0.05,
                'drift': 0.05,
                'anomaly': 0.10,
                'uncertainty': 0.05
            }
        }

    def verify_reproducibility(self, sample_runs: List[str]) -> float:
        """
        Calculate reproducibility rate from accumulated results.

        Args:
            sample_runs: List of run IDs to calculate rate for

        Returns:
            Match rate as percentage (0.0 to 1.0)
        """
        # Filter results for specified runs
        relevant_results = [r for r in self.results if r.run_id in sample_runs]

        if not relevant_results:
            # Run replay for all sample runs first
            for run_id in sample_runs:
                self.replay_run(run_id, "current")
            relevant_results = [r for r in self.results if r.run_id in sample_runs]

        matches = sum(1 for r in relevant_results if r.match)
        total = len(relevant_results)
        return matches / total if total > 0 else 0.0

    def batch_replay(
        self,
        run_ids: List[str],
        threshold_version: str,
        policy_version: str = None
    ) -> List[ReplayResult]:
        """
        Batch replay for acceptance testing.

        Used for:
        - Threshold migration validation
        - Version upgrade testing
        - Reproducibility audit

        Args:
            run_ids: List of historical run IDs to replay
            threshold_version: Threshold version to apply
            policy_version: Optional policy version

        Returns:
            List of ReplayResults for each run
        """
        results = []
        for run_id in run_ids:
            try:
                result = self.replay_run(run_id, threshold_version, policy_version)
                results.append(result)
            except Exception as e:
                logger.error(f"Replay failed for run_id={run_id}: {e}")
                results.append(ReplayResult(
                    original_decision="error",
                    replay_decision="error",
                    threshold_version=threshold_version,
                    policy_version=policy_version or "default",
                    match=False,
                    diff_explanation=str(e),
                    run_id=run_id
                ))

        # Log summary
        matches = sum(1 for r in results if r.match)
        match_rate = matches / len(results) if results else 0.0
        logger.info(
            f"Batch replay completed: {matches}/{len(results)} matches "
            f"({match_rate*100:.1f}% reproducibility)"
        )

        return results

    def audit_reproducibility(
        self,
        run_ids: List[str],
        min_match_rate: float = 0.99
    ) -> Dict:
        """
        Audit reproducibility and report compliance status.

        Args:
            run_ids: Run IDs to audit
            min_match_rate: Minimum required match rate (default 99%)

        Returns:
            Audit report with pass/fail status and details
        """
        results = self.batch_replay(run_ids, "current")
        match_rate = sum(1 for r in results if r.match) / len(results) if results else 0.0

        failed_runs = [r for r in results if not r.match]

        return {
            'passed': match_rate >= min_match_rate,
            'match_rate': match_rate,
            'required_rate': min_match_rate,
            'total_runs': len(results),
            'matching_runs': sum(1 for r in results if r.match),
            'failed_runs': len(failed_runs),
            'failures': [
                {
                    'run_id': r.run_id,
                    'original': r.original_decision,
                    'replay': r.replay_decision,
                    'explanation': r.diff_explanation
                }
                for r in failed_runs
            ],
            'audit_timestamp': datetime.now(timezone.utc).isoformat()
        }

    def explain_difference(
        self,
        original: Dict,
        replay: Dict
    ) -> str:
        """
        Explain why replay differs from original.

        Analyzes potential causes:
        - Threshold version changed
        - Scorer weights changed
        - Hard override rules changed
        - Embedding model changed
        - Score boundary crossing
        """
        explanations = []

        orig_decision = original.get('decision', 'unknown')
        replay_decision = replay.get('decision', 'unknown')

        # Decision change analysis
        if orig_decision != replay_decision:
            explanations.append(f"Decision changed: {orig_decision} -> {replay_decision}")

        # Score comparison
        orig_scores = original.get('scores', {})
        replay_scores = replay.get('scores', {})

        for scorer in ['taboo_proximity', 'reject_similarity', 'constitution_alignment']:
            orig_val = orig_scores.get(scorer, 0)
            replay_val = replay_scores.get(scorer, 0)
            delta = replay_val - orig_val
            if abs(delta) > 0.01:
                explanations.append(f"{scorer} changed: {orig_val:.3f} -> {replay_val:.3f} (delta={delta:.3f})")

        # Threshold comparison
        orig_thresholds = original.get('thresholds', {})
        replay_thresholds = replay.get('thresholds', {})

        for threshold_name in ['taboo_block', 'taboo_warn', 'reject_block', 'reject_warn']:
            orig_thresh = orig_thresholds.get(threshold_name, 0)
            replay_thresh = replay_thresholds.get(threshold_name, 0)
            if abs(orig_thresh - replay_thresh) > 0.01:
                explanations.append(
                    f"{threshold_name} threshold changed: {orig_thresh:.3f} -> {replay_thresh:.3f}"
                )

        # Boundary crossing detection
        for scorer in ['taboo_proximity', 'reject_similarity']:
            score = replay_scores.get(scorer, 0)
            block_thresh = replay_thresholds.get(f'{scorer.split("_")[0]}_block', 0.85)
            warn_thresh = replay_thresholds.get(f'{scorer.split("_")[0]}_warn', 0.80)
            if score >= block_thresh and orig_scores.get(scorer, 0) < block_thresh:
                explanations.append(f"{scorer} crossed block threshold")
            elif score >= warn_thresh and orig_scores.get(scorer, 0) < warn_thresh:
                explanations.append(f"{scorer} crossed warn threshold")

        return '; '.join(explanations) if explanations else "No significant differences detected"