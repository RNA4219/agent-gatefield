"""
Tests for Harness Adapters.
"""

import pytest
from datetime import datetime, timezone

from src.adapters.dataclasses import RunEvent, ArtifactSnapshot, StaticGateResult
from src.adapters.base import HarnessAdapter
from src.adapters.generic_adapter import GenericHarnessAdapter
from src.adapters.registry import HarnessRegistry
from src.adapters.claude_adapter import ClaudeCodeAdapter
from src.adapters.openai_adapter import OpenAIAgentsSDKAdapter
from src.adapters.langgraph_adapter import LangGraphAdapter


class TestDataclasses:
    """Tests for adapter dataclasses."""

    def test_run_event_creation(self):
        """RunEvent basic creation."""
        event = RunEvent(
            run_id="run-1",
            trace_id="trace-1",
            event_type="run_started",
            timestamp="2024-01-01T00:00:00Z",
            actor="user",
            artifact_ref=None,
            checkpoint_ref=None,
            payload_ref=None
        )
        assert event.run_id == "run-1"
        assert event.event_type == "run_started"

    def test_artifact_snapshot_creation(self):
        """ArtifactSnapshot basic creation."""
        snapshot = ArtifactSnapshot(
            run_id="run-1",
            artifact_id="artifact-1",
            hash="sha256:abc123",
            diff=None,
            source_step="step_1",
            commit="commit-1",
            branch="main"
        )
        assert snapshot.run_id == "run-1"
        assert snapshot.hash == "sha256:abc123"

    def test_static_gate_result_creation(self):
        """StaticGateResult basic creation."""
        result = StaticGateResult(
            run_id="run-1",
            gate_type="license",
            passed=True,
            severity="low",
            details={"licenses": ["MIT", "Apache-2.0"]},
            timestamp="2024-01-01T00:00:00Z"
        )
        assert result.passed is True
        assert result.gate_type == "license"


