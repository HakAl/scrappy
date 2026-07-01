"""
Platform orchestrator implementation.

Coordinates platform detection, command translation, validation, and
execution strategies to provide smart cross-platform command execution.
"""

from typing import Dict, Any, Optional, List

from scrappy.platform.protocols.detection import PlatformDetectorProtocol
from scrappy.platform.protocols.translation import CommandTranslatorProtocol
from scrappy.platform.protocols.validation import CommandValidatorProtocol
from scrappy.platform.protocols.execution import CommandExecutorProtocol, ExecutionResult


class SmartPlatformOrchestrator:
    """
    Concrete implementation of PlatformOrchestrator.

    Provides smart command execution with automatic platform detection,
    translation, validation, and fallback strategies.

    CRITICAL: All dependencies are INJECTED, not instantiated directly.
    This enables testing, dependency inversion, and loose coupling.
    """

    def __init__(
        self,
        detector: PlatformDetectorProtocol,
        translator: CommandTranslatorProtocol,
        validator: CommandValidatorProtocol,
        executors: List[CommandExecutorProtocol]
    ):
        """
        Initialize the orchestrator with injected dependencies.

        Args:
            detector: Platform detector implementation
            translator: Command translator implementation
            validator: Command validator implementation
            executors: List of command executors in priority order

        Note: Unlike the document plan, we require all dependencies to be
        injected. Factory functions will provide defaults for convenience.
        """
        self._detector = detector
        self._translator = translator
        self._validator = validator
        self._executors = executors

        self._usage_stats = {
            'total_commands': 0,
            'by_method': {
                'native': 0,
                'translated': 0,
                'python_fallback': 0,
                'error': 0
            },
            'by_platform': {},
            'error_rate': 0.0
        }

    @property
    def detector(self) -> PlatformDetectorProtocol:
        """Get platform detector implementation."""
        return self._detector

    @property
    def translator(self) -> CommandTranslatorProtocol:
        """Get command translator implementation."""
        return self._translator

    @property
    def validator(self) -> CommandValidatorProtocol:
        """Get command validator implementation."""
        return self._validator

    @property
    def executors(self) -> list[CommandExecutorProtocol]:
        """Get list of available command executors in priority order."""
        return self._executors

    def smart_execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30
    ) -> ExecutionResult:
        """
        Execute a command with automatic platform translation and Python fallback.

        Tries execution strategies in priority order:
        1. Python fallback for common Unix commands on Windows
        2. Translated commands (Unix to Windows)
        3. Native execution

        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            ExecutionResult with output, returncode, and method used
        """
        is_valid, warning = self._validator.validate_command_for_platform(command)
        if not is_valid:
            self._update_usage_stats('error')
            return ExecutionResult.error(warning)

        for executor in self._executors:
            result = executor.execute(command, cwd, timeout)

            if result.success:
                self._update_usage_stats(result.method)
                return result
            elif result.method in ('timeout', 'error'):
                self._update_usage_stats('error')
                return result

        self._update_usage_stats('error')
        return ExecutionResult.error("All execution strategies failed")

    def get_usage_report(self) -> Dict[str, Any]:
        """
        Get usage statistics report.

        Returns:
            Dictionary containing usage statistics including:
            - total_commands: Total commands executed
            - by_method: Execution method breakdown (native/translated/fallback)
            - by_platform: Platform-specific statistics
            - error_rate: Error rate statistics
        """
        return self._usage_stats.copy()

    def _update_usage_stats(self, method: str):
        """
        Update usage statistics after command execution.

        Args:
            method: Execution method used
        """
        self._usage_stats['total_commands'] += 1

        if method in self._usage_stats['by_method']:
            self._usage_stats['by_method'][method] += 1
        else:
            self._usage_stats['by_method']['error'] += 1

        platform = self._detector.get_platform_name()
        if platform not in self._usage_stats['by_platform']:
            self._usage_stats['by_platform'][platform] = 0
        self._usage_stats['by_platform'][platform] += 1

        total = self._usage_stats['total_commands']
        errors = self._usage_stats['by_method']['error']
        self._usage_stats['error_rate'] = errors / total if total > 0 else 0.0
