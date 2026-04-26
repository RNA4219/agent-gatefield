"""
Static Gate Adapters - External scanner integration

This module provides:
- Base classes: GateSeverity, GateResult, StaticGateAdapter
- Gate adapters: LintGate, TypeCheckGate, TestExecutionGate, SASTGate, SecretScanGate, LicenseGate, ToolPolicyGate
- Runner: StaticGateRunner, create_static_gates_from_config
"""

from .base import GateSeverity, GateResult, StaticGateAdapter
from .lint_gate import LintGate
from .typecheck_gate import TypeCheckGate
from .test_gate import TestExecutionGate, TestGate  # TestGate is alias for backward compatibility
from .sast_gate import SASTGate
from .secret_gate import SecretScanGate
from .license_gate import LicenseGate
from .tool_policy_gate import ToolPolicyGate
from .runner import StaticGateRunner, create_static_gates_from_config

__all__ = [
    # Base classes
    'GateSeverity',
    'GateResult',
    'StaticGateAdapter',
    # Gate adapters
    'LintGate',
    'TypeCheckGate',
    'TestExecutionGate',
    'TestGate',  # Alias for backward compatibility
    'SASTGate',
    'SecretScanGate',
    'LicenseGate',
    'ToolPolicyGate',
    # Runner
    'StaticGateRunner',
    'create_static_gates_from_config',
]