"""
Session context module for CLI.

Centralizes shared session state to eliminate fragile synchronization
between CLI, CommandRouter, and InteractiveMode components.
"""

from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from scrappy.cli.conversation_store import ConversationStoreProtocol


class SessionContextProtocol(Protocol):
    """
    Protocol defining the contract for session context.

    SessionContext holds mutable session state that needs to be shared
    across multiple CLI components (CommandRouter, InteractiveMode, etc).

    By centralizing this state in a single object passed to all components,
    we eliminate the need for state synchronization and proxy properties.
    """

    @property
    def conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history."""
        ...

    @conversation_history.setter
    def conversation_history(self, value: List[Dict[str, str]]) -> None:
        """Set conversation history."""
        ...


    @property
    def smart_mode(self) -> bool:
        """Get smart query mode."""
        ...

    @smart_mode.setter
    def smart_mode(self, value: bool) -> None:
        """Set smart query mode."""
        ...

    @property
    def auto_save(self) -> bool:
        """Get auto-save setting."""
        ...

    @auto_save.setter
    def auto_save(self, value: bool) -> None:
        """Set auto-save setting."""
        ...

    @property
    def verbose_mode(self) -> bool:
        """Get verbose output mode."""
        ...

    @verbose_mode.setter
    def verbose_mode(self, value: bool) -> None:
        """Set verbose output mode."""
        ...

    @property
    def is_stale(self) -> bool:
        """Check if session is stale (> 4 hours since last message)."""
        ...

    def add_message(self, message: Dict[str, Any]) -> None:
        """Persist message to conversation store.

        Args:
            message: Full message dict with 'role', 'content', and optionally
                    'tool_calls' or 'tool_call_id'
        """
        ...


class SessionContext:
    """
    Concrete implementation of SessionContextProtocol.

    Holds mutable session state that is shared across CLI components.
    Components receive a reference to this context and modify it directly,
    eliminating the need for state copying and synchronization.
    """

    def __init__(
        self,
        conversation_history: List[Dict[str, str]] | None = None,
        smart_mode: bool = False,
        auto_save: bool = True,
        verbose_mode: bool = False,
        conversation_store: Optional["ConversationStoreProtocol"] = None
    ) -> None:
        """
        Initialize SessionContext with default settings.

        Args:
            conversation_history: Chat history. Defaults to empty list.
            smart_mode: Enable smart query mode. Defaults to False.
            auto_save: Enable auto-save on exit. Defaults to True.
            verbose_mode: Show detailed metadata (provider, tokens, time). Defaults to False.
            conversation_store: Optional conversation persistence store.
        """
        self._conversation_history = conversation_history or []
        self._smart_mode = smart_mode
        self._auto_save = auto_save
        self._verbose_mode = verbose_mode
        self._conversation_store = conversation_store

    @property
    def conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history."""
        return self._conversation_history

    @conversation_history.setter
    def conversation_history(self, value: List[Dict[str, str]]) -> None:
        """Set conversation history."""
        self._conversation_history = value

    @property
    def smart_mode(self) -> bool:
        """Get smart query mode."""
        return self._smart_mode

    @smart_mode.setter
    def smart_mode(self, value: bool) -> None:
        """Set smart query mode."""
        self._smart_mode = value

    @property
    def auto_save(self) -> bool:
        """Get auto-save setting."""
        return self._auto_save

    @auto_save.setter
    def auto_save(self, value: bool) -> None:
        """Set auto-save setting."""
        self._auto_save = value

    @property
    def verbose_mode(self) -> bool:
        """Get verbose output mode."""
        return self._verbose_mode

    @verbose_mode.setter
    def verbose_mode(self, value: bool) -> None:
        """Set verbose output mode."""
        self._verbose_mode = value

    @property
    def is_stale(self) -> bool:
        """
        Check if session is stale (> 4 hours since last message).

        Returns:
            True if session is stale or no store available
        """
        if self._conversation_store is None:
            return False

        from scrappy.cli.conversation_store import check_session_staleness

        last_time = self._conversation_store.get_last_message_time()
        return check_session_staleness(last_time)

    def add_message(self, message: Dict[str, Any]) -> None:
        """
        Persist message to conversation store.

        Accepts full message dict to support Phase 1.5 tool call fidelity.

        Args:
            message: Full message dict with 'role', 'content', and optionally
                    'tool_calls' (for assistant) or 'tool_call_id' (for tool role)
        """
        if self._conversation_store is not None:
            self._conversation_store.add_message(message)
