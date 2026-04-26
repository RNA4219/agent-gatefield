"""
OpenAI Agents SDK Adapter.
"""

import logging
from datetime import datetime, timezone
from typing import Dict

from .base import HarnessAdapter
from .dataclasses import ArtifactSnapshot

logger = logging.getLogger(__name__)


class OpenAIAgentsSDKAdapter(HarnessAdapter):
    """
    Adapter for OpenAI Agents SDK.
    Uses guardrails, human review, tracing, checkpointing.
    """

    def __init__(self):
        self._traces: Dict[str, Dict] = {}
        self._guardrails_configured = False
        self._checkpoints: Dict[str, str] = {}

    def subscribe_events(self) -> None:
        logger.info("Subscribing to OpenAI Agents SDK events via OTel exporter")

    def pause_run(self, run_id: str) -> str:
        checkpoint_ref = f"otel://checkpoint/{run_id}/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self._checkpoints[run_id] = checkpoint_ref
        logger.info(f"OpenAI SDK: Paused run {run_id}")
        return checkpoint_ref

    def resume_run(self, run_id: str, checkpoint_ref: str) -> None:
        logger.info(f"OpenAI SDK: Resuming run {run_id} from {checkpoint_ref}")

    def check_tool_policy(self, tool_call: Dict) -> str:
        tool_name = tool_call.get('name', tool_call.get('tool', 'unknown'))

        dangerous_tools = ['execute_code', 'run_shell', 'file_write']
        if tool_name in dangerous_tools:
            return "hold"

        return "allow"

    def get_artifact_snapshot(self, run_id: str) -> ArtifactSnapshot:
        trace_data = self._traces.get(run_id, {})
        return ArtifactSnapshot(
            run_id=run_id,
            artifact_id=f"{run_id}-artifact",
            hash=f"sha256:{run_id}",
            diff=trace_data.get('diff'),
            source_step=trace_data.get('last_step', 'final'),
            commit=trace_data.get('commit'),
            branch=trace_data.get('branch')
        )

    def ingest_static_gate_result(self, result: Dict) -> None:
        run_id = result.get('run_id')
        if run_id in self._traces:
            self._traces[run_id]['static_gates'] = result
        logger.info(f"OpenAI SDK: Ingested gate result for {run_id}")

    def get_trace_context(self, run_id: str) -> Dict:
        trace_data = self._traces.get(run_id, {})
        return {
            "trace_id": trace_data.get('trace_id', f"otel-{run_id}"),
            "span_id": trace_data.get('span_id', f"span-{run_id}"),
            "run_id": run_id
        }

    def register_trace(self, run_id: str, trace_data: Dict) -> None:
        self._traces[run_id] = trace_data


__all__ = ['OpenAIAgentsSDKAdapter']