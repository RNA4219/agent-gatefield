"""
Harness adapter base class.
"""

from abc import ABC, abstractmethod
from typing import Dict

from .dataclasses import ArtifactSnapshot


class HarnessAdapter(ABC):
    """
    Base adapter for harness integration.
    Implements the contract from requirements.
    """

    @abstractmethod
    def subscribe_events(self) -> None:
        """Subscribe to run lifecycle events (P0)"""
        pass

    @abstractmethod
    def pause_run(self, run_id: str) -> str:
        """Pause run and return checkpoint ref (P0)"""
        pass

    @abstractmethod
    def resume_run(self, run_id: str, checkpoint_ref: str) -> None:
        """Resume from checkpoint (P0)"""
        pass

    @abstractmethod
    def check_tool_policy(self, tool_call: Dict) -> str:
        """Check tool call policy, return deny/hold/allow (P0)"""
        pass

    @abstractmethod
    def get_artifact_snapshot(self, run_id: str) -> ArtifactSnapshot:
        """Get artifact metadata (P0)"""
        pass

    @abstractmethod
    def ingest_static_gate_result(self, result: Dict) -> None:
        """Import static gate results from CI/scanners (P0)"""
        pass

    @abstractmethod
    def get_trace_context(self, run_id: str) -> Dict:
        """Get trace_id/span_id for correlation (P0)"""
        pass


__all__ = ['HarnessAdapter']