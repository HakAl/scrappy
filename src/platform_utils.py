"""
Platform detection and cross-platform utilities.

FACADE MODULE: This module provides backward-compatible functions that delegate
to the new protocol-based platform architecture in src/platform/.

This facade maintains existing function signatures while internally using the
new decomposed, protocol-based components following SOLID principles.

For new code, prefer importing from src.platform directly:
    from src.platform.factory import create_platform_orchestrator
    orchestrator = create_platform_orchestrator()

For backward compatibility, these module-level functions continue to work:
    from src.platform_utils import is_windows, translate_command_for_platform
"""

from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

# Lazy-loaded singleton orchestrator
_orchestrator = None


def _get_orchestrator():
    """Get or create the singleton platform orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        from src.platform.factory import create_platform_orchestrator
        _orchestrator = create_platform_orchestrator()
    return _orchestrator


def _reset_orchestrator():
    """
    Reset the singleton orchestrator.

    This is primarily for testing purposes, allowing tests to mock
    platform detection and have the orchestrator re-created with
    the mocked values.
    """
    global _orchestrator
    _orchestrator = None


# ============================================================================
# Platform Detection
# ============================================================================

def is_windows() -> bool:
    """Check if running on Windows."""
    return _get_orchestrator().detector.is_windows()


def is_unix() -> bool:
    """Check if running on Unix-like system (Linux, macOS, BSD)."""
    return _get_orchestrator().detector.is_unix()


def is_macos() -> bool:
    """Check if running on macOS."""
    return _get_orchestrator().detector.is_macos()


def get_platform_name() -> str:
    """Get human-readable platform name."""
    return _get_orchestrator().detector.get_platform_name()


def get_shell_info() -> Dict[str, Optional[str]]:
    """
    Get information about available shells.

    Returns:
        Dict with 'default', 'bash', 'powershell', 'cmd' keys.
    """
    return _get_orchestrator().detector.get_shell_info()


def has_git_bash() -> bool:
    """Check if Git Bash is available (common on Windows)."""
    return _get_orchestrator().detector.has_git_bash()


# ============================================================================
# Command Translation
# ============================================================================

def translate_command_for_platform(command: str) -> Tuple[str, bool]:
    """
    Translate Unix commands to Windows equivalents when necessary.

    Args:
        command: Original command

    Returns:
        Tuple of (translated_command, was_translated)
    """
    return _get_orchestrator().translator.translate_command(command)


def normalize_command_paths(command: str) -> Tuple[str, bool, str]:
    """
    Normalize paths in shell commands for the current platform.

    Args:
        command: Shell command that may contain paths

    Returns:
        Tuple of (normalized_command, was_modified, message)
    """
    return _get_orchestrator().translator.normalize_command_paths(command)


def normalize_npm_command_for_windows(command: str) -> Tuple[str, bool, str]:
    """
    Normalize npm commands for Windows to prevent Unicode output issues.

    Args:
        command: npm command to normalize

    Returns:
        Tuple of (normalized_command, was_modified, message)
    """
    return _get_orchestrator().translator.normalize_npm_command_for_windows(command)


def fix_spring_initializr_command(command: str) -> Tuple[str, bool, str]:
    """
    Fix curl/PowerShell commands that use Spring Initializr.

    Args:
        command: The shell command to fix

    Returns:
        Tuple of (fixed_command, was_fixed, message)
    """
    return _get_orchestrator().translator.fix_spring_initializr_command(command)


# ============================================================================
# Command Validation
# ============================================================================

def validate_command_for_platform(command: str) -> Tuple[bool, str]:
    """
    Validate if a command is appropriate for the current platform.

    Args:
        command: Command to validate

    Returns:
        Tuple of (is_valid, warning_message)
    """
    return _get_orchestrator().validator.validate_command_for_platform(command)


def get_dangerous_commands() -> List[str]:
    """
    Get list of dangerous command patterns for the current platform.

    Returns:
        List of dangerous command patterns to block (regex patterns)
    """
    return _get_orchestrator().validator.get_dangerous_commands()


def get_interactive_commands() -> List[str]:
    """
    Get list of commands that may prompt for user input.

    Returns:
        List of interactive command patterns
    """
    return _get_orchestrator().validator.get_interactive_commands()


# ============================================================================
# Path Utilities
# ============================================================================

def get_null_device() -> str:
    """Get the null device path for the current platform."""
    return "NUL" if is_windows() else "/dev/null"


def get_path_separator() -> str:
    """Get the path separator for the current platform."""
    return "\\" if is_windows() else "/"


def normalize_path_for_shell(path: str) -> str:
    """
    Normalize a path for use in shell commands.

    Args:
        path: Path to normalize

    Returns:
        Normalized path string
    """
    if is_windows():
        return path.replace('/', '\\')
    else:
        return path.replace('\\', '/')


def get_file_check_command(path: str) -> str:
    """
    Get platform-appropriate command to check if a file exists.

    Args:
        path: File path to check

    Returns:
        Shell command that checks file existence
    """
    if is_windows():
        return f'if exist "{path}" (echo File exists) else (echo File does not exist)'
    else:
        return f'test -f "{path}" && echo "File exists" || echo "File does not exist"'


def get_directory_list_command(path: str = ".") -> str:
    """
    Get platform-appropriate command to list directory contents.

    Args:
        path: Directory path to list

    Returns:
        Shell command to list directory
    """
    if is_windows():
        return f'dir "{path}"'
    else:
        return f'ls -la "{path}"'


# ============================================================================
# Command Execution
# ============================================================================

def smart_execute_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Execute a command with automatic platform translation and Python fallback.

    Args:
        command: Command to execute
        cwd: Working directory
        timeout: Timeout in seconds

    Returns:
        Dict with 'output', 'returncode', 'method' (native/translated/python_fallback)
    """
    result = _get_orchestrator().smart_execute_command(command, cwd, timeout)
    return {
        'output': result.output,
        'returncode': result.returncode,
        'method': result.method
    }


