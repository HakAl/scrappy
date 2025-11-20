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
    from src.platform.factory import create_platform_orchestrator

    orchestrator = create_platform_orchestrator()
    result = orchestrator.smart_execute_command("ls -la")

    if result.success:
        print(result.output)
"""

from src.platform.factory import (
    create_platform_orchestrator,
    create_platform_detector,
    create_command_translator,
    create_command_validator,
)

from src.platform.detection import SystemPlatformDetector
from src.platform.translation import SmartCommandTranslator
from src.platform.validation import SecurityCommandValidator
from src.platform.fallback import PythonCommandFallbackImpl
from src.platform.executors import (
    NativeCommandExecutor,
    TranslatedCommandExecutor,
    FallbackCommandExecutor,
)
from src.platform.orchestrator import SmartPlatformOrchestrator

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
]
