"""HTTP client patching for rate limit header capture.

Patches httpx.Client and httpx.AsyncClient to intercept response headers
containing rate limit information. This allows capturing actual remaining
quotas reported by providers.

Thread-safe and supports both sync and async HTTP operations.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional, Protocol
from urllib.parse import urlparse
import httpx


class RateLimitHeaderHandler(Protocol):
    """Protocol for handling captured rate limit headers."""

    def update_from_headers(self, provider: str, headers: Dict[str, str]) -> None:
        """Update rate limits from HTTP response headers."""
        ...


# Thread-local storage for captured headers (for debugging/testing)
_captured_headers: threading.local = threading.local()

# Global handler reference
_handler: Optional[RateLimitHeaderHandler] = None
_installed: bool = False
_lock = threading.Lock()


def _extract_provider_from_url(url: str | httpx.URL) -> Optional[str]:
    """Extract provider name from request URL.

    Args:
        url: The request URL

    Returns:
        Provider name or None if not recognized
    """
    parsed = urlparse(str(url))
    host = parsed.netloc.lower()

    # Map hosts to provider names
    provider_map = {
        "api.groq.com": "groq",
        "api.cerebras.ai": "cerebras",
        "api.sambanova.ai": "sambanova",
        "generativelanguage.googleapis.com": "gemini",
    }

    for domain, provider in provider_map.items():
        if domain in host:
            return provider

    return None


def _extract_rate_limit_headers(headers: httpx.Headers) -> Dict[str, str]:
    """Extract rate limit headers from response.

    Args:
        headers: HTTP response headers

    Returns:
        Dict of rate limit headers (lowercase keys)
    """
    return {
        k.lower(): v
        for k, v in headers.items()
        if "ratelimit" in k.lower()
    }


def _capture_sync_response(response: httpx.Response) -> None:
    """Sync hook to capture rate limit headers from response.

    Args:
        response: The HTTP response
    """
    global _handler

    if _handler is None:
        return

    provider = _extract_provider_from_url(response.request.url)
    if provider is None:
        return

    headers = _extract_rate_limit_headers(response.headers)
    if headers:
        _handler.update_from_headers(provider, headers)


async def _capture_async_response(response: httpx.Response) -> None:
    """Async hook to capture rate limit headers from response.

    Must be async function for httpx AsyncClient event hooks.

    Args:
        response: The HTTP response
    """
    global _handler

    if _handler is None:
        return

    provider = _extract_provider_from_url(response.request.url)
    if provider is None:
        return

    headers = _extract_rate_limit_headers(response.headers)
    if headers:
        _handler.update_from_headers(provider, headers)


# Store original __init__ methods
_original_client_init: Optional[Callable[..., None]] = None
_original_async_client_init: Optional[Callable[..., None]] = None


def _patched_client_init(self: httpx.Client, *args: Any, **kwargs: Any) -> None:
    """Patched httpx.Client.__init__ that injects response hooks."""
    existing_hooks = kwargs.get("event_hooks") or {}
    response_hooks = list(existing_hooks.get("response") or [])
    response_hooks.append(_capture_sync_response)
    existing_hooks["response"] = response_hooks
    kwargs["event_hooks"] = existing_hooks

    if _original_client_init is not None:
        _original_client_init(self, *args, **kwargs)


def _patched_async_client_init(
    self: httpx.AsyncClient, *args: Any, **kwargs: Any
) -> None:
    """Patched httpx.AsyncClient.__init__ that injects async response hooks."""
    existing_hooks = kwargs.get("event_hooks") or {}
    response_hooks = list(existing_hooks.get("response") or [])
    response_hooks.append(_capture_async_response)
    existing_hooks["response"] = response_hooks
    kwargs["event_hooks"] = existing_hooks

    if _original_async_client_init is not None:
        _original_async_client_init(self, *args, **kwargs)


def install_rate_limit_hooks(handler: RateLimitHeaderHandler) -> None:
    """Install httpx patches to capture rate limit headers.

    Call once at application startup. Thread-safe.

    Args:
        handler: Object implementing update_from_headers() to receive headers
    """
    global _handler, _installed, _original_client_init, _original_async_client_init

    with _lock:
        if _installed:
            # Already installed, just update handler
            _handler = handler
            return

        _handler = handler

        # Store originals before patching
        _original_client_init = httpx.Client.__init__
        _original_async_client_init = httpx.AsyncClient.__init__

        # Apply patches
        httpx.Client.__init__ = _patched_client_init  # type: ignore[method-assign]
        httpx.AsyncClient.__init__ = _patched_async_client_init  # type: ignore[method-assign]

        _installed = True


def uninstall_rate_limit_hooks() -> None:
    """Remove httpx patches. Primarily for testing."""
    global _handler, _installed, _original_client_init, _original_async_client_init

    with _lock:
        if not _installed:
            return

        # Restore originals
        if _original_client_init is not None:
            httpx.Client.__init__ = _original_client_init  # type: ignore[method-assign]
        if _original_async_client_init is not None:
            httpx.AsyncClient.__init__ = _original_async_client_init  # type: ignore[method-assign]

        _handler = None
        _installed = False
        _original_client_init = None
        _original_async_client_init = None


def is_installed() -> bool:
    """Check if hooks are currently installed."""
    return _installed
