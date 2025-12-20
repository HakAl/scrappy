"""Tests for httpx rate limit header capture.

CRITICAL: NO REAL API CALLS. All tests use mocks/fakes.
"""
from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest
import httpx

from scrappy.orchestrator.rate_limiting.httpx_patcher import (
    install_rate_limit_hooks,
    uninstall_rate_limit_hooks,
    is_installed,
    _extract_provider_from_url,
    _extract_rate_limit_headers,
)


class FakeHandler:
    """Fake handler that captures calls to update_from_headers."""

    def __init__(self):
        self.calls: list[tuple[str, Dict[str, str]]] = []

    def update_from_headers(self, provider: str, headers: Dict[str, str]) -> None:
        self.calls.append((provider, headers))


@pytest.fixture(autouse=True)
def cleanup_hooks():
    """Ensure hooks are uninstalled before and after each test."""
    uninstall_rate_limit_hooks()
    yield
    uninstall_rate_limit_hooks()


class TestExtractProviderFromUrl:
    """Tests for provider extraction from URLs."""

    @pytest.mark.unit
    def test_extracts_groq(self):
        url = "https://api.groq.com/openai/v1/chat/completions"
        assert _extract_provider_from_url(url) == "groq"

    @pytest.mark.unit
    def test_extracts_cerebras(self):
        url = "https://api.cerebras.ai/v1/chat/completions"
        assert _extract_provider_from_url(url) == "cerebras"

    @pytest.mark.unit
    def test_extracts_sambanova(self):
        url = "https://api.sambanova.ai/v1/chat/completions"
        assert _extract_provider_from_url(url) == "sambanova"

    @pytest.mark.unit
    def test_extracts_gemini(self):
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini"
        assert _extract_provider_from_url(url) == "gemini"

    @pytest.mark.unit
    def test_returns_none_for_unknown(self):
        url = "https://api.unknown.com/v1/completions"
        assert _extract_provider_from_url(url) is None

    @pytest.mark.unit
    def test_handles_httpx_url_object(self):
        url = httpx.URL("https://api.groq.com/openai/v1/chat/completions")
        assert _extract_provider_from_url(str(url)) == "groq"


class TestExtractRateLimitHeaders:
    """Tests for rate limit header extraction."""

    @pytest.mark.unit
    def test_extracts_ratelimit_headers(self):
        headers = httpx.Headers({
            "content-type": "application/json",
            "x-ratelimit-remaining-requests": "100",
            "x-ratelimit-limit-requests": "1000",
            "x-request-id": "abc123",
        })
        result = _extract_rate_limit_headers(headers)

        assert "x-ratelimit-remaining-requests" in result
        assert "x-ratelimit-limit-requests" in result
        assert "content-type" not in result
        assert "x-request-id" not in result

    @pytest.mark.unit
    def test_case_insensitive(self):
        headers = httpx.Headers({
            "X-RateLimit-Remaining-Requests": "100",
        })
        result = _extract_rate_limit_headers(headers)

        # Result keys should be lowercase
        assert "x-ratelimit-remaining-requests" in result

    @pytest.mark.unit
    def test_empty_when_no_ratelimit_headers(self):
        headers = httpx.Headers({
            "content-type": "application/json",
        })
        result = _extract_rate_limit_headers(headers)
        assert result == {}


class TestInstallHooks:
    """Tests for hook installation and uninstallation."""

    @pytest.mark.unit
    def test_install_sets_installed_flag(self):
        handler = FakeHandler()
        assert not is_installed()

        install_rate_limit_hooks(handler)

        assert is_installed()

    @pytest.mark.unit
    def test_uninstall_clears_installed_flag(self):
        handler = FakeHandler()
        install_rate_limit_hooks(handler)
        assert is_installed()

        uninstall_rate_limit_hooks()

        assert not is_installed()

    @pytest.mark.unit
    def test_install_is_idempotent(self):
        handler1 = FakeHandler()
        handler2 = FakeHandler()

        install_rate_limit_hooks(handler1)
        install_rate_limit_hooks(handler2)  # Should update handler

        # Should still be installed (no error)
        assert is_installed()

    @pytest.mark.unit
    def test_uninstall_is_idempotent(self):
        # Should not raise when not installed
        uninstall_rate_limit_hooks()
        uninstall_rate_limit_hooks()

        assert not is_installed()


