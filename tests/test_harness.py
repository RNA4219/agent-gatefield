"""
Tests for Harness Adapters facade module.
"""

import pytest

from src.adapters.harness import (
    RunEvent,
    ArtifactSnapshot,
    StaticGateResult,
    HarnessAdapter,
    GenericHarnessAdapter,
    OpenAIAgentsSDKAdapter,
    ClaudeCodeAdapter,
    LangGraphAdapter,
    HarnessRegistry,
)


class TestHarnessImports:
    """Tests for harness facade imports."""

    def test_run_event_import(self):
        """RunEvent imports successfully."""
        assert RunEvent is not None

    def test_artifact_snapshot_import(self):
        """ArtifactSnapshot imports successfully."""
        assert ArtifactSnapshot is not None

    def test_static_gate_result_import(self):
        """StaticGateResult imports successfully."""
        assert StaticGateResult is not None

    def test_harness_adapter_import(self):
        """HarnessAdapter imports successfully."""
        assert HarnessAdapter is not None

    def test_generic_harness_adapter_import(self):
        """GenericHarnessAdapter imports successfully."""
        assert GenericHarnessAdapter is not None

    def test_openai_agents_sdk_adapter_import(self):
        """OpenAIAgentsSDKAdapter imports successfully."""
        assert OpenAIAgentsSDKAdapter is not None

    def test_claude_code_adapter_import(self):
        """ClaudeCodeAdapter imports successfully."""
        assert ClaudeCodeAdapter is not None

    def test_langgraph_adapter_import(self):
        """LangGraphAdapter imports successfully."""
        assert LangGraphAdapter is not None

    def test_harness_registry_import(self):
        """HarnessRegistry imports successfully."""
        assert HarnessRegistry is not None


class TestHarnessAllExports:
    """Tests for __all__ exports."""

    def test_all_exports_count(self):
        """All exports count."""
        from src.adapters.harness import __all__
        assert len(__all__) == 9

    def test_all_exports_contains_run_event(self):
        """__all__ contains RunEvent."""
        from src.adapters.harness import __all__
        assert 'RunEvent' in __all__

    def test_all_exports_contains_artifact_snapshot(self):
        """__all__ contains ArtifactSnapshot."""
        from src.adapters.harness import __all__
        assert 'ArtifactSnapshot' in __all__

    def test_all_exports_contains_static_gate_result(self):
        """__all__ contains StaticGateResult."""
        from src.adapters.harness import __all__
        assert 'StaticGateResult' in __all__

    def test_all_exports_contains_harness_adapter(self):
        """__all__ contains HarnessAdapter."""
        from src.adapters.harness import __all__
        assert 'HarnessAdapter' in __all__

    def test_all_exports_contains_generic_adapter(self):
        """__all__ contains GenericHarnessAdapter."""
        from src.adapters.harness import __all__
        assert 'GenericHarnessAdapter' in __all__

    def test_all_exports_contains_openai_adapter(self):
        """__all__ contains OpenAIAgentsSDKAdapter."""
        from src.adapters.harness import __all__
        assert 'OpenAIAgentsSDKAdapter' in __all__

    def test_all_exports_contains_claude_adapter(self):
        """__all__ contains ClaudeCodeAdapter."""
        from src.adapters.harness import __all__
        assert 'ClaudeCodeAdapter' in __all__

    def test_all_exports_contains_langgraph_adapter(self):
        """__all__ contains LangGraphAdapter."""
        from src.adapters.harness import __all__
        assert 'LangGraphAdapter' in __all__

    def test_all_exports_contains_registry(self):
        """__all__ contains HarnessRegistry."""
        from src.adapters.harness import __all__
        assert 'HarnessRegistry' in __all__


class TestHarnessClassTypes:
    """Tests for class types."""

    def test_run_event_is_dataclass(self):
        """RunEvent is a dataclass."""
        from dataclasses import is_dataclass
        assert is_dataclass(RunEvent)

    def test_artifact_snapshot_is_dataclass(self):
        """ArtifactSnapshot is a dataclass."""
        from dataclasses import is_dataclass
        assert is_dataclass(ArtifactSnapshot)

    def test_static_gate_result_is_dataclass(self):
        """StaticGateResult is a dataclass."""
        from dataclasses import is_dataclass
        assert is_dataclass(StaticGateResult)

    def test_harness_adapter_is_abstract(self):
        """HarnessAdapter is an abstract base class."""
        from abc import ABC
        assert issubclass(HarnessAdapter, ABC)

    def test_generic_adapter_inherits_base(self):
        """GenericHarnessAdapter inherits HarnessAdapter."""
        assert issubclass(GenericHarnessAdapter, HarnessAdapter)

    def test_openai_adapter_inherits_base(self):
        """OpenAIAgentsSDKAdapter inherits HarnessAdapter."""
        assert issubclass(OpenAIAgentsSDKAdapter, HarnessAdapter)

    def test_claude_adapter_inherits_base(self):
        """ClaudeCodeAdapter inherits HarnessAdapter."""
        assert issubclass(ClaudeCodeAdapter, HarnessAdapter)

    def test_langgraph_adapter_inherits_base(self):
        """LangGraphAdapter inherits HarnessAdapter."""
        assert issubclass(LangGraphAdapter, HarnessAdapter)

    def test_registry_is_class(self):
        """HarnessRegistry is a class."""
        assert HarnessRegistry is not None
        # Check it can be instantiated
        registry = HarnessRegistry()
        assert registry is not None


class TestHarnessModuleDocstring:
    """Tests for module docstring."""

    def test_module_has_docstring(self):
        """Module has docstring."""
        import src.adapters.harness as harness_module
        assert harness_module.__doc__ is not None

    def test_docstring_mentions_facade(self):
        """Docstring mentions facade."""
        import src.adapters.harness as harness_module
        assert 'facade' in harness_module.__doc__.lower()