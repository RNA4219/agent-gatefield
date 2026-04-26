"""
Tests for ThresholdVersioning - version locking and replay.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone

from src.core.threshold_versioning import (
    ThresholdVersionManager,
    ThresholdReplayContext,
    lock_threshold_version,
    replay_with_version,
)
from src.core.exceptions import ThresholdNotFoundError


class TestThresholdVersionManager:
    """Tests for ThresholdVersionManager."""

    def test_initialization(self):
        """VersionManager initializes correctly."""
        manager = ThresholdVersionManager()
        assert manager.current_version == 'v1'
        assert manager._versions == {}

    def test_initialization_custom_version(self):
        """VersionManager with custom initial version."""
        manager = ThresholdVersionManager(initial_version='v2')
        assert manager.current_version == 'v2'

    def test_lock_version(self):
        """Lock threshold configuration."""
        manager = ThresholdVersionManager()
        thresholds = {'taboo_block': 0.88, 'taboo_warn': 0.80}
        hard_overrides = {'block_on_match': True}

        manager.lock_version('v1', thresholds, hard_overrides)

        assert 'v1' in manager._versions
        assert manager._versions['v1']['thresholds'] == thresholds
        assert manager._versions['v1']['hard_overrides'] == hard_overrides
        assert 'locked_at' in manager._versions['v1']
        assert 'config_hash' in manager._versions['v1']

    def test_get_locked_config_found(self):
        """Get locked config for existing version."""
        manager = ThresholdVersionManager()
        thresholds = {'taboo_block': 0.88}
        hard_overrides = {}
        manager.lock_version('v1', thresholds, hard_overrides)

        config = manager.get_locked_config('v1')
        assert config is not None
        assert config['thresholds'] == thresholds

    def test_get_locked_config_not_found(self):
        """Get locked config returns None for missing version."""
        manager = ThresholdVersionManager()
        config = manager.get_locked_config('v2')
        assert config is None

    def test_set_current_version(self):
        """Set current version."""
        manager = ThresholdVersionManager()
        manager.set_current_version('v2')
        assert manager.current_version == 'v2'

    def test_compute_hash(self):
        """Compute hash for threshold config."""
        manager = ThresholdVersionManager()
        thresholds = {'taboo_block': 0.88, 'taboo_warn': 0.80}
        hash1 = manager._compute_hash(thresholds)
        assert len(hash1) == 16  # SHA256 prefix

        # Same config should produce same hash
        hash2 = manager._compute_hash(thresholds)
        assert hash1 == hash2

    def test_compute_hash_different_configs(self):
        """Different configs produce different hashes."""
        manager = ThresholdVersionManager()
        hash1 = manager._compute_hash({'taboo_block': 0.88})
        hash2 = manager._compute_hash({'taboo_block': 0.90})
        assert hash1 != hash2

    def test_verify_version_integrity_match(self):
        """Verify version integrity when hash matches."""
        manager = ThresholdVersionManager()
        thresholds = {'taboo_block': 0.88}
        manager.lock_version('v1', thresholds, {})

        result = manager.verify_version_integrity('v1', thresholds)
        assert result is True

    def test_verify_version_integrity_mismatch(self):
        """Verify version integrity when hash differs."""
        manager = ThresholdVersionManager()
        thresholds = {'taboo_block': 0.88}
        manager.lock_version('v1', thresholds, {})

        result = manager.verify_version_integrity('v1', {'taboo_block': 0.90})
        assert result is False

    def test_verify_version_integrity_missing_version(self):
        """Verify returns False for missing version."""
        manager = ThresholdVersionManager()
        result = manager.verify_version_integrity('v999', {'taboo_block': 0.88})
        assert result is False

    def test_lock_multiple_versions(self):
        """Lock multiple versions."""
        manager = ThresholdVersionManager()
        manager.lock_version('v1', {'taboo_block': 0.88}, {})
        manager.lock_version('v2', {'taboo_block': 0.90}, {})

        assert len(manager._versions) == 2
        assert manager._versions['v1']['thresholds']['taboo_block'] == 0.88
        assert manager._versions['v2']['thresholds']['taboo_block'] == 0.90

    def test_lock_version_copies_config(self):
        """Locked config is a copy, not reference."""
        manager = ThresholdVersionManager()
        thresholds = {'taboo_block': 0.88}
        manager.lock_version('v1', thresholds, {})

        # Modify original
        thresholds['taboo_block'] = 0.95

        # Locked version should not change
        assert manager._versions['v1']['thresholds']['taboo_block'] == 0.88


class TestThresholdReplayContext:
    """Tests for ThresholdReplayContext."""

    def test_context_enter_swaps_thresholds(self):
        """Context manager swaps thresholds on enter."""
        mock_engine = Mock()
        mock_engine.thresholds = {'taboo_block': 0.90}
        mock_engine.hard_overrides = {}
        mock_engine.get_locked_thresholds.return_value = {
            'thresholds': {'taboo_block': 0.88},
            'hard_overrides': {'block_on_match': True}
        }

        ctx = ThresholdReplayContext(mock_engine, 'v1')
        with ctx:
            assert mock_engine.thresholds == {'taboo_block': 0.88}
            assert mock_engine.hard_overrides == {'block_on_match': True}

    def test_context_exit_restores_thresholds(self):
        """Context manager restores thresholds on exit."""
        mock_engine = Mock()
        mock_engine.thresholds = {'taboo_block': 0.90}
        mock_engine.hard_overrides = {}
        mock_engine.get_locked_thresholds.return_value = {
            'thresholds': {'taboo_block': 0.88},
            'hard_overrides': {}
        }

        ctx = ThresholdReplayContext(mock_engine, 'v1')
        with ctx:
            pass

        assert mock_engine.thresholds == {'taboo_block': 0.90}

    def test_context_missing_version_raises(self):
        """Context raises for missing version."""
        mock_engine = Mock()
        mock_engine.get_locked_thresholds.return_value = None

        ctx = ThresholdReplayContext(mock_engine, 'v999')
        with pytest.raises(ThresholdNotFoundError):
            ctx.__enter__()

    def test_context_returns_self(self):
        """Context manager returns self on enter."""
        mock_engine = Mock()
        mock_engine.thresholds = {}
        mock_engine.hard_overrides = {}
        mock_engine.get_locked_thresholds.return_value = {
            'thresholds': {},
            'hard_overrides': {}
        }

        ctx = ThresholdReplayContext(mock_engine, 'v1')
        with ctx as result:
            assert result is ctx


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_lock_threshold_version_func(self):
        """lock_threshold_version convenience function."""
        manager = ThresholdVersionManager()
        thresholds = {'taboo_block': 0.88}
        hard_overrides = {}

        lock_threshold_version(manager, 'v1', thresholds, hard_overrides)

        assert 'v1' in manager._versions

    def test_replay_with_version_success(self):
        """replay_with_version returns result."""
        mock_engine = Mock()
        mock_engine.thresholds = {'taboo_block': 0.90}
        mock_engine.hard_overrides = {}
        mock_engine.get_locked_thresholds.return_value = {
            'thresholds': {'taboo_block': 0.88},
            'hard_overrides': {}
        }
        mock_result = Mock()
        mock_result.threshold_version = None
        mock_engine.evaluate.return_value = mock_result

        result = replay_with_version(
            mock_engine, 'v1', {'state': 'vector'}
        )

        assert result is mock_result
        assert result.threshold_version == 'v1'
        # Original thresholds restored
        assert mock_engine.thresholds == {'taboo_block': 0.90}

    def test_replay_with_version_missing(self):
        """replay_with_version returns None for missing version."""
        mock_engine = Mock()
        mock_engine.get_locked_thresholds.return_value = None

        result = replay_with_version(mock_engine, 'v999', {})
        assert result is None

    def test_replay_with_kb_embeddings(self):
        """replay_with_version passes kb_embeddings."""
        mock_engine = Mock()
        mock_engine.thresholds = {}
        mock_engine.hard_overrides = {}
        mock_engine.get_locked_thresholds.return_value = {
            'thresholds': {},
            'hard_overrides': {}
        }
        mock_engine.evaluate.return_value = Mock(threshold_version=None)

        replay_with_version(
            mock_engine, 'v1',
            {'state': 'vector'},
            kb_embeddings={'embed': [0.1]}
        )

        mock_engine.evaluate.assert_called_once_with(
            {'state': 'vector'}, {'embed': [0.1]}
        )


class TestThresholdVersionManagerIntegration:
    """Integration-like tests."""

    def test_full_workflow(self):
        """Full lock, verify, replay workflow."""
        manager = ThresholdVersionManager()

        # Lock v1
        v1_thresholds = {'taboo_block': 0.88, 'taboo_warn': 0.80}
        manager.lock_version('v1', v1_thresholds, {})

        # Lock v2
        v2_thresholds = {'taboo_block': 0.90, 'taboo_warn': 0.85}
        manager.lock_version('v2', v2_thresholds, {})

        # Set current to v2
        manager.set_current_version('v2')

        # Verify v1 still intact
        assert manager.verify_version_integrity('v1', v1_thresholds)

        # Get locked configs
        config_v1 = manager.get_locked_config('v1')
        config_v2 = manager.get_locked_config('v2')

        assert config_v1['thresholds']['taboo_block'] == 0.88
        assert config_v2['thresholds']['taboo_block'] == 0.90

    def test_version_independence(self):
        """Versions are independent."""
        manager = ThresholdVersionManager()

        manager.lock_version('v1', {'taboo_block': 0.88}, {})
        manager.lock_version('v2', {'taboo_block': 0.90}, {})

        # Verify each independently
        assert manager.verify_version_integrity('v1', {'taboo_block': 0.88})
        assert manager.verify_version_integrity('v2', {'taboo_block': 0.90})
        assert not manager.verify_version_integrity('v1', {'taboo_block': 0.90})