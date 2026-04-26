"""
Harness Adapters - Interface to existing agent harness.

This module is a facade that imports from submodules.
Direct imports from submodule files are recommended for type checking.
"""

from .dataclasses import RunEvent, ArtifactSnapshot, StaticGateResult
from .base import HarnessAdapter
from .generic_adapter import GenericHarnessAdapter
from .openai_adapter import OpenAIAgentsSDKAdapter
from .claude_adapter import ClaudeCodeAdapter
from .langgraph_adapter import LangGraphAdapter
from .registry import HarnessRegistry

__all__ = [
    'RunEvent',
    'ArtifactSnapshot',
    'StaticGateResult',
    'HarnessAdapter',
    'GenericHarnessAdapter',
    'OpenAIAgentsSDKAdapter',
    'ClaudeCodeAdapter',
    'LangGraphAdapter',
    'HarnessRegistry',
]