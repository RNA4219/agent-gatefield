"""
Test execution gate - Supports pytest (Python), jest (JavaScript), go test
"""

import json
import os
import logging
import re
from typing import Dict

from .base import StaticGateAdapter, GateResult, GateSeverity

logger = logging.getLogger(__name__)


class TestExecutionGate(StaticGateAdapter):
    """Test execution gate - Supports pytest (Python), jest (JavaScript)"""

    __test__ = False  # Prevent pytest collection

    def __init__(self, min_pass_rate: float = 1.0, test_runner: str = "pytest"):
        self.min_pass_rate = min_pass_rate
        self.test_runner = test_runner

    def name(self) -> str:
        return "tests"

    def run(self, artifact_path: str, context: Dict) -> GateResult:
        """Run tests and check pass rate"""
        runner = self.test_runner
        cwd = context.get('cwd', os.getcwd())

        if runner == "pytest":
            return self._run_pytest(artifact_path, cwd)
        elif runner == "jest":
            return self._run_jest(artifact_path, cwd)
        elif runner == "go":
            return self._run_go_test(artifact_path, cwd)
        else:
            return GateResult(
                gate_name=self.name(),
                status="pass",
                details={"message": f"No test runner configured: {runner}"}
            )

    def _run_pytest(self, artifact_path: str, cwd: str) -> GateResult:
        """Run pytest"""
        if not self._check_tool_available("pytest"):
            return GateResult(
                gate_name=self.name(),
                status="warn",
                details={"message": "pytest not available"}
            )

        cmd = ["pytest", "-v", "--tb=no", "-q", artifact_path]
        exit_code, stdout, stderr = self._run_command(cmd, cwd=cwd, timeout=300)

        passed = len(re.findall(r'PASSED', stdout))
        failed = len(re.findall(r'FAILED', stdout))
        errors = len(re.findall(r'ERROR', stdout))

        total = passed + failed + errors
        pass_rate = passed / total if total > 0 else 0

        status = "fail" if pass_rate < self.min_pass_rate else "pass"
        severity = GateSeverity.HIGH.value if failed > 0 else None

        findings = []
        for line in stdout.split('\n'):
            if 'FAILED' in line or 'ERROR' in line:
                findings.append({"message": line.strip(), "severity": "error"})

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=severity,
            findings=findings,
            error_count=failed + errors,
            details={
                "tool": "pytest",
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "pass_rate": pass_rate,
                "min_pass_rate": self.min_pass_rate
            }
        )

    def _run_jest(self, artifact_path: str, cwd: str) -> GateResult:
        """Run jest"""
        if not self._check_tool_available("jest") or not self._check_tool_available("npx"):
            return GateResult(
                gate_name=self.name(),
                status="warn",
                details={"message": "jest not available"}
            )

        cmd = ["npx", "jest", "--passWithNoTests", "--json"]
        exit_code, stdout, stderr = self._run_command(cmd, cwd=cwd, timeout=300)

        try:
            result = json.loads(stdout)
            passed = result.get('success', 0)
            failed = result.get('numFailedTests', 0)
            total = passed + failed
            pass_rate = passed / total if total > 0 else 0
        except json.JSONDecodeError:
            passed = len(re.findall(r'PASS', stdout))
            failed = len(re.findall(r'FAIL', stdout))
            total = passed + failed
            pass_rate = passed / total if total > 0 else 0

        status = "fail" if pass_rate < self.min_pass_rate else "pass"

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=GateSeverity.HIGH.value if failed > 0 else None,
            error_count=failed,
            details={"tool": "jest", "pass_rate": pass_rate}
        )

    def _run_go_test(self, artifact_path: str, cwd: str) -> GateResult:
        """Run go test"""
        if not self._check_tool_available("go"):
            return GateResult(
                gate_name=self.name(),
                status="warn",
                details={"message": "go not available"}
            )

        cmd = ["go", "test", "-v", "./..."]
        exit_code, stdout, stderr = self._run_command(cmd, cwd=cwd, timeout=300)

        passed = len(re.findall(r'PASS', stdout))
        failed = len(re.findall(r'FAIL', stdout))
        total = passed + failed
        pass_rate = passed / total if total > 0 else 0

        status = "fail" if pass_rate < self.min_pass_rate else "pass"

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=GateSeverity.HIGH.value if failed > 0 else None,
            error_count=failed,
            details={"tool": "go test", "pass_rate": pass_rate}
        )


# Alias for backward compatibility
TestGate = TestExecutionGate