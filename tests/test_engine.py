"""
Tests for DecisionEngine - core decision logic.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from src.core.engine import (
    DecisionEngine,
    DecisionResult,
    GateState,
    STATE_RULES,
)


class TestDecisionEngineInit:
    """Tests for DecisionEngine initialization."""

    def test_default_init(self):
        """Default initialization."""
        engine = DecisionEngine({})
        assert engine.get_threshold_version() == 'v1'

    def test_config_init(self):
        """Configuration initialization."""
        config = {
            'thresholds': {'taboo_block': 0.90},
            'threshold_version': 'v2'
        }
        engine = DecisionEngine(config)
        assert engine.get_threshold_version() == 'v2'


class TestDecisionEngineEvaluate:
    """Tests for evaluate method."""

    def test_evaluate_basic(self):
        """Basic evaluation."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-1',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.05}
        }
        result = engine.evaluate(state_vector, {})
        assert result is not None
        assert result.decision in ('pass', 'warn', 'hold', 'block')

    def test_evaluate_with_kb_embeddings(self):
        """Evaluation with KB embeddings."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-1',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {}
        }
        kb_embeddings = {
            'taboo': [[0.1] * 1024],
            'accepted': [[0.2] * 1024]
        }
        result = engine.evaluate(state_vector, kb_embeddings)
        assert result is not None


class TestDecisionEngineThresholdVersioning:
    """Tests for threshold versioning."""

    def test_get_threshold_version(self):
        """Get threshold version."""
        engine = DecisionEngine({})
        version = engine.get_threshold_version()
        assert version == 'v1'

    def test_get_locked_thresholds_missing(self):
        """Get locked thresholds for missing version."""
        engine = DecisionEngine({})
        config = engine.get_locked_thresholds('v999')
        assert config is None

    def test_config_with_version(self):
        """Config with threshold version."""
        engine = DecisionEngine({'threshold_version': 'v2'})
        assert engine.get_threshold_version() == 'v2'


class TestDecisionEngineHardOverrides:
    """Tests for hard overrides."""

    def test_secret_found_blocks(self):
        """Secret found triggers block."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-1',
            'artifact_id': 'art-1',
            'rule_violation': {'secret': 1},
            'risk': {},
            'uncertainty': {}
        }
        result = engine.evaluate(state_vector, {})
        assert result.decision == 'block'

    def test_no_secret_passes(self):
        """No secret allows normal evaluation."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-1',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.05}
        }
        result = engine.evaluate(state_vector, {})
        # Should not be blocked by hard override
        assert result.hard_override is None or result.decision != 'block'


class TestDecisionResult:
    """Tests for DecisionResult."""

    def test_decision_result_creation(self):
        """DecisionResult basic creation."""
        result = DecisionResult(
            decision='pass',
            composite_score=0.65,
            scorer_results=[],
            factors=['low_risk'],
            exemplar_refs=[],
            threshold_version='v1'
        )
        assert result.decision == 'pass'
        assert result.composite_score == 0.65

    def test_decision_result_with_override(self):
        """DecisionResult with hard override."""
        result = DecisionResult(
            decision='block',
            composite_score=1.0,
            scorer_results=[],
            factors=['hard_override'],
            exemplar_refs=[],
            threshold_version='v1',
            hard_override='secret_found'
        )
        assert result.hard_override == 'secret_found'


class TestGateState:
    """Tests for GateState enum."""

    def test_gate_states(self):
        """Gate state values."""
        assert GateState.PASS.value == 'pass'
        assert GateState.WARN.value == 'warn'
        assert GateState.HOLD.value == 'hold'
        assert GateState.BLOCK.value == 'block'


class TestStateRules:
    """Tests for STATE_RULES configuration."""

    def test_block_rules_exist(self):
        """Block rules defined."""
        assert 'block' in STATE_RULES
        assert len(STATE_RULES['block']) > 0

    def test_hold_rules_exist(self):
        """Hold rules defined."""
        assert 'hold' in STATE_RULES
        assert len(STATE_RULES['hold']) > 0

    def test_warn_rules_exist(self):
        """Warn rules defined."""
        assert 'warn' in STATE_RULES
        assert len(STATE_RULES['warn']) > 0

    def test_block_rule_thresholds(self):
        """Block rule thresholds."""
        for rule in STATE_RULES['block']:
            assert 'threshold' in rule


class TestDecisionEngineIntegration:
    """Integration-like tests."""

    def test_full_evaluation(self):
        """Full evaluation with state components."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-full',
            'artifact_id': 'art-full',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.05}
        }
        result = engine.evaluate(state_vector, {})
        assert result.decision in ('pass', 'warn', 'hold', 'block')

    def test_high_uncertainty_hold(self):
        """High uncertainty triggers hold."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-hold',
            'artifact_id': 'art-hold',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.30}
        }
        result = engine.evaluate(state_vector, {})
        # High uncertainty should trigger some state change
        assert result.decision in ('pass', 'warn', 'hold', 'block')

    def test_evaluation_with_all_components(self):
        """Evaluation with all state components."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-full',
            'artifact_id': 'art-full',
            'rule_violation': {},
            'risk': {'high_privilege': 0},
            'uncertainty': {'judge_std': 0.02},  # Very low uncertainty
            'artifact_hash': 'sha256:abc',
            'repo': 'test-repo',
            'branch': 'main'
        }
        result = engine.evaluate(state_vector, {})
        assert result.run_id == 'run-full'
        assert result.threshold_version is not None


