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

from scrappy.task_router.protocols import (
    OutputHandlerProtocol,
    ExecutionStrategyProtocol,
    TaskClassifierProtocol,
    IntentClarifierProtocol,
)


class TestOutputHandlerProtocolConformance:
    """Tests for OutputHandlerProtocol implementations."""








class TestOutputHandlerBehavior:
    """Tests that verify output handler behavior matches protocol contract."""

    def test_buffer_handler_captures_classification(self):
        """BufferOutputHandler should capture classification info."""
        from scrappy.task_router.output_handler import BufferOutputHandler

        handler = BufferOutputHandler()
        handler.log_classification("RESEARCH", 0.85, 5, "Test reasoning")

        output = handler.get_output()
        assert "RESEARCH" in output
        assert "0.85" in output
        assert "Test reasoning" in output

    def test_buffer_handler_captures_provider(self):
        """BufferOutputHandler should capture provider selection."""
        from scrappy.task_router.output_handler import BufferOutputHandler

        handler = BufferOutputHandler()
        handler.log_provider_selection("groq", "llama3", "test source")

        output = handler.get_output()
        assert "groq" in output
        assert "llama3" in output
        assert "test source" in output

    def test_buffer_handler_captures_execution(self):
        """BufferOutputHandler should capture execution start."""
        from scrappy.task_router.output_handler import BufferOutputHandler

        handler = BufferOutputHandler()
        handler.log_execution_start("ResearchStrategy")

        output = handler.get_output()
        assert "ResearchStrategy" in output

    def test_buffer_handler_captures_info(self):
        """BufferOutputHandler should capture info messages."""
        from scrappy.task_router.output_handler import BufferOutputHandler

        handler = BufferOutputHandler()
        handler.log_info("Test info message")

        output = handler.get_output()
        assert "Test info message" in output




class TestExecutionStrategyProtocolConformance:
    """Tests for ExecutionStrategyProtocol implementations."""







class TestExecutionStrategyBehavior:
    """Tests that verify execution strategy behavior matches protocol contract."""

    def test_direct_executor_has_name(self):
        """DirectExecutor.name should return a string."""
        from scrappy.task_router.strategies.direct_executor import DirectExecutor

        executor = DirectExecutor()
        assert isinstance(executor.name, str)
        assert len(executor.name) > 0


class TestTaskClassifierProtocolConformance:
    """Tests for TaskClassifierProtocol."""





class TestIntentClarifierProtocolConformance:
    """Tests for IntentClarifierProtocol implementations."""






class TestIntentClarifierBehavior:
    """Tests that verify clarifier behavior matches protocol contract."""

    def test_null_clarifier_returns_input_unchanged(self):
        """NullClarifier.clarify() should return task unchanged."""
        from scrappy.task_router.intent_clarifier import NullClarifier
        from scrappy.task_router.classifier import ClassifiedTask, TaskType

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
        from scrappy.task_router.intent_clarifier import AutoClarifier
        from scrappy.task_router.classifier import ClassifiedTask, TaskType

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



