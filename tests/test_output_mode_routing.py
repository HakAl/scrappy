"""Tests to verify output routing in TUI vs CLI mode.

These tests verify that:
1. TUI mode uses OutputSinkAdapter (routes through OutputSink)
2. CLI mode uses DirectConsoleOutput
3. Factory functions respect mode for progress reporters and output handlers
4. Mode detection utilities work correctly
"""

from typing import Any, List

import pytest

from src.cli.unified_io import UnifiedIO
from src.cli.mode_utils import is_tui_mode, get_output_sink
from src.infrastructure.progress import (
    create_progress_reporter,
    NullProgressReporter,
    RichProgressReporter,
    LiveProgressReporter,
    UnifiedIOProgressReporter,
)
from src.task_router.output_handler import (
    create_output_handler,
    NullOutputHandler,
    CLIIOOutputHandler,
    RichOutputHandler,
)


class MockOutputSink:
    """Mock OutputSink for testing TUI mode."""

    def __init__(self):
        """Initialize mock output sink."""
        self.plain_messages: List[str] = []
        self.renderables: List[Any] = []

    def post_output(self, content: str) -> None:
        """Capture plain text output."""
        self.plain_messages.append(content)

    def post_renderable(self, obj: Any) -> None:
        """Capture Rich renderables."""
        self.renderables.append(obj)

    def get_all_output(self) -> str:
        """Get all plain output as string."""
        return "".join(self.plain_messages)

    def clear(self) -> None:
        """Clear all captured output."""
        self.plain_messages.clear()
        self.renderables.clear()


class TestModeDetection:
    """Test mode detection utilities."""

    def test_cli_mode_detection(self):
        """CLI mode (no output_sink) returns is_tui_mode=False."""
        io = UnifiedIO(output_sink=None)
        assert io.is_tui_mode is False
        assert is_tui_mode(io) is False

    def test_tui_mode_detection(self):
        """TUI mode (with output_sink) returns is_tui_mode=True."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)
        assert io.is_tui_mode is True
        assert is_tui_mode(io) is True

    def test_get_output_sink_cli_mode(self):
        """get_output_sink returns None in CLI mode."""
        io = UnifiedIO(output_sink=None)
        assert get_output_sink(io) is None

    def test_get_output_sink_tui_mode(self):
        """get_output_sink returns sink in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)
        assert get_output_sink(io) is sink

    def test_is_tui_mode_handles_non_io_objects(self):
        """is_tui_mode returns False for objects without is_tui_mode attr."""
        class FakeIO:
            pass
        assert is_tui_mode(FakeIO()) is False

    def test_get_output_sink_handles_non_io_objects(self):
        """get_output_sink returns None for objects without output_sink attr."""
        class FakeIO:
            pass
        assert get_output_sink(FakeIO()) is None


class TestProgressReporterFactory:
    """Test create_progress_reporter factory respects mode."""

    def test_none_io_returns_null_reporter(self):
        """No IO returns NullProgressReporter."""
        reporter = create_progress_reporter(io=None)
        assert isinstance(reporter, NullProgressReporter)

    def test_tui_mode_returns_unified_io_reporter(self):
        """TUI mode always returns UnifiedIOProgressReporter."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        # Even with use_spinner=True, TUI mode uses UnifiedIOProgressReporter
        reporter = create_progress_reporter(io, use_spinner=True)
        assert isinstance(reporter, UnifiedIOProgressReporter)

    def test_tui_mode_ignores_use_live(self):
        """TUI mode ignores use_live parameter."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        # use_live=True is ignored in TUI mode
        reporter = create_progress_reporter(io, use_live=True)
        assert isinstance(reporter, UnifiedIOProgressReporter)

    def test_cli_mode_with_spinner_returns_rich_reporter(self):
        """CLI mode with use_spinner returns RichProgressReporter."""
        io = UnifiedIO(output_sink=None)

        reporter = create_progress_reporter(io, use_spinner=True)
        assert isinstance(reporter, RichProgressReporter)

    def test_cli_mode_with_live_returns_live_reporter(self):
        """CLI mode with use_live returns LiveProgressReporter."""
        io = UnifiedIO(output_sink=None)

        reporter = create_progress_reporter(io, use_live=True)
        assert isinstance(reporter, LiveProgressReporter)

    def test_cli_mode_default_returns_unified_io_reporter(self):
        """CLI mode without options returns UnifiedIOProgressReporter."""
        io = UnifiedIO(output_sink=None)

        reporter = create_progress_reporter(io, use_spinner=False, use_live=False)
        assert isinstance(reporter, UnifiedIOProgressReporter)


