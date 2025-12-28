"""
Tests for Verifier component.

Tests verification of code changes using mocked subprocesses.
No real pytest/ruff/mypy execution occurs in these tests.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from scrappy.agent.verifier import Verifier
from scrappy.agent.models import (
    Step,
    Plan,
    VerificationPolicy,
    UnitTestResult,
    LintResult,
    TypecheckResult,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def verifier(tmp_path: Path) -> Verifier:
    """Create a Verifier with a temporary project root."""
    # Create basic project structure
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return Verifier(project_root=tmp_path)


@pytest.fixture
def strict_verifier(tmp_path: Path) -> Verifier:
    """Create a strict Verifier that fails on warnings too."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    policy = VerificationPolicy(
        fail_on_lint_warnings=True,
        fail_on_type_warnings=True,
        fail_on_test_skip=True,
    )
    return Verifier(policy=policy, project_root=tmp_path)


@pytest.fixture
def sample_step() -> Step:
    """Create a sample step for testing."""
    return Step(
        id="step-1",
        description="Add a new function",
        tool="write_file",
        parameters={"path": "src/foo.py", "content": "def foo(): pass"},
    )


@pytest.fixture
def sample_plan() -> Plan:
    """Create a sample plan for testing."""
    return Plan(
        id="plan-1",
        goal="Implement feature X",
        steps=[
            Step(id="s1", description="Write code"),
            Step(id="s2", description="Write tests"),
        ],
    )


# =============================================================================
# Verifier Initialization Tests
# =============================================================================


class TestVerifierInit:
    """Tests for Verifier initialization."""

    def test_default_initialization(self):
        """Verifier should use defaults when no args provided."""
        verifier = Verifier()

        assert verifier.policy is not None
        assert verifier.project_root == Path.cwd()

    def test_custom_policy(self, tmp_path: Path):
        """Verifier should use provided policy."""
        policy = VerificationPolicy(fail_on_lint_warnings=True)
        verifier = Verifier(policy=policy, project_root=tmp_path)

        assert verifier.policy.fail_on_lint_warnings is True

    def test_custom_project_root(self, tmp_path: Path):
        """Verifier should use provided project root."""
        verifier = Verifier(project_root=tmp_path)

        assert verifier.project_root == tmp_path


# =============================================================================
# run_tests Tests
# =============================================================================


class TestRunTests:
    """Tests for run_tests method."""

    @pytest.mark.asyncio
    async def test_run_tests_empty_paths(self, verifier: Verifier):
        """run_tests should handle empty paths gracefully."""
        result = await verifier.run_tests([])

        assert result.success is True
        assert result.passed == 0
        assert result.failed == 0
        assert "No test paths" in result.output

    @pytest.mark.asyncio
    async def test_run_tests_all_passed(self, verifier: Verifier, tmp_path: Path):
        """run_tests should report success when all tests pass."""
        mock_output = "5 passed in 0.5s"
        test_path = str(tmp_path / "tests")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = (mock_output, "", 0)
            result = await verifier.run_tests([test_path])

        assert result.success is True
        assert result.passed == 5
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_run_tests_some_failed(self, verifier: Verifier, tmp_path: Path):
        """run_tests should report failure when tests fail."""
        mock_output = """
        FAILED tests/test_foo.py::test_bar - AssertionError
        3 passed, 2 failed, 1 skipped
        """
        test_path = str(tmp_path / "tests")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = (mock_output, "", 1)
            result = await verifier.run_tests([test_path])

        assert result.success is False
        assert result.passed == 3
        assert result.failed == 2
        assert result.skipped == 1
        assert len(result.errors) > 0
        assert "FAILED" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_tests_tool_not_found(self, verifier: Verifier, tmp_path: Path):
        """run_tests should handle pytest not being installed."""
        test_path = str(tmp_path / "tests")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = None  # Indicates tool not found
            result = await verifier.run_tests([test_path])

        assert result.success is True
        assert result.passed == 0
        assert "not installed" in result.output

    @pytest.mark.asyncio
    async def test_run_tests_timeout(self, verifier: Verifier, tmp_path: Path):
        """run_tests should handle timeout gracefully."""
        test_path = str(tmp_path / "tests")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.side_effect = asyncio.TimeoutError()
            result = await verifier.run_tests([test_path])

        assert result.success is False
        assert "timed out" in result.errors[0]


