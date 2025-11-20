"""
Session management functionality for the CLI.
Handles context, cache, rate limits, and session persistence.
"""

from typing import Any, Dict, List, Optional

from .io_interface import CLIIOProtocol
from .rich_output import RichIO
from .context_manager import ContextManager
from .cache_manager import CacheManager
from .rate_limiter import RateLimiter
from .persistence import SessionPersistence


class CLISessionManager:
    """Manages session state, caching, and persistence."""

    def __init__(
        self,
        orchestrator: Any,
        context_manager: ContextManager,
        cache_manager: CacheManager,
        rate_limiter: RateLimiter,
        session_persistence: SessionPersistence
    ) -> None:
        """Initialize session manager.

        Args:
            orchestrator: The AgentOrchestrator instance
            context_manager: Context manager for codebase context
            cache_manager: Cache manager for response caching
            rate_limiter: Rate limiter for tracking usage
            session_persistence: Session persistence for saving/loading
        """
        self.orchestrator = orchestrator
        self._context_manager = context_manager
        self._cache_manager = cache_manager
        self._rate_limiter = rate_limiter
        self._session_persistence = session_persistence

    def manage_context(self, args: str = "", io: Optional[CLIIOProtocol] = None) -> None:
        """Manage codebase context through the context manager.

        Delegates to ContextManager to handle context operations like exploring,
        refreshing, clearing, and toggling context awareness.

        Args:
            args: Command arguments (explore|refresh|clear|clearmem|toggle).
                Empty string shows context status.
            io: I/O interface for output. Defaults to ClickIO if None.

        State Changes:
            - May modify orchestrator.context_aware flag (toggle)
            - May clear context cache (clear)
            - May populate context with project data (explore/refresh)

        Side Effects:
            - Writes status or confirmation to stdout via io

        Returns:
            None
        """
        self._context_manager.manage_context(args, io)

    def manage_cache(self, args: str = "", io: Optional[CLIIOProtocol] = None) -> None:
        """Manage response cache through the cache manager.

        Delegates to CacheManager to handle cache operations like showing stats,
        clearing cache, and toggling caching on/off.

        Args:
            args: Command arguments (clear|toggle). Empty string shows cache stats.
            io: I/O interface for output. Defaults to ClickIO if None.

        State Changes:
            - May toggle orchestrator caching state (toggle)
            - May clear all cached responses (clear)

        Side Effects:
            - Writes cache statistics or confirmation to stdout via io

        Returns:
            None
        """
        self._cache_manager.manage_cache(args, io)

    def show_rate_limits(self, args: str = "", io: Optional[CLIIOProtocol] = None) -> None:
        """Show rate limit usage with persistent tracking.

        Delegates to RateLimiter to display rate limit information. Tracks usage
        across sessions via persistent storage.

        Args:
            args: Optional provider name to show specific provider limits,
                or 'reset' to reset tracking. Empty string shows all providers.
            io: I/O interface for output. Defaults to ClickIO if None.

        State Changes:
            - May reset persistent rate limit tracking (reset)

        Side Effects:
            - Writes rate limit statistics to stdout via io
            - Reads/writes persistent rate limit data

        Returns:
            None
        """
        self._rate_limiter.show_rate_limits(args, io)

    def manage_session(
        self,
        args: str = "",
        conversation_history: Optional[List[Dict[str, str]]] = None,
        auto_save: bool = True,
        io: Optional[CLIIOProtocol] = None
    ) -> Dict[str, Any]:
        """Manage session persistence.

        Args:
            args: Command arguments
            conversation_history: Current conversation history
            auto_save: Current auto-save setting
            io: I/O interface for output

        Returns:
            dict with keys:
                - conversation_history: Updated conversation history (if loaded)
                - auto_save: Updated auto-save setting (if toggled)
        """
        return self._session_persistence.manage_session(args, conversation_history, auto_save, io)
