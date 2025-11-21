"""
Tests for display formatting infrastructure.

These tests prove that formatters correctly format statistics displays
with appropriate colors, alignment, and structure.
"""

import pytest
from src.infrastructure.formatters import (
    StatsFormatter,
    RateLimitFormatter,
    CacheFormatter,
)


class TestStatsFormatter:
    """Tests for base stats formatter."""

    def test_format_header_creates_colored_header(self):
        """Formatter creates header with title and separator."""
        formatter = StatsFormatter()
        result = formatter.format_header("Test Header", width=30)

        assert "Test Header" in result
        assert "-" in result  # Contains separator

    def test_format_key_value_creates_pair(self):
        """Formatter creates key-value pair display."""
        formatter = StatsFormatter()
        result = formatter.format_key_value("Key", "Value")

        assert "Key: Value" in result

    def test_format_key_value_respects_indent(self):
        """Formatter indents key-value pairs correctly."""
        formatter = StatsFormatter()
        result = formatter.format_key_value("Key", "Value", indent=4)

        assert result.startswith("    ")  # 4 spaces
        assert "Key: Value" in result

    def test_format_percentage_shows_numbers(self):
        """Formatter displays percentage with numbers."""
        formatter = StatsFormatter()
        result = formatter.format_percentage(25, 100, show_numbers=True)

        assert "25" in result
        assert "100" in result
        assert "25.0%" in result

    def test_format_percentage_without_numbers(self):
        """Formatter displays percentage without numbers."""
        formatter = StatsFormatter()
        result = formatter.format_percentage(25, 100, show_numbers=False)

        # Should only show percentage
        assert "25.0%" in result
        # Should not show fraction in plain text (may have ANSI codes)
        assert "25/100" not in result.replace("\x1b", "")  # Remove ANSI

    def test_format_percentage_handles_zero_total(self):
        """Formatter handles zero total gracefully."""
        formatter = StatsFormatter()
        result = formatter.format_percentage(10, 0)

        assert "0.0%" in result  # Should show 0% not error

    def test_format_percentage_colors_by_threshold(self):
        """Formatter applies different colors based on percentage."""
        formatter = StatsFormatter()

        # Low usage should be green (< 75%)
        low_result = formatter.format_percentage(50, 100)
        assert "\x1b" in low_result  # Has ANSI color codes

        # Medium usage should be yellow (75-90%)
        medium_result = formatter.format_percentage(80, 100)
        assert "\x1b" in medium_result

        # High usage should be red (>= 90%)
        high_result = formatter.format_percentage(95, 100)
        assert "\x1b" in high_result

    def test_format_number_adds_commas(self):
        """Formatter adds thousand separators to numbers."""
        formatter = StatsFormatter()
        result = formatter.format_number(1234567, with_commas=True)

        assert result == "1,234,567"

    def test_format_number_without_commas(self):
        """Formatter displays numbers without separators."""
        formatter = StatsFormatter()
        result = formatter.format_number(1234567, with_commas=False)

        assert result == "1234567"

    def test_format_boolean_status_true(self):
        """Formatter displays enabled status in green."""
        formatter = StatsFormatter()
        result = formatter.format_boolean_status(True)

        assert "Enabled" in result
        assert "\x1b" in result  # Has color codes

    def test_format_boolean_status_false(self):
        """Formatter displays disabled status in red."""
        formatter = StatsFormatter()
        result = formatter.format_boolean_status(False)

        assert "Disabled" in result
        assert "\x1b" in result  # Has color codes

    def test_format_boolean_status_custom_labels(self):
        """Formatter uses custom labels for boolean status."""
        formatter = StatsFormatter()
        result = formatter.format_boolean_status(True, "Active", "Inactive")

        assert "Active" in result


