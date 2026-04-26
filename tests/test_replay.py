"""
Tests for ReplayEngine - reproducibility verification.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from src.core.replay import ReplayEngine, ReplayResult


class TestReplayResult:
    """Tests for ReplayResult dataclass."""

    def test_replay_result_creation(self):
        """ReplayResult basic creation."""
        result = ReplayResult(
            original_decision="pass",
            replay_decision="pass",
            threshold_version="v1",
            policy_version="v1",
            match=True,
            diff_explanation=None
        )
        assert result.match is True
        assert result.original_decision == "pass"
        assert result.replay_decision == "pass"

    def test_replay_result_mismatch(self):
        """ReplayResult with mismatch."""
        result = ReplayResult(
            original_decision="pass",
            replay_decision="hold",
            threshold_version="v1",
            policy_version="v2",
            match=False,
            diff_explanation="Threshold changed"
        )
        assert result.match is False
        assert result.diff_explanation == "Threshold changed"

    def test_replay_result_with_scores(self):
        """ReplayResult with score details."""
        result = ReplayResult(
            original_decision="warn",
            replay_decision="warn",
            threshold_version="v1",
            policy_version="v1",
            match=True,
            diff_explanation=None,
            original_scores={'taboo_proximity': 0.15},
            replay_scores={'taboo_proximity': 0.15},
            run_id='run-1'
        )
        assert result.original_scores['taboo_proximity'] == 0.15
        assert result.run_id == 'run-1'


class TestReplayEngine:
    """Tests for ReplayEngine."""

    def test_initialization(self):
        """ReplayEngine initializes correctly."""
        engine = ReplayEngine()
        assert engine.vector_store is None
        assert engine.engine is None
        assert engine.results == []

    def test_initialization_with_dependencies(self):
        """ReplayEngine with mock dependencies."""
        mock_vs = Mock()
        mock_engine = Mock()
        replay = ReplayEngine(vector_store=mock_vs, engine=mock_engine)
        assert replay.vector_store == mock_vs
        assert replay.engine == mock_engine

    def test_replay_run_mock_mode(self):
        """Replay without vector_store returns mock data."""
        replay = ReplayEngine()
        result = replay.replay_run("run-1", "v1")
        # Mock mode returns mock state vector with decision='pass'
        assert result.run_id == "run-1"
        assert result.match is True  # Mock returns pass == pass

    def test_batch_replay(self):
        """Batch replay multiple runs."""
        replay = ReplayEngine()
        results = replay.batch_replay(["run-1", "run-2", "run-3"], "v1")
        assert len(results) == 3
        assert all(r.match for r in results)  # Mock mode all pass

    def test_verify_reproducibility(self):
        """Verify reproducibility rate calculation."""
        replay = ReplayEngine()
        replay.results = [
            ReplayResult("pass", "pass", "v1", "v1", True, None, run_id="run-1"),
            ReplayResult("pass", "hold", "v1", "v1", False, "Threshold", run_id="run-2"),
            ReplayResult("warn", "warn", "v1", "v1", True, None, run_id="run-3"),
        ]
        rate = replay.verify_reproducibility(["run-1", "run-2", "run-3"])
        assert rate == 2/3

    def test_audit_reproducibility_pass(self):
        """Audit reproducibility passes at 99%."""
        replay = ReplayEngine()
        # Mock batch_replay to return matching results
        replay.batch_replay = lambda runs, ver: [
            ReplayResult("pass", "pass", "v1", "v1", True, None, run_id=r) for r in runs
        ]
        report = replay.audit_reproducibility(["run-1", "run-2"], min_match_rate=0.99)
        assert report['passed'] is True
        assert report['match_rate'] == 1.0

    def test_audit_reproducibility_fail(self):
        """Audit reproducibility fails below threshold."""
        replay = ReplayEngine()
        replay.batch_replay = lambda runs, ver: [
            ReplayResult("pass", "pass", "v1", "v1", True, None, run_id="run-1"),
            ReplayResult("pass", "hold", "v1", "v1", False, "Threshold", run_id="run-2"),
        ]
        report = replay.audit_reproducibility(["run-1", "run-2"], min_match_rate=0.99)
        assert report['passed'] is False
        assert report['match_rate'] == 0.5

    def test_explain_difference(self):
        """Explain difference between decisions."""
        replay = ReplayEngine()
        explanation = replay.explain_difference(
            {'decision': 'pass', 'scores': {'taboo_proximity': 0.10}, 'thresholds': {}},
            {'decision': 'hold', 'scores': {'taboo_proximity': 0.82}, 'thresholds': {'taboo_warn': 0.80}}
        )
        assert "Decision changed" in explanation
        assert "taboo_proximity" in explanation

    def test_explain_difference_threshold_change(self):
        """Explain threshold change."""
        replay = ReplayEngine()
        explanation = replay.explain_difference(
            {'decision': 'pass', 'scores': {}, 'thresholds': {'taboo_block': 0.88}},
            {'decision': 'pass', 'scores': {}, 'thresholds': {'taboo_block': 0.85}}
        )
        assert "taboo_block threshold changed" in explanation

    def test_get_default_thresholds(self):
        """Get default threshold config."""
        replay = ReplayEngine()
        defaults = replay._get_default_thresholds()
        assert defaults['thresholds']['taboo_block'] == 0.88
        assert defaults['weights']['taboo_proximity'] == 0.30

    def test_results_accumulation(self):
        """Results accumulate across replays."""
        replay = ReplayEngine()
        replay.replay_run("run-1", "v1")
        replay.replay_run("run-2", "v1")
        assert len(replay.results) == 2


class TestReplayEngineWithVectorStore:
    """Tests with mocked VectorStore."""

    def test_replay_with_vector_store_no_state(self):
        """Replay when state vector not found."""
        mock_vs = Mock()
        mock_vs.get_state_vector_by_run_id.return_value = None
        replay = ReplayEngine(vector_store=mock_vs)
        result = replay.replay_run("run-missing", "v1")
        assert result.original_decision == "unknown"
        assert result.replay_decision == "unknown"
        assert result.match is False

    def test_replay_with_vector_store_found(self):
        """Replay when state vector found."""
        mock_vs = Mock()
        mock_vs.get_state_vector_by_run_id.return_value = {
            'run_id': 'run-1',
            'decision': 'warn',
            'scorer_results': {'taboo_proximity': 0.15},
            'thresholds': {'taboo_block': 0.88}
        }
        mock_vs.get_threshold_version.return_value = None
        replay = ReplayEngine(vector_store=mock_vs)
        result = replay.replay_run("run-1", "v1")
        mock_vs.get_state_vector_by_run_id.assert_called_once_with("run-1")
        assert result.run_id == "run-1"

    def test_replay_with_threshold_config(self):
        """Replay with historical threshold config."""
        mock_vs = Mock()
        mock_vs.get_state_vector_by_run_id.return_value = {
            'run_id': 'run-1',
            'decision': 'pass',
            'scorer_results': {},
            'thresholds': {}
        }
        mock_vs.get_threshold_version.return_value = {
            'thresholds': {'taboo_block': 0.90},
            'weights': {'taboo_proximity': 0.35}
        }
        replay = ReplayEngine(vector_store=mock_vs)
        result = replay.replay_run("run-1", "v2")
        mock_vs.get_threshold_version.assert_called_once_with("v2")
        # Config cached
        assert "v2" in replay._historical_configs


class TestReplayEngineIntegration:
    """Integration-like tests."""

    def test_full_audit_workflow(self):
        """Full audit workflow."""
        replay = ReplayEngine()
        runs = ["run-1", "run-2", "run-3", "run-4", "run-5"]
        report = replay.audit_reproducibility(runs, min_match_rate=0.80)
        # Mock mode returns all matching
        assert report['total_runs'] == 5
        assert report['passed'] is True