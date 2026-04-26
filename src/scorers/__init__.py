"""
Scorers - 各判定器の実装

This module provides scorers for evaluating agent trajectories
against various criteria (constitution alignment, taboo proximity, etc).

All individual scorers are available directly from this module for backward
compatibility. The internal implementation is split into separate files.
"""

from typing import List, Dict

# Import base classes and result type
from .base import BaseScorer, ScorerResult

# Import individual scorers
from .constitution import ConstitutionAlignmentScorer
from .taboo import TabooProximityScorer
from .similarity import AcceptSimilarityScorer, RejectSimilarityScorer
from .drift import DriftScorer
from .anomaly import AnomalyScorer
from .uncertainty import UncertaintyScorer

# Import composite scorer and direction scorer
from .composite import CompositeScorer, DirectionScorer

# Export all public classes
__all__ = [
    'ScorerResult',
    'BaseScorer',
    'ConstitutionAlignmentScorer',
    'TabooProximityScorer',
    'AcceptSimilarityScorer',
    'RejectSimilarityScorer',
    'DriftScorer',
    'DirectionScorer',
    'AnomalyScorer',
    'UncertaintyScorer',
    'CompositeScorer',
    'create_scorers_from_config',
]


def create_scorers_from_config(config: Dict) -> Dict:
    """
    Create scorer instances from configuration.

    Factory function that creates all individual scorer instances
    with weights from the provided configuration.

    Args:
        config: Configuration dict with scorer weights.
            Expected keys: constitution_alignment, taboo_proximity,
            accept_similarity, reject_similarity, direction, drift,
            anomaly, uncertainty

    Returns:
        Dict mapping scorer names to scorer instances

    Example:
        config = {
            'constitution_alignment': {'weight': 0.20},
            'taboo_proximity': {'weight': 0.30},
            # ... other scorers
        }
        scorers = create_scorers_from_config(config)
        result = scorers['constitution_alignment'].score(...)
    """
    return {
        "constitution_alignment": ConstitutionAlignmentScorer(
            config.get('constitution_alignment', {}).get('weight', 0.20)
        ),
        "taboo_proximity": TabooProximityScorer(
            config.get('taboo_proximity', {}).get('weight', 0.30)
        ),
        "accept_similarity": AcceptSimilarityScorer(
            config.get('accept_similarity', {}).get('weight', 0.10)
        ),
        "reject_similarity": RejectSimilarityScorer(
            config.get('reject_similarity', {}).get('weight', 0.15)
        ),
        "direction": DirectionScorer(
            config.get('direction', {}).get('weight', 0.05)
        ),
        "drift": DriftScorer(
            config.get('drift', {}).get('weight', 0.10)
        ),
        "anomaly": AnomalyScorer(
            config.get('anomaly', {}).get('weight', 0.10)
        ),
        "uncertainty": UncertaintyScorer(
            config.get('uncertainty', {}).get('weight', 0.05)
        ),
    }