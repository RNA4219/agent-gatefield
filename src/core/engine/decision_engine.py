"""
Core Engine - Composite Decision Engine

This is the main entry point for gate decisions. It coordinates:
- Hard override rules (immediate block/hold conditions)
- Scorer execution and composite score calculation
- State determination based on thresholds
- SLA handling, threshold versioning, and self-correction tracking

Note: Helper functions moved to engine/helpers.py for maintainability.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import uuid

from src.scorers import (
    ConstitutionAlignmentScorer,
    TabooProximityScorer,
    AcceptSimilarityScorer,
    RejectSimilarityScorer,
    DirectionScorer,
    DriftScorer,
    AnomalyScorer,
    UncertaintyScorer,
    CompositeScorer,
    ScorerResult,
    create_scorers_from_config
)
from src.core.distance import cosine_similarity
from src.core.types import ScoreFactor, ExemplarRef, GateState, DecisionResult
from src.core.constants import (
    THRESHOLD_TABOO_WARN, THRESHOLD_TABOO_BLOCK,
    THRESHOLD_REJECT_WARN, THRESHOLD_REJECT_BLOCK,
    THRESHOLD_JUDGE_STD_WARN, THRESHOLD_JUDGE_STD_BLOCK,
    THRESHOLD_TOOL_FAILURE_WARN, THRESHOLD_TOOL_FAILURE_BLOCK,
    THRESHOLD_DIRECTION_BLOCK, THRESHOLD_DIRECTION_WARN,
    THRESHOLD_ANOMALY_BLOCK, THRESHOLD_ANOMALY_WARN, THRESHOLD_ANOMALY_SELF_CORRECT,
    THRESHOLD_COMPOSITE_WARN,
)
from .helpers import (
    compute_centroid,
    build_score_factors,
    build_exemplar_refs,
    build_static_gate_summary,
)

# Import split modules
from src.core.audit import (
    audit_logger,
    log_state_transition,
    log_hard_override,
    log_late_hard_fail,
    log_checkpoint_rollback
)
from src.core.hard_overrides import (
    apply_hard_overrides,
    check_hard_override_ho02,
    HO01_SECRET_FOUND,
    HO02_PROD_WRITE_TABOO_WARN,
    HO03_HIGH_PRIVILEGE_UNCERTAIN,
    HO04_SAST_HIGH,
    HO05_TOOL_POLICY_DENY
)
from src.core.sla_handler import (
    SLAHandler,
    calculate_sla_deadlines,
    check_sla_timeout,
    handle_sla_timeout
)
from src.core.threshold_versioning import (
    ThresholdVersionManager,
    ThresholdReplayContext,
    replay_with_version
)
from src.core.self_correction import (
    SelfCorrectionTracker,
    track_self_correction,
    check_persistent_factor_escalation
)


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


# Gate summary rules (declarative)
GATE_SUMMARY_RULES = [
    {'field': 'secret', 'gate': 'secret_scan', 'severity': 'critical', 'rule_id': 'secret_detection', 'type': 'hard'},
    {'field': 'secret_scan', 'gate': 'secret_scan', 'severity': 'critical', 'rule_id': 'secret_detection', 'type': 'hard'},
    {'field': 'sast_high', 'gate': 'sast', 'severity': 'high', 'rule_id': 'sast_high', 'type': 'hard'},
    {'field': 'sast_medium', 'gate': 'sast', 'type': 'warning'},
    {'field': 'lint_error', 'gate': 'lint', 'severity': 'high', 'rule_id': 'lint_error', 'type': 'hard'},
    {'field': 'lint_warning', 'gate': 'lint', 'type': 'warning'},
    {'field': 'type_error', 'gate': 'typecheck', 'severity': 'high', 'rule_id': 'type_error', 'type': 'hard'},
    {'field': 'license_forbidden', 'gate': 'license_scan', 'severity': 'high', 'rule_id': 'license_forbidden', 'type': 'hard'},
    {'field': 'license_unknown', 'gate': 'license_scan', 'type': 'warning'},
    {'field': 'tool_policy_deny', 'gate': 'tool_policy', 'severity': 'critical', 'rule_id': 'tool_policy_deny', 'type': 'hard'},
]


class DecisionEngine:
    """
    State space gate decision engine.

    Coordinates evaluation of state vectors through:
    1. Hard override rule checks (immediate block/hold)
    2. Scorer execution (constitution, taboo, similarity, etc.)
    3. Composite score calculation
    4. Threshold-based state determination
    """

    # Default limits
    MAX_SELF_CORRECTION_LOOPS = 2
    PERSISTENT_FACTOR_THRESHOLD = 3

    def __init__(self, config: Dict):
        """
        Initialize the decision engine.

        Args:
            config: Configuration dict containing thresholds, scorers, etc.
        """
        self.config = config
        self.thresholds = config.get('thresholds', {})
        self.hard_overrides = config.get('hard_overrides', {})

        # Initialize threshold version manager
        initial_version = config.get('threshold_version', 'v1')
        self._threshold_version_manager = ThresholdVersionManager(initial_version)
        self._threshold_version_manager.lock_version(
            initial_version,
            self.thresholds,
            self.hard_overrides
        )

        # Initialize scorers from config
        scorer_config = config.get('state_space_gate', {}).get('scorers', {})
        self.scorers = create_scorers_from_config(scorer_config)
        self.composite_scorer = CompositeScorer(scorer_config)

        # Initialize SLA handler
        self._sla_handler = SLAHandler()

        # Initialize self-correction tracker
        max_loops = config.get('actions', {}).get(
            'max_self_correction_loops',
            self.MAX_SELF_CORRECTION_LOOPS
        )
        persistent_threshold = config.get('actions', {}).get(
            'persistent_factor_threshold',
            self.PERSISTENT_FACTOR_THRESHOLD
        )
        self._self_correction_tracker = SelfCorrectionTracker(
            max_loops=max_loops,
            persistent_threshold=persistent_threshold
        )

    # Backward-compatible properties for tests
    @property
    def max_correction_loops(self) -> int:
        """Maximum self-correction loops before escalation."""
        return self._self_correction_tracker.max_loops

    @property
    def persistent_factor_threshold(self) -> int:
        """Threshold for persistent factor escalation."""
        return self._self_correction_tracker.persistent_threshold

    def evaluate(
        self,
        state_vector: Dict,
        kb_embeddings: Dict = None,
        historical_baseline: Dict = None
    ) -> Dict:
        """
        Evaluate state vector and return gate decision.

        Per API_SPEC.md section 2.1, the canonical signature is:
            evaluate(state_vector: dict) -> dict

        The state_vector should contain all needed data per the StateEncoder
        output format. Optional parameters are provided for backward compatibility
        with existing tests and for explicit KB override scenarios.

        Args:
            state_vector: Composite state vector (semantic, rule_violation, risk,
                          uncertainty, trajectory, etc.) per StateEncoder.encode()
                          output schema. May also include kb_embeddings and
                          historical_baseline embedded within.
            kb_embeddings: (Optional) Judgment KB embeddings for override/explicit
                           passing. If None, extracted from state_vector if present.
                           Backward compat parameter - prefer embedding in state_vector.
            historical_baseline: (Optional) Historical baseline for drift/anomaly.
                                 If None, extracted from state_vector if present.
                                 Backward compat parameter.

        Returns:
            Dict: Gate decision result with fields per API_SPEC.md evaluate() return:
                - decision: "pass"|"warn"|"hold"|"block"
                - composite_score: float (0.0-1.0)
                - factors: list of {name, value, weight, contribution}
                - exemplar_refs: list of {doc_id, axis_type, similarity}
                - action: dict with action_type
                - threshold_version: str
                - static_gate_summary: dict

        Note:
            The returned object is a DecisionResult dataclass which provides
            a .to_dict() method for explicit dict conversion. Tests may access
            attributes directly (e.g., result.decision) while API consumers
            should use dict access (e.g., result['decision'] or result.to_dict()).
        """
        threshold_version = self._threshold_version_manager.current_version
        policy_version = self.config.get('policy_version', 'v1')

        # Step 1: Check hard overrides first (immediate block)
        # Note: HO02 (prod_write + taboo_warn) is evaluated after scorers
        hard_override_result = apply_hard_overrides(
            state_vector=state_vector,
            thresholds=self.thresholds,
            hard_overrides_config=self.hard_overrides,
            threshold_version=threshold_version,
            policy_version=policy_version,
            gate_state_cls=GateState,
            decision_result_cls=DecisionResult
        )
        if hard_override_result:
            hard_override_result.decision_id = state_vector.get('decision_id') or str(uuid.uuid4())
            hard_override_result.run_id = state_vector.get('run_id', '')
            hard_override_result.trace_id = state_vector.get('trace_id')
            return hard_override_result

        # Step 2: Run all scorers
        scorer_results = self._run_scorers(state_vector, kb_embeddings, historical_baseline)

        # Step 3: Compute composite score
        composite_score = self.composite_scorer.compute_composite(scorer_results)

        # Step 4: Determine state based on thresholds
        decision_state, action_type = self._determine_state(
            composite_score, scorer_results, state_vector, threshold_version, policy_version
        )
        # Convert GateState enum to string per spec
        decision = decision_state.value

        # Step 5: Collect top factors as ScoreFactor objects
        factors = build_score_factors(scorer_results, n=3)

        # Step 6: Collect exemplar refs as ExemplarRef objects
        exemplar_refs = build_exemplar_refs(scorer_results, max_refs=5)

        # Step 7: Build static_gate_summary from state_vector
        static_gate_summary = build_static_gate_summary(state_vector, GATE_SUMMARY_RULES)

        # Step 8: Build action recommendation dict
        action = {
            "action_type": action_type,
            "checkpoint_ref": None  # Set later if hold
        }

        # Step 9: Extract artifact identity and state_vector_ref from state_vector
        artifact_id = state_vector.get('artifact_id', '')
        artifact_ref = state_vector.get('artifact_ref')
        diff_hash = state_vector.get('diff_hash', '')
        if artifact_ref and not isinstance(artifact_ref, dict):
            artifact_ref = {
                'uri': artifact_ref,
                'diff_hash': diff_hash,
            }
        run_id = state_vector.get('run_id', '')
        trace_id = state_vector.get('trace_id')
        state_vector_ref = f"state://{state_vector.get('run_id', '')}" if state_vector.get('run_id') else ''

        # Step 10: Create result with all spec-compliant fields
        result = DecisionResult(
            decision=decision,
            composite_score=composite_score,
            artifact_id=artifact_id,
            artifact_ref=artifact_ref,
            diff_hash=diff_hash,
            policy_version=policy_version,
            factors=factors,
            exemplar_refs=exemplar_refs,
            action=action,
            threshold_version=threshold_version,
            static_gate_summary=static_gate_summary,
            state_vector_ref=state_vector_ref,
            scorer_results=scorer_results,
            created_at=datetime.now(timezone.utc),
            decision_id=state_vector.get('decision_id') or str(uuid.uuid4()),
            run_id=run_id,
            trace_id=trace_id
        )

        # Step 11: Log state transition for audit (STATE_TRANSITION_SPEC 11)
        log_state_transition(result, previous_state=None, audit_logger=audit_logger)

        return result

    def _run_scorers(
        self,
        state_vector: Dict,
        kb_embeddings: Dict,
        historical_baseline: Dict
    ) -> List[ScorerResult]:
        """
        Execute all scorers and collect results.

        Args:
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
                self.scorers['constitution_alignment'].score(
                    semantic_vector, centroid, constitution_docs
                )
            )
        else:
            results.append(ScorerResult(
                name="constitution_alignment",
                score=0.5,
                weight=self.scorers['constitution_alignment'].weight,
                weighted_score=0.5 * self.scorers['constitution_alignment'].weight,
                top_exemplar_refs=[],
                explanation="No constitution embeddings available"
            ))

        # Taboo proximity
        results.append(
            self.scorers['taboo_proximity'].score(
                semantic_vector, taboo_embeddings, taboo_docs
            )
        )

        # Accept similarity
        results.append(
            self.scorers['accept_similarity'].score(
                semantic_vector, accepted_embeddings, accepted_docs
            )
        )

        # Reject similarity
        results.append(
            self.scorers['reject_similarity'].score(
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
                self.scorers['direction'].score(
                    delta_semantic, accepted_centroid, rejected_centroid
                )
            )
        else:
            results.append(ScorerResult(
                name="direction",
                score=0.0,
                weight=self.scorers['direction'].weight,
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
            self.scorers['drift'].score(
                semantic_vector, ewma, historical_vectors
            )
        )

        # Anomaly
        trajectory = state_vector.get('trajectory', {})
        feature_mean = historical_baseline.get('feature_mean') if historical_baseline else None
        feature_cov_inv = historical_baseline.get('feature_cov_inv') if historical_baseline else None
        results.append(
            self.scorers['anomaly'].score(
                trajectory, feature_mean, feature_cov_inv
            )
        )

        # Uncertainty
        uncertainty = state_vector.get('uncertainty', {})
        results.append(
            self.scorers['uncertainty'].score(
                judge_std=uncertainty.get('judge_std', 0),
                self_confidence=uncertainty.get('self_confidence', 0),
                tool_error_rate=uncertainty.get('tool_error_rate', 0),
                evidence_gap=uncertainty.get('evidence_gap', 0)
            )
        )

        return results

    def _determine_state(
        self,
        composite_score: float,
        scorer_results: List[ScorerResult],
        state_vector: Dict,
        threshold_version: str,
        policy_version: str
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
            thresholds=self.thresholds,
            hard_overrides_config=self.hard_overrides,
            threshold_version=threshold_version,
            policy_version=policy_version,
            gate_state_cls=GateState,
            decision_result_cls=DecisionResult,
            taboo_score=taboo_score
        )
        if ho02_result:
            return GateState.BLOCK, "process_correction"

        # Apply declarative rules
        for state_name, rules in STATE_RULES.items():
            for rule in rules:
                if self._matches_rule(rule, scores, composite_score, tool_error_rate):
                    gate_state = GateState[state_name.upper()]
                    return gate_state, rule['action']

        return GateState.PASS, "continue"

    def _matches_rule(self, rule: Dict, scores: Dict, composite: float, tool_error: float) -> bool:
        """Check if a single rule matches."""
        threshold = rule['threshold']
        op = rule.get('op', 'ge')

        # Get threshold value from config if string key
        if isinstance(threshold, str):
            threshold = self.thresholds.get(threshold, 0.0)

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

    def evaluate_with_kb(
        self,
        state_vector: Dict,
        kb_store: 'VectorStore',
        scope: str = None
    ) -> DecisionResult:
        """
        Evaluate using KB store (vector_store module integration).

        Args:
            state_vector: State vector to evaluate
            kb_store: VectorStore instance
            scope: Optional scope filter

        Returns:
            DecisionResult
        """
        semantic = state_vector.get('semantic', {})
        semantic_vector = semantic.get('vector', [])

        kb_embeddings = {}
        for axis in ['constitution', 'taboo', 'accepted', 'rejected']:
            docs = kb_store.search_by_axis(semantic_vector, axis, limit=10)
            kb_embeddings[axis] = [d.get('embedding', []) for d in docs]
            kb_embeddings[f'{axis}_docs'] = docs

        return self.evaluate(state_vector, kb_embeddings)

    # ========== Threshold Version Management ==========

    def get_threshold_version(self) -> str:
        """Get current threshold version."""
        return self._threshold_version_manager.current_version

    def update_threshold_version(self, version: str) -> None:
        """Update threshold version."""
        self._threshold_version_manager.set_current_version(version)
        self.config['threshold_version'] = version

    def get_locked_thresholds(self, version: str) -> Optional[Dict]:
        """Retrieve locked threshold configuration for a specific version."""
        return self._threshold_version_manager.get_locked_config(version)

    def replay_with_version(
        self,
        version: str,
        state_vector: Dict,
        kb_embeddings: Dict = None
    ) -> Optional[DecisionResult]:
        """
        Re-evaluate using a specific locked threshold version.

        Args:
            version: Threshold version to use
            state_vector: State vector to evaluate
            kb_embeddings: Optional KB embeddings

        Returns:
            DecisionResult or None if version not found
        """
        locked_config = self.get_locked_thresholds(version)
        if not locked_config:
            return None

        # Temporarily swap thresholds
        original_thresholds = self.thresholds
        original_overrides = self.hard_overrides

        self.thresholds = locked_config['thresholds']
        self.hard_overrides = locked_config['hard_overrides']

        result = self.evaluate(state_vector, kb_embeddings)
        result.threshold_version = version

        # Restore original thresholds
        self.thresholds = original_thresholds
        self.hard_overrides = original_overrides

        return result

    # ========== SLA Handling ==========

    def calculate_sla_deadlines(
        self,
        severity: str,
        created_at: datetime = None
    ) -> Dict[str, Optional[datetime]]:
        """Calculate SLA ACK and decision deadlines based on severity."""
        return self._sla_handler.calculate_deadlines(severity, created_at)

    def check_sla_timeout(
        self,
        severity: str,
        review_created_at: datetime,
        ack_taken_at: datetime = None
    ) -> Tuple[bool, Optional[str]]:
        """Check if SLA timeout has been exceeded."""
        return self._sla_handler.check_timeout(severity, review_created_at, ack_taken_at)

    def handle_sla_timeout(
        self,
        decision_id: str,
        timeout_type: str,
        sla_deadline: datetime,
        escalation_target: str
    ) -> DecisionResult:
        """Handle SLA timeout by failing closed."""
        return self._sla_handler.handle_timeout(
            decision_id,
            timeout_type,
            sla_deadline,
            escalation_target,
            GateState,
            DecisionResult,
            self.get_threshold_version()
        )

    # ========== Late Hard Fail Handling ==========

    def handle_late_hard_fail(
        self,
        original_decision_id: str,
        late_fail_type: str,
        affected_artifacts: List[str],
        detection_time: datetime = None
    ) -> DecisionResult:
        """
        Handle late hard fail detected after run completed with PASS state.

        STATE_TRANSITION_SPEC 9.1, T27: Invalidates issued artifact.
        """
        if detection_time is None:
            detection_time = datetime.now(timezone.utc)

        # Build ScoreFactor for late hard fail
        late_fail_factor = ScoreFactor(
            name='late_hard_fail',
            value=1.0,
            weight=1.0,
            contribution=1.0
        )

        result = DecisionResult(
            decision='block',
            composite_score=1.0,
            artifact_ref={'uri': affected_artifacts[0], 'diff_hash': ''} if affected_artifacts else None,
            factors=[late_fail_factor],
            exemplar_refs=[],
            action={'action_type': 'artifact_correction'},
            threshold_version=self.get_threshold_version(),
            hard_override=f'late_hard_fail_{late_fail_type}',
            static_gate_summary={'gates_executed': [], 'all_passed': False, 'hard_failures': [], 'warnings': []},
            scorer_results=[],
            transition_reason='late_fail_superseding_pass',
            created_at=detection_time
        )

        log_late_hard_fail(
            original_decision_id,
            late_fail_type,
            affected_artifacts,
            detection_time,
            audit_logger=audit_logger
        )

        return result

    # ========== Checkpoint Rollback Support ==========

    def handle_checkpoint_rollback(
        self,
        rollback_reason: str,
        source_checkpoint_ref: str,
        target_checkpoint_ref: str,
        upstream_failure_ref: str = None
    ) -> Tuple[GateState, str]:
        """
        Handle checkpoint rollback request due to upstream failure.

        STATE_TRANSITION_SPEC 9.3, T28: Returns (HOLD, 're-evaluate').
        """
        log_checkpoint_rollback(
            rollback_reason,
            source_checkpoint_ref,
            target_checkpoint_ref,
            upstream_failure_ref,
            audit_logger=audit_logger
        )

        return GateState.HOLD, 're-evaluate'

    def rollback_to_checkpoint(
        self,
        checkpoint_ref: str,
        state_vector: Dict,
        kb_embeddings: Dict = None
    ) -> DecisionResult:
        """Restore state from checkpoint and re-evaluate."""
        result = self.evaluate(state_vector, kb_embeddings)
        result.checkpoint_ref = checkpoint_ref
        result.previous_state = 'pass'
        result.transition_reason = 'checkpoint_rollback_re_evaluation'

        log_state_transition(result, result.previous_state, audit_logger=audit_logger)

        return result

    # ========== Self-Correction Tracking ==========

    def track_self_correction(
        self,
        current_count: int,
        top_factors: List[str]
    ) -> Tuple[bool, List[str]]:
        """Track self-correction iteration and determine if escalation needed."""
        return self._self_correction_tracker.track_iteration(current_count, top_factors)

    def check_persistent_factor_escalation(
        self,
        factor_history: List[List[str]]
    ) -> bool:
        """Check if same top factor persists for N consecutive runs."""
        return self._self_correction_tracker.check_persistent_factor(factor_history)

    def _log_state_transition(
        self,
        result: DecisionResult,
        previous_state: GateState = None
    ) -> None:
        """Log state transition for audit trail (backward-compatible method)."""
        log_state_transition(result, previous_state, audit_logger=audit_logger)

    # ========== Severity Calculation ==========

    def calculate_severity(self, result: DecisionResult) -> str:
        """
        Calculate review severity based on decision factors.

        Used for review queue routing.
        """
        # Critical: hard override blocks, secret detection, prod_write + taboo
        if result.hard_override in [
            'secret_found',
            'prod_write_taboo',
            'sast_high',
            'sla_timeout_fail_closed'
        ]:
            return 'critical'

        # Critical: taboo block threshold
        for scorer_result in result.scorer_results:
            if scorer_result.name == 'taboo_proximity':
                if scorer_result.score >= self.thresholds.get('taboo_block', 0.88):
                    return 'critical'

        # High: high privilege + uncertainty, hold states with significant risk
        if result.decision == 'hold':
            if 'High privilege' in str(result.factors):
                return 'high'
            for factor in result.factors:
                if any(keyword in factor.name for keyword in ['taboo', 'reject', 'anomaly']):
                    return 'high'
            return 'medium'

        # Medium: warn states
        if result.decision == 'warn':
            return 'medium'

        return 'low'
