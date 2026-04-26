"""
Static gate runner - Execute all gates and aggregate results
"""

import logging
from typing import Dict, List

from .base import StaticGateAdapter, GateResult, GateSeverity
from .lint_gate import LintGate
from .typecheck_gate import TypeCheckGate
from .test_gate import TestExecutionGate
from .sast_gate import SASTGate
from .secret_gate import SecretScanGate
from .license_gate import LicenseGate
from .tool_policy_gate import ToolPolicyGate

logger = logging.getLogger(__name__)


class StaticGateRunner:
    """Run all static gates in sequence"""

    def __init__(self, gates: List[StaticGateAdapter] = None):
        self.gates = gates or [
            LintGate(),
            TypeCheckGate(),
            TestExecutionGate(),
            SASTGate(),
            SecretScanGate(),
            LicenseGate(),
            ToolPolicyGate(),
        ]

    def run_all(self, artifact_path: str, context: Dict) -> List[GateResult]:
        """Execute all gates and return results"""
        results = []
        for gate in self.gates:
            try:
                result = gate.run(artifact_path, context)
                results.append(result)
            except Exception as e:
                logger.error(f"Gate {gate.name()} failed: {e}")
                results.append(GateResult(
                    gate_name=gate.name(),
                    status="warn",
                    severity=GateSeverity.LOW.value,
                    details={"error": str(e)}
                ))
        return results

    def has_hard_fail(self, results: List[GateResult]) -> bool:
        """Check if any gate has hard fail"""
        return any(r.status == "fail" for r in results)

    def get_failures(self, results: List[GateResult]) -> List[GateResult]:
        """Get all failed gates"""
        return [r for r in results if r.status == "fail"]

    def get_warnings(self, results: List[GateResult]) -> List[GateResult]:
        """Get all warning gates"""
        return [r for r in results if r.status == "warn"]

    def to_rule_violation(self, results: List[GateResult]) -> Dict:
        """
        Convert gate results to rule_violation dict for state vector

        Returns dict with counts for each violation type
        """
        violation = {
            "lint": 0,
            "typecheck": 0,
            "tests": 0,
            "sast_high": 0,
            "sast_medium": 0,
            "secret": 0,
            "license_forbidden": 0,
            "license_unknown": 0,
            "tool_policy_deny": 0,
        }

        for r in results:
            gate_name = r.gate_name
            if gate_name == "lint":
                violation["lint"] = r.error_count
            elif gate_name == "typecheck":
                violation["typecheck"] = r.error_count
            elif gate_name == "tests":
                violation["tests"] = r.error_count
            elif gate_name == "sast":
                violation["sast_high"] = r.error_count
                violation["sast_medium"] = r.warning_count
            elif gate_name == "secret_scan":
                violation["secret"] = r.error_count
            elif gate_name == "license_scan":
                violation["license_forbidden"] = r.error_count
                violation["license_unknown"] = r.warning_count
            elif gate_name == "tool_policy":
                violation["tool_policy_deny"] = r.error_count

        return violation


def create_static_gates_from_config(config: Dict) -> List[StaticGateAdapter]:
    """
    Create static gates from configuration

    Args:
        config: Dict with static_gates configuration

    Returns:
        List of configured gate adapters
    """
    gates = []
    static_config = config.get('static_gates', {})

    if static_config.get('lint', {}).get('enabled'):
        gates.append(LintGate(
            language=static_config['lint'].get('language', 'python'),
            config_file=static_config['lint'].get('config_file')
        ))

    if static_config.get('typecheck', {}).get('enabled'):
        gates.append(TypeCheckGate(
            language=static_config['typecheck'].get('language', 'python')
        ))

    if static_config.get('tests', {}).get('enabled'):
        gates.append(TestExecutionGate(
            min_pass_rate=static_config['tests'].get('min_pass_rate', 1.0)
        ))

    if static_config.get('sast', {}).get('enabled'):
        gates.append(SASTGate(
            engine=static_config['sast'].get('engine', 'semgrep'),
            rulesets=static_config['sast'].get('rulesets', ['defaults'])
        ))

    if static_config.get('secret_scan', {}).get('enabled'):
        gates.append(SecretScanGate(
            engine=static_config['secret_scan'].get('engine', 'trivy')
        ))

    if static_config.get('license_scan', {}).get('enabled'):
        gates.append(LicenseGate(
            engine=static_config['license_scan'].get('engine', 'trivy'),
            forbidden_licenses=static_config['license_scan'].get('forbidden_licenses')
        ))

    if static_config.get('tool_policy', {}).get('enabled'):
        gates.append(ToolPolicyGate(
            deny_patterns=static_config['tool_policy'].get('deny_patterns'),
            allow_patterns=static_config['tool_policy'].get('allow_patterns')
        ))

    return gates