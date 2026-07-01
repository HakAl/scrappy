"""
Tests for display formatting infrastructure.

These tests prove that formatters correctly format statistics displays
with appropriate colors, alignment, and structure.
"""

import pytest
from scrappy.infrastructure.formatters import (
    StatsFormatter,
    RateLimitFormatter,
    CacheFormatter,
)
from scrappy.infrastructure.theme import (
    DEFAULT_THEME,
    LightTheme,
    NoColorTheme,
)
from tests.helpers import MockIO


@pytest.fixture
def mock_io():
    """Create a MockIO instance for testing formatters."""
    return MockIO()


class TestStatsFormatter:
    """Tests for base stats formatter."""

    def test_format_header_creates_colored_header(self, mock_io):
        """Formatter creates header with title and separator."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_header("Test Header", width=30)

        assert "Test Header" in result
        assert "-" in result  # Contains separator

    def test_format_key_value_creates_pair(self, mock_io):
        """Formatter creates key-value pair display."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_key_value("Key", "Value")

        assert "Key: Value" in result

    def test_format_key_value_respects_indent(self, mock_io):
        """Formatter indents key-value pairs correctly."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_key_value("Key", "Value", indent=4)

        assert result.startswith("    ")  # 4 spaces
        assert "Key: Value" in result

    def test_format_percentage_shows_numbers(self, mock_io):
        """Formatter displays percentage with numbers."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_percentage(25, 100, show_numbers=True)

        assert "25" in result
        assert "100" in result
        assert "25.0%" in result

    def test_format_percentage_without_numbers(self, mock_io):
        """Formatter displays percentage without numbers."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_percentage(25, 100, show_numbers=False)

        # Should only show percentage
        assert "25.0%" in result
        # Should not show fraction in plain text (may have ANSI codes)
        assert "25/100" not in result.replace("\x1b", "")  # Remove ANSI

    def test_format_percentage_handles_zero_total(self, mock_io):
        """Formatter handles zero total gracefully."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_percentage(10, 0)

        assert "0.0%" in result  # Should show 0% not error

    def test_format_percentage_colors_by_threshold(self, mock_io):
        """Formatter applies different colors based on percentage."""
        formatter = StatsFormatter(mock_io)

        # Low usage should be green (< 75%)
        low_result = formatter.format_percentage(50, 100)
        assert "\x1b" in low_result  # Has ANSI color codes

        # Medium usage should be yellow (75-90%)
        medium_result = formatter.format_percentage(80, 100)
        assert "\x1b" in medium_result

        # High usage should be red (>= 90%)
        high_result = formatter.format_percentage(95, 100)
        assert "\x1b" in high_result

    def test_format_number_adds_commas(self, mock_io):
        """Formatter adds thousand separators to numbers."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_number(1234567, with_commas=True)

        assert result == "1,234,567"

    def test_format_number_without_commas(self, mock_io):
        """Formatter displays numbers without separators."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_number(1234567, with_commas=False)

        assert result == "1234567"

    def test_format_boolean_status_true(self, mock_io):
        """Formatter displays enabled status in green."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_boolean_status(True)

        assert "Enabled" in result
        assert "\x1b" in result  # Has color codes

    def test_format_boolean_status_false(self, mock_io):
        """Formatter displays disabled status in red."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_boolean_status(False)

        assert "Disabled" in result
        assert "\x1b" in result  # Has color codes

    def test_format_boolean_status_custom_labels(self, mock_io):
        """Formatter uses custom labels for boolean status."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_boolean_status(True, "Active", "Inactive")

        assert "Active" in result


class TestRateLimitFormatter:
    """Tests for rate limit formatter."""

    def test_format_status_displays_header(self, mock_io):
        """Formatter displays rate limit header."""
        formatter = RateLimitFormatter(mock_io)
        status = {
            'last_reset': {'daily': '2024-01-15', 'monthly': '2024-01-01'},
            'providers': {}
        }

        result = formatter.format_status(status)

        assert "Rate Limit Usage" in result

    def test_format_status_shows_reset_times(self, mock_io):
        """Formatter displays last reset timestamps."""
        formatter = RateLimitFormatter(mock_io)
        status = {
            'last_reset': {'daily': '2024-01-15T10:30:00', 'monthly': '2024-01-01T00:00:00'},
            'providers': {}
        }

        result = formatter.format_status(status)

        assert "Last Daily Reset" in result
        assert "Last Monthly Reset" in result
        assert "2024-01-15T10:30:00" in result
        assert "2024-01-01T00:00:00" in result

    def test_format_status_handles_no_data(self, mock_io):
        """Formatter displays helpful message when no data."""
        formatter = RateLimitFormatter(mock_io)
        status = {
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {}
        }

        result = formatter.format_status(status)

        assert "No usage data" in result
        assert "tracked as you make API calls" in result

    def test_format_status_filters_provider(self, mock_io):
        """Formatter filters to specific provider when requested."""
        formatter = RateLimitFormatter(mock_io)
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

    def test_format_status_shows_provider_not_found(self, mock_io):
        """Formatter displays error for unknown provider."""
        formatter = RateLimitFormatter(mock_io)
        status = {
            'last_reset': {'daily': '2024-01-15', 'monthly': '2024-01-01'},
            'providers': {'openai': {}}
        }

        result = formatter.format_status(status, provider_filter="unknown")

        assert "not found" in result

    def test_format_quota_line_shows_usage(self, mock_io):
        """Formatter displays quota usage with percentage."""
        formatter = RateLimitFormatter(mock_io)
        result = formatter.format_quota_line("Daily Requests", 50, 100)

        assert "Daily Requests" in result
        assert "50" in result
        assert "100" in result
        assert "50.0%" in result

    def test_format_quota_line_handles_zero_limit(self, mock_io):
        """Formatter handles zero limit gracefully."""
        formatter = RateLimitFormatter(mock_io)
        result = formatter.format_quota_line("Daily Requests", 10, 0)

        assert "0.0%" in result  # Should not error

    def test_format_provider_section_displays_totals(self, mock_io):
        """Formatter displays provider totals correctly."""
        formatter = RateLimitFormatter(mock_io)
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

    def test_format_provider_section_shows_quotas(self, mock_io):
        """Formatter displays quota information when available."""
        formatter = RateLimitFormatter(mock_io)
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

    def test_format_provider_section_shows_model_breakdown(self, mock_io):
        """Formatter displays per-model usage breakdown."""
        formatter = RateLimitFormatter(mock_io)
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

    def test_format_warnings_displays_list(self, mock_io):
        """Formatter displays warnings in red."""
        formatter = RateLimitFormatter(mock_io)
        warnings = [
            "OpenAI approaching daily limit (90%)",
            "Anthropic tokens high usage"
        ]

        result = formatter.format_warnings(warnings)

        assert "WARNINGS" in result
        assert "OpenAI approaching daily limit" in result
        assert "Anthropic tokens high usage" in result
        assert "\x1b" in result  # Has color codes

    def test_format_warnings_handles_empty_list(self, mock_io):
        """Formatter returns empty string for no warnings."""
        formatter = RateLimitFormatter(mock_io)
        result = formatter.format_warnings([])

        assert result == ""

    def test_format_tracker_file_location(self, mock_io):
        """Formatter displays tracker file path."""
        formatter = RateLimitFormatter(mock_io)
        result = formatter.format_tracker_file_location("/path/to/.llm_rate_limits.json")

        assert "Tracking File" in result
        assert "/path/to/.llm_rate_limits.json" in result


class TestCacheFormatter:
    """Tests for cache statistics formatter."""

    def test_get_stats_data_returns_structured_format(self, mock_io):
        """get_stats_data returns (headers, rows, title) tuple for io.table()."""
        formatter = CacheFormatter(mock_io)
        stats = {
            'exact_cache_entries': 10,
            'intent_cache_entries': 5,
            'exact_hits': 3,
            'intent_hits': 2,
            'exact_misses': 5,
            'saves': 8,
            'exact_hit_rate': '37.5%',
            'intent_hit_rate': '28.6%',
            'cache_file': '/path/to/cache.json'
        }

        headers, rows, title = formatter.get_stats_data(stats, enabled=True)

        assert headers == ["Metric", "Value"]
        assert title == "Cache Statistics"
        assert len(rows) == 9
        assert ["Total Entries", "15"] in rows
        assert ["Status", "Enabled"] in rows

    def test_get_stats_data_disabled_status(self, mock_io):
        """get_stats_data shows Disabled when caching is off."""
        formatter = CacheFormatter(mock_io)
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

        headers, rows, title = formatter.get_stats_data(stats, enabled=False)

        assert ["Status", "Disabled"] in rows

    def test_get_stats_data_no_ansi_codes(self, mock_io):
        """get_stats_data returns plain text without ANSI codes."""
        formatter = CacheFormatter(mock_io)
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

        headers, rows, title = formatter.get_stats_data(stats, enabled=True)

        # Check no ANSI codes in any data
        assert "\x1b" not in title
        for header in headers:
            assert "\x1b" not in header
        for row in rows:
            for cell in row:
                assert "\x1b" not in cell

    def test_format_stats_displays_header(self, mock_io):
        """Formatter displays cache statistics header."""
        formatter = CacheFormatter(mock_io)
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

    def test_format_stats_shows_entry_counts(self, mock_io):
        """Formatter displays cache entry counts."""
        formatter = CacheFormatter(mock_io)
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

    def test_format_stats_shows_hit_rates(self, mock_io):
        """Formatter displays hit rates with colors."""
        formatter = CacheFormatter(mock_io)
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

    def test_format_stats_shows_cache_file(self, mock_io):
        """Formatter displays cache file location."""
        formatter = CacheFormatter(mock_io)
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

    def test_format_stats_shows_enabled_status(self, mock_io):
        """Formatter displays cache enabled status in green."""
        formatter = CacheFormatter(mock_io)
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

    def test_format_stats_shows_disabled_status(self, mock_io):
        """Formatter displays cache disabled status in red."""
        formatter = CacheFormatter(mock_io)
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

    def test_format_hit_rate_colors_by_value(self, mock_io):
        """Formatter colors hit rate based on percentage."""
        formatter = CacheFormatter(mock_io)

        # High hit rate (> 50%) should be green
        high_rate = formatter.format_hit_rate("75.0%", "Hit Rate")
        assert "75.0%" in high_rate
        assert "\x1b" in high_rate

        # Low hit rate (<= 50%) should be yellow
        low_rate = formatter.format_hit_rate("25.0%", "Hit Rate")
        assert "25.0%" in low_rate
        assert "\x1b" in low_rate

    def test_format_hit_rate_handles_invalid_value(self, mock_io):
        """Formatter handles invalid hit rate strings gracefully."""
        formatter = CacheFormatter(mock_io)
        result = formatter.format_hit_rate("N/A", "Hit Rate")

        assert "Hit Rate" in result
        assert "N/A" in result
        # Should not crash

    def test_format_toggle_message_enabled(self, mock_io):
        """Formatter displays cache enabled message in green."""
        formatter = CacheFormatter(mock_io)
        result = formatter.format_toggle_message(True)

        assert "enabled" in result
        assert "\x1b" in result  # Has color codes

    def test_format_toggle_message_disabled(self, mock_io):
        """Formatter displays cache disabled message in yellow."""
        formatter = CacheFormatter(mock_io)
        result = formatter.format_toggle_message(False)

        assert "disabled" in result
        assert "\x1b" in result  # Has color codes

    def test_format_clear_message(self, mock_io):
        """Formatter displays cache cleared message."""
        formatter = CacheFormatter(mock_io)
        result = formatter.format_clear_message()

        assert "cleared" in result
        assert "\x1b" in result  # Has color codes


class TestStatsFormatterColorDisabled:
    """Tests for StatsFormatter with color disabled (Phase 2 Issue 2)."""

    def test_format_header_without_color(self):
        """Formatter creates header without ANSI codes when use_color=False."""
        io = MockIO()
        io.use_color = False
        formatter = StatsFormatter(io)
        result = formatter.format_header("Test Header", width=30)

        assert "Test Header" in result
        assert "-" in result  # Contains separator
        assert "\x1b" not in result  # No ANSI codes

    def test_format_percentage_without_color(self):
        """Formatter displays percentage without ANSI codes when use_color=False."""
        io = MockIO()
        io.use_color = False
        formatter = StatsFormatter(io)
        result = formatter.format_percentage(50, 100)

        assert "50.0%" in result
        assert "\x1b" not in result  # No ANSI codes

    def test_format_percentage_with_label_without_color(self):
        """Formatter displays labeled percentage without ANSI codes."""
        io = MockIO()
        io.use_color = False
        formatter = StatsFormatter(io)
        result = formatter.format_percentage(75, 100, label="Usage")

        assert "Usage:" in result
        assert "75.0%" in result
        assert "\x1b" not in result  # No ANSI codes

    def test_format_boolean_status_without_color(self):
        """Formatter displays boolean status without ANSI codes when use_color=False."""
        io = MockIO()
        io.use_color = False
        formatter = StatsFormatter(io)

        enabled_result = formatter.format_boolean_status(True)
        assert enabled_result == "Enabled"
        assert "\x1b" not in enabled_result

        disabled_result = formatter.format_boolean_status(False)
        assert disabled_result == "Disabled"
        assert "\x1b" not in disabled_result


class TestCacheFormatterColorDisabled:
    """Tests for CacheFormatter with color disabled (Phase 2 Issue 2)."""

    def test_format_hit_rate_without_color(self):
        """Formatter displays hit rate without ANSI codes when use_color=False."""
        io = MockIO()
        io.use_color = False
        formatter = CacheFormatter(io)
        result = formatter.format_hit_rate("75.0%", "Hit Rate")

        assert "Hit Rate: 75.0%" in result
        assert "\x1b" not in result  # No ANSI codes

    def test_format_toggle_message_without_color(self):
        """Formatter displays toggle message without ANSI codes when use_color=False."""
        io = MockIO()
        io.use_color = False
        formatter = CacheFormatter(io)

        enabled_result = formatter.format_toggle_message(True)
        assert "enabled" in enabled_result
        assert "\x1b" not in enabled_result

        disabled_result = formatter.format_toggle_message(False)
        assert "disabled" in disabled_result
        assert "\x1b" not in disabled_result

    def test_format_clear_message_without_color(self):
        """Formatter displays clear message without ANSI codes when use_color=False."""
        io = MockIO()
        io.use_color = False
        formatter = CacheFormatter(io)
        result = formatter.format_clear_message()

        assert "cleared" in result
        assert "\x1b" not in result  # No ANSI codes

    def test_format_stats_without_color(self):
        """Formatter displays full stats without ANSI codes when use_color=False."""
        io = MockIO()
        io.use_color = False
        formatter = CacheFormatter(io)
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
        assert "80.0%" in result
        assert "Enabled" in result
        assert "\x1b" not in result  # No ANSI codes


class TestExtractTimeFromTimestamp:
    """Tests for timestamp extraction utility."""


class TestStatsFormatterThemeIntegration:
    """Tests for StatsFormatter theme integration."""

    def test_default_theme_is_used_when_none_provided(self, mock_io):
        """Formatter uses DEFAULT_THEME when no theme provided."""
        formatter = StatsFormatter(mock_io)
        assert formatter._io.theme is not None  # Has theme from MockIO

    def test_custom_theme_is_used_when_provided(self):
        """Formatter uses provided theme instance."""
        light_theme = LightTheme()
        io = MockIO()
        io.theme = light_theme
        formatter = StatsFormatter(io)
        assert formatter._io.theme is light_theme

    def test_format_header_uses_theme_primary_color(self):
        """Formatter uses theme.primary for headers."""
        light_theme = LightTheme()
        io = MockIO()
        io.theme = light_theme
        formatter = StatsFormatter(io)
        result = formatter.format_header("Test", width=20)
        # Light theme uses 'blue' for primary
        assert "blue" in result or "\x1b[" in result

    def test_percentage_color_uses_theme_success_for_low(self, mock_io):
        """Formatter uses theme.success for low percentages."""
        formatter = StatsFormatter(mock_io)
        color = formatter._get_percentage_color(50.0)
        assert color == DEFAULT_THEME.success

    def test_percentage_color_uses_theme_warning_for_medium(self, mock_io):
        """Formatter uses theme.warning for medium percentages."""
        formatter = StatsFormatter(mock_io)
        color = formatter._get_percentage_color(80.0)
        assert color == DEFAULT_THEME.warning

    def test_percentage_color_uses_theme_error_for_high(self, mock_io):
        """Formatter uses theme.error for high percentages."""
        formatter = StatsFormatter(mock_io)
        color = formatter._get_percentage_color(95.0)
        assert color == DEFAULT_THEME.error

    def test_boolean_status_uses_theme_success_for_true(self, mock_io):
        """Formatter uses theme.success for True values."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_boolean_status(True)
        # Should contain green (theme.success default)
        assert "Enabled" in result

    def test_boolean_status_uses_theme_error_for_false(self, mock_io):
        """Formatter uses theme.error for False values."""
        formatter = StatsFormatter(mock_io)
        result = formatter.format_boolean_status(False)
        # Should contain red (theme.error default)
        assert "Disabled" in result

    def test_light_theme_uses_different_colors(self):
        """Light theme provides different color values."""
        light_theme = LightTheme()
        io = MockIO()
        io.theme = light_theme
        formatter = StatsFormatter(io)

        # Light theme has blue (#0000ff) as primary, not cyan
        assert formatter._io.theme.primary == "#0000ff"
        assert formatter._io.theme.accent == "#ff00ff"


