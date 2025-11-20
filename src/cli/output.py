"""
Generic output abstraction layer.

Provides library-agnostic output interface. Implementation library (click, rich, etc.)
is completely hidden from consumers. Use adapter pattern to swap implementations.

Usage:
    from src.cli.output import Output, TestOutput

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


class OutputInterface(ABC):
    """Abstract base class for output implementations."""

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

    def styled_echo(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Backward compatible styled echo method."""
        self.print(message, color=fg, bold=bold, newline=nl)

    def input_line(self) -> str:
        """Read raw line of input."""
        try:
            return input()
        except EOFError:
            return ""


class TestOutput(OutputInterface):
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


class RichOutput(OutputInterface):
    """Output implementation using Rich library."""

    def __init__(self):
        """Initialize Rich output."""
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
        """Get user input using Rich prompt."""
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
        """Get confirmation using Rich."""
        try:
            return self._Confirm.ask(text, default=default, console=self._console)
        except EOFError:
            return default


class ClickOutput(OutputInterface):
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


def create_output() -> OutputInterface:
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


class Output(OutputInterface):
    """Main output class that delegates to configured implementation.

    This is the primary class consumers should use. Implementation library
    is selected automatically based on configuration.

    Usage:
        from src.cli.output import Output

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