# =============================================================================
# run_lint Tests
# =============================================================================


class TestRunLint:
    """Tests for run_lint method."""

    @pytest.mark.asyncio
    async def test_run_lint_empty_paths(self, verifier: Verifier):
        """run_lint should handle empty paths gracefully."""
        result = await verifier.run_lint([])

        assert result.success is True
        assert result.error_count == 0
        assert result.warning_count == 0

    @pytest.mark.asyncio
    async def test_run_lint_no_issues(self, verifier: Verifier, tmp_path: Path):
        """run_lint should report success when no issues found."""
        src_path = str(tmp_path / "src" / "foo.py")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = ("[]", "", 0)
            result = await verifier.run_lint([src_path])

        assert result.success is True
        assert result.error_count == 0
        assert result.warning_count == 0

    @pytest.mark.asyncio
    async def test_run_lint_with_errors(self, verifier: Verifier, tmp_path: Path):
        """run_lint should parse errors from JSON output."""
        src_path = str(tmp_path / "src" / "foo.py")
        ruff_output = json.dumps([
            {
                "filename": "src/foo.py",
                "location": {"row": 10, "column": 5},
                "code": "E501",
                "message": "Line too long",
            },
            {
                "filename": "src/foo.py",
                "location": {"row": 20, "column": 1},
                "code": "F401",
                "message": "Unused import",
            },
        ])

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = (ruff_output, "", 1)
            result = await verifier.run_lint([src_path])

        assert result.success is False
        assert result.error_count == 2
        assert result.warning_count == 0
        assert "E501" in result.errors[0]
        assert "F401" in result.errors[1]

    @pytest.mark.asyncio
    async def test_run_lint_with_warnings(self, verifier: Verifier, tmp_path: Path):
        """run_lint should separate warnings from errors."""
        src_path = str(tmp_path / "src" / "foo.py")
        ruff_output = json.dumps([
            {
                "filename": "src/foo.py",
                "location": {"row": 10, "column": 5},
                "code": "W503",
                "message": "Line break before binary operator",
            },
        ])

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = (ruff_output, "", 0)
            result = await verifier.run_lint([src_path])

        assert result.success is True  # Warnings don't cause failure
        assert result.error_count == 0
        assert result.warning_count == 1
        assert "W503" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_run_lint_tool_not_found(self, verifier: Verifier, tmp_path: Path):
        """run_lint should handle ruff not being installed."""
        src_path = str(tmp_path / "src" / "foo.py")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = None
            result = await verifier.run_lint([src_path])

        assert result.success is True
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_run_lint_timeout(self, verifier: Verifier, tmp_path: Path):
        """run_lint should handle timeout gracefully."""
        src_path = str(tmp_path / "src" / "foo.py")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.side_effect = asyncio.TimeoutError()
            result = await verifier.run_lint([src_path])

        assert result.success is False
        assert result.error_count == 1
        assert "timed out" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_lint_invalid_json(self, verifier: Verifier, tmp_path: Path):
        """run_lint should handle invalid JSON output."""
        src_path = str(tmp_path / "src" / "foo.py")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = ("not valid json", "", 1)
            result = await verifier.run_lint([src_path])

        assert result.success is False
        assert result.error_count == 1
        assert "Failed to parse" in result.errors[0]


# =============================================================================
# run_typecheck Tests
# =============================================================================


