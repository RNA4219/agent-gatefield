"""
Unit tests for Calibration Profile Manager (AGF-REQ-007).

Tests percentile threshold calculation, scorer weight validation,
threshold version generation, reproducibility verification,
drift detection, online calibration, and Mahalanobis distance.

Coverage target: 85%
"""

import pytest
import math
from datetime import datetime
from typing import Dict, List

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
    DRIFT_INDICATORS,
    DRIFT_RESPONSES,
    MIGRATION_CRITERIA,
    REPRODUCIBILITY_TARGET,
    ONLINE_ADJUSTMENT_LIMITS,
    CALIBRATION_TRIGGERS,
    ANOMALY_FEATURES,
    normalize_feature,
    calculate_ewma,
    calculate_uncertainty_score,
)
from src.core.exceptions import (
    CalibrationError,
    InsufficientSamplesError,
    WeightValidationError,
    EmptyDistributionError,
    MatrixSingularError,
    InvalidVersionStringError,
)


# =============================================================================
# Constants Validation Tests
# =============================================================================

class TestConstants:
    """Test calibration constants are valid."""

    def test_default_weights_sum_to_one(self):
        """Weights must sum to 1.0 per WEIGHT_CONSTRAINTS."""
        total = sum(DEFAULT_SCORER_WEIGHTS.values())
        assert math.isclose(total, WEIGHT_CONSTRAINTS["sum"], rel_tol=1e-6)

    def test_all_weights_within_constraints(self):
        """Each weight must be between min_weight and max_weight."""
        for name, weight in DEFAULT_SCORER_WEIGHTS.items():
            if name != "uncertainty":  # uncertainty has fixed value
                assert weight >= WEIGHT_CONSTRAINTS["min_weight"], \
                    f"{name} weight {weight} below minimum"
                assert weight <= WEIGHT_CONSTRAINTS["max_weight"], \
                    f"{name} weight {weight} exceeds maximum"

    def test_uncertainty_weight_is_fixed(self):
        """Uncertainty weight should be fixed for escalation path."""
        assert DEFAULT_SCORER_WEIGHTS["uncertainty"] == WEIGHT_CONSTRAINTS["uncertainty_fixed"]

    def test_weight_constraints_valid(self):
        """Weight constraints must be logical."""
        assert WEIGHT_CONSTRAINTS["min_weight"] > 0
        assert WEIGHT_CONSTRAINTS["max_weight"] < 1.0
        assert WEIGHT_CONSTRAINTS["min_weight"] < WEIGHT_CONSTRAINTS["max_weight"]
        assert WEIGHT_CONSTRAINTS["taboo_min_weight"] >= WEIGHT_CONSTRAINTS["min_weight"]

    def test_percentile_defaults_valid(self):
        """Percentile defaults should be standard values."""
        assert PERCENTILE_DEFAULTS["warn"] == 95
        assert PERCENTILE_DEFAULTS["block"] == 99
        assert PERCENTILE_DEFAULTS["warn"] < PERCENTILE_DEFAULTS["block"]

    def test_min_sample_sizes_valid(self):
        """Minimum sample sizes must be positive integers."""
        for axis, sizes in MIN_SAMPLE_SIZES.items():
            for key, value in sizes.items():
                if value is not None:
                    assert value > 0, f"{axis}.{key} must be positive"
                    assert isinstance(value, int), f"{axis}.{key} must be integer"

    def test_isolation_forest_defaults_valid(self):
        """Isolation Forest defaults must be valid ranges."""
        assert ISOLATION_FOREST_DEFAULTS["contamination_range"][0] < \
               ISOLATION_FOREST_DEFAULTS["contamination_range"][1]
        assert ISOLATION_FOREST_DEFAULTS["n_estimators_range"][0] < \
               ISOLATION_FOREST_DEFAULTS["n_estimators_range"][1]

    def test_contamination_by_env_ordering(self):
        """Production should be most conservative (lowest contamination)."""
        assert CONTAMINATION_BY_ENV["production"] < CONTAMINATION_BY_ENV["staging"]
        assert CONTAMINATION_BY_ENV["staging"] < CONTAMINATION_BY_ENV["development"]

    def test_reproducibility_target(self):
        """Reproducibility target must be 99%."""
        assert REPRODUCIBILITY_TARGET == 0.99

    def test_drift_indicator_thresholds_valid(self):
        """Drift indicator thresholds must be sensible."""
        assert DRIFT_INDICATORS["score_mean_shift"] > 0
        assert DRIFT_INDICATORS["score_variance_shift_high"] > 1.0
        assert DRIFT_INDICATORS["score_variance_shift_low"] < 1.0
        assert DRIFT_INDICATORS["override_rate"] > 0

    def test_online_adjustment_limits_valid(self):
        """Online adjustment limits must be small increments."""
        assert ONLINE_ADJUSTMENT_LIMITS["threshold_step"] <= 0.05
        assert ONLINE_ADJUSTMENT_LIMITS["weight_step"] <= 0.02
        assert ONLINE_ADJUSTMENT_LIMITS["contamination_step"] <= 0.005


# =============================================================================
# ThresholdVersion Tests
# =============================================================================

class TestThresholdVersion:
    """Test threshold version generation and parsing."""

    def test_version_string_format(self):
        """Version string must match format threshold-v{major}.{minor}-{date}."""
        version = ThresholdVersion(major=1, minor=0, timestamp=datetime(2026, 4, 26))
        version_str = str(version)
        assert version_str.startswith("threshold-v")
        assert "1.0" in version_str
        assert "20260426" in version_str

    def test_version_parse_valid(self):
        """Parse valid version string."""
        version_str = "threshold-v1.2-20260426"
        version = ThresholdVersion.parse(version_str)
        assert version.major == 1
        assert version.minor == 2
        assert version.timestamp.year == 2026
        assert version.timestamp.month == 4
        assert version.timestamp.day == 26

    def test_version_parse_no_minor(self):
        """Parse version string without minor version."""
        version_str = "threshold-v2-20260115"
        version = ThresholdVersion.parse(version_str)
        assert version.major == 2
        assert version.minor == 0

    def test_version_parse_invalid_format(self):
        """Invalid version string raises InvalidVersionStringError."""
        with pytest.raises(InvalidVersionStringError):
            ThresholdVersion.parse("invalid-format")

    def test_version_parse_wrong_prefix(self):
        """Version string without 'threshold' prefix raises InvalidVersionStringError."""
        with pytest.raises(InvalidVersionStringError):
            ThresholdVersion.parse("v1.0-20260426")


