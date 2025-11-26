"""
Output handling implementations.

This module provides injectable output handling to separate business logic
from I/O concerns. This makes the code testable and allows easy switching
between console, file, buffer, or silent output.

All handlers implement the OutputHandlerProtocol from protocols.py.
"""
from typing import List, Optional, TYPE_CHECKING

from rich.console import Console
from rich.table import Table
from rich.text import Text

from src.infrastructure.output_mode import OutputModeContext

if TYPE_CHECKING:
    from ..cli.io_interface import CLIIOProtocol


def format_complexity_bar(complexity: int, width: int = 10) -> str:
    """
    Format complexity as a visual progress bar with percentage.

    Args:
        complexity: Complexity value from 0-10
        width: Width of the progress bar in characters

    Returns:
        Formatted string like "###======= 30%"
    """
    percentage = complexity * 10
    filled = int(width * complexity / 10)
    empty = width - filled

    bar = "#" * filled + "=" * empty
    return f"{bar} {percentage}%"


class ConsoleOutputHandler:
    """
    Console output handler that uses CLIIOProtocol for output.

    This is the default handler for CLI usage. It provides
    formatted output for classification decisions and execution status.

    Following dependency injection principles, accepts optional IO interface.
    If not provided, uses NullOutputHandler behavior (silent).
    """

    def __init__(self, io: Optional['CLIIOProtocol'] = None):
        """Initialize with optional IO interface.

        Args:
            io: Optional CLIIOProtocol instance. If None, output is suppressed.
        """
        self._io = io

    def log_classification(
        self,
        task_type: str,
        confidence: float,
        complexity: int,
        reasoning: str
    ) -> None:
        """Output classification information via IO interface."""
        if not self._io:
            return
        self._io.echo(f"\nTask Classification:")
        self._io.echo(f"  Type: {task_type}")
        self._io.echo(f"  Confidence: {confidence:.2f}")
        self._io.echo(f"  Complexity: {complexity}/10")
        self._io.echo(f"  Reasoning: {reasoning}")

    def log_provider_selection(
        self,
        provider: str,
        model: Optional[str],
        source: str
    ) -> None:
        """Output provider selection via IO interface."""
        if not self._io:
            return
        model_info = f" ({model})" if model else ""
        self._io.echo(f"  Provider: {provider}{model_info} ({source})")

    def log_execution_start(self, strategy_name: str) -> None:
        """Output execution start via IO interface."""
        if not self._io:
            return
        self._io.echo(f"  Executing with: {strategy_name}")

    def log_info(self, message: str) -> None:
        """Output info message via IO interface."""
        if not self._io:
            return
        self._io.echo(f"  {message}")


class BufferOutputHandler:
    """
    Buffer output handler that captures output in memory.

    This is crucial for testing - it allows us to:
    - Verify what would be printed without actually printing
    - Assert on specific output patterns
    - Test business logic without I/O side effects
    """

    def __init__(self):
        """Initialize with empty buffer."""
        self._buffer: List[str] = []

    def log_classification(
        self,
        task_type: str,
        confidence: float,
        complexity: int,
        reasoning: str
    ) -> None:
        """Capture classification information in buffer."""
        self._buffer.append(f"\nTask Classification:")
        self._buffer.append(f"  Type: {task_type}")
        self._buffer.append(f"  Confidence: {confidence:.2f}")
        self._buffer.append(f"  Complexity: {complexity}/10")
        self._buffer.append(f"  Reasoning: {reasoning}")

    def log_provider_selection(
        self,
        provider: str,
        model: Optional[str],
        source: str
    ) -> None:
        """Capture provider selection in buffer."""
        model_info = f" ({model})" if model else ""
        self._buffer.append(f"  Provider: {provider}{model_info} ({source})")

    def log_execution_start(self, strategy_name: str) -> None:
        """Capture execution start in buffer."""
        self._buffer.append(f"  Executing with: {strategy_name}")

    def log_info(self, message: str) -> None:
        """Capture info message in buffer."""
        self._buffer.append(f"  {message}")

    def get_output(self) -> str:
        """
        Get all captured output as a single string.

        Returns:
            All captured output joined with newlines
        """
        return "\n".join(self._buffer)

    def clear(self) -> None:
        """Clear the buffer."""
        self._buffer.clear()


