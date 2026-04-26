"""
Tests for Harness Adapter Base Class.
"""

import pytest
from abc import ABC

from src.adapters.base import HarnessAdapter
from src.adapters.dataclasses import ArtifactSnapshot


class ConcreteAdapter(HarnessAdapter):
    """Concrete implementation for testing."""

    def subscribe_events(self) -> None:
        pass

    def pause_run(self, run_id: str) -> str:
        return 'checkpoint-ref'

    def resume_run(self, run_id: str, checkpoint_ref: str) -> None:
        pass

    def check_tool_policy(self, tool_call: dict) -> str:
        return 'allow'

    def get_artifact_snapshot(self, run_id: str) -> ArtifactSnapshot:
        return ArtifactSnapshot(
            run_id=run_id,
            artifact_id='test-artifact',
            hash='sha256:abc',
            diff=None,
            source_step='test-step',
            commit=None,
            branch=None
        )

    def ingest_static_gate_result(self, result: dict) -> None:
        pass

    def get_trace_context(self, run_id: str) -> dict:
        return {'trace_id': 'test-trace'}


class TestHarnessAdapterBase:
    """Tests for HarnessAdapter base class."""

    def test_is_abstract(self):
        assert issubclass(HarnessAdapter, ABC)

    def test_has_abstract_methods(self):
        methods = [
            'subscribe_events',
            'pause_run',
            'resume_run',
            'check_tool_policy',
            'get_artifact_snapshot',
            'ingest_static_gate_result',
            'get_trace_context'
        ]
        for method in methods:
            assert hasattr(HarnessAdapter, method)

    def test_cannot_instantiate_base(self):
        with pytest.raises(TypeError):
            HarnessAdapter()

    def test_concrete_can_instantiate(self):
        adapter = ConcreteAdapter()
        assert adapter is not None


class TestConcreteAdapterMethods:
    """Tests using concrete adapter."""

    @pytest.fixture
    def adapter(self):
        return ConcreteAdapter()

    def test_subscribe_events(self, adapter):
        adapter.subscribe_events()

    def test_pause_run(self, adapter):
        result = adapter.pause_run('run-1')
        assert result == 'checkpoint-ref'

    def test_resume_run(self, adapter):
        adapter.resume_run('run-1', 'checkpoint-ref')

    def test_check_tool_policy(self, adapter):
        result = adapter.check_tool_policy({'tool': 'test'})
        assert result == 'allow'

    def test_get_artifact_snapshot(self, adapter):
        snapshot = adapter.get_artifact_snapshot('run-1')
        assert snapshot.artifact_id == 'test-artifact'
        assert snapshot.run_id == 'run-1'

    def test_ingest_static_gate_result(self, adapter):
        adapter.ingest_static_gate_result({'gate': 'sast'})

    def test_get_trace_context(self, adapter):
        context = adapter.get_trace_context('run-1')
        assert context['trace_id'] == 'test-trace'


class TestHarnessAdapterProtocol:
    """Tests for adapter protocol compliance."""

    def test_all_methods_return_correct_types(self):
        adapter = ConcreteAdapter()

        assert adapter.pause_run('run') == 'checkpoint-ref'
        assert adapter.check_tool_policy({}) == 'allow'
        assert isinstance(adapter.get_artifact_snapshot('run'), ArtifactSnapshot)
        assert isinstance(adapter.get_trace_context('run'), dict)


class TestHarnessAdapterExports:
    """Tests for __all__."""

    def test_exports(self):
        from src.adapters.base import __all__
        assert 'HarnessAdapter' in __all__


class TestInheritanceChain:
    """Tests for inheritance."""

    def test_concrete_inherits_base(self):
        adapter = ConcreteAdapter()
        assert isinstance(adapter, HarnessAdapter)

    def test_generic_inherits_base(self):
        from src.adapters.generic_adapter import GenericHarnessAdapter
        adapter = GenericHarnessAdapter()
        assert isinstance(adapter, HarnessAdapter)

    def test_openai_inherits_base(self):
        from src.adapters.openai_adapter import OpenAIAgentsSDKAdapter
        adapter = OpenAIAgentsSDKAdapter()
        assert isinstance(adapter, HarnessAdapter)

    def test_claude_inherits_base(self):
        from src.adapters.claude_adapter import ClaudeCodeAdapter
        adapter = ClaudeCodeAdapter()
        assert isinstance(adapter, HarnessAdapter)

    def test_langgraph_inherits_base(self):
        from src.adapters.langgraph_adapter import LangGraphAdapter
        adapter = LangGraphAdapter()
        assert isinstance(adapter, HarnessAdapter)