class TestRunTypecheck:
    """Tests for run_typecheck method."""

    @pytest.mark.asyncio
    async def test_run_typecheck_empty_paths(self, verifier: Verifier):
        """run_typecheck should handle empty paths gracefully."""
        result = await verifier.run_typecheck([])

        assert result.success is True
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_run_typecheck_no_errors(self, verifier: Verifier, tmp_path: Path):
        """run_typecheck should report success when no errors found."""
        mock_output = "Success: no issues found in 5 source files"
        src_path = str(tmp_path / "src")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = (mock_output, "", 0)
            result = await verifier.run_typecheck([src_path])

        assert result.success is True
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_run_typecheck_with_errors(self, verifier: Verifier, tmp_path: Path):
        """run_typecheck should parse errors from output."""
        mock_output = """
        src/foo.py:10: error: Incompatible return type
        src/foo.py:20: error: Argument has incompatible type
        Found 2 errors in 1 file
        """
        src_path = str(tmp_path / "src")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = (mock_output, "", 1)
            result = await verifier.run_typecheck([src_path])

        assert result.success is False
        assert result.error_count == 2
        assert "Incompatible return type" in result.errors[0]
        assert "Argument has incompatible type" in result.errors[1]

    @pytest.mark.asyncio
    async def test_run_typecheck_with_notes(self, verifier: Verifier, tmp_path: Path):
        """run_typecheck should treat notes as warnings."""
        mock_output = """
        src/foo.py:10: note: Consider using Optional
        Success: no issues found
        """
        src_path = str(tmp_path / "src")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = (mock_output, "", 0)
            result = await verifier.run_typecheck([src_path])

        assert result.success is True
        assert result.error_count == 0
        assert result.warning_count == 1
        assert "Optional" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_run_typecheck_tool_not_found(self, verifier: Verifier, tmp_path: Path):
        """run_typecheck should handle mypy not being installed."""
        src_path = str(tmp_path / "src")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = None
            result = await verifier.run_typecheck([src_path])

        assert result.success is True
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_run_typecheck_timeout(self, verifier: Verifier, tmp_path: Path):
        """run_typecheck should handle timeout gracefully."""
        src_path = str(tmp_path / "src")

        with patch.object(verifier, "_run_subprocess") as mock_subprocess:
            mock_subprocess.side_effect = asyncio.TimeoutError()
            result = await verifier.run_typecheck([src_path])

        assert result.success is False
        assert result.error_count == 1
        assert "timed out" in result.errors[0]


# =============================================================================
# verify_step Tests
# =============================================================================


