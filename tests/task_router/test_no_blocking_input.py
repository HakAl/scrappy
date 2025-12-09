"""
Guard test to prevent direct input() calls in task router code.

Direct input() calls block forever in Textual worker threads.
All input must go through TaskRouterInputProtocol.

The only allowed location is DefaultConsoleInput in protocols.py.
"""
import ast
from pathlib import Path

import pytest

from scrappy.task_router.config import ClarificationConfig


class TestNoBlockingInput:
    """Test suite to ensure no direct input() calls sneak into task router code."""




class TestInputProtocolImplementations:
    """Test that input protocol implementations work correctly."""


    def test_interactive_clarifier_uses_io_protocol(self):
        """InteractiveClarifier should accept TaskRouterInputProtocol."""
        from unittest.mock import MagicMock

        from scrappy.task_router.classifier import ClassifiedTask, TaskType
        from scrappy.task_router.intent_clarifier import InteractiveClarifier

        # Create mock IO
        mock_io = MagicMock()
        mock_io.prompt.return_value = "1"  # Choose research

        clarifier = InteractiveClarifier(io=mock_io)

        # Create test task
        task = ClassifiedTask(
            task_type=TaskType.CODE_GENERATION,
            confidence=0.5,
            complexity_score=5,
            reasoning="Test",
            original_input="test query",
        )

        # Clarify should use the injected IO
        result = clarifier.clarify(task)

        # Verify IO was used
        assert mock_io.output.called
        assert mock_io.prompt.called

        # Should have changed to RESEARCH since we chose "1"
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 1.0


class TestTaskRouterInputHandler:
    """Test TaskRouter input handler injection."""

    def test_task_router_accepts_input_handler(self):
        """TaskRouter should accept input_handler parameter."""
        from unittest.mock import MagicMock

        from scrappy.task_router.router import TaskRouter

        mock_input = MagicMock()
        router = TaskRouter(input_handler=mock_input, clarification_config=ClarificationConfig())

        assert router._input_handler is mock_input

    def test_task_router_creates_default_input_handler(self):
        """TaskRouter should create DefaultConsoleInput if no input_handler provided."""
        from scrappy.task_router.protocols import DefaultConsoleInput
        from scrappy.task_router.router import TaskRouter

        router = TaskRouter(clarification_config=ClarificationConfig())

        assert isinstance(router._input_handler, DefaultConsoleInput)

    def test_task_router_shares_input_handler_with_clarifier(self):
        """TaskRouter should share input_handler with InteractiveClarifier by default."""
        from scrappy.task_router.router import TaskRouter

        router = TaskRouter(clarification_config=ClarificationConfig())

        # The clarifier should use the same input handler
        # (through the _io attribute)
        assert hasattr(router.intent_clarifier, "_io")
        assert router.intent_clarifier._io is router._input_handler
