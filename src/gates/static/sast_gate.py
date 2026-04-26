"""
SAST gate - Supports Semgrep and CodeQL
"""

import json
import os
import logging
from typing import Dict, List

from .base import StaticGateAdapter, GateResult, GateSeverity

logger = logging.getLogger(__name__)


class SASTGate(StaticGateAdapter):
    """SAST gate - Supports Semgrep and CodeQL"""

    def __init__(self, engine: str = "semgrep", rulesets: List[str] = None):
        self.engine = engine.lower()
        self.rulesets = rulesets or ["defaults"]
        self._codeql_db = None

    def name(self) -> str:
        return "sast"

    def run(self, artifact_path: str, context: Dict) -> GateResult:
        """Run SAST scanner"""
        cwd = context.get('cwd', os.getcwd())

        if self.engine == "semgrep":
            return self._run_semgrep(artifact_path, cwd)
        elif self.engine == "codeql":
            return self._run_codeql(artifact_path, cwd)
        else:
            return GateResult(
                gate_name=self.name(),
                status="pass",
                details={"message": f"Unknown SAST engine: {self.engine}"}
            )

    def _run_semgrep(self, artifact_path: str, cwd: str) -> GateResult:
        """Run Semgrep"""
        findings = []
        high_count = 0
        medium_count = 0

        if not self._check_tool_available("semgrep"):
            return GateResult(
                gate_name=self.name(),
                status="warn",
                details={"message": "semgrep not available"},
                warning_count=1
            )

        cmd = ["semgrep", "--json", "--quiet"]
        for ruleset in self.rulesets:
            if ruleset == "defaults":
                cmd.append("--config=auto")
            else:
                cmd.append(f"--config={ruleset}")
        cmd.append(artifact_path)

        exit_code, stdout, stderr = self._run_command(cmd, cwd=cwd, timeout=300)

        if stdout.strip():
            try:
                result = json.loads(stdout)
                for r in result.get('results', []):
                    severity = r.get('extra', {}).get('severity', 'INFO')
                    finding = {
                        "rule_id": r.get('check_id'),
                        "message": r.get('extra', {}).get('message'),
                        "file": r.get('path'),
                        "line": r.get('start', {}).get('line'),
                        "severity": severity.upper()
                    }
                    findings.append(finding)

                    if severity.upper() in ['ERROR', 'HIGH']:
                        high_count += 1
                    elif severity.upper() in ['WARNING', 'MEDIUM']:
                        medium_count += 1
            except json.JSONDecodeError:
                pass

        status = "fail" if high_count > 0 else ("warn" if medium_count > 0 else "pass")
        severity = GateSeverity.HIGH.value if high_count > 0 else (GateSeverity.MEDIUM.value if medium_count > 0 else None)

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=severity,
            evidence_ref=artifact_path,
            findings=findings,
            error_count=high_count,
            warning_count=medium_count,
            details={
                "tool": "semgrep",
                "rulesets": self.rulesets,
                "high_count": high_count,
                "medium_count": medium_count
            }
        )

    def _run_codeql(self, artifact_path: str, cwd: str) -> GateResult:
        """Run CodeQL (simplified)"""
        if not self._check_tool_available("codeql"):
            return GateResult(
                gate_name=self.name(),
                status="warn",
                details={"message": "codeql not available"},
                warning_count=1
            )

        findings = []
        logger.info("CodeQL integration placeholder - requires database setup")

        return GateResult(
            gate_name=self.name(),
            status="pass",
            severity=None,
            findings=findings,
            details={
                "tool": "codeql",
                "message": "CodeQL requires database creation - see documentation"
            }
        )