class NullOutputHandler:
    """
    Null output handler that produces no output.

    Useful for:
    - Silent mode operation
    - When output is disabled
    - Performance-critical code where logging is overhead
    - Testing paths where output doesn't matter
    """

    def log_classification(
        self,
        task_type: str,
        confidence: float,
        complexity: int,
        reasoning: str
    ) -> None:
        """Do nothing - null implementation."""
        pass

    def log_provider_selection(
        self,
        provider: str,
        model: Optional[str],
        source: str
    ) -> None:
        """Do nothing - null implementation."""
        pass

    def log_execution_start(self, strategy_name: str) -> None:
        """Do nothing - null implementation."""
        pass

    def log_info(self, message: str) -> None:
        """Do nothing - null implementation."""
        pass


class FileOutputHandler:
    """
    File output handler that writes to a file.

    Useful for:
    - Logging to file for later analysis
    - Audit trails
    - Debugging production issues
    """

    def __init__(self, file_path: str):
        """
        Initialize file output handler.

        Args:
            file_path: Path to the output file
        """
        self.file_path = file_path
        # Note: In production, consider using proper logging library
        # This is a simple implementation for demonstration

    def _write(self, message: str) -> None:
        """Write message to file."""
        with open(self.file_path, 'a') as f:
            f.write(message + '\n')

    def log_classification(
        self,
        task_type: str,
        confidence: float,
        complexity: int,
        reasoning: str
    ) -> None:
        """Write classification information to file."""
        self._write(f"\nTask Classification:")
        self._write(f"  Type: {task_type}")
        self._write(f"  Confidence: {confidence:.2f}")
        self._write(f"  Complexity: {complexity}/10")
        self._write(f"  Reasoning: {reasoning}")

    def log_provider_selection(
        self,
        provider: str,
        model: Optional[str],
        source: str
    ) -> None:
        """Write provider selection to file."""
        model_info = f" ({model})" if model else ""
        self._write(f"  Provider: {provider}{model_info} ({source})")

    def log_execution_start(self, strategy_name: str) -> None:
        """Write execution start to file."""
        self._write(f"  Executing with: {strategy_name}")

    def log_info(self, message: str) -> None:
        """Write info message to file."""
        self._write(f"  {message}")


class CLIIOOutputHandler:
    """
    Adapter that wraps CLIIOProtocol to implement OutputHandlerProtocol.

    This enables the task router to use the injected CLI IO system,
    ensuring output goes to the correct UI (Rich/Click/Textual) instead
    of directly to stdout via print().
    """

    def __init__(self, io):
        """
        Initialize with a CLIIOProtocol instance.

        Args:
            io: CLIIOProtocol instance (RichIO, or TextualIO)
        """
        self._io = io

    def log_classification(
        self,
        task_type: str,
        confidence: float,
        complexity: int,
        reasoning: str
    ) -> None:
        """Output classification information via injected IO."""
        self._io.echo("\nTask Classification:")
        self._io.echo(f"  Type: {task_type}")
        self._io.echo(f"  Confidence: {confidence:.2f}")
        self._io.echo(f"  Complexity: {complexity}/10")
        self._io.echo(f"  Reasoning: {reasoning}")

    def log_provider_selection(
        self,
        provider: str,
        model: Optional[str],
        source: str
    ) -> None:
        """Output provider selection via injected IO."""
        model_info = f" ({model})" if model else ""
        self._io.echo(f"  Provider: {provider}{model_info} ({source})")

    def log_execution_start(self, strategy_name: str) -> None:
        """Output execution start via injected IO."""
        self._io.echo(f"  Executing with: {strategy_name}")

    def log_info(self, message: str) -> None:
        """Output info message via injected IO."""
        self._io.echo(f"  {message}")