class TestRateLimitFormatter:
    """Tests for rate limit formatter."""

    def test_format_status_displays_header(self):
        """Formatter displays rate limit header."""
        formatter = RateLimitFormatter()
        status = {
            'last_reset': {'daily': '2024-01-15', 'monthly': '2024-01-01'},
            'providers': {}
        }

        result = formatter.format_status(status)

        assert "Rate Limit Usage" in result

    def test_format_status_shows_reset_times(self):
        """Formatter displays last reset timestamps."""
        formatter = RateLimitFormatter()
        status = {
            'last_reset': {'daily': '2024-01-15T10:30:00', 'monthly': '2024-01-01T00:00:00'},
            'providers': {}
        }

        result = formatter.format_status(status)

        assert "Last Daily Reset" in result
        assert "Last Monthly Reset" in result
        assert "2024-01-15T10:30:00" in result
        assert "2024-01-01T00:00:00" in result

    def test_format_status_handles_no_data(self):
        """Formatter displays helpful message when no data."""
        formatter = RateLimitFormatter()
        status = {
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {}
        }

        result = formatter.format_status(status)

        assert "No usage data" in result
        assert "tracked as you make API calls" in result

    def test_format_status_filters_provider(self):
        """Formatter filters to specific provider when requested."""
        formatter = RateLimitFormatter()
        status = {
            'last_reset': {'daily': '2024-01-15', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {'total_requests_today': 10, 'total_tokens_today': 1000, 'total_requests_month': 50},
                'anthropic': {'total_requests_today': 5, 'total_tokens_today': 500, 'total_requests_month': 25}
            }
        }

        result = formatter.format_status(status, provider_filter="openai")

        assert "OPENAI" in result
        assert "ANTHROPIC" not in result

    def test_format_status_shows_provider_not_found(self):
        """Formatter displays error for unknown provider."""
        formatter = RateLimitFormatter()
        status = {
            'last_reset': {'daily': '2024-01-15', 'monthly': '2024-01-01'},
            'providers': {'openai': {}}
        }

        result = formatter.format_status(status, provider_filter="unknown")

        assert "not found" in result

    def test_format_quota_line_shows_usage(self):
        """Formatter displays quota usage with percentage."""
        formatter = RateLimitFormatter()
        result = formatter.format_quota_line("Daily Requests", 50, 100)

        assert "Daily Requests" in result
        assert "50" in result
        assert "100" in result
        assert "50.0%" in result

    def test_format_quota_line_handles_zero_limit(self):
        """Formatter handles zero limit gracefully."""
        formatter = RateLimitFormatter()
        result = formatter.format_quota_line("Daily Requests", 10, 0)

        assert "0.0%" in result  # Should not error

    def test_format_provider_section_displays_totals(self):
        """Formatter displays provider totals correctly."""
        formatter = RateLimitFormatter()
        data = {
            'total_requests_today': 42,
            'total_tokens_today': 12345,
            'total_requests_month': 200
        }

        result = formatter.format_provider_section("openai", data)

        assert "OPENAI" in result
        assert "42" in result
        assert "12,345" in result  # With comma separator
        assert "200" in result

    def test_format_provider_section_shows_quotas(self):
        """Formatter displays quota information when available."""
        formatter = RateLimitFormatter()
        data = {
            'total_requests_today': 50,
            'total_tokens_today': 10000,
            'total_requests_month': 150,
            'limits': {
                'requests_per_day': 100,
                'tokens_per_day': 50000
            },
            'remaining': {
                'usage_today': 50,
                'tokens_today': 10000
            }
        }

        result = formatter.format_provider_section("openai", data)

        assert "Quotas" in result
        assert "Daily Requests" in result
        assert "Daily Tokens" in result

    def test_format_provider_section_shows_model_breakdown(self):
        """Formatter displays per-model usage breakdown."""
        formatter = RateLimitFormatter()
        data = {
            'total_requests_today': 30,
            'total_tokens_today': 5000,
            'total_requests_month': 100,
            'by_model': {
                'gpt-4': {
                    'requests_today': 20,
                    'tokens_today': 4000,
                    'last_request': '2024-01-15T10:30:45'
                },
                'gpt-3.5-turbo': {
                    'requests_today': 10,
                    'tokens_today': 1000,
                    'last_request': '2024-01-15T09:15:30'
                }
            }
        }

        result = formatter.format_provider_section("openai", data)

        assert "By Model" in result
        assert "gpt-4" in result
        assert "gpt-3.5-turbo" in result
        assert "20" in result  # gpt-4 requests
        assert "10" in result  # gpt-3.5 requests

    def test_format_warnings_displays_list(self):
        """Formatter displays warnings in red."""
        formatter = RateLimitFormatter()
        warnings = [
            "OpenAI approaching daily limit (90%)",
            "Anthropic tokens high usage"
        ]

        result = formatter.format_warnings(warnings)

        assert "WARNINGS" in result
        assert "OpenAI approaching daily limit" in result
        assert "Anthropic tokens high usage" in result
        assert "\x1b" in result  # Has color codes

    def test_format_warnings_handles_empty_list(self):
        """Formatter returns empty string for no warnings."""
        formatter = RateLimitFormatter()
        result = formatter.format_warnings([])

        assert result == ""

    def test_format_tracker_file_location(self):
        """Formatter displays tracker file path."""
        formatter = RateLimitFormatter()
        result = formatter.format_tracker_file_location("/path/to/.llm_rate_limits.json")

        assert "Tracking File" in result
        assert "/path/to/.llm_rate_limits.json" in result


