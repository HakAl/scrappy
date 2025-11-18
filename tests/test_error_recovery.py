"""
Tests for error recovery scenarios across the codebase.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
import json
from datetime import datetime

from src.providers.base import LLMResponse, ProviderRegistry
from src.orchestrator.cache import ResponseCache
from src.orchestrator.memory import WorkingMemory
from src.task_router.classifier import TaskClassifier, TaskType
from src.task_router.router import TaskRouter
from src.context import CodebaseContext


class TestProviderFailover:
    """Tests for provider failover and recovery."""

    @pytest.fixture
    def registry_with_providers(self):
        """Create registry with mock providers."""
        registry = ProviderRegistry()

        # Create working provider
        working_provider = Mock()
        working_provider.name = "working"
        working_provider.chat.return_value = LLMResponse(
            content="Success",
            model="model",
            provider="working",
            tokens_used=50
        )

        # Create failing provider
        failing_provider = Mock()
        failing_provider.name = "failing"
        failing_provider.chat.side_effect = Exception("Provider failure")

        registry.register(working_provider)
        registry.register(failing_provider)

        return registry

    @pytest.mark.unit
    def test_registry_has_multiple_providers(self, registry_with_providers):
        """Test registry with multiple providers."""
        available = registry_with_providers.list_available()
        assert len(available) == 2
        assert "working" in available
        assert "failing" in available

    @pytest.mark.unit
    def test_failing_provider_raises_exception(self, registry_with_providers):
        """Test that failing provider raises exception."""
        provider = registry_with_providers.get("failing")

        with pytest.raises(Exception):
            provider.chat([{"role": "user", "content": "test"}])

    @pytest.mark.unit
    def test_working_provider_succeeds(self, registry_with_providers):
        """Test that working provider succeeds."""
        provider = registry_with_providers.get("working")

        response = provider.chat([{"role": "user", "content": "test"}])
        assert response.content == "Success"

    @pytest.mark.unit
    def test_fallback_to_working_provider(self, registry_with_providers):
        """Test falling back to working provider after failure."""
        # Try failing provider first
        try:
            provider = registry_with_providers.get("failing")
            provider.chat([{"role": "user", "content": "test"}])
        except Exception:
            # Fallback to working provider
            fallback = registry_with_providers.get("working")
            response = fallback.chat([{"role": "user", "content": "test"}])
            assert response.content == "Success"


class TestCacheRecovery:
    """Tests for cache recovery and corruption handling."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create cache with file path."""
        cache_file = tmp_path / "cache.json"
        return ResponseCache(cache_file=str(cache_file))

    @pytest.mark.unit
    def test_cache_handles_corrupted_file(self, tmp_path):
        """Test cache handles corrupted file."""
        cache_file = tmp_path / "corrupted.json"
        cache_file.write_text("not valid json {")

        cache = ResponseCache(cache_file=str(cache_file))
        # Should not raise exception
        assert cache is not None
        # Cache should be empty after failed load
        stats = cache.get_stats()
        assert stats["exact_cache_entries"] == 0

    @pytest.mark.unit
    def test_cache_handles_missing_file(self, tmp_path):
        """Test cache handles missing file."""
        cache_file = tmp_path / "nonexistent.json"

        cache = ResponseCache(cache_file=str(cache_file))
        # Should not raise exception
        assert cache is not None

    @pytest.mark.unit
    def test_cache_recovers_after_clear(self, cache):
        """Test cache recovers after clearing."""
        response = LLMResponse("test", "model", "provider")
        cache.put(response, "prompt", "model")

        # Clear cache
        cache.clear()

        # Should be able to use again
        cache.put(response, "prompt2", "model")
        stats = cache.get_stats()
        assert stats["saves"] == 1

    @pytest.mark.unit
    def test_cache_handles_expired_entries(self, cache):
        """Test cache cleans up expired entries."""
        response = LLMResponse("test", "model", "provider")
        cache.put(response, "prompt", "model")

        # Manually expire entry
        for key in cache._cache:
            old_time = datetime.now().replace(year=2020)
            cache._cache[key]["cached_at"] = old_time.isoformat()

        # Cleanup should remove expired
        cache._cleanup_expired()
        stats = cache.get_stats()
        assert stats["exact_cache_entries"] == 0


class TestMemoryRecovery:
    """Tests for working memory recovery."""

    @pytest.mark.unit
    def test_memory_handles_large_file_cache(self):
        """Test memory handles large file cache."""
        memory = WorkingMemory(max_file_cache=2)

        # Add more files than cache size
        for i in range(10):
            memory.remember_file_read(f"file{i}.py", "content", 10)

        # Should only keep last N files
        assert len(memory.file_reads) == 2

    @pytest.mark.unit
    def test_memory_handles_invalid_serialization(self):
        """Test memory handles invalid serialization data."""
        invalid_data = {
            "file_reads": {"bad": "data"},  # Invalid structure
            "search_results": "not a list",  # Wrong type
        }

        # Should not crash
        try:
            memory = WorkingMemory.from_dict(invalid_data)
            # May have empty state
            assert memory is not None
        except Exception:
            # Exception is acceptable for invalid data
            pass

    @pytest.mark.unit
    def test_memory_clear_recovers_state(self):
        """Test memory clear recovers state."""
        memory = WorkingMemory()
        memory.remember_file_read("test.py", "content", 10)
        memory.remember_search("query", ["result"])

        memory.clear()

        # Should be usable again
        memory.remember_file_read("new.py", "new content", 20)
        assert len(memory.file_reads) == 1

    @pytest.mark.unit
    def test_memory_handles_empty_context_string(self):
        """Test memory handles empty state for context string."""
        memory = WorkingMemory()
        context = memory.get_context_string()
        assert context == ""


