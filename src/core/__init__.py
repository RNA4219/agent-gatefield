"""
Core module - Decision engine and utilities.

This module provides:
- DecisionEngine: Main gate decision engine
- DecisionResult: Gate decision result dataclass
- GateState: Gate state enum
- Distance utilities: cosine_similarity, cosine_distance, mahalanobis_distance
- Calibration: CalibrationPipeline, CalibrationResult, dataclasses, constants
- Replay: ReplayEngine, ReplayResult
- Audit: Audit logging utilities
- Hard overrides: Hard override rules
- SLA handling: SLA timeout management
- Threshold versioning: Threshold lock and replay
- Self-correction: Self-correction tracking
- Exceptions: Custom exception classes
"""

# Lazy imports to avoid circular dependency
# Import directly from submodules instead

__all__ = [
    # Main engine
    'DecisionEngine',
    'DecisionResult',
    'GateState',
    # Distance utilities
    'cosine_similarity',
    'cosine_distance',
    'mahalanobis_distance',
    # Calibration classes
    'CalibrationPipeline',
    'CalibrationResult',
    'ThresholdVersion',
    'DriftIndicators',
    'MahalanobisParams',
    'CalibrationProfile',
    # Calibration constants
    'DEFAULT_SCORER_WEIGHTS',
    'WEIGHT_CONSTRAINTS',
    'DEFAULT_THRESHOLDS',
    'PERCENTILE_DEFAULTS',
    'MIN_SAMPLE_SIZES',
    'ISOLATION_FOREST_DEFAULTS',
    'CONTAMINATION_BY_ENV',
    'ANOMALY_FEATURES',
    'FEATURE_NORMALIZATION',
    'DRIFT_INDICATORS',
    'DRIFT_RESPONSES',
    'MIGRATION_CRITERIA',
    'REPRODUCIBILITY_TARGET',
    'ONLINE_ADJUSTMENT_LIMITS',
    'CALIBRATION_TRIGGERS',
    # Calibration utility functions
    'normalize_feature',
    'calculate_ewma',
    'calculate_uncertainty_score',
    # Replay
    'ReplayEngine',
    'ReplayResult',
    # Audit
    'audit_logger',
    'log_state_transition',
    'log_hard_override',
    'log_sla_timeout',
    'log_late_hard_fail',
    'log_checkpoint_rollback',
    # Hard overrides
    'apply_hard_overrides',
    'check_hard_override_ho02',
    'HO01_SECRET_FOUND',
    'HO02_PROD_WRITE_TABOO_WARN',
    'HO03_HIGH_PRIVILEGE_UNCERTAIN',
    'HO04_SAST_HIGH',
    'HO05_TOOL_POLICY_DENY',
    # SLA handling
    'SLAHandler',
    'calculate_sla_deadlines',
    'check_sla_timeout',
    'handle_sla_timeout',
    # Threshold versioning
    'ThresholdVersionManager',
    'ThresholdReplayContext',
    'replay_with_version',
    # Self-correction
    'SelfCorrectionTracker',
    'track_self_correction',
    'check_persistent_factor_escalation',
    # Exceptions
    'GateEvaluationError',
    'CalibrationError',
    'InsufficientSamplesError',
    'WeightValidationError',
    'ThresholdError',
    'ThresholdNotFoundError',
    'InvalidThresholdError',
    'DriftDetectionError',
    'EmptyDistributionError',
    'VectorDimensionMismatchError',
    'MatrixSingularError',
    'VersionError',
    'InvalidVersionStringError',
    'VersionLockError',
    'MigrationValidationError',
    'ReproducibilityError',
    'ReviewQueueError',
    'ItemNotFoundError',
    'PairNotFoundError',
]