# ============================================================================
# Python Fallback
# ============================================================================

def get_python_fallback(command: str, cwd: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Execute Unix commands using Python implementations when native commands fail.

    Args:
        command: Unix command to execute
        cwd: Working directory

    Returns:
        Dict with 'output', 'returncode', 'used_fallback' if fallback was used, None otherwise
    """
    # Delegate to fallback executor
    from src.platform.executors import FallbackCommandExecutor
    from src.platform.fallback import PythonCommandFallbackImpl

    executor = FallbackCommandExecutor(
        _get_orchestrator().detector,
        PythonCommandFallbackImpl()
    )

    result = executor.execute(command, cwd)

    if result.method == "python_fallback" and result.success:
        return {
            'output': result.output,
            'returncode': result.returncode,
            'used_fallback': True
        }

    return None


# ============================================================================
# Spring Initializr Utilities (Keep for backward compatibility)
# ============================================================================

def validate_spring_initializr_url(url: str) -> Tuple[bool, str, str]:
    """
    Validate and fix Spring Initializr URLs to prevent 400 Bad Request errors.

    Args:
        url: The Spring Initializr URL to validate

    Returns:
        Tuple of (is_valid, fixed_url, error_message)
    """
    # Delegate to translator
    return _get_orchestrator().translator.validate_spring_initializr_url(url)


def intercept_spring_initializr_download(command: str, target_dir: str = ".") -> Optional[Dict[str, Any]]:
    """
    Intercept Spring Initializr download commands and suggest using local templates.

    Args:
        command: Shell command that might be downloading from Spring Initializr
        target_dir: Directory where the project should be created

    Returns:
        Dict with 'should_intercept', 'reason', 'suggested_action', and 'template_params'
        or None if not a Spring Initializr command
    """
    # Delegate to translator
    return _get_orchestrator().translator.intercept_spring_initializr_download(command, target_dir)


def get_spring_boot_fallback_files(
    group_id: str = "com.example",
    artifact_id: str = "demo",
    package_name: str = "com.example.demo",
    dependencies: List[str] = None
) -> Dict[str, str]:
    """
    Generate fallback Spring Boot project files when network download fails.

    Args:
        group_id: Maven group ID
        artifact_id: Maven artifact ID
        package_name: Java package name
        dependencies: List of dependencies

    Returns:
        Dict mapping file paths to file contents
    """
    # Delegate to translator
    return _get_orchestrator().translator.get_spring_boot_fallback_files(
        group_id, artifact_id, package_name, dependencies
    )
