"""
Protocol definitions for CLI handlers.

This module defines the common interface that all CLI handlers must implement,
enabling consistent behavior, testability, and type checking across the CLI layer.
"""

from typing import TYPE_CHECKING, Protocol, Dict, runtime_checkable

if TYPE_CHECKING:
    from ..orchestrator import AgentOrchestrator


@runtime_checkable
class CLIHandlerProtocol(Protocol):
    """Protocol defining common interface for all CLI handlers.

    All CLI handlers should implement this protocol to ensure consistent
    behavior and enable proper type checking. The protocol defines:

    - orchestrator: Reference to the AgentOrchestrator for LLM operations
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

    orchestrator: "AgentOrchestrator"

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
