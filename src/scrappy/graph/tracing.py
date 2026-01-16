"""
Langfuse observability integration for LangGraph agent.

This module provides tracing capabilities using Langfuse (self-hosted, free).
It gracefully falls back to no-op tracing when Langfuse is not available,
allowing development without Docker/Langfuse running.

Usage:
    from scrappy.graph.tracing import get_tracer, trace_node

    tracer = get_tracer()

    @trace_node("think")
    def think_node(state: AgentState) -> AgentState:
        ...
"""

import functools
import os
import threading
from contextlib import contextmanager
from typing import Any, Callable, Generator, Optional, Protocol, TypeVar, runtime_checkable, TYPE_CHECKING

from typing_extensions import ParamSpec

from scrappy.infrastructure.logging import get_logger

# Lazy import to avoid loading langfuse at module import time
# This prevents langfuse from corrupting terminal state in TUI apps
if TYPE_CHECKING:
    from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

logger = get_logger(__name__)

# Thread-safe lock for global tracer access
_tracer_lock = threading.Lock()

# Type variables for decorated functions with proper signature preservation
P = ParamSpec("P")
R = TypeVar("R")


@runtime_checkable
class TracerProtocol(Protocol):
    """
    Protocol for tracer implementations.

    Defines the minimal interface for tracing, enabling dependency injection
    and testability. Both LangfuseTracer and NoOpTracer implement this protocol.

    This protocol enables:
    - Type hints that accept any conforming implementation
    - Easy substitution of test mocks for unit testing
    - Loose coupling between components and tracing
    """

    def trace(self, name: str, **kwargs: Any) -> Any:
        """Create a new trace."""
        ...

    def span(self, name: str, **kwargs: Any) -> Any:
        """Create a span within current trace."""
        ...

    def generation(self, name: str, **kwargs: Any) -> Any:
        """Create a generation span for LLM calls."""
        ...

    def flush(self) -> None:
        """Flush pending traces."""
        ...

    def shutdown(self, timeout: float = 2.0) -> None:
        """Flush pending traces and shutdown background threads.

        Args:
            timeout: Maximum seconds to wait for shutdown
        """
        ...


class NoOpSpan:
    """No-op span for when Langfuse is not available."""

    def __init__(self, name: str = "") -> None:
        self.name = name

    def __enter__(self) -> "NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op attribute setter."""
        pass

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        """No-op event adder."""
        pass

    def end(self) -> None:
        """No-op end."""
        pass


class NoOpTracer:
    """No-op tracer for when Langfuse is not available."""

    def trace(self, name: str, **kwargs: Any) -> NoOpSpan:
        """Return a no-op span."""
        return NoOpSpan(name)

    def span(self, name: str, **kwargs: Any) -> NoOpSpan:
        """Return a no-op span."""
        return NoOpSpan(name)

    def generation(self, name: str, **kwargs: Any) -> NoOpSpan:
        """Return a no-op span for LLM generations."""
        return NoOpSpan(name)

    def flush(self) -> None:
        """No-op flush."""
        pass

    def shutdown(self, timeout: float = 2.0) -> None:
        """No-op shutdown."""
        pass


