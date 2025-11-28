"""
Session context module for CLI.

Centralizes shared session state to eliminate fragile synchronization
between CLI, CommandRouter, and InteractiveMode components.
"""

from typing import Dict, List, Protocol


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
        verbose_mode: bool = False
    ) -> None:
        """
        Initialize SessionContext with default settings.

        Args:
            conversation_history: Chat history. Defaults to empty list.
            smart_mode: Enable smart query mode. Defaults to False.
            auto_save: Enable auto-save on exit. Defaults to True.
            verbose_mode: Show detailed metadata (provider, tokens, time). Defaults to False.
        """
        self._conversation_history = conversation_history or []
        self._smart_mode = smart_mode
        self._auto_save = auto_save
        self._verbose_mode = verbose_mode

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