class TestVerifyStep:
    """Tests for verify_step method."""

    @pytest.mark.asyncio
    async def test_verify_step_no_files(self, verifier: Verifier, sample_step: Step):
        """verify_step should pass when no files changed."""
        result = await verifier.verify_step(sample_step, [])

        assert result.success is True
        assert "No files changed" in result.message

    @pytest.mark.asyncio
    async def test_verify_step_no_python_files(
        self, verifier: Verifier, sample_step: Step
    ):
        """verify_step should pass when no Python files changed."""
        result = await verifier.verify_step(sample_step, ["README.md", "config.yaml"])

        assert result.success is True
        assert "No Python files" in result.message

    @pytest.mark.asyncio
    async def test_verify_step_all_pass(self, verifier: Verifier, sample_step: Step):
        """verify_step should pass when all checks pass."""
        with patch.object(verifier, "run_lint") as mock_lint:
            with patch.object(verifier, "run_typecheck") as mock_typecheck:
                with patch.object(verifier, "_find_related_tests") as mock_find:
                    mock_lint.return_value = LintResult(
                        success=True, error_count=0, warning_count=0
                    )
                    mock_typecheck.return_value = TypecheckResult(
                        success=True, error_count=0
                    )
                    mock_find.return_value = []  # No related tests

                    result = await verifier.verify_step(sample_step, ["src/foo.py"])

        assert result.success is True
        assert "passed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_verify_step_lint_failure(
        self, verifier: Verifier, sample_step: Step
    ):
        """verify_step should fail when lint fails."""
        with patch.object(verifier, "run_lint") as mock_lint:
            with patch.object(verifier, "run_typecheck") as mock_typecheck:
                with patch.object(verifier, "_find_related_tests") as mock_find:
                    mock_lint.return_value = LintResult(
                        success=False,
                        error_count=2,
                        warning_count=0,
                        errors=["E501: line too long", "F401: unused import"],
                    )
                    mock_typecheck.return_value = TypecheckResult(
                        success=True, error_count=0
                    )
                    mock_find.return_value = []

                    result = await verifier.verify_step(sample_step, ["src/foo.py"])

        assert result.success is False
        assert "lint error" in result.message.lower()
        assert len(result.errors) == 2

    @pytest.mark.asyncio
    async def test_verify_step_typecheck_failure(
        self, verifier: Verifier, sample_step: Step
    ):
        """verify_step should fail when typecheck fails."""
        with patch.object(verifier, "run_lint") as mock_lint:
            with patch.object(verifier, "run_typecheck") as mock_typecheck:
                with patch.object(verifier, "_find_related_tests") as mock_find:
                    mock_lint.return_value = LintResult(
                        success=True, error_count=0, warning_count=0
                    )
                    mock_typecheck.return_value = TypecheckResult(
                        success=False,
                        error_count=1,
                        errors=["src/foo.py:10: error: type mismatch"],
                    )
                    mock_find.return_value = []

                    result = await verifier.verify_step(sample_step, ["src/foo.py"])

        assert result.success is False
        assert "type error" in result.message.lower()

    @pytest.mark.asyncio
    async def test_verify_step_test_failure(
        self, verifier: Verifier, sample_step: Step, tmp_path: Path
    ):
        """verify_step should fail when related tests fail."""
        # Create a test file that will be found
        test_file = tmp_path / "tests" / "test_foo.py"
        test_file.write_text("def test_foo(): pass")

        with patch.object(verifier, "run_lint") as mock_lint:
            with patch.object(verifier, "run_typecheck") as mock_typecheck:
                with patch.object(verifier, "run_tests") as mock_tests:
                    with patch.object(verifier, "_find_related_tests") as mock_find:
                        mock_lint.return_value = LintResult(
                            success=True, error_count=0, warning_count=0
                        )
                        mock_typecheck.return_value = TypecheckResult(
                            success=True, error_count=0
                        )
                        mock_find.return_value = [str(test_file)]
                        mock_tests.return_value = UnitTestResult(
                            success=False,
                            passed=0,
                            failed=1,
                            skipped=0,
                            errors=["test_foo FAILED"],
                        )

                        result = await verifier.verify_step(sample_step, ["src/foo.py"])

        assert result.success is False
        assert "test failure" in result.message.lower()

    @pytest.mark.asyncio
    async def test_verify_step_warnings_only(
        self, verifier: Verifier, sample_step: Step
    ):
        """verify_step should pass with warnings only (default policy)."""
        with patch.object(verifier, "run_lint") as mock_lint:
            with patch.object(verifier, "run_typecheck") as mock_typecheck:
                with patch.object(verifier, "_find_related_tests") as mock_find:
                    mock_lint.return_value = LintResult(
                        success=True,
                        error_count=0,
                        warning_count=2,
                        warnings=["W503", "W504"],
                    )
                    mock_typecheck.return_value = TypecheckResult(
                        success=True, error_count=0, warning_count=1, warnings=["note"]
                    )
                    mock_find.return_value = []

                    result = await verifier.verify_step(sample_step, ["src/foo.py"])

        assert result.success is True
        assert len(result.warnings) == 3  # All warnings collected

    @pytest.mark.asyncio
    async def test_verify_step_strict_fails_on_warnings(
        self, strict_verifier: Verifier, sample_step: Step
    ):
        """verify_step should fail on warnings with strict policy."""
        with patch.object(strict_verifier, "run_lint") as mock_lint:
            with patch.object(strict_verifier, "run_typecheck") as mock_typecheck:
                with patch.object(strict_verifier, "_find_related_tests") as mock_find:
                    mock_lint.return_value = LintResult(
                        success=True,
                        error_count=0,
                        warning_count=1,
                        warnings=["W503"],
                    )
                    mock_typecheck.return_value = TypecheckResult(
                        success=True, error_count=0
                    )
                    mock_find.return_value = []

                    result = await strict_verifier.verify_step(
                        sample_step, ["src/foo.py"]
                    )

        assert result.success is False
        assert "warning" in result.message.lower()


# =============================================================================
# verify_plan Tests
# =============================================================================