class TestGenericHarnessAdapter:
    """Tests for GenericHarnessAdapter."""

    def test_initialization(self):
        """Adapter initializes correctly."""
        adapter = GenericHarnessAdapter()
        assert adapter.deny_patterns is not None
        assert len(adapter.deny_patterns) > 0
        assert adapter._event_log == []
        assert adapter._checkpoints == {}

    def test_initialization_custom_deny_patterns(self):
        """Adapter with custom deny patterns."""
        adapter = GenericHarnessAdapter(deny_patterns=["malicious_cmd"])
        assert "malicious_cmd" in adapter.deny_patterns

    def test_subscribe_events(self):
        """Subscribe events registers handlers."""
        adapter = GenericHarnessAdapter()
        adapter.subscribe_events()
        assert 'run_started' in adapter.event_handlers
        assert 'run_completed' in adapter.event_handlers

    def test_pause_run(self):
        """Pause run creates checkpoint."""
        adapter = GenericHarnessAdapter()
        checkpoint = adapter.pause_run("run-1")
        assert checkpoint.startswith("checkpoint://")
        assert "run-1" in checkpoint
        assert "run-1" in adapter._checkpoints

    def test_resume_run(self):
        """Resume run from checkpoint."""
        adapter = GenericHarnessAdapter()
        checkpoint = adapter.pause_run("run-1")
        adapter.resume_run("run-1", checkpoint)
        # Event logged
        assert len(adapter._event_log) >= 2  # pause + resume events

    def test_check_tool_policy_deny(self):
        """Tool policy denies dangerous commands."""
        adapter = GenericHarnessAdapter()
        assert adapter.check_tool_policy({"command": "rm -rf /"}) == "deny"
        assert adapter.check_tool_policy({"command": "DROP DATABASE test"}) == "deny"

    def test_check_tool_policy_hold_production(self):
        """Tool policy holds production commands."""
        adapter = GenericHarnessAdapter()
        assert adapter.check_tool_policy({"command": "deploy production"}) == "hold"
        assert adapter.check_tool_policy({"tool": "publish release"}) == "hold"

    def test_check_tool_policy_hold_high_risk(self):
        """Tool policy holds high-risk commands."""
        adapter = GenericHarnessAdapter()
        assert adapter.check_tool_policy({"command": "sudo admin"}) == "hold"

    def test_check_tool_policy_allow(self):
        """Tool policy allows safe commands."""
        adapter = GenericHarnessAdapter()
        assert adapter.check_tool_policy({"command": "list files"}) == "allow"
        assert adapter.check_tool_policy({"name": "read_config"}) == "allow"

    def test_get_artifact_snapshot(self):
        """Get artifact snapshot."""
        adapter = GenericHarnessAdapter()
        snapshot = adapter.get_artifact_snapshot("run-1")
        assert snapshot.run_id == "run-1"
        assert snapshot.artifact_id == "run-1-artifact"
        assert snapshot.hash.startswith("sha256:")

    def test_ingest_static_gate_result(self):
        """Ingest static gate result."""
        adapter = GenericHarnessAdapter()
        adapter.ingest_static_gate_result({
            'run_id': 'run-1',
            'gate_type': 'lint',
            'passed': True,
            'severity': 'low',
            'details': {'errors': 0}
        })
        assert len(adapter._gate_results) == 1
        assert adapter._gate_results[0].gate_type == 'lint'

    def test_get_trace_context(self):
        """Get trace context."""
        adapter = GenericHarnessAdapter()
        ctx = adapter.get_trace_context("run-1")
        assert ctx['run_id'] == 'run-1'
        assert 'trace_id' in ctx
        assert 'span_id' in ctx

    def test_emit_event(self):
        """Emit event calls handler."""
        adapter = GenericHarnessAdapter()
        adapter.subscribe_events()

        event = RunEvent(
            run_id="run-1",
            trace_id="trace-1",
            event_type="run_started",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor="user",
            artifact_ref=None,
            checkpoint_ref=None,
            payload_ref=None
        )
        adapter.emit_event(event)

        assert len(adapter._event_log) >= 1

    def test_get_event_log(self):
        """Get event log."""
        adapter = GenericHarnessAdapter()
        adapter.subscribe_events()

        event = RunEvent(
            run_id="run-1",
            trace_id="trace-1",
            event_type="run_started",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor="user",
            artifact_ref=None,
            checkpoint_ref=None,
            payload_ref=None
        )
        adapter.emit_event(event)

        log = adapter.get_event_log("run-1")
        assert len(log) >= 1
        assert all(e.run_id == "run-1" for e in log)

    def test_get_gate_results(self):
        """Get gate results."""
        adapter = GenericHarnessAdapter()
        adapter.ingest_static_gate_result({'run_id': 'run-1', 'gate_type': 'lint', 'passed': True})
        adapter.ingest_static_gate_result({'run_id': 'run-2', 'gate_type': 'sast', 'passed': False})

        results = adapter.get_gate_results("run-1")
        assert len(results) == 1
        assert results[0].run_id == 'run-1'


class TestHarnessRegistry:
    """Tests for HarnessRegistry."""

    def test_initialization(self):
        """Registry initializes correctly."""
        registry = HarnessRegistry()
        assert registry.adapters == {}

    def test_register(self):
        """Register adapter."""
        registry = HarnessRegistry()
        adapter = GenericHarnessAdapter()
        registry.register("generic", adapter)
        assert "generic" in registry.adapters

    def test_get_found(self):
        """Get registered adapter."""
        registry = HarnessRegistry()
        adapter = GenericHarnessAdapter()
        registry.register("generic", adapter)
        found = registry.get("generic")
        assert found is adapter

    def test_get_not_found(self):
        """Get returns None for missing adapter."""
        registry = HarnessRegistry()
        found = registry.get("missing")
        assert found is None

    def test_detect_harness_generic(self):
        """Detect returns generic when no specific harness."""
        registry = HarnessRegistry()
        # Clear environment indicators
        harness = registry.detect_harness()
        assert harness == "generic"

    def test_get_auto_adapter(self):
        """Get auto adapter creates and registers."""
        registry = HarnessRegistry()
        adapter = registry.get_auto_adapter()
        assert adapter is not None
        # Should be registered
        assert registry.get("generic") is adapter


