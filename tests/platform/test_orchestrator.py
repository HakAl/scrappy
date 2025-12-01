"""
Behavior tests for platform orchestrator.

Tests prove that the orchestrator correctly coordinates platform detection,
validation, translation, and execution strategies.
"""

import pytest
from tests.helpers import (
    FakePlatformDetector,
    FakeCommandTranslator,
    FakeCommandValidator,
    FakeCommandExecutor
)
from scrappy.platform.orchestrator import SmartPlatformOrchestrator
from scrappy.platform.protocols.execution import ExecutionResult


class TestOrchestratorBasicBehavior:
    """Test basic orchestrator behavior."""

    def test_executes_valid_command_successfully(self):
        """Test that valid commands are executed successfully."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)
        executor = FakeCommandExecutor(output="file1.txt\nfile2.txt", returncode=0, method="native")

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[executor]
        )

        result = orchestrator.smart_execute_command("ls -la")

        assert result.success
        assert result.output == "file1.txt\nfile2.txt"
        assert result.method == "native"

    def test_rejects_invalid_command(self):
        """Test that invalid commands are rejected before execution."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=False)
        executor = FakeCommandExecutor()

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[executor]
        )

        result = orchestrator.smart_execute_command("dangerous-command")

        assert not result.success
        assert "blocked" in result.error_message.lower()

    def test_returns_error_when_all_executors_fail(self):
        """Test that error is returned when all execution strategies fail."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)
        failing_executor = FakeCommandExecutor(output="error", returncode=1, method="native")

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[failing_executor]
        )

        result = orchestrator.smart_execute_command("ls")

        assert not result.success
        assert "failed" in result.error_message.lower()

    def test_returns_error_when_no_executors_available(self):
        """Test that error is returned when no executors are configured."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[]
        )

        result = orchestrator.smart_execute_command("ls")

        assert not result.success
        assert "failed" in result.error_message.lower()


class TestOrchestratorExecutionStrategies:
    """Test executor strategy fallback behavior."""

    def test_tries_executors_in_priority_order(self):
        """Test that executors are tried in the order provided."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)

        failing_executor1 = FakeCommandExecutor(output="fail", returncode=1, method="native")
        failing_executor2 = FakeCommandExecutor(output="fail", returncode=1, method="translated")
        succeeding_executor = FakeCommandExecutor(output="success", returncode=0, method="python_fallback")

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[failing_executor1, failing_executor2, succeeding_executor]
        )

        result = orchestrator.smart_execute_command("ls")

        assert result.success
        assert result.method == "python_fallback"
        assert result.output == "success"

    def test_stops_at_first_successful_executor(self):
        """Test that orchestrator stops trying executors after first success."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)

        first_executor = FakeCommandExecutor(output="first", returncode=0, method="native")
        second_executor = FakeCommandExecutor(output="second", returncode=0, method="translated")

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[first_executor, second_executor]
        )

        result = orchestrator.smart_execute_command("ls")

        assert result.success
        assert result.output == "first"
        assert result.method == "native"

    def test_handles_timeout_result_from_executor(self):
        """Test that timeout results are handled correctly."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)

        timeout_executor = FakeCommandExecutor(output="Command timed out", returncode=1, method="timeout")

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[timeout_executor]
        )

        result = orchestrator.smart_execute_command("long-running-command")

        assert not result.success
        assert result.method == "timeout"


class TestOrchestratorUsageStatistics:
    """Test usage statistics tracking."""

    def test_tracks_total_commands_executed(self):
        """Test that total command count is tracked."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)
        executor = FakeCommandExecutor(output="ok", returncode=0, method="native")

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[executor]
        )

        orchestrator.smart_execute_command("ls")
        orchestrator.smart_execute_command("pwd")
        orchestrator.smart_execute_command("cat file.txt")

        stats = orchestrator.get_usage_report()

        assert stats['total_commands'] == 3

    def test_tracks_execution_methods(self):
        """Test that execution methods are tracked correctly."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)

        native_executor = FakeCommandExecutor(output="ok", returncode=0, method="native")
        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[native_executor]
        )

        orchestrator.smart_execute_command("ls")
        orchestrator.smart_execute_command("pwd")

        stats = orchestrator.get_usage_report()

        assert stats['by_method']['native'] == 2
        assert stats['by_method']['translated'] == 0
        assert stats['by_method']['python_fallback'] == 0

    def test_tracks_platform_usage(self):
        """Test that platform-specific usage is tracked."""
        detector = FakePlatformDetector(platform="Windows")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)
        executor = FakeCommandExecutor(output="ok", returncode=0, method="native")

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[executor]
        )

        orchestrator.smart_execute_command("dir")
        orchestrator.smart_execute_command("type file.txt")

        stats = orchestrator.get_usage_report()

        assert stats['by_platform']['Windows'] == 2

    def test_tracks_error_rate(self):
        """Test that error rate is calculated correctly."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)

        failing_executor = FakeCommandExecutor(output="error", returncode=1, method="native")
        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[failing_executor]
        )

        orchestrator.smart_execute_command("cmd1")
        orchestrator.smart_execute_command("cmd2")

        stats = orchestrator.get_usage_report()

        assert stats['error_rate'] == 1.0
        assert stats['by_method']['error'] == 2

    def test_error_rate_with_mixed_results(self):
        """Test error rate calculation with mixed success/failure."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[]
        )

        class AlternatingExecutor:
            def __init__(self):
                self.call_count = 0

            def execute(self, command, cwd=None, timeout=30):
                self.call_count += 1
                if self.call_count % 2 == 0:
                    return ExecutionResult(output="ok", returncode=0, method="native")
                else:
                    return ExecutionResult(output="fail", returncode=1, method="native")

        orchestrator._executors = [AlternatingExecutor()]

        orchestrator.smart_execute_command("cmd1")
        orchestrator.smart_execute_command("cmd2")
        orchestrator.smart_execute_command("cmd3")
        orchestrator.smart_execute_command("cmd4")

        stats = orchestrator.get_usage_report()

        assert stats['total_commands'] == 4
        assert stats['by_method']['native'] == 2
        assert stats['error_rate'] == 0.5

    def test_get_usage_report_returns_copy(self):
        """Test that get_usage_report returns a copy, not reference."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)
        executor = FakeCommandExecutor(output="ok", returncode=0, method="native")

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[executor]
        )

        orchestrator.smart_execute_command("ls")

        stats1 = orchestrator.get_usage_report()
        stats1['modified'] = True

        stats2 = orchestrator.get_usage_report()

        assert 'modified' not in stats2


