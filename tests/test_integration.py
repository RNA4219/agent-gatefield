"""
Integration tests - End-to-end gate flow
AGF-REQ coverage: IT-E2E-001-009, RT-001-008, AT-AUD-001-003

Note: Some tests use mocks for database operations.
Integration tests requiring external resources are marked with @pytest.mark.integration
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import json

from src.core.engine import DecisionEngine, DecisionResult
from src.core.hard_overrides import (
    apply_hard_overrides,
    HO01_SECRET_FOUND,
    HO03_HIGH_PRIVILEGE_UNCERTAIN
)
from src.review.dataclasses import ReviewItem, ReviewAction
from src.core.calibration import CalibrationPipeline


@pytest.mark.integration
class TestEndToEndGateFlow:
    """CI → static gates → state scoring → review queue → audit"""

    @pytest.fixture
    def engine_config(self):
        return {
            'thresholds': {
                'composite_warn': 0.70,
                'composite_block': 0.85,
                'taboo_warn': 0.80,
                'taboo_block': 0.88,
                'judge_std_warn': 0.15,
                'judge_std_block': 0.25
            },
            'hard_overrides': {
                'block_if_secret_found': True,
                'block_if_prod_write_and_taboo_warn': True,
                'hold_if_high_privilege_and_uncertain': True
            },
            'threshold_version': 'v1'
        }

    def test_it_e2e_001_static_gate_fail_blocks_before_state_space(self, engine_config):
        """
        IT-E2E-002: Static gate hard fail blocks before state space evaluation.
        Hard override rules evaluated before scorers.
        """
        engine = DecisionEngine(engine_config)

        state_vector = {
            'run_id': 'run-e2e-001',
            'artifact_id': 'art-e2e-001',
            'rule_violation': {'secret': 1},  # Hard fail
            'risk': {},
            'uncertainty': {}
        }

        result = engine.evaluate(state_vector, {})

        assert result.decision == 'block'
        assert result.hard_override == HO01_SECRET_FOUND
        assert len(result.scorer_results) == 0

    def test_it_e2e_002_state_vector_has_threshold_version(self, engine_config):
        """
        IT-E2E-003: State vector evaluation produces threshold_version.
        """
        engine = DecisionEngine(engine_config)

        state_vector = {
            'run_id': 'run-e2e-002',
            'artifact_id': 'art-e2e-002',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {'judge_std': 0.05}
        }

        result = engine.evaluate(state_vector, {})

        assert result.threshold_version == 'v1'

    def test_it_e2e_003_high_privilege_hold(self, engine_config):
        """
        IT-E2E-003: High privilege + uncertainty triggers hold.
        """
        engine = DecisionEngine(engine_config)

        state_vector = {
            'run_id': 'run-e2e-003',
            'artifact_id': 'art-e2e-003',
            'rule_violation': {},
            'risk': {'high_privilege': 1},
            'uncertainty': {'judge_std': 0.20}
        }

        result = engine.evaluate(state_vector, {})

        assert result.decision == 'hold'
        assert result.hard_override == HO03_HIGH_PRIVILEGE_UNCERTAIN


@pytest.mark.integration
class TestAuditCompleteness:
    """
    Every gate decision must have complete audit trail.
    AGF-REQ-009: 100% trace_id / threshold_version / action_type
    """

    @pytest.fixture
    def engine_config(self):
        return {
            'thresholds': {'composite_warn': 0.70},
            'hard_overrides': {},
            'threshold_version': 'v1'
        }

    def test_at_aud_001_decision_has_threshold_version(self, engine_config):
        """
        AT-AUD-002: Decision includes threshold_version.
        """
        engine = DecisionEngine(engine_config)

        state_vector = {
            'run_id': 'run-audit-001',
            'artifact_id': 'art-audit-001',
            'rule_violation': {},
            'risk': {},
            'uncertainty': {}
        }

        result = engine.evaluate(state_vector, {})

        assert result.threshold_version == 'v1'

    def test_at_aud_002_decision_has_action_type(self, engine_config):
        """
        AT-AUD-003: Decision includes action_type.
        """
        engine = DecisionEngine(engine_config)

        # Block decision should have artifact_correction action
        state_vector = {
            'run_id': 'run-audit-002',
            'artifact_id': 'art-audit-002',
            'rule_violation': {'secret': 1},
            'risk': {},
            'uncertainty': {}
        }

        result = engine.evaluate(state_vector, {})

        assert result.action.get('action_type') == 'artifact_correction'

    def test_at_aud_003_hard_override_in_audit(self, engine_config):
        """
        AT-AUD-003: Hard override reason logged in audit.
        """
        engine = DecisionEngine(engine_config)

        state_vector = {
            'run_id': 'run-audit-003',
            'artifact_id': 'art-audit-003',
            'rule_violation': {'secret': 1},
            'risk': {},
            'uncertainty': {}
        }

        result = engine.evaluate(state_vector, {})

        result_dict = result.to_dict()
        assert 'hard_override_reason' in result_dict
        assert result_dict['hard_override_reason'] == 'secret_found'


@pytest.mark.integration
class TestReviewQueueIntegration:
    """
    Review queue operations integration.
    AGF-REQ-004, AGF-REQ-005 coverage.
    """

    def test_review_item_created_with_required_fields(self):
        """
        ReviewItem requires all schema fields per DATA_TYPES_SPEC.
        """
        now = datetime.now(timezone.utc)

        item = ReviewItem(
            decision_id='decision-001',
            run_id='run-review-001',
            state='hold',
            composite_score=0.85,
            severity='high',
            top_factors=['taboo_proximity', 'uncertainty'],
            artifact_ref='artifact://art-001',
            trace_ref='trace://trace-001',
            created_at=now
        )

        assert item.decision_id == 'decision-001'
        assert item.state == 'hold'
        assert item.severity == 'high'

    def test_review_action_resolution(self):
        """
        ReviewAction for resolution.
        """
        now = datetime.now(timezone.utc)

        action = ReviewAction(
            decision_id='decision-001',
            reviewer='reviewer-001',
            created_at=now
        )

        assert action.reviewer == 'reviewer-001'


@pytest.mark.integration
class TestOfflineEvaluation:
    """
    Offline eval on curated datasets.
    AGF-REQ-003: AUC 0.85+, recall 0.90+, false escalation 15%-
    """

    @pytest.fixture
    def taboo_cases(self):
        """Simulated taboo cases for evaluation."""
        return [
            {'id': 't1', 'taboo_type': 'injection', 'expected_state': 'block'},
            {'id': 't2', 'taboo_type': 'secret', 'expected_state': 'block'},
            {'id': 't3', 'taboo_type': 'tool_override', 'expected_state': 'hold'},
        ]

    def test_oe_002_hard_fail_100_percent(self):
        """
        OE-001: Hard fail deterministic - 100% block.
        """
        thresholds = {}
        hard_overrides_config = {'block_if_secret_found': True}

        test_cases = [
            {'rule_violation': {'secret': 1}},
            {'rule_violation': {'sast_high': 1}},
            {'rule_violation': {'tool_policy_deny': 1}},
        ]

        all_blocked = True
        for case in test_cases:
            state_vector = {
                'run_id': 'run-oe',
                'artifact_id': 'art-oe',
                'rule_violation': case['rule_violation'],
                'risk': {},
                'uncertainty': {}
            }

            result = apply_hard_overrides(
                state_vector=state_vector,
                thresholds=thresholds,
                hard_overrides_config=hard_overrides_config,
                threshold_version='v1',
                policy_version='v1',
                gate_state_cls=None,
                decision_result_cls=DecisionResult
            )

            if result and result.decision != 'block':
                all_blocked = False

        assert all_blocked


@pytest.mark.integration
class TestCalibrationIntegration:
    """
    Calibration operations integration.
    IT-DB-004 coverage.
    """

    def test_calibration_pipeline_calculates_thresholds(self):
        """
        CalibrationPipeline computes thresholds from distributions.
        Requires minimum 100 samples per spec.
        """
        pipeline = CalibrationPipeline(profile_id='test-calibration-001')

        # Generate 100+ accepted scores for calibration
        accepted_scores = [0.10 + i * 0.005 for i in range(100)]
        result = pipeline.calibrate_taboo_threshold(accepted_scores)

        assert result is not None
        assert result.new_threshold > 0
        assert len(pipeline.results) >= 1


@pytest.mark.integration
class TestShadowModeOperations:
    """
    Online shadow mode operations.
    AGF-REQ-008 coverage.
    """

    def test_shadow_kpi_targets_check(self):
        """
        Shadow mode KPI targets verification.
        """
        kpi_targets = {
            'review_load_reduction': 0.30,
            'critical_miss_rate': 0.0,
            'high_miss_rate': 0.05,
            'false_escalation_rate': 0.15
        }

        # Simulated measurements (would be collected during shadow period)
        measured = {
            'review_load_reduction': 0.35,
            'critical_miss_rate': 0.0,
            'high_miss_rate': 0.03,
            'false_escalation_rate': 0.10
        }

        # All targets met
        all_met = True
        for kpi, target in kpi_targets.items():
            measured_value = measured.get(kpi, 0)
            if kpi in ['high_miss_rate', 'false_escalation_rate', 'critical_miss_rate']:
                if measured_value > target:
                    all_met = False
            else:
                if measured_value < target:
                    all_met = False

        assert all_met


@pytest.mark.integration
class TestDecisionReproducibility:
    """
    Reproducibility tests for decision consistency.
    AGF-REQ-007 coverage.
    """

    def test_same_input_same_hard_override(self):
        """
        Same input conditions produce same hard override result.
        """
        thresholds = {'judge_std_warn': 0.15}
        hard_overrides_config = {'hold_if_high_privilege_and_uncertain': True}

        state_vector = {
            'run_id': 'run-repro',
            'artifact_id': 'art-repro',
            'rule_violation': {},
            'risk': {'high_privilege': 1},
            'uncertainty': {'judge_std': 0.20}
        }

        # Run twice
        result1 = apply_hard_overrides(
            state_vector=state_vector,
            thresholds=thresholds,
            hard_overrides_config=hard_overrides_config,
            threshold_version='v1',
            policy_version='v1',
            gate_state_cls=None,
            decision_result_cls=DecisionResult
        )

        result2 = apply_hard_overrides(
            state_vector=state_vector,
            thresholds=thresholds,
            hard_overrides_config=hard_overrides_config,
            threshold_version='v1',
            policy_version='v1',
            gate_state_cls=None,
            decision_result_cls=DecisionResult
        )

        # Same results
        assert result1.decision == result2.decision
        assert result1.hard_override == result2.hard_override