# =============================================================================
# CalibrationResult Tests
# =============================================================================

class TestCalibrationResult:
    """Test calibration result data class."""

    def test_calibration_result_fields(self):
        """CalibrationResult must have all required fields."""
        result = CalibrationResult(
            axis="taboo",
            old_threshold=0.80,
            new_threshold=0.85,
            sample_size=100,
            metric_name="accepted_p95",
            metric_value=0.85
        )
        assert result.axis == "taboo"
        assert result.old_threshold == 0.80
        assert result.new_threshold == 0.85
        assert result.sample_size == 100
        assert result.metric_name == "accepted_p95"
        assert result.metric_value == 0.85


# =============================================================================
# DriftIndicators Tests
# =============================================================================

class TestDriftIndicators:
    """Test drift indicators data class."""

    def test_drift_indicators_defaults(self):
        """DriftIndicators default values."""
        indicators = DriftIndicators()
        assert indicators.score_mean_shift == 0.0
        assert indicators.score_variance_shift == 1.0
        assert indicators.threshold_crossing_rate == 1.0
        assert indicators.override_rate == 0.0
        assert indicators.alert_triggered == False
        assert indicators.drift_type is None

    def test_drift_indicators_with_values(self):
        """DriftIndicators with custom values."""
        indicators = DriftIndicators(
            score_mean_shift=0.7,
            score_variance_shift=1.3,
            threshold_crossing_rate=1.5,
            override_rate=0.08,
            alert_triggered=True,
            drift_type="score_inflation"
        )
        assert indicators.score_mean_shift == 0.7
        assert indicators.alert_triggered == True
        assert indicators.drift_type == "score_inflation"


# =============================================================================
# MahalanobisParams Tests
# =============================================================================

class TestMahalanobisParams:
    """Test Mahalanobis parameters data class."""

    def test_mahalanobis_params_to_dict(self):
        """MahalanobisParams serialization."""
        params = MahalanobisParams(
            mean=[1.0, 2.0],
            covariance_inverse=[[1.0, 0.0], [0.0, 1.0]],
            warn_distance=3.0,
            block_distance=5.0,
            regularization_lambda=1e-6
        )
        d = params.to_dict()
        assert d["mean"] == [1.0, 2.0]
        assert d["warn_distance"] == 3.0
        assert d["block_distance"] == 5.0
        assert d["regularization_lambda"] == 1e-6


# =============================================================================
# CalibrationProfile Tests
# =============================================================================

class TestCalibrationProfile:
    """Test calibration profile data class."""

    def test_calibration_profile_creation(self):
        """CalibrationProfile with all fields."""
        version = ThresholdVersion(major=1, minor=0, timestamp=datetime.now())
        profile = CalibrationProfile(
            profile_id="test-profile",
            scope="repo",
            threshold_version=version,
            weights=DEFAULT_SCORER_WEIGHTS.copy(),
            warn_thresholds={"taboo": 0.80},
            block_thresholds={"taboo": 0.88}
        )
        assert profile.profile_id == "test-profile"
        assert profile.scope == "repo"
        assert profile.weights["taboo_proximity"] == 0.30

    def test_calibration_profile_to_dict(self):
        """CalibrationProfile serialization."""
        version = ThresholdVersion(major=1, minor=0, timestamp=datetime(2026, 4, 26))
        profile = CalibrationProfile(
            profile_id="test-profile",
            scope="repo",
            threshold_version=version
        )
        d = profile.to_dict()
        assert d["profile_id"] == "test-profile"
        assert d["threshold_version"] == str(version)
        assert "weights" in d


# =============================================================================
# CalibrationPipeline - Percentile Threshold Tests (P95, P99)
# =============================================================================

