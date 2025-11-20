"""
Legacy compatibility shim for RateLimitTracker.

DEPRECATED: Import from orchestrator.rate_limiting instead.
This file maintains backward compatibility during the migration period.

For new code, use:
    from orchestrator.rate_limiting import create_rate_limit_tracker
    tracker = create_rate_limit_tracker(tracker_file="usage.json", auto_load=True)

Migration notes:
- The constructor signature has changed to use dependency injection
- For production use, use create_rate_limit_tracker() factory function
- For testing, instantiate RateLimitTracker with test doubles
- The 'persistence' parameter is replaced by the storage protocol
- The 'output' parameter is no longer used (was not functional in old implementation)
"""
from .rate_limiting import RateLimitTracker, create_rate_limit_tracker

__all__ = ["RateLimitTracker", "create_rate_limit_tracker"]