class TestVerifyPlan:
    """Tests for verify_plan method."""

    @pytest.mark.asyncio
    async def test_verify_plan_all_pass(self, verifier: Verifier, sample_plan: Plan):
        """verify_plan should pass when all checks pass."""
        with patch.object(verifier, "run_lint") as mock_lint:
            with patch.object(verifier, "run_typecheck") as mock_typecheck:
                with patch.object(verifier, "run_tests") as mock_tests:
                    mock_lint.return_value = LintResult(
                        success=True, error_count=0, warning_count=0
                    )
                    mock_typecheck.return_value = TypecheckResult(
                        success=True, error_count=0
                    )
                    mock_tests.return_value = UnitTestResult(
                        success=True, passed=10, failed=0, skipped=0
                    )

                    result = await verifier.verify_plan(sample_plan)

        assert result.success is True
        assert "passed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_verify_plan_failure(self, verifier: Verifier, sample_plan: Plan):
        """verify_plan should fail when any check fails."""
        with patch.object(verifier, "run_lint") as mock_lint:
            with patch.object(verifier, "run_typecheck") as mock_typecheck:
                with patch.object(verifier, "run_tests") as mock_tests:
                    mock_lint.return_value = LintResult(
                        success=False, error_count=1, errors=["E501"]
                    )
                    mock_typecheck.return_value = TypecheckResult(
                        success=True, error_count=0
                    )
                    mock_tests.return_value = UnitTestResult(
                        success=True, passed=10, failed=0, skipped=0
                    )

                    result = await verifier.verify_plan(sample_plan)

        assert result.success is False
        assert "lint error" in result.message.lower()

    @pytest.mark.asyncio
    async def test_verify_plan_no_tests_dir(self, verifier: Verifier, sample_plan: Plan):
        """verify_plan should handle missing tests directory."""
        # Remove tests directory
        tests_dir = verifier.project_root / "tests"
        if tests_dir.exists():
            tests_dir.rmdir()

        with patch.object(verifier, "run_lint") as mock_lint:
            with patch.object(verifier, "run_typecheck") as mock_typecheck:
                mock_lint.return_value = LintResult(
                    success=True, error_count=0, warning_count=0
                )
                mock_typecheck.return_value = TypecheckResult(
                    success=True, error_count=0
                )

                result = await verifier.verify_plan(sample_plan)

        assert result.success is True
        # run_tests should not be called
        assert "passed" in result.message.lower()


# =============================================================================
# _find_related_tests Tests
# =============================================================================


class TestFindRelatedTests:
    """Tests for _find_related_tests method."""

    def test_find_related_tests_src_convention(self, verifier: Verifier, tmp_path: Path):
        """Should find tests following src/foo.py -> tests/test_foo.py convention."""
        # Create test file
        test_file = tmp_path / "tests" / "test_bar.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_bar(): pass")

        source_files = [str(tmp_path / "src" / "bar.py")]
        result = verifier._find_related_tests(source_files)

        assert len(result) == 1
        assert "test_bar.py" in result[0]

    def test_find_related_tests_nested_path(self, verifier: Verifier, tmp_path: Path):
        """Should find tests for nested source files."""
        # Create nested test file
        test_file = tmp_path / "tests" / "subdir" / "test_baz.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_baz(): pass")

        source_files = [str(tmp_path / "src" / "subdir" / "baz.py")]
        result = verifier._find_related_tests(source_files)

        assert len(result) == 1
        assert "test_baz.py" in result[0]

    def test_find_related_tests_already_test_file(
        self, verifier: Verifier, tmp_path: Path
    ):
        """Should return test files that are directly passed."""
        test_file = tmp_path / "tests" / "test_existing.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_existing(): pass")

        source_files = [str(test_file)]
        result = verifier._find_related_tests(source_files)

        assert len(result) == 1
        assert "test_existing.py" in result[0]

    def test_find_related_tests_no_match(self, verifier: Verifier, tmp_path: Path):
        """Should return empty list when no related tests found."""
        source_files = [str(tmp_path / "src" / "no_tests.py")]
        result = verifier._find_related_tests(source_files)

        assert result == []

    def test_find_related_tests_multiple_files(
        self, verifier: Verifier, tmp_path: Path
    ):
        """Should find tests for multiple source files."""
        # Create test files
        for name in ["alpha", "beta"]:
            test_file = tmp_path / "tests" / f"test_{name}.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text(f"def test_{name}(): pass")

        source_files = [
            str(tmp_path / "src" / "alpha.py"),
            str(tmp_path / "src" / "beta.py"),
            str(tmp_path / "src" / "gamma.py"),  # No test for this
        ]
        result = verifier._find_related_tests(source_files)

        assert len(result) == 2
        assert any("test_alpha.py" in r for r in result)
        assert any("test_beta.py" in r for r in result)