class TestPercentileThresholdCalculation:
    """Test percentile-based threshold calculation (P95, P99)."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_calibrate_taboo_threshold_p95(self, pipeline):
        """Calibrate taboo threshold at P95 from accepted distribution."""
        # Generate 100 accepted scores
        accepted_scores = [i * 0.01 for i in range(100)]  # 0.00 to 0.99

        result = pipeline.calibrate_taboo_threshold(accepted_scores, percentile=95)

        assert result.axis == "taboo"
        assert result.metric_name == "accepted_p95"
        # P95 of 100 samples sorted: index 95 -> value 0.95
        assert math.isclose(result.new_threshold, 0.95, rel_tol=0.01)
        assert result.sample_size == 100

    def test_calibrate_taboo_threshold_p99(self, pipeline):
        """Calibrate taboo threshold at P99 from accepted distribution."""
        accepted_scores = [i * 0.01 for i in range(100)]

        result = pipeline.calibrate_taboo_threshold(accepted_scores, percentile=99)

        assert result.metric_name == "accepted_p99"
        # P99 of 100 samples: index 99 -> value 0.99
        assert math.isclose(result.new_threshold, 0.99, rel_tol=0.01)

    def test_calibrate_taboo_insufficient_samples(self, pipeline):
        """Insufficient samples raises InsufficientSamplesError."""
        accepted_scores = [0.1, 0.2, 0.3]  # Only 3 samples

        with pytest.raises(InsufficientSamplesError) as exc_info:
            pipeline.calibrate_taboo_threshold(accepted_scores)

        assert "Insufficient samples" in str(exc_info.value)

    def test_calibrate_drift_threshold_p95_p99(self, pipeline):
        """Calibrate drift thresholds at P95 warn and P99 block."""
        # Generate 50 drift scores
        drift_scores = [i * 0.02 for i in range(50)]  # 0.00 to 0.98

        results = pipeline.calibrate_drift_threshold(
            drift_scores, warn_percentile=95, block_percentile=99
        )

        assert "warn" in results
        assert "block" in results

        # P95 of 50: index 47 -> value 0.94
        assert math.isclose(results["warn"].new_threshold, 0.94, rel_tol=0.02)
        # P99 of 50: index 49 -> value 0.98
        assert math.isclose(results["block"].new_threshold, 0.98, rel_tol=0.02)

    def test_calibrate_drift_insufficient_samples(self, pipeline):
        """Insufficient drift samples raises InsufficientSamplesError."""
        drift_scores = [0.1, 0.2]  # Only 2 samples

        with pytest.raises(InsufficientSamplesError) as exc_info:
            pipeline.calibrate_drift_threshold(drift_scores)

        assert "Insufficient samples" in str(exc_info.value)

    def test_calibrate_anomaly_percentile(self, pipeline):
        """Calibrate anomaly thresholds at P95/P99."""
        # Generate 200 anomaly scores
        anomaly_scores = [i * 0.005 for i in range(200)]  # 0.00 to 0.995

        result = pipeline.calibrate_anomaly_percentile(
            anomaly_scores, warn_percentile=95, block_percentile=99
        )

        assert result["warn_percentile"] == 95
        assert result["block_percentile"] == 99
        assert result["sample_size"] == 200
        # P95 of 200: index 190 -> value 0.95
        assert math.isclose(result["warn_threshold"], 0.95, rel_tol=0.01)
        # P99 of 200: index 198 -> value 0.99
        assert math.isclose(result["block_threshold"], 0.99, rel_tol=0.01)

    def test_calibrate_anomaly_insufficient_samples(self, pipeline):
        """Insufficient anomaly samples raises InsufficientSamplesError."""
        anomaly_scores = [i * 0.01 for i in range(50)]  # Only 50

        with pytest.raises(InsufficientSamplesError) as exc_info:
            pipeline.calibrate_anomaly_percentile(anomaly_scores)

        assert "Insufficient samples" in str(exc_info.value)

    def test_calibrate_constitution_threshold(self, pipeline):
        """Calibrate constitution alignment threshold (safe-side scorer)."""
        # For safe-side, lower scores are riskier
        accepted_scores = [i * 0.01 for i in range(100)]

        results = pipeline.calibrate_constitution_threshold(
            accepted_scores, warn_percentile=5, block_percentile=1
        )

        assert "warn" in results
        assert "block" in results

        # P5 of 100: index 5 -> value 0.05
        assert math.isclose(results["warn"].new_threshold, 0.05, rel_tol=0.01)
        # P1 of 100: index 1 -> value 0.01
        assert math.isclose(results["block"].new_threshold, 0.01, rel_tol=0.01)


# =============================================================================
# CalibrationPipeline - Weight Validation Tests
# =============================================================================

class TestWeightValidation:
    """Test scorer weight validation."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_validate_weights_sum_to_one(self, pipeline):
        """Weights must sum to 1.0."""
        weights = {
            "constitution_alignment": 0.20,
            "taboo_proximity": 0.30,
            "accept_similarity": 0.10,
            "reject_similarity": 0.15,
            "drift": 0.10,
            "anomaly": 0.10,
            "uncertainty": 0.05
        }
        # Should pass
        assert pipeline._validate_weights(weights) == True

    def test_validate_weights_invalid_sum(self, pipeline):
        """Weights not summing to 1.0 raises WeightValidationError."""
        weights = {
            "constitution_alignment": 0.30,
            "taboo_proximity": 0.30,
            "accept_similarity": 0.20
        }

        with pytest.raises(WeightValidationError) as exc_info:
            pipeline._validate_weights(weights)

        assert "sum to" in str(exc_info.value).lower()

    def test_validate_weights_below_minimum(self, pipeline):
        """Weight below minimum raises WeightValidationError."""
        weights = DEFAULT_SCORER_WEIGHTS.copy()
        # Reduce taboo to below minimum, increase another to keep sum = 1.0
        weights["taboo_proximity"] = 0.01  # Below 0.05
        weights["constitution_alignment"] = 0.49  # Compensate to keep sum = 1.0

        with pytest.raises(WeightValidationError) as exc_info:
            pipeline._validate_weights(weights)

        assert "below minimum" in str(exc_info.value)

    def test_validate_weights_above_maximum(self, pipeline):
        """Weight above maximum raises WeightValidationError."""
        # Create weights that sum to 1.0 but have taboo above maximum
        weights = {
            "constitution_alignment": 0.24,
            "taboo_proximity": 0.51,  # Above 0.50 maximum
            "accept_similarity": 0.05,
            "reject_similarity": 0.05,
            "drift": 0.05,
            "anomaly": 0.05,
            "uncertainty": 0.05
        }
        # Sum = 0.24 + 0.51 + 0.05 + 0.05 + 0.05 + 0.05 + 0.05 = 1.00

        with pytest.raises(WeightValidationError) as exc_info:
            pipeline._validate_weights(weights)

        assert "exceeds maximum" in str(exc_info.value)

    def test_create_profile_with_valid_weights(self, pipeline):
        """Create profile with valid custom weights."""
        custom_weights = DEFAULT_SCORER_WEIGHTS.copy()
        custom_weights["taboo_proximity"] = 0.35
        custom_weights["drift"] = 0.05

        profile = pipeline.create_profile(weights=custom_weights)

        assert profile.weights["taboo_proximity"] == 0.35

    def test_create_profile_with_invalid_weights(self, pipeline):
        """Create profile with invalid weights raises WeightValidationError."""
        invalid_weights = {"taboo_proximity": 0.99}  # Sum not 1.0

        with pytest.raises(WeightValidationError):
            pipeline.create_profile(weights=invalid_weights)

    def test_compute_weighted_score(self, pipeline):
        """Compute composite weighted score."""
        scores = {
            "constitution_alignment": 0.8,
            "taboo_proximity": 0.2,
            "accept_similarity": 0.9,
            "reject_similarity": 0.1,
            "drift": 0.3,
            "anomaly": 0.2,
            "uncertainty": 0.4
        }

        composite = pipeline.compute_weighted_score(scores)

        # Expected: 0.8*0.20 + 0.2*0.30 + 0.9*0.10 + 0.1*0.15 + 0.3*0.10 + 0.2*0.10 + 0.4*0.05
        # = 0.16 + 0.06 + 0.09 + 0.015 + 0.03 + 0.02 + 0.02 = 0.395
        assert math.isclose(composite, 0.395, rel_tol=0.001)

    def test_compute_weighted_score_partial_scores(self, pipeline):
        """Weighted score with partial scorer results."""
        scores = {"taboo_proximity": 0.5, "drift": 0.3}

        composite = pipeline.compute_weighted_score(scores)

        # Only counts available scorers: 0.5*0.30 + 0.3*0.10 = 0.15 + 0.03 = 0.18
        assert math.isclose(composite, 0.18, rel_tol=0.001)


