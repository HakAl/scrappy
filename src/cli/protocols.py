"""
Protocol definitions for CLI handlers.

This module defines the common interface that all CLI handlers must implement,
enabling consistent behavior, testability, and type checking across the CLI layer.
"""

from typing import TYPE_CHECKING, Protocol, Dict, Any, List, Optional, Callable, runtime_checkable

if TYPE_CHECKING:
    from ..orchestrator.protocols import Orchestrator


@runtime_checkable
class CLIHandlerProtocol(Protocol):
    """Protocol defining common interface for all CLI handlers.

    All CLI handlers should implement this protocol to ensure consistent
    behavior and enable proper type checking. The protocol defines:

    - orchestrator: Reference to the Orchestrator for LLM operations
    - Lifecycle methods: initialize() and cleanup()
    - Diagnostic methods: get_status() and reset()

    Example implementation:
        class MyHandler:
            def __init__(self, orchestrator):
                self.orchestrator = orchestrator
                self._state = {}

            def initialize(self) -> None:
                self._state = {'ready': True}

            def cleanup(self) -> None:
                self._state = {}

            def get_status(self) -> Dict[str, Any]:
                return {'name': 'MyHandler', 'state': self._state}

            def reset(self) -> None:
                self._state = {}

            # Additional custom methods specific to this handler
            def do_something(self):
                ...
    """

    orchestrator: "Orchestrator"

    def initialize(self) -> None:
        """Initialize the handler.

        Called after construction to set up any required state, connections,
        or resources. This is separate from __init__ to allow for deferred
        initialization and easier testing.

        Implementations should:
        - Set up any caches or internal data structures
        - Establish connections to external services if needed
        - Prepare the handler for use
        """
        ...

    def cleanup(self) -> None:
        """Clean up handler resources.

        Called when the handler is being shut down or the CLI session ends.
        Implementations should release any held resources.

        Implementations should:
        - Close any open connections
        - Release any held resources
        - Clear any sensitive data from memory
        """
        ...

    def get_status(self) -> Dict[str, object]:
        """Return handler status and diagnostic information.

        Provides insight into the handler's current state for debugging,
        monitoring, or display purposes.

        Returns:
            Dictionary containing status information. Common keys include:
            - 'name': Handler class name
            - 'initialized': Whether initialize() has been called
            - 'call_count': Number of operations performed
            - 'error_count': Number of errors encountered
            - Additional handler-specific metrics
        """
        ...

    def reset(self) -> None:
        """Reset handler state.

        Clears internal state to initial values without requiring
        reconstruction. Useful for starting fresh within a session
        or between tests.

        Implementations should:
        - Reset counters and metrics to zero
        - Clear caches and histories
        - Return to post-initialize state
        """
        ...


@runtime_checkable
class DisplayFormatterProtocol(Protocol):
    """
    Protocol for display formatting.

    Abstracts display formatting to enable testing without actual
    terminal output and support different output formats.

    Implementations:
    - RichFormatter: Rich text formatting with colors and styles
    - PlainFormatter: Plain text without formatting
    - HTMLFormatter: HTML-formatted output
    - MarkdownFormatter: Markdown-formatted output

    Example:
        def display_results(formatter: DisplayFormatterProtocol, data: Dict[str, Any]) -> str:
            return formatter.format(data)
    """

    def format(self, data: Any, format_type: str = "default") -> str:
        """
        Format data for display.

        Args:
            data: Data to format
            format_type: Type of formatting to apply

        Returns:
            Formatted string
        """
        ...

    def format_table(
        self,
        data: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
    ) -> str:
        """
        Format data as table.

        Args:
            data: List of row dictionaries
            columns: Column names to display (None for all)

        Returns:
            Formatted table string
        """
        ...

    def format_error(
        self,
        error: Exception,
        include_traceback: bool = False,
    ) -> str:
        """
        Format error message.

        Args:
            error: Exception to format
            include_traceback: Whether to include traceback

        Returns:
            Formatted error string
        """
        ...

    def format_list(
        self,
        items: List[Any],
        numbered: bool = False,
    ) -> str:
        """
        Format list of items.

        Args:
            items: List of items to format
            numbered: Use numbered list instead of bullets

        Returns:
            Formatted list string
        """
        ...

    def format_code(
        self,
        code: str,
        language: Optional[str] = None,
    ) -> str:
        """
        Format code block.

        Args:
            code: Code to format
            language: Programming language for syntax highlighting

        Returns:
            Formatted code string
        """
        ...

    def format_json(
        self,
        data: Dict[str, Any],
        indent: int = 2,
    ) -> str:
        """
        Format JSON data.

        Args:
            data: Dictionary to format as JSON
            indent: Indentation spaces

        Returns:
            Formatted JSON string
        """
        ...


@runtime_checkable
class InputValidatorProtocol(Protocol):
    """
    Protocol for input validation.

    Abstracts input validation to enable testing with controlled
    validation and support different validation strategies.

    Implementations:
    - SchemaValidator: Validates against JSON schema
    - RegexValidator: Validates using regex patterns
    - CustomValidator: Custom validation logic
    - NoOpValidator: Always validates successfully

    Example:
        def validate_user_input(validator: InputValidatorProtocol, input: str) -> bool:
            if not validator.validate(input):
                errors = validator.get_errors()
                raise ValueError(f"Invalid input: {errors}")
            return True
    """

    def validate(
        self,
        value: Any,
        rules: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Validate input value.

        Args:
            value: Value to validate
            rules: Optional validation rules

        Returns:
            True if valid, False otherwise
        """
        ...

    def sanitize(
        self,
        value: str,
        strategy: str = "default",
    ) -> str:
        """
        Sanitize input value.

        Args:
            value: Value to sanitize
            strategy: Sanitization strategy to use

        Returns:
            Sanitized value
        """
        ...

    def get_errors(self) -> List[str]:
        """
        Get validation errors from last validation.

        Returns:
            List of error messages
        """
        ...

    def add_rule(
        self,
        name: str,
        validator_func: Callable[[Any], bool],
        error_message: str,
    ) -> None:
        """
        Add custom validation rule.

        Args:
            name: Rule name
            validator_func: Function that returns True if valid
            error_message: Error message if validation fails
        """
        ...

    def remove_rule(self, name: str) -> bool:
        """
        Remove validation rule.

        Args:
            name: Rule name to remove

        Returns:
            True if rule was removed, False if not found
        """
        ...

    def validate_many(
        self,
        values: List[Any],
        rules: Optional[Dict[str, Any]] = None,
    ) -> Dict[int, List[str]]:
        """
        Validate multiple values.

        Args:
            values: List of values to validate
            rules: Optional validation rules

        Returns:
            Dictionary mapping indices to error lists
            Empty dict if all valid
        """
        ...
