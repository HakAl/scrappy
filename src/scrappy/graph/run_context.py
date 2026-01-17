"""
AgentRunContext - ephemeral context for a single agent run.

This module provides the missing middle layer between CLI Session (persistent)
and Per-Task context (per-iteration). AgentRunContext tracks:
- Model affinity (stick with provider unless handoff triggered)
- File cache (avoid re-reading files within same run)
- Status updates (provider display in status bar)
- Cancellation callbacks (cleanup on cancel/complete)

Lifecycle:
- Created at start of run_agent()
- Passed to nodes via config["configurable"]["run_context"]
- Destroyed when run completes or is cancelled
- NOT persisted with checkpoints (ephemeral)

Related beads: scrappy-vpa2, scrappy-b6gg, scrappy-iq9k
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from scrappy.infrastructure.logging import get_logger
from scrappy.infrastructure.threading.protocols import CancellationTokenProtocol

if TYPE_CHECKING:
    from scrappy.context.protocols import SemanticSearchProtocol

logger = get_logger(__name__)


# Handoff triggers - when to try a different provider
# True = immediate handoff, int = after N consecutive errors, False = never
HANDOFF_TRIGGERS: Dict[str, bool | int] = {
    # Always handoff immediately
    "rate_limit": True,
    "auth_error": True,
    "quota_exceeded": True,
    "model_not_found": True,
    "context_length_exceeded": True,

    # Handoff after N consecutive errors
    "server_error": 3,
    "timeout": 2,

    # Never handoff (retry same provider)
    "network": False,
    "parse": False,
}


@runtime_checkable
class AgentRunContextProtocol(Protocol):
    """Protocol for agent run context.

    Defines the interface for tracking run-level state that persists
    across iterations but not across runs.
    """

    # === Model Affinity ===

    @property
    def preferred_provider(self) -> Optional[str]:
        """Provider that succeeded first - stick with it unless handoff triggered."""
        ...

    @property
    def preferred_model(self) -> Optional[str]:
        """Model that succeeded first - stick with it unless handoff triggered."""
        ...

    @property
    def model_selection(self) -> Optional[Any]:
        """Model selection service for deterministic priority-based selection."""
        ...

    def record_provider_success(self, provider: str, model: str) -> None:
        """Record successful response - sets affinity if first success."""
        ...

    def record_provider_error(self, provider: str, error_category: str) -> None:
        """Record provider error - may trigger handoff based on category."""
        ...

    def should_handoff(self) -> bool:
        """Check if we should try a different provider."""
        ...

    def get_handoff_reason(self) -> Optional[str]:
        """Get reason for handoff (for logging/display)."""
        ...

    def clear_handoff(self) -> None:
        """Clear handoff state after successful switch."""
        ...

    # === File Caching ===

    def get_cached_file(self, path: str) -> Optional[str]:
        """Get file content if already read this run. Returns None if not cached."""
        ...

    def cache_file(self, path: str, content: str) -> None:
        """Cache file content for this run. Limited to MAX_CACHE_SIZE."""
        ...

    def invalidate_file(self, path: str) -> None:
        """Remove file from cache (call after write/edit)."""
        ...

    # === Status Updates ===

    def update_status(self, message: str) -> None:
        """Update status bar with current state."""
        ...

    def set_status_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for status updates."""
        ...

    # === Cancellation ===

    @property
    def cancellation_token(self) -> Optional[CancellationTokenProtocol]:
        """Get cancellation token for this run."""
        ...

    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        ...

    def is_force_cancelled(self) -> bool:
        """Check if force cancellation requested (2nd+ escape)."""
        ...

    # === Lifecycle ===

    def register_cancel_callback(self, callback: Callable[[], None]) -> None:
        """Register component to be notified on cancel/complete."""
        ...

    def on_cancel(self) -> None:
        """Called when run is cancelled - cleanup and notify dependents."""
        ...

    def on_complete(self, success: bool) -> None:
        """Called when run completes - cleanup."""
        ...


