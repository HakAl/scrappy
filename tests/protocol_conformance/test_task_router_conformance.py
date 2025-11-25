"""Task router protocol conformance tests.

Tests that task router implementations correctly conform to their protocols:
- OutputHandlerProtocol
- ExecutionStrategyProtocol
- TaskClassifierProtocol
- IntentClarifierProtocol
"""

import pytest

from tests.protocol_conformance.conftest import (
    assert_implements_protocol,
    assert_has_method,
    assert_has_property,
)

from src.task_router.protocols import (
    OutputHandlerProtocol,
    ExecutionStrategyProtocol,
    TaskClassifierProtocol,
    IntentClarifierProtocol,
)


class TestOutputHandlerProtocolConformance:
    """Tests for OutputHandlerProtocol implementations."""

    def test_console_handler_implements_protocol(self):
        """ConsoleOutputHandler should implement OutputHandlerProtocol."""
        from src.task_router.output_handler import ConsoleOutputHandler

        assert_implements_protocol(ConsoleOutputHandler, OutputHandlerProtocol)

    def test_buffer_handler_implements_protocol(self):
        """BufferOutputHandler should implement OutputHandlerProtocol."""
        from src.task_router.output_handler import BufferOutputHandler

        assert_implements_protocol(BufferOutputHandler, OutputHandlerProtocol)

    def test_null_handler_implements_protocol(self):
        """NullOutputHandler should implement OutputHandlerProtocol."""
        from src.task_router.output_handler import NullOutputHandler

        assert_implements_protocol(NullOutputHandler, OutputHandlerProtocol)

    def test_file_handler_implements_protocol(self):
        """FileOutputHandler should implement OutputHandlerProtocol."""
        from src.task_router.output_handler import FileOutputHandler

        assert_implements_protocol(FileOutputHandler, OutputHandlerProtocol)

    def test_cliio_handler_implements_protocol(self):
        """CLIIOOutputHandler should implement OutputHandlerProtocol."""
        from src.task_router.output_handler import CLIIOOutputHandler

        assert_implements_protocol(CLIIOOutputHandler, OutputHandlerProtocol)

    def test_rich_handler_implements_protocol(self):
        """RichOutputHandler should implement OutputHandlerProtocol."""
        from src.task_router.output_handler import RichOutputHandler

        assert_implements_protocol(RichOutputHandler, OutputHandlerProtocol)


class TestOutputHandlerBehavior:
    """Tests that verify output handler behavior matches protocol contract."""

    def test_buffer_handler_captures_classification(self):
        """BufferOutputHandler should capture classification info."""
        from src.task_router.output_handler import BufferOutputHandler

        handler = BufferOutputHandler()
        handler.log_classification("RESEARCH", 0.85, 5, "Test reasoning")

        output = handler.get_output()
        assert "RESEARCH" in output
        assert "0.85" in output
        assert "Test reasoning" in output

    def test_buffer_handler_captures_provider(self):
        """BufferOutputHandler should capture provider selection."""
        from src.task_router.output_handler import BufferOutputHandler

        handler = BufferOutputHandler()
        handler.log_provider_selection("groq", "llama3", "test source")

        output = handler.get_output()
        assert "groq" in output
        assert "llama3" in output
        assert "test source" in output

    def test_buffer_handler_captures_execution(self):
        """BufferOutputHandler should capture execution start."""
        from src.task_router.output_handler import BufferOutputHandler

        handler = BufferOutputHandler()
        handler.log_execution_start("ResearchStrategy")

        output = handler.get_output()
        assert "ResearchStrategy" in output

    def test_buffer_handler_captures_info(self):
        """BufferOutputHandler should capture info messages."""
        from src.task_router.output_handler import BufferOutputHandler

        handler = BufferOutputHandler()
        handler.log_info("Test info message")

        output = handler.get_output()
        assert "Test info message" in output

    def test_null_handler_does_not_raise(self):
        """NullOutputHandler should accept calls without raising."""
        from src.task_router.output_handler import NullOutputHandler

        handler = NullOutputHandler()

        # Should not raise any exceptions
        handler.log_classification("TEST", 0.5, 3, "test")
        handler.log_provider_selection("test", None, "source")
        handler.log_execution_start("TestStrategy")
        handler.log_info("info")

    def test_console_handler_without_io_is_silent(self):
        """ConsoleOutputHandler without IO should be silent (not raise)."""
        from src.task_router.output_handler import ConsoleOutputHandler

        handler = ConsoleOutputHandler(io=None)

        # Should not raise
        handler.log_classification("TEST", 0.5, 3, "test")
        handler.log_provider_selection("test", None, "source")
        handler.log_execution_start("TestStrategy")
        handler.log_info("info")