# =============================================================================
# CalibrationPipeline - Threshold Version Generation Tests
# =============================================================================

class TestThresholdVersionGeneration:
    """Test threshold version generation."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_generate_threshold_version(self, pipeline):
        """Generate threshold version identifier."""
        version = pipeline.generate_threshold_version(major=1, minor=0)

        assert version.major == 1
        assert version.minor == 0
        assert isinstance(version.timestamp, datetime)

    def test_generate_threshold_version_custom(self, pipeline):
        """Generate custom version."""
        version = pipeline.generate_threshold_version(major=2, minor=3)

        assert version.major == 2
        assert version.minor == 3

    def test_generate_threshold_version_format(self, pipeline):
        """Version string format is correct."""
        version = pipeline.generate_threshold_version(major=1, minor=5)
        version_str = str(version)

        assert "threshold-v1.5" in version_str


# =============================================================================
# CalibrationPipeline - Reproducibility Verification Tests (99% target)
# =============================================================================

class TestReproducibilityVerification:
    """Test reproducibility verification (99% target)."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_verify_reproducibility_exact_match(self, pipeline):
        """100% match passes reproducibility check."""
        original = ["pass", "pass", "block", "warn", "pass"]
        replay = ["pass", "pass", "block", "warn", "pass"]

        result = pipeline.verify_reproducibility(original, replay)

        assert result["passed"] == True
        assert result["match_rate"] == 1.0
        assert result["matches"] == 5
        assert result["total"] == 5

    def test_verify_reproducibility_99_percent_match(self, pipeline):
        """99% match meets threshold."""
        # 100 decisions, 1 divergence = 99% match
        original = ["pass"] * 99 + ["block"]
        replay = ["pass"] * 99 + ["pass"]  # One block -> pass

        result = pipeline.verify_reproducibility(original, replay)

        assert result["passed"] == True
        assert math.isclose(result["match_rate"], 0.99, rel_tol=0.001)

    def test_verify_reproducibility_below_threshold(self, pipeline):
        """Below 99% fails reproducibility check."""
        original = ["pass"] * 98 + ["block", "block"]
        replay = ["pass"] * 100  # Two blocks became pass

        result = pipeline.verify_reproducibility(original, replay)

        assert result["passed"] == False
        assert result["match_rate"] == 0.98

    def test_verify_reproducibility_critical_divergences(self, pipeline):
        """pass_to_block divergences are critical."""
        original = ["pass", "pass", "pass"]
        replay = ["block", "pass", "block"]  # Two pass -> block

        result = pipeline.verify_reproducibility(original, replay)

        assert len(result["critical_divergences"]) > 0
        assert result["critical_divergences"][0]["type"] == "pass_to_block"
        assert "Security review required" in \
               result["critical_divergences"][0]["action_required"]

    def test_verify_reproducibility_block_to_pass_critical(self, pipeline):
        """block_to_pass divergences require justification."""
        original = ["block", "pass", "block"]
        replay = ["pass", "pass", "pass"]

        result = pipeline.verify_reproducibility(original, replay)

        critical = result["critical_divergences"]
        block_to_pass_found = any(d["type"] == "block_to_pass" for d in critical)
        assert block_to_pass_found

    def test_verify_reproducibility_mismatched_length(self, pipeline):
        """Mismatched decision lists raises CalibrationError."""
        original = ["pass", "pass"]
        replay = ["pass"]

        with pytest.raises(CalibrationError) as exc_info:
            pipeline.verify_reproducibility(original, replay)

        assert "equal length" in str(exc_info.value)

    def test_verify_reproducibility_empty_lists(self, pipeline):
        """Empty decision lists return 0% match."""
        result = pipeline.verify_reproducibility([], [])

        # Empty lists should have 0% match rate (or handle specially)
        assert result["match_rate"] == 0.0
        assert result["total"] == 0

    def test_verify_reproducibility_custom_tolerance(self, pipeline):
        """Custom tolerance can be specified."""
        original = ["pass"] * 95 + ["block"] * 5
        replay = ["pass"] * 100

        # 95% match should pass with 95% tolerance
        result = pipeline.verify_reproducibility(original, replay, tolerance=0.95)
        assert result["passed"] == True

        # But fail with 99% tolerance
        result = pipeline.verify_reproducibility(original, replay, tolerance=0.99)
        assert result["passed"] == False


# =============================================================================
# CalibrationPipeline - Drift Detection Tests
# =============================================================================