@dataclass
class AgentRunContext:
    """
    Ephemeral context for a single agent run.

    Created at start of run_agent(), destroyed when run ends.
    NOT persisted with checkpoints.
    """

    # === Model Affinity ===
    preferred_provider: Optional[str] = None
    preferred_model: Optional[str] = None
    _provider_errors: Dict[str, List[str]] = field(default_factory=dict)
    _handoff_triggered: bool = False
    _handoff_reason: Optional[str] = None

    # === File Caching ===
    _file_cache: Dict[str, str] = field(default_factory=dict)
    _cache_size_bytes: int = 0
    MAX_CACHE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5MB limit

    # === Status Updates ===
    _status_callback: Optional[Callable[[str], None]] = None

    # === Cancellation ===
    _cancellation_token: Optional[CancellationTokenProtocol] = None

    # === Lifecycle ===
    _cancel_callbacks: List[Callable[[], None]] = field(default_factory=list)

    # === Model Selection Service ===
    # Injected by langgraph_bridge for deterministic model selection
    model_selection: Optional[Any] = None  # Type: ModelSelectionServiceProtocol

    # === Semantic Search ===
    # Injected by langgraph_bridge from codebase context
    semantic_search: Optional["SemanticSearchProtocol"] = None

    # === Model Affinity Methods ===

    def record_provider_success(self, provider: str, model: str) -> None:
        """Record successful response - sets affinity if first success."""
        if self.preferred_provider is None:
            self.preferred_provider = provider
            self.preferred_model = model
            logger.debug(f"Set provider affinity: {provider}/{model}")

    def record_provider_error(self, provider: str, error_category: str) -> None:
        """Record provider error - may trigger handoff based on category."""
        if provider not in self._provider_errors:
            self._provider_errors[provider] = []
        self._provider_errors[provider].append(error_category)

        # Check if handoff should trigger
        trigger = HANDOFF_TRIGGERS.get(error_category)
        if trigger is True:
            self._handoff_triggered = True
            self._handoff_reason = f"{error_category} from {provider}"
            logger.info(f"Handoff triggered: {self._handoff_reason}")
        elif trigger is False:
            # Never trigger handoff for this error type (retry same provider)
            pass
        elif isinstance(trigger, int) and trigger > 0:
            # Count consecutive errors of this category
            recent = self._provider_errors[provider][-trigger:]
            if len(recent) >= trigger and all(e == error_category for e in recent):
                self._handoff_triggered = True
                self._handoff_reason = f"{trigger}x {error_category} from {provider}"
                logger.info(f"Handoff triggered: {self._handoff_reason}")

    def should_handoff(self) -> bool:
        """Check if we should try a different provider."""
        return self._handoff_triggered

    def get_handoff_reason(self) -> Optional[str]:
        """Get reason for handoff (for logging/display)."""
        return self._handoff_reason

    def clear_handoff(self) -> None:
        """Clear handoff state after successful switch."""
        self._handoff_triggered = False
        self._handoff_reason = None
        # Clear affinity to allow fallback selection
        self.preferred_provider = None
        self.preferred_model = None

    # === File Caching Methods ===

    def get_cached_file(self, path: str) -> Optional[str]:
        """Get file content if already read this run."""
        return self._file_cache.get(path)

    def cache_file(self, path: str, content: str) -> None:
        """Cache file content for this run."""
        content_size = len(content.encode('utf-8'))

        # Evict oldest entries if over limit
        while self._cache_size_bytes + content_size > self.MAX_CACHE_SIZE_BYTES:
            if not self._file_cache:
                # Single file too large to cache
                logger.debug(f"File too large to cache: {path} ({content_size} bytes)")
                return
            # Evict oldest (first inserted due to dict ordering in Python 3.7+)
            oldest_path = next(iter(self._file_cache))
            self._evict(oldest_path)

        self._file_cache[path] = content
        self._cache_size_bytes += content_size
        logger.debug(f"Cached file: {path} ({content_size} bytes)")

    def invalidate_file(self, path: str) -> None:
        """Remove file from cache (call after write/edit)."""
        if path in self._file_cache:
            content = self._file_cache[path]
            self._cache_size_bytes -= len(content.encode('utf-8'))
            del self._file_cache[path]
            logger.debug(f"Invalidated cache: {path}")

    def _evict(self, path: str) -> None:
        """Evict a file from cache."""
        if path in self._file_cache:
            content = self._file_cache[path]
            self._cache_size_bytes -= len(content.encode('utf-8'))
            del self._file_cache[path]
            logger.debug(f"Evicted from cache: {path}")

    # === Status Update Methods ===

    def set_status_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for status updates."""
        self._status_callback = callback

    def update_status(self, message: str) -> None:
        """Update status bar with current state."""
        if self._status_callback:
            try:
                self._status_callback(message)
            except Exception as e:
                logger.warning(f"Status callback failed: {e}")

    # === Cancellation Methods ===

    @property
    def cancellation_token(self) -> Optional[CancellationTokenProtocol]:
        """Get cancellation token for this run."""
        return self._cancellation_token

    @cancellation_token.setter
    def cancellation_token(self, token: Optional[CancellationTokenProtocol]) -> None:
        """Set cancellation token for this run."""
        self._cancellation_token = token

    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested.

        Returns:
            True if cancel() has been called on the token
        """
        return (
            self._cancellation_token is not None
            and self._cancellation_token.is_cancelled
        )

    def is_force_cancelled(self) -> bool:
        """Check if force cancellation requested (2nd+ escape).

        Returns:
            True if cancel() has been called multiple times on the token
        """
        return (
            self._cancellation_token is not None
            and self._cancellation_token.is_force_cancelled
        )

    # === Lifecycle Methods ===

    def register_cancel_callback(self, callback: Callable[[], None]) -> None:
        """Register component to be notified on cancel/complete."""
        self._cancel_callbacks.append(callback)

    def on_cancel(self) -> None:
        """Called when run is cancelled - cleanup and notify dependents."""
        for callback in self._cancel_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"Cancel callback failed: {e}")
        self._cancel_callbacks.clear()
        self._file_cache.clear()
        self._cache_size_bytes = 0

    def on_complete(self, success: bool) -> None:
        """Called when run completes - cleanup."""
        # Same cleanup as cancel
        self.on_cancel()
