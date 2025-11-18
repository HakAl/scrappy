"""
Session management functionality for the CLI.
Handles context, cache, rate limits, and session persistence.
"""

from typing import Any, Dict, List, Optional

try:
    from .io_interface import CLIIOProtocol, ClickIO
    from .context_manager import ContextManager
    from .cache_manager import CacheManager
    from .rate_limiter import RateLimiter
    from .persistence import SessionPersistence
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cli.io_interface import CLIIOProtocol, ClickIO  # type: ignore[no-redef]
    from cli.context_manager import ContextManager  # type: ignore[no-redef]
    from cli.cache_manager import CacheManager  # type: ignore[no-redef]
    from cli.rate_limiter import RateLimiter  # type: ignore[no-redef]
    from cli.persistence import SessionPersistence  # type: ignore[no-redef]


class CLISessionManager:
    """Manages session state, caching, and persistence."""

    def __init__(self, orchestrator: Any) -> None:
        """Initialize session manager.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator
        self._context_manager = ContextManager(orchestrator)
        self._cache_manager = CacheManager(orchestrator)
        self._rate_limiter = RateLimiter(orchestrator)
        self._session_persistence = SessionPersistence(orchestrator)

    def manage_context(self, args: str = "", io: Optional[CLIIOProtocol] = None) -> None:
        """Manage codebase context."""
        self._context_manager.manage_context(args, io)

    def manage_cache(self, args: str = "", io: Optional[CLIIOProtocol] = None) -> None:
        """Manage response cache."""
        self._cache_manager.manage_cache(args, io)

    def show_rate_limits(self, args: str = "", io: Optional[CLIIOProtocol] = None) -> None:
        """Show rate limit usage (persistent tracking)."""
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