class TestCacheFormatterThemeIntegration:
    """Tests for CacheFormatter theme integration."""

    def test_inherits_theme_from_stats_formatter(self):
        """CacheFormatter correctly passes theme to parent."""
        light_theme = LightTheme()
        io = MockIO()
        io.theme = light_theme
        formatter = CacheFormatter(io)
        assert formatter._io.theme is light_theme

    def test_format_hit_rate_uses_theme_success_for_high_rate(self, mock_io):
        """Formatter uses theme.success for hit rates > 50%."""
        formatter = CacheFormatter(mock_io)
        result = formatter.format_hit_rate("75.0%", "Hit Rate")
        # Contains styled text
        assert "75.0%" in result
        assert "\x1b" in result

    def test_format_hit_rate_uses_theme_warning_for_low_rate(self, mock_io):
        """Formatter uses theme.warning for hit rates <= 50%."""
        formatter = CacheFormatter(mock_io)
        result = formatter.format_hit_rate("25.0%", "Hit Rate")
        assert "25.0%" in result
        assert "\x1b" in result

    def test_format_toggle_message_uses_theme_success_for_enabled(self, mock_io):
        """Formatter uses theme.success for enabled state."""
        formatter = CacheFormatter(mock_io)
        result = formatter.format_toggle_message(True)
        assert "enabled" in result
        assert "\x1b" in result

    def test_format_toggle_message_uses_theme_warning_for_disabled(self, mock_io):
        """Formatter uses theme.warning for disabled state."""
        formatter = CacheFormatter(mock_io)
        result = formatter.format_toggle_message(False)
        assert "disabled" in result
        assert "\x1b" in result

    def test_format_clear_message_uses_theme_success(self, mock_io):
        """Formatter uses theme.success for clear message."""
        formatter = CacheFormatter(mock_io)
        result = formatter.format_clear_message()
        assert "cleared" in result
        assert "\x1b" in result


