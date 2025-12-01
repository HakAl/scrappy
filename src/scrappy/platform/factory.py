"""
Factory functions for creating platform components.

Provides convenient functions to create fully configured platform
orchestrators and components with sensible defaults.
"""

from typing import Optional

from scrappy.platform.protocols.orchestrator import PlatformOrchestratorProtocol
from scrappy.platform.detection import SystemPlatformDetector
from scrappy.platform.translation import SmartCommandTranslator
from scrappy.platform.validation import SecurityCommandValidator
from scrappy.platform.fallback import PythonCommandFallbackImpl
from scrappy.platform.executors import (
    NativeCommandExecutor,
    TranslatedCommandExecutor,
    FallbackCommandExecutor
)
from scrappy.platform.orchestrator import SmartPlatformOrchestrator


def create_platform_orchestrator() -> PlatformOrchestratorProtocol:
    """
    Factory function to create a fully configured PlatformOrchestrator
    with default implementations.

    This is the recommended way to instantiate the orchestrator for
    production use, as it provides all default dependencies while
    maintaining testability.

    The execution strategy priority order is:
    1. Python fallback (fastest for common Unix commands on Windows)
    2. Translated commands (Unix to Windows equivalents)
    3. Native execution (commands already appropriate for platform)

    Returns:
        Fully configured PlatformOrchestrator instance
    """
    detector = SystemPlatformDetector()
    translator = SmartCommandTranslator(detector)
    validator = SecurityCommandValidator(detector)
    fallback = PythonCommandFallbackImpl()

    executors = [
        FallbackCommandExecutor(detector, fallback),
        TranslatedCommandExecutor(detector, translator),
        NativeCommandExecutor(detector)
    ]

    return SmartPlatformOrchestrator(
        detector=detector,
        translator=translator,
        validator=validator,
        executors=executors
    )


def create_platform_detector() -> SystemPlatformDetector:
    """
    Create a standalone platform detector.

    Returns:
        SystemPlatformDetector instance
    """
    return SystemPlatformDetector()


def create_command_translator(
    detector: Optional[SystemPlatformDetector] = None
) -> SmartCommandTranslator:
    """
    Create a command translator.

    Args:
        detector: Optional platform detector. Creates default if not provided.

    Returns:
        SmartCommandTranslator instance
    """
    if detector is None:
        detector = SystemPlatformDetector()
    return SmartCommandTranslator(detector)


def create_command_validator(
    detector: Optional[SystemPlatformDetector] = None
) -> SecurityCommandValidator:
    """
    Create a command validator.

    Args:
        detector: Optional platform detector. Creates default if not provided.

    Returns:
        SecurityCommandValidator instance
    """
    if detector is None:
        detector = SystemPlatformDetector()
    return SecurityCommandValidator(detector)
