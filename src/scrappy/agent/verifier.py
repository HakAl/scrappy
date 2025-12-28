"""
Verifier component for running pytest, ruff, and mypy.

Implements VerifierProtocol for verification of code changes during
agent execution.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from .models import (
    Plan,
    Step,
    VerificationResult,
    UnitTestResult,
    LintResult,
    TypecheckResult,
    VerificationPolicy,
)


# Default timeout for subprocess calls (30 seconds)
DEFAULT_TIMEOUT_SECONDS = 30


class PathValidationError(ValueError):
    """Raised when a path fails security validation."""
    pass


class Verifier:
    """
    Runs verification tools (pytest, ruff, mypy) and evaluates results.

    Implements VerifierProtocol.

    This component is responsible for:
    - Running quick verification after each step (on changed files only)
    - Running full verification at plan completion
    - Parsing tool output and applying policy to determine pass/fail
    - Graceful handling of missing tools and timeouts

    Example:
        verifier = Verifier(policy=VerificationPolicy())
        result = await verifier.verify_step(step, ["src/foo.py"])
        if not result.success:
            print(f"Verification failed: {result.message}")
    """

    def __init__(
        self,
        policy: Optional[VerificationPolicy] = None,
        project_root: Optional[Path] = None,
    ):
        """
        Initialize the verifier.

        Args:
            policy: Verification policy controlling strictness.
                    Defaults to VerificationPolicy() which fails on errors
                    but not warnings.
            project_root: Root directory of the project.
                          Defaults to current working directory.
        """
        self._policy = policy or VerificationPolicy()
        self._project_root = project_root or Path.cwd()

    @property
    def policy(self) -> VerificationPolicy:
        """Get the verification policy."""
        return self._policy

    @property
    def project_root(self) -> Path:
        """Get the project root directory."""
        return self._project_root

    def _validate_path(self, path: str) -> bool:
        """
        Validate that a path is within the project root.

        Security: Prevents path traversal attacks where user-provided paths
        could escape the project directory.

        Args:
            path: Path to validate

        Returns:
            True if path is within project root, False otherwise
        """
        try:
            resolved = Path(path).resolve()
            project_resolved = self._project_root.resolve()
            # Check if the path is under the project root
            return resolved == project_resolved or project_resolved in resolved.parents
        except (OSError, ValueError):
            return False

    def _validate_paths(self, paths: list[str]) -> list[str]:
        """
        Validate and filter paths to ensure they are within project root.

        Args:
            paths: List of paths to validate

        Returns:
            List of valid paths (paths outside project root are filtered out)

        Raises:
            PathValidationError: If any path is outside the project root
        """
        validated = []
        invalid = []

        for path in paths:
            if self._validate_path(path):
                validated.append(path)
            else:
                invalid.append(path)

        if invalid:
            raise PathValidationError(
                f"Path(s) outside project root: {invalid}"
            )

        return validated

    async def verify_step(
        self,
        step: Step,
        changed_files: list[str],
    ) -> VerificationResult:
        """
        Quick verification after a step executes.

        Only checks changed files for fast feedback. Runs lint and typecheck
        on changed files, and finds/runs related tests.

        Args:
            step: The completed step to verify
            changed_files: List of files that were modified

        Returns:
            VerificationResult with success status and any errors
        """
        if not changed_files:
            return VerificationResult(
                success=True,
                message="No files changed, skipping verification",
                files_checked=[],
            )

        # Filter to only Python files
        python_files = [f for f in changed_files if f.endswith(".py")]
        if not python_files:
            return VerificationResult(
                success=True,
                message="No Python files changed, skipping verification",
                files_checked=changed_files,
            )

        # Run verification tools in parallel
        lint_task = self.run_lint(python_files)
        typecheck_task = self.run_typecheck(python_files)

        # Find related tests
        related_tests = self._find_related_tests(python_files)
        test_task = self.run_tests(related_tests) if related_tests else None

        # Await all tasks
        lint_result, typecheck_result = await asyncio.gather(
            lint_task,
            typecheck_task,
        )

        test_result = None
        if test_task:
            test_result = await test_task

        # Apply policy to determine pass/fail
        should_fail, reason = self._policy.should_fail(
            lint_result=lint_result,
            typecheck_result=typecheck_result,
            test_result=test_result,
        )

        # Collect all errors
        all_errors: list[str] = []
        all_warnings: list[str] = []

        all_errors.extend(lint_result.errors)
        all_warnings.extend(lint_result.warnings)
        all_errors.extend(typecheck_result.errors)
        all_warnings.extend(typecheck_result.warnings)
        if test_result:
            all_errors.extend(test_result.errors)

        if should_fail:
            return VerificationResult(
                success=False,
                message=f"Step verification failed: {reason}",
                errors=all_errors,
                warnings=all_warnings,
                files_checked=python_files,
            )

        return VerificationResult(
            success=True,
            message="Step verification passed",
            errors=[],
            warnings=all_warnings,
            files_checked=python_files,
        )

    async def verify_plan(self, plan: Plan) -> VerificationResult:
        """
        Full verification at plan completion.

        Runs complete test suite and full lint/typecheck on the project.

        Args:
            plan: The completed plan to verify

        Returns:
            VerificationResult with overall success status
        """
        # Run full verification on project
        src_dir = str(self._project_root / "src")
        tests_dir = str(self._project_root / "tests")

        # Check if directories exist
        src_exists = (self._project_root / "src").exists()
        tests_exist = (self._project_root / "tests").exists()

        lint_paths = [src_dir] if src_exists else [str(self._project_root)]
        typecheck_paths = [src_dir] if src_exists else [str(self._project_root)]
        test_paths = [tests_dir] if tests_exist else []

        # Run all verification tools in parallel
        if test_paths:
            lint_result, typecheck_result, test_result = await asyncio.gather(
                self.run_lint(lint_paths),
                self.run_typecheck(typecheck_paths),
                self.run_tests(test_paths),
            )
        else:
            lint_result, typecheck_result = await asyncio.gather(
                self.run_lint(lint_paths),
                self.run_typecheck(typecheck_paths),
            )
            test_result = None

        # Apply policy
        should_fail, reason = self._policy.should_fail(
            lint_result=lint_result,
            typecheck_result=typecheck_result,
            test_result=test_result,
        )

        # Collect all errors
        all_errors: list[str] = []
        all_warnings: list[str] = []

        all_errors.extend(lint_result.errors)
        all_warnings.extend(lint_result.warnings)
        all_errors.extend(typecheck_result.errors)
        all_warnings.extend(typecheck_result.warnings)
        if test_result:
            all_errors.extend(test_result.errors)

        files_checked = lint_paths + typecheck_paths + test_paths

        if should_fail:
            return VerificationResult(
                success=False,
                message=f"Plan verification failed: {reason}",
                errors=all_errors,
                warnings=all_warnings,
                files_checked=files_checked,
            )

        return VerificationResult(
            success=True,
            message="Plan verification passed",
            errors=[],
            warnings=all_warnings,
            files_checked=files_checked,
        )

    async def run_tests(self, test_paths: list[str]) -> UnitTestResult:
        """
        Run pytest on specified paths.

        Args:
            test_paths: List of test file or directory paths

        Returns:
            UnitTestResult with pass/fail counts and output
        """
        if not test_paths:
            return UnitTestResult(
                success=True,
                passed=0,
                failed=0,
                skipped=0,
                errors=[],
                output="No test paths provided",
            )

        try:
            # Security: Validate paths are within project root
            validated_paths = self._validate_paths(test_paths)

            # Run pytest with short traceback and quiet output
            args = ["pytest"] + validated_paths + ["--tb=short", "-q"]
            result = await self._run_subprocess(args)

            if result is None:
                # Tool not installed
                return UnitTestResult(
                    success=True,
                    passed=0,
                    failed=0,
                    skipped=0,
                    errors=[],
                    output="pytest not installed",
                )

            stdout, stderr, returncode = result
            output = stdout + stderr

            # Parse pytest output for counts
            passed, failed, skipped, errors = self._parse_pytest_output(output)

            return UnitTestResult(
                success=failed == 0,
                passed=passed,
                failed=failed,
                skipped=skipped,
                errors=errors,
                output=output,
            )

        except asyncio.TimeoutError:
            return UnitTestResult(
                success=False,
                passed=0,
                failed=0,
                skipped=0,
                errors=["pytest timed out"],
                output="Test execution timed out",
            )
        except PathValidationError as e:
            return UnitTestResult(
                success=False,
                passed=0,
                failed=0,
                skipped=0,
                errors=[f"Path validation failed: {e}"],
                output=str(e),
            )

    async def run_lint(self, file_paths: list[str]) -> LintResult:
        """
        Run ruff on specified paths.

        Args:
            file_paths: List of files or directories to lint

        Returns:
            LintResult with error/warning counts
        """
        if not file_paths:
            return LintResult(
                success=True,
                error_count=0,
                warning_count=0,
                errors=[],
                warnings=[],
                files_checked=[],
            )

        try:
            # Security: Validate paths are within project root
            validated_paths = self._validate_paths(file_paths)

            # Run ruff with JSON output for easy parsing
            args = ["ruff", "check"] + validated_paths + ["--output-format=json"]
            result = await self._run_subprocess(args)

            if result is None:
                # Tool not installed
                return LintResult(
                    success=True,
                    error_count=0,
                    warning_count=0,
                    errors=[],
                    warnings=[],
                    files_checked=file_paths,
                )

            stdout, stderr, returncode = result

            # Parse ruff JSON output
            errors, warnings = self._parse_ruff_output(stdout)

            return LintResult(
                success=len(errors) == 0,
                error_count=len(errors),
                warning_count=len(warnings),
                errors=errors,
                warnings=warnings,
                files_checked=file_paths,
            )

        except asyncio.TimeoutError:
            return LintResult(
                success=False,
                error_count=1,
                warning_count=0,
                errors=["ruff timed out"],
                warnings=[],
                files_checked=file_paths,
            )
        except PathValidationError as e:
            return LintResult(
                success=False,
                error_count=1,
                warning_count=0,
                errors=[f"Path validation failed: {e}"],
                warnings=[],
                files_checked=file_paths,
            )

    async def run_typecheck(self, file_paths: list[str]) -> TypecheckResult:
        """
        Run mypy on specified paths.

        Args:
            file_paths: List of files or directories to type check

        Returns:
            TypecheckResult with error/warning counts
        """
        if not file_paths:
            return TypecheckResult(
                success=True,
                error_count=0,
                warning_count=0,
                errors=[],
                warnings=[],
                files_checked=[],
            )

        try:
            # Security: Validate paths are within project root
            validated_paths = self._validate_paths(file_paths)

            # Run mypy
            args = ["mypy"] + validated_paths
            result = await self._run_subprocess(args)

            if result is None:
                # Tool not installed
                return TypecheckResult(
                    success=True,
                    error_count=0,
                    warning_count=0,
                    errors=[],
                    warnings=[],
                    files_checked=file_paths,
                )

            stdout, stderr, returncode = result
            output = stdout + stderr

            # Parse mypy output
            errors, warnings = self._parse_mypy_output(output)

            return TypecheckResult(
                success=len(errors) == 0,
                error_count=len(errors),
                warning_count=len(warnings),
                errors=errors,
                warnings=warnings,
                files_checked=file_paths,
            )

        except asyncio.TimeoutError:
            return TypecheckResult(
                success=False,
                error_count=1,
                warning_count=0,
                errors=["mypy timed out"],
                warnings=[],
                files_checked=file_paths,
            )
        except PathValidationError as e:
            return TypecheckResult(
                success=False,
                error_count=1,
                warning_count=0,
                errors=[f"Path validation failed: {e}"],
                warnings=[],
                files_checked=file_paths,
            )

    def _find_related_tests(self, source_files: list[str]) -> list[str]:
        """
        Find test files related to source files.

        Uses the convention: src/foo/bar.py -> tests/foo/test_bar.py

        Args:
            source_files: List of source file paths

        Returns:
            List of test file paths that exist
        """
        related_tests: list[str] = []

        for source_path in source_files:
            source = Path(source_path)

            # Skip if already a test file
            if source.name.startswith("test_"):
                if source.exists():
                    related_tests.append(str(source))
                continue

            # Try to find related test file
            # Convention: src/foo/bar.py -> tests/foo/test_bar.py
            parts = source.parts

            # Find 'src' in path and replace with 'tests'
            if "src" in parts:
                src_idx = parts.index("src")
                test_parts = (
                    parts[:src_idx]
                    + ("tests",)
                    + parts[src_idx + 1 : -1]
                    + (f"test_{source.name}",)
                )
                test_path = Path(*test_parts)
            else:
                # Fallback: look in tests/ with test_ prefix
                test_path = self._project_root / "tests" / f"test_{source.name}"

            if test_path.exists():
                related_tests.append(str(test_path))

        return related_tests

    async def _run_subprocess(
        self,
        args: list[str],
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> Optional[tuple[str, str, int]]:
        """
        Run a subprocess asynchronously.

        Args:
            args: Command and arguments
            timeout: Timeout in seconds

        Returns:
            Tuple of (stdout, stderr, returncode), or None if tool not found

        Raises:
            asyncio.TimeoutError: If command times out
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._project_root),
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            returncode = process.returncode or 0

            return stdout, stderr, returncode

        except FileNotFoundError:
            # Tool not installed
            return None
        except OSError as e:
            # Handle Windows-specific errors for missing executables
            if e.errno == 2:  # ENOENT - No such file or directory
                return None
            raise

    def _parse_pytest_output(
        self, output: str
    ) -> tuple[int, int, int, list[str]]:
        """
        Parse pytest output for test counts.

        Args:
            output: Raw pytest output

        Returns:
            Tuple of (passed, failed, skipped, error_messages)
        """
        passed = 0
        failed = 0
        skipped = 0
        errors: list[str] = []

        # Look for summary line like "5 passed, 2 failed, 1 skipped"
        # or "5 passed in 0.5s"
        summary_pattern = r"(\d+)\s+(passed|failed|skipped|error)"
        matches = re.findall(summary_pattern, output, re.IGNORECASE)

        for count_str, status in matches:
            count = int(count_str)
            if status.lower() == "passed":
                passed = count
            elif status.lower() == "failed":
                failed = count
            elif status.lower() == "skipped":
                skipped = count
            elif status.lower() == "error":
                failed += count

        # Extract failure messages (lines starting with FAILED or ERROR)
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("FAILED") or line.startswith("ERROR"):
                errors.append(line)

        return passed, failed, skipped, errors

    def _parse_ruff_output(self, output: str) -> tuple[list[str], list[str]]:
        """
        Parse ruff JSON output for errors and warnings.

        Args:
            output: Raw ruff JSON output

        Returns:
            Tuple of (errors, warnings)
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not output.strip():
            return errors, warnings

        try:
            issues = json.loads(output)
            if not isinstance(issues, list):
                return errors, warnings

            for issue in issues:
                # Format: "path:line:col: CODE message"
                path = issue.get("filename", "unknown")
                line = issue.get("location", {}).get("row", 0)
                col = issue.get("location", {}).get("column", 0)
                code = issue.get("code", "")
                message = issue.get("message", "")

                formatted = f"{path}:{line}:{col}: {code} {message}"

                # Ruff warnings typically have codes starting with W
                # Everything else is treated as an error
                if code.startswith("W"):
                    warnings.append(formatted)
                else:
                    errors.append(formatted)

        except json.JSONDecodeError:
            # Fall back to treating non-empty output as an error
            if output.strip():
                errors.append(f"Failed to parse ruff output: {output[:200]}")

        return errors, warnings

    def _parse_mypy_output(self, output: str) -> tuple[list[str], list[str]]:
        """
        Parse mypy output for errors and warnings.

        Args:
            output: Raw mypy output

        Returns:
            Tuple of (errors, warnings)
        """
        errors: list[str] = []
        warnings: list[str] = []

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Skip summary lines
            if line.startswith("Found") or line.startswith("Success"):
                continue

            # Mypy format: "path:line: error: message" or "path:line: note: message"
            if ": error:" in line:
                errors.append(line)
            elif ": warning:" in line:
                warnings.append(line)
            elif ": note:" in line:
                # Notes are informational, treat as warnings
                warnings.append(line)

        return errors, warnings
