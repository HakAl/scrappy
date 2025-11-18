"""
Output handling interfaces and implementations.

This module provides injectable output handling to separate business logic
from I/O concerns. This makes the code testable and allows easy switching
between console, file, buffer, or silent output.
"""
from abc import ABC, abstractmethod
from typing import List, Optional


class OutputHandlerInterface(ABC):
    """
    Interface for handling output/logging.

    Implementations can write to console, file, buffer, or nowhere.
    This makes business logic testable by capturing output.
    """

    @abstractmethod
    def log_classification(
        self,
        task_type: str,
        confidence: float,
        complexity: int,
        reasoning: str
    ) -> None:
        """Log task classification information."""
        pass

    @abstractmethod
    def log_provider_selection(
        self,
        provider: str,
        model: Optional[str],
        source: str
    ) -> None:
        """Log provider selection information."""
        pass

    @abstractmethod
    def log_execution_start(self, strategy_name: str) -> None:
        """Log execution start with strategy name."""
        pass

    @abstractmethod
    def log_info(self, message: str) -> None:
        """Log general information message."""
        pass


class ConsoleOutputHandler(OutputHandlerInterface):
    """
    Console output handler that prints to stdout.

    This is the default handler for CLI usage. It provides
    formatted output for classification decisions and execution status.
    """

    def log_classification(
        self,
        task_type: str,
        confidence: float,
        complexity: int,
        reasoning: str
    ) -> None:
        """Print classification information to console."""
        print(f"\nTask Classification:")
        print(f"  Type: {task_type}")
        print(f"  Confidence: {confidence:.2f}")
        print(f"  Complexity: {complexity}/10")
        print(f"  Reasoning: {reasoning}")

    def log_provider_selection(
        self,
        provider: str,
        model: Optional[str],
        source: str
    ) -> None:
        """Print provider selection to console."""
        model_info = f" ({model})" if model else ""
        print(f"  Provider: {provider}{model_info} ({source})")

    def log_execution_start(self, strategy_name: str) -> None:
        """Print execution start to console."""
        print(f"  Executing with: {strategy_name}")

    def log_info(self, message: str) -> None:
        """Print info message to console."""
        print(f"  {message}")


class BufferOutputHandler(OutputHandlerInterface):
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


class NullOutputHandler(OutputHandlerInterface):
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


class FileOutputHandler(OutputHandlerInterface):
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
