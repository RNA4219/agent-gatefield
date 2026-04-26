"""
Harness adapter dataclasses.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class RunEvent:
    """Run lifecycle event."""
    run_id: str
    trace_id: str
    event_type: str
    timestamp: str
    actor: str
    artifact_ref: Optional[str]
    checkpoint_ref: Optional[str]
    payload_ref: Optional[str]


@dataclass
class ArtifactSnapshot:
    """Artifact metadata snapshot."""
    run_id: str
    artifact_id: str
    hash: str
    diff: Optional[str]
    source_step: str
    commit: Optional[str]
    branch: Optional[str]


@dataclass
class StaticGateResult:
    """Static gate execution result."""
    run_id: str
    gate_type: str
    passed: bool
    severity: str
    details: Dict
    timestamp: str


__all__ = ['RunEvent', 'ArtifactSnapshot', 'StaticGateResult']