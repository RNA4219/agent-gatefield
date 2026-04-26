"""
Unit tests for Static Gate Adapters

Tests cover:
- LintGate (pylint, eslint)
- SASTGate (semgrep patterns)
- SecretScanGate (trivy patterns)
- LicenseGate
- ToolPolicyGate (deny patterns)
- StaticGateRunner.run_all()
- Hard fail detection
- evidence_ref generation

Uses mocking for subprocess calls to achieve 90%+ coverage.
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.gates.static import (
    GateSeverity,
    GateResult,
    StaticGateAdapter,
    LintGate,
    TypeCheckGate,
    TestExecutionGate,
    SASTGate,
    SecretScanGate,
    LicenseGate,
    ToolPolicyGate,
    StaticGateRunner,
    create_static_gates_from_config,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for all tests"""
    with patch('src.gates.static.base.subprocess.run') as mock_run:
        yield mock_run


@pytest.fixture
def temp_artifact():
    """Create a temporary artifact file for testing"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("def test_function():\n    pass\n")
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def temp_js_artifact():
    """Create a temporary JavaScript artifact file for testing"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
        f.write("function testFunction() { return true; }\n")
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def temp_tool_calls_file():
    """Create a temporary file with tool calls"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(json.dumps([
            {"command": "ls -la"},
            {"command": "cat file.txt"}
        ]))
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def mock_context():
    """Standard mock context for gate execution"""
    return {
        'cwd': '/tmp/test',
        'run_id': 'test-run-001',
        'artifact_id': 'test-artifact-001'
    }


# ============================================================================
# GateSeverity Tests
# ============================================================================

class TestGateSeverity:
    """Tests for GateSeverity enum"""

    def test_severity_values(self):
        """Test all severity level values"""
        assert GateSeverity.LOW.value == "low"
        assert GateSeverity.MEDIUM.value == "medium"
        assert GateSeverity.HIGH.value == "high"
        assert GateSeverity.CRITICAL.value == "critical"

    def test_severity_count(self):
        """Test that we have 4 severity levels"""
        assert len(list(GateSeverity)) == 4


# ============================================================================
# GateResult Tests
# ============================================================================

class TestGateResult:
    """Tests for GateResult dataclass"""

    def test_basic_result(self):
        """Test basic GateResult creation"""
        result = GateResult(
            gate_name="test_gate",
            status="pass"
        )
        assert result.gate_name == "test_gate"
        assert result.status == "pass"
        assert result.findings == []
        assert result.error_count == 0
        assert result.warning_count == 0

    def test_result_with_findings(self):
        """Test GateResult with findings"""
        findings = [{"rule": "test-rule", "message": "test message"}]
        result = GateResult(
            gate_name="test_gate",
            status="fail",
            severity=GateSeverity.HIGH.value,
            evidence_ref="test_ref",
            findings=findings,
            error_count=1
        )
        assert result.gate_name == "test_gate"
        assert result.status == "fail"
        assert result.severity == "high"
        assert result.evidence_ref == "test_ref"
        assert len(result.findings) == 1
        assert result.error_count == 1

    def test_result_with_details(self):
        """Test GateResult with details dict"""
        details = {"tool": "pylint", "language": "python"}
        result = GateResult(
            gate_name="lint",
            status="pass",
            details=details
        )
        assert result.details["tool"] == "pylint"
        assert result.details["language"] == "python"


# ============================================================================
# LintGate Tests (UT-HOV-004 related, AGF-REQ-002)
# ============================================================================

class TestLintGate:
    """Tests for LintGate adapter"""

    def test_name(self):
        """Test gate name"""
        gate = LintGate()
        assert gate.name() == "lint"

    def test_default_language(self):
        """Test default language is python"""
        gate = LintGate()
        assert gate.language == "python"

    def test_custom_language(self):
        """Test custom language setting"""
        gate = LintGate(language="javascript")
        assert gate.language == "javascript"

    def test_pylint_pass(self, mock_subprocess, temp_artifact, mock_context):
        """Test pylint pass scenario"""
        gate = LintGate(language="python")

        # Mock tool available check and pylint execution
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="[]",  # No findings
            stderr=""
        )

        result = gate.run(temp_artifact, mock_context)

        assert result.gate_name == "lint"
        assert result.status == "pass"
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.details["tool"] == "pylint"

    def test_pylint_errors(self, mock_subprocess, temp_artifact, mock_context):
        """Test pylint with errors - should fail"""
        gate = LintGate(language="python")

        pylint_output = json.dumps([
            {"type": "error", "module": "test", "message": "Test error", "line": 1}
        ])

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=pylint_output,
            stderr=""
        )

        result = gate.run(temp_artifact, mock_context)

        assert result.status == "fail"
        assert result.severity == GateSeverity.HIGH.value
        assert result.error_count == 1
        assert result.details["tool"] == "pylint"
        assert result.evidence_ref == temp_artifact

    def test_pylint_warnings(self, mock_subprocess, temp_artifact, mock_context):
        """Test pylint with warnings only - should warn"""
        gate = LintGate(language="python")

        pylint_output = json.dumps([
            {"type": "warning", "module": "test", "message": "Test warning", "line": 5}
        ])

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=pylint_output,
            stderr=""
        )

        result = gate.run(temp_artifact, mock_context)

        assert result.status == "warn"
        assert result.severity == GateSeverity.LOW.value
        assert result.warning_count == 1

    def test_pylint_mixed_findings(self, mock_subprocess, temp_artifact, mock_context):
        """Test pylint with mixed errors and warnings"""
        gate = LintGate(language="python")

        pylint_output = json.dumps([
            {"type": "error", "module": "test", "message": "Error 1", "line": 1},
            {"type": "warning", "module": "test", "message": "Warning 1", "line": 5},
            {"type": "convention", "module": "test", "message": "Convention 1", "line": 10},
        ])

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=pylint_output,
            stderr=""
        )

        result = gate.run(temp_artifact, mock_context)

        assert result.status == "fail"
        assert result.error_count == 1
        assert result.warning_count == 2  # warning + convention

    def test_pylint_fatal_error(self, mock_subprocess, temp_artifact, mock_context):
        """Test pylint fatal error - should fail"""
        gate = LintGate(language="python")

        pylint_output = json.dumps([
            {"type": "fatal", "module": "test", "message": "Fatal error", "line": 1}
        ])

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=pylint_output,
            stderr=""
        )

        result = gate.run(temp_artifact, mock_context)

        assert result.status == "fail"
        assert result.error_count == 1

    def test_pylint_not_available(self, mock_subprocess, temp_artifact, mock_context):
        """Test pylint not available - should warn"""
        gate = LintGate(language="python")

        # Mock tool not available (FileNotFoundError for --version check)
        mock_subprocess.side_effect = FileNotFoundError("pylint not found")

        result = gate.run(temp_artifact, mock_context)

        assert result.status == "warn"
        assert result.details["message"] == "pylint not available"

    def test_pylint_text_output_fallback(self, mock_subprocess, temp_artifact, mock_context):
        """Test pylint text output fallback parsing"""
        gate = LintGate(language="python")

        # Mock returns non-JSON text
        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout="E: 1: Test error\nW: 5: Test warning\nE: 10: Another error",
            stderr=""
        )

        result = gate.run(temp_artifact, mock_context)

        # Should parse text output
        assert result.status == "fail"
        assert result.error_count == 2
        assert result.warning_count == 1

    def test_eslint_pass(self, mock_subprocess, temp_js_artifact, mock_context):
        """Test eslint pass scenario"""
        gate = LintGate(language="javascript")

        eslint_output = json.dumps([{
            "filePath": temp_js_artifact,
            "messages": []
        }])

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=eslint_output,
            stderr=""
        )

        result = gate.run(temp_js_artifact, mock_context)

        assert result.gate_name == "lint"
        assert result.status == "pass"
        assert result.details["tool"] == "eslint"

    def test_eslint_errors(self, mock_subprocess, temp_js_artifact, mock_context):
        """Test eslint with errors - should fail"""
        gate = LintGate(language="javascript")

        eslint_output = json.dumps([{
            "filePath": temp_js_artifact,
            "messages": [
                {"ruleId": "no-unused-vars", "severity": 2, "message": "Unused var", "line": 5}
            ]
        }])

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=eslint_output,
            stderr=""
        )

        result = gate.run(temp_js_artifact, mock_context)

        assert result.status == "fail"
        assert result.severity == GateSeverity.HIGH.value
        assert result.error_count == 1
        assert len(result.findings) == 1
        assert result.findings[0]["severity"] == "error"

    def test_eslint_warnings(self, mock_subprocess, temp_js_artifact, mock_context):
        """Test eslint with warnings only - should warn"""
        gate = LintGate(language="javascript")

        eslint_output = json.dumps([{
            "filePath": temp_js_artifact,
            "messages": [
                {"ruleId": "no-console", "severity": 1, "message": "Console", "line": 10}
            ]
        }])

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=eslint_output,
            stderr=""
        )

        result = gate.run(temp_js_artifact, mock_context)

        assert result.status == "warn"
        assert result.warning_count == 1

    def test_eslint_not_available(self, mock_subprocess, temp_js_artifact, mock_context):
        """Test eslint not available"""
        gate = LintGate(language="javascript")

        mock_subprocess.side_effect = FileNotFoundError("eslint not found")

        result = gate.run(temp_js_artifact, mock_context)

        assert result.status == "warn"
        assert result.details["message"] == "eslint not available"

    def test_config_file_passed(self, mock_subprocess, temp_artifact, mock_context):
        """Test that config file is passed to pylint"""
        gate = LintGate(language="python", config_file=".pylintrc")

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="[]",
            stderr=""
        )

        result = gate.run(temp_artifact, mock_context)

        # Verify config file was in the command
        calls = mock_subprocess.call_args_list
        assert any("--rcfile" in str(call) for call in calls)

    def test_go_lint(self, mock_subprocess, mock_context):
        """Test golint for Go files"""
        gate = LintGate(language="go")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.go', delete=False) as f:
            f.write("package main\n")
            artifact = f.name

        try:
            mock_subprocess.return_value = Mock(
                returncode=0,
                stdout="test.go:5: warning message",
                stderr=""
            )

            result = gate.run(artifact, mock_context)

            assert result.gate_name == "lint"
            assert result.details["tool"] == "golint"
        finally:
            os.unlink(artifact)

    def test_unknown_language(self, mock_subprocess, mock_context):
        """Test unknown language returns pass"""
        gate = LintGate(language="rust")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write("fn main() {}\n")
            artifact = f.name

        try:
            result = gate.run(artifact, mock_context)

            assert result.status == "pass"
            assert "No lint tool configured" in result.details["message"]
        finally:
            os.unlink(artifact)

    def test_language_detection_from_extension(self, mock_subprocess, mock_context):
        """Test language detection from file extension"""
        gate = LintGate(language=None)  # No explicit language

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test(): pass\n")
            artifact = f.name

        try:
            mock_subprocess.return_value = Mock(
                returncode=0,
                stdout="[]",
                stderr=""
            )

            result = gate.run(artifact, mock_context)

            # Should detect Python from .py extension
            assert result.details["language"] == "python"
        finally:
            os.unlink(artifact)


# ============================================================================
# TypeCheckGate Tests
# ============================================================================

class TestTypeCheckGate:
    """Tests for TypeCheckGate adapter"""

    def test_name(self):
        """Test gate name"""
        gate = TypeCheckGate()
        assert gate.name() == "typecheck"

    def test_mypy_pass(self, mock_subprocess, mock_context):
        """Test mypy pass scenario"""
        gate = TypeCheckGate(language="python")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test(x: int) -> int: return x\n")
            artifact = f.name

        try:
            mock_subprocess.return_value = Mock(
                returncode=0,
                stdout="Success: no issues found",
                stderr=""
            )

            result = gate.run(artifact, mock_context)

            assert result.status == "pass"
            assert result.details["tool"] == "mypy"
        finally:
            os.unlink(artifact)

    def test_mypy_errors(self, mock_subprocess, mock_context):
        """Test mypy with type errors"""
        gate = TypeCheckGate(language="python")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test(x): return x  # No type hints\n")
            artifact = f.name

        try:
            mock_subprocess.return_value = Mock(
                returncode=1,
                stdout="test.py:1: error: Function is missing type annotation",
                stderr=""
            )

            result = gate.run(artifact, mock_context)

            assert result.status == "fail"
            assert result.error_count == 1
            assert result.severity == GateSeverity.HIGH.value
        finally:
            os.unlink(artifact)

    def test_mypy_not_available(self, mock_subprocess, mock_context):
        """Test mypy not available"""
        gate = TypeCheckGate(language="python")

        mock_subprocess.side_effect = FileNotFoundError("mypy not found")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test(): pass\n")
            artifact = f.name

        try:
            result = gate.run(artifact, mock_context)

            assert result.status == "warn"
            assert result.details["message"] == "mypy not available"
        finally:
            os.unlink(artifact)

    def test_tsc_pass(self, mock_subprocess, mock_context):
        """Test TypeScript compiler pass"""
        gate = TypeCheckGate(language="typescript")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', delete=False) as f:
            f.write("function test(x: number): number { return x; }\n")
            artifact = f.name

        try:
            mock_subprocess.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            result = gate.run(artifact, mock_context)

            assert result.status == "pass"
            assert result.details["tool"] == "tsc"
        finally:
            os.unlink(artifact)

    def test_tsc_errors(self, mock_subprocess, mock_context):
        """Test TypeScript compiler errors"""
        gate = TypeCheckGate(language="typescript")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', delete=False) as f:
            f.write("function test(x: string): number { return x; }\n")
            artifact = f.name

        try:
            mock_subprocess.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="test.ts(1,35): error TS2322: Type 'string' is not assignable to type 'number'"
            )

            result = gate.run(artifact, mock_context)

            assert result.status == "fail"
            assert result.error_count == 1
        finally:
            os.unlink(artifact)


# ============================================================================
# TestExecutionGate Tests
# ============================================================================

class TestTestExecutionGate:
    """Tests for TestExecutionGate adapter"""

    def test_name(self):
        """Test gate name"""
        gate = TestExecutionGate()
        assert gate.name() == "tests"

    def test_pytest_pass(self, mock_subprocess, mock_context):
        """Test pytest pass scenario"""
        gate = TestExecutionGate()

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="test_1 PASSED\ntest_2 PASSED\n3 passed in 0.1s",
            stderr=""
        )

        result = gate.run("tests/", mock_context)

        assert result.status == "pass"
        assert result.details["tool"] == "pytest"
        assert result.details["passed"] == 2

    def test_pytest_fail(self, mock_subprocess, mock_context):
        """Test pytest failure scenario"""
        gate = TestExecutionGate()

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout="test_1 PASSED\ntest_2 FAILED\ntest_3 ERROR\n",
            stderr=""
        )

        result = gate.run("tests/", mock_context)

        assert result.status == "fail"
        assert result.error_count == 2  # 1 failed + 1 error
        assert result.severity == GateSeverity.HIGH.value

    def test_pytest_min_pass_rate(self, mock_subprocess, mock_context):
        """Test pytest with minimum pass rate"""
        gate = TestExecutionGate(min_pass_rate=0.8)

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="test_1 PASSED\ntest_2 PASSED\ntest_3 PASSED\ntest_4 FAILED\n",
            stderr=""
        )

        result = gate.run("tests/", mock_context)

        # 3 passed, 1 failed = 0.75 pass rate < 0.8 threshold
        assert result.status == "fail"

    def test_pytest_min_pass_rate_met(self, mock_subprocess, mock_context):
        """Test pytest meeting minimum pass rate"""
        gate = TestExecutionGate(min_pass_rate=0.7)

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="test_1 PASSED\ntest_2 PASSED\ntest_3 PASSED\ntest_4 FAILED\n",
            stderr=""
        )

        result = gate.run("tests/", mock_context)

        # 3 passed, 1 failed = 0.75 pass rate >= 0.7 threshold
        assert result.status == "pass"

    def test_pytest_not_available(self, mock_subprocess, mock_context):
        """Test pytest not available"""
        gate = TestExecutionGate()

        mock_subprocess.side_effect = FileNotFoundError("pytest not found")

        result = gate.run("tests/", mock_context)

        assert result.status == "warn"
        assert result.details["message"] == "pytest not available"

    def test_jest_pass(self, mock_subprocess, mock_context):
        """Test jest pass scenario"""
        gate = TestExecutionGate(test_runner="jest")

        jest_output = json.dumps({
            "success": 5,
            "numFailedTests": 0
        })

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=jest_output,
            stderr=""
        )

        result = gate.run("tests/", mock_context)

        assert result.status == "pass"
        assert result.details["tool"] == "jest"

    def test_jest_fail(self, mock_subprocess, mock_context):
        """Test jest failure scenario"""
        gate = TestExecutionGate(test_runner="jest")

        jest_output = json.dumps({
            "success": 3,
            "numFailedTests": 2
        })

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=jest_output,
            stderr=""
        )

        result = gate.run("tests/", mock_context)

        assert result.status == "fail"
        assert result.error_count == 2

    def test_go_test_pass(self, mock_subprocess, mock_context):
        """Test go test pass scenario"""
        gate = TestExecutionGate(test_runner="go")

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="PASS\nPASS\nPASS\n",
            stderr=""
        )

        result = gate.run("./...", mock_context)

        assert result.status == "pass"
        assert result.details["tool"] == "go test"


# ============================================================================
# SASTGate Tests (AGF-REQ-002)
# ============================================================================

class TestSASTGate:
    """Tests for SASTGate adapter"""

    def test_name(self):
        """Test gate name"""
        gate = SASTGate()
        assert gate.name() == "sast"

    def test_default_engine(self):
        """Test default engine is semgrep"""
        gate = SASTGate()
        assert gate.engine == "semgrep"

    def test_custom_engine(self):
        """Test custom engine setting"""
        gate = SASTGate(engine="codeql")
        assert gate.engine == "codeql"

    def test_semgrep_pass(self, mock_subprocess, mock_context):
        """Test semgrep pass scenario"""
        gate = SASTGate(engine="semgrep")

        semgrep_output = json.dumps({"results": []})

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=semgrep_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "pass"
        assert result.details["tool"] == "semgrep"
        assert result.details["high_count"] == 0

    def test_semgrep_high_severity(self, mock_subprocess, mock_context):
        """Test semgrep high severity finding - should fail"""
        gate = SASTGate(engine="semgrep")

        semgrep_output = json.dumps({
            "results": [
                {
                    "check_id": "python.lang.security.audit.dangerous-subprocess-use",
                    "path": "test.py",
                    "start": {"line": 10},
                    "extra": {
                        "severity": "ERROR",
                        "message": "Dangerous subprocess use"
                    }
                }
            ]
        })

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=semgrep_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "fail"
        assert result.severity == GateSeverity.HIGH.value
        assert result.error_count == 1
        assert result.evidence_ref == "."
        assert len(result.findings) == 1
        assert result.findings[0]["severity"] == "ERROR"

    def test_semgrep_medium_severity(self, mock_subprocess, mock_context):
        """Test semgrep medium severity finding - should warn"""
        gate = SASTGate(engine="semgrep")

        semgrep_output = json.dumps({
            "results": [
                {
                    "check_id": "python.lang.best-practice.use-isinstance",
                    "path": "test.py",
                    "start": {"line": 5},
                    "extra": {
                        "severity": "WARNING",
                        "message": "Use isinstance"
                    }
                }
            ]
        })

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=semgrep_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "warn"
        assert result.severity == GateSeverity.MEDIUM.value
        assert result.warning_count == 1

    def test_semgrep_multiple_findings(self, mock_subprocess, mock_context):
        """Test semgrep with multiple findings"""
        gate = SASTGate(engine="semgrep")

        semgrep_output = json.dumps({
            "results": [
                {
                    "check_id": "rule1",
                    "path": "test.py",
                    "start": {"line": 10},
                    "extra": {"severity": "ERROR", "message": "Error 1"}
                },
                {
                    "check_id": "rule2",
                    "path": "test.py",
                    "start": {"line": 20},
                    "extra": {"severity": "WARNING", "message": "Warning 1"}
                },
                {
                    "check_id": "rule3",
                    "path": "test.py",
                    "start": {"line": 30},
                    "extra": {"severity": "HIGH", "message": "High 1"}
                },
            ]
        })

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=semgrep_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "fail"
        # ERROR + HIGH should count as high severity
        assert result.error_count == 2
        assert result.warning_count == 1

    def test_semgrep_custom_rulesets(self, mock_subprocess, mock_context):
        """Test semgrep with custom rulesets"""
        gate = SASTGate(engine="semgrep", rulesets=["p/python", "p/security"])

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=json.dumps({"results": []}),
            stderr=""
        )

        result = gate.run(".", mock_context)

        # Check rulesets in details
        assert result.details["rulesets"] == ["p/python", "p/security"]

    def test_semgrep_not_available(self, mock_subprocess, mock_context):
        """Test semgrep not available"""
        gate = SASTGate(engine="semgrep")

        mock_subprocess.side_effect = FileNotFoundError("semgrep not found")

        result = gate.run(".", mock_context)

        assert result.status == "warn"
        assert result.details["message"] == "semgrep not available"

    def test_codeql_placeholder(self, mock_subprocess, mock_context):
        """Test CodeQL placeholder behavior"""
        gate = SASTGate(engine="codeql")

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="",
            stderr=""
        )

        result = gate.run(".", mock_context)

        # CodeQL is placeholder for MVP
        assert result.status == "pass"
        assert result.details["tool"] == "codeql"

    def test_unknown_engine(self, mock_subprocess, mock_context):
        """Test unknown SAST engine"""
        gate = SASTGate(engine="unknown")

        result = gate.run(".", mock_context)

        assert result.status == "pass"
        assert "Unknown SAST engine" in result.details["message"]

    def test_semgrep_json_parse_error(self, mock_subprocess, mock_context):
        """Test semgrep handles JSON parse error"""
        gate = SASTGate(engine="semgrep")

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="invalid json output",
            stderr=""
        )

        result = gate.run(".", mock_context)

        # Should gracefully handle parse error
        assert result.status == "pass"


# ============================================================================
# SecretScanGate Tests (AGF-REQ-002, UT-HOV-001)
# ============================================================================

class TestSecretScanGate:
    """Tests for SecretScanGate adapter"""

    def test_name(self):
        """Test gate name"""
        gate = SecretScanGate()
        assert gate.name() == "secret_scan"

    def test_default_engine(self):
        """Test default engine is trivy"""
        gate = SecretScanGate()
        assert gate.engine == "trivy"

    def test_trivy_pass(self, mock_subprocess, mock_context):
        """Test trivy secret scan pass"""
        gate = SecretScanGate(engine="trivy")

        trivy_output = json.dumps({"Results": []})

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=trivy_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "pass"
        assert result.details["tool"] == "trivy"
        assert result.details["secret_count"] == 0

    def test_trivy_secret_found_hard_fail(self, mock_subprocess, mock_context):
        """Test trivy secret found - should hard fail (CRITICAL)"""
        gate = SecretScanGate(engine="trivy")

        trivy_output = json.dumps({
            "Results": [
                {
                    "Target": "config.yaml",
                    "Misconfigurations": [
                        {
                            "Category": "secret",
                            "Severity": "CRITICAL",
                            "Title": "AWS Access Key detected"
                        }
                    ]
                }
            ]
        })

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=trivy_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        # Secrets should trigger hard fail
        assert result.status == "fail"
        assert result.severity == GateSeverity.CRITICAL.value
        assert result.error_count == 1
        assert result.details["block_on_secret"] == True
        assert result.evidence_ref == "."
        assert len(result.findings) == 1
        assert result.findings[0]["type"] == "secret"

    def test_trivy_multiple_secrets(self, mock_subprocess, mock_context):
        """Test trivy with multiple secrets"""
        gate = SecretScanGate(engine="trivy")

        trivy_output = json.dumps({
            "Results": [
                {
                    "Target": "file1.yaml",
                    "Misconfigurations": [
                        {"Category": "secret", "Severity": "CRITICAL", "Title": "AWS Key"}
                    ]
                },
                {
                    "Target": "file2.yaml",
                    "Misconfigurations": [
                        {"Category": "secret", "Severity": "HIGH", "Title": "API Key"}
                    ]
                }
            ]
        })

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=trivy_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "fail"
        assert result.error_count == 2

    def test_trivy_not_available(self, mock_subprocess, mock_context):
        """Test trivy not available"""
        gate = SecretScanGate(engine="trivy")

        mock_subprocess.side_effect = FileNotFoundError("trivy not found")

        result = gate.run(".", mock_context)

        assert result.status == "warn"
        assert result.details["message"] == "trivy not available"

    def test_gitleaks_pass(self, mock_subprocess, mock_context):
        """Test gitleaks pass"""
        gate = SecretScanGate(engine="gitleaks")

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="[]",
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "pass"
        assert result.details["tool"] == "gitleaks"

    def test_gitleaks_secret_found(self, mock_subprocess, mock_context):
        """Test gitleaks secret found - should hard fail"""
        gate = SecretScanGate(engine="gitleaks")

        gitleaks_output = json.dumps([
            {
                "File": "config.py",
                "StartLine": 10,
                "RuleID": "aws-access-key",
            }
        ])

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=gitleaks_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "fail"
        assert result.severity == GateSeverity.CRITICAL.value
        assert result.error_count == 1
        assert result.findings[0]["severity"] == "CRITICAL"

    def test_gitleaks_not_available(self, mock_subprocess, mock_context):
        """Test gitleaks not available"""
        gate = SecretScanGate(engine="gitleaks")

        mock_subprocess.side_effect = FileNotFoundError("gitleaks not found")

        result = gate.run(".", mock_context)

        assert result.status == "warn"

    def test_unknown_engine(self, mock_subprocess, mock_context):
        """Test unknown secret scanner engine"""
        gate = SecretScanGate(engine="unknown")

        result = gate.run(".", mock_context)

        assert result.status == "pass"
        assert "Unknown secret scanner" in result.details["message"]


# ============================================================================
# LicenseGate Tests (AGF-REQ-002)
# ============================================================================

class TestLicenseGate:
    """Tests for LicenseGate adapter"""

    def test_name(self):
        """Test gate name"""
        gate = LicenseGate()
        assert gate.name() == "license_scan"

    def test_default_forbidden_licenses(self):
        """Test default forbidden licenses"""
        gate = LicenseGate()
        assert "GPL-3.0" in gate.forbidden_licenses
        assert "AGPL-3.0" in gate.forbidden_licenses

    def test_custom_forbidden_licenses(self):
        """Test custom forbidden licenses"""
        gate = LicenseGate(forbidden_licenses=["GPL-2.0", "Proprietary"])
        assert gate.forbidden_licenses == ["GPL-2.0", "Proprietary"]

    def test_trivy_pass(self, mock_subprocess, mock_context):
        """Test trivy license scan pass"""
        gate = LicenseGate(engine="trivy")

        trivy_output = json.dumps({"Results": []})

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=trivy_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "pass"
        assert result.details["tool"] == "trivy"

    def test_trivy_forbidden_license(self, mock_subprocess, mock_context):
        """Test trivy forbidden license found - should fail"""
        gate = LicenseGate(engine="trivy")

        trivy_output = json.dumps({
            "Results": [
                {
                    "Target": "package.json",
                    "Licenses": [
                        {
                            "License": {"ID": "GPL-3.0"},
                            "Severity": "CRITICAL"
                        }
                    ]
                }
            ]
        })

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=trivy_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "fail"
        assert result.severity == GateSeverity.CRITICAL.value
        assert result.error_count == 1
        assert len(result.findings) == 1
        assert result.findings[0]["severity"] == "CRITICAL"
        assert "Forbidden license" in result.findings[0]["message"]

    def test_trivy_unknown_license(self, mock_subprocess, mock_context):
        """Test trivy unknown license - should warn"""
        gate = LicenseGate(engine="trivy")

        trivy_output = json.dumps({
            "Results": [
                {
                    "Target": "package.json",
                    "Licenses": [
                        {
                            "License": {"ID": "Unknown"},
                            "Severity": "HIGH"
                        }
                    ]
                }
            ]
        })

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=trivy_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "warn"
        assert result.severity == GateSeverity.HIGH.value
        assert result.warning_count == 1

    def test_trivy_mixed_licenses(self, mock_subprocess, mock_context):
        """Test trivy with mixed license findings"""
        gate = LicenseGate(engine="trivy")

        trivy_output = json.dumps({
            "Results": [
                {
                    "Target": "pkg1",
                    "Licenses": [
                        {"License": {"ID": "GPL-3.0"}, "Severity": "CRITICAL"}
                    ]
                },
                {
                    "Target": "pkg2",
                    "Licenses": [
                        {"License": {"ID": "Unknown"}, "Severity": "HIGH"}
                    ]
                },
                {
                    "Target": "pkg3",
                    "Licenses": [
                        {"License": {"ID": "MIT"}, "Severity": "LOW"}
                    ]
                }
            ]
        })

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=trivy_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        # Forbidden license should cause fail
        assert result.status == "fail"
        assert result.error_count == 1  # GPL-3.0
        assert result.warning_count == 1  # Unknown

    def test_trivy_not_available(self, mock_subprocess, mock_context):
        """Test trivy not available"""
        gate = LicenseGate(engine="trivy")

        mock_subprocess.side_effect = FileNotFoundError("trivy not found")

        result = gate.run(".", mock_context)

        assert result.status == "warn"
        assert result.details["message"] == "trivy not available"

    def test_unknown_engine(self, mock_subprocess, mock_context):
        """Test unknown license scanner engine"""
        gate = LicenseGate(engine="unknown")

        result = gate.run(".", mock_context)

        assert result.status == "pass"
        assert "Unknown license scanner" in result.details["message"]


# ============================================================================
# ToolPolicyGate Tests (AGF-REQ-002, UT-HOV-005)
# ============================================================================

class TestToolPolicyGate:
    """Tests for ToolPolicyGate adapter"""

    def test_name(self):
        """Test gate name"""
        gate = ToolPolicyGate()
        assert gate.name() == "tool_policy"

    def test_default_deny_patterns(self):
        """Test default deny patterns"""
        gate = ToolPolicyGate()
        assert "rm -rf /" in gate.deny_patterns
        assert "DROP DATABASE" in gate.deny_patterns
        assert "kubectl delete --all" in gate.deny_patterns

    def test_custom_deny_patterns(self):
        """Test custom deny patterns"""
        gate = ToolPolicyGate(deny_patterns=["custom-dangerous-cmd"])
        assert "custom-dangerous-cmd" in gate.deny_patterns

    def test_pass_no_tool_calls(self, mock_context):
        """Test pass when no tool calls"""
        gate = ToolPolicyGate()

        result = gate.run("", mock_context)

        assert result.status == "pass"
        assert result.error_count == 0

    def test_pass_safe_commands(self, mock_context):
        """Test pass with safe commands"""
        gate = ToolPolicyGate()

        context = mock_context.copy()
        context["tool_calls"] = [
            {"command": "ls -la"},
            {"command": "cat README.md"},
            {"command": "npm install"},
        ]

        result = gate.run("", context)

        assert result.status == "pass"
        assert result.error_count == 0

    def test_fail_dangerous_command(self, mock_context):
        """Test fail with dangerous command - hard fail"""
        gate = ToolPolicyGate()

        context = mock_context.copy()
        context["tool_calls"] = [
            {"command": "rm -rf /important-data"}
        ]

        result = gate.run("", context)

        assert result.status == "fail"
        assert result.severity == GateSeverity.CRITICAL.value
        assert result.error_count == 1
        assert len(result.findings) == 1
        assert result.findings[0]["severity"] == "CRITICAL"

    def test_fail_drop_database(self, mock_context):
        """Test fail with DROP DATABASE command"""
        gate = ToolPolicyGate()

        context = mock_context.copy()
        context["tool_calls"] = [
            {"command": "DROP DATABASE production;"}
        ]

        result = gate.run("", context)

        assert result.status == "fail"
        assert result.error_count == 1

    def test_fail_kubectl_delete_all(self, mock_context):
        """Test fail with kubectl delete --all"""
        gate = ToolPolicyGate()

        context = mock_context.copy()
        context["tool_calls"] = [
            {"command": "kubectl delete --all"}  # Exact match with deny pattern
        ]

        result = gate.run("", context)

        assert result.status == "fail"

    def test_fail_fork_bomb(self, mock_context):
        """Test fail with fork bomb pattern"""
        gate = ToolPolicyGate()

        context = mock_context.copy()
        context["tool_calls"] = [
            {"command": ":(){ :|:& };:"}
        ]

        result = gate.run("", context)

        assert result.status == "fail"

    def test_multiple_deny_patterns_matched(self, mock_context):
        """Test multiple deny patterns matched"""
        gate = ToolPolicyGate()

        context = mock_context.copy()
        context["tool_calls"] = [
            {"command": "rm -rf /"},
            {"command": "DROP DATABASE test;"},
            {"command": "sudo rm important_file"},
        ]

        result = gate.run("", context)

        assert result.status == "fail"
        assert result.error_count == 3

    def test_allow_pattern_overrides_deny(self, mock_context):
        """Test allow pattern overrides deny"""
        gate = ToolPolicyGate(
            deny_patterns=["rm"],
            allow_patterns=["rm test"]  # Allow specific rm command
        )

        context = mock_context.copy()
        context["tool_calls"] = [
            {"command": "rm test.txt"}  # Should be allowed
        ]

        result = gate.run("", context)

        # Allow pattern should override deny
        assert result.status == "pass"

    def test_tool_calls_from_file(self, temp_tool_calls_file, mock_context):
        """Test tool calls parsed from file"""
        gate = ToolPolicyGate()

        result = gate.run(temp_tool_calls_file, mock_context)

        # File contains safe commands (ls, cat)
        assert result.status == "pass"

    def test_dangerous_commands_from_file(self, mock_context):
        """Test dangerous commands parsed from file"""
        gate = ToolPolicyGate()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(json.dumps([
                {"command": "rm -rf /data"}
            ]))
            artifact = f.name

        try:
            result = gate.run(artifact, mock_context)

            assert result.status == "fail"
            assert result.error_count == 1
        finally:
            os.unlink(artifact)

    def test_tool_name_field(self, mock_context):
        """Test tool_name field used as command"""
        gate = ToolPolicyGate()

        context = mock_context.copy()
        context["tool_calls"] = [
            {"tool_name": "kubectl delete --all"}  # Using tool_name field
        ]

        result = gate.run("", context)

        assert result.status == "fail"

    def test_case_insensitive_matching(self, mock_context):
        """Test case insensitive pattern matching"""
        gate = ToolPolicyGate()

        context = mock_context.copy()
        context["tool_calls"] = [
            {"command": "DROP DATABASE PRODUCTION"}  # Uppercase
        ]

        result = gate.run("", context)

        assert result.status == "fail"

    def test_checked_calls_count(self, mock_context):
        """Test checked_calls count in details"""
        gate = ToolPolicyGate()

        context = mock_context.copy()
        context["tool_calls"] = [
            {"command": "ls"},
            {"command": "cat"},
            {"command": "echo"},
        ]

        result = gate.run("", context)

        assert result.details["checked_calls"] == 3


# ============================================================================
# StaticGateRunner Tests
# ============================================================================

class TestStaticGateRunner:
    """Tests for StaticGateRunner"""

    def test_default_gates(self):
        """Test default gate configuration"""
        runner = StaticGateRunner()

        assert len(runner.gates) == 7
        gate_names = [g.name() for g in runner.gates]
        assert "lint" in gate_names
        assert "sast" in gate_names
        assert "secret_scan" in gate_names
        assert "license_scan" in gate_names
        assert "tool_policy" in gate_names

    def test_custom_gates(self):
        """Test custom gate configuration"""
        custom_gates = [LintGate(), SASTGate()]
        runner = StaticGateRunner(gates=custom_gates)

        assert len(runner.gates) == 2

    def test_run_all(self, mock_subprocess, mock_context):
        """Test run_all returns results for all gates"""
        runner = StaticGateRunner(gates=[LintGate(), SASTGate()])

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="[]",
            stderr=""
        )

        results = runner.run_all(".", mock_context)

        assert len(results) == 2
        assert all(isinstance(r, GateResult) for r in results)

    def test_run_all_handles_exceptions(self, mock_context):
        """Test run_all handles gate exceptions gracefully"""
        runner = StaticGateRunner()

        # Create a gate that raises exception
        broken_gate = Mock(spec=StaticGateAdapter)
        broken_gate.name.return_value = "broken"
        broken_gate.run.side_effect = Exception("Gate failed")
        runner.gates = [broken_gate]

        results = runner.run_all(".", mock_context)

        assert len(results) == 1
        assert results[0].status == "warn"
        assert "error" in results[0].details

    def test_has_hard_fail_true(self):
        """Test has_hard_fail returns True with failures"""
        runner = StaticGateRunner()

        results = [
            GateResult(gate_name="test1", status="pass"),
            GateResult(gate_name="test2", status="fail"),
        ]

        assert runner.has_hard_fail(results) == True

    def test_has_hard_fail_false(self):
        """Test has_hard_fail returns False without failures"""
        runner = StaticGateRunner()

        results = [
            GateResult(gate_name="test1", status="pass"),
            GateResult(gate_name="test2", status="warn"),
        ]

        assert runner.has_hard_fail(results) == False

    def test_get_failures(self):
        """Test get_failures returns only failed results"""
        runner = StaticGateRunner()

        results = [
            GateResult(gate_name="test1", status="pass"),
            GateResult(gate_name="test2", status="fail", error_count=1),
            GateResult(gate_name="test3", status="fail", error_count=2),
            GateResult(gate_name="test4", status="warn"),
        ]

        failures = runner.get_failures(results)

        assert len(failures) == 2
        assert all(f.status == "fail" for f in failures)

    def test_get_warnings(self):
        """Test get_warnings returns only warning results"""
        runner = StaticGateRunner()

        results = [
            GateResult(gate_name="test1", status="pass"),
            GateResult(gate_name="test2", status="warn"),
            GateResult(gate_name="test3", status="fail"),
        ]

        warnings = runner.get_warnings(results)

        assert len(warnings) == 1
        assert warnings[0].status == "warn"

    def test_to_rule_violation(self):
        """Test to_rule_violation conversion"""
        runner = StaticGateRunner()

        results = [
            GateResult(gate_name="lint", status="fail", error_count=2),
            GateResult(gate_name="sast", status="fail", error_count=1, warning_count=3),
            GateResult(gate_name="secret_scan", status="fail", error_count=1),
            GateResult(gate_name="license_scan", status="warn", error_count=0, warning_count=1),
            GateResult(gate_name="tool_policy", status="fail", error_count=2),
        ]

        violation = runner.to_rule_violation(results)

        assert violation["lint"] == 2
        assert violation["sast_high"] == 1
        assert violation["sast_medium"] == 3
        assert violation["secret"] == 1
        assert violation["license_forbidden"] == 0
        assert violation["license_unknown"] == 1
        assert violation["tool_policy_deny"] == 2

    def test_to_rule_violation_empty_results(self):
        """Test to_rule_violation with empty results"""
        runner = StaticGateRunner()

        violation = runner.to_rule_violation([])

        # All should be 0
        assert all(v == 0 for v in violation.values())

    def test_to_rule_violation_all_pass(self):
        """Test to_rule_violation with all passing"""
        runner = StaticGateRunner()

        results = [
            GateResult(gate_name="lint", status="pass", error_count=0),
            GateResult(gate_name="sast", status="pass", error_count=0, warning_count=0),
        ]

        violation = runner.to_rule_violation(results)

        assert violation["lint"] == 0
        assert violation["sast_high"] == 0


# ============================================================================
# Hard Fail Detection Tests (AGF-REQ-002)
# ============================================================================

class TestHardFailDetection:
    """Tests for hard fail scenarios per AGF-REQ-002"""

    def test_secret_hard_fail(self, mock_subprocess, mock_context):
        """UT-HOV-001: Secret found triggers BLOCK"""
        gate = SecretScanGate(engine="trivy")

        trivy_output = json.dumps({
            "Results": [
                {
                    "Target": "config.py",
                    "Misconfigurations": [
                        {"Category": "secret", "Severity": "CRITICAL", "Title": "API Key"}
                    ]
                }
            ]
        })

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=trivy_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        # Secret should be hard fail (BLOCK)
        assert result.status == "fail"
        assert result.severity == GateSeverity.CRITICAL.value
        assert result.error_count > 0  # rule_violation.secret > 0

    def test_sast_high_hard_fail(self, mock_subprocess, mock_context):
        """UT-HOV-004: SAST high severity triggers BLOCK"""
        gate = SASTGate(engine="semgrep")

        semgrep_output = json.dumps({
            "results": [
                {
                    "check_id": "security.sql-injection",
                    "path": "app.py",
                    "extra": {"severity": "ERROR", "message": "SQL injection"}
                }
            ]
        })

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=semgrep_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        # SAST high should be hard fail (BLOCK)
        assert result.status == "fail"
        assert result.severity == GateSeverity.HIGH.value
        assert result.error_count > 0  # rule_violation.sast_high > 0

    def test_tool_policy_deny_hard_fail(self, mock_context):
        """UT-HOV-005: Tool policy deny triggers BLOCK"""
        gate = ToolPolicyGate()

        context = mock_context.copy()
        context["tool_calls"] = [
            {"command": "rm -rf /"}
        ]

        result = gate.run("", context)

        # Tool policy deny should be hard fail (BLOCK)
        assert result.status == "fail"
        assert result.severity == GateSeverity.CRITICAL.value
        assert result.error_count > 0  # rule_violation.tool_policy_deny > 0

    def test_license_forbidden_hard_fail(self, mock_subprocess, mock_context):
        """Forbidden license triggers BLOCK"""
        gate = LicenseGate(engine="trivy")

        trivy_output = json.dumps({
            "Results": [
                {
                    "Target": "package.json",
                    "Licenses": [
                        {"License": {"ID": "GPL-3.0"}, "Severity": "CRITICAL"}
                    ]
                }
            ]
        })

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=trivy_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.status == "fail"
        assert result.severity == GateSeverity.CRITICAL.value

    def test_runner_detects_hard_fail(self, mock_subprocess, mock_context):
        """Test runner correctly identifies hard fail"""
        runner = StaticGateRunner(gates=[
            SecretScanGate(engine="trivy"),
            SASTGate(engine="semgrep"),
        ])

        # Mock: --version checks (2), then actual scans (2)
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="trivy version 0.50.0", stderr=""),  # trivy --version
            Mock(returncode=1, stdout=json.dumps({"Results": [{"Misconfigurations": [{"Category": "secret"}]}]}), stderr=""),  # trivy scan with secret
            Mock(returncode=0, stdout="semgrep version 1.0", stderr=""),  # semgrep --version
            Mock(returncode=0, stdout=json.dumps({"results": []}), stderr=""),  # semgrep scan pass
        ]

        results = runner.run_all(".", mock_context)
        has_fail = runner.has_hard_fail(results)

        assert has_fail == True


# ============================================================================
# evidence_ref Tests
# ============================================================================

class TestEvidenceRef:
    """Tests for evidence_ref generation"""

    def test_lint_evidence_ref(self, mock_subprocess, temp_artifact, mock_context):
        """Test lint gate generates evidence_ref"""
        gate = LintGate(language="python")

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=json.dumps([{"type": "error", "message": "test"}]),
            stderr=""
        )

        result = gate.run(temp_artifact, mock_context)

        assert result.evidence_ref == temp_artifact

    def test_sast_evidence_ref(self, mock_subprocess, mock_context):
        """Test SAST gate generates evidence_ref"""
        gate = SASTGate(engine="semgrep")

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=json.dumps({"results": [{"check_id": "test"}]}),
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.evidence_ref == "."

    def test_secret_scan_evidence_ref(self, mock_subprocess, mock_context):
        """Test secret scan gate generates evidence_ref"""
        gate = SecretScanGate(engine="trivy")

        trivy_output = json.dumps({
            "Results": [{"Misconfigurations": [{"Category": "secret"}]}]
        })

        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout=trivy_output,
            stderr=""
        )

        result = gate.run(".", mock_context)

        assert result.evidence_ref == "."


# ============================================================================
# create_static_gates_from_config Tests
# ============================================================================

class TestCreateStaticGatesFromConfig:
    """Tests for config-based gate creation"""

    def test_empty_config(self):
        """Test empty config returns no gates"""
        gates = create_static_gates_from_config({})
        assert len(gates) == 0

    def test_all_gates_enabled(self):
        """Test all gates enabled in config"""
        config = {
            'static_gates': {
                'lint': {'enabled': True, 'language': 'python'},
                'typecheck': {'enabled': True, 'language': 'python'},
                'tests': {'enabled': True, 'min_pass_rate': 0.9},
                'sast': {'enabled': True, 'engine': 'semgrep'},
                'secret_scan': {'enabled': True, 'engine': 'trivy'},
                'license_scan': {'enabled': True, 'engine': 'trivy'},
                'tool_policy': {'enabled': True, 'deny_patterns': ['rm']},
            }
        }

        gates = create_static_gates_from_config(config)

        assert len(gates) == 7
        gate_names = [g.name() for g in gates]
        assert "lint" in gate_names
        assert "sast" in gate_names

    def test_partial_gates_enabled(self):
        """Test only some gates enabled"""
        config = {
            'static_gates': {
                'lint': {'enabled': True},
                'sast': {'enabled': False},
                'secret_scan': {'enabled': True},
            }
        }

        gates = create_static_gates_from_config(config)

        assert len(gates) == 2
        gate_names = [g.name() for g in gates]
        assert "lint" in gate_names
        assert "sast" not in gate_names
        assert "secret_scan" in gate_names

    def test_custom_config_file(self):
        """Test custom config file passed"""
        config = {
            'static_gates': {
                'lint': {'enabled': True, 'config_file': '.pylintrc'},
            }
        }

        gates = create_static_gates_from_config(config)

        assert len(gates) == 1
        assert gates[0].config_file == ".pylintrc"

    def test_custom_forbidden_licenses(self):
        """Test custom forbidden licenses passed"""
        config = {
            'static_gates': {
                'license_scan': {
                    'enabled': True,
                    'forbidden_licenses': ['GPL-2.0', 'Custom']
                },
            }
        }

        gates = create_static_gates_from_config(config)

        assert len(gates) == 1
        assert "GPL-2.0" in gates[0].forbidden_licenses
        assert "Custom" in gates[0].forbidden_licenses

    def test_custom_rulesets(self):
        """Test custom rulesets passed"""
        config = {
            'static_gates': {
                'sast': {
                    'enabled': True,
                    'rulesets': ['p/python', 'p/security']
                },
            }
        }

        gates = create_static_gates_from_config(config)

        assert len(gates) == 1
        assert gates[0].rulesets == ['p/python', 'p/security']


# ============================================================================
# StaticGateAdapter Base Tests
# ============================================================================

class TestStaticGateAdapterBase:
    """Tests for StaticGateAdapter base functionality"""

    def test_run_command_success(self, mock_subprocess):
        """Test _run_command success"""
        gate = LintGate()

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="output",
            stderr=""
        )

        exit_code, stdout, stderr = gate._run_command(["test"])

        assert exit_code == 0
        assert stdout == "output"
        assert stderr == ""

    def test_run_command_timeout(self, mock_subprocess):
        """Test _run_command handles timeout"""
        import subprocess
        gate = LintGate()

        mock_subprocess.side_effect = subprocess.TimeoutExpired("test", 120)

        exit_code, stdout, stderr = gate._run_command(["test"], timeout=120)

        assert exit_code == -1
        assert stderr == "Timeout expired"

    def test_run_command_not_found(self, mock_subprocess):
        """Test _run_command handles FileNotFoundError"""
        gate = LintGate()

        mock_subprocess.side_effect = FileNotFoundError("test not found")

        exit_code, stdout, stderr = gate._run_command(["test"])

        assert exit_code == -2
        assert "not found" in stderr

    def test_run_command_exception(self, mock_subprocess):
        """Test _run_command handles general exception"""
        gate = LintGate()

        mock_subprocess.side_effect = Exception("Unexpected error")

        exit_code, stdout, stderr = gate._run_command(["test"])

        assert exit_code == -3
        assert "Unexpected error" in stderr

    def test_check_tool_available_true(self, mock_subprocess):
        """Test _check_tool_available returns True"""
        gate = LintGate()

        mock_subprocess.return_value = Mock(returncode=0)

        assert gate._check_tool_available("pylint") == True

    def test_check_tool_available_false(self, mock_subprocess):
        """Test _check_tool_available returns False"""
        gate = LintGate()

        mock_subprocess.side_effect = FileNotFoundError()

        assert gate._check_tool_available("notexist") == False


# ============================================================================
# Integration-style Tests (marked as integration)
# ============================================================================

@pytest.mark.integration
class TestStaticGatesIntegration:
    """Integration tests for static gates (requires actual tools)"""

    def test_real_pylint_execution(self):
        """Test real pylint execution if available"""
        gate = LintGate(language="python")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test():\n    x = 1  # unused variable\n")
            artifact = f.name

        try:
            result = gate.run(artifact, {'cwd': os.getcwd()})

            # If pylint is available, should detect issues
            # If not available, should warn
            assert result.gate_name == "lint"
        finally:
            os.unlink(artifact)

    def test_real_semgrep_execution(self):
        """Test real semgrep execution if available"""
        gate = SASTGate(engine="semgrep")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("import os\nos.system('ls')\n")
            artifact = f.name

        try:
            result = gate.run(artifact, {'cwd': os.getcwd()})

            assert result.gate_name == "sast"
        finally:
            os.unlink(artifact)