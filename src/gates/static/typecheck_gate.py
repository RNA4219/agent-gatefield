"""
Type check gate - Supports mypy (Python), tsc (TypeScript)
"""

import logging
import pathlib
from typing import Dict

from .base import StaticGateAdapter, GateResult, GateSeverity

logger = logging.getLogger(__name__)


class TypeCheckGate(StaticGateAdapter):
    """Type check gate - Supports mypy (Python), tsc (TypeScript)"""

    def __init__(self, language: str = "python", config_file: str = None):
        self.language = language.lower() if language else "python"
        self.config_file = config_file

    def name(self) -> str:
        return "typecheck"

    def run(self, artifact_path: str, context: Dict) -> GateResult:
        """Run type checker"""
        lang = self.language
        if not lang:
            ext = pathlib.Path(artifact_path).suffix.lower()
            if ext in ['.py']:
                lang = 'python'
            elif ext in ['.ts', '.tsx']:
                lang = 'typescript'

        if lang == 'python':
            return self._run_mypy(artifact_path)
        elif lang == 'typescript':
            return self._run_tsc(artifact_path)
        else:
            return GateResult(
                gate_name=self.name(),
                status="pass",
                details={"message": f"No type checker for {lang}"}
            )

    def _run_mypy(self, artifact_path: str) -> GateResult:
        """Run mypy for Python"""
        error_count = 0
        findings = []

        if not self._check_tool_available("mypy"):
            return GateResult(
                gate_name=self.name(),
                status="warn",
                details={"message": "mypy not available"}
            )

        cmd = ["mypy", "--no-error-summary", artifact_path]
        if self.config_file:
            cmd.extend(["--config-file", self.config_file])

        exit_code, stdout, stderr = self._run_command(cmd)

        for line in stdout.split('\n'):
            if 'error:' in line.lower():
                error_count += 1
                findings.append({"message": line.strip(), "severity": "error"})

        status = "fail" if error_count > 0 else "pass"

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=GateSeverity.HIGH.value if error_count > 0 else None,
            findings=findings,
            error_count=error_count,
            details={"tool": "mypy", "language": "python"}
        )

    def _run_tsc(self, artifact_path: str) -> GateResult:
        """Run TypeScript compiler for type checking"""
        error_count = 0
        findings = []

        if not self._check_tool_available("tsc"):
            return GateResult(
                gate_name=self.name(),
                status="warn",
                details={"message": "tsc not available"}
            )

        cmd = ["tsc", "--noEmit", artifact_path]
        exit_code, stdout, stderr = self._run_command(cmd)

        for line in stderr.split('\n'):
            if 'error TS' in line:
                error_count += 1
                findings.append({"message": line.strip(), "severity": "error"})

        status = "fail" if error_count > 0 else "pass"

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=GateSeverity.HIGH.value if error_count > 0 else None,
            findings=findings,
            error_count=error_count,
            details={"tool": "tsc", "language": "typescript"}
        )