"""
Platform-aware command execution and utilities.

This package provides protocol-based abstractions for platform detection,
command translation, validation, and execution with proper dependency injection.

Main components:
- protocols: Protocol definitions for all platform-related abstractions
- detection: Platform and tool detection
- translation: Command translation for cross-platform compatibility
- validation: Command safety and compatibility validation
- execution: Command execution strategies (native, translated, fallback)
- fallback: Python implementations of Unix commands
- orchestrator: Coordinates all components with strategy pattern
- factory: Convenience functions for creating configured instances

Example usage:
    from scrappy.platform.factory import create_platform_orchestrator

    orchestrator = create_platform_orchestrator()
    result = orchestrator.smart_execute_command("ls -la")

    if result.success:
        print(result.output)
"""

from scrappy.platform.factory import (
    create_platform_orchestrator,
    create_platform_detector,
    create_command_translator,
    create_command_validator,
)

from scrappy.platform.detection import SystemPlatformDetector
from scrappy.platform.translation import SmartCommandTranslator
from scrappy.platform.validation import SecurityCommandValidator
from scrappy.platform.fallback import PythonCommandFallbackImpl
from scrappy.platform.executors import (
    NativeCommandExecutor,
    TranslatedCommandExecutor,
    FallbackCommandExecutor,
)
from scrappy.platform.orchestrator import SmartPlatformOrchestrator
from scrappy.platform.testing import MockPlatformDetector

import sys
import os
import io
from typing import List


# Global cache for validator instance
_cached_validator = None


def configure_console_encoding() -> None:
    """
    Configure UTF-8 encoding for console output on Windows.

    This prevents 'charmap' codec errors when printing Unicode characters.
    Must be called early in application startup before any output.
    """
    detector = create_platform_detector()
    if detector.is_windows():
        # Force UTF-8 encoding for stdout/stderr
        if hasattr(sys.stdout, 'reconfigure'):
            # Python 3.7+ - reconfigure streams to use UTF-8
            try:
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass  # Fallback if reconfigure fails
        else:
            # Older Python - wrap streams
            try:
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
            except Exception:
                pass

        # Set environment variable for child processes
        os.environ['PYTHONUTF8'] = '1'
        os.environ['PYTHONIOENCODING'] = 'utf-8:replace'


def get_dangerous_commands() -> List[str]:
    """Get platform-specific dangerous command patterns."""
    global _cached_validator
    if _cached_validator is None:
        _cached_validator = create_command_validator()
    return _cached_validator.get_dangerous_commands()


def get_interactive_commands() -> List[str]:
    """Get platform-specific interactive command patterns."""
    global _cached_validator
    if _cached_validator is None:
        _cached_validator = create_command_validator()
    return _cached_validator.get_interactive_commands()


# Global cache for translator instance
_cached_translator = None


# Convenience functions for command translation
def is_windows() -> bool:
    """Check if running on Windows."""
    detector = create_platform_detector()
    return detector.is_windows()


def normalize_command_paths(command: str):
    """Normalize paths in shell commands for the current platform."""
    global _cached_translator
    if _cached_translator is None:
        _cached_translator = create_command_translator()
    return _cached_translator.normalize_command_paths(command)


def normalize_npm_command_for_windows(command: str):
    """Normalize npm commands for Windows to prevent Unicode output issues."""
    global _cached_translator
    if _cached_translator is None:
        _cached_translator = create_command_translator()
    return _cached_translator.normalize_npm_command_for_windows(command)


def fix_spring_initializr_command(command: str):
    """Fix curl/PowerShell commands that use Spring Initializr."""
    global _cached_translator
    if _cached_translator is None:
        _cached_translator = create_command_translator()
    return _cached_translator.fix_spring_initializr_command(command)


def validate_command_for_platform(command: str):
    """Validate if a command is appropriate for the current platform."""
    global _cached_validator
    if _cached_validator is None:
        _cached_validator = create_command_validator()
    return _cached_validator.validate_command_for_platform(command)


def intercept_spring_initializr_download(command: str, target_dir: str = "."):
    """Intercept Spring Initializr download commands and suggest using local templates."""
    global _cached_translator
    if _cached_translator is None:
        _cached_translator = create_command_translator()
    return _cached_translator.intercept_spring_initializr_download(command, target_dir)


def get_python_fallback(command: str, cwd=None):
    """Execute Unix commands using Python implementations when native commands fail."""
    from scrappy.platform.executors import FallbackCommandExecutor
    from scrappy.platform.fallback import PythonCommandFallbackImpl

    detector = create_platform_detector()
    executor = FallbackCommandExecutor(
        detector,
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


__all__ = [
    # Factory functions (recommended for production use)
    'create_platform_orchestrator',
    'create_platform_detector',
    'create_command_translator',
    'create_command_validator',
    # Concrete implementations (for advanced use cases and testing)
    'SystemPlatformDetector',
    'SmartCommandTranslator',
    'SecurityCommandValidator',
    'PythonCommandFallbackImpl',
    'NativeCommandExecutor',
    'TranslatedCommandExecutor',
    'FallbackCommandExecutor',
    'SmartPlatformOrchestrator',
    # Testing utilities
    'MockPlatformDetector',
    # Utility functions
    'configure_console_encoding',
    'get_dangerous_commands',
    'get_interactive_commands',
    # Convenience functions (backward compatibility with platform_utils)
    'is_windows',
    'normalize_command_paths',
    'normalize_npm_command_for_windows',
    'fix_spring_initializr_command',
    'validate_command_for_platform',
    'intercept_spring_initializr_download',
    'get_python_fallback',
]
