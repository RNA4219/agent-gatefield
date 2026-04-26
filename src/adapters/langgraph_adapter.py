"""
LangGraph Adapter.
"""

import logging
from datetime import datetime, timezone
from typing import Dict

from .base import HarnessAdapter
from .dataclasses import ArtifactSnapshot

logger = logging.getLogger(__name__)


class LangGraphAdapter(HarnessAdapter):
    """
    Adapter for LangGraph framework.
    Uses state checkpoints, interrupt patterns, and streaming.
    """

    def __init__(self):
        self._graph_states: Dict[str, Dict] = {}
        self._checkpoints: Dict[str, str] = {}

    def subscribe_events(self) -> None:
        logger.info("Subscribing to LangGraph state transition events")

    def pause_run(self, run_id: str) -> str:
        checkpoint_ref = f"langgraph://checkpoint/{run_id}/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self._checkpoints[run_id] = checkpoint_ref
        logger.info(f"LangGraph: Interrupted graph {run_id}")
        return checkpoint_ref

    def resume_run(self, run_id: str, checkpoint_ref: str) -> None:
        logger.info(f"LangGraph: Resuming graph {run_id} from {checkpoint_ref}")

    def check_tool_policy(self, tool_call: Dict) -> str:
        return "allow"

    def get_artifact_snapshot(self, run_id: str) -> ArtifactSnapshot:
        state = self._graph_states.get(run_id, {})
        return ArtifactSnapshot(
            run_id=run_id,
            artifact_id=f"{run_id}-artifact",
            hash=f"sha256:{run_id}",
            diff=state.get('diff'),
            source_step=state.get('current_node', 'final'),
            commit=state.get('commit'),
            branch=state.get('branch')
        )

    def ingest_static_gate_result(self, result: Dict) -> None:
        run_id = result.get('run_id')
        if run_id in self._graph_states:
            self._graph_states[run_id]['static_gates'] = result

    def get_trace_context(self, run_id: str) -> Dict:
        return {
            "trace_id": f"langgraph-{run_id}",
            "span_id": f"node-{run_id}",
            "run_id": run_id,
            "thread_id": run_id
        }


__all__ = ['LangGraphAdapter']