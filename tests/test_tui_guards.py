"""
Tests for TUI mode guards added in Phase 2.

Tests that components raise RuntimeError when used in TUI mode
when they should be using TUI-compatible alternatives.
"""

import pytest
from unittest.mock import MagicMock

from src.infrastructure.output_mode import OutputModeContext


@pytest.fixture(autouse=True)
def reset_output_mode():
    """Ensure clean state before and after each test."""
    OutputModeContext.reset()
    yield
    OutputModeContext.reset()


class TestProgressReporterTUIGuards:
    """Tests for progress reporter TUI mode guards."""

    def test_rich_progress_reporter_raises_in_tui_mode(self):
        """RichProgressReporter raises RuntimeError in TUI mode."""
        from src.infrastructure.progress import RichProgressReporter

        OutputModeContext.set_tui_mode(True)

        with pytest.raises(RuntimeError) as exc_info:
            RichProgressReporter()

        assert "TUI mode" in str(exc_info.value)
        assert "UnifiedIOProgressReporter" in str(exc_info.value)

    def test_rich_progress_reporter_works_in_cli_mode(self):
        """RichProgressReporter works normally in CLI mode."""
        from src.infrastructure.progress import RichProgressReporter

        # Should not raise
        reporter = RichProgressReporter()
        assert reporter._console is None  # Not started yet

    def test_live_progress_reporter_raises_in_tui_mode(self):
        """LiveProgressReporter raises RuntimeError in TUI mode."""
        from src.infrastructure.progress import LiveProgressReporter

        OutputModeContext.set_tui_mode(True)

        with pytest.raises(RuntimeError) as exc_info:
            LiveProgressReporter()

        assert "TUI mode" in str(exc_info.value)
        assert "UnifiedIOProgressReporter" in str(exc_info.value)

    def test_live_progress_reporter_works_in_cli_mode(self):
        """LiveProgressReporter works normally in CLI mode."""
        from src.infrastructure.progress import LiveProgressReporter

        # Should not raise
        reporter = LiveProgressReporter()
        assert reporter._live is None  # Not started yet


class TestOutputHandlerTUIGuards:
    """Tests for output handler TUI mode guards."""

    def test_rich_output_handler_raises_in_tui_mode(self):
        """RichOutputHandler raises RuntimeError in TUI mode."""
        from src.task_router.output_handler import RichOutputHandler
        from rich.console import Console

        OutputModeContext.set_tui_mode(True)

        with pytest.raises(RuntimeError) as exc_info:
            RichOutputHandler(Console())

        assert "TUI mode" in str(exc_info.value)
        assert "CLIIOOutputHandler" in str(exc_info.value)

    def test_rich_output_handler_works_in_cli_mode(self):
        """RichOutputHandler works normally in CLI mode."""
        from src.task_router.output_handler import RichOutputHandler
        from rich.console import Console

        # Should not raise
        handler = RichOutputHandler(Console())
        assert handler._console is not None


class TestDefaultConsoleInputTUIGuards:
    """Tests for DefaultConsoleInput TUI mode guards."""

    def test_prompt_raises_in_tui_mode(self):
        """DefaultConsoleInput.prompt() raises in TUI mode."""
        from src.task_router.protocols import DefaultConsoleInput

        handler = DefaultConsoleInput()
        OutputModeContext.set_tui_mode(True)

        with pytest.raises(RuntimeError) as exc_info:
            handler.prompt("Test?")

        assert "TUI mode" in str(exc_info.value)
        assert "IOBasedInput" in str(exc_info.value)

    def test_confirm_raises_in_tui_mode(self):
        """DefaultConsoleInput.confirm() raises in TUI mode."""
        from src.task_router.protocols import DefaultConsoleInput

        handler = DefaultConsoleInput()
        OutputModeContext.set_tui_mode(True)

        with pytest.raises(RuntimeError) as exc_info:
            handler.confirm("Continue?")

        assert "TUI mode" in str(exc_info.value)

    def test_output_raises_in_tui_mode(self):
        """DefaultConsoleInput.output() raises in TUI mode."""
        from src.task_router.protocols import DefaultConsoleInput

        handler = DefaultConsoleInput()
        OutputModeContext.set_tui_mode(True)

        with pytest.raises(RuntimeError) as exc_info:
            handler.output("Hello")

        assert "TUI mode" in str(exc_info.value)


class TestOutputClassTUIGuards:
    """Tests for Output class TUI mode guards."""

    def test_input_line_raises_in_tui_mode(self):
        """Output.input_line() raises in TUI mode."""
        from src.cli.output import Output

        output = Output()
        OutputModeContext.set_tui_mode(True)

        with pytest.raises(RuntimeError) as exc_info:
            output.input_line()

        assert "TUI mode" in str(exc_info.value)


class TestRichOutputTUIGuards:
    """Tests for RichOutput TUI mode guards."""

    def test_rich_output_raises_in_tui_mode(self):
        """RichOutput raises RuntimeError when instantiated in TUI mode."""
        from src.cli.output import RichOutput

        OutputModeContext.set_tui_mode(True)

        with pytest.raises(RuntimeError) as exc_info:
            RichOutput()

        assert "TUI mode" in str(exc_info.value)
        assert "UnifiedIO" in str(exc_info.value)

    def test_rich_output_works_in_cli_mode(self):
        """RichOutput works normally in CLI mode."""
        from src.cli.output import RichOutput

        # Should not raise
        output = RichOutput()
        assert output._console is not None


