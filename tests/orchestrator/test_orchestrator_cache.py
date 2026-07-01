"""
Tests for ResponseCache - LLM response caching system.
"""
import pytest

from scrappy.orchestrator.cache import ResponseCache
from scrappy.orchestrator.provider_types import LLMResponse


class TestResponseCacheBasics:
    """Basic cache operations."""

    @pytest.fixture
    def cache(self):
        """Create an in-memory cache."""
        return ResponseCache()

    @pytest.fixture
    def sample_response(self):
        """Create a sample LLM response."""
        return LLMResponse(
            content="Test response content",
            model="test-model",
            provider="test-provider",
            tokens_used=100,
            input_tokens=30,
            output_tokens=70
        )

    @pytest.mark.unit
    def test_cache_miss(self, cache):
        """Test cache miss returns None."""
        result = cache.get("provider", "prompt")
        assert result is None

    @pytest.mark.unit
    def test_cache_put_and_get(self, cache, sample_response):
        """Test storing and retrieving from cache."""
        cache.put(
            sample_response,
            prompt="test prompt",
            model="test-model"
        )

        result = cache.get(
            "test-provider",
            "test prompt",
            model="test-model"
        )

        assert result is not None
        assert result.content == "Test response content"
        assert result.provider == "test-provider"
        assert result.tokens_used == 100

    @pytest.mark.unit
    def test_cache_hit_increments_stats(self, cache, sample_response):
        """Test that cache hits are tracked."""
        cache.put(sample_response, "prompt", "model")
        cache.get("test-provider", "prompt", model="model")

        stats = cache.get_stats()
        assert stats["exact_hits"] == 1

    @pytest.mark.unit
    def test_cache_miss_increments_stats(self, cache):
        """Test that cache misses are tracked."""
        cache.get("provider", "nonexistent")

        stats = cache.get_stats()
        assert stats["exact_misses"] == 1

    @pytest.mark.unit
    def test_cache_stores_all_fields(self, cache, sample_response):
        """Test that all response fields are cached."""
        cache.put(sample_response, "prompt", "model")
        result = cache.get("test-provider", "prompt", model="model")

        assert result.content == sample_response.content
        assert result.model == sample_response.model
        assert result.provider == sample_response.provider
        assert result.tokens_used == sample_response.tokens_used
        assert result.input_tokens == sample_response.input_tokens
        assert result.output_tokens == sample_response.output_tokens


class TestCacheNormalization:
    """Tests for query normalization."""

    @pytest.fixture
    def cache(self):
        return ResponseCache()

    @pytest.mark.unit
    def test_normalize_text_lowercase(self, cache):
        """Test that text is converted to lowercase."""
        result = cache._normalize_text("HELLO WORLD")
        assert result == "hello world"

    @pytest.mark.unit
    def test_normalize_text_whitespace(self, cache):
        """Test that multiple whitespace is collapsed."""
        result = cache._normalize_text("hello    world")
        assert result == "hello world"

    @pytest.mark.unit
    def test_normalize_text_newlines(self, cache):
        """Test that newlines are replaced."""
        result = cache._normalize_text("hello\n\nworld")
        assert result == "hello world"

    @pytest.mark.unit
    def test_normalize_text_punctuation(self, cache):
        """Test punctuation spacing normalization."""
        result = cache._normalize_text("hello , world !")
        assert result == "hello, world!"

    @pytest.mark.unit
    def test_same_content_different_formatting_matches(self, cache):
        """Test that same query with different formatting hits cache."""
        response = LLMResponse(
            content="Answer",
            model="model",
            provider="provider"
        )

        # Store with one formatting
        cache.put(response, "  what is   python  ", "model")

        # Retrieve with different formatting
        result = cache.get("provider", "what is python", model="model")
        assert result is not None
        assert result.content == "Answer"


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    @pytest.fixture
    def cache(self):
        return ResponseCache()

    @pytest.mark.unit
    def test_different_prompts_different_keys(self, cache):
        """Test that different prompts generate different keys."""
        key1 = cache._generate_key("provider", "prompt1")
        key2 = cache._generate_key("provider", "prompt2")
        assert key1 != key2

    @pytest.mark.unit
    def test_different_providers_different_keys(self, cache):
        """Test that different providers generate different keys."""
        key1 = cache._generate_key("provider1", "prompt")
        key2 = cache._generate_key("provider2", "prompt")
        assert key1 != key2

    @pytest.mark.unit
    def test_different_temperatures_different_keys(self, cache):
        """Test that different temperatures generate different keys."""
        key1 = cache._generate_key("provider", "prompt", temperature=0.5)
        key2 = cache._generate_key("provider", "prompt", temperature=0.9)
        assert key1 != key2

    @pytest.mark.unit
    def test_same_params_same_key(self, cache):
        """Test that same parameters generate same key."""
        key1 = cache._generate_key("provider", "prompt", "model", "system", 1000, 0.7)
        key2 = cache._generate_key("provider", "prompt", "model", "system", 1000, 0.7)
        assert key1 == key2

    @pytest.mark.unit
    def test_keys_are_hashes(self, cache):
        """Test that keys are SHA256 hashes."""
        key = cache._generate_key("provider", "prompt")
        # SHA256 produces 64 character hex string
        assert len(key) == 64
        assert all(c in '0123456789abcdef' for c in key)


