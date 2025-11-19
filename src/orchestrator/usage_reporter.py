"""
UsageReporter - Handles usage statistics and cache management.

Extracted from core.py to provide a cohesive reporting unit.
"""

from datetime import datetime
from typing import List


class UsageReporter:
    """
    Manages usage reporting and cache operations for the orchestrator.

    Provides methods to:
    - Generate usage reports with per-provider statistics
    - Access and manage cache statistics
    - Toggle caching on/off
    """

    def __init__(
        self,
        cache,
        task_history: List[dict],
        created_at: datetime,
        caching_enabled: bool
    ):
        """
        Initialize UsageReporter with dependencies.

        Args:
            cache: Cache object with get_stats() and clear() methods
            task_history: List of task dictionaries (reference, not copy)
            created_at: Session start time for duration calculation
            caching_enabled: Initial caching state
        """
        self.cache = cache
        self.task_history = task_history
        self.created_at = created_at
        self.caching_enabled = caching_enabled

    def get_usage_report(self) -> dict:
        """
        Get usage statistics for current session.

        Returns:
            Dictionary containing:
            - total_tasks: Total number of tasks executed
            - cached_hits: Number of cache hits
            - api_calls: Number of actual API calls
            - by_provider: Per-provider statistics
            - session_duration: Time since session started
            - cache_stats: Cache statistics
        """
        if not self.task_history:
            return {
                'message': 'No tasks executed yet',
                'cache_stats': self.cache.get_stats()
            }

        by_provider = {}
        cached_hits = 0

        for task in self.task_history:
            provider = task['provider']
            if provider not in by_provider:
                by_provider[provider] = {
                    'count': 0,
                    'total_tokens': 0,
                    'total_latency_ms': 0,
                    'cached_hits': 0,
                }
            by_provider[provider]['count'] += 1
            by_provider[provider]['total_tokens'] += task['tokens_used']
            by_provider[provider]['total_latency_ms'] += task['latency_ms']

            if task.get('cached', False):
                by_provider[provider]['cached_hits'] += 1
                cached_hits += 1

        # Calculate averages
        for provider, stats in by_provider.items():
            stats['avg_tokens'] = stats['total_tokens'] / stats['count']
            stats['avg_latency_ms'] = stats['total_latency_ms'] / stats['count']

        return {
            'total_tasks': len(self.task_history),
            'cached_hits': cached_hits,
            'api_calls': len(self.task_history) - cached_hits,
            'by_provider': by_provider,
            'session_duration': str(datetime.now() - self.created_at),
            'cache_stats': self.cache.get_stats(),
        }

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return self.cache.get_stats()

    def clear_cache(self):
        """Clear the response cache."""
        self.cache.clear()

    def toggle_cache(self) -> bool:
        """
        Toggle caching on/off.

        Returns:
            New caching state (True = enabled, False = disabled)
        """
        self.caching_enabled = not self.caching_enabled
        return self.caching_enabled