class RichOutputHandler:
    """
    Rich-enhanced output handler with formatted tables.

    Displays task classification information in visually appealing
    tables with progress bars for complexity and styled output.

    Uses Rich Console for formatted output.

    WARNING: CLI MODE ONLY. This handler outputs directly to the console
    and will bypass Textual's output routing in TUI mode. For TUI-compatible
    output, use CLIIOOutputHandler instead, or use the create_output_handler()
    factory function which automatically selects the correct handler.
    """

    def __init__(self, console: Console):
        """
        Initialize output handler with Rich Console.

        Args:
            console: Rich Console for formatted output

        Raises:
            RuntimeError: If called in TUI mode (must use CLIIOOutputHandler)

        Note:
            For TUI mode, use CLIIOOutputHandler instead which routes
            through the IO abstraction.
        """
        if OutputModeContext.is_tui_mode():
            raise RuntimeError(
                "RichOutputHandler cannot be used in TUI mode. "
                "Use CLIIOOutputHandler or create_output_handler() factory instead."
            )
        self._console = console
        self._classification_data: dict = {}

    def log_classification(
        self,
        task_type: str,
        confidence: float,
        complexity: int,
        reasoning: str
    ) -> None:
        """
        Display classification as a Rich table.

        Creates a formatted table with:
        - Task type
        - Confidence as percentage
        - Complexity as visual progress bar
        - Reasoning text
        """
        # Store for potential integration with provider/strategy
        self._classification_data = {
            'task_type': task_type,
            'confidence': confidence,
            'complexity': complexity,
            'reasoning': reasoning
        }

        # Create classification table
        table = Table(title="Task Classification", show_header=True)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        # Add rows
        table.add_row("Type", task_type)
        table.add_row("Confidence", f"{int(confidence * 100)}%")
        table.add_row("Complexity", format_complexity_bar(complexity))
        table.add_row("Reasoning", reasoning)

        self._console.print(table)

    def log_provider_selection(
        self,
        provider: str,
        model: Optional[str],
        source: str
    ) -> None:
        """
        Display provider selection information.

        Shows provider name, model (if provided), and selection source.
        """
        # Build provider info text
        if model:
            provider_text = f"{provider} ({model})"
        else:
            provider_text = provider

        # Create a simple styled output
        text = Text()
        text.append("Provider: ", style="cyan")
        text.append(provider_text, style="green")
        text.append(f" [{source}]", style="dim")

        self._console.print(text)

    def log_execution_start(self, strategy_name: str) -> None:
        """
        Display execution strategy information.

        Shows the strategy being used for task execution.
        """
        text = Text()
        text.append("Strategy: ", style="cyan")
        text.append(strategy_name, style="yellow")

        self._console.print(text)

    def log_info(self, message: str) -> None:
        """
        Display general info message.

        Args:
            message: The info message to display
        """
        self._console.print(f"  {message}")


def create_output_handler(io: Optional['CLIIOProtocol'] = None, rich_tables: bool = False):
    """
    Factory function to create the appropriate output handler based on mode.

    This function selects the correct output handler implementation:
    - If io is None: Returns NullOutputHandler (silent)
    - If io is in TUI mode: Always returns CLIIOOutputHandler (routes through IO)
    - If io is in CLI mode and rich_tables=True: Returns RichOutputHandler
    - If io is in CLI mode and rich_tables=False: Returns CLIIOOutputHandler

    Args:
        io: Optional CLIIOProtocol instance
        rich_tables: Whether to use Rich tables for output (CLI mode only)

    Returns:
        OutputHandlerProtocol implementation appropriate for the current mode

    Example:
        # In TUI mode, always routes through IO
        handler = create_output_handler(io)

        # In CLI mode with fancy tables
        handler = create_output_handler(io, rich_tables=True)
    """
    if io is None:
        return NullOutputHandler()

    # Import here to avoid circular imports
    from ..cli.mode_utils import is_tui_mode

    if is_tui_mode(io):
        # TUI mode: always use IO-based handler
        return CLIIOOutputHandler(io)

    if rich_tables:
        # CLI mode with Rich tables
        console = getattr(io, 'console', None) or Console()
        return RichOutputHandler(console=console)

    # CLI mode with simple output
    return CLIIOOutputHandler(io)