class TestDirectConsoleOutputTUIGuards:
    """Tests for DirectConsoleOutput TUI mode guards."""

    def test_input_prompt_raises_in_tui_mode(self):
        """DirectConsoleOutput.input_prompt() raises in TUI mode."""
        from src.cli.unified_io import DirectConsoleOutput
        from rich.console import Console

        strategy = DirectConsoleOutput(Console())
        OutputModeContext.set_tui_mode(True)

        with pytest.raises(RuntimeError) as exc_info:
            strategy.input_prompt("Name?")

        assert "TUI mode" in str(exc_info.value)
        assert "OutputSinkAdapter" in str(exc_info.value)

    def test_input_confirm_raises_in_tui_mode(self):
        """DirectConsoleOutput.input_confirm() raises in TUI mode."""
        from src.cli.unified_io import DirectConsoleOutput
        from rich.console import Console

        strategy = DirectConsoleOutput(Console())
        OutputModeContext.set_tui_mode(True)

        with pytest.raises(RuntimeError) as exc_info:
            strategy.input_confirm("Continue?")

        assert "TUI mode" in str(exc_info.value)

    def test_input_line_raises_in_tui_mode(self):
        """DirectConsoleOutput.input_line() raises in TUI mode."""
        from src.cli.unified_io import DirectConsoleOutput
        from rich.console import Console

        strategy = DirectConsoleOutput(Console())
        OutputModeContext.set_tui_mode(True)

        with pytest.raises(RuntimeError) as exc_info:
            strategy.input_line()

        assert "TUI mode" in str(exc_info.value)


class TestInteractiveBannerTUIGuards:
    """Tests for interactive_banner TUI mode guards."""

    def test_display_banner_raises_when_tui_mode_but_no_sink(self):
        """display_banner raises RuntimeError when TUI mode but no output_sink."""
        from src.cli.interactive_banner import display_banner

        # Mock IO with no output_sink
        mock_io = MagicMock()
        mock_io.is_tui_mode = False  # IO says not TUI
        del mock_io.output_sink  # Ensure no output_sink attribute

        # But OutputModeContext says TUI mode
        OutputModeContext.set_tui_mode(True)  # No sink provided

        with pytest.raises(RuntimeError) as exc_info:
            display_banner(mock_io)

        assert "TUI mode detected" in str(exc_info.value)
        assert "no output_sink available" in str(exc_info.value)

    def test_display_banner_uses_io_output_sink_in_tui_mode(self):
        """display_banner uses io.output_sink when available in TUI mode."""
        from src.cli.interactive_banner import display_banner

        mock_sink = MagicMock()
        mock_io = MagicMock()
        mock_io.is_tui_mode = True
        mock_io.output_sink = mock_sink

        display_banner(mock_io)

        mock_sink.post_renderable.assert_called_once()

    def test_display_banner_uses_context_sink_when_io_has_none(self):
        """display_banner uses OutputModeContext sink when io.output_sink is None."""
        from src.cli.interactive_banner import display_banner

        mock_sink = MagicMock()
        mock_io = MagicMock()
        mock_io.is_tui_mode = False  # IO doesn't know it's TUI
        mock_io.output_sink = None

        # But context says TUI with sink
        OutputModeContext.set_tui_mode(True, mock_sink)

        display_banner(mock_io)

        mock_sink.post_renderable.assert_called_once()

    def test_display_banner_uses_console_in_cli_mode(self):
        """display_banner uses console.print in CLI mode."""
        from src.cli.interactive_banner import display_banner

        mock_console = MagicMock()
        mock_io = MagicMock()
        mock_io.is_tui_mode = False
        mock_io.console = mock_console

        display_banner(mock_io)

        mock_console.print.assert_called_once()


class TestFactoryFunctionsBehavior:
    """Tests that factory functions correctly select implementations based on mode."""

    def test_create_progress_reporter_returns_unified_io_in_tui_mode(self):
        """create_progress_reporter returns UnifiedIOProgressReporter in TUI mode."""
        from src.infrastructure.progress import create_progress_reporter, UnifiedIOProgressReporter

        # Create a mock IO that reports TUI mode
        mock_io = MagicMock()
        mock_io.is_tui_mode = True
        mock_io.secho = MagicMock()

        reporter = create_progress_reporter(mock_io)

        assert isinstance(reporter, UnifiedIOProgressReporter)

    def test_create_output_handler_returns_cliio_in_tui_mode(self):
        """create_output_handler returns CLIIOOutputHandler in TUI mode."""
        from src.task_router.output_handler import create_output_handler, CLIIOOutputHandler

        # Create a mock IO that reports TUI mode
        mock_io = MagicMock()
        mock_io.is_tui_mode = True
        mock_io.echo = MagicMock()

        handler = create_output_handler(mock_io)

        assert isinstance(handler, CLIIOOutputHandler)