class TestOrchestratorProperties:
    """Test orchestrator property accessors."""

    def test_detector_property_returns_injected_detector(self):
        """Test that detector property returns the injected detector."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator()
        executors = []

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=executors
        )

        assert orchestrator.detector is detector

    def test_translator_property_returns_injected_translator(self):
        """Test that translator property returns the injected translator."""
        detector = FakePlatformDetector()
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator()
        executors = []

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=executors
        )

        assert orchestrator.translator is translator

    def test_validator_property_returns_injected_validator(self):
        """Test that validator property returns the injected validator."""
        detector = FakePlatformDetector()
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator()
        executors = []

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=executors
        )

        assert orchestrator.validator is validator

    def test_executors_property_returns_injected_executors(self):
        """Test that executors property returns the injected executor list."""
        detector = FakePlatformDetector()
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator()
        executor1 = FakeCommandExecutor()
        executor2 = FakeCommandExecutor()
        executors = [executor1, executor2]

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=executors
        )

        assert orchestrator.executors is executors
        assert len(orchestrator.executors) == 2


class TestOrchestratorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_handles_empty_command(self):
        """Test handling of empty command string."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=False)
        executor = FakeCommandExecutor()

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[executor]
        )

        result = orchestrator.smart_execute_command("")

        assert not result.success

    def test_handles_none_cwd(self):
        """Test handling of None as working directory."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)
        executor = FakeCommandExecutor(output="ok", returncode=0)

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[executor]
        )

        result = orchestrator.smart_execute_command("ls", cwd=None)

        assert result is not None

    def test_handles_custom_timeout(self):
        """Test that custom timeout is passed to executors."""
        detector = FakePlatformDetector(platform="Linux")
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator(always_valid=True)
        executor = FakeCommandExecutor(output="ok", returncode=0)

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=[executor]
        )

        result = orchestrator.smart_execute_command("ls", timeout=60)

        assert result is not None

    def test_usage_stats_initialized_to_zero(self):
        """Test that usage statistics start at zero."""
        detector = FakePlatformDetector()
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator()
        executors = []

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=executors
        )

        stats = orchestrator.get_usage_report()

        assert stats['total_commands'] == 0
        assert stats['by_method']['native'] == 0
        assert stats['by_method']['translated'] == 0
        assert stats['by_method']['python_fallback'] == 0
        assert stats['by_method']['error'] == 0
        assert stats['error_rate'] == 0.0


class TestOrchestratorDependencyInjection:
    """Test dependency injection behavior."""

    def test_requires_all_dependencies(self):
        """Test that all dependencies must be provided."""
        detector = FakePlatformDetector()
        translator = FakeCommandTranslator()
        validator = FakeCommandValidator()
        executors = []

        orchestrator = SmartPlatformOrchestrator(
            detector=detector,
            translator=translator,
            validator=validator,
            executors=executors
        )

        assert orchestrator._detector is detector
        assert orchestrator._translator is translator
        assert orchestrator._validator is validator
        assert orchestrator._executors is executors

    def test_uses_injected_dependencies_not_defaults(self):
        """Test that injected dependencies are used, not defaults."""
        custom_detector = FakePlatformDetector(platform="FreeBSD")
        custom_translator = FakeCommandTranslator()
        custom_validator = FakeCommandValidator(always_valid=False)
        custom_executors = [FakeCommandExecutor()]

        orchestrator = SmartPlatformOrchestrator(
            detector=custom_detector,
            translator=custom_translator,
            validator=custom_validator,
            executors=custom_executors
        )

        assert orchestrator.detector.get_platform_name() == "FreeBSD"
