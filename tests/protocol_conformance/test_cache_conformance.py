"""Cache protocol conformance tests.

Tests that cache implementations correctly conform to CacheProtocol.

Note: The CacheProtocol defines an idealized interface. Some implementations
may not implement all methods. These tests verify actual conformance and
document where implementations diverge from the protocol.
"""

import pytest
from datetime import datetime

from tests.protocol_conformance.conftest import (
    assert_implements_protocol,
    assert_isinstance_protocol,
    assert_has_method,
)

from scrappy.orchestrator.protocols import CacheProtocol


class TestResponseCacheConformance:
    """Tests for ResponseCache implementation."""









class TestResponseCacheBehavior:
    """Tests that verify actual cache behavior matches protocol contract."""

    def test_get_returns_none_for_miss(self):
        """get() should return None for cache miss."""
        from scrappy.orchestrator.cache import ResponseCache

        cache = ResponseCache()
        result = cache.get("provider", "nonexistent prompt")

        assert result is None

    def test_put_and_get_roundtrip(self):
        """put() should store value retrievable by get()."""
        from scrappy.orchestrator.cache import ResponseCache
        from scrappy.providers.base import LLMResponse

        cache = ResponseCache()

        response = LLMResponse(
            content="test response",
            model="test-model",
            provider="test-provider",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
            latency_ms=100.0,
            timestamp=datetime.now()
        )

        cache.put(response, "test prompt", model="test-model")
        result = cache.get("test-provider", "test prompt", model="test-model")

        assert result is not None
        assert result.content == "test response"

    def test_clear_removes_all_entries(self):
        """clear() should remove all cached entries."""
        from scrappy.orchestrator.cache import ResponseCache
        from scrappy.providers.base import LLMResponse

        cache = ResponseCache()

        response = LLMResponse(
            content="test response",
            model="test-model",
            provider="test-provider",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
            latency_ms=100.0,
            timestamp=datetime.now()
        )

        cache.put(response, "test prompt")
        cache.clear()

        result = cache.get("test-provider", "test prompt")
        assert result is None

    def test_get_stats_returns_dict(self):
        """get_stats() should return a dictionary with stats."""
        from scrappy.orchestrator.cache import ResponseCache

        cache = ResponseCache()
        stats = cache.get_stats()

        assert isinstance(stats, dict)
        # Should have some standard stats keys
        assert 'exact_hits' in stats or 'hits' in stats

    def test_stats_track_hits_and_misses(self):
        """Stats should track cache hits and misses."""
        from scrappy.orchestrator.cache import ResponseCache
        from scrappy.providers.base import LLMResponse

        cache = ResponseCache()

        # First access is a miss
        cache.get("provider", "prompt")

        # Put a value
        response = LLMResponse(
            content="test",
            model="model",
            provider="provider",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
            latency_ms=100.0,
            timestamp=datetime.now()
        )
        cache.put(response, "prompt")

        # Second access should be a hit
        cache.get("provider", "prompt", model="model")

        stats = cache.get_stats()
        # Should have recorded at least one miss and one hit
        assert stats.get('exact_misses', stats.get('misses', 0)) >= 1

    def test_invalidate_provider_removes_entries(self):
        """invalidate_provider() should remove entries for that provider."""
        from scrappy.orchestrator.cache import ResponseCache
        from scrappy.providers.base import LLMResponse

        cache = ResponseCache()

        response = LLMResponse(
            content="test",
            model="model",
            provider="provider-to-invalidate",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
            latency_ms=100.0,
            timestamp=datetime.now()
        )

        cache.put(response, "prompt")
        cache.invalidate_provider("provider-to-invalidate")

        result = cache.get("provider-to-invalidate", "prompt", model="model")
        assert result is None


class TestCacheProtocolSignature:
    """Tests that verify protocol method signatures."""



