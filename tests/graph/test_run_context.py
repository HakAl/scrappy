"""Tests for AgentRunContext.

Tests cover:
- Model affinity (provider success/error tracking)
- File caching (cache, invalidate, eviction)
- Status updates (callbacks)
- Lifecycle (cancel callbacks, cleanup)
- Handoff triggers (rate limit, timeout thresholds)
- Cancellation token integration
"""

import pytest

from scrappy.graph.run_context import (
    AgentRunContext,
    AgentRunContextProtocol,
    HANDOFF_TRIGGERS,
)
from scrappy.infrastructure.threading.cancellation import CancellationToken


class TestAgentRunContextProtocol:
    """Test that AgentRunContext implements the protocol."""

    def test_implements_protocol(self):
        """AgentRunContext should implement AgentRunContextProtocol."""
        ctx = AgentRunContext()
        assert isinstance(ctx, AgentRunContextProtocol)


class TestModelAffinity:
    """Tests for model affinity tracking."""

    def test_initial_state_no_preferred_provider(self):
        """Fresh context should have no preferred provider."""
        ctx = AgentRunContext()
        assert ctx.preferred_provider is None
        assert ctx.preferred_model is None

    def test_record_provider_success_sets_affinity(self):
        """First successful response should set provider affinity."""
        ctx = AgentRunContext()
        ctx.record_provider_success("anthropic", "claude-3-opus")

        assert ctx.preferred_provider == "anthropic"
        assert ctx.preferred_model == "claude-3-opus"

    def test_record_provider_success_ignores_subsequent(self):
        """Subsequent successes should not change affinity."""
        ctx = AgentRunContext()
        ctx.record_provider_success("anthropic", "claude-3-opus")
        ctx.record_provider_success("openai", "gpt-4o")

        assert ctx.preferred_provider == "anthropic"
        assert ctx.preferred_model == "claude-3-opus"

    def test_should_handoff_initially_false(self):
        """Fresh context should not trigger handoff."""
        ctx = AgentRunContext()
        assert ctx.should_handoff() is False
        assert ctx.get_handoff_reason() is None


class TestHandoffTriggers:
    """Tests for error-based handoff triggers."""

    def test_rate_limit_triggers_immediate_handoff(self):
        """Rate limit error should trigger immediate handoff."""
        ctx = AgentRunContext()
        ctx.record_provider_error("anthropic", "rate_limit")

        assert ctx.should_handoff() is True
        assert "rate_limit" in ctx.get_handoff_reason()

    def test_auth_error_triggers_immediate_handoff(self):
        """Auth error should trigger immediate handoff."""
        ctx = AgentRunContext()
        ctx.record_provider_error("anthropic", "auth_error")

        assert ctx.should_handoff() is True
        assert "auth_error" in ctx.get_handoff_reason()

    def test_quota_exceeded_triggers_immediate_handoff(self):
        """Quota exceeded should trigger immediate handoff."""
        ctx = AgentRunContext()
        ctx.record_provider_error("openai", "quota_exceeded")

        assert ctx.should_handoff() is True
        assert "quota_exceeded" in ctx.get_handoff_reason()

    def test_context_length_exceeded_triggers_immediate_handoff(self):
        """Context length exceeded should trigger immediate handoff."""
        ctx = AgentRunContext()
        ctx.record_provider_error("anthropic", "context_length_exceeded")

        assert ctx.should_handoff() is True
        assert "context_length_exceeded" in ctx.get_handoff_reason()

    def test_timeout_triggers_handoff_after_threshold(self):
        """Timeout should trigger handoff after N consecutive errors."""
        ctx = AgentRunContext()
        threshold = HANDOFF_TRIGGERS.get("timeout", 2)

        # First timeout - should not trigger
        ctx.record_provider_error("anthropic", "timeout")
        assert ctx.should_handoff() is False

        # Second timeout - should trigger (threshold is 2)
        ctx.record_provider_error("anthropic", "timeout")
        assert ctx.should_handoff() is True
        assert "timeout" in ctx.get_handoff_reason()

    def test_server_error_triggers_handoff_after_threshold(self):
        """Server error should trigger handoff after N consecutive errors."""
        ctx = AgentRunContext()
        threshold = HANDOFF_TRIGGERS.get("server_error", 3)

        # Errors below threshold
        for _ in range(threshold - 1):
            ctx.record_provider_error("anthropic", "server_error")
            assert ctx.should_handoff() is False

        # Error at threshold - should trigger
        ctx.record_provider_error("anthropic", "server_error")
        assert ctx.should_handoff() is True
        assert "server_error" in ctx.get_handoff_reason()

    def test_network_error_never_triggers_handoff(self):
        """Network errors should never trigger handoff (retry same provider)."""
        ctx = AgentRunContext()

        # Many network errors should not trigger handoff
        for _ in range(10):
            ctx.record_provider_error("anthropic", "network")

        assert ctx.should_handoff() is False

    def test_parse_error_never_triggers_handoff(self):
        """Parse errors should never trigger handoff."""
        ctx = AgentRunContext()

        for _ in range(10):
            ctx.record_provider_error("anthropic", "parse")

        assert ctx.should_handoff() is False

    def test_clear_handoff_resets_state(self):
        """clear_handoff should reset handoff state and affinity."""
        ctx = AgentRunContext()
        ctx.record_provider_success("anthropic", "claude-3-opus")
        ctx.record_provider_error("anthropic", "rate_limit")

        assert ctx.should_handoff() is True
        assert ctx.preferred_provider == "anthropic"

        ctx.clear_handoff()

        assert ctx.should_handoff() is False
        assert ctx.get_handoff_reason() is None
        assert ctx.preferred_provider is None
        assert ctx.preferred_model is None


