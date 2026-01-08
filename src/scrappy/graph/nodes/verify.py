"""
Verify node for LangGraph agent.

Runs linting and type checking on changed Python files to catch errors
before continuing the agent loop.

Features:
- Batched verification (not per-file) for efficiency
- Runs ruff check on all changed Python files
- Runs mypy on all changed Python files (optional, slower)
- Updates error_count and last_error on failures
- Sets files_verified flag on success
- Langfuse tracing integration

Security:
- File paths are validated before passing to subprocess
- Only files within working_dir are processed (prevents path traversal)
- subprocess.run uses shell=False explicitly (defense-in-depth)
"""

import subprocess
from pathlib import Path

from scrappy.graph.state import AgentState
from scrappy.infrastructure.logging import get_logger

logger = get_logger(__name__)


def sanitize_file_paths(
    files: list[str],
    working_dir: str,
) -> tuple[list[str], list[str]]:
    """
    Validate and sanitize file paths for subprocess execution.

    Security checks:
    - File must exist
    - File must be within working_dir (prevents path traversal)
    - Returns absolute paths for clarity

    Args:
        files: List of file paths (relative or absolute)
        working_dir: Working directory that files must be within

    Returns:
        Tuple of (valid_files, skipped_files)
    """
    valid_files: list[str] = []
    skipped_files: list[str] = []

    try:
        working_path = Path(working_dir).resolve()
    except (OSError, ValueError) as e:
        logger.warning("Invalid working_dir %r: %s", working_dir, e)
        return [], files

    for file_path in files:
        try:
            # Resolve to absolute path
            abs_path = Path(working_dir, file_path).resolve()

            # Security: ensure file is within working_dir (prevents ../../../etc/passwd)
            try:
                abs_path.relative_to(working_path)
            except ValueError:
                logger.warning(
                    "Path traversal blocked: %r is outside working_dir %r",
                    file_path,
                    working_dir,
                )
                skipped_files.append(file_path)
                continue

            # Check file exists
            if not abs_path.is_file():
                logger.debug("Skipping non-existent file: %s", file_path)
                skipped_files.append(file_path)
                continue

            valid_files.append(str(abs_path))

        except (OSError, ValueError) as e:
            logger.warning("Invalid file path %r: %s", file_path, e)
            skipped_files.append(file_path)

    return valid_files, skipped_files


def filter_python_files(files: list[str]) -> list[str]:
    """Filter list to only include Python files."""
    return [f for f in files if f.endswith(".py")]


def _revalidate_paths(files: list[str], working_dir: str) -> list[str]:
    """
    Re-validate file paths immediately before subprocess execution.

    This mitigates TOCTOU (time-of-check-time-of-use) vulnerabilities where
    a symlink could be created between initial validation and use.

    Args:
        files: List of file paths to re-validate
        working_dir: Working directory files must be within

    Returns:
        List of files that are still valid (within working_dir)
    """
    working_path = Path(working_dir).resolve()
    valid_files: list[str] = []

    for file_path in files:
        try:
            # Re-resolve to catch any symlink changes
            resolved = Path(file_path).resolve()
            # Verify still within working_dir
            resolved.relative_to(working_path)
            valid_files.append(str(resolved))
        except (ValueError, OSError):
            # Path is now outside working_dir or invalid - skip silently
            logger.warning("TOCTOU: Path %r no longer within working_dir, skipping", file_path)

    return valid_files


def run_ruff(files: list[str], working_dir: str) -> tuple[bool, str]:
    """
    Run ruff check on files.

    Args:
        files: List of Python file paths (should be sanitized absolute paths)
        working_dir: Working directory for subprocess

    Returns:
        Tuple of (success, output)
    """
    # Re-validate paths immediately before subprocess (TOCTOU mitigation)
    safe_files = _revalidate_paths(files, working_dir)
    if not safe_files:
        return True, ""  # No valid files to check

    try:
        result = subprocess.run(
            ["ruff", "check"] + safe_files,
            capture_output=True,
            text=True,
            cwd=working_dir,
            timeout=60,
            shell=False,  # Explicit for security (defense-in-depth)
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip()
    except FileNotFoundError:
        return True, ""  # ruff not installed, skip
    except subprocess.TimeoutExpired:
        return False, "ruff check timed out after 60 seconds"


def run_mypy(files: list[str], working_dir: str) -> tuple[bool, str]:
    """
    Run mypy on files.

    Args:
        files: List of Python file paths (should be sanitized absolute paths)
        working_dir: Working directory for subprocess

    Returns:
        Tuple of (success, output)
    """
    # Re-validate paths immediately before subprocess (TOCTOU mitigation)
    safe_files = _revalidate_paths(files, working_dir)
    if not safe_files:
        return True, ""  # No valid files to check

    try:
        result = subprocess.run(
            ["mypy"] + safe_files,
            capture_output=True,
            text=True,
            cwd=working_dir,
            timeout=120,
            shell=False,  # Explicit for security (defense-in-depth)
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip()
    except FileNotFoundError:
        return True, ""  # mypy not installed, skip
    except subprocess.TimeoutExpired:
        return False, "mypy check timed out after 120 seconds"


def verify_node(
    state: AgentState,
    run_mypy_check: bool = True,
) -> AgentState:
    """
    Verify node - runs linting/testing on changed files.

    Only runs verification if:
    - files_changed is non-empty
    - files_verified is False

    On success: sets files_verified = True
    On failure: increments error_count, sets last_error

    Security:
    - All file paths are sanitized before subprocess execution
    - Path traversal attacks are blocked
    - Only files within working_dir are processed

    Args:
        state: Current agent state
        run_mypy_check: Whether to run mypy (default True, can be slow)

    Returns:
        Updated AgentState
    """
    # Skip if no files changed or already verified
    if not state.files_changed or state.files_verified:
        logger.debug("Skipping verify: no changes or already verified")
        return state

    # Filter to Python files only
    python_files = filter_python_files(state.files_changed)
    if not python_files:
        logger.debug("No Python files to verify")
        return state.model_copy(update={"files_verified": True})

    # Security: sanitize file paths before subprocess execution
    valid_files, skipped_files = sanitize_file_paths(python_files, state.working_dir)

    if skipped_files:
        logger.warning(
            "Skipped %d file(s) during verification: %s",
            len(skipped_files),
            skipped_files,
        )

    if not valid_files:
        logger.debug("No valid Python files to verify after sanitization")
        return state.model_copy(update={"files_verified": True})

    logger.info("Verifying %d Python file(s)", len(valid_files))

    errors: list[str] = []

    # Run ruff on sanitized file paths
    ruff_ok, ruff_output = run_ruff(valid_files, state.working_dir)
    if not ruff_ok:
        errors.append(f"ruff errors:\n{ruff_output}")

    # Run mypy (optional) on sanitized file paths
    if run_mypy_check:
        mypy_ok, mypy_output = run_mypy(valid_files, state.working_dir)
        if not mypy_ok:
            errors.append(f"mypy errors:\n{mypy_output}")

    # Handle results
    if errors:
        error_msg = "\n\n".join(errors)
        logger.warning("Verification failed:\n%s", error_msg)

        # Append error to messages
        new_messages = list(state.messages) + [{
            "role": "system",
            "content": f"[Verification failed]\n{error_msg}",
        }]

        return state.model_copy(
            update={
                "error_count": state.error_count + 1,
                "last_error": error_msg,
                "messages": new_messages,
            }
        )

    logger.info("Verification passed")
    return state.model_copy(update={"files_verified": True})
