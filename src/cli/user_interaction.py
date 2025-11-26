"""Mode-aware user interaction implementations.

This module provides different strategies for user interactions (prompts, confirmations)
depending on the execution context:

- CLIUserInteraction: Blocking prompts for CLI mode (main thread)
- TUIUserInteraction: Modal dialogs via ThreadSafeAsyncBridge for TUI mode (worker thread)
- AutoApproveInteraction: Fallback with sensible defaults and logging

The UserInteractionProtocol (defined in protocols.py) allows command handlers to
remain agnostic of the execution mode while still providing appropriate UX.

Architecture (per CLAUDE.md):
- Protocol-first: UserInteractionProtocol defines the contract
- Dependency injection: Interaction strategy is injected into handlers
- Single responsibility: Each implementation handles one mode
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .io_interface import CLIIOProtocol
    from .textual_app import ThreadSafeAsyncBridge


class CLIUserInteraction:
    """CLI mode - uses blocking prompts.

    This implementation delegates directly to the IO interface's
    prompt() and confirm() methods, which block the main thread
    waiting for user input.

    Thread Safety: Only safe when called from main thread (CLI mode).
    """

    def __init__(self, io: "CLIIOProtocol") -> None:
        """Initialize with IO interface.

        Args:
            io: CLI IO protocol implementation (e.g., RichIO, TestIO)
        """
        self._io = io

    def confirm(self, question: str, default: bool = False) -> bool:
        """Get yes/no confirmation via blocking prompt.

        Args:
            question: Question to ask user
            default: Default value if user provides no input

        Returns:
            True for yes/confirm, False for no/cancel
        """
        return self._io.confirm(question, default=default)

    def prompt(self, message: str, default: str = "") -> str:
        """Get text input via blocking prompt.

        Args:
            message: Prompt message to display
            default: Default value if user provides no input

        Returns:
            User's text input or default value
        """
        return self._io.prompt(message, default=default)


class TUIUserInteraction:
    """TUI mode - uses modal dialogs via ThreadSafeAsyncBridge.

    This implementation uses the ThreadSafeAsyncBridge to request
    modal dialogs from the main thread while blocking the worker thread.

    The bridge handles the thread synchronization:
    1. Worker calls blocking_prompt() or blocking_confirm()
    2. Bridge posts message to main thread
    3. Worker blocks on threading.Event
    4. Main thread shows modal, gets result
    5. Bridge unblocks worker with result

    Thread Safety: Designed to be called from worker threads only.
    Will raise RuntimeError if called from main thread (deadlock guard).
    """

    def __init__(self, bridge: "ThreadSafeAsyncBridge") -> None:
        """Initialize with ThreadSafeAsyncBridge.

        Args:
            bridge: ThreadSafeAsyncBridge instance from ScrappyApp
        """
        self._bridge = bridge

    def confirm(self, question: str, default: bool = False) -> bool:
        """Get yes/no confirmation via modal dialog.

        Args:
            question: Question to ask user
            default: Default value (currently unused - modal requires explicit choice)

        Returns:
            True if user confirmed, False otherwise

        Raises:
            RuntimeError: If called from main thread (would cause deadlock)
        """
        return self._bridge.blocking_confirm(question)

    def prompt(self, message: str, default: str = "") -> str:
        """Get text input via modal dialog.

        Args:
            message: Prompt message to display
            default: Default value shown in input field

        Returns:
            User's text input or default value

        Raises:
            RuntimeError: If called from main thread (would cause deadlock)
        """
        return self._bridge.blocking_prompt(message, default=default)


class AutoApproveInteraction:
    """Fallback - auto-approves with sensible defaults.

    Used when modal dialogs are not available in TUI mode (e.g., bridge not wired).
    Logs decisions for audit trail so user can see what was auto-decided.

    Sensible defaults:
    - confirm(..., default=True) -> True (safety first for checkpoints)
    - confirm(..., default=False) -> False (don't do optional things)
    - prompt(..., default="foo") -> "foo" (use provided default)

    Thread Safety: Thread-safe (no blocking operations).
    """

    def __init__(self, io: "CLIIOProtocol") -> None:
        """Initialize with IO interface for logging.

        Args:
            io: CLI IO protocol implementation for output
        """
        self._io = io

    def confirm(self, question: str, default: bool = False) -> bool:
        """Auto-approve with default and log decision.

        Args:
            question: Question that would have been asked
            default: Default value to use

        Returns:
            The default value
        """
        result_str = "Yes" if default else "No"
        self._io.echo(f"[Auto-approved: {question}] -> {result_str}")
        return default

    def prompt(self, message: str, default: str = "") -> str:
        """Auto-input with default and log decision.

        Args:
            message: Prompt that would have been shown
            default: Default value to use

        Returns:
            The default value
        """
        display_default = default if default else "(empty)"
        self._io.echo(f"[Auto-input: {message}] -> '{display_default}'")
        return default


def get_user_interaction(
    io: "CLIIOProtocol",
    bridge: Optional["ThreadSafeAsyncBridge"] = None,
) -> "CLIUserInteraction | TUIUserInteraction | AutoApproveInteraction":
    """Get appropriate user interaction handler for current mode.

    Factory function that returns the right interaction strategy based on
    the execution context:

    - CLI mode (no TUI): CLIUserInteraction with blocking prompts
    - TUI mode with bridge: TUIUserInteraction with modal dialogs
    - TUI mode without bridge: AutoApproveInteraction fallback

    Args:
        io: IO interface (used for mode detection and CLI interaction)
        bridge: Optional ThreadSafeAsyncBridge for TUI mode

    Returns:
        UserInteractionProtocol implementation appropriate for context
    """
    from .mode_utils import is_tui_mode

    if not is_tui_mode(io):
        return CLIUserInteraction(io)

    if bridge is not None:
        return TUIUserInteraction(bridge)

    # Fallback: TUI mode without bridge -> auto-approve with logging
    return AutoApproveInteraction(io)
