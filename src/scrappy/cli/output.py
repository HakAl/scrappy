"""
Generic output abstraction layer.

Provides library-agnostic output interface. Implementation library (click, rich, etc.)
is completely hidden from consumers. Use adapter pattern to swap implementations.

This module implements the FormattedOutputProtocol from scrappy/protocols/output.py,
which extends BaseOutputProtocol with styled output and user interaction.

Usage:
    from scrappy.cli.output import Output, TestOutput

    # Production code - implementation library hidden
    output = Output()
    output.print("Hello", color="green", bold=True)

    # Test code - captures output
    test_output = TestOutput()
    test_output.print("Test")
    assert "Test" in test_output.get_output()
"""

from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod

from scrappy.infrastructure.output_mode import OutputModeContext


# Global configuration
_config = {
    'use_rich': True,  # Default to rich if available, fallback to click
}


def configure_output(use_rich: bool = True) -> None:
    """Configure which output library to use.

    Args:
        use_rich: If True, use rich library. If False, use click.
    """
    global _config
    _config['use_rich'] = use_rich


class FormattedOutputInterface(ABC):
    """Abstract base class for formatted output implementations.

    Implements the FormattedOutputProtocol from src/protocols/output.py,
    providing both:
    - BaseOutputProtocol methods: info, warn, error, success
    - Formatted output methods: print, style, prompt, confirm

    For operational logging only, see BaseOutputProtocol in src/protocols/output.py.
    """

    @abstractmethod
    def print(
        self,
        text: str = "",
        color: Optional[str] = None,
        bold: bool = False,
        newline: bool = True
    ) -> None:
        """Print text with optional styling.

        Args:
            text: Text to print
            color: Color name (red, green, yellow, cyan, etc.)
            bold: Whether to make text bold
            newline: Whether to append newline
        """
        pass

    @abstractmethod
    def style(
        self,
        text: str,
        color: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return styled text for inline use.

        Args:
            text: Text to style
            color: Color name
            bold: Whether to make text bold

        Returns:
            Styled text string
        """
        pass

    @abstractmethod
    def prompt(
        self,
        text: str,
        default: str = ""
    ) -> str:
        """Get user input with prompt.

        Args:
            text: Prompt text
            default: Default value if no input

        Returns:
            User input or default
        """
        pass

    @abstractmethod
    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Get yes/no confirmation.

        Args:
            text: Confirmation prompt
            default: Default value

        Returns:
            True for yes, False for no
        """
        pass

    # BaseOutputProtocol methods - default implementations using print()
    def info(self, message: str) -> None:
        """Output informational message.

        Args:
            message: Information message to output
        """
        self.print(message)

    def warn(self, message: str) -> None:
        """Output warning message.

        Args:
            message: Warning message to output
        """
        self.print(message, color="yellow")

    def error(self, message: str) -> None:
        """Output error message.

        Args:
            message: Error message to output
        """
        self.print(message, color="red", bold=True)

    def success(self, message: str) -> None:
        """Output success message.

        Args:
            message: Success message to output
        """
        self.print(message, color="green")

    # Backward compatibility methods
    def echo(self, message: str = "", nl: bool = True) -> None:
        """Backward compatible echo method."""
        self.print(message, newline=nl)

    def secho(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Backward compatible styled echo method."""
        self.print(message, color=fg, bold=bold, newline=nl)

    def input_line(self) -> str:
        """Read raw line of input.

        WARNING: CLI MODE ONLY. This method uses blocking input()
        which will hang in TUI worker threads. In TUI mode, use
        Input widget events or IOBasedInput from task_router.protocols.

        Raises:
            RuntimeError: If called in TUI mode
        """
        if OutputModeContext.is_tui_mode():
            raise RuntimeError(
                "Output.input_line() called in TUI mode. "
                "Use Input widget events or IOBasedInput instead."
            )
        try:
            return input()
        except EOFError:
            return ""


class TestOutput(FormattedOutputInterface):
    """Test output implementation that captures output for testing.

    Usage in tests:
        output = TestOutput(inputs=["user response"], confirmations=[True])
        my_function(output)
        assert "expected" in output.get_output()
    """

    def __init__(
        self,
        inputs: Optional[List[str]] = None,
        confirmations: Optional[List[bool]] = None
    ):
        """Initialize test output with preset responses.

        Args:
            inputs: List of preset input responses
            confirmations: List of preset confirmation responses
        """
        self._output_buffer: List[str] = []
        self._styled_calls: List[Dict[str, Any]] = []
        self._inputs = list(inputs) if inputs else []
        self._confirmations = list(confirmations) if confirmations else []
        self._input_index = 0
        self._confirm_index = 0

    def print(
        self,
        text: str = "",
        color: Optional[str] = None,
        bold: bool = False,
        newline: bool = True
    ) -> None:
        """Capture printed text."""
        # Record style info if styling was requested
        if color or bold:
            self._styled_calls.append({
                'text': text,
                'color': color,
                'bold': bold,
                'newline': newline
            })

        # Capture output
        if newline:
            self._output_buffer.append(text + "\n")
        else:
            self._output_buffer.append(text)

    def style(
        self,
        text: str,
        color: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return unstyled text for testing."""
        return text

    def prompt(
        self,
        text: str,
        default: str = ""
    ) -> str:
        """Return preset input or default."""
        if self._input_index < len(self._inputs):
            result = self._inputs[self._input_index]
            self._input_index += 1
            return result
        return default

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Return preset confirmation or default."""
        if self._confirm_index < len(self._confirmations):
            result = self._confirmations[self._confirm_index]
            self._confirm_index += 1
            return result
        return default

    def get_output(self) -> str:
        """Get all captured output as string."""
        return "".join(self._output_buffer)

    def get_styled_calls(self) -> List[Dict[str, Any]]:
        """Get list of all styled print calls for verification."""
        return self._styled_calls

    def clear(self) -> None:
        """Clear all captured output."""
        self._output_buffer = []
        self._styled_calls = []


class RichOutput(FormattedOutputInterface):
    """Output implementation using Rich library.

    WARNING: CLI MODE ONLY. Do NOT use in Textual/TUI mode.

    This class creates its own Rich Console instance and outputs directly
    to stdout. In TUI mode, all output must route through UnifiedIO's
    OutputSinkAdapter to ensure thread-safe rendering in the Textual app.

    For TUI-compatible output, use:
    - UnifiedIO with output_sink parameter (routes through OutputSink)
    - CLIIOProtocol methods (echo, secho, panel, etc.)

    This class is intended for:
    - Standalone CLI scripts
    - Non-interactive command output
    - Tests (with TestOutput or captured console)
    """

    def __init__(self):
        """Initialize Rich output.

        Raises:
            RuntimeError: If called in TUI mode (must use UnifiedIO)
        """
        if OutputModeContext.is_tui_mode():
            raise RuntimeError(
                "RichOutput cannot be used in TUI mode. "
                "Use UnifiedIO with output_sink instead."
            )
        try:
            from rich.console import Console
            from rich.text import Text
            from rich.prompt import Confirm
            self._console = Console()
            self._Text = Text
            self._Confirm = Confirm
        except ImportError:
            raise ImportError("Rich library required for RichOutput")

    def print(
        self,
        text: str = "",
        color: Optional[str] = None,
        bold: bool = False,
        newline: bool = True
    ) -> None:
        """Print using Rich."""
        style_parts = []
        if bold:
            style_parts.append('bold')
        if color:
            style_parts.append(color)

        style = ' '.join(style_parts) if style_parts else None

        self._console.print(text, style=style, end='\n' if newline else '')

    def style(
        self,
        text: str,
        color: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return styled text using Rich."""
        style_parts = []
        if bold:
            style_parts.append('bold')
        if color:
            style_parts.append(color)

        if not style_parts:
            return text

        style = ' '.join(style_parts)
        styled_text = self._Text(text, style=style)

        with self._console.capture() as capture:
            self._console.print(styled_text, end='')
        return capture.get()

    def prompt(
        self,
        text: str,
        default: str = ""
    ) -> str:
        """Get user input using Rich prompt.

        WARNING: CLI MODE ONLY. Uses blocking input() call that will
        hang in TUI worker threads. In TUI mode, use CLIIOProtocol.prompt()
        which routes through Textual's modal input system.
        """
        prompt_text = text
        if default:
            prompt_text = f"{text} [{default}]"

        self._console.print(prompt_text, end=' ')
        try:
            user_input = input()
            return user_input if user_input else default
        except EOFError:
            return default

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Get confirmation using Rich.

        WARNING: CLI MODE ONLY. Uses blocking Confirm.ask() call that will
        hang in TUI worker threads. In TUI mode, use CLIIOProtocol.confirm()
        which routes through Textual's modal confirmation system.
        """
        try:
            return self._Confirm.ask(text, default=default, console=self._console)
        except EOFError:
            return default


class ClickOutput(FormattedOutputInterface):
    """Output implementation using Click library."""

    def __init__(self):
        """Initialize Click output."""
        try:
            import click
            self._click = click
        except ImportError:
            raise ImportError("Click library required for ClickOutput")

    def print(
        self,
        text: str = "",
        color: Optional[str] = None,
        bold: bool = False,
        newline: bool = True
    ) -> None:
        """Print using Click."""
        if color or bold:
            self._click.secho(text, fg=color, bold=bold, nl=newline)
        else:
            self._click.echo(text, nl=newline)

    def style(
        self,
        text: str,
        color: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return styled text using Click."""
        return self._click.style(text, fg=color, bold=bold)

    def prompt(
        self,
        text: str,
        default: str = ""
    ) -> str:
        """Get user input using Click."""
        return self._click.prompt(text, default=default)

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Get confirmation using Click."""
        return self._click.confirm(text, default=default)


def create_output() -> FormattedOutputInterface:
    """Factory function to create output instance.

    Returns appropriate output implementation based on configuration
    and available libraries.

    Returns:
        Output implementation instance
    """
    if _config['use_rich']:
        try:
            return RichOutput()
        except ImportError:
            # Fallback to click if rich not available
            pass

    try:
        return ClickOutput()
    except ImportError:
        raise ImportError("Either rich or click library must be installed")


class Output(FormattedOutputInterface):
    """Main output class that delegates to configured implementation.

    This is the primary class consumers should use. Implementation library
    is selected automatically based on configuration.

    Usage:
        from scrappy.cli.output import Output

        output = Output()
        output.print("Hello!", color="green")
    """

    def __init__(self):
        """Initialize output using factory."""
        self._impl = create_output()

    def print(
        self,
        text: str = "",
        color: Optional[str] = None,
        bold: bool = False,
        newline: bool = True
    ) -> None:
        """Delegate to implementation."""
        self._impl.print(text, color=color, bold=bold, newline=newline)

    def style(
        self,
        text: str,
        color: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Delegate to implementation."""
        return self._impl.style(text, color=color, bold=bold)

    def prompt(
        self,
        text: str,
        default: str = ""
    ) -> str:
        """Delegate to implementation."""
        return self._impl.prompt(text, default=default)

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Delegate to implementation."""
        return self._impl.confirm(text, default=default)
