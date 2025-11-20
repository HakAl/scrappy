"""
Tests for UsageReporter.

Focuses on proving BEHAVIOR works, not structure.
Tests use real objects and only mock external dependencies (cache).

Following CLAUDE.md guidelines:
- Tests prove features work, not just that code runs
- Edge cases covered (empty, zero, boundaries)
- Minimal mocking (only cache, which is external dependency)
- Tests would fail if feature breaks
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock
from src.orchestrator.usage_reporter import UsageReporter


class TestUsageRecording:
    """Test that usage recording actually captures and aggregates data correctly."""

    def test_records_single_task_and_retrieves_it(self):
        """Recording a task should make it appear in the report."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='cerebras', tokens_used=150, cached=False)

        report = reporter.get_report()

        assert report['total_tasks'] == 1
        assert report['token_usage'] == 150
        assert report['by_provider']['cerebras']['count'] == 1
        assert report['by_provider']['cerebras']['total_tokens'] == 150

    def test_records_multiple_tasks_from_same_provider(self):
        """Multiple tasks from same provider should aggregate correctly."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='cerebras', tokens_used=100, cached=False)
        reporter.record(provider='cerebras', tokens_used=200, cached=False)

        report = reporter.get_report()

        assert report['total_tasks'] == 2
        assert report['token_usage'] == 300
        assert report['by_provider']['cerebras']['count'] == 2
        assert report['by_provider']['cerebras']['total_tokens'] == 300
        assert report['by_provider']['cerebras']['avg_tokens'] == 150

    def test_records_tasks_from_multiple_providers(self):
        """Tasks from different providers should be tracked separately."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='cerebras', tokens_used=100, cached=False)
        reporter.record(provider='groq', tokens_used=200, cached=False)
        reporter.record(provider='cerebras', tokens_used=50, cached=False)

        report = reporter.get_report()

        assert report['total_tasks'] == 3
        assert report['token_usage'] == 350
        assert report['by_provider']['cerebras']['count'] == 2
        assert report['by_provider']['cerebras']['total_tokens'] == 150
        assert report['by_provider']['groq']['count'] == 1
        assert report['by_provider']['groq']['total_tokens'] == 200

    def test_distinguishes_cached_from_api_calls(self):
        """Cached hits should be counted separately from API calls."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='cerebras', tokens_used=100, cached=True)
        reporter.record(provider='cerebras', tokens_used=100, cached=False)
        reporter.record(provider='groq', tokens_used=200, cached=True)

        report = reporter.get_report()

        assert report['total_tasks'] == 3
        assert report['cached_hits'] == 2
        assert report['api_calls'] == 1
        assert report['by_provider']['cerebras']['cached_hits'] == 1
        assert report['by_provider']['groq']['cached_hits'] == 1

    def test_records_metadata_like_latency(self):
        """Metadata like latency_ms should be tracked and averaged."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='cerebras', tokens_used=100, cached=False,
                       metadata={'latency_ms': 50})
        reporter.record(provider='cerebras', tokens_used=200, cached=False,
                       metadata={'latency_ms': 150})

        report = reporter.get_report()

        assert report['by_provider']['cerebras']['total_latency_ms'] == 200
        assert report['by_provider']['cerebras']['avg_latency_ms'] == 100


class TestUsageReset:
    """Test that reset actually clears data."""

    def test_reset_clears_all_recorded_tasks(self):
        """Reset should remove all task history."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='cerebras', tokens_used=100, cached=False)
        reporter.record(provider='groq', tokens_used=200, cached=False)

        reporter.reset()

        report = reporter.get_report()
        assert report['total_tasks'] == 0
        assert report['token_usage'] == 0

    def test_reset_preserves_session_start_time(self):
        """Reset should not change when the session started."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        start_time = datetime.now() - timedelta(hours=1)
        reporter = UsageReporter(cache=mock_cache, created_at=start_time)
        reporter.record(provider='cerebras', tokens_used=100, cached=False)

        reporter.reset()

        assert reporter.created_at == start_time

    def test_can_record_again_after_reset(self):
        """After reset, should be able to record new tasks."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='cerebras', tokens_used=100, cached=False)
        reporter.reset()
        reporter.record(provider='groq', tokens_used=200, cached=False)

        report = reporter.get_report()
        assert report['total_tasks'] == 1
        assert report['token_usage'] == 200
        assert 'groq' in report['by_provider']
        assert 'cerebras' not in report['by_provider']


class TestUsageExport:
    """Test that export produces valid output in different formats."""

    def test_exports_to_json_format(self):
        """Export as JSON should produce valid JSON string."""
        import json

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {'hits': 5}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='cerebras', tokens_used=100, cached=False)

        exported = reporter.export(format='json')

        # Should be valid JSON
        data = json.loads(exported)
        assert data['total_tasks'] == 1
        assert data['token_usage'] == 100

    def test_exports_to_csv_format(self):
        """Export as CSV should produce valid CSV string."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='cerebras', tokens_used=100, cached=False)
        reporter.record(provider='groq', tokens_used=200, cached=True)

        exported = reporter.export(format='csv')

        lines = exported.split('\n')
        assert 'metric,value' in lines[0]
        assert 'total_tasks,2' in exported
        assert 'cached_hits,1' in exported
        assert 'api_calls,1' in exported
        assert 'token_usage,300' in exported