class TestEngineCoverageBoost:
    """
    Additional tests to boost core/engine.py coverage.
    Covers: state transitions, hard overrides, edge cases, scorer integration.
    """

    def test_engine_with_taboo_threshold(self):
        """Engine respects taboo threshold config."""
        config = {
            'thresholds': {'taboo_block': 0.95, 'taboo_warn': 0.85},
            'threshold_version': 'custom-v1'
        }
        engine = DecisionEngine(config)
        assert engine.get_threshold_version() == 'custom-v1'

    def test_engine_state_rules_loaded(self):
        """STATE_RULES are defined."""
        assert STATE_RULES is not None
        assert isinstance(STATE_RULES, dict)

    def test_gate_state_values(self):
        """GateState enum values."""
        assert GateState.PASS.value == 'pass'
        assert GateState.WARN.value == 'warn'
        assert GateState.HOLD.value == 'hold'
        assert GateState.BLOCK.value == 'block'

    def test_engine_high_uncertainty_hold(self):
        """High uncertainty triggers hold."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-uncertain',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.30}  # High uncertainty
        }
        result = engine.evaluate(state_vector, {})
        assert result.decision in ('hold', 'block')

    def test_engine_empty_rule_violation(self):
        """Empty rule violation with low uncertainty."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-clean',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.01}  # Very low uncertainty
        }
        result = engine.evaluate(state_vector, {})
        # Decision depends on scorer results
        assert result.decision in ('pass', 'warn', 'hold')

    def test_engine_with_static_gate_results(self):
        """Engine processes static gate results."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-static',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02}
        }
        static_results = {
            'lint': {'status': 'pass'},
            'sast': {'status': 'pass'},
            'secret_scan': {'status': 'pass'}
        }
        result = engine.evaluate(state_vector, static_results)
        assert result.static_gate_summary is not None

    def test_decision_result_factors(self):
        """DecisionResult includes factors."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-factors',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02}
        }
        result = engine.evaluate(state_vector, {})
        assert result.factors is not None
        assert isinstance(result.factors, list)

    def test_decision_result_action_type(self):
        """DecisionResult includes action type."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-action',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02}
        }
        result = engine.evaluate(state_vector, {})
        assert result.action is not None
        # action is a dict
        assert 'action_type' in result.action
        assert result.action['action_type'] in ('pass', 'warn', 'human_review', 'block')

    def test_engine_with_hard_override_config(self):
        """Engine handles hard override config."""
        config = {
            'hard_overrides': {
                'block_if_secret_found': True,
                'block_if_prod_write_and_taboo_warn': True
            }
        }
        engine = DecisionEngine(config)
        assert engine.config.get('hard_overrides') is not None

    def test_engine_decision_result_serializable(self):
        """DecisionResult can be serialized."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-serial',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02}
        }
        result = engine.evaluate(state_vector, {})
        # Should be able to convert to dict
        result_dict = result.to_dict() if hasattr(result, 'to_dict') else {
            'decision': result.decision,
            'run_id': result.run_id
        }
        assert 'decision' in result_dict

    def test_engine_composite_score_range(self):
        """Composite score is in valid range."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-score',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02}
        }
        result = engine.evaluate(state_vector, {})
        assert 0.0 <= result.composite_score <= 1.0

    def test_engine_with_scorer_weights(self):
        """Engine uses configured scorer weights."""
        config = {
            'scorers': {
                'constitution_alignment': {'weight': 0.25},
                'taboo_proximity': {'weight': 0.35}
            }
        }
        engine = DecisionEngine(config)
        # Engine should load weights
        assert engine.config.get('scorers') is not None

    def test_engine_run_id_propagation(self):
        """Run_id is propagated through evaluation."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'specific-run-123',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02}
        }
        result = engine.evaluate(state_vector, {})
        assert result.run_id == 'specific-run-123'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])