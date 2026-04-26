"""
Tests for Harness Registry.
"""

import pytest
import os
from unittest.mock import patch, MagicMock

from src.adapters.registry import HarnessRegistry
from src.adapters.generic_adapter import GenericHarnessAdapter
from src.adapters.openai_adapter import OpenAIAgentsSDKAdapter
from src.adapters.claude_adapter import ClaudeCodeAdapter
from src.adapters.langgraph_adapter import LangGraphAdapter


class TestHarnessRegistryInit:
    """Tests for HarnessRegistry initialization."""

    def test_default_init(self):
        # Note: adapters is a class-level dict, may not be empty
        registry = HarnessRegistry()
        assert isinstance(registry.adapters, dict)

    def test_class_level_adapters(self):
        # Class level adapters dict
        assert hasattr(HarnessRegistry, 'adapters')


class TestRegister:
    """Tests for register method."""

    def test_register_adapter(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        adapter = GenericHarnessAdapter()
        registry.register('test', adapter)
        assert registry.adapters['test'] == adapter

    def test_register_multiple(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        adapter1 = GenericHarnessAdapter()
        adapter2 = GenericHarnessAdapter()
        registry.register('adapter1', adapter1)
        registry.register('adapter2', adapter2)
        assert len(registry.adapters) == 2

    def test_register_overwrites(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        adapter1 = GenericHarnessAdapter()
        adapter2 = GenericHarnessAdapter()
        registry.register('test', adapter1)
        registry.register('test', adapter2)
        assert registry.adapters['test'] == adapter2


class TestGet:
    """Tests for get method."""

    def test_get_existing(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        adapter = GenericHarnessAdapter()
        registry.register('test', adapter)
        result = registry.get('test')
        assert result == adapter

    def test_get_nonexistent(self):
        registry = HarnessRegistry()
        result = registry.get('nonexistent')
        assert result is None

    def test_get_empty_registry(self):
        registry = HarnessRegistry()
        result = registry.get('anything')
        assert result is None


class TestDetectHarness:
    """Tests for detect_harness method."""

    def test_detect_generic_default(self):
        registry = HarnessRegistry()
        with patch.dict(os.environ, {}, clear=True):
            result = registry.detect_harness()
            assert result == 'generic'

    def test_detect_openai_with_api_key(self):
        registry = HarnessRegistry()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'PYTHONPATH': 'openai'}):
            result = registry.detect_harness()
            assert result == 'openai_agents_sdk'

    def test_detect_claude_with_session(self):
        registry = HarnessRegistry()
        with patch.dict(os.environ, {'CLAUDE_CODE_SESSION': 'session-1'}):
            result = registry.detect_harness()
            assert result == 'claude_code'

    def test_detect_langgraph_with_pythonpath(self):
        registry = HarnessRegistry()
        with patch.dict(os.environ, {'PYTHONPATH': 'langgraph'}):
            result = registry.detect_harness()
            assert result == 'langgraph'

    def test_detect_langgraph_with_file(self):
        registry = HarnessRegistry()
        # Mock only langgraph.json exists, not .claude/settings.json
        def mock_exists(path):
            return path == 'langgraph.json'
        with patch.dict(os.environ, {}, clear=True):
            with patch('os.path.exists', side_effect=mock_exists):
                result = registry.detect_harness()
                assert result == 'langgraph'


class TestGetAutoAdapter:
    """Tests for get_auto_adapter method."""

    def test_get_auto_adapter_generic(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        with patch.dict(os.environ, {}, clear=True):
            adapter = registry.get_auto_adapter()
            assert isinstance(adapter, GenericHarnessAdapter)

    def test_get_auto_adapter_registers(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        with patch.dict(os.environ, {}, clear=True):
            adapter = registry.get_auto_adapter()
            # Should be registered
            assert 'generic' in registry.adapters

    def test_get_auto_adapter_cached(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        with patch.dict(os.environ, {}, clear=True):
            adapter1 = registry.get_auto_adapter()
            adapter2 = registry.get_auto_adapter()
            # Same adapter instance
            assert adapter1 == adapter2

    def test_get_auto_adapter_openai(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'PYTHONPATH': 'openai'}):
            adapter = registry.get_auto_adapter()
            assert isinstance(adapter, OpenAIAgentsSDKAdapter)

    def test_get_auto_adapter_claude(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        with patch.dict(os.environ, {'CLAUDE_CODE_SESSION': 'session-1'}):
            adapter = registry.get_auto_adapter()
            assert isinstance(adapter, ClaudeCodeAdapter)

    def test_get_auto_adapter_langgraph(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        with patch.dict(os.environ, {'PYTHONPATH': 'langgraph'}):
            adapter = registry.get_auto_adapter()
            assert isinstance(adapter, LangGraphAdapter)

    def test_get_auto_adapter_existing_registration(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        adapter = GenericHarnessAdapter()
        registry.register('generic', adapter)
        result = registry.get_auto_adapter()
        assert result == adapter


class TestHarnessRegistryIntegration:
    """Integration tests."""

    def test_full_registration_workflow(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        adapter = GenericHarnessAdapter()
        registry.register('my_adapter', adapter)
        retrieved = registry.get('my_adapter')
        assert retrieved == adapter

    def test_auto_detect_and_register(self):
        registry = HarnessRegistry()
        registry.adapters = {}  # Clear class-level dict
        with patch.dict(os.environ, {}, clear=True):
            adapter = registry.get_auto_adapter()
            assert 'generic' in registry.adapters
            assert registry.get('generic') == adapter