class TestCacheFormatter:
    """Tests for cache statistics formatter."""

    def test_format_stats_displays_header(self):
        """Formatter displays cache statistics header."""
        formatter = CacheFormatter()
        stats = {
            'exact_cache_entries': 10,
            'intent_cache_entries': 5,
            'exact_hits': 8,
            'intent_hits': 3,
            'exact_misses': 2,
            'saves': 15,
            'exact_hit_rate': '80.0%',
            'intent_hit_rate': '60.0%',
            'cache_file': '/path/to/cache.json'
        }

        result = formatter.format_stats(stats, enabled=True)

        assert "Cache Statistics" in result

    def test_format_stats_shows_entry_counts(self):
        """Formatter displays cache entry counts."""
        formatter = CacheFormatter()
        stats = {
            'exact_cache_entries': 12,
            'intent_cache_entries': 8,
            'exact_hits': 10,
            'intent_hits': 5,
            'exact_misses': 5,
            'saves': 20,
            'exact_hit_rate': '66.7%',
            'intent_hit_rate': '50.0%',
            'cache_file': '/path/to/cache.json'
        }

        result = formatter.format_stats(stats, enabled=True)

        assert "Total Entries: 20" in result  # 12 + 8
        assert "Exact Cache Hits: 10" in result
        assert "Intent Cache Hits: 5" in result
        assert "Cache Misses: 5" in result
        assert "Cache Saves: 20" in result

    def test_format_stats_shows_hit_rates(self):
        """Formatter displays hit rates with colors."""
        formatter = CacheFormatter()
        stats = {
            'exact_cache_entries': 10,
            'intent_cache_entries': 5,
            'exact_hits': 8,
            'intent_hits': 3,
            'exact_misses': 2,
            'saves': 15,
            'exact_hit_rate': '80.0%',
            'intent_hit_rate': '60.0%',
            'cache_file': '/path/to/cache.json'
        }

        result = formatter.format_stats(stats, enabled=True)

        assert "Exact Hit Rate" in result
        assert "80.0%" in result
        assert "Intent Hit Rate" in result
        assert "60.0%" in result
        assert "\x1b" in result  # Has color codes

    def test_format_stats_shows_cache_file(self):
        """Formatter displays cache file location."""
        formatter = CacheFormatter()
        stats = {
            'exact_cache_entries': 0,
            'intent_cache_entries': 0,
            'exact_hits': 0,
            'intent_hits': 0,
            'exact_misses': 0,
            'saves': 0,
            'exact_hit_rate': '0.0%',
            'intent_hit_rate': '0.0%',
            'cache_file': '/path/to/.llm_cache.json'
        }

        result = formatter.format_stats(stats, enabled=True)

        assert "Cache File" in result
        assert "/path/to/.llm_cache.json" in result

    def test_format_stats_shows_enabled_status(self):
        """Formatter displays cache enabled status in green."""
        formatter = CacheFormatter()
        stats = {
            'exact_cache_entries': 0,
            'intent_cache_entries': 0,
            'exact_hits': 0,
            'intent_hits': 0,
            'exact_misses': 0,
            'saves': 0,
            'exact_hit_rate': '0.0%',
            'intent_hit_rate': '0.0%',
            'cache_file': '/path/to/cache.json'
        }

        result = formatter.format_stats(stats, enabled=True)

        assert "Caching:" in result
        assert "Enabled" in result
        assert "\x1b" in result  # Has color codes

    def test_format_stats_shows_disabled_status(self):
        """Formatter displays cache disabled status in red."""
        formatter = CacheFormatter()
        stats = {
            'exact_cache_entries': 0,
            'intent_cache_entries': 0,
            'exact_hits': 0,
            'intent_hits': 0,
            'exact_misses': 0,
            'saves': 0,
            'exact_hit_rate': '0.0%',
            'intent_hit_rate': '0.0%',
            'cache_file': '/path/to/cache.json'
        }

        result = formatter.format_stats(stats, enabled=False)

        assert "Caching:" in result
        assert "Disabled" in result
        assert "\x1b" in result  # Has color codes

    def test_format_hit_rate_colors_by_value(self):
        """Formatter colors hit rate based on percentage."""
        formatter = CacheFormatter()

        # High hit rate (> 50%) should be green
        high_rate = formatter.format_hit_rate("75.0%", "Hit Rate")
        assert "75.0%" in high_rate
        assert "\x1b" in high_rate

        # Low hit rate (<= 50%) should be yellow
        low_rate = formatter.format_hit_rate("25.0%", "Hit Rate")
        assert "25.0%" in low_rate
        assert "\x1b" in low_rate

    def test_format_hit_rate_handles_invalid_value(self):
        """Formatter handles invalid hit rate strings gracefully."""
        formatter = CacheFormatter()
        result = formatter.format_hit_rate("N/A", "Hit Rate")

        assert "Hit Rate" in result
        assert "N/A" in result
        # Should not crash

    def test_format_toggle_message_enabled(self):
        """Formatter displays cache enabled message in green."""
        formatter = CacheFormatter()
        result = formatter.format_toggle_message(True)

        assert "enabled" in result
        assert "\x1b" in result  # Has color codes

    def test_format_toggle_message_disabled(self):
        """Formatter displays cache disabled message in yellow."""
        formatter = CacheFormatter()
        result = formatter.format_toggle_message(False)

        assert "disabled" in result
        assert "\x1b" in result  # Has color codes

    def test_format_clear_message(self):
        """Formatter displays cache cleared message."""
        formatter = CacheFormatter()
        result = formatter.format_clear_message()

        assert "cleared" in result
        assert "\x1b" in result  # Has color codes


class TestExtractTimeFromTimestamp:
    """Tests for timestamp extraction utility."""