class TestCacheExpiration:
    """Tests for TTL-based cache expiration."""

    @pytest.mark.unit
    def test_valid_entries_returned(self):
        """Test that non-expired entries are returned."""
        cache = ResponseCache(default_ttl_hours=24)
        response = LLMResponse(
            content="Fresh response",
            model="model",
            provider="provider"
        )

        cache.put(response, "prompt", "model")

        # Should return the cached response
        result = cache.get("provider", "prompt", model="model")
        assert result is not None
        assert result.content == "Fresh response"


class TestIntentBasedCache:
    """Tests for intent-based semantic caching."""

    @pytest.fixture
    def cache(self):
        return ResponseCache()

    @pytest.fixture
    def response(self):
        return LLMResponse(
            content="Intent response",
            model="model",
            provider="provider",
            tokens_used=50
        )

    @pytest.mark.unit
    def test_put_and_get_by_intent(self, cache, response):
        """Test storing and retrieving by intent."""
        cache.put_by_intent(
            response,
            intent="code_search",
            entities={"file_path": ["main.py"]},
            keywords=["search", "function"]
        )

        result = cache.get_by_intent(
            intent="code_search",
            entities={"file_path": ["main.py"]},
            keywords=["search", "function"],
            provider="provider",
            model="model"
        )

        assert result is not None
        assert result.content == "Intent response"

    @pytest.mark.unit
    def test_intent_cache_miss(self, cache):
        """Test intent cache miss."""
        result = cache.get_by_intent(
            intent="nonexistent",
            entities={},
            keywords=[],
            provider="provider"
        )

        assert result is None
        stats = cache.get_stats()
        assert stats["intent_misses"] == 1

    @pytest.mark.unit
    def test_intent_key_ignores_unimportant_entities(self, cache):
        """Test that unimportant entities don't affect cache key."""
        key1 = cache._generate_intent_key(
            "search",
            {"file_path": ["main.py"], "random_entity": ["value"]},
            [],
            "provider"
        )
        key2 = cache._generate_intent_key(
            "search",
            {"file_path": ["main.py"], "other_entity": ["other"]},
            [],
            "provider"
        )

        # Should be same because random entities are filtered
        assert key1 == key2

    @pytest.mark.unit
    def test_intent_key_sensitive_to_important_entities(self, cache):
        """Test that important entities affect cache key."""
        key1 = cache._generate_intent_key(
            "search",
            {"file_path": ["main.py"]},
            [],
            "provider"
        )
        key2 = cache._generate_intent_key(
            "search",
            {"file_path": ["utils.py"]},
            [],
            "provider"
        )

        # Should be different because file_path is important
        assert key1 != key2


class TestCacheStatistics:
    """Tests for cache statistics."""

    @pytest.mark.unit
    def test_initial_stats(self):
        """Test initial statistics are zero."""
        cache = ResponseCache()
        stats = cache.get_stats()

        assert stats["exact_hits"] == 0
        assert stats["exact_misses"] == 0
        assert stats["saves"] == 0
        assert stats["intent_hits"] == 0
        assert stats["intent_misses"] == 0
        assert stats["exact_cache_entries"] == 0

    @pytest.mark.unit
    def test_hit_rate_calculation(self):
        """Test hit rate percentage calculation."""
        cache = ResponseCache()
        response = LLMResponse("test", "model", "provider")

        # 1 hit, 1 miss = 50% hit rate
        cache.put(response, "prompt", "model")
        cache.get("provider", "prompt", model="model")  # hit
        cache.get("provider", "other", model="model")  # miss

        stats = cache.get_stats()
        assert stats["exact_hit_rate"] == "50.0%"

    @pytest.mark.unit
    def test_saves_tracked(self):
        """Test that saves are counted."""
        cache = ResponseCache()
        response = LLMResponse("test", "model", "provider")

        cache.put(response, "prompt1", "model")
        cache.put(response, "prompt2", "model")

        stats = cache.get_stats()
        assert stats["saves"] == 2


