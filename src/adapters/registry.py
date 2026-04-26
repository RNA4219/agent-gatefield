"""
Harness Registry.
"""

import logging
import os
from typing import Dict, Optional

from .base import HarnessAdapter
from .generic_adapter import GenericHarnessAdapter
from .openai_adapter import OpenAIAgentsSDKAdapter
from .claude_adapter import ClaudeCodeAdapter
from .langgraph_adapter import LangGraphAdapter

logger = logging.getLogger(__name__)


class HarnessRegistry:
    """Registry for harness adapters."""

    adapters: Dict[str, HarnessAdapter] = {}

    def register(self, name: str, adapter: HarnessAdapter) -> None:
        self.adapters[name] = adapter
        logger.info(f"Registered harness adapter: {name}")

    def get(self, name: str) -> Optional[HarnessAdapter]:
        return self.adapters.get(name)

    def detect_harness(self) -> str:
        """
        Auto-detect harness type from environment.
        """
        if os.environ.get('OPENAI_API_KEY') and 'openai' in os.environ.get('PYTHONPATH', '').lower():
            logger.info("Detected OpenAI Agents SDK environment")
            return "openai_agents_sdk"

        if os.environ.get('CLAUDE_CODE_SESSION') or os.path.exists('.claude/settings.json'):
            logger.info("Detected Claude Code CLI environment")
            return "claude_code"

        if 'langgraph' in os.environ.get('PYTHONPATH', '').lower() or os.path.exists('langgraph.json'):
            logger.info("Detected LangGraph environment")
            return "langgraph"

        logger.info("No specific harness detected, using generic")
        return "generic"

    def get_auto_adapter(self) -> HarnessAdapter:
        harness_type = self.detect_harness()
        adapter = self.get(harness_type)

        if not adapter:
            if harness_type == "openai_agents_sdk":
                adapter = OpenAIAgentsSDKAdapter()
            elif harness_type == "claude_code":
                adapter = ClaudeCodeAdapter()
            elif harness_type == "langgraph":
                adapter = LangGraphAdapter()
            else:
                adapter = GenericHarnessAdapter()

            self.register(harness_type, adapter)

        return adapter


__all__ = ['HarnessRegistry']