# =============================================================================
# _run_subprocess Tests
# =============================================================================


class TestRunSubprocess:
    """Tests for _run_subprocess method."""

    @pytest.mark.asyncio
    async def test_run_subprocess_success(self, verifier: Verifier):
        """Should return stdout, stderr, returncode on success."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            result = await verifier._run_subprocess(["echo", "hello"])

        assert result is not None
        stdout, stderr, returncode = result
        assert stdout == "output"
        assert returncode == 0

    @pytest.mark.asyncio
    async def test_run_subprocess_tool_not_found(self, verifier: Verifier):
        """Should return None when tool is not found."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = FileNotFoundError("not found")

            result = await verifier._run_subprocess(["nonexistent_tool"])

        assert result is None

    @pytest.mark.asyncio
    async def test_run_subprocess_timeout(self, verifier: Verifier):
        """Should raise TimeoutError on timeout."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_exec.return_value = mock_process

            with pytest.raises(asyncio.TimeoutError):
                await verifier._run_subprocess(["slow_command"], timeout=1)

    @pytest.mark.asyncio
    async def test_run_subprocess_handles_windows_enoent(self, verifier: Verifier):
        """Should return None for Windows ENOENT error."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            error = OSError()
            error.errno = 2  # ENOENT
            mock_exec.side_effect = error

            result = await verifier._run_subprocess(["missing_tool"])

        assert result is None


# =============================================================================
# Output Parsing Tests
# =============================================================================


class TestParsePytestOutput:
    """Tests for _parse_pytest_output method."""

    def test_parse_simple_passed(self, verifier: Verifier):
        """Should parse simple passed output."""
        output = "5 passed in 0.5s"
        passed, failed, skipped, errors = verifier._parse_pytest_output(output)

        assert passed == 5
        assert failed == 0
        assert skipped == 0
        assert errors == []

    def test_parse_mixed_results(self, verifier: Verifier):
        """Should parse mixed pass/fail/skip output."""
        output = "10 passed, 3 failed, 2 skipped in 1.5s"
        passed, failed, skipped, errors = verifier._parse_pytest_output(output)

        assert passed == 10
        assert failed == 3
        assert skipped == 2

    def test_parse_with_failure_lines(self, verifier: Verifier):
        """Should extract FAILED lines as errors."""
        output = """
        FAILED tests/test_foo.py::test_bar - AssertionError
        ERROR tests/test_baz.py::test_qux - RuntimeError
        2 passed, 1 failed, 1 error
        """
        passed, failed, skipped, errors = verifier._parse_pytest_output(output)

        assert len(errors) == 2
        assert "FAILED" in errors[0]
        assert "ERROR" in errors[1]


class TestParseRuffOutput:
    """Tests for _parse_ruff_output method."""

    def test_parse_empty_output(self, verifier: Verifier):
        """Should handle empty output."""
        errors, warnings = verifier._parse_ruff_output("")
        assert errors == []
        assert warnings == []

    def test_parse_empty_array(self, verifier: Verifier):
        """Should handle empty JSON array."""
        errors, warnings = verifier._parse_ruff_output("[]")
        assert errors == []
        assert warnings == []

    def test_parse_errors(self, verifier: Verifier):
        """Should parse error codes."""
        output = json.dumps([
            {
                "filename": "foo.py",
                "location": {"row": 1, "column": 1},
                "code": "E501",
                "message": "too long",
            }
        ])
        errors, warnings = verifier._parse_ruff_output(output)

        assert len(errors) == 1
        assert "E501" in errors[0]

    def test_parse_warnings(self, verifier: Verifier):
        """Should parse warning codes (W prefix)."""
        output = json.dumps([
            {
                "filename": "foo.py",
                "location": {"row": 1, "column": 1},
                "code": "W503",
                "message": "line break",
            }
        ])
        errors, warnings = verifier._parse_ruff_output(output)

        assert len(errors) == 0
        assert len(warnings) == 1
        assert "W503" in warnings[0]


