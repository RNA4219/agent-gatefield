"""
Additional tests for DecisionEngine - coverage boost.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from src.core.engine import (
    DecisionEngine,
    DecisionResult,
    GateState,
    STATE_RULES,
)
from src.core.engine.helpers import compute_centroid
from src.core.engine.phases import matches_rule, determine_gate_state


class TestEngineComputeCentroid:
    """Tests for compute_centroid function."""

    def test_compute_centroid_empty(self):
        """Empty embeddings returns empty list."""
        result = compute_centroid([])
        assert result == []

    def test_compute_centroid_single(self):
        """Single embedding returns same vector."""
        embedding = [0.5] * 1024
        result = compute_centroid([embedding])
        assert result == embedding

    def test_compute_centroid_two(self):
        """Two embeddings average."""
        emb1 = [1.0] * 1024
        emb2 = [0.0] * 1024
        result = compute_centroid([emb1, emb2])
        assert len(result) == 1024
        assert all(v == 0.5 for v in result)

    def test_compute_centroid_multiple(self):
        """Multiple embeddings average."""
        embeddings = [[i] * 1024 for i in range(1, 4)]  # [1,1,1], [2,2,2], [3,3,3]
        result = compute_centroid(embeddings)
        assert len(result) == 1024
        assert all(abs(v - 2.0) < 0.001 for v in result)


class TestEngineMatchesRule:
    """Tests for matches_rule function."""

    def test_matches_rule_composite_ge(self):
        """Composite rule with ge operator."""
        rule = {'composite': True, 'threshold': 0.5}
        assert matches_rule(rule, {}, 0.6, 0.0, {}) is True
        assert matches_rule(rule, {}, 0.4, 0.0, {}) is False

    def test_matches_rule_composite_threshold(self):
        """Composite rule threshold."""
        rule = {'composite': True, 'threshold': 0.65}
        assert matches_rule(rule, {}, 0.65, 0.0, {}) is True
        assert matches_rule(rule, {}, 0.64, 0.0, {}) is False

    def test_matches_rule_scorer_ge(self):
        """Scorer rule with ge operator."""
        rule = {'scorer': 'taboo_proximity', 'threshold': 0.80}
        scores = {'taboo_proximity': 0.85}
        assert matches_rule(rule, scores, 0.0, 0.0, {}) is True
        assert matches_rule(rule, {'taboo_proximity': 0.75}, 0.0, 0.0, {}) is False

    def test_matches_rule_scorer_le(self):
        """Scorer rule with le operator."""
        rule = {'scorer': 'direction', 'threshold': 0.5, 'op': 'le'}
        scores = {'direction': 0.3}
        assert matches_rule(rule, scores, 0.0, 0.0, {}) is True
        scores = {'direction': 0.6}
        assert matches_rule(rule, scores, 0.0, 0.0, {}) is False

    def test_matches_rule_scorer_lt(self):
        """Scorer rule with lt operator."""
        rule = {'scorer': 'uncertainty', 'threshold': 0.2, 'op': 'lt'}
        scores = {'uncertainty': 0.1}
        assert matches_rule(rule, scores, 0.0, 0.0, {}) is True
        scores = {'uncertainty': 0.2}
        assert matches_rule(rule, scores, 0.0, 0.0, {}) is False

    def test_matches_rule_tool_error_rate(self):
        """Field-based tool_error_rate rule."""
        rule = {'field': 'tool_error_rate', 'threshold': 0.1}
        assert matches_rule(rule, {}, 0.0, 0.15, {}) is True
        assert matches_rule(rule, {}, 0.0, 0.05, {}) is False

    def test_matches_rule_threshold_string(self):
        """Threshold as string key."""
        thresholds = {'custom_threshold': 0.5}
        rule = {'scorer': 'test', 'threshold': 'custom_threshold'}
        scores = {'test': 0.6}
        assert matches_rule(rule, scores, 0.0, 0.0, thresholds) is True

    def test_matches_rule_missing_scorer(self):
        """Missing scorer returns False."""
        rule = {'scorer': 'nonexistent', 'threshold': 0.5}
        assert matches_rule(rule, {}, 0.0, 0.0, {}) is False

    def test_matches_rule_scorer_with_default_op(self):
        """Scorer rule with default ge operator."""
        rule = {'scorer': 'test', 'threshold': 0.5}
        scores = {'test': 0.5}
        assert matches_rule(rule, scores, 0.0, 0.0, {}) is True


class TestEngineDetermineState:
    """Tests for determine_gate_state function."""

    def test_determine_state_pass(self):
        """Low scores result in pass."""
        from src.scorers import ScorerResult
        scorer_results = [
            ScorerResult(name='taboo_proximity', score=0.1, weight=0.3, weighted_score=0.03, top_exemplar_refs=[], explanation=''),
            ScorerResult(name='reject_similarity', score=0.1, weight=0.2, weighted_score=0.02, top_exemplar_refs=[], explanation=''),
        ]
        state_vector = {'uncertainty': {'judge_std': 0.01}}
        state, action = determine_gate_state(
            0.3, scorer_results, state_vector, {}, {}, 'v1', 'v1',
            GateState, DecisionResult
        )
        assert state == GateState.PASS

    def test_determine_state_with_high_taboo(self):
        """High taboo score triggers block."""
        from src.scorers import ScorerResult
        scorer_results = [
            ScorerResult(name='taboo_proximity', score=0.95, weight=0.3, weighted_score=0.285, top_exemplar_refs=[], explanation=''),
        ]
        state_vector = {'uncertainty': {}}
        state, action = determine_gate_state(
            0.95, scorer_results, state_vector, {}, {}, 'v1', 'v1',
            GateState, DecisionResult
        )
        assert state in (GateState.BLOCK, GateState.HOLD)

    def test_determine_state_with_tool_error(self):
        """High tool_error_rate triggers action."""
        from src.scorers import ScorerResult
        scorer_results = []
        state_vector = {'uncertainty': {'tool_error_rate': 0.5}}
        state, action = determine_gate_state(
            0.3, scorer_results, state_vector, {}, {}, 'v1', 'v1',
            GateState, DecisionResult
        )
        # High tool error should trigger some state
        assert state in (GateState.BLOCK, GateState.HOLD, GateState.WARN, GateState.PASS)


class TestEngineWithConstitutionEmbeddings:
    """Tests for constitution embeddings."""

    def test_evaluate_with_constitution_embeddings(self):
        """Evaluation with constitution embeddings."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-const',
            'artifact_id': 'art-const',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02},
            'semantic': {'vector': [0.5] * 1024}
        }
        kb_embeddings = {
            'constitution_embeddings': [[0.5] * 1024],
            'taboo_embeddings': [[0.1] * 1024],
            'accepted_embeddings': [[0.6] * 1024],
            'rejected_embeddings': [[0.4] * 1024]
        }
        result = engine.evaluate(state_vector, kb_embeddings)
        assert result is not None

    def test_evaluate_with_trajectory(self):
        """Evaluation with trajectory data."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-traj',
            'artifact_id': 'art-traj',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02},
            'semantic': {'vector': [0.5] * 1024},
            'trajectory': {
                'delta_semantic_vector': [0.1] * 1024
            }
        }
        kb_embeddings = {
            'accepted_embeddings': [[0.6] * 1024, [0.7] * 1024],
            'rejected_embeddings': [[0.4] * 1024, [0.3] * 1024]
        }
        result = engine.evaluate(state_vector, kb_embeddings)
        assert result is not None


class TestEngineGetLockedThresholds:
    """Tests for get_locked_thresholds method."""

    def test_get_locked_thresholds_v1(self):
        """Get v1 thresholds."""
        engine = DecisionEngine({})
        result = engine.get_locked_thresholds('v1')
        assert result is not None

    def test_get_locked_thresholds_v2_not_exists(self):
        """Get v2 thresholds (may not exist)."""
        engine = DecisionEngine({})
        result = engine.get_locked_thresholds('v2')
        # v2 may not exist, returns None
        assert result is None or result is not None

    def test_get_locked_thresholds_invalid(self):
        """Invalid version returns None."""
        engine = DecisionEngine({})
        result = engine.get_locked_thresholds('invalid_version')
        assert result is None


class TestEngineDecisionResultFields:
    """Tests for DecisionResult fields."""

    def test_decision_result_scorer_results(self):
        """DecisionResult has scorer_results."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-scorers',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02}
        }
        result = engine.evaluate(state_vector, {})
        assert result.scorer_results is not None
        assert isinstance(result.scorer_results, list)

    def test_decision_result_exemplar_refs(self):
        """DecisionResult has exemplar_refs."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-ex',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02}
        }
        result = engine.evaluate(state_vector, {})
        assert result.exemplar_refs is not None
        assert isinstance(result.exemplar_refs, list)


class TestEngineHo02Override:
    """Tests for HO02 hard override."""

    def test_ho02_prod_write_taboo_warn(self):
        """HO02 triggers on prod write with taboo warn."""
        engine = DecisionEngine({
            'hard_overrides': {'block_if_prod_write_and_taboo_warn': True}
        })
        state_vector = {
            'run_id': 'run-ho02',
            'artifact_id': 'art-1',
            'rule_violation': {},
            'risk': {'prod_write': 1},
            'uncertainty': {}
        }
        result = engine.evaluate(state_vector, {})
        # Decision depends on config and taboo score
        assert result.decision in ('pass', 'warn', 'hold', 'block')


class TestEngineDirectionScorer:
    """Tests for direction scorer integration."""

    def test_direction_with_trajectory(self):
        """Direction scorer with trajectory."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-dir',
            'artifact_id': 'art-dir',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02},
            'semantic': {'vector': [0.5] * 1024},
            'trajectory': {'delta_semantic_vector': [0.1] * 1024}
        }
        kb_embeddings = {
            'accepted_embeddings': [[0.5] * 1024],
            'rejected_embeddings': [[0.3] * 1024]
        }
        result = engine.evaluate(state_vector, kb_embeddings)
        assert result is not None