class LangfuseTracer:
    """Wrapper around Langfuse client for tracing."""

    def __init__(self) -> None:
        """Initialize Langfuse client from environment variables."""
        # Security: Log key presence, not key values
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        host = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

        logger.debug(
            "Langfuse config: public_key=%s, secret_key=%s, host=%s",
            "present" if public_key else "missing",
            "present" if secret_key else "missing",
            host,
        )

        # Type annotations for mypy (Langfuse imported conditionally)
        self._client: Optional[Any] = None
        self._available: bool = False

        try:
            # Check if Langfuse server is reachable before enabling
            import socket
            from urllib.parse import urlparse
            parsed = urlparse(host)
            hostname = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 3000)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect((hostname, port))
            sock.close()

            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            self._available = True
            logger.info("Langfuse tracing initialized successfully")
        except (ImportError, ConnectionError, OSError, socket.error, socket.timeout) as e:
            # Catch specific exceptions: import failures, connection issues, network errors
            # Avoid catching KeyboardInterrupt, SystemExit, etc.
            logger.debug(f"Langfuse unavailable: {e}")
            self._client = None
            self._available = False

    @property
    def available(self) -> bool:
        """Check if Langfuse is available."""
        return self._available

    def trace(self, name: str, **kwargs: Any) -> Any:
        """Create a new trace."""
        if not self._available or self._client is None:
            return NoOpSpan(name)
        return self._client.trace(name=name, **kwargs)

    def span(self, name: str, **kwargs: Any) -> Any:
        """
        Create a span within current trace.

        NOTE: This is intentionally a stub returning NoOpSpan.
        Langfuse spans require a parent trace context to be meaningful.
        Full implementation deferred to Phase 1 when trace context propagation
        is added. For now, use trace() for top-level tracing.
        """
        # Always return NoOpSpan - full span support requires trace context propagation
        return NoOpSpan(name)

    def generation(self, name: str, **kwargs: Any) -> Any:
        """
        Create a generation span for LLM calls.

        NOTE: This is intentionally a stub returning NoOpSpan.
        Langfuse generation tracking requires integration with the LLM provider
        layer to capture model, tokens, and latency. Full implementation deferred
        to Phase 1 when provider integration is added.
        """
        # Always return NoOpSpan - full generation support requires provider integration
        return NoOpSpan(name)

    def flush(self) -> None:
        """Flush pending traces to Langfuse."""
        if self._available and self._client is not None:
            try:
                self._client.flush()
            except Exception as e:
                logger.warning(f"Failed to flush Langfuse traces: {e}")

    def shutdown(self, timeout: float = 2.0) -> None:
        """
        Flush pending traces and shutdown Langfuse background threads.

        This is the proper shutdown method per Langfuse docs:
        - Flushes all buffered data
        - Waits for background threads to terminate (blocking)

        Uses a timeout to prevent hanging if Langfuse has issues.

        Args:
            timeout: Maximum seconds to wait for shutdown (default: 2.0)
        """
        if not self._available or self._client is None:
            return

        import threading

        shutdown_complete = threading.Event()
        shutdown_error = [None]  # Use list to allow mutation in nested function

        def do_shutdown():
            try:
                self._client.shutdown()
            except Exception as e:
                shutdown_error[0] = e
            finally:
                shutdown_complete.set()

        thread = threading.Thread(target=do_shutdown, name="LangfuseShutdown")
        thread.start()

        if shutdown_complete.wait(timeout=timeout):
            if shutdown_error[0]:
                logger.warning(f"Failed to shutdown Langfuse: {shutdown_error[0]}")
            else:
                logger.debug("Langfuse shutdown complete")
        else:
            logger.warning(f"Langfuse shutdown timed out after {timeout}s - continuing")

        # Always mark as unavailable to prevent further use
        self._available = False
        self._client = None

    def get_callback_handler(self) -> Optional["LangfuseCallbackHandler"]:
        """Get CallbackHandler for LangGraph integration.

        Shares the same Langfuse client as the tracer so that shutdown_tracing()
        properly cleans up all langfuse resources.
        """
        if not self._available or self._client is None:
            return None
        # Lazy import to avoid loading at module import time
        from langfuse.callback import CallbackHandler
        # Pass our existing client to avoid creating a separate one
        return CallbackHandler(langfuse_client=self._client)


# Global tracer instance (lazy singleton)
# Use set_tracer() for testing, get_tracer() for production
_tracer: Optional[TracerProtocol] = None


def set_tracer(tracer: Optional[TracerProtocol]) -> None:
    """
    Set the global tracer instance for testing.

    This function enables dependency injection for tests. In production code,
    use get_tracer() which handles lazy initialization automatically.

    Thread-safe: Uses lock to prevent race conditions.

    Args:
        tracer: Tracer instance to use, or None to reset to default behavior

    Example:
        # In tests:
        from scrappy.graph.tracing import set_tracer, NoOpTracer

        def test_something():
            set_tracer(NoOpTracer())
            try:
                # test code
            finally:
                set_tracer(None)  # Reset for other tests
    """
    global _tracer
    with _tracer_lock:
        _tracer = tracer


