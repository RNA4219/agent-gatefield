"""
Engine module - Composite Decision Engine.

This module provides the main decision engine for gate decisions,
along with helper functions for score building and gate summary.

Backward compatibility: Also exports types from src.core.types that were
previously imported directly from src.core.engine.
"""

from .decision_engine import DecisionEngine, STATE_RULES, GATE_SUMMARY_RULES
from .helpers import (
    compute_centroid,
    build_score_factors,
    build_exemplar_refs,
    build_static_gate_summary,
)

# Re-export types for backward compatibility (previously imported from src.core.engine)
from src.core.types import DecisionResult, GateState, ScoreFactor, ExemplarRef

__all__ = [
    'DecisionEngine',
    'DecisionResult',
    'GateState',
    'ScoreFactor',
    'ExemplarRef',
    'STATE_RULES',
    'GATE_SUMMARY_RULES',
    'compute_centroid',
    'build_score_factors',
    'build_exemplar_refs',
    'build_static_gate_summary',
]