class TestEdgeCases:
    """Test boundary conditions and edge cases."""

    def test_empty_report_when_no_tasks_recorded(self):
        """Report with no tasks should return appropriate message."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {'hits': 0}

        reporter = UsageReporter(cache=mock_cache)

        report = reporter.get_report()

        assert 'message' in report
        assert 'No tasks executed' in report['message']
        assert report['total_tasks'] == 0

    def test_handles_zero_tokens(self):
        """Should handle tasks with zero tokens correctly."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='test', tokens_used=0, cached=False)

        report = reporter.get_report()

        assert report['token_usage'] == 0
        assert report['by_provider']['test']['avg_tokens'] == 0

    def test_handles_zero_latency(self):
        """Should handle tasks with zero latency correctly."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='test', tokens_used=100, cached=False,
                       metadata={'latency_ms': 0})

        report = reporter.get_report()

        assert report['by_provider']['test']['avg_latency_ms'] == 0

    def test_all_cached_tasks_results_in_zero_api_calls(self):
        """When all tasks are cached, API calls should be zero."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='test', tokens_used=100, cached=True)
        reporter.record(provider='test', tokens_used=100, cached=True)

        report = reporter.get_report()

        assert report['api_calls'] == 0
        assert report['cached_hits'] == 2

    def test_handles_large_number_of_tasks(self):
        """Should efficiently handle large task history."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)

        # Record 1000 tasks across 5 providers
        for i in range(1000):
            reporter.record(
                provider=f'provider_{i % 5}',
                tokens_used=100,
                cached=i % 3 == 0
            )

        report = reporter.get_report()

        assert report['total_tasks'] == 1000
        assert len(report['by_provider']) == 5
        # Every 3rd task is cached
        assert report['cached_hits'] == 334


class TestCacheIntegration:
    """Test integration with cache statistics."""

    def test_includes_cache_stats_in_report(self):
        """Report should include cache statistics from cache object."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {
            'exact_hits': 10,
            'intent_hits': 5,
            'misses': 20
        }

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='test', tokens_used=100, cached=False)

        report = reporter.get_report()

        assert report['cache_stats']['exact_hits'] == 10
        assert report['cache_stats']['intent_hits'] == 5
        assert report['cache_stats']['misses'] == 20

    def test_get_cache_stats_delegates_to_cache(self):
        """get_cache_stats() should return cache.get_stats()."""
        mock_cache = Mock()
        expected_stats = {'hits': 42, 'misses': 13}
        mock_cache.get_stats.return_value = expected_stats

        reporter = UsageReporter(cache=mock_cache)

        stats = reporter.get_cache_stats()

        assert stats == expected_stats
        mock_cache.get_stats.assert_called_once()



class TestBackwardCompatibility:
    """Test backward compatibility methods still work."""

    def test_get_usage_report_delegates_to_get_report(self):
        """DEPRECATED get_usage_report() should still work."""
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {}

        reporter = UsageReporter(cache=mock_cache)
        reporter.record(provider='test', tokens_used=100, cached=False)

        # Both should return functionally equivalent data
        # (session_duration may differ by microseconds due to timing)
        report1 = reporter.get_report()
        report2 = reporter.get_usage_report()

        assert report1['total_tasks'] == report2['total_tasks']
        assert report1['token_usage'] == report2['token_usage']
        assert report1['by_provider'] == report2['by_provider']
        assert report1['cached_hits'] == report2['cached_hits']
        assert report1['api_calls'] == report2['api_calls']
