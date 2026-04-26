"""
Generic Harness Adapter.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable

from .base import HarnessAdapter
from .dataclasses import RunEvent, ArtifactSnapshot, StaticGateResult

logger = logging.getLogger(__name__)


class GenericHarnessAdapter(HarnessAdapter):
    """
    Generic adapter for harnesses with standard hooks.

    Provides basic implementations that can be extended or overridden
    for specific harness integrations.
    """

    def __init__(
        self,
        deny_patterns: List[str] = None,
        event_handlers: Dict[str, Callable] = None
    ):
        self.deny_patterns = deny_patterns or [
            "rm -rf /",
            "DROP DATABASE",
            "kubectl delete --all",
            "DELETE FROM",
            "format disk",
            "shutdown",
            "reboot"
        ]
        self.event_handlers = event_handlers or {}
        self._event_log: List[RunEvent] = []
        self._gate_results: List[StaticGateResult] = []
        self._checkpoints: Dict[str, str] = {}

    def subscribe_events(self) -> None:
        logger.info("Subscribing to harness lifecycle events")

        default_handlers = {
            'run_started': self._handle_run_started,
            'step_started': self._handle_step_started,
            'tool_call_requested': self._handle_tool_call_requested,
            'artifact_emitted': self._handle_artifact_emitted,
            'static_gate_completed': self._handle_static_gate_completed,
            'run_completed': self._handle_run_completed,
            'run_failed': self._handle_run_failed,
        }

        for event_type, handler in default_handlers.items():
            if event_type not in self.event_handlers:
                self.event_handlers[event_type] = handler

        logger.info(f"Registered {len(self.event_handlers)} event handlers")

    def _handle_run_started(self, event: RunEvent) -> None:
        logger.info(f"Run started: {event.run_id}")
        self._event_log.append(event)

    def _handle_step_started(self, event: RunEvent) -> None:
        logger.debug(f"Step started: {event.run_id}")

    def _handle_tool_call_requested(self, event: RunEvent) -> None:
        logger.debug(f"Tool call requested: {event.run_id}")

    def _handle_artifact_emitted(self, event: RunEvent) -> None:
        logger.info(f"Artifact emitted: {event.run_id} -> {event.artifact_ref}")
        self._event_log.append(event)

    def _handle_static_gate_completed(self, event: RunEvent) -> None:
        logger.info(f"Static gate completed: {event.run_id}")

    def _handle_run_completed(self, event: RunEvent) -> None:
        logger.info(f"Run completed: {event.run_id}")
        self._event_log.append(event)

    def _handle_run_failed(self, event: RunEvent) -> None:
        logger.error(f"Run failed: {event.run_id}")
        self._event_log.append(event)

    def emit_event(self, event: RunEvent) -> None:
        handler = self.event_handlers.get(event.event_type)
        if handler:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler failed for {event.event_type}: {e}")
        else:
            logger.warning(f"No handler for event type: {event.event_type}")

    def pause_run(self, run_id: str) -> str:
        checkpoint_ref = f"checkpoint://{run_id}/cp/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self._checkpoints[run_id] = checkpoint_ref

        logger.info(f"Paused run {run_id}, checkpoint: {checkpoint_ref}")

        event = RunEvent(
            run_id=run_id,
            trace_id=f"trace-{run_id}",
            event_type="run_paused",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor="gate_system",
            artifact_ref=None,
            checkpoint_ref=checkpoint_ref,
            payload_ref=None
        )
        self._event_log.append(event)

        return checkpoint_ref

    def resume_run(self, run_id: str, checkpoint_ref: str) -> None:
        if run_id in self._checkpoints:
            stored_checkpoint = self._checkpoints[run_id]
            if stored_checkpoint != checkpoint_ref:
                logger.warning(
                    f"Checkpoint mismatch for {run_id}: "
                    f"expected {stored_checkpoint}, got {checkpoint_ref}"
                )

        logger.info(f"Resuming run {run_id} from checkpoint {checkpoint_ref}")

        event = RunEvent(
            run_id=run_id,
            trace_id=f"trace-{run_id}",
            event_type="run_resumed",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor="gate_system",
            artifact_ref=None,
            checkpoint_ref=checkpoint_ref,
            payload_ref=None
        )
        self._event_log.append(event)

    def check_tool_policy(self, tool_call: Dict) -> str:
        command = str(tool_call.get('command', tool_call.get('tool', tool_call.get('name', ''))))

        for pattern in self.deny_patterns:
            if pattern.lower() in command.lower():
                logger.warning(f"Tool call DENIED: matches pattern '{pattern}'")
                return "deny"

        prod_keywords = ['production', 'prod', 'deploy', 'release', 'publish']
        for keyword in prod_keywords:
            if keyword in command.lower():
                logger.info(f"Tool call HOLD: contains production keyword '{keyword}'")
                return "hold"

        high_risk_keywords = ['admin', 'root', 'sudo', 'privilege']
        for keyword in high_risk_keywords:
            if keyword in command.lower():
                logger.info(f"Tool call HOLD: contains high-risk keyword '{keyword}'")
                return "hold"

        logger.debug(f"Tool call ALLOWED: {command}")
        return "allow"

    def get_artifact_snapshot(self, run_id: str) -> ArtifactSnapshot:
        artifact_events = [
            e for e in self._event_log
            if e.run_id == run_id and e.event_type == 'artifact_emitted'
        ]

        artifact_ref = None
        if artifact_events:
            artifact_ref = artifact_events[-1].artifact_ref

        return ArtifactSnapshot(
            run_id=run_id,
            artifact_id=f"{run_id}-artifact",
            hash=f"sha256:{run_id}",
            diff=None,
            source_step="step_final",
            commit=None,
            branch=None
        )

    def ingest_static_gate_result(self, result: Dict) -> None:
        gate_result = StaticGateResult(
            run_id=result.get('run_id', 'unknown'),
            gate_type=result.get('gate_type', 'unknown'),
            passed=result.get('passed', False),
            severity=result.get('severity', 'medium'),
            details=result.get('details', {}),
            timestamp=datetime.now(timezone.utc).isoformat()
        )

        self._gate_results.append(gate_result)

        logger.info(
            f"Ingested static gate result: run={gate_result.run_id}, "
            f"type={gate_result.gate_type}, passed={gate_result.passed}"
        )

    def get_trace_context(self, run_id: str) -> Dict:
        return {
            "trace_id": f"trace-{run_id}",
            "span_id": f"span-{run_id}",
            "run_id": run_id
        }

    def get_event_log(self, run_id: Optional[str] = None) -> List[RunEvent]:
        if run_id:
            return [e for e in self._event_log if e.run_id == run_id]
        return self._event_log

    def get_gate_results(self, run_id: Optional[str] = None) -> List[StaticGateResult]:
        if run_id:
            return [r for r in self._gate_results if r.run_id == run_id]
        return self._gate_results


__all__ = ['GenericHarnessAdapter']