"""
Secret scanning gate - Supports Trivy and Gitleaks
"""

import json
import os
import logging
from typing import Dict

from .base import StaticGateAdapter, GateResult, GateSeverity

logger = logging.getLogger(__name__)


class SecretScanGate(StaticGateAdapter):
    """Secret scanning gate - Supports Trivy and Gitleaks"""

    def __init__(self, engine: str = "trivy"):
        self.engine = engine.lower()

    def name(self) -> str:
        return "secret_scan"

    def run(self, artifact_path: str, context: Dict) -> GateResult:
        """Run secret scanner - Block on any secret found"""
        cwd = context.get('cwd', os.getcwd())

        if self.engine == "trivy":
            return self._run_trivy_secret(artifact_path, cwd)
        elif self.engine == "gitleaks":
            return self._run_gitleaks(artifact_path, cwd)
        else:
            return GateResult(
                gate_name=self.name(),
                status="pass",
                details={"message": f"Unknown secret scanner: {self.engine}"}
            )

    def _run_trivy_secret(self, artifact_path: str, cwd: str) -> GateResult:
        """Run Trivy secret scanning"""
        findings = []

        if not self._check_tool_available("trivy"):
            return GateResult(
                gate_name=self.name(),
                status="warn",
                details={"message": "trivy not available"},
                warning_count=1
            )

        cmd = ["trivy", "fs", "--scanners", "secret", "--format", "json", "--quiet", artifact_path]
        exit_code, stdout, stderr = self._run_command(cmd, cwd=cwd, timeout=120)

        secret_count = 0
        if stdout.strip():
            try:
                result = json.loads(stdout)
                for r in result.get('Results', []):
                    for misconf in r.get('Misconfigurations', []):
                        if misconf.get('Category') == 'secret':
                            secret_count += 1
                            findings.append({
                                "type": "secret",
                                "file": r.get('Target'),
                                "severity": misconf.get('Severity'),
                                "message": misconf.get('Title')
                            })
            except json.JSONDecodeError:
                pass

        status = "fail" if secret_count > 0 else "pass"
        severity = GateSeverity.CRITICAL.value if secret_count > 0 else None

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=severity,
            evidence_ref=artifact_path,
            findings=findings,
            error_count=secret_count,
            details={
                "tool": "trivy",
                "secret_count": secret_count,
                "block_on_secret": True
            }
        )

    def _run_gitleaks(self, artifact_path: str, cwd: str) -> GateResult:
        """Run Gitleaks"""
        findings = []

        if not self._check_tool_available("gitleaks"):
            return GateResult(
                gate_name=self.name(),
                status="warn",
                details={"message": "gitleaks not available"},
                warning_count=1
            )

        cmd = ["gitleaks", "detect", "--source", artifact_path, "--report-format", "json", "--no-git"]
        exit_code, stdout, stderr = self._run_command(cmd, cwd=cwd, timeout=120)

        secret_count = 0
        if stdout.strip():
            try:
                result = json.loads(stdout)
                for leak in result:
                    secret_count += 1
                    findings.append({
                        "type": "secret",
                        "file": leak.get('File'),
                        "line": leak.get('StartLine'),
                        "rule": leak.get('RuleID'),
                        "severity": "CRITICAL"
                    })
            except json.JSONDecodeError:
                secret_count = 1 if exit_code == 1 else 0

        status = "fail" if secret_count > 0 else "pass"
        severity = GateSeverity.CRITICAL.value if secret_count > 0 else None

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=severity,
            findings=findings,
            error_count=secret_count,
            details={"tool": "gitleaks", "secret_count": secret_count}
        )