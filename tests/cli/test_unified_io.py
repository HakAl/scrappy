"""
Comprehensive tests for UnifiedIO.

Test Matrix:
1. CLI mode (output_sink=None) - Direct console output
2. TUI mode (output_sink=mock) - OutputSink routing
3. Feature completeness - All protocol methods implemented
4. Strategy behavior - Context managers work correctly in both modes
5. Edge cases - Empty strings, None values, special characters
"""

import pytest
from typing import List, Any
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from scrappy.cli.unified_io import UnifiedIO, ProgressTracker, StreamWriter, SimplifiedProgressTracker
from scrappy.cli.protocols import OutputSink, UnifiedIOProtocol
from scrappy.cli.mode_utils import is_tui_mode, get_output_sink


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

    def get_renderable_types(self) -> List[str]:
        """Get types of all posted renderables."""
        return [type(r).__name__ for r in self.renderables]

    def clear(self) -> None:
        """Clear all captured output."""
        self.plain_messages.clear()
        self.renderables.clear()


class TestUnifiedIOCLIMode:
    """Test UnifiedIO in CLI mode (output_sink=None)."""

    def test_implements_protocol(self):
        """UnifiedIO implements UnifiedIOProtocol."""
        io = UnifiedIO()
        assert isinstance(io, UnifiedIOProtocol)

    def test_is_tui_mode_false_in_cli_mode(self):
        """is_tui_mode returns False when output_sink is None."""
        io = UnifiedIO()
        assert io.is_tui_mode is False

    def test_console_property(self):
        """UnifiedIO provides console property."""
        io = UnifiedIO()
        assert isinstance(io.console, Console)

    def test_custom_console(self):
        """UnifiedIO accepts custom console."""
        custom_console = Console()
        io = UnifiedIO(console=custom_console)
        assert io.console is custom_console

    def test_echo_plain_text(self):
        """CLI mode echoes plain text."""
        console = Console(file=None)
        io = UnifiedIO(console=console)

        with console.capture() as capture:
            io.echo("Hello, world!")

        output = capture.get()
        assert "Hello, world!" in output

    def test_secho_styled_text(self):
        """CLI mode outputs styled text."""
        console = Console(file=None, force_terminal=True)
        io = UnifiedIO(console=console)

        with console.capture() as capture:
            io.secho("Error message", fg="red", bold=True)

        output = capture.get()
        assert "Error message" in output

    def test_panel_output(self):
        """CLI mode outputs panels."""
        console = Console(file=None)
        io = UnifiedIO(console=console)

        with console.capture() as capture:
            io.panel("Panel content", title="Test Panel")

        output = capture.get()
        assert "Panel content" in output
        assert "Test Panel" in output

    def test_table_output(self):
        """CLI mode outputs tables."""
        console = Console(file=None)
        io = UnifiedIO(console=console)

        with console.capture() as capture:
            io.table(["Col1", "Col2"], [["a", "b"], ["c", "d"]])

        output = capture.get()
        assert "Col1" in output
        assert "Col2" in output
        assert "a" in output or "b" in output

    def test_syntax_output(self):
        """CLI mode outputs syntax-highlighted code."""
        console = Console(file=None)
        io = UnifiedIO(console=console)

        with console.capture() as capture:
            io.syntax("def foo():\n    pass", language="python")

        output = capture.get()
        assert "def" in output
        assert "foo" in output

    def test_rule_output(self):
        """CLI mode outputs horizontal rules."""
        console = Console(file=None)
        io = UnifiedIO(console=console)

        with console.capture() as capture:
            io.rule("Section")

        output = capture.get()
        assert "Section" in output

    def test_style_returns_markup(self):
        """CLI mode style() returns styled text."""
        io = UnifiedIO()
        styled = io.style("text", fg="red", bold=True)
        assert "text" in styled

    def test_progress_context(self):
        """CLI mode progress context works."""
        io = UnifiedIO()

        with io.progress(total=10, description="Testing") as tracker:
            assert isinstance(tracker, (ProgressTracker, SimplifiedProgressTracker))
            assert tracker.total == 10
            assert tracker.current == 0

            tracker.advance(5)
            assert tracker.current == 5

    def test_spinner_context(self):
        """CLI mode spinner context works."""
        io = UnifiedIO()

        completed = False
        with io.spinner("Working..."):
            completed = True

        assert completed

    def test_stream_context(self):
        """CLI mode stream context works."""
        io = UnifiedIO()

        with io.stream() as writer:
            assert isinstance(writer, StreamWriter)


