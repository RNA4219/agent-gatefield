"""
Lint gate - Supports Python (pylint), JavaScript (eslint), Go (golint)
"""

import json
import logging
import re
import pathlib
from typing import Dict

from .base import StaticGateAdapter, GateResult, GateSeverity

logger = logging.getLogger(__name__)


class LintGate(StaticGateAdapter):
    """Lint/type check gate - Supports Python (pylint) and JavaScript (eslint)"""

    def __init__(self, language: str = "python", config_file: str = None):
        self.language = language.lower() if language else "python"
        self.config_file = config_file

    def name(self) -> str:
        return "lint"

    def run(self, artifact_path: str, context: Dict) -> GateResult:
        """
        Run lint check based on language

        Python: pylint
        JavaScript: eslint
        """
        # Determine language from context or file extension
        lang = self.language
        if not lang:
            ext = pathlib.Path(artifact_path).suffix.lower()
            if ext in ['.py']:
                lang = 'python'
            elif ext in ['.js', '.ts', '.jsx', '.tsx']:
                lang = 'javascript'
            elif ext in ['.go']:
                lang = 'go'

        if lang == 'python':
            return self._run_python_lint(artifact_path, context)
        elif lang in ['javascript', 'typescript']:
            return self._run_js_lint(artifact_path, context)
        elif lang == 'go':
            return self._run_go_lint(artifact_path, context)
        else:
            return GateResult(
                gate_name=self.name(),
                status="pass",
                severity=GateSeverity.LOW.value,
                details={"message": f"No lint tool configured for language: {lang}"}
            )

    def _run_python_lint(self, artifact_path: str, context: Dict) -> GateResult:
        """Run pylint for Python"""
        findings = []
        error_count = 0
        warning_count = 0

        if not self._check_tool_available("pylint"):
            logger.warning("pylint not available, skipping")
            return GateResult(
                gate_name=self.name(),
                status="warn",
                severity=GateSeverity.LOW.value,
                details={"message": "pylint not available"},
                warning_count=1
            )

        cmd = ["pylint", "--output-format=json", artifact_path]
        if self.config_file:
            cmd.extend(["--rcfile", self.config_file])

        exit_code, stdout, stderr = self._run_command(cmd)

        if stdout.strip():
            try:
                findings = json.loads(stdout)
                for f in findings:
                    severity = f.get('type', 'warning')
                    if severity in ['error', 'fatal']:
                        error_count += 1
                    else:
                        warning_count += 1
            except json.JSONDecodeError:
                error_count = len(re.findall(r'E:\s*\d+', stdout))
                warning_count = len(re.findall(r'W:\s*\d+', stdout))

        status = "fail" if error_count > 0 else ("warn" if warning_count > 0 else "pass")
        severity = GateSeverity.HIGH.value if error_count > 0 else GateSeverity.LOW.value

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=severity,
            evidence_ref=artifact_path,
            findings=findings,
            error_count=error_count,
            warning_count=warning_count,
            details={
                "tool": "pylint",
                "language": "python",
                "total_errors": error_count,
                "total_warnings": warning_count
            }
        )

    def _run_js_lint(self, artifact_path: str, context: Dict) -> GateResult:
        """Run eslint for JavaScript/TypeScript"""
        findings = []
        error_count = 0
        warning_count = 0

        if not self._check_tool_available("eslint"):
            logger.warning("eslint not available, skipping")
            return GateResult(
                gate_name=self.name(),
                status="warn",
                severity=GateSeverity.LOW.value,
                details={"message": "eslint not available"},
                warning_count=1
            )

        cmd = ["eslint", "--format=json", artifact_path]
        if self.config_file:
            cmd.extend(["-c", self.config_file])

        exit_code, stdout, stderr = self._run_command(cmd)

        if stdout.strip():
            try:
                results = json.loads(stdout)
                for r in results:
                    for msg in r.get('messages', []):
                        severity = msg.get('severity', 1)
                        if severity == 2:  # Error
                            error_count += 1
                            findings.append({
                                'rule': msg.get('ruleId'),
                                'message': msg.get('message'),
                                'line': msg.get('line'),
                                'severity': 'error'
                            })
                        else:  # Warning
                            warning_count += 1
            except json.JSONDecodeError:
                pass

        status = "fail" if error_count > 0 else ("warn" if warning_count > 0 else "pass")

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=GateSeverity.HIGH.value if error_count > 0 else GateSeverity.LOW.value,
            evidence_ref=artifact_path,
            findings=findings,
            error_count=error_count,
            warning_count=warning_count,
            details={"tool": "eslint", "language": "javascript"}
        )

    def _run_go_lint(self, artifact_path: str, context: Dict) -> GateResult:
        """Run golint for Go"""
        if not self._check_tool_available("golint"):
            return GateResult(
                gate_name=self.name(),
                status="warn",
                details={"message": "golint not available"}
            )

        cmd = ["golint", artifact_path]
        exit_code, stdout, stderr = self._run_command(cmd)

        issues = stdout.strip().split('\n') if stdout.strip() else []
        warning_count = len([i for i in issues if i.strip()])
        status = "warn" if warning_count > 0 else "pass"

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=GateSeverity.LOW.value,
            findings=[{"message": i} for i in issues if i.strip()],
            warning_count=warning_count,
            details={"tool": "golint"}
        )