class TestDriftDetection:
    """Test drift detection indicators."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_compute_drift_no_drift(self, pipeline):
        """No drift when distributions match."""
        baseline = [0.5, 0.55, 0.6, 0.55, 0.5]  # mean ~0.54
        current = [0.5, 0.55, 0.6, 0.55, 0.5]  # identical

        indicators = pipeline.compute_drift_indicators(
            current, baseline, axis="taboo"
        )

        assert indicators.score_mean_shift < DRIFT_INDICATORS["score_mean_shift"]
        assert indicators.alert_triggered == False

    def test_compute_drift_mean_shift_detected(self, pipeline):
        """Drift detected when mean shifts significantly."""
        baseline = [0.5, 0.5, 0.5, 0.5, 0.5]  # mean 0.5, std 0
        # Actually need some variance for std calculation
        baseline = [0.4, 0.5, 0.5, 0.5, 0.6]  # mean 0.5, std ~0.07

        current = [0.7, 0.8, 0.75, 0.8, 0.85]  # mean ~0.78

        indicators = pipeline.compute_drift_indicators(
            current, baseline, axis="taboo"
        )

        # Mean shift should be large: (0.78 - 0.5) / 0.07 ~ 4
        assert indicators.score_mean_shift > DRIFT_INDICATORS["score_mean_shift"]
        assert indicators.alert_triggered == True
        assert indicators.drift_type in ["score_inflation", "score_deflation"]

    def test_compute_drift_variance_shift_high(self, pipeline):
        """Drift detected when variance increases significantly."""
        baseline = [0.5, 0.5, 0.5, 0.5, 0.5]  # low variance
        # Need actual variance
        baseline = [0.49, 0.50, 0.50, 0.50, 0.51]  # std ~0.007

        current = [0.2, 0.3, 0.5, 0.7, 0.9]  # much higher variance

        indicators = pipeline.compute_drift_indicators(
            current, baseline, axis="drift"
        )

        # Variance ratio should be > 1.5
        assert indicators.score_variance_shift > DRIFT_INDICATORS["score_variance_shift_high"]

    def test_compute_drift_variance_shift_low(self, pipeline):
        """Drift detected when variance decreases significantly."""
        baseline = [0.2, 0.4, 0.6, 0.5, 0.3]  # moderate variance
        current = [0.50, 0.50, 0.50, 0.50, 0.50]  # very low variance

        indicators = pipeline.compute_drift_indicators(
            current, baseline, axis="taboo"
        )

        # Variance ratio should be < 0.67
        assert indicators.score_variance_shift < DRIFT_INDICATORS["score_variance_shift_low"]

    def test_compute_drift_override_rate(self, pipeline):
        """High override rate triggers drift alert."""
        baseline = [0.5] * 10
        current = [0.5] * 10

        indicators = pipeline.compute_drift_indicators(
            current, baseline, axis="taboo", override_rate=0.10
        )

        # Override rate 10% > threshold 5%
        assert indicators.override_rate > DRIFT_INDICATORS["override_rate"]
        assert indicators.alert_triggered == True
        assert indicators.drift_type == "threshold_decay"

    def test_compute_drift_threshold_crossing_rate(self, pipeline):
        """High threshold crossing rate triggers drift."""
        baseline = [0.5] * 10
        current = [0.5] * 10

        indicators = pipeline.compute_drift_indicators(
            current, baseline, axis="taboo",
            threshold_crossing_rate=1.5
        )

        # Crossing rate 1.5 > threshold 1.2
        assert indicators.threshold_crossing_rate > DRIFT_INDICATORS["threshold_crossing_rate"]
        assert indicators.alert_triggered == True

    def test_compute_drift_empty_current_raises(self, pipeline):
        """Empty current scores raises EmptyDistributionError."""
        with pytest.raises(EmptyDistributionError):
            pipeline.compute_drift_indicators([], [0.5, 0.6], axis="taboo")

    def test_compute_drift_empty_baseline_raises(self, pipeline):
        """Empty baseline scores raises EmptyDistributionError."""
        with pytest.raises(EmptyDistributionError):
            pipeline.compute_drift_indicators([0.5, 0.6], [], axis="taboo")

    def test_get_drift_response(self, pipeline):
        """Get recommended response for drift type."""
        response = pipeline.get_drift_response("score_inflation")
        assert "Re-embed" in response or "recalibrate" in response.lower()

        response = pipeline.get_drift_response("threshold_decay")
        assert "Review" in response or "adjust" in response.lower()

        response = pipeline.get_drift_response("unknown_type")
        assert "Investigate" in response


# =============================================================================
# CalibrationPipeline - Online Calibration Tests
# =============================================================================

class TestOnlineCalibration:
    """Test online calibration from corrections."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_incorporate_correction_pass_to_block(self, pipeline):
        """Pass overridden to block means threshold too loose."""
        result = pipeline.incorporate_correction(
            "pass_to_block", current_threshold=0.80
        )

        # Should tighten threshold (negative adjustment)
        assert result["threshold_adjustment"] < 0
        assert result["action"] == "tighten_threshold"

    def test_incorporate_correction_block_to_pass(self, pipeline):
        """Block overridden to pass means threshold too tight."""
        result = pipeline.incorporate_correction(
            "block_to_pass", current_threshold=0.80
        )

        # Should loosen threshold (positive adjustment)
        assert result["threshold_adjustment"] > 0
        assert result["action"] == "loosen_threshold"

    def test_incorporate_correction_threshold_adjust(self, pipeline):
        """Direct threshold adjustment."""
        result = pipeline.incorporate_correction(
            "threshold_adjust", current_threshold=0.80
        )

        assert result["action"] == "direct_threshold_modification"

    def test_incorporate_correction_weight_adjust(self, pipeline):
        """Weight adjustment action."""
        result = pipeline.incorporate_correction(
            "weight_adjust", current_threshold=0.80
        )

        assert result["action"] == "profile_weight_update"

    def test_incorporate_correction_adjustment_limits(self, pipeline):
        """Adjustment is within allowed limits."""
        result = pipeline.incorporate_correction(
            "pass_to_block", current_threshold=0.80
        )

        assert abs(result["threshold_adjustment"]) <= \
               ONLINE_ADJUSTMENT_LIMITS["threshold_step"]

    def test_check_calibration_trigger_no_trigger(self, pipeline):
        """No trigger when override rate is low."""
        result = pipeline.check_calibration_trigger(
            override_count=3, total_decisions=100
        )

        # Override rate 3% < threshold 5%
        assert result["triggered"] == False
        assert result["override_rate"] == 0.03

    def test_check_calibration_trigger_override_surge(self, pipeline):
        """Trigger when override rate exceeds threshold."""
        result = pipeline.check_calibration_trigger(
            override_count=10, total_decisions=100
        )

        # Override rate 10% > threshold 5%
        assert result["triggered"] == True
        assert len(result["triggers"]) > 0
        assert result["triggers"][0]["type"] == "override_surge"
        assert result["recommended_action"] == "schedule_recalibration"

    def test_check_calibration_trigger_zero_decisions(self, pipeline):
        """Handle zero total decisions."""
        result = pipeline.check_calibration_trigger(
            override_count=0, total_decisions=0
        )

        assert result["override_rate"] == 0.0
        assert result["triggered"] == False


# =============================================================================
# CalibrationPipeline - Mahalanobis Distance Tests
# =============================================================================

