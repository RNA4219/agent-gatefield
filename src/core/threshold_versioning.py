"""
Threshold Versioning - Lock and Replay Threshold Configurations

STATE_TRANSITION_SPEC 12.1 and ACCEPTANCE_CRITERIA_SPEC 9.2 compliant
threshold version locking for reproducible evaluations.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Optional

from src.core.audit import audit_logger
from .exceptions import ThresholdNotFoundError


class ThresholdVersionManager:
    """
    Manages threshold version locking for reproducible replay evaluations.

    Allows locking threshold configurations under version identifiers
    and replaying decisions with specific locked versions.
    """

    def __init__(self, initial_version: str = 'v1'):
        """
        Initialize the version manager.

        Args:
            initial_version: The starting threshold version
        """
        self._current_version = initial_version
        self._versions: Dict[str, Dict] = {}  # version -> config

    @property
    def current_version(self) -> str:
        """Get the current threshold version."""
        return self._current_version

    def lock_version(
        self,
        version: str,
        thresholds: Dict,
        hard_overrides: Dict
    ) -> None:
        """
        Lock threshold configuration under a specific version.

        Args:
            version: Version identifier (e.g., 'v1', 'v2')
            thresholds: Threshold configuration dict
            hard_overrides: Hard overrides configuration dict
        """
        self._versions[version] = {
            'thresholds': thresholds.copy(),
            'hard_overrides': hard_overrides.copy(),
            'locked_at': datetime.now(timezone.utc).isoformat(),
            'config_hash': self._compute_hash(thresholds)
        }

    def get_locked_config(self, version: str) -> Optional[Dict]:
        """
        Retrieve locked configuration for a specific version.

        Args:
            version: Version identifier

        Returns:
            Locked config dict or None if version not found
        """
        return self._versions.get(version)

    def set_current_version(self, version: str) -> None:
        """
        Set the current threshold version.

        Args:
            version: Version identifier to set as current
        """
        self._current_version = version

    def _compute_hash(self, thresholds: Dict) -> str:
        """
        Compute hash of threshold configuration for verification.

        Args:
            thresholds: Threshold configuration dict

        Returns:
            SHA256 hash prefix (16 chars)
        """
        threshold_json = json.dumps(thresholds, sort_keys=True)
        return hashlib.sha256(threshold_json.encode()).hexdigest()[:16]

    def verify_version_integrity(self, version: str, thresholds: Dict) -> bool:
        """
        Verify that a threshold config matches its locked version.

        Args:
            version: Version identifier
            thresholds: Threshold configuration to verify

        Returns:
            True if hash matches, False otherwise
        """
        locked_config = self._versions.get(version)
        if not locked_config:
            return False

        current_hash = self._compute_hash(thresholds)
        return current_hash == locked_config.get('config_hash')


class ThresholdReplayContext:
    """
    Context manager for temporarily swapping threshold versions.

    Usage:
        with ThresholdReplayContext(engine, 'v1') as ctx:
            result = engine.evaluate(state_vector)
    """

    def __init__(self, engine: 'DecisionEngine', version: str):
        """
        Initialize the replay context.

        Args:
            engine: DecisionEngine instance
            version: Threshold version to use
        """
        self.engine = engine
        self.version = version
        self.original_thresholds = None
        self.original_overrides = None

    def __enter__(self):
        """Swap to locked threshold version."""
        locked_config = self.engine.get_locked_thresholds(self.version)
        if not locked_config:
            raise ThresholdNotFoundError(self.version)

        self.original_thresholds = self.engine.thresholds
        self.original_overrides = self.engine.hard_overrides

        self.engine.thresholds = locked_config['thresholds']
        self.engine.hard_overrides = locked_config['hard_overrides']

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original thresholds."""
        self.engine.thresholds = self.original_thresholds
        self.engine.hard_overrides = self.original_overrides
        return False


def lock_threshold_version(
    version_manager: ThresholdVersionManager,
    version: str,
    thresholds: Dict,
    hard_overrides: Dict
) -> None:
    """
    Convenience function to lock a threshold version.

    Args:
        version_manager: ThresholdVersionManager instance
        version: Version identifier
        thresholds: Threshold configuration
        hard_overrides: Hard overrides configuration
    """
    version_manager.lock_version(version, thresholds, hard_overrides)


def replay_with_version(
    engine: 'DecisionEngine',
    version: str,
    state_vector: Dict,
    kb_embeddings: Dict = None
) -> Optional['DecisionResult']:
    """
    Re-evaluate using a specific locked threshold version.

    Args:
        engine: DecisionEngine instance
        version: Threshold version to use
        state_vector: State vector to evaluate
        kb_embeddings: Optional knowledge base embeddings

    Returns:
        DecisionResult or None if version not found
    """
    locked_config = engine.get_locked_thresholds(version)
    if not locked_config:
        return None

    # Temporarily swap thresholds
    original_thresholds = engine.thresholds
    original_overrides = engine.hard_overrides

    engine.thresholds = locked_config['thresholds']
    engine.hard_overrides = locked_config['hard_overrides']

    result = engine.evaluate(state_vector, kb_embeddings)
    result.threshold_version = version

    # Restore original thresholds
    engine.thresholds = original_thresholds
    engine.hard_overrides = original_overrides

    return result