def get_tracer() -> TracerProtocol:
    """
    Get or create the global tracer instance.

    Returns Langfuse tracer if configured, otherwise returns no-op tracer.
    This allows code to use tracing unconditionally without checking availability.

    Thread-safe: Uses double-checked locking pattern for efficiency.
    For production use. In tests, prefer set_tracer() for explicit control.

    Returns:
        Tracer instance conforming to TracerProtocol
    """
    global _tracer

    # Fast path: tracer already initialized (no lock needed)
    if _tracer is not None:
        return _tracer

    # Slow path: acquire lock and check again (double-checked locking)
    with _tracer_lock:
        # Check again inside lock in case another thread initialized it
        if _tracer is not None:
            return _tracer

        # Check if Langfuse is configured
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            langfuse_tracer = LangfuseTracer()
            if langfuse_tracer.available:
                _tracer = langfuse_tracer
            else:
                _tracer = NoOpTracer()
        else:
            logger.debug("Langfuse not configured (missing API keys). Tracing disabled.")
            _tracer = NoOpTracer()

        return _tracer


def is_tracing_enabled() -> bool:
    """
    Check if tracing is enabled and available.

    Returns:
        True if Langfuse is configured and connected
    """
    tracer = get_tracer()
    return isinstance(tracer, LangfuseTracer) and tracer.available


@contextmanager
def trace_context(name: str, **kwargs: Any) -> Generator[Any, None, None]:
    """
    Context manager for tracing a block of code.

    Args:
        name: Name of the trace/span
        **kwargs: Additional attributes for the span

    Yields:
        Span object (or NoOpSpan if tracing disabled)
    """
    tracer = get_tracer()
    span = tracer.trace(name, **kwargs)
    try:
        yield span
    finally:
        if hasattr(span, "end"):
            span.end()


def trace_node(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to trace a graph node function.

    Args:
        name: Name of the node (e.g., "think", "execute", "verify")

    Returns:
        Decorated function with tracing

    Usage:
        @trace_node("think")
        def think_node(state: AgentState) -> AgentState:
            ...
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with trace_context(f"node:{name}"):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def shutdown_tracing(timeout: float = 2.0) -> None:
    """
    Properly shutdown tracing, flushing data and terminating background threads.

    Per Langfuse docs, shutdown() (not just flush()) must be called to:
    - Flush all buffered trace data
    - Wait for background threads to terminate
    - Prevent hanging on app exit

    This shuts down both:
    1. Our LangfuseTracer client (used by LangGraph callbacks)
    2. The global langfuse client used by litellm's integration

    Thread-safe: Uses lock to prevent race conditions.
    All shutdown operations have timeouts to prevent hanging.

    Args:
        timeout: Maximum seconds to wait for each shutdown operation
    """
    global _tracer
    with _tracer_lock:
        if _tracer is not None:
            _tracer.shutdown(timeout=timeout)
            _tracer = None

    # Also shutdown litellm's langfuse client (separate from our tracer)
    # litellm uses langfuse.get_client() internally when "langfuse" callback is enabled
    # Only attempt if langfuse is installed (optional dev dependency)
    try:
        from langfuse import get_client
        client = get_client()
        if client is not None:
            _shutdown_langfuse_client(client, timeout=timeout)
    except ImportError:
        pass  # langfuse not installed, nothing to shutdown


def _shutdown_langfuse_client(client, timeout: float = 2.0) -> None:
    """Shutdown a langfuse client with timeout.

    Args:
        client: Langfuse client instance
        timeout: Maximum seconds to wait for shutdown
    """
    import threading

    shutdown_complete = threading.Event()

    def do_shutdown():
        try:
            client.shutdown()
        except Exception as e:
            logger.debug(f"Error during langfuse client shutdown: {e}")
        finally:
            shutdown_complete.set()

    thread = threading.Thread(target=do_shutdown, name="LangfuseClientShutdown")
    thread.start()

    if shutdown_complete.wait(timeout=timeout):
        logger.debug("Litellm's langfuse client shutdown complete")
    else:
        logger.warning(f"Litellm's langfuse client shutdown timed out after {timeout}s")


def get_langfuse_callback() -> Optional["LangfuseCallbackHandler"]:
    """
    Get Langfuse CallbackHandler for LangGraph integration.

    Returns handler if Langfuse is configured, None otherwise.

    Usage:
        handler = get_langfuse_callback()
        if handler:
            graph = compiled.with_config({"callbacks": [handler]})
    """
    tracer = get_tracer()
    if isinstance(tracer, LangfuseTracer):
        return tracer.get_callback_handler()
    return None
