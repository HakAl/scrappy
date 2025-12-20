"""
Dependency checking utilities for agent features.

Checks for external tools required by agent mode.
"""

import shutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class DependencyStatus:
    """Result of dependency check."""
    available: bool
    path: Optional[str] = None
    error: Optional[str] = None


def check_git() -> DependencyStatus:
    """Check if git is available.

    Returns:
        DependencyStatus with availability info
    """
    path = shutil.which("git")
    if path:
        return DependencyStatus(available=True, path=path)
    return DependencyStatus(
        available=False,
        error="git not found. Install git to use agent mode."
    )


def check_rg() -> DependencyStatus:
    """Check if ripgrep is available.

    Returns:
        DependencyStatus with availability info
    """
    path = shutil.which("rg")
    if path:
        return DependencyStatus(available=True, path=path)
    return DependencyStatus(
        available=False,
        error="ripgrep (rg) not found. Install for faster text search."
    )


def check_pytest() -> DependencyStatus:
    """Check if pytest is available.

    Returns:
        DependencyStatus with availability info
    """
    path = shutil.which("pytest")
    if path:
        return DependencyStatus(available=True, path=path)
    # Also check for python -m pytest
    python_path = shutil.which("python")
    if python_path:
        return DependencyStatus(
            available=True,
            path=f"{python_path} -m pytest"
        )
    return DependencyStatus(
        available=False,
        error="pytest not found. Install pytest to run tests."
    )


def check_agent_dependencies() -> tuple[bool, list[str]]:
    """Check all dependencies required for agent mode.

    Returns:
        Tuple of (all_ok, list of error messages)
    """
    errors = []

    git_status = check_git()
    if not git_status.available and git_status.error:
        errors.append(git_status.error)

    # pytest is optional - just warn, don't block
    # pytest_status = check_pytest()
    # if not pytest_status.available:
    #     errors.append(pytest_status.error)

    return len(errors) == 0, errors


def check_optional_dependencies() -> list[str]:
    """Check optional dependencies and return warnings.

    These are non-blocking - agent will work without them but with reduced
    functionality or performance.

    Returns:
        List of warning messages for missing optional dependencies.
    """
    warnings = []

    rg_status = check_rg()
    if not rg_status.available and rg_status.error:
        warnings.append(rg_status.error)

    return warnings
