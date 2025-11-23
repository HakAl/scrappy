"""
Textual-based interactive mode for Scrappy CLI.

Provides a clean TUI interface using Textual framework.
"""

from typing import TYPE_CHECKING

from .textual_app import ScrappyApp

if TYPE_CHECKING:
    from ..orchestrator.protocols import Orchestrator


class TextualInteractiveMode:
    """Interactive mode using Textual TUI.

    Provides a modern terminal UI with:
    - Thread-safe output routing via message queue
    - Native copy/paste support
    - Responsive UI during blocking operations
    - Clean separation of concerns via protocols
    """

    def __init__(self, orchestrator: "Orchestrator"):
        """Initialize TextualInteractiveMode.

        Args:
            orchestrator: The orchestrator instance for routing commands
        """
        self.orchestrator = orchestrator

    def run(self) -> None:
        """Launch the Textual TUI application."""
        app = ScrappyApp(self.orchestrator)
        app.run()
