"""
UsageReporter - Handles usage statistics and reporting.

Properly implements UsageReporterProtocol with dependency injection.
Follows SOLID principles:
- Single Responsibility: Only manages usage tracking and reporting
- Dependency Inversion: Depends on CacheProtocol abstraction
- Interface Segregation: Implements focused UsageReporterProtocol
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
import json

try:
    from .protocols import CacheProtocol
except ImportError:
    from orchestrator.protocols import CacheProtocol


class UsageReporter:
    """
    Manages usage reporting and statistics for the orchestrator.

    Implements UsageReporterProtocol to provide:
    - Recording of usage events via record()
    - Generation of usage reports with per-provider statistics via get_report()
    - Export of reports in various formats via export()
    - Reset of statistics via reset()

    Protocol Conformance:
        This class implements UsageReporterProtocol from manager_protocols.py
    """

    def __init__(
        self,
        cache: CacheProtocol,
        created_at: Optional[datetime] = None
    ):
        """
        Initialize UsageReporter with dependencies.

        NO side effects - just assigns dependencies.
        Owns its own task_history instead of receiving it as a parameter.

        Args:
            cache: Cache protocol for cache statistics
            created_at: Session start time (defaults to now)
        """
        self.cache = cache
        self.created_at = created_at or datetime.now()
        self.task_history: List[Dict[str, Any]] = []

    def record(
        self,
        provider: str,
        tokens_used: int,
        cached: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record usage event.

        Args:
            provider: Provider name
            tokens_used: Number of tokens used
            cached: Whether response was cached
            metadata: Optional additional metadata (e.g., latency_ms)
        """
        task_record = {
            'provider': provider,
            'tokens_used': tokens_used,
            'cached': cached,
            'timestamp': datetime.now(),
        }

        # Add metadata fields if provided
        if metadata:
            task_record.update(metadata)

        self.task_history.append(task_record)

    def get_report(self) -> Dict[str, Any]:
        """
        Get usage report.

        Returns:
            Dictionary containing:
            - total_tasks: Total tasks executed
            - by_provider: Per-provider breakdown
            - cache_stats: Cache hit/miss statistics
            - token_usage: Total tokens used
            - session_duration: Time since session started
            - cached_hits: Number of cache hits
            - api_calls: Number of actual API calls
        """
        if not self.task_history:
            return {
                'message': 'No tasks executed yet',
                'cache_stats': self.cache.get_stats(),
                'total_tasks': 0,
                'token_usage': 0,
            }

        by_provider = {}
        total_tokens = 0
        cached_hits = 0

        for task in self.task_history:
            provider = task['provider']
            tokens = task['tokens_used']

            if provider not in by_provider:
                by_provider[provider] = {
                    'count': 0,
                    'total_tokens': 0,
                    'cached_hits': 0,
                }
                # Track latency if available
                if 'latency_ms' in task:
                    by_provider[provider]['total_latency_ms'] = 0

            by_provider[provider]['count'] += 1
            by_provider[provider]['total_tokens'] += tokens
            total_tokens += tokens

            if 'latency_ms' in task:
                by_provider[provider]['total_latency_ms'] += task['latency_ms']

            if task.get('cached', False):
                by_provider[provider]['cached_hits'] += 1
                cached_hits += 1

        # Calculate averages
        for provider, stats in by_provider.items():
            stats['avg_tokens'] = stats['total_tokens'] / stats['count']
            if 'total_latency_ms' in stats:
                stats['avg_latency_ms'] = stats['total_latency_ms'] / stats['count']

        return {
            'total_tasks': len(self.task_history),
            'cached_hits': cached_hits,
            'api_calls': len(self.task_history) - cached_hits,
            'token_usage': total_tokens,
            'by_provider': by_provider,
            'session_duration': str(datetime.now() - self.created_at),
            'cache_stats': self.cache.get_stats(),
        }

    def reset(self) -> None:
        """
        Reset usage statistics.

        Clears task history but preserves session start time.
        Does not clear the cache (use cache.clear() for that).
        """
        self.task_history.clear()

    def export(self, format: str = "json") -> str:
        """
        Export usage report in specified format.

        Args:
            format: Export format (json, csv, etc.)

        Returns:
            Formatted report string

        Raises:
            ValueError: If format is not supported
        """
        report = self.get_report()

        if format == "json":
            return json.dumps(report, indent=2, default=str)
        elif format == "csv":
            # Simple CSV export for basic stats
            lines = ["metric,value"]
            lines.append(f"total_tasks,{report.get('total_tasks', 0)}")
            lines.append(f"cached_hits,{report.get('cached_hits', 0)}")
            lines.append(f"api_calls,{report.get('api_calls', 0)}")
            lines.append(f"token_usage,{report.get('token_usage', 0)}")
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    # Backward compatibility methods
    # These delegate to the protocol methods above

    def get_usage_report(self) -> Dict[str, Any]:
        """
        DEPRECATED: Use get_report() instead.
        Kept for backward compatibility with existing code.
        """
        return self.get_report()

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics directly from cache.

        This is a convenience method that delegates to cache.get_stats().
        """
        return self.cache.get_stats()

    def clear_cache(self) -> None:
        """
        Clear the response cache.

        This is a convenience method that delegates to cache.clear().
        """
        self.cache.clear()
