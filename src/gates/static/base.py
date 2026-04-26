"""
Base classes for static gates
"""

import subprocess
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class GateSeverity(Enum):
    """Severity levels for gate findings"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class GateResult:
    """Result from a static gate execution"""
    gate_name: str
    status: str  # pass, fail, warn
    severity: Optional[str] = None  # low, medium, high, critical
    evidence_ref: Optional[str] = None
    details: Optional[Dict] = None
    findings: List[Dict] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0


class StaticGateAdapter(ABC):
    """Base class for static gate adapters"""

    @abstractmethod
    def run(self, artifact_path: str, context: Dict) -> GateResult:
        """Execute the gate and return result"""
        pass

    @abstractmethod
    def name(self) -> str:
        """Return gate name"""
        pass

    def _run_command(
        self,
        cmd: List[str],
        cwd: str = None,
        timeout: int = 120,
        capture_output: bool = True
    ) -> Tuple[int, str, str]:
        """
        Run external command safely

        Returns: (exit_code, stdout, stderr)
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                timeout=timeout,
                capture_output=capture_output,
                text=True
            )
            return result.returncode, result.stdout or "", result.stderr or ""
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {cmd}")
            return -1, "", "Timeout expired"
        except FileNotFoundError:
            logger.error(f"Command not found: {cmd[0]}")
            return -2, "", f"Command not found: {cmd[0]}"
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return -3, "", str(e)

    def _check_tool_available(self, tool: str) -> bool:
        """Check if external tool is available"""
        try:
            result = subprocess.run(
                [tool, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0 or result.returncode in [0, 1, 2]
        except Exception:
            return False