class TestSyncHeaderCapture:
    """Tests for sync httpx.Client header capture."""

    @pytest.mark.unit
    def test_captures_headers_on_sync_response(self):
        """Sync client should capture rate limit headers."""
        handler = FakeHandler()
        install_rate_limit_hooks(handler)

        # Create a mock response with rate limit headers
        mock_response = Mock(spec=httpx.Response)
        mock_response.request = Mock()
        mock_response.request.url = "https://api.groq.com/openai/v1/chat/completions"
        mock_response.headers = httpx.Headers({
            "x-ratelimit-remaining-requests": "14399",
            "x-ratelimit-limit-requests": "14400",
        })

        # Import the capture function and call it directly
        from scrappy.orchestrator.rate_limiting.httpx_patcher import _capture_sync_response
        _capture_sync_response(mock_response)

        # Verify handler was called
        assert len(handler.calls) == 1
        provider, headers = handler.calls[0]
        assert provider == "groq"
        assert "x-ratelimit-remaining-requests" in headers

    @pytest.mark.unit
    def test_skips_non_provider_urls(self):
        """Should not capture headers for unknown providers."""
        handler = FakeHandler()
        install_rate_limit_hooks(handler)

        mock_response = Mock(spec=httpx.Response)
        mock_response.request = Mock()
        mock_response.request.url = "https://api.unknown.com/v1/completions"
        mock_response.headers = httpx.Headers({
            "x-ratelimit-remaining-requests": "100",
        })

        from scrappy.orchestrator.rate_limiting.httpx_patcher import _capture_sync_response
        _capture_sync_response(mock_response)

        # Handler should NOT be called for unknown provider
        assert len(handler.calls) == 0

    @pytest.mark.unit
    def test_skips_responses_without_ratelimit_headers(self):
        """Should not call handler when no rate limit headers present."""
        handler = FakeHandler()
        install_rate_limit_hooks(handler)

        mock_response = Mock(spec=httpx.Response)
        mock_response.request = Mock()
        mock_response.request.url = "https://api.groq.com/openai/v1/chat/completions"
        mock_response.headers = httpx.Headers({
            "content-type": "application/json",
        })

        from scrappy.orchestrator.rate_limiting.httpx_patcher import _capture_sync_response
        _capture_sync_response(mock_response)

        # Handler should NOT be called when no rate limit headers
        assert len(handler.calls) == 0


class TestAsyncHeaderCapture:
    """Tests for async httpx.AsyncClient header capture."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_captures_headers_on_async_response(self):
        """Async client should capture rate limit headers."""
        handler = FakeHandler()
        install_rate_limit_hooks(handler)

        mock_response = Mock(spec=httpx.Response)
        mock_response.request = Mock()
        mock_response.request.url = "https://api.cerebras.ai/v1/chat/completions"
        mock_response.headers = httpx.Headers({
            "x-ratelimit-remaining-requests-day": "14375",
            "x-ratelimit-remaining-tokens-minute": "48171",
        })

        from scrappy.orchestrator.rate_limiting.httpx_patcher import _capture_async_response
        await _capture_async_response(mock_response)

        assert len(handler.calls) == 1
        provider, headers = handler.calls[0]
        assert provider == "cerebras"
        assert "x-ratelimit-remaining-requests-day" in headers

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_async_hook_is_async_function(self):
        """Async hook must be awaitable (not return None)."""
        handler = FakeHandler()
        install_rate_limit_hooks(handler)

        mock_response = Mock(spec=httpx.Response)
        mock_response.request = Mock()
        mock_response.request.url = "https://api.groq.com/v1/completions"
        mock_response.headers = httpx.Headers({
            "x-ratelimit-remaining-requests": "100",
        })

        from scrappy.orchestrator.rate_limiting.httpx_patcher import _capture_async_response

        # Should not raise - async hook must be properly awaitable
        result = await _capture_async_response(mock_response)

        # Result is None (no return value), but await should succeed
        assert result is None


class TestClientPatching:
    """Tests that verify httpx clients get patched correctly."""

    @pytest.mark.unit
    def test_sync_client_gets_hook_injected(self):
        """New httpx.Client instances should have hook injected."""
        handler = FakeHandler()
        install_rate_limit_hooks(handler)

        # Create a new client after hooks installed
        client = httpx.Client()

        # Check that event_hooks contains our hook
        response_hooks = client.event_hooks.get("response", [])
        assert len(response_hooks) > 0

        client.close()

    @pytest.mark.unit
    def test_async_client_gets_hook_injected(self):
        """New httpx.AsyncClient instances should have hook injected."""
        handler = FakeHandler()
        install_rate_limit_hooks(handler)

        # Create a new async client after hooks installed
        client = httpx.AsyncClient()

        # Check that event_hooks contains our hook
        response_hooks = client.event_hooks.get("response", [])
        assert len(response_hooks) > 0

        # Note: We don't actually close async client here since we're not in async context

    @pytest.mark.unit
    def test_preserves_existing_hooks(self):
        """Should preserve any existing event hooks."""
        handler = FakeHandler()
        custom_hook_called = []

        def custom_hook(response):
            custom_hook_called.append(True)

        install_rate_limit_hooks(handler)

        # Create client with existing hook
        client = httpx.Client(event_hooks={"response": [custom_hook]})

        # Should have both hooks
        response_hooks = client.event_hooks.get("response", [])
        assert len(response_hooks) >= 2  # Custom + our hook

        client.close()
