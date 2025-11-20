"""
Display formatting infrastructure.

Provides formatters for statistics, tables, and other CLI displays.
Extracted from CLI handlers to eliminate duplication.
"""

from .protocols import (
    StatsFormatterProtocol,
    RateLimitFormatterProtocol,
    CacheFormatterProtocol,
    TableFormatterProtocol,
)
from .stats_formatter import StatsFormatter
from .rate_limit_formatter import RateLimitFormatter
from .cache_formatter import CacheFormatter

__all__ = [
    # Protocols
    "StatsFormatterProtocol",
    "RateLimitFormatterProtocol",
    "CacheFormatterProtocol",
    "TableFormatterProtocol",
    # Implementations
    "StatsFormatter",
    "RateLimitFormatter",
    "CacheFormatter",
]
