"""
Platform protocols - abstract interfaces for platform-related operations.

All protocols use structural subtyping (Protocol) for maximum flexibility
and testability. Classes don't need explicit inheritance to satisfy protocols.

Protocols defined:
- PlatformDetectorProtocol: Platform and tool detection
- CommandTranslatorProtocol: Command translation
- CommandValidatorProtocol: Command validation
- CommandExecutorProtocol: Command execution strategy
- PythonCommandFallbackProtocol: Python fallback implementations
- PlatformOrchestratorProtocol: Main orchestrator interface

Usage:
    from src.platform.protocols import PlatformDetectorProtocol

    def use_detector(detector: PlatformDetectorProtocol):
        if detector.is_windows():
            # Windows-specific logic
            pass
"""

from .detection import PlatformDetectorProtocol, PlatformType
from .translation import CommandTranslatorProtocol
from .validation import CommandValidatorProtocol
from .execution import CommandExecutorProtocol, ExecutionResult
from .fallback import PythonCommandFallbackProtocol
from .orchestrator import PlatformOrchestratorProtocol

__all__ = [
    "PlatformDetectorProtocol",
    "PlatformType",
    "CommandTranslatorProtocol",
    "CommandValidatorProtocol",
    "CommandExecutorProtocol",
    "ExecutionResult",
    "PythonCommandFallbackProtocol",
    "PlatformOrchestratorProtocol",
]