class TestBaseAdapterContract:
    """Tests for adapter base class contract."""

    def test_abstract_methods(self):
        """Base class has abstract methods."""
        # Verify abstract methods exist
        assert hasattr(HarnessAdapter, 'subscribe_events')
        assert hasattr(HarnessAdapter, 'pause_run')
        assert hasattr(HarnessAdapter, 'resume_run')
        assert hasattr(HarnessAdapter, 'check_tool_policy')
        assert hasattr(HarnessAdapter, 'get_artifact_snapshot')
        assert hasattr(HarnessAdapter, 'ingest_static_gate_result')
        assert hasattr(HarnessAdapter, 'get_trace_context')

    def test_generic_adapter_implements_contract(self):
        """Generic adapter implements all abstract methods."""
        adapter = GenericHarnessAdapter()
        adapter.subscribe_events()
        adapter.pause_run("run-1")
        adapter.resume_run("run-1", "checkpoint://test")
        adapter.check_tool_policy({"command": "test"})
        adapter.get_artifact_snapshot("run-1")
        adapter.ingest_static_gate_result({'run_id': 'run-1'})
        adapter.get_trace_context("run-1")
        # All methods work without error


class TestGenericHarnessAdapterIntegration:
    """Integration-like tests."""

    def test_full_workflow(self):
        """Full run workflow with adapter."""
        adapter = GenericHarnessAdapter()
        adapter.subscribe_events()

        # Start run
        start_event = RunEvent(
            run_id="run-1",
            trace_id="trace-1",
            event_type="run_started",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor="user",
            artifact_ref=None,
            checkpoint_ref=None,
            payload_ref=None
        )
        adapter.emit_event(start_event)

        # Emit artifact
        artifact_event = RunEvent(
            run_id="run-1",
            trace_id="trace-1",
            event_type="artifact_emitted",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor="agent",
            artifact_ref="artifact://output.json",
            checkpoint_ref=None,
            payload_ref=None
        )
        adapter.emit_event(artifact_event)

        # Pause
        checkpoint = adapter.pause_run("run-1")

        # Resume
        adapter.resume_run("run-1", checkpoint)

        # Complete
        complete_event = RunEvent(
            run_id="run-1",
            trace_id="trace-1",
            event_type="run_completed",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor="agent",
            artifact_ref=None,
            checkpoint_ref=None,
            payload_ref=None
        )
        adapter.emit_event(complete_event)

        # Verify event log
        log = adapter.get_event_log("run-1")
        event_types = [e.event_type for e in log]
        assert "run_started" in event_types
        assert "artifact_emitted" in event_types
        assert "run_completed" in event_types

    def test_tool_policy_multiple_commands(self):
        """Tool policy check multiple commands."""
        adapter = GenericHarnessAdapter()

        commands = [
            ("list files", "allow"),
            ("deploy prod", "hold"),
            ("sudo rm -rf /", "deny"),
            ("read config", "allow"),
            ("shutdown system", "deny"),
        ]

        for cmd, expected in commands:
            result = adapter.check_tool_policy({"command": cmd})
            assert result == expected