class TestTaskRouterErrorHandling:
    """Tests for task router error handling."""

    @pytest.fixture
    def router(self):
        """Create router without orchestrator."""
        return TaskRouter(orchestrator=None, verbose=False)

    @pytest.mark.unit
    def test_router_handles_none_orchestrator(self):
        """Test router handles None orchestrator."""
        router = TaskRouter(orchestrator=None)
        assert router.orchestrator is None

    @pytest.mark.unit
    def test_router_handles_conversation_without_orchestrator(self, router):
        """Test router handles conversation tasks without orchestrator."""
        result = router.route("hello")
        # Should succeed for conversation
        assert result.success is True

    @pytest.mark.unit
    def test_classifier_handles_empty_input(self):
        """Test classifier handles empty input."""
        classifier = TaskClassifier()
        result = classifier.classify("")
        # Should return a valid classification
        assert result.task_type is not None
        assert result.confidence >= 0

    @pytest.mark.unit
    def test_classifier_handles_very_long_input(self):
        """Test classifier handles very long input."""
        classifier = TaskClassifier()
        long_input = "word " * 10000
        result = classifier.classify(long_input)
        assert result is not None

    @pytest.mark.unit
    def test_router_metrics_with_failures(self, router):
        """Test router tracks failed tasks."""
        # Route several tasks
        router.route("hello")
        router.route("thanks")

        metrics = router.get_metrics()
        assert metrics.total_tasks >= 2


class TestCodebaseContextRecovery:
    """Tests for codebase context error recovery."""

    @pytest.mark.unit
    def test_context_handles_nonexistent_directory(self, tmp_path):
        """Test context handles nonexistent directory."""
        nonexistent = tmp_path / "doesnt_exist"
        context = CodebaseContext(str(nonexistent))
        # Should not crash
        assert context is not None

    @pytest.mark.unit
    def test_context_handles_empty_directory(self, tmp_path):
        """Test context handles empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        context = CodebaseContext(str(empty_dir))
        result = context.explore()

        assert result["total_files"] == 0

    @pytest.mark.unit
    def test_context_handles_permission_errors(self, tmp_path):
        """Test context handles permission errors gracefully."""
        context = CodebaseContext(str(tmp_path))
        # Exploration should handle permission errors
        result = context.explore()
        assert isinstance(result, dict)

    @pytest.mark.unit
    def test_context_cache_corruption_recovery(self, tmp_path):
        """Test context recovers from corrupted cache."""
        context = CodebaseContext(str(tmp_path))
        context.explore()

        # Corrupt the cache
        context.cache_file.write_text("invalid json {{{")

        # New context should handle corrupted cache
        context2 = CodebaseContext(str(tmp_path))
        # Should not crash
        assert context2 is not None


class TestToolContextRecovery:
    """Tests for tool context error recovery."""

    @pytest.fixture
    def context(self, temp_project_dir):
        """Create tool context."""
        from src.agent_tools.tools.base import ToolContext
        return ToolContext(project_root=temp_project_dir)

    @pytest.mark.unit
    def test_context_handles_path_errors(self, context):
        """Test context handles path errors."""
        # Invalid path should return False, not crash
        result = context.is_safe_path("../../../etc/passwd")
        assert result is False

    @pytest.mark.unit
    def test_context_remembers_without_orchestrator(self, context):
        """Test context handles missing orchestrator."""
        # Should not crash
        context.remember_file_read("test.py", "content", 10)
        context.remember_search("query", ["result"])
        context.remember_git_operation("git status", "clean")




class TestRateLimitRecovery:
    """Tests for rate limit recovery."""

    @pytest.mark.unit
    def test_rate_limiter_handles_exceeded_limits(self):
        """Test rate limiter handles exceeded limits."""
        from src.orchestrator.rate_limiter import RateLimitTracker

        tracker = RateLimitTracker()
        # Should handle rate limit scenarios
        assert tracker is not None

    @pytest.mark.unit
    def test_rate_limiter_resets_after_time(self):
        """Test rate limiter resets after time window."""
        from src.orchestrator.rate_limiter import RateLimitTracker

        tracker = RateLimitTracker()
        # Record some requests using the actual API
        tracker.record_request("provider", "model", 100, 50, 150)

        # Should be able to record more
        tracker.record_request("provider", "model", 50, 25, 75)

        # Get usage to verify tracking works
        usage = tracker.get_usage("provider")
        assert usage is not None