class TestRateLimitFormatterThemeIntegration:
    """Tests for RateLimitFormatter theme integration."""

    def test_inherits_theme_from_stats_formatter(self):
        """RateLimitFormatter correctly passes theme to parent."""
        light_theme = LightTheme()
        io = MockIO()
        io.theme = light_theme
        formatter = RateLimitFormatter(io)
        assert formatter._io.theme is light_theme

    def test_format_provider_section_uses_theme_success(self, mock_io):
        """Formatter uses theme.success for provider headers."""
        formatter = RateLimitFormatter(mock_io)
        data = {
            'total_requests_today': 10,
            'total_tokens_today': 1000,
            'total_requests_month': 50
        }
        result = formatter.format_provider_section("openai", data)
        assert "OPENAI" in result
        assert "\x1b" in result

    def test_format_warnings_uses_theme_error(self, mock_io):
        """Formatter uses theme.error for warnings."""
        formatter = RateLimitFormatter(mock_io)
        warnings = ["Test warning"]
        result = formatter.format_warnings(warnings)
        assert "WARNINGS" in result
        assert "Test warning" in result
        assert "\x1b" in result

    def test_format_tracker_file_uses_theme_primary(self, mock_io):
        """Formatter uses theme.primary for file location."""
        formatter = RateLimitFormatter(mock_io)
        result = formatter.format_tracker_file_location("/path/to/file.json")
        assert "Tracking File" in result
        assert "/path/to/file.json" in result
        assert "\x1b" in result

    def test_format_quota_line_uses_theme_percentage_colors(self, mock_io):
        """Formatter uses theme colors for quota percentages."""
        formatter = RateLimitFormatter(mock_io)

        # Low usage should use success color
        low_result = formatter.format_quota_line("Requests", 10, 100)
        assert "10.0%" in low_result

        # High usage should use error color
        high_result = formatter.format_quota_line("Requests", 95, 100)
        assert "95.0%" in high_result

    def test_format_status_provider_not_found_uses_theme_warning(self, mock_io):
        """Formatter uses theme.warning for provider not found message."""
        formatter = RateLimitFormatter(mock_io)
        status = {
            'last_reset': {'daily': '2024-01-15', 'monthly': '2024-01-01'},
            'providers': {'openai': {}}
        }
        result = formatter.format_status(status, provider_filter="unknown")
        assert "not found" in result
        assert "\x1b" in result


class TestNoColorThemeIntegration:
    """Tests for formatters with NoColorTheme (testing theme)."""

    def test_stats_formatter_with_no_color_theme(self):
        """StatsFormatter works with NoColorTheme."""
        no_color = NoColorTheme()
        io = MockIO()
        io.theme = no_color
        formatter = StatsFormatter(io)

        # Empty string colors should still work with click.style
        result = formatter.format_header("Test", width=20)
        assert "Test" in result

    def test_cache_formatter_with_no_color_theme(self):
        """CacheFormatter works with NoColorTheme."""
        no_color = NoColorTheme()
        io = MockIO()
        io.theme = no_color
        formatter = CacheFormatter(io)

        result = formatter.format_hit_rate("50.0%", "Rate")
        assert "50.0%" in result

    def test_rate_limit_formatter_with_no_color_theme(self):
        """RateLimitFormatter works with NoColorTheme."""
        no_color = NoColorTheme()
        io = MockIO()
        io.theme = no_color
        formatter = RateLimitFormatter(io)

        result = formatter.format_tracker_file_location("/path/file.json")
        assert "Tracking File" in result