class TestMahalanobisDistance:
    """Test Mahalanobis distance calculation."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_calibrate_mahalanobis_basic(self, pipeline):
        """Basic Mahalanobis calibration."""
        # Simple 2D features
        features = [
            [1.0, 2.0],
            [1.1, 2.1],
            [0.9, 1.9],
            [1.0, 2.0],
            [1.2, 2.2]
        ]

        params = pipeline.calibrate_mahalanobis(features)

        assert len(params.mean) == 2
        assert len(params.covariance_inverse) == 2
        assert params.warn_distance is not None
        assert params.block_distance is not None

    def test_calibrate_mahalanobis_mean_calculation(self, pipeline):
        """Mean is calculated correctly."""
        features = [
            [1.0, 2.0],
            [3.0, 4.0],
            [5.0, 6.0]
        ]

        params = pipeline.calibrate_mahalanobis(features)

        # Mean should be [3.0, 4.0]
        assert math.isclose(params.mean[0], 3.0, rel_tol=0.01)
        assert math.isclose(params.mean[1], 4.0, rel_tol=0.01)

    def test_calibrate_mahalanobis_distance_ordering(self, pipeline):
        """Block distance >= warn distance."""
        features = [
            [i * 0.1, i * 0.1] for i in range(20)
        ]

        params = pipeline.calibrate_mahalanobis(
            features, warn_percentile=95, block_percentile=99
        )

        assert params.block_distance >= params.warn_distance

    def test_calibrate_mahalanobis_empty_features(self, pipeline):
        """Empty features raises CalibrationError."""
        with pytest.raises(CalibrationError) as exc_info:
            pipeline.calibrate_mahalanobis([])

        assert "No accepted features" in str(exc_info.value)

    def test_calibrate_mahalanobis_regularization(self, pipeline):
        """Regularization lambda is applied."""
        # Need at least 2 samples for covariance calculation (n-1 > 0)
        features = [[1.0, 2.0], [1.1, 2.1]]

        # Should work with regularization
        params = pipeline.calibrate_mahalanobis(
            features, regularization_lambda=1e-3
        )

        assert params.regularization_lambda == 1e-3

    def test_mahalanobis_distance_calculation(self, pipeline):
        """Internal distance calculation is correct."""
        mean = [0.0, 0.0]
        cov_inv = [[1.0, 0.0], [0.0, 1.0]]  # Identity

        # Distance for [3, 4] should be 5 (Euclidean with identity)
        distance = pipeline._mahalanobis_distance([3.0, 4.0], mean, cov_inv)
        assert math.isclose(distance, 5.0, rel_tol=0.01)

    def test_compute_anomaly_score(self, pipeline):
        """Anomaly score normalization."""
        # Distance 10 should give score 1.0 (max)
        score = pipeline.compute_anomaly_score(10.0)
        assert score == 1.0

        # Distance 5 should give score 0.5
        score = pipeline.compute_anomaly_score(5.0)
        assert math.isclose(score, 0.5, rel_tol=0.01)

        # Very large distance capped at 1.0
        score = pipeline.compute_anomaly_score(100.0)
        assert score == 1.0


# =============================================================================
# CalibrationPipeline - Isolation Forest Tests
# =============================================================================

class TestIsolationForestCalibration:
    """Test Isolation Forest calibration."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_calibrate_isolation_forest_environment(self, pipeline):
        """Contamination varies by environment."""
        scores = [i * 0.005 for i in range(200)]

        dev_config = pipeline.calibrate_isolation_forest(scores, "development")
        assert dev_config["contamination"] == CONTAMINATION_BY_ENV["development"]

        prod_config = pipeline.calibrate_isolation_forest(scores, "production")
        assert prod_config["contamination"] == CONTAMINATION_BY_ENV["production"]

        # Production should be most conservative
        assert prod_config["contamination"] < dev_config["contamination"]

    def test_calibrate_isolation_forest_defaults(self, pipeline):
        """Uses Isolation Forest defaults."""
        scores = [i * 0.01 for i in range(200)]

        config = pipeline.calibrate_isolation_forest(scores)

        assert config["n_estimators"] == ISOLATION_FOREST_DEFAULTS["n_estimators"]
        assert config["max_samples"] == ISOLATION_FOREST_DEFAULTS["max_samples"]

    def test_calibrate_isolation_forest_contamination_bounds(self, pipeline):
        """Contamination clamped to valid range."""
        scores = [i * 0.01 for i in range(200)]

        # Unknown environment should use default (staging = 0.01)
        config = pipeline.calibrate_isolation_forest(scores, "unknown_env")

        min_c, max_c = ISOLATION_FOREST_DEFAULTS["contamination_range"]
        assert config["contamination"] >= min_c
        assert config["contamination"] <= max_c


# =============================================================================
# CalibrationPipeline - Metrics Tests
# =============================================================================

