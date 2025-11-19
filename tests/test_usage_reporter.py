"""
Tests for UsageReporter - extracted from core.py.

Tests usage reporting, cache statistics, and cache management functionality.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock


class TestUsageReporterInit:
    """Test UsageReporter initialization."""

    def test_init_with_required_dependencies(self):
        """Should initialize with cache, task_history, created_at, and caching_enabled."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        task_history = []
        created_at = datetime.now()

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=created_at,
            caching_enabled=True
        )

        assert reporter is not None

    def test_init_stores_references_not_copies(self):
        """Should store references to allow external mutation tracking."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        task_history = []
        created_at = datetime.now()

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=created_at,
            caching_enabled=True
        )

        # Add task to the original list
        task_history.append({
            'provider': 'test',
            'tokens_used': 100,
            'latency_ms': 50,
            'cached': False
        })

        # Reporter should see the new task
        report = reporter.get_usage_report()
        assert report['total_tasks'] == 1


class TestGetUsageReport:
    """Test get_usage_report() functionality."""

    def test_no_tasks_returns_message_and_cache_stats(self):
        """When no tasks executed, should return message and cache stats."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {'hits': 0, 'misses': 0}

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=[],
            created_at=datetime.now(),
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        assert 'message' in report
        assert 'No tasks executed' in report['message']
        assert 'cache_stats' in report

    def test_single_provider_single_task(self):
        """Should aggregate stats for a single task."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {'hits': 0}

        task_history = [{
            'provider': 'cerebras',
            'tokens_used': 150,
            'latency_ms': 200,
            'cached': False
        }]

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=datetime.now(),
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        assert report['total_tasks'] == 1
        assert report['api_calls'] == 1
        assert report['cached_hits'] == 0
        assert 'cerebras' in report['by_provider']
        assert report['by_provider']['cerebras']['count'] == 1
        assert report['by_provider']['cerebras']['total_tokens'] == 150
        assert report['by_provider']['cerebras']['total_latency_ms'] == 200

    def test_multiple_providers(self):
        """Should aggregate stats by provider."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        task_history = [
            {'provider': 'cerebras', 'tokens_used': 100, 'latency_ms': 50, 'cached': False},
            {'provider': 'groq', 'tokens_used': 200, 'latency_ms': 100, 'cached': False},
            {'provider': 'cerebras', 'tokens_used': 150, 'latency_ms': 75, 'cached': False},
        ]

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=datetime.now(),
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        assert report['total_tasks'] == 3
        assert report['by_provider']['cerebras']['count'] == 2
        assert report['by_provider']['cerebras']['total_tokens'] == 250
        assert report['by_provider']['groq']['count'] == 1
        assert report['by_provider']['groq']['total_tokens'] == 200

    def test_cached_hits_tracking(self):
        """Should track cached hits separately from API calls."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        task_history = [
            {'provider': 'cerebras', 'tokens_used': 100, 'latency_ms': 50, 'cached': True},
            {'provider': 'cerebras', 'tokens_used': 100, 'latency_ms': 50, 'cached': False},
            {'provider': 'groq', 'tokens_used': 200, 'latency_ms': 100, 'cached': True},
        ]

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=datetime.now(),
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        assert report['total_tasks'] == 3
        assert report['cached_hits'] == 2
        assert report['api_calls'] == 1
        assert report['by_provider']['cerebras']['cached_hits'] == 1
        assert report['by_provider']['groq']['cached_hits'] == 1

    def test_average_calculations(self):
        """Should calculate correct averages for tokens and latency."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        task_history = [
            {'provider': 'cerebras', 'tokens_used': 100, 'latency_ms': 50, 'cached': False},
            {'provider': 'cerebras', 'tokens_used': 200, 'latency_ms': 150, 'cached': False},
        ]

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=datetime.now(),
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        # Average of 100 and 200 = 150
        assert report['by_provider']['cerebras']['avg_tokens'] == 150
        # Average of 50 and 150 = 100
        assert report['by_provider']['cerebras']['avg_latency_ms'] == 100

    def test_session_duration_included(self):
        """Should include session duration in report."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        created_at = datetime.now() - timedelta(hours=1, minutes=30)

        task_history = [
            {'provider': 'test', 'tokens_used': 100, 'latency_ms': 50, 'cached': False}
        ]

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=created_at,
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        assert 'session_duration' in report
        # Duration should be a string representation
        assert isinstance(report['session_duration'], str)

    def test_cache_stats_included(self):
        """Should include cache stats from cache object."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {
            'exact_hits': 10,
            'intent_hits': 5,
            'misses': 20
        }

        task_history = [
            {'provider': 'test', 'tokens_used': 100, 'latency_ms': 50, 'cached': False}
        ]

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=datetime.now(),
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        assert report['cache_stats']['exact_hits'] == 10
        assert report['cache_stats']['intent_hits'] == 5

    def test_task_without_cached_field_treated_as_not_cached(self):
        """Tasks without 'cached' field should be treated as not cached."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        # Task without 'cached' key
        task_history = [
            {'provider': 'test', 'tokens_used': 100, 'latency_ms': 50}
        ]

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=datetime.now(),
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        assert report['cached_hits'] == 0
        assert report['api_calls'] == 1


class TestGetCacheStats:
    """Test get_cache_stats() delegation."""

    def test_delegates_to_cache(self):
        """Should delegate to cache.get_stats()."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        expected_stats = {
            'exact_cache_entries': 10,
            'intent_cache_entries': 5,
            'hits': 20
        }
        mock_cache.get_stats.return_value = expected_stats

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=[],
            created_at=datetime.now(),
            caching_enabled=True
        )

        stats = reporter.get_cache_stats()

        mock_cache.get_stats.assert_called_once()
        assert stats == expected_stats