class TestOutputHandlerFactory:
    """Test create_output_handler factory respects mode."""

    def test_none_io_returns_null_handler(self):
        """No IO returns NullOutputHandler."""
        handler = create_output_handler(io=None)
        assert isinstance(handler, NullOutputHandler)

    def test_tui_mode_returns_cliio_handler(self):
        """TUI mode always returns CLIIOOutputHandler."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        handler = create_output_handler(io)
        assert isinstance(handler, CLIIOOutputHandler)

    def test_tui_mode_ignores_rich_tables(self):
        """TUI mode ignores rich_tables parameter."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        # rich_tables=True is ignored in TUI mode
        handler = create_output_handler(io, rich_tables=True)
        assert isinstance(handler, CLIIOOutputHandler)

    def test_cli_mode_with_rich_tables_returns_rich_handler(self):
        """CLI mode with rich_tables returns RichOutputHandler."""
        io = UnifiedIO(output_sink=None)

        handler = create_output_handler(io, rich_tables=True)
        assert isinstance(handler, RichOutputHandler)

    def test_cli_mode_without_rich_tables_returns_cliio_handler(self):
        """CLI mode without rich_tables returns CLIIOOutputHandler."""
        io = UnifiedIO(output_sink=None)

        handler = create_output_handler(io, rich_tables=False)
        assert isinstance(handler, CLIIOOutputHandler)


class TestTUIOutputRouting:
    """Test that TUI mode routes output through OutputSink."""

    def test_echo_routes_through_sink(self):
        """echo() routes through OutputSink in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.echo("test message")

        assert "test message" in sink.get_all_output()

    def test_secho_routes_through_sink(self):
        """secho() routes through OutputSink in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.secho("styled message", fg="red")

        # Styled output posts a renderable
        assert len(sink.renderables) > 0

    def test_panel_routes_through_sink(self):
        """panel() routes through OutputSink in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.panel("panel content", title="Test Panel")

        assert "Panel" in [type(r).__name__ for r in sink.renderables]

    def test_table_routes_through_sink(self):
        """table() routes through OutputSink in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.table(["Col1", "Col2"], [["a", "b"]])

        assert "Table" in [type(r).__name__ for r in sink.renderables]


class TestCLIOutputDirect:
    """Test that CLI mode outputs directly (not through sink)."""

    def test_cli_mode_has_no_sink(self):
        """CLI mode has no output_sink."""
        io = UnifiedIO(output_sink=None)
        assert get_output_sink(io) is None

    def test_cli_mode_echo_does_not_crash(self):
        """CLI mode echo() works without crashing."""
        io = UnifiedIO(output_sink=None)
        # This should not raise
        io.echo("test message")

    def test_cli_mode_secho_does_not_crash(self):
        """CLI mode secho() works without crashing."""
        io = UnifiedIO(output_sink=None)
        # This should not raise
        io.secho("styled message", fg="red")


class TestProgressReporterTUIBehavior:
    """Test progress reporter behavior in TUI mode."""

    def test_unified_io_reporter_routes_through_io(self):
        """UnifiedIOProgressReporter routes through IO in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)
        reporter = UnifiedIOProgressReporter(io)

        reporter.start("Processing...", total=10)
        reporter.update(5, "Half done")
        reporter.complete("Done!")

        # secho posts Text renderables, not plain text
        # Check that renderables were posted
        assert len(sink.renderables) > 0

    def test_null_reporter_does_nothing(self):
        """NullProgressReporter does nothing (silent)."""
        reporter = NullProgressReporter()

        # These should not raise
        reporter.start("Processing...", total=10)
        reporter.update(5, "Half done")
        reporter.complete("Done!")
        reporter.error("Failed!")


class TestOutputHandlerTUIBehavior:
    """Test output handler behavior in TUI mode."""

    def test_cliio_handler_routes_through_io(self):
        """CLIIOOutputHandler routes through IO in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)
        handler = CLIIOOutputHandler(io)

        handler.log_classification(
            task_type="research",
            confidence=0.95,
            complexity=5,
            reasoning="Test reasoning"
        )

        output = sink.get_all_output()
        assert "research" in output or "Classification" in output

    def test_null_handler_does_nothing(self):
        """NullOutputHandler does nothing (silent)."""
        handler = NullOutputHandler()

        # These should not raise
        handler.log_classification(
            task_type="research",
            confidence=0.95,
            complexity=5,
            reasoning="Test"
        )
        handler.log_provider_selection("openai", "gpt-4", "env")
        handler.log_execution_start("research")
        handler.log_info("Test info message")