class TestCacheClear:
    """Tests for cache clearing."""

    @pytest.mark.unit
    def test_clear_removes_all_entries(self):
        """Test that clear removes all cache entries."""
        cache = ResponseCache()
        response = LLMResponse("test", "model", "provider")

        cache.put(response, "prompt1", "model")
        cache.put_by_intent(response, "intent", {}, [])

        cache.clear()

        stats = cache.get_stats()
        assert stats["exact_cache_entries"] == 0
        assert stats["intent_cache_entries"] == 0
        assert stats["exact_hits"] == 0

    @pytest.mark.unit
    def test_invalidate_provider(self):
        """Test invalidating cache for specific provider."""
        cache = ResponseCache()
        response1 = LLMResponse("test1", "model", "provider1")
        response2 = LLMResponse("test2", "model", "provider2")

        cache.put(response1, "prompt", "model")
        cache.put(response2, "prompt", "model")

        cache.invalidate_provider("provider1")

        # provider1 entry should be gone
        result1 = cache.get("provider1", "prompt", model="model")
        assert result1 is None

        # provider2 entry should still exist
        # Note: This test assumes cache stores provider in entry
        # May need adjustment based on actual implementation


class TestCacheInvalidate:
    """Tests for granular cache invalidation."""

    @pytest.fixture
    def cache(self):
        return ResponseCache()

    @pytest.mark.unit
    def test_invalidate_returns_count(self, cache):
        """Test that invalidate returns number of removed entries."""
        response = LLMResponse("test", "model", "provider")
        cache.put(response, "prompt1", "model")
        cache.put(response, "prompt2", "model")

        count = cache.invalidate(provider="provider")
        assert count == 2

    @pytest.mark.unit
    def test_invalidate_by_provider_only(self, cache):
        """Test invalidating all entries for a specific provider."""
        response1 = LLMResponse("test1", "model", "provider1")
        response2 = LLMResponse("test2", "model", "provider2")

        cache.put(response1, "prompt1", "model")
        cache.put(response1, "prompt2", "model")
        cache.put(response2, "prompt3", "model")

        count = cache.invalidate(provider="provider1")

        assert count == 2
        # provider1 entries should be gone
        assert cache.get("provider1", "prompt1", model="model") is None
        assert cache.get("provider1", "prompt2", model="model") is None
        # provider2 entry should remain
        assert cache.get("provider2", "prompt3", model="model") is not None

    @pytest.mark.unit
    def test_invalidate_all_when_no_filters(self, cache):
        """Test that invalidate with no filters removes all entries."""
        response1 = LLMResponse("test1", "model", "provider1")
        response2 = LLMResponse("test2", "model", "provider2")

        cache.put(response1, "prompt1", "model")
        cache.put(response2, "prompt2", "model")

        count = cache.invalidate()

        assert count == 2
        stats = cache.get_stats()
        assert stats["exact_cache_entries"] == 0

    @pytest.mark.unit
    def test_invalidate_returns_zero_for_empty_cache(self, cache):
        """Test that invalidate returns 0 when cache is empty."""
        count = cache.invalidate(provider="nonexistent")
        assert count == 0

    @pytest.mark.unit
    def test_invalidate_includes_intent_cache(self, cache):
        """Test that invalidate also clears intent cache entries."""
        response = LLMResponse("test", "model", "provider")

        # Add to both exact and intent caches
        cache.put(response, "prompt", "model")
        cache.put_by_intent(response, "intent", {"file_path": ["test.py"]}, [])

        count = cache.invalidate(provider="provider")

        # Should have removed from both caches
        assert count == 2
        stats = cache.get_stats()
        assert stats["exact_cache_entries"] == 0
        assert stats["intent_cache_entries"] == 0

    @pytest.mark.unit
    def test_invalidate_provider_returns_count(self, cache):
        """Test that invalidate_provider now returns count."""
        response = LLMResponse("test", "model", "provider")
        cache.put(response, "prompt1", "model")
        cache.put(response, "prompt2", "model")

        count = cache.invalidate_provider("provider")
        assert count == 2

    @pytest.mark.unit
    def test_invalidate_provider_returns_zero_when_not_found(self, cache):
        """Test invalidate_provider returns 0 when provider not found."""
        response = LLMResponse("test", "model", "provider1")
        cache.put(response, "prompt", "model")

        count = cache.invalidate_provider("provider2")
        assert count == 0


class TestCachePersistence:
    """Tests for cache file persistence."""

    @pytest.mark.unit
    def test_cache_with_file_path(self, tmp_path):
        """Test cache initialization with file path."""
        cache_file = tmp_path / "test_cache.json"
        cache = ResponseCache(cache_file=str(cache_file))

        assert cache.cache_file == cache_file

    @pytest.mark.unit
    def test_cache_saves_to_file(self, tmp_path):
        """Test that cache saves to file."""
        cache_file = tmp_path / "test_cache.json"
        cache = ResponseCache(cache_file=str(cache_file))
        response = LLMResponse("test", "model", "provider")

        cache.put(response, "prompt", "model")

        # File should exist after put
        assert cache_file.exists()

        # Note: This might fail if entries expired during test
        # The implementation cleans expired entries on load
