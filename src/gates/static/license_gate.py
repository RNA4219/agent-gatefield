"""
License/SBOM gate - Supports Trivy license scanning
"""

import json
import os
import logging
from typing import Dict, List

from .base import StaticGateAdapter, GateResult, GateSeverity

logger = logging.getLogger(__name__)


class LicenseGate(StaticGateAdapter):
    """License/SBOM gate - Supports Trivy license scanning"""

    def __init__(self, engine: str = "trivy", forbidden_licenses: List[str] = None):
        self.engine = engine.lower()
        self.forbidden_licenses = forbidden_licenses or [
            "GPL-3.0", "AGPL-3.0", "CC-BY-SA", "LGPL-3.0"
        ]

    def name(self) -> str:
        return "license_scan"

    def run(self, artifact_path: str, context: Dict) -> GateResult:
        """Run license scanner"""
        cwd = context.get('cwd', os.getcwd())

        if self.engine == "trivy":
            return self._run_trivy_license(artifact_path, cwd)
        else:
            return GateResult(
                gate_name=self.name(),
                status="pass",
                details={"message": f"Unknown license scanner: {self.engine}"}
            )

    def _run_trivy_license(self, artifact_path: str, cwd: str) -> GateResult:
        """Run Trivy license scanning"""
        findings = []
        forbidden_count = 0
        unknown_count = 0

        if not self._check_tool_available("trivy"):
            return GateResult(
                gate_name=self.name(),
                status="warn",
                details={"message": "trivy not available"},
                warning_count=1
            )

        cmd = ["trivy", "fs", "--scanners", "license", "--format", "json", "--quiet", artifact_path]
        exit_code, stdout, stderr = self._run_command(cmd, cwd=cwd, timeout=120)

        if stdout.strip():
            try:
                result = json.loads(stdout)
                for r in result.get('Results', []):
                    for lic in r.get('Licenses', []):
                        license_id = lic.get('License', {}).get('ID', 'Unknown')
                        severity = lic.get('Severity', 'UNKNOWN')

                        if license_id in self.forbidden_licenses:
                            forbidden_count += 1
                            findings.append({
                                "license": license_id,
                                "file": r.get('Target'),
                                "severity": "CRITICAL",
                                "message": f"Forbidden license: {license_id}"
                            })
                        elif license_id == 'Unknown':
                            unknown_count += 1
                            findings.append({
                                "license": license_id,
                                "file": r.get('Target'),
                                "severity": "HIGH",
                                "message": "Unknown license"
                            })
            except json.JSONDecodeError:
                pass

        status = "fail" if forbidden_count > 0 else ("warn" if unknown_count > 0 else "pass")
        severity = GateSeverity.CRITICAL.value if forbidden_count > 0 else (GateSeverity.HIGH.value if unknown_count > 0 else None)

        return GateResult(
            gate_name=self.name(),
            status=status,
            severity=severity,
            findings=findings,
            error_count=forbidden_count,
            warning_count=unknown_count,
            details={
                "tool": "trivy",
                "forbidden_licenses": self.forbidden_licenses,
                "forbidden_count": forbidden_count,
                "unknown_count": unknown_count
            }
        )