class TestMetricsComputation:
    """Test metrics computation."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_compute_metrics_perfect(self, pipeline):
        """Perfect predictions give 1.0 metrics."""
        predictions = ["block", "block", "pass", "pass"]
        labels = ["block", "block", "pass", "pass"]

        metrics = pipeline.compute_metrics(predictions, labels)

        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1"] == 1.0
        assert metrics["tp"] == 2
        assert metrics["fp"] == 0
        assert metrics["tn"] == 2
        assert metrics["fn"] == 0

    def test_compute_metrics_with_fp(self, pipeline):
        """Metrics with false positives."""
        predictions = ["block", "block", "block", "pass"]  # 3 blocks predicted
        labels = ["block", "pass", "pass", "pass"]  # Only 1 actual block

        metrics = pipeline.compute_metrics(predictions, labels)

        assert metrics["tp"] == 1  # 1 correct block
        assert metrics["fp"] == 2  # 2 incorrect blocks
        assert metrics["precision"] == 1/3  # 1 / (1+2)

    def test_compute_metrics_with_fn(self, pipeline):
        """Metrics with false negatives."""
        predictions = ["pass", "pass", "pass", "block"]
        labels = ["block", "block", "pass", "block"]

        metrics = pipeline.compute_metrics(predictions, labels)

        assert metrics["fn"] == 2  # 2 missed blocks
        assert metrics["recall"] == 1/3  # 1 / (1+2)

    def test_compute_metrics_false_escalation(self, pipeline):
        """False escalation rate calculation."""
        predictions = ["block", "block", "pass", "pass"]  # 2 blocks
        labels = ["pass", "pass", "pass", "pass"]  # All pass

        metrics = pipeline.compute_metrics(predictions, labels)

        # False escalation = FP / total_pass = 2 / 4 = 0.5
        assert metrics["false_escalation"] == 0.5

    def test_compute_metrics_empty(self, pipeline):
        """Empty predictions return zero metrics."""
        metrics = pipeline.compute_metrics([], [])

        assert metrics["precision"] == 0.0
        assert metrics["recall"] == 0.0
        assert metrics["f1"] == 0.0

    def test_compute_auc_basic(self, pipeline):
        """AUC computation."""
        predictions = ["block", "block", "pass", "pass"]
        labels = ["block", "block", "pass", "pass"]
        scores = [0.9, 0.8, 0.3, 0.2]  # High scores for blocks

        metrics = pipeline.compute_metrics(predictions, labels, scores)

        # Perfect separation should give high AUC
        assert metrics["auc"] is not None
        assert metrics["auc"] > 0.9


# =============================================================================
# CalibrationPipeline - Migration Validation Tests
# =============================================================================

class TestMigrationValidation:
    """Test migration validation criteria."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_validate_migration_no_degradation(self, pipeline):
        """Migration with no degradation passes."""
        old_metrics = {"precision": 0.90, "recall": 0.85, "f1": 0.87, "false_escalation": 0.10}
        new_metrics = {"precision": 0.92, "recall": 0.88, "f1": 0.90, "false_escalation": 0.08}

        is_valid, violations = pipeline.validate_migration(old_metrics, new_metrics)

        assert is_valid == True
        assert len(violations) == 0

    def test_validate_migration_precision_degradation(self, pipeline):
        """Precision degradation beyond threshold fails."""
        old_metrics = {"precision": 0.90, "recall": 0.85, "f1": 0.87, "false_escalation": 0.10}
        new_metrics = {"precision": 0.80, "recall": 0.85, "f1": 0.82, "false_escalation": 0.10}

        is_valid, violations = pipeline.validate_migration(old_metrics, new_metrics)

        # 10% degradation > 5% threshold
        assert is_valid == False
        assert any("Precision" in v for v in violations)

    def test_validate_migration_recall_degradation(self, pipeline):
        """Recall degradation beyond threshold fails."""
        old_metrics = {"precision": 0.90, "recall": 0.90, "f1": 0.90, "false_escalation": 0.10}
        new_metrics = {"precision": 0.90, "recall": 0.82, "f1": 0.86, "false_escalation": 0.10}

        is_valid, violations = pipeline.validate_migration(old_metrics, new_metrics)

        # 8% degradation > 3% threshold
        assert is_valid == False
        assert any("Recall" in v for v in violations)

    def test_validate_migration_false_escalation_increase(self, pipeline):
        """False escalation increase beyond threshold fails."""
        old_metrics = {"precision": 0.90, "recall": 0.85, "f1": 0.87, "false_escalation": 0.10}
        new_metrics = {"precision": 0.90, "recall": 0.85, "f1": 0.87, "false_escalation": 0.20}

        is_valid, violations = pipeline.validate_migration(old_metrics, new_metrics)

        # 10% increase > 5% threshold
        assert is_valid == False
        assert any("False escalation" in v for v in violations)

    def test_validate_migration_within_threshold(self, pipeline):
        """Small degradation within threshold passes."""
        old_metrics = {"precision": 0.90, "recall": 0.90, "f1": 0.90, "false_escalation": 0.10}
        new_metrics = {"precision": 0.87, "recall": 0.89, "f1": 0.88, "false_escalation": 0.12}

        is_valid, violations = pipeline.validate_migration(old_metrics, new_metrics)

        # 3% precision, 1% recall, 2% F1, 2% FE - all within thresholds
        assert is_valid == True


# =============================================================================
# CalibrationPipeline - Profile Management Tests
# =============================================================================