class TestUnifiedIOTUIMode:
    """Test UnifiedIO in TUI mode (with output_sink)."""

    def test_is_tui_mode_true_in_tui_mode(self):
        """is_tui_mode returns True when output_sink is provided."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)
        assert io.is_tui_mode is True

    def test_routes_through_sink(self):
        """TUI mode routes all output through OutputSink."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.echo("test message")

        assert len(sink.plain_messages) > 0
        assert "test message" in sink.get_all_output()

    def test_secho_posts_renderable(self):
        """TUI mode secho() posts Rich Text renderable."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.secho("styled text", fg="red")

        assert len(sink.renderables) > 0
        assert isinstance(sink.renderables[0], Text)

    def test_panel_posts_renderable(self):
        """TUI mode panel() posts Panel renderable."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.panel("content", title="Title")

        assert "Panel" in sink.get_renderable_types()
        panel = next(r for r in sink.renderables if isinstance(r, Panel))
        assert panel is not None

    def test_table_posts_renderable(self):
        """TUI mode table() posts Table renderable."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.table(["Col1", "Col2"], [["a", "b"]])

        assert "Table" in sink.get_renderable_types()
        table = next(r for r in sink.renderables if isinstance(r, Table))
        assert table is not None

    def test_syntax_posts_renderable(self):
        """TUI mode syntax() posts Syntax renderable."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.syntax("def foo(): pass", language="python")

        assert "Syntax" in sink.get_renderable_types()

    def test_rule_posts_renderable(self):
        """TUI mode rule() posts Rule renderable."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.rule("Section")

        assert "Rule" in sink.get_renderable_types()

    def test_prompt_auto_approves_with_warning(self):
        """TUI mode prompt() auto-approves with warning panel."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        result = io.prompt("Name?", default="User")

        assert result == "User"
        assert "Panel" in sink.get_renderable_types()
        panels = [r for r in sink.renderables if isinstance(r, Panel)]
        assert len(panels) > 0

    def test_confirm_auto_approves_with_warning(self):
        """TUI mode confirm() auto-approves with security warning."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        result = io.confirm("Delete file?")

        assert result is True
        assert "Panel" in sink.get_renderable_types()
        panels = [r for r in sink.renderables if isinstance(r, Panel)]
        assert len(panels) > 0

    def test_input_line_raises_not_implemented(self):
        """TUI mode input_line() raises NotImplementedError."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        with pytest.raises(NotImplementedError, match="not supported in Textual mode"):
            io.input_line()

    def test_spinner_simplified(self):
        """TUI mode spinner logs messages instead of animating."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        with io.spinner("Working..."):
            pass

        output = sink.get_all_output()
        assert "Working..." in output
        assert "Completed" in output

    def test_progress_simplified(self):
        """TUI mode progress uses text-based updates."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        with io.progress(total=10, description="Progress") as tracker:
            assert isinstance(tracker, SimplifiedProgressTracker)
            assert tracker.total == 10

            tracker.advance(3)
            assert tracker.current == 3

        output = sink.get_all_output()
        assert "Progress:" in output or "0/10" in output


class TestProgressTracker:
    """Test ProgressTracker helper class."""

    def test_tracks_progress(self):
        """ProgressTracker tracks current progress."""
        from rich.progress import Progress

        with Progress() as progress:
            task_id = progress.add_task("Test", total=10)
            tracker = ProgressTracker(progress, task_id)

            assert tracker.total == 10
            assert tracker.current == 0
            assert not tracker.completed

            tracker.advance(5)
            assert tracker.current == 5
            assert not tracker.completed

            tracker.advance(5)
            assert tracker.current == 10
            assert tracker.completed

    def test_advance_negative(self):
        """ProgressTracker handles negative advance."""
        from rich.progress import Progress

        with Progress() as progress:
            task_id = progress.add_task("Test", total=10)
            tracker = ProgressTracker(progress, task_id)

            tracker.advance(5)
            tracker.advance(-3)
            assert tracker.current == 2

    def test_update_description(self):
        """ProgressTracker updates description."""
        from rich.progress import Progress

        with Progress() as progress:
            task_id = progress.add_task("Test", total=10)
            tracker = ProgressTracker(progress, task_id)

            tracker.update_description("New description")
            assert progress.tasks[task_id].description == "New description"