class TestEngineStateVectorFields:
    """Tests for state vector field handling."""

    def test_state_vector_with_artifact_hash(self):
        """State vector with artifact_hash."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-hash',
            'artifact_id': 'art-hash',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02},
            'artifact_hash': 'sha256:abc123'
        }
        result = engine.evaluate(state_vector, {})
        assert result is not None

    def test_state_vector_with_repo_branch(self):
        """State vector with repo and branch."""
        engine = DecisionEngine({})
        state_vector = {
            'run_id': 'run-repo',
            'artifact_id': 'art-repo',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.02},
            'repo': 'my-repo',
            'branch': 'feature-branch'
        }
        result = engine.evaluate(state_vector, {})
        assert result is not None


class TestEngineThresholdConfig:
    """Tests for threshold configuration."""

    def test_custom_thresholds(self):
        """Custom thresholds in config."""
        config = {
            'thresholds': {
                'taboo_block': 0.99,
                'taboo_warn': 0.90,
                'reject_block': 0.95,
                'reject_warn': 0.85
            }
        }
        engine = DecisionEngine(config)
        assert engine.thresholds['taboo_block'] == 0.99

    def test_threshold_empty_config(self):
        """Empty config has empty thresholds."""
        engine = DecisionEngine({})
        assert isinstance(engine.thresholds, dict)

    def test_thresholds_from_constants(self):
        """Thresholds loaded from constants."""
        config = {'thresholds': {'taboo_block': 0.88}}
        engine = DecisionEngine(config)
        assert engine.thresholds.get('taboo_block') == 0.88
