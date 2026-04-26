"""
Tool execution policy gate - Check tool calls against deny patterns
"""

import json
import logging
from typing import Dict, List

from .base import StaticGateAdapter, GateResult, GateSeverity

logger = logging.getLogger(__name__)


class ToolPolicyGate(StaticGateAdapter):
    """Tool execution policy gate - Check tool calls against deny patterns"""

    def __init__(self, deny_patterns: List[str] = None, allow_patterns: List[str] = None):
        self.deny_patterns = deny_patterns or [
            "rm -rf /",
            "DROP DATABASE",
            "DROP TABLE",
            "kubectl delete --all",
            "kubectl delete namespace",
            "sudo rm",
            "> /dev/sda",
            "mkfs",
            "dd if=",
            ":(){ :|:& };:",  # Fork bomb
            "chmod 777",
            "chown root",
        ]
        self.allow_patterns = allow_patterns or []

    def name(self) -> str:
        return "tool_policy"

    def run(self, artifact_path: str, context: Dict) -> GateResult:
        """
        Check tool calls against deny patterns

        artifact_path can be a file containing tool calls, or context can contain tool_calls list
        """
        findings = []
        deny_count = 0

        # Get tool calls from context or parse from file
        tool_calls = context.get('tool_calls', [])
        if not tool_calls and artifact_path:
            try:
                with open(artifact_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    try:
                        data = json.loads(content)
                        tool_calls = data if isinstance(data, list) else [data]
                    except json.JSONDecodeError:
                        tool_calls = [{"command": content}]
            except Exception:
                pass

        # Check each tool call against patterns
        for tc in tool_calls:
            command = tc.get('command', tc.get('tool_name', str(tc)))

            for pattern in self.deny_patterns:
                if pattern.lower() in str(command).lower():
                    deny_count += 1
                    findings.append({
                        "pattern": pattern,
                        "command": str(command)[:100],
                        "severity": "CRITICAL",
                        "message": f"Command matches deny pattern: {pattern}"
                    })
                    break

            # Check allow patterns (override deny if explicitly allowed)
            for pattern in self.allow_patterns:
                if pattern.lower() in str(command).lower():
                    findings = [f for f in findings if f.get('command') != str(command)[:100]]
                    deny_count -= 1
                    break

        status = "fail" if deny_count > 0 else "pass"
        severity = GateSeverity.CRITICAL.value if deny_count > 0 else None

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=severity,
            findings=findings,
            error_count=deny_count,
            details={
                "deny_patterns": self.deny_patterns,
                "deny_count": deny_count,
                "checked_calls": len(tool_calls)
            }
        )