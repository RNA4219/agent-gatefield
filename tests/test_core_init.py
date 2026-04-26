"""
Tests for Core __init__ - lazy imports and exports.
"""

import pytest


class TestCoreImports:
    """Tests for lazy imports from src.core."""

    def test_import_decision_engine(self):
        from src.core import DecisionEngine
        assert DecisionEngine is not None

    def test_import_decision_result(self):
        from src.core import DecisionResult
        assert DecisionResult is not None

    def test_import_gate_state(self):
        from src.core import GateState
        assert GateState is not None

    def test_import_cosine_similarity(self):
        from src.core import cosine_similarity
        assert cosine_similarity is not None

    def test_import_cosine_distance(self):
        from src.core import cosine_distance
        assert cosine_distance is not None

    def test_import_mahalanobis_distance(self):
        from src.core import mahalanobis_distance
        assert mahalanobis_distance is not None

    def test_import_calibration_pipeline(self):
        from src.core import CalibrationPipeline
        assert CalibrationPipeline is not None

    def test_import_calibration_result(self):
        from src.core import CalibrationResult
        assert CalibrationResult is not None

    def test_import_threshold_version(self):
        from src.core import ThresholdVersion
        assert ThresholdVersion is not None

    def test_import_drift_indicators(self):
        from src.core import DriftIndicators
        assert DriftIndicators is not None

    def test_import_mahalanobis_params(self):
        from src.core import MahalanobisParams
        assert MahalanobisParams is not None

    def test_import_calibration_profile(self):
        from src.core import CalibrationProfile
        assert CalibrationProfile is not None

    def test_import_default_scorer_weights(self):
        from src.core import DEFAULT_SCORER_WEIGHTS
        assert DEFAULT_SCORER_WEIGHTS is not None

    def test_import_weight_constraints(self):
        from src.core import WEIGHT_CONSTRAINTS
        assert WEIGHT_CONSTRAINTS is not None

    def test_import_default_thresholds(self):
        from src.core import DEFAULT_THRESHOLDS
        assert DEFAULT_THRESHOLDS is not None

    def test_import_percentile_defaults(self):
        from src.core import PERCENTILE_DEFAULTS
        assert PERCENTILE_DEFAULTS is not None

    def test_import_min_sample_sizes(self):
        from src.core import MIN_SAMPLE_SIZES
        assert MIN_SAMPLE_SIZES is not None

    def test_import_isolation_forest_defaults(self):
        from src.core import ISOLATION_FOREST_DEFAULTS
        assert ISOLATION_FOREST_DEFAULTS is not None

    def test_import_contamination_by_env(self):
        from src.core import CONTAMINATION_BY_ENV
        assert CONTAMINATION_BY_ENV is not None

    def test_import_anomaly_features(self):
        from src.core import ANOMALY_FEATURES
        assert ANOMALY_FEATURES is not None

    def test_import_feature_normalization(self):
        from src.core import FEATURE_NORMALIZATION
        assert FEATURE_NORMALIZATION is not None

    def test_import_drift_indicators_const(self):
        from src.core import DRIFT_INDICATORS
        assert DRIFT_INDICATORS is not None

    def test_import_drift_responses(self):
        from src.core import DRIFT_RESPONSES
        assert DRIFT_RESPONSES is not None

    def test_import_migration_criteria(self):
        from src.core import MIGRATION_CRITERIA
        assert MIGRATION_CRITERIA is not None

    def test_import_reproducibility_target(self):
        from src.core import REPRODUCIBILITY_TARGET
        assert REPRODUCIBILITY_TARGET is not None

    def test_import_online_adjustment_limits(self):
        from src.core import ONLINE_ADJUSTMENT_LIMITS
        assert ONLINE_ADJUSTMENT_LIMITS is not None

    def test_import_calibration_triggers(self):
        from src.core import CALIBRATION_TRIGGERS
        assert CALIBRATION_TRIGGERS is not None

    def test_import_normalize_feature(self):
        from src.core import normalize_feature
        assert normalize_feature is not None

    def test_import_calculate_ewma(self):
        from src.core import calculate_ewma
        assert calculate_ewma is not None

    def test_import_calculate_uncertainty_score(self):
        from src.core import calculate_uncertainty_score
        assert calculate_uncertainty_score is not None

    def test_import_replay_engine(self):
        from src.core import ReplayEngine
        assert ReplayEngine is not None

    def test_import_replay_result(self):
        from src.core import ReplayResult
        assert ReplayResult is not None

    def test_import_audit_logger(self):
        from src.core import audit_logger
        assert audit_logger is not None

    def test_import_log_state_transition(self):
        from src.core import log_state_transition
        assert log_state_transition is not None

    def test_import_log_hard_override(self):
        from src.core import log_hard_override
        assert log_hard_override is not None

    def test_import_log_sla_timeout(self):
        from src.core import log_sla_timeout
        assert log_sla_timeout is not None

    def test_import_log_late_hard_fail(self):
        from src.core import log_late_hard_fail
        assert log_late_hard_fail is not None

    def test_import_log_checkpoint_rollback(self):
        from src.core import log_checkpoint_rollback
        assert log_checkpoint_rollback is not None

    def test_import_apply_hard_overrides(self):
        from src.core import apply_hard_overrides
        assert apply_hard_overrides is not None

    def test_import_check_hard_override_ho02(self):
        from src.core import check_hard_override_ho02
        assert check_hard_override_ho02 is not None

    def test_import_ho01_secret_found(self):
        from src.core import HO01_SECRET_FOUND
        assert HO01_SECRET_FOUND is not None

    def test_import_ho02_prod_write_taboo_warn(self):
        from src.core import HO02_PROD_WRITE_TABOO_WARN
        assert HO02_PROD_WRITE_TABOO_WARN is not None

    def test_import_ho03_high_privilege_uncertain(self):
        from src.core import HO03_HIGH_PRIVILEGE_UNCERTAIN
        assert HO03_HIGH_PRIVILEGE_UNCERTAIN is not None

    def test_import_ho04_sast_high(self):
        from src.core import HO04_SAST_HIGH
        assert HO04_SAST_HIGH is not None

    def test_import_ho05_tool_policy_deny(self):
        from src.core import HO05_TOOL_POLICY_DENY
        assert HO05_TOOL_POLICY_DENY is not None

    def test_import_sla_handler(self):
        from src.core import SLAHandler
        assert SLAHandler is not None

    def test_import_calculate_sla_deadlines_core(self):
        from src.core import calculate_sla_deadlines
        assert calculate_sla_deadlines is not None

    def test_import_check_sla_timeout(self):
        from src.core import check_sla_timeout
        assert check_sla_timeout is not None

    def test_import_handle_sla_timeout(self):
        from src.core import handle_sla_timeout
        assert handle_sla_timeout is not None

    def test_import_threshold_version_manager(self):
        from src.core import ThresholdVersionManager
        assert ThresholdVersionManager is not None

    def test_import_threshold_replay_context(self):
        from src.core import ThresholdReplayContext
        assert ThresholdReplayContext is not None

    def test_import_replay_with_version(self):
        from src.core import replay_with_version
        assert replay_with_version is not None

    def test_import_self_correction_tracker(self):
        from src.core import SelfCorrectionTracker
        assert SelfCorrectionTracker is not None

    def test_import_track_self_correction_core(self):
        from src.core import track_self_correction
        assert track_self_correction is not None

    def test_import_check_persistent_factor_escalation_core(self):
        from src.core import check_persistent_factor_escalation
        assert check_persistent_factor_escalation is not None

    def test_import_gate_evaluation_error(self):
        from src.core import GateEvaluationError
        assert GateEvaluationError is not None

    def test_import_calibration_error(self):
        from src.core import CalibrationError
        assert CalibrationError is not None

    def test_import_insufficient_samples_error(self):
        from src.core import InsufficientSamplesError
        assert InsufficientSamplesError is not None

    def test_import_weight_validation_error(self):
        from src.core import WeightValidationError
        assert WeightValidationError is not None

    def test_import_threshold_error(self):
        from src.core import ThresholdError
        assert ThresholdError is not None

    def test_import_threshold_not_found_error(self):
        from src.core import ThresholdNotFoundError
        assert ThresholdNotFoundError is not None

    def test_import_invalid_threshold_error(self):
        from src.core import InvalidThresholdError
        assert InvalidThresholdError is not None

    def test_import_drift_detection_error(self):
        from src.core import DriftDetectionError
        assert DriftDetectionError is not None

    def test_import_empty_distribution_error(self):
        from src.core import EmptyDistributionError
        assert EmptyDistributionError is not None

    def test_import_vector_dimension_mismatch_error(self):
        from src.core import VectorDimensionMismatchError
        assert VectorDimensionMismatchError is not None

    def test_import_matrix_singular_error(self):
        from src.core import MatrixSingularError
        assert MatrixSingularError is not None

    def test_import_version_error(self):
        from src.core import VersionError
        assert VersionError is not None

    def test_import_invalid_version_string_error(self):
        from src.core import InvalidVersionStringError
        assert InvalidVersionStringError is not None

    def test_import_version_lock_error(self):
        from src.core import VersionLockError
        assert VersionLockError is not None

    def test_import_migration_validation_error(self):
        from src.core import MigrationValidationError
        assert MigrationValidationError is not None

    def test_import_reproducibility_error(self):
        from src.core import ReproducibilityError
        assert ReproducibilityError is not None

    def test_import_review_queue_error(self):
        from src.core import ReviewQueueError
        assert ReviewQueueError is not None

    def test_import_item_not_found_error(self):
        from src.core import ItemNotFoundError
        assert ItemNotFoundError is not None

    def test_import_pair_not_found_error(self):
        from src.core import PairNotFoundError
        assert PairNotFoundError is not None


class TestCoreExports:
    """Tests for __all__ exports."""

    def test_all_exports_count(self):
        import src.core as core
        assert len(core.__all__) >= 50

    def test_all_exports_contains_engine(self):
        import src.core as core
        assert 'DecisionEngine' in core.__all__

    def test_all_exports_contains_exceptions(self):
        import src.core as core
        assert 'GateEvaluationError' in core.__all__
        assert 'CalibrationError' in core.__all__


class TestCoreAttributeError:
    """Tests for invalid attribute access."""

    def test_invalid_attribute_raises(self):
        import src.core as core
        with pytest.raises(AttributeError):
            core.nonexistent_attribute


class TestCoreImportUsage:
    """Tests for using imported classes."""

    def test_use_decision_engine(self):
        from src.core import DecisionEngine
        engine = DecisionEngine({})
        assert engine is not None

    def test_use_gate_state(self):
        from src.core import GateState
        assert GateState.PASS.value == 'pass'

    def test_use_exception(self):
        from src.core import GateEvaluationError
        try:
            raise GateEvaluationError('test')
        except GateEvaluationError as e:
            assert 'test' in str(e)
