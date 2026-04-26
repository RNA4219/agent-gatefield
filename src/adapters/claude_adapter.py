"""
Claude Code CLI Adapter.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List

from .base import HarnessAdapter
from .dataclasses import ArtifactSnapshot

logger = logging.getLogger(__name__)


class ClaudeCodeAdapter(HarnessAdapter):
    """
    Adapter for Claude Code CLI.
    Uses hooks for PreToolUse, PostToolUse, etc.
    """

    def __init__(self):
        self._hook_results: List[Dict] = []
        self._artifacts: Dict[str, ArtifactSnapshot] = {}
        self._session_checkpoints: Dict[str, str] = {}
        self._deny_patterns: List[str] = [
            "rm -rf",
            "DROP DATABASE",
            "kubectl delete",
            "sudo",
            "format"
        ]

    def subscribe_events(self) -> None:
        logger.info("Configuring Claude Code hook subscriptions")

    def pause_run(self, run_id: str) -> str:
        checkpoint_ref = f"claude://session/{run_id}/hold/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self._session_checkpoints[run_id] = checkpoint_ref
        logger.info(f"Claude Code: Holding session {run_id}")
        return checkpoint_ref

    def resume_run(self, run_id: str, checkpoint_ref: str) -> None:
        if run_id in self._session_checkpoints:
            del self._session_checkpoints[run_id]
        logger.info(f"Claude Code: Released hold on session {run_id}")

    def check_tool_policy(self, tool_call: Dict) -> str:
        tool_name = tool_call.get('tool_name', tool_call.get('tool', 'unknown'))
        tool_input = tool_call.get('tool_input', {})
        command = str(tool_input.get('command', tool_input.get('file_path', '')))

        for pattern in self._deny_patterns:
            if pattern.lower() in command.lower():
                logger.warning(f"Claude Code: Denying tool {tool_name} - matches '{pattern}'")
                return "deny"

        if 'production' in command.lower() or 'prod' in command.lower():
            return "hold"

        return "allow"

    def get_artifact_snapshot(self, run_id: str) -> ArtifactSnapshot:
        if run_id in self._artifacts:
            return self._artifacts[run_id]

        return ArtifactSnapshot(
            run_id=run_id,
            artifact_id=f"{run_id}-artifact",
            hash=f"sha256:{run_id}",
            diff=None,
            source_step="write_tool",
            commit=None,
            branch=None
        )

    def ingest_static_gate_result(self, result: Dict) -> None:
        self._hook_results.append(result)
        logger.info(f"Claude Code: Logged gate result for {result.get('run_id')}")

    def get_trace_context(self, run_id: str) -> Dict:
        return {
            "trace_id": f"claude-session-{run_id}",
            "span_id": f"hook-{run_id}",
            "run_id": run_id,
            "session_id": run_id
        }

    def register_artifact(self, run_id: str, artifact: ArtifactSnapshot) -> None:
        self._artifacts[run_id] = artifact


__all__ = ['ClaudeCodeAdapter']