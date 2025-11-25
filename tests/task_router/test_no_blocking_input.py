"""
Guard test to prevent direct input() calls in task router code.

Direct input() calls block forever in Textual worker threads.
All input must go through TaskRouterInputProtocol.

The only allowed location is DefaultConsoleInput in protocols.py.
"""
import ast
from pathlib import Path

import pytest


class TestNoBlockingInput:
    """Test suite to ensure no direct input() calls sneak into task router code."""

    def test_no_direct_input_calls_in_task_router(self):
        """Ensure no direct input() calls in task router code.

        Direct input() calls block forever in Textual worker threads.
        All input must go through TaskRouterInputProtocol.

        The only allowed locations are:
        - protocols.py: DefaultConsoleInput lives here
        - intent_clarifier.py: _LegacyInputAdapter wraps legacy functions
        """
        task_router_dir = Path("src/task_router")
        # Files that are ALLOWED to contain input() calls
        allowed_files = {
            "protocols.py",  # DefaultConsoleInput lives here
            "intent_clarifier.py",  # _LegacyInputAdapter wraps legacy input_fn
        }

        violations = []

        for py_file in task_router_dir.glob("**/*.py"):
            if py_file.name in allowed_files:
                continue
            if py_file.name.startswith("__"):
                continue  # Skip __init__.py, __pycache__, etc.

            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError:
                continue  # Skip files with syntax errors

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "input":
                        violations.append(
                            f"{py_file.relative_to(Path.cwd())}:{node.lineno}"
                        )

        if violations:
            violation_list = "\n  - ".join(violations)
            pytest.fail(
                f"Direct input() calls found in task router code:\n  - {violation_list}\n\n"
                f"Use TaskRouterInputProtocol instead to avoid blocking in Textual."
            )

    def test_no_direct_input_calls_in_cli_task_router_handler(self):
        """Ensure no direct input() calls in CLI task router handler.

        The CLITaskRouterHandler should use CLIIOInputAdapter for all input.
        """
        handler_file = Path("src/cli/task_router_handler.py")
        if not handler_file.exists():
            pytest.skip("task_router_handler.py not found")

        tree = ast.parse(handler_file.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "input":
                    pytest.fail(
                        f"Direct input() call in {handler_file}:{node.lineno}. "
                        f"Use CLIIOInputAdapter instead."
                    )


class TestInputProtocolImplementations:
    """Test that input protocol implementations work correctly."""

    def test_default_console_input_implements_protocol(self):
        """DefaultConsoleInput should implement TaskRouterInputProtocol."""
        from src.task_router.protocols import (
            DefaultConsoleInput,
            TaskRouterInputProtocol,
        )

        instance = DefaultConsoleInput()

        # Check it has the required methods
        assert hasattr(instance, "prompt")
        assert hasattr(instance, "confirm")
        assert hasattr(instance, "output")
        assert callable(instance.prompt)
        assert callable(instance.confirm)
        assert callable(instance.output)

        # Check it's runtime checkable
        assert isinstance(instance, TaskRouterInputProtocol)

    def test_interactive_clarifier_uses_io_protocol(self):
        """InteractiveClarifier should accept TaskRouterInputProtocol."""
        from unittest.mock import MagicMock

        from src.task_router.classifier import ClassifiedTask, TaskType
        from src.task_router.intent_clarifier import InteractiveClarifier

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

    def test_interactive_clarifier_legacy_mode(self):
        """InteractiveClarifier should support legacy input_fn/output_fn."""
        from src.task_router.classifier import ClassifiedTask, TaskType
        from src.task_router.intent_clarifier import InteractiveClarifier

        outputs = []
        inputs = iter(["2"])  # Choose action

        def mock_input(prompt):
            return next(inputs)

        def mock_output(msg):
            outputs.append(msg)

        clarifier = InteractiveClarifier(input_fn=mock_input, output_fn=mock_output)

        task = ClassifiedTask(
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            complexity_score=5,
            reasoning="Test",
            original_input="test query",
        )

        result = clarifier.clarify(task)

        # Should have used legacy functions
        assert len(outputs) > 0
        # Should have changed to CODE_GENERATION since we chose "2"
        assert result.task_type == TaskType.CODE_GENERATION


class TestTaskRouterInputHandler:
    """Test TaskRouter input handler injection."""

    def test_task_router_accepts_input_handler(self):
        """TaskRouter should accept input_handler parameter."""
        from unittest.mock import MagicMock

        from src.task_router.router import TaskRouter

        mock_input = MagicMock()
        router = TaskRouter(input_handler=mock_input)

        assert router._input_handler is mock_input

    def test_task_router_creates_default_input_handler(self):
        """TaskRouter should create DefaultConsoleInput if no input_handler provided."""
        from src.task_router.protocols import DefaultConsoleInput
        from src.task_router.router import TaskRouter

        router = TaskRouter()

        assert isinstance(router._input_handler, DefaultConsoleInput)

    def test_task_router_shares_input_handler_with_clarifier(self):
        """TaskRouter should share input_handler with InteractiveClarifier by default."""
        from src.task_router.router import TaskRouter

        router = TaskRouter()

        # The clarifier should use the same input handler
        # (through the _io attribute)
        assert hasattr(router.intent_clarifier, "_io")
        assert router.intent_clarifier._io is router._input_handler