class TestClaudeCodeAdapter:
    """Tests for ClaudeCodeAdapter."""

    def test_initialization(self):
        """Adapter initializes correctly."""
        adapter = ClaudeCodeAdapter()
        assert adapter._hook_results == []
        assert adapter._artifacts == {}
        assert len(adapter._deny_patterns) > 0

    def test_subscribe_events(self):
        """Subscribe events."""
        adapter = ClaudeCodeAdapter()
        adapter.subscribe_events()

    def test_pause_run(self):
        """Pause run creates checkpoint."""
        adapter = ClaudeCodeAdapter()
        checkpoint = adapter.pause_run("run-1")
        assert checkpoint.startswith("claude://session/")

    def test_resume_run(self):
        """Resume run clears checkpoint."""
        adapter = ClaudeCodeAdapter()
        checkpoint = adapter.pause_run("run-1")
        adapter.resume_run("run-1", checkpoint)
        assert "run-1" not in adapter._session_checkpoints

    def test_check_tool_policy_deny(self):
        """Tool policy denies dangerous patterns."""
        adapter = ClaudeCodeAdapter()
        assert adapter.check_tool_policy({"tool_name": "bash", "tool_input": {"command": "rm -rf"}}) == "deny"
        assert adapter.check_tool_policy({"tool_name": "bash", "tool_input": {"command": "sudo"}}) == "deny"

    def test_check_tool_policy_hold(self):
        """Tool policy holds production commands."""
        adapter = ClaudeCodeAdapter()
        assert adapter.check_tool_policy({"tool_name": "bash", "tool_input": {"command": "deploy production"}}) == "hold"

    def test_check_tool_policy_allow(self):
        """Tool policy allows safe commands."""
        adapter = ClaudeCodeAdapter()
        assert adapter.check_tool_policy({"tool_name": "read", "tool_input": {"file_path": "/tmp/test"}}) == "allow"

    def test_get_artifact_snapshot(self):
        """Get artifact snapshot."""
        adapter = ClaudeCodeAdapter()
        snapshot = adapter.get_artifact_snapshot("run-1")
        assert snapshot.run_id == "run-1"

    def test_get_artifact_snapshot_registered(self):
        """Get registered artifact."""
        adapter = ClaudeCodeAdapter()
        artifact = ArtifactSnapshot(
            run_id="run-1",
            artifact_id="custom",
            hash="sha256:custom",
            diff=None,
            source_step="custom",
            commit=None,
            branch=None
        )
        adapter.register_artifact("run-1", artifact)
        snapshot = adapter.get_artifact_snapshot("run-1")
        assert snapshot.artifact_id == "custom"

    def test_ingest_static_gate_result(self):
        """Ingest gate result."""
        adapter = ClaudeCodeAdapter()
        adapter.ingest_static_gate_result({'run_id': 'run-1', 'gate_type': 'lint', 'passed': True})
        assert len(adapter._hook_results) == 1

    def test_get_trace_context(self):
        """Get trace context."""
        adapter = ClaudeCodeAdapter()
        ctx = adapter.get_trace_context("run-1")
        assert ctx['run_id'] == 'run-1'
        assert 'trace_id' in ctx


