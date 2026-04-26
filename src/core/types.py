"""
Core Types - Data structures for gate decisions

DATA_TYPES_SPEC compliant type definitions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum


class GateState(Enum):
    """Gate decision states (DATA_TYPES_SPEC 2.1)"""
    PASS = "pass"
    WARN = "warn"
    HOLD = "hold"
    BLOCK = "block"


@dataclass
class ScoreFactor:
    """Contributing factor to composite score (DATA_TYPES_SPEC 3.1)"""
    name: str
    value: float
    weight: float
    contribution: float  # = value * weight
    threshold: Optional[float] = None
    threshold_type: Optional[str] = None  # "warn" or "block"


@dataclass
class ExemplarRef:
    """Reference to exemplar from judgment KB (DATA_TYPES_SPEC 3.1)"""
    doc_id: str
    axis_type: str
    similarity: float
    version: Optional[str] = None
    text_excerpt: Optional[str] = None


@dataclass
class DecisionResult:
    """Gate decision result (DATA_TYPES_SPEC DecisionPacket v1.0.0)"""
    # Required fields (no defaults) - must come first
    decision: str  # "pass"|"warn"|"hold"|"block" (string per spec, not enum)
    composite_score: float

    # Optional fields with defaults - come after required fields
    schema_version: str = "1.0.0"
    artifact_id: str = ""
    policy_version: str = ""
    factors: List[ScoreFactor] = field(default_factory=list)
    exemplar_refs: List[ExemplarRef] = field(default_factory=list)
    action: Dict = field(default_factory=dict)  # ActionRecommendation structure
    threshold_version: str = ""
    static_gate_summary: Dict = field(default_factory=dict)
    hard_override: Optional[str] = None  # enum: secret_found, prod_write_taboo, etc.
    self_correction_count: int = 0
    state_vector_ref: str = ""
    review_override: Optional[Dict] = None
    scorer_results: List = field(default_factory=list)  # ScorerResult list
    persistent_factors: List[str] = field(default_factory=list)
    checkpoint_ref: Optional[str] = None
    created_at: Optional[str | datetime] = None  # ISO format timestamp
    # Audit fields (STATE_TRANSITION_SPEC 11.1)
    decision_id: Optional[str] = None
    run_id: Optional[str] = None
    trace_id: Optional[str] = None
    previous_state: Optional[str] = None
    transition_reason: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        created_at = self.created_at
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()

        return {
            'schema_version': self.schema_version,
            'decision_id': self.decision_id,
            'run_id': self.run_id,
            'artifact_id': self.artifact_id,
            'decision': self.decision,
            'composite_score': self.composite_score,
            'factors': [f.__dict__ if hasattr(f, '__dict__') else f for f in self.factors],
            'exemplar_refs': [e.__dict__ if hasattr(e, '__dict__') else e for e in self.exemplar_refs],
            'action': self.action,
            'threshold_version': self.threshold_version,
            'policy_version': self.policy_version,
            'static_gate_summary': self.static_gate_summary,
            'created_at': created_at,
            'hard_override': self.hard_override,
            'hard_override_reason': self.hard_override,
            'self_correction_count': self.self_correction_count,
            'trace_id': self.trace_id,
            'state_vector_ref': self.state_vector_ref,
            'review_override': self.review_override,
            'persistent_factors': self.persistent_factors,
            'checkpoint_ref': self.checkpoint_ref,
            'previous_state': self.previous_state,
            'transition_reason': self.transition_reason,
        }
