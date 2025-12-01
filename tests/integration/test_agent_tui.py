"""Integration tests for agent command in TUI mode.

These tests verify that agent output routes through the TUI (Textual)
output system correctly, rather than going directly to console.

The key verification is that when running with an OutputSink (TUI mode),
all output goes through the sink and can be captured.
"""

from typing import Any, List, Dict, Optional

import pytest
from unittest.mock import Mock, patch, MagicMock

from scrappy.cli.unified_io import UnifiedIO
from scrappy.cli.mode_utils import is_tui_mode
from scrappy.infrastructure.progress import create_progress_reporter, UnifiedIOProgressReporter
from scrappy.task_router.output_handler import create_output_handler, CLIIOOutputHandler


class MockOutputSink:
    """Mock OutputSink for testing TUI mode output routing."""

    def __init__(self):
        """Initialize mock output sink."""
        self.plain_messages: List[str] = []
        self.renderables: List[Any] = []
        self.post_output_calls = 0
        self.post_renderable_calls = 0

    def post_output(self, content: str) -> None:
        """Capture plain text output."""
        self.plain_messages.append(content)
        self.post_output_calls += 1

    def post_renderable(self, obj: Any) -> None:
        """Capture Rich renderables."""
        self.renderables.append(obj)
        self.post_renderable_calls += 1

    def get_all_output(self) -> str:
        """Get all plain output as string."""
        return "".join(self.plain_messages)

    def get_renderable_types(self) -> List[str]:
        """Get types of all posted renderables."""
        return [type(r).__name__ for r in self.renderables]

    def clear(self) -> None:
        """Clear all captured output."""
        self.plain_messages.clear()
        self.renderables.clear()
        self.post_output_calls = 0
        self.post_renderable_calls = 0