class TestProfileManagement:
    """Test profile creation and management."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_create_profile_default(self, pipeline):
        """Create profile with default settings."""
        profile = pipeline.create_profile()

        assert profile.profile_id == "test-pipeline"
        assert profile.scope == "repo"
        assert profile.weights == DEFAULT_SCORER_WEIGHTS

    def test_create_profile_with_version(self, pipeline):
        """Create profile with custom version."""
        version = ThresholdVersion(major=2, minor=1, timestamp=datetime.now())
        profile = pipeline.create_profile(version=version)

        assert profile.threshold_version.major == 2
        assert profile.threshold_version.minor == 1

    def test_create_profile_anomaly_config(self, pipeline):
        """Profile includes anomaly detector config."""
        profile = pipeline.create_profile()

        assert profile.anomaly_detector_config is not None
        assert profile.anomaly_detector_config["type"] == "isolation_forest"
        assert "feature_set" in profile.anomaly_detector_config

    def test_get_effective_threshold_both_set(self, pipeline):
        """Effective threshold with both percentile and fixed."""
        percentile = 0.85
        fixed = 0.90

        # Risk-side: min
        result = pipeline.get_effective_threshold(percentile, fixed, is_risk_side=True)
        assert result == 0.85

        # Safe-side: max
        result = pipeline.get_effective_threshold(percentile, fixed, is_risk_side=False)
        assert result == 0.90

    def test_get_effective_threshold_one_set(self, pipeline):
        """Effective threshold with only one set."""
        percentile = 0.85

        result = pipeline.get_effective_threshold(percentile, None)
        assert result == 0.85

        result = pipeline.get_effective_threshold(None, 0.90)
        assert result == 0.90

    def test_get_effective_threshold_none(self, pipeline):
        """Effective threshold with neither set."""
        result = pipeline.get_effective_threshold(None, None)
        assert result is None

    def test_save_profile(self, pipeline):
        """Save profile returns dictionary."""
        profile_dict = pipeline.save_profile()

        assert profile_dict["profile_id"] == "test-pipeline"
        assert "updated_at" in profile_dict


# =============================================================================
# Utility Function Tests
# =============================================================================

class TestUtilityFunctions:
    """Test utility functions."""

    def test_normalize_feature_delta_semantic(self):
        """Normalize delta_semantic feature."""
        # Value 5 normalized to 0.5
        result = normalize_feature("delta_semantic", 5.0)
        assert math.isclose(result, 0.5, rel_tol=0.01)

        # Value 20 capped at 1.0
        result = normalize_feature("delta_semantic", 20.0)
        assert result == 1.0

    def test_normalize_feature_tool_calls(self):
        """Normalize tool_calls feature."""
        result = normalize_feature("tool_calls", 10)
        assert math.isclose(result, 0.5, rel_tol=0.01)

        result = normalize_feature("tool_calls", 30)
        assert result == 1.0

    def test_normalize_feature_error_rate(self):
        """Normalize error_rate (already normalized)."""
        result = normalize_feature("error_rate", 0.5)
        assert result == 0.5

    def test_normalize_feature_unknown(self):
        """Unknown feature returns original value."""
        result = normalize_feature("unknown_feature", 42.0)
        assert result == 42.0

    def test_calculate_ewma(self):
        """EWMA calculation."""
        alpha = 0.1
        current = 10.0
        old_ewma = 5.0

        result = calculate_ewma(current, old_ewma, alpha)

        # 0.1 * 10 + 0.9 * 5 = 1 + 4.5 = 5.5
        assert math.isclose(result, 5.5, rel_tol=0.001)

    def test_calculate_ewma_default_alpha(self):
        """EWMA with default alpha."""
        current = 10.0
        old_ewma = 0.0

        result = calculate_ewma(current, old_ewma)  # alpha=0.1

        # 0.1 * 10 + 0.9 * 0 = 1.0
        assert math.isclose(result, 1.0, rel_tol=0.001)

    def test_calculate_uncertainty_score(self):
        """Uncertainty score calculation."""
        # All components 0.5
        judge_std = 0.5
        self_confidence = 0.5
        tool_error_rate = 0.5
        evidence_gap = 0.5

        result = calculate_uncertainty_score(
            judge_std, self_confidence, tool_error_rate, evidence_gap
        )

        # 0.25 * 0.5 + 0.25 * (1-0.5) + 0.25 * 0.5 + 0.25 * 0.5 = 0.5
        assert math.isclose(result, 0.5, rel_tol=0.001)

    def test_calculate_uncertainty_score_high(self):
        """High uncertainty score."""
        result = calculate_uncertainty_score(
            judge_std=1.0,  # High
            self_confidence=0.0,  # Low confidence
            tool_error_rate=1.0,  # High
            evidence_gap=1.0  # High
        )

        # All components at max -> 1.0
        assert math.isclose(result, 1.0, rel_tol=0.001)

    def test_calculate_uncertainty_score_low(self):
        """Low uncertainty score."""
        result = calculate_uncertainty_score(
            judge_std=0.0,
            self_confidence=1.0,
            tool_error_rate=0.0,
            evidence_gap=0.0
        )

        # All components at min -> 0.0
        assert math.isclose(result, 0.0, rel_tol=0.001)


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def pipeline(self):
        return CalibrationPipeline(profile_id="test-pipeline")

    def test_calibrate_threshold_with_duplicates(self, pipeline):
        """Threshold calibration handles duplicate scores."""
        accepted = [0.5] * 100  # All same value

        result = pipeline.calibrate_taboo_threshold(accepted)

        # All duplicates -> threshold should be 0.5
        assert result.new_threshold == 0.5

    def test_calibrate_threshold_single_value_range(self, pipeline):
        """Single value range in distribution."""
        accepted = [0.0] * 50 + [1.0] * 50

        result = pipeline.calibrate_taboo_threshold(accepted, percentile=50)

        # Median between 0 and 1
        assert result.new_threshold in [0.0, 1.0]

    def test_matrix_inverse_singular(self, pipeline):
        """Singular matrix raises MatrixSingularError."""
        singular_matrix = [[1.0, 1.0], [1.0, 1.0]]  # Rank 1

        with pytest.raises(MatrixSingularError) as exc_info:
            pipeline._matrix_inverse(singular_matrix)

        assert "singular" in str(exc_info.value).lower()

    def test_run_offline_eval_not_implemented(self, pipeline):
        """Offline eval returns error when dataset not found."""
        result = pipeline.run_offline_eval("dataset.jsonl", "threshold-v1.0")
        # Returns error result when no dataset found
        assert result["status"] == "error"
        assert result.get("samples_loaded", 0) == 0


# =============================================================================
# AGF-REQ-007 Coverage Summary Tests
# =============================================================================

class TestCoverageSummary:
    """Tests verifying coverage requirements for AGF-REQ-007."""

    def test_anomaly_features_defined(self):
        """Anomaly feature set is defined."""
        assert len(ANOMALY_FEATURES) > 0
        assert "delta_semantic" in ANOMALY_FEATURES
        assert "tool_calls" in ANOMALY_FEATURES

    def test_migration_criteria_defined(self):
        """Migration criteria are defined."""
        assert MIGRATION_CRITERIA["precision_max_degradation"] > 0
        assert MIGRATION_CRITERIA["recall_max_degradation"] > 0
        assert MIGRATION_CRITERIA["f1_max_degradation"] > 0
        assert MIGRATION_CRITERIA["false_escalation_max_increase"] > 0

    def test_calibration_triggers_defined(self):
        """Calibration triggers are defined."""
        assert CALIBRATION_TRIGGERS["override_surge_rate"] > 0
        assert CALIBRATION_TRIGGERS["override_surge_window_days"] > 0
        assert CALIBRATION_TRIGGERS["critical_miss_priority"] == "P0"

    def test_drift_responses_defined(self):
        """Drift responses are defined for all types."""
        assert "score_inflation" in DRIFT_RESPONSES
        assert "score_deflation" in DRIFT_RESPONSES
        assert "threshold_decay" in DRIFT_RESPONSES
        assert "distribution_shift" in DRIFT_RESPONSES

    def test_default_thresholds_defined(self):
        """Default thresholds are defined for all axes."""
        assert "taboo" in DEFAULT_THRESHOLDS
        assert "drift" in DEFAULT_THRESHOLDS
        assert "anomaly_percentile" in DEFAULT_THRESHOLDS
        assert "constitution_alignment" in DEFAULT_THRESHOLDS