class TestClearCache:
    """Test clear_cache() delegation."""

    def test_delegates_to_cache(self):
        """Should call cache.clear()."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=[],
            created_at=datetime.now(),
            caching_enabled=True
        )

        reporter.clear_cache()

        mock_cache.clear.assert_called_once()


class TestToggleCache:
    """Test toggle_cache() functionality."""

    def test_toggles_from_enabled_to_disabled(self):
        """Should toggle from True to False and return new state."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=[],
            created_at=datetime.now(),
            caching_enabled=True
        )

        result = reporter.toggle_cache()

        assert result is False
        assert reporter.caching_enabled is False

    def test_toggles_from_disabled_to_enabled(self):
        """Should toggle from False to True and return new state."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=[],
            created_at=datetime.now(),
            caching_enabled=False
        )

        result = reporter.toggle_cache()

        assert result is True
        assert reporter.caching_enabled is True

    def test_multiple_toggles(self):
        """Should correctly toggle multiple times."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=[],
            created_at=datetime.now(),
            caching_enabled=True
        )

        # Toggle 3 times: True -> False -> True -> False
        assert reporter.toggle_cache() is False
        assert reporter.toggle_cache() is True
        assert reporter.toggle_cache() is False


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_tokens_in_task(self):
        """Should handle tasks with zero tokens."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        task_history = [
            {'provider': 'test', 'tokens_used': 0, 'latency_ms': 50, 'cached': False}
        ]

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=datetime.now(),
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        assert report['by_provider']['test']['total_tokens'] == 0
        assert report['by_provider']['test']['avg_tokens'] == 0

    def test_zero_latency_in_task(self):
        """Should handle tasks with zero latency."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        task_history = [
            {'provider': 'test', 'tokens_used': 100, 'latency_ms': 0, 'cached': False}
        ]

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=datetime.now(),
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        assert report['by_provider']['test']['total_latency_ms'] == 0
        assert report['by_provider']['test']['avg_latency_ms'] == 0

    def test_all_tasks_cached(self):
        """Should handle when all tasks are cached hits."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        task_history = [
            {'provider': 'test', 'tokens_used': 100, 'latency_ms': 50, 'cached': True},
            {'provider': 'test', 'tokens_used': 100, 'latency_ms': 50, 'cached': True},
        ]

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=datetime.now(),
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        assert report['total_tasks'] == 2
        assert report['cached_hits'] == 2
        assert report['api_calls'] == 0

    def test_large_number_of_tasks(self):
        """Should handle large task history efficiently."""
        from src.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        # Create 1000 tasks
        task_history = [
            {'provider': f'provider_{i % 5}', 'tokens_used': 100, 'latency_ms': 50, 'cached': i % 3 == 0}
            for i in range(1000)
        ]

        reporter = UsageReporter(
            cache=mock_cache,
            task_history=task_history,
            created_at=datetime.now(),
            caching_enabled=True
        )

        report = reporter.get_usage_report()

        assert report['total_tasks'] == 1000
        # 5 providers
        assert len(report['by_provider']) == 5


class TestIntegrationWithRealCache:
    """Integration-style tests with cache behavior."""

    def test_cache_stats_reflect_actual_usage(self):
        """Cache stats should come directly from cache object."""
        from src.orchestrator.usage_reporter import UsageReporter

        # Create a simple cache mock that tracks calls
        cache = Mock()
        cache.get_stats.return_value = {'initial': True}

        reporter = UsageReporter(
            cache=cache,
            task_history=[],
            created_at=datetime.now(),
            caching_enabled=True
        )

        # First call
        stats1 = reporter.get_cache_stats()
        assert stats1 == {'initial': True}

        # Update cache stats
        cache.get_stats.return_value = {'updated': True}

        # Second call should get updated stats
        stats2 = reporter.get_cache_stats()
        assert stats2 == {'updated': True}

    def test_clear_cache_affects_subsequent_stats(self):
        """Clearing cache should be reflected in subsequent stat calls."""
        from src.orchestrator.usage_reporter import UsageReporter

        cache = Mock()

        reporter = UsageReporter(
            cache=cache,
            task_history=[],
            created_at=datetime.now(),
            caching_enabled=True
        )

        reporter.clear_cache()

        # Verify clear was called
        cache.clear.assert_called_once()