class TestAgentOutputTUIRouting:
    """Test that agent-related output routes through TUI correctly."""

    def test_tui_io_routes_through_sink(self):
        """UnifiedIO in TUI mode routes all output through OutputSink."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        # Verify we're in TUI mode
        assert io.is_tui_mode is True

        # All output should go through sink
        io.echo("test message")
        assert sink.post_output_calls > 0
        assert "test message" in sink.get_all_output()

    def test_styled_output_routes_through_sink(self):
        """Styled output posts renderables in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.secho("styled message", fg="red", bold=True)

        # Should post a renderable, not plain text
        assert sink.post_renderable_calls > 0
        assert "Text" in sink.get_renderable_types()

    def test_panel_output_routes_through_sink(self):
        """Panel output routes through sink in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.panel("Panel content", title="Test Panel")

        assert "Panel" in sink.get_renderable_types()

    def test_progress_reporter_uses_io_in_tui_mode(self):
        """Progress reporter routes through IO in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        # Factory should return UnifiedIOProgressReporter in TUI mode
        reporter = create_progress_reporter(io)
        assert isinstance(reporter, UnifiedIOProgressReporter)

        # Progress output should go through sink
        reporter.start("Processing...")
        reporter.complete("Done!")

        # secho posts renderables
        assert sink.post_renderable_calls > 0

    def test_output_handler_uses_io_in_tui_mode(self):
        """Output handler routes through IO in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        # Factory should return CLIIOOutputHandler in TUI mode
        handler = create_output_handler(io)
        assert isinstance(handler, CLIIOOutputHandler)

        # Handler output should go through sink
        handler.log_classification(
            task_type="research",
            confidence=0.95,
            complexity=5,
            reasoning="Test reasoning"
        )

        # Should have posted some output
        assert sink.post_output_calls > 0 or sink.post_renderable_calls > 0


class TestAgentOutputCLIMode:
    """Test that CLI mode works without TUI sink."""

    def test_cli_io_works_without_sink(self):
        """UnifiedIO in CLI mode works without OutputSink."""
        io = UnifiedIO(output_sink=None)

        # Verify we're in CLI mode
        assert io.is_tui_mode is False

        # Should not crash
        io.echo("test message")
        io.secho("styled message", fg="red")

    def test_cli_mode_progress_reporter(self):
        """Progress reporter works in CLI mode."""
        io = UnifiedIO(output_sink=None)

        reporter = create_progress_reporter(io, use_spinner=False)

        # Should not crash
        reporter.start("Processing...")
        reporter.update(5, "Still processing")
        reporter.complete("Done!")

    def test_cli_mode_output_handler(self):
        """Output handler works in CLI mode."""
        io = UnifiedIO(output_sink=None)

        handler = create_output_handler(io, rich_tables=False)

        # Should not crash
        handler.log_classification(
            task_type="coding",
            confidence=0.90,
            complexity=7,
            reasoning="Complex task"
        )


class TestModeAwareFactories:
    """Test that factory functions select correct implementations based on mode."""

    def test_progress_factory_tui_vs_cli(self):
        """Progress factory selects different implementations for TUI vs CLI."""
        sink = MockOutputSink()
        tui_io = UnifiedIO(output_sink=sink)
        cli_io = UnifiedIO(output_sink=None)

        tui_reporter = create_progress_reporter(tui_io)
        cli_reporter = create_progress_reporter(cli_io, use_spinner=True)

        # TUI mode always gets UnifiedIOProgressReporter
        assert isinstance(tui_reporter, UnifiedIOProgressReporter)

        # CLI mode with spinner gets RichProgressReporter (imported to check)
        from scrappy.infrastructure.progress import RichProgressReporter
        assert isinstance(cli_reporter, RichProgressReporter)

    def test_output_handler_factory_tui_vs_cli(self):
        """Output handler factory selects different implementations for TUI vs CLI."""
        sink = MockOutputSink()
        tui_io = UnifiedIO(output_sink=sink)
        cli_io = UnifiedIO(output_sink=None)

        tui_handler = create_output_handler(tui_io)
        cli_handler_simple = create_output_handler(cli_io, rich_tables=False)
        cli_handler_rich = create_output_handler(cli_io, rich_tables=True)

        # TUI mode always gets CLIIOOutputHandler
        assert isinstance(tui_handler, CLIIOOutputHandler)

        # CLI mode gets CLIIOOutputHandler or RichOutputHandler based on flag
        assert isinstance(cli_handler_simple, CLIIOOutputHandler)

        from scrappy.task_router.output_handler import RichOutputHandler
        assert isinstance(cli_handler_rich, RichOutputHandler)


class TestTUINoDirectConsoleOutput:
    """Test that TUI mode never outputs directly to console."""

    def test_no_direct_print_in_tui_echo(self):
        """TUI mode echo() does not print directly."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        # Capture stdout to verify no direct output
        import io as io_module
        import sys

        old_stdout = sys.stdout
        sys.stdout = io_module.StringIO()

        try:
            io.echo("test message")
            stdout_output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        # Nothing should have been printed directly
        assert stdout_output == ""

        # But the sink should have received the message
        assert "test message" in sink.get_all_output()

    def test_no_direct_print_in_tui_secho(self):
        """TUI mode secho() does not print directly."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        import io as io_module
        import sys

        old_stdout = sys.stdout
        sys.stdout = io_module.StringIO()

        try:
            io.secho("styled message", fg="green")
            stdout_output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        # Nothing should have been printed directly
        assert stdout_output == ""

        # But the sink should have received a renderable
        assert len(sink.renderables) > 0


class TestAgentManagerBridgedIO:
    """Test that CLIAgentManager properly bridges IO to CodeAgent.

    Phase 3 of AGENT_BUG_CLEANUP: These tests verify that the io instance
    passed to CLIAgentManager is properly propagated to CodeAgent, preventing
    the TUI deadlock bug where CodeAgent would create its own unbridged RichIO.
    """

    def test_agent_manager_passes_tui_io_to_code_agent(self):
        """CLIAgentManager passes TUI-mode IO to CodeAgent.

        This is the critical integration test for the TUI deadlock bug fix.
        When running in TUI mode with an OutputSink, the io instance must
        be passed to CodeAgent so that all confirmations go through the
        bridged io, not a new unbridged RichIO.
        """
        from scrappy.cli.agent_manager import CLIAgentManager
        from unittest.mock import Mock, patch

        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        # Verify we're in TUI mode
        assert io.is_tui_mode is True

        # Create mock orchestrator
        mock_orch = Mock()
        mock_orch.context.project_path = "/test/path"
        mock_orch.working_memory = Mock()
        mock_orch.working_memory.add_discovery = Mock()

        manager = CLIAgentManager(mock_orch, io)

        # Verify the manager stored the io directly
        assert manager.io is io
        assert manager.io.is_tui_mode is True

    def test_agent_manager_io_in_tui_mode_routes_through_sink(self):
        """Verify IO stored in CLIAgentManager routes output through sink.

        This tests that output from CLIAgentManager in TUI mode goes through
        the sink, not directly to console.
        """
        from scrappy.cli.agent_manager import CLIAgentManager
        from unittest.mock import Mock

        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        mock_orch = Mock()
        mock_orch.context.project_path = "/test/path"
        mock_orch.working_memory = Mock()

        manager = CLIAgentManager(mock_orch, io)

        # Output through the stored io should go to the sink
        manager.io.echo("Test output from manager")

        assert "Test output from manager" in sink.get_all_output()

    def test_code_agent_receives_tui_io_not_new_instance(self):
        """Verify CodeAgent is created with the passed io, not a new one.

        This is the exact bug that caused the TUI deadlock: CodeAgent was
        being created without io, causing it to create its own unbridged
        RichIO instance.
        """
        from scrappy.cli.agent_manager import CLIAgentManager
        from unittest.mock import Mock, patch

        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        mock_orch = Mock()
        mock_orch.context.project_path = "/test/path"
        mock_orch.working_memory = Mock()
        mock_orch.working_memory.add_discovery = Mock()

        manager = CLIAgentManager(mock_orch, io)

        with patch('scrappy.cli.agent_manager.CodeAgent') as mock_agent_class, \
             patch('scrappy.cli.agent_manager.create_git_checkpoint') as mock_checkpoint:

            mock_checkpoint.return_value = None

            mock_agent = Mock()
            mock_agent.run.return_value = {
                "success": True,
                "result": "Done",
                "iterations": 1,
                "audit_log": []
            }
            mock_agent.planner = "test"
            mock_agent.executor = "test"
            mock_agent.project_root = "/test"
            mock_agent_class.return_value = mock_agent

            # Mock confirm to return False for all prompts
            original_confirm = io.confirm
            io.confirm = Mock(return_value=False)

            try:
                manager.run_agent("Test task")
            finally:
                io.confirm = original_confirm

            # The critical assertion: CodeAgent must receive io=io
            mock_agent_class.assert_called_once()
            call_kwargs = mock_agent_class.call_args[1]
            assert 'io' in call_kwargs, "CodeAgent must receive io parameter"
            assert call_kwargs['io'] is io, "CodeAgent must receive the same io instance"