class TestParseMypyOutput:
    """Tests for _parse_mypy_output method."""

    def test_parse_success(self, verifier: Verifier):
        """Should handle success message."""
        output = "Success: no issues found in 5 source files"
        errors, warnings = verifier._parse_mypy_output(output)

        assert errors == []
        assert warnings == []

    def test_parse_errors(self, verifier: Verifier):
        """Should parse error lines."""
        output = """
        foo.py:10: error: Incompatible type
        bar.py:20: error: Missing return
        Found 2 errors
        """
        errors, warnings = verifier._parse_mypy_output(output)

        assert len(errors) == 2
        assert "Incompatible type" in errors[0]

    def test_parse_notes_as_warnings(self, verifier: Verifier):
        """Should parse note lines as warnings."""
        output = """
        foo.py:10: note: Consider using Optional
        Success: no issues
        """
        errors, warnings = verifier._parse_mypy_output(output)

        assert len(errors) == 0
        assert len(warnings) == 1
        assert "Optional" in warnings[0]


# =============================================================================
# Path Validation Security Tests
# =============================================================================


class TestPathValidation:
    """Security tests for path traversal prevention."""

    def test_validate_path_within_project(self, verifier: Verifier, tmp_path: Path):
        """Valid paths within project root should pass."""
        valid_path = str(tmp_path / "src" / "foo.py")
        assert verifier._validate_path(valid_path) is True

    def test_validate_path_project_root_itself(self, verifier: Verifier, tmp_path: Path):
        """Project root itself should be valid."""
        assert verifier._validate_path(str(tmp_path)) is True

    def test_validate_path_traversal_attack(self, verifier: Verifier, tmp_path: Path):
        """Path traversal attempts should be rejected."""
        # Attempt to escape project root
        malicious_paths = [
            str(tmp_path / ".." / "etc" / "passwd"),
            str(tmp_path / "src" / ".." / ".." / "etc" / "passwd"),
            "/etc/passwd",
            "C:\\Windows\\System32\\config",
        ]

        for malicious_path in malicious_paths:
            assert verifier._validate_path(malicious_path) is False, \
                f"Path traversal not blocked: {malicious_path}"

    def test_validate_path_absolute_outside_project(self, verifier: Verifier):
        """Absolute paths outside project should be rejected."""
        # Use a path that definitely isn't in the project
        assert verifier._validate_path("/tmp/malicious.py") is False
        assert verifier._validate_path("/etc/hosts") is False

    def test_validate_paths_filters_invalid(self, verifier: Verifier, tmp_path: Path):
        """_validate_paths should raise on invalid paths."""
        from scrappy.agent.verifier import PathValidationError

        valid = str(tmp_path / "src" / "foo.py")
        invalid = "/etc/passwd"

        with pytest.raises(PathValidationError):
            verifier._validate_paths([valid, invalid])

    @pytest.mark.asyncio
    async def test_run_tests_rejects_traversal(self, verifier: Verifier):
        """run_tests should reject path traversal attempts."""
        result = await verifier.run_tests(["/etc/passwd", "../../../etc/shadow"])

        assert result.success is False
        assert "Path validation failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_lint_rejects_traversal(self, verifier: Verifier):
        """run_lint should reject path traversal attempts."""
        result = await verifier.run_lint(["/etc/passwd"])

        assert result.success is False
        assert "Path validation failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_typecheck_rejects_traversal(self, verifier: Verifier):
        """run_typecheck should reject path traversal attempts."""
        result = await verifier.run_typecheck(["/etc/passwd"])

        assert result.success is False
        assert "Path validation failed" in result.errors[0]