def __getattr__(name):
    """Lazy import to avoid circular dependency"""
    # Main engine and types
    if name == 'DecisionEngine':
        from src.core.engine import DecisionEngine
        return DecisionEngine
    elif name in ('DecisionResult', 'GateState'):
        from src.core.types import DecisionResult, GateState
        return eval(name)
    # Distance utilities
    elif name in ('cosine_similarity', 'cosine_distance', 'mahalanobis_distance'):
        from src.core.distance import cosine_similarity, cosine_distance, mahalanobis_distance
        return eval(name)
    # Calibration (all exports from calibration.py)
    elif name in ('CalibrationPipeline', 'CalibrationResult', 'ThresholdVersion',
                  'DriftIndicators', 'MahalanobisParams', 'CalibrationProfile',
                  'DEFAULT_SCORER_WEIGHTS', 'WEIGHT_CONSTRAINTS', 'DEFAULT_THRESHOLDS',
                  'PERCENTILE_DEFAULTS', 'MIN_SAMPLE_SIZES', 'ISOLATION_FOREST_DEFAULTS',
                  'CONTAMINATION_BY_ENV', 'ANOMALY_FEATURES', 'FEATURE_NORMALIZATION',
                  'DRIFT_INDICATORS', 'DRIFT_RESPONSES', 'MIGRATION_CRITERIA',
                  'REPRODUCIBILITY_TARGET', 'ONLINE_ADJUSTMENT_LIMITS', 'CALIBRATION_TRIGGERS',
                  'normalize_feature', 'calculate_ewma', 'calculate_uncertainty_score'):
        from src.core.calibration import (
            CalibrationPipeline,
            CalibrationResult,
            ThresholdVersion,
            DriftIndicators,
            MahalanobisParams,
            CalibrationProfile,
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
            normalize_feature,
            calculate_ewma,
            calculate_uncertainty_score,
        )
        return eval(name)
    # Replay
    elif name in ('ReplayEngine', 'ReplayResult'):
        from src.core.replay import ReplayEngine, ReplayResult
        return eval(name)
    # Audit
    elif name in ('audit_logger', 'log_state_transition', 'log_hard_override',
                  'log_sla_timeout', 'log_late_hard_fail', 'log_checkpoint_rollback'):
        from src.core.audit import (
            audit_logger,
            log_state_transition,
            log_hard_override,
            log_sla_timeout,
            log_late_hard_fail,
            log_checkpoint_rollback
        )
        return eval(name)
    # Hard overrides
    elif name in ('apply_hard_overrides', 'check_hard_override_ho02',
                  'HO01_SECRET_FOUND', 'HO02_PROD_WRITE_TABOO_WARN',
                  'HO03_HIGH_PRIVILEGE_UNCERTAIN', 'HO04_SAST_HIGH',
                  'HO05_TOOL_POLICY_DENY'):
        from src.core.hard_overrides import (
            apply_hard_overrides,
            check_hard_override_ho02,
            HO01_SECRET_FOUND,
            HO02_PROD_WRITE_TABOO_WARN,
            HO03_HIGH_PRIVILEGE_UNCERTAIN,
            HO04_SAST_HIGH,
            HO05_TOOL_POLICY_DENY
        )
        return eval(name)
    # SLA handling
    elif name in ('SLAHandler', 'calculate_sla_deadlines',
                  'check_sla_timeout', 'handle_sla_timeout'):
        from src.core.sla_handler import (
            SLAHandler,
            calculate_sla_deadlines,
            check_sla_timeout,
            handle_sla_timeout
        )
        return eval(name)
    # Threshold versioning
    elif name in ('ThresholdVersionManager', 'ThresholdReplayContext', 'replay_with_version'):
        from src.core.threshold_versioning import (
            ThresholdVersionManager,
            ThresholdReplayContext,
            replay_with_version
        )
        return eval(name)
    # Self-correction
    elif name in ('SelfCorrectionTracker', 'track_self_correction',
                  'check_persistent_factor_escalation'):
        from src.core.self_correction import (
            SelfCorrectionTracker,
            track_self_correction,
            check_persistent_factor_escalation
        )
        return eval(name)
    # Exceptions
    elif name in ('GateEvaluationError', 'CalibrationError', 'InsufficientSamplesError',
                  'WeightValidationError', 'ThresholdError', 'ThresholdNotFoundError',
                  'InvalidThresholdError', 'DriftDetectionError', 'EmptyDistributionError',
                  'VectorDimensionMismatchError', 'MatrixSingularError', 'VersionError',
                  'InvalidVersionStringError', 'VersionLockError', 'MigrationValidationError',
                  'ReproducibilityError', 'ReviewQueueError', 'ItemNotFoundError', 'PairNotFoundError'):
        from src.core.exceptions import (
            GateEvaluationError,
            CalibrationError,
            InsufficientSamplesError,
            WeightValidationError,
            ThresholdError,
            ThresholdNotFoundError,
            InvalidThresholdError,
            DriftDetectionError,
            EmptyDistributionError,
            VectorDimensionMismatchError,
            MatrixSingularError,
            VersionError,
            InvalidVersionStringError,
            VersionLockError,
            MigrationValidationError,
            ReproducibilityError,
            ReviewQueueError,
            ItemNotFoundError,
            PairNotFoundError,
        )
        return eval(name)
    raise AttributeError(f"module {__name__} has no attribute {name}")