class TestFileCaching:
    """Tests for file caching functionality."""

    def test_cache_and_retrieve_file(self):
        """Cached files should be retrievable."""
        ctx = AgentRunContext()
        ctx.cache_file("test.py", "print('hello')")

        assert ctx.get_cached_file("test.py") == "print('hello')"

    def test_get_uncached_file_returns_none(self):
        """Getting uncached file should return None."""
        ctx = AgentRunContext()
        assert ctx.get_cached_file("nonexistent.py") is None

    def test_invalidate_file_removes_from_cache(self):
        """Invalidating a file should remove it from cache."""
        ctx = AgentRunContext()
        ctx.cache_file("test.py", "content")

        ctx.invalidate_file("test.py")

        assert ctx.get_cached_file("test.py") is None  # Should not raise

    def test_cache_eviction_when_over_limit(self):
        """Oldest files should be evicted when cache exceeds limit."""
        ctx = AgentRunContext()
        ctx.MAX_CACHE_SIZE_BYTES = 100  # Small limit for testing

        # Cache files until we hit the limit
        ctx.cache_file("file1.py", "a" * 40)
        ctx.cache_file("file2.py", "b" * 40)

        # Both should be cached
        assert ctx.get_cached_file("file1.py") is not None
        assert ctx.get_cached_file("file2.py") is not None

        # Adding third file should evict oldest
        ctx.cache_file("file3.py", "c" * 40)

        # file1 should be evicted (oldest)
        assert ctx.get_cached_file("file1.py") is None
        assert ctx.get_cached_file("file2.py") is not None
        assert ctx.get_cached_file("file3.py") is not None

    def test_large_file_not_cached(self):
        """Files larger than cache limit should not be cached."""
        ctx = AgentRunContext()
        ctx.MAX_CACHE_SIZE_BYTES = 100

        # Try to cache a file larger than the limit
        ctx.cache_file("huge.py", "x" * 200)

        assert ctx.get_cached_file("huge.py") is None


class TestStatusUpdates:
    """Tests for status update callbacks."""

    def test_set_and_call_status_callback(self):
        """Status callback should be called with messages."""
        messages = []
        ctx = AgentRunContext()
        ctx.set_status_callback(lambda msg: messages.append(msg))

        ctx.update_status("thinking")
        ctx.update_status("executing tools")

        assert messages == ["thinking", "executing tools"]  # Should not raise


class TestLifecycle:
    """Tests for lifecycle management."""

    def test_register_and_call_cancel_callbacks(self):
        """Cancel callbacks should be called on cancel."""
        called = []
        ctx = AgentRunContext()
        ctx.register_cancel_callback(lambda: called.append("cb1"))
        ctx.register_cancel_callback(lambda: called.append("cb2"))

        ctx.on_cancel()

        assert called == ["cb1", "cb2"]

    def test_on_cancel_clears_file_cache(self):
        """on_cancel should clear the file cache."""
        ctx = AgentRunContext()
        ctx.cache_file("test.py", "content")

        ctx.on_cancel()

        assert ctx.get_cached_file("test.py") is None

    def test_on_cancel_clears_callbacks(self):
        """on_cancel should clear the callback list."""
        called = []
        ctx = AgentRunContext()
        ctx.register_cancel_callback(lambda: called.append("cb"))

        ctx.on_cancel()
        called.clear()  # Clear to check if second cancel calls again

        ctx.on_cancel()  # Should not call callback again

        assert called == []

    def test_callback_error_does_not_stop_others(self):
        """One callback error should not prevent other callbacks."""
        called = []
        ctx = AgentRunContext()
        ctx.register_cancel_callback(lambda: 1 / 0)  # Will raise
        ctx.register_cancel_callback(lambda: called.append("cb2"))

        ctx.on_cancel()  # Should not raise

        assert called == ["cb2"]

    def test_on_complete_calls_on_cancel(self):
        """on_complete should trigger same cleanup as on_cancel."""
        called = []
        ctx = AgentRunContext()
        ctx.register_cancel_callback(lambda: called.append("cb"))
        ctx.cache_file("test.py", "content")

        ctx.on_complete(success=True)

        assert called == ["cb"]
        assert ctx.get_cached_file("test.py") is None


class TestHandoffTriggersConfiguration:
    """Tests for HANDOFF_TRIGGERS configuration."""

    def test_all_expected_triggers_defined(self):
        """All expected error categories should be defined."""
        expected = [
            "rate_limit",
            "auth_error",
            "quota_exceeded",
            "model_not_found",
            "context_length_exceeded",
            "server_error",
            "timeout",
            "network",
            "parse",
        ]
        for trigger in expected:
            assert trigger in HANDOFF_TRIGGERS, f"Missing trigger: {trigger}"

    def test_immediate_triggers_are_true(self):
        """Immediate handoff triggers should have True value."""
        immediate = ["rate_limit", "auth_error", "quota_exceeded", "model_not_found", "context_length_exceeded"]
        for trigger in immediate:
            assert HANDOFF_TRIGGERS[trigger] is True, f"{trigger} should be True"

    def test_threshold_triggers_are_positive_int(self):
        """Threshold triggers should be positive integers."""
        threshold = ["server_error", "timeout"]
        for trigger in threshold:
            value = HANDOFF_TRIGGERS[trigger]
            assert isinstance(value, int), f"{trigger} should be int"
            assert value > 0, f"{trigger} should be positive"

    def test_never_triggers_are_false(self):
        """Never-handoff triggers should have False value."""
        never = ["network", "parse"]
        for trigger in never:
            assert HANDOFF_TRIGGERS[trigger] is False, f"{trigger} should be False"


class TestCancellationToken:
    """Tests for cancellation token integration."""

    def test_initial_state_not_cancelled(self):
        """Fresh context without token should not be cancelled."""
        ctx = AgentRunContext()
        assert ctx.is_cancelled() is False
        assert ctx.is_force_cancelled() is False

    def test_cancellation_token_property_getter_setter(self):
        """Should be able to set and get cancellation token."""
        ctx = AgentRunContext()
        token = CancellationToken()

        ctx.cancellation_token = token

        assert ctx.cancellation_token is token

    def test_is_cancelled_false_when_token_not_cancelled(self):
        """is_cancelled should return False when token is not cancelled."""
        ctx = AgentRunContext()
        token = CancellationToken()
        ctx.cancellation_token = token

        assert ctx.is_cancelled() is False

    def test_is_cancelled_true_when_token_cancelled(self):
        """is_cancelled should return True when token.cancel() called."""
        ctx = AgentRunContext()
        token = CancellationToken()
        ctx.cancellation_token = token

        token.cancel()

        assert ctx.is_cancelled() is True

    def test_is_force_cancelled_false_after_single_cancel(self):
        """is_force_cancelled should be False after single cancel."""
        ctx = AgentRunContext()
        token = CancellationToken()
        ctx.cancellation_token = token

        token.cancel()

        assert ctx.is_cancelled() is True
        assert ctx.is_force_cancelled() is False

    def test_is_force_cancelled_true_after_double_cancel(self):
        """is_force_cancelled should be True after two cancels."""
        ctx = AgentRunContext()
        token = CancellationToken()
        ctx.cancellation_token = token

        token.cancel()
        token.cancel()

        assert ctx.is_cancelled() is True
        assert ctx.is_force_cancelled() is True

    def test_is_cancelled_false_when_no_token(self):
        """is_cancelled should return False when no token is set."""
        ctx = AgentRunContext()
        # No token set
        assert ctx.is_cancelled() is False
        assert ctx.is_force_cancelled() is False

    def test_cancellation_token_initially_none(self):
        """Cancellation token should be None initially."""
        ctx = AgentRunContext()
        assert ctx.cancellation_token is None