class TestOpenAIAgentsSDKAdapter:
    """Tests for OpenAIAgentsSDKAdapter."""

    def test_initialization(self):
        """Adapter initializes correctly."""
        adapter = OpenAIAgentsSDKAdapter()
        assert adapter._traces == {}
        assert adapter._checkpoints == {}

    def test_subscribe_events(self):
        """Subscribe events."""
        adapter = OpenAIAgentsSDKAdapter()
        adapter.subscribe_events()

    def test_pause_run(self):
        """Pause run creates checkpoint."""
        adapter = OpenAIAgentsSDKAdapter()
        checkpoint = adapter.pause_run("run-1")
        assert checkpoint.startswith("otel://checkpoint/")

    def test_resume_run(self):
        """Resume run."""
        adapter = OpenAIAgentsSDKAdapter()
        checkpoint = adapter.pause_run("run-1")
        adapter.resume_run("run-1", checkpoint)

    def test_check_tool_policy_hold(self):
        """Tool policy holds dangerous tools."""
        adapter = OpenAIAgentsSDKAdapter()
        assert adapter.check_tool_policy({"name": "execute_code"}) == "hold"
        assert adapter.check_tool_policy({"name": "run_shell"}) == "hold"
        assert adapter.check_tool_policy({"name": "file_write"}) == "hold"

    def test_check_tool_policy_allow(self):
        """Tool policy allows safe tools."""
        adapter = OpenAIAgentsSDKAdapter()
        assert adapter.check_tool_policy({"name": "read_file"}) == "allow"

    def test_get_artifact_snapshot(self):
        """Get artifact snapshot."""
        adapter = OpenAIAgentsSDKAdapter()
        snapshot = adapter.get_artifact_snapshot("run-1")
        assert snapshot.run_id == "run-1"

    def test_get_artifact_snapshot_with_trace(self):
        """Get artifact snapshot with trace data."""
        adapter = OpenAIAgentsSDKAdapter()
        adapter.register_trace("run-1", {"diff": "test diff", "last_step": "step_2"})
        snapshot = adapter.get_artifact_snapshot("run-1")
        assert snapshot.diff == "test diff"

    def test_ingest_static_gate_result(self):
        """Ingest gate result."""
        adapter = OpenAIAgentsSDKAdapter()
        adapter.register_trace("run-1", {})
        adapter.ingest_static_gate_result({'run_id': 'run-1', 'gate_type': 'lint', 'passed': True})
        assert 'static_gates' in adapter._traces['run-1']

    def test_get_trace_context(self):
        """Get trace context."""
        adapter = OpenAIAgentsSDKAdapter()
        ctx = adapter.get_trace_context("run-1")
        assert ctx['run_id'] == 'run-1'

    def test_get_trace_context_with_trace(self):
        """Get trace context with registered trace."""
        adapter = OpenAIAgentsSDKAdapter()
        adapter.register_trace("run-1", {"trace_id": "custom-trace", "span_id": "custom-span"})
        ctx = adapter.get_trace_context("run-1")
        assert ctx['trace_id'] == "custom-trace"


class TestLangGraphAdapter:
    """Tests for LangGraphAdapter."""

    def test_initialization(self):
        """Adapter initializes correctly."""
        adapter = LangGraphAdapter()
        assert adapter._graph_states == {}
        assert adapter._checkpoints == {}

    def test_subscribe_events(self):
        """Subscribe events."""
        adapter = LangGraphAdapter()
        adapter.subscribe_events()

    def test_pause_run(self):
        """Pause run creates checkpoint."""
        adapter = LangGraphAdapter()
        checkpoint = adapter.pause_run("run-1")
        assert checkpoint.startswith("langgraph://checkpoint/")

    def test_resume_run(self):
        """Resume run."""
        adapter = LangGraphAdapter()
        checkpoint = adapter.pause_run("run-1")
        adapter.resume_run("run-1", checkpoint)

    def test_check_tool_policy(self):
        """Tool policy always allows."""
        adapter = LangGraphAdapter()
        assert adapter.check_tool_policy({"tool": "any"}) == "allow"

    def test_get_artifact_snapshot(self):
        """Get artifact snapshot."""
        adapter = LangGraphAdapter()
        snapshot = adapter.get_artifact_snapshot("run-1")
        assert snapshot.run_id == "run-1"

    def test_get_artifact_snapshot_with_state(self):
        """Get artifact snapshot with graph state."""
        adapter = LangGraphAdapter()
        adapter._graph_states["run-1"] = {"diff": "test diff", "current_node": "node_1"}
        snapshot = adapter.get_artifact_snapshot("run-1")
        assert snapshot.diff == "test diff"
        assert snapshot.source_step == "node_1"

    def test_ingest_static_gate_result(self):
        """Ingest gate result."""
        adapter = LangGraphAdapter()
        adapter._graph_states["run-1"] = {}
        adapter.ingest_static_gate_result({'run_id': 'run-1', 'gate_type': 'lint', 'passed': True})
        assert 'static_gates' in adapter._graph_states['run-1']

    def test_get_trace_context(self):
        """Get trace context."""
        adapter = LangGraphAdapter()
        ctx = adapter.get_trace_context("run-1")
        assert ctx['run_id'] == 'run-1'
        assert 'thread_id' in ctx