class TestSimplifiedProgressTracker:
    """Test SimplifiedProgressTracker for TUI mode."""

    def test_tracks_progress(self):
        """SimplifiedProgressTracker tracks current progress."""
        sink = MockOutputSink()
        tracker = SimplifiedProgressTracker(sink, total=10, description="Test")

        assert tracker.total == 10
        assert tracker.current == 0
        assert not tracker.completed

        tracker.advance(5)
        assert tracker.current == 5
        assert not tracker.completed

        tracker.advance(5)
        assert tracker.current == 10
        assert tracker.completed

    def test_posts_progress_messages(self):
        """SimplifiedProgressTracker posts progress updates to sink."""
        sink = MockOutputSink()
        tracker = SimplifiedProgressTracker(sink, total=10, description="Test")

        tracker.advance(3)

        output = sink.get_all_output()
        assert "Test:" in output or "3/10" in output

    def test_clamps_progress(self):
        """SimplifiedProgressTracker clamps progress to bounds."""
        sink = MockOutputSink()
        tracker = SimplifiedProgressTracker(sink, total=10, description="Test")

        tracker.advance(-5)
        assert tracker.current == 0

        tracker.advance(20)
        assert tracker.current == 10


class TestStreamWriter:
    """Test StreamWriter helper class."""

    def test_writes_without_newline(self):
        """StreamWriter writes text without newline."""
        console = Console(file=None)
        writer = StreamWriter(console)

        with console.capture() as capture:
            writer.write("test")

        output = capture.get()
        assert "test" in output

    def test_writeline_with_newline(self):
        """StreamWriter writeline() adds newline."""
        console = Console(file=None)
        writer = StreamWriter(console)

        with console.capture() as capture:
            writer.writeline("test")

        output = capture.get()
        assert "test" in output

    def test_buffers_content(self):
        """StreamWriter buffers written content."""
        console = Console(file=None)
        writer = StreamWriter(console)

        writer.write("hello")
        writer.write(" ")
        writer.writeline("world")

        buffer = writer.get_buffer()
        assert "hello" in buffer
        assert "world" in buffer


class TestBackwardsCompatibility:
    """Test backwards compatibility with existing code."""

    def test_echo_without_newline(self):
        """echo() supports nl=False."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.echo("test", nl=False)

        output = sink.get_all_output()
        assert "test" in output


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_string_output(self):
        """Handles empty string output."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.echo("")

        assert len(sink.plain_messages) > 0

    def test_none_title_panel(self):
        """Panel with None title works."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.panel("content", title=None)

        assert "Panel" in sink.get_renderable_types()

    def test_empty_table(self):
        """Table with empty rows works."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.table(["Col1"], [])

        assert "Table" in sink.get_renderable_types()

    def test_rule_without_title(self):
        """Rule without title works."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)

        io.rule()

        assert "Rule" in sink.get_renderable_types()


class TestProtocolCompliance:
    """Test compliance with UnifiedIOProtocol."""

    def test_all_cliio_methods_present(self):
        """UnifiedIO implements all CLIIOProtocol methods."""
        io = UnifiedIO()

        assert hasattr(io, 'echo')
        assert hasattr(io, 'secho')
        assert hasattr(io, 'style')
        assert hasattr(io, 'prompt')
        assert hasattr(io, 'confirm')
        assert hasattr(io, 'input_line')
        assert hasattr(io, 'table')
        assert hasattr(io, 'panel')

    def test_all_richoutput_methods_present(self):
        """UnifiedIO implements all RichOutputProtocol methods."""
        io = UnifiedIO()

        assert hasattr(io, 'panel')
        assert hasattr(io, 'table')
        assert hasattr(io, 'syntax')
        assert hasattr(io, 'rule')
        assert hasattr(io, 'progress')
        assert hasattr(io, 'spinner')
        assert hasattr(io, 'stream')

    def test_console_property_present(self):
        """UnifiedIO has console property."""
        io = UnifiedIO()

        assert hasattr(io, 'console')
        assert isinstance(io.console, Console)


class TestModeUtils:
    """Test mode detection utility functions."""

    def test_is_tui_mode_with_cli_io(self):
        """is_tui_mode returns False for CLI mode UnifiedIO."""
        io = UnifiedIO()
        assert is_tui_mode(io) is False

    def test_is_tui_mode_with_tui_io(self):
        """is_tui_mode returns True for TUI mode UnifiedIO."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)
        assert is_tui_mode(io) is True

    def test_is_tui_mode_with_unknown_object(self):
        """is_tui_mode returns False for objects without is_tui_mode attr."""

        class FakeIO:
            pass

        fake = FakeIO()
        assert is_tui_mode(fake) is False

    def test_get_output_sink_cli_mode(self):
        """get_output_sink returns None in CLI mode."""
        io = UnifiedIO()
        assert get_output_sink(io) is None

    def test_get_output_sink_tui_mode(self):
        """get_output_sink returns the OutputSink in TUI mode."""
        sink = MockOutputSink()
        io = UnifiedIO(output_sink=sink)
        assert get_output_sink(io) is sink

    def test_get_output_sink_unknown_object(self):
        """get_output_sink returns None for objects without output_sink attr."""

        class FakeIO:
            pass

        fake = FakeIO()
        assert get_output_sink(fake) is None