class TestExecutionStrategyProtocolConformance:
    """Tests for ExecutionStrategyProtocol implementations."""

    def test_protocol_has_name(self):
        """ExecutionStrategyProtocol should define name property."""
        assert_has_property(ExecutionStrategyProtocol, 'name')

    def test_protocol_has_execute(self):
        """ExecutionStrategyProtocol should define execute method."""
        assert_has_method(ExecutionStrategyProtocol, 'execute')

    def test_protocol_has_can_handle(self):
        """ExecutionStrategyProtocol should define can_handle method."""
        assert_has_method(ExecutionStrategyProtocol, 'can_handle')

    def test_direct_executor_implements_protocol(self):
        """DirectExecutor should implement ExecutionStrategyProtocol."""
        from src.task_router.strategies.direct_executor import DirectExecutor

        assert_implements_protocol(DirectExecutor, ExecutionStrategyProtocol)

    def test_conversation_executor_implements_protocol(self):
        """ConversationExecutor should implement ExecutionStrategyProtocol."""
        from src.task_router.strategies.conversation_executor import ConversationExecutor

        assert_implements_protocol(ConversationExecutor, ExecutionStrategyProtocol)


class TestExecutionStrategyBehavior:
    """Tests that verify execution strategy behavior matches protocol contract."""

    def test_direct_executor_has_name(self):
        """DirectExecutor.name should return a string."""
        from src.task_router.strategies.direct_executor import DirectExecutor

        executor = DirectExecutor()
        assert isinstance(executor.name, str)
        assert len(executor.name) > 0


class TestTaskClassifierProtocolConformance:
    """Tests for TaskClassifierProtocol."""

    def test_protocol_has_classify(self):
        """TaskClassifierProtocol should define classify method."""
        assert_has_method(TaskClassifierProtocol, 'classify')

    def test_protocol_has_get_confidence(self):
        """TaskClassifierProtocol should define get_confidence method."""
        assert_has_method(TaskClassifierProtocol, 'get_confidence')

    def test_protocol_has_get_supported_types(self):
        """TaskClassifierProtocol should define get_supported_types method."""
        assert_has_method(TaskClassifierProtocol, 'get_supported_types')


class TestIntentClarifierProtocolConformance:
    """Tests for IntentClarifierProtocol implementations."""

    def test_protocol_has_clarify(self):
        """IntentClarifierProtocol should define clarify method."""
        assert_has_method(IntentClarifierProtocol, 'clarify')

    def test_interactive_clarifier_implements_protocol(self):
        """InteractiveClarifier should implement IntentClarifierProtocol."""
        from src.task_router.intent_clarifier import InteractiveClarifier

        assert_implements_protocol(InteractiveClarifier, IntentClarifierProtocol)

    def test_auto_clarifier_implements_protocol(self):
        """AutoClarifier should implement IntentClarifierProtocol."""
        from src.task_router.intent_clarifier import AutoClarifier

        assert_implements_protocol(AutoClarifier, IntentClarifierProtocol)

    def test_null_clarifier_implements_protocol(self):
        """NullClarifier should implement IntentClarifierProtocol."""
        from src.task_router.intent_clarifier import NullClarifier

        assert_implements_protocol(NullClarifier, IntentClarifierProtocol)


class TestIntentClarifierBehavior:
    """Tests that verify clarifier behavior matches protocol contract."""

    def test_null_clarifier_returns_input_unchanged(self):
        """NullClarifier.clarify() should return task unchanged."""
        from src.task_router.intent_clarifier import NullClarifier
        from src.task_router.classifier import ClassifiedTask, TaskType

        clarifier = NullClarifier()
        task = ClassifiedTask(
            original_input="test input",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )

        result = clarifier.clarify(task)

        # Should return the same task
        assert result.original_input == task.original_input
        assert result.task_type == task.task_type

    def test_auto_clarifier_does_not_prompt(self):
        """AutoClarifier should not require user interaction."""
        from src.task_router.intent_clarifier import AutoClarifier
        from src.task_router.classifier import ClassifiedTask, TaskType

        clarifier = AutoClarifier()
        task = ClassifiedTask(
            original_input="test input",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )

        # Should complete without blocking for input
        result = clarifier.clarify(task)

        assert result is not None


class TestDefaultConsoleInputConformance:
    """Tests for DefaultConsoleInput (fallback implementation)."""

    def test_default_input_has_prompt(self):
        """DefaultConsoleInput should have prompt method."""
        from src.task_router.protocols import DefaultConsoleInput

        assert_has_method(DefaultConsoleInput, 'prompt')

    def test_default_input_has_confirm(self):
        """DefaultConsoleInput should have confirm method."""
        from src.task_router.protocols import DefaultConsoleInput

        assert_has_method(DefaultConsoleInput, 'confirm')

    def test_default_input_has_output(self):
        """DefaultConsoleInput should have output method."""
        from src.task_router.protocols import DefaultConsoleInput

        assert_has_method(DefaultConsoleInput, 'output')
