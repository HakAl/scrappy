"""
Tests for CLI defaults configuration module.

TDD: Tests written first for the defaults.py module which centralizes
all numeric default values used throughout the CLI. This eliminates
magic numbers scattered across the codebase.
"""

import pytest


class TestDefaultsModuleStructure:
    """Tests for the defaults module structure and exports."""

    def test_module_imports_successfully(self):
        """Module should import without errors."""
        from src.cli.config import defaults
        assert defaults is not None

    def test_module_has_docstring(self):
        """Defaults module should have a module-level docstring."""
        from src.cli.config import defaults
        assert defaults.__doc__ is not None
        assert len(defaults.__doc__) > 0


class TestTemperatureDefaults:
    """Tests for LLM temperature default values."""

    def test_temperature_low_exists(self):
        """TEMPERATURE_LOW should be exported for precise responses."""
        from src.cli.config.defaults import TEMPERATURE_LOW
        assert TEMPERATURE_LOW is not None
        assert isinstance(TEMPERATURE_LOW, (int, float))

    def test_temperature_low_value(self):
        """TEMPERATURE_LOW should be 0.3 for precise responses."""
        from src.cli.config.defaults import TEMPERATURE_LOW
        assert TEMPERATURE_LOW == 0.3

    def test_temperature_default_exists(self):
        """TEMPERATURE_DEFAULT should be exported."""
        from src.cli.config.defaults import TEMPERATURE_DEFAULT
        assert TEMPERATURE_DEFAULT is not None
        assert isinstance(TEMPERATURE_DEFAULT, (int, float))

    def test_temperature_default_value(self):
        """TEMPERATURE_DEFAULT should be 0.7."""
        from src.cli.config.defaults import TEMPERATURE_DEFAULT
        assert TEMPERATURE_DEFAULT == 0.7


class TestTokenLimitDefaults:
    """Tests for max token limit default values."""

    def test_max_tokens_query_exists(self):
        """MAX_TOKENS_QUERY should be exported for CLI queries."""
        from src.cli.config.defaults import MAX_TOKENS_QUERY
        assert MAX_TOKENS_QUERY is not None
        assert isinstance(MAX_TOKENS_QUERY, int)

    def test_max_tokens_query_value(self):
        """MAX_TOKENS_QUERY should be 1000."""
        from src.cli.config.defaults import MAX_TOKENS_QUERY
        assert MAX_TOKENS_QUERY == 1000

    def test_max_tokens_summary_exists(self):
        """MAX_TOKENS_SUMMARY should be exported for file summaries."""
        from src.cli.config.defaults import MAX_TOKENS_SUMMARY
        assert MAX_TOKENS_SUMMARY is not None
        assert isinstance(MAX_TOKENS_SUMMARY, int)

    def test_max_tokens_summary_value(self):
        """MAX_TOKENS_SUMMARY should be 2000."""
        from src.cli.config.defaults import MAX_TOKENS_SUMMARY
        assert MAX_TOKENS_SUMMARY == 2000


class TestLineLimitDefaults:
    """Tests for line/read limit default values."""

    def test_max_lines_config_exists(self):
        """MAX_LINES_CONFIG should be exported for reading config files."""
        from src.cli.config.defaults import MAX_LINES_CONFIG
        assert MAX_LINES_CONFIG is not None
        assert isinstance(MAX_LINES_CONFIG, int)

    def test_max_lines_config_value(self):
        """MAX_LINES_CONFIG should be 100."""
        from src.cli.config.defaults import MAX_LINES_CONFIG
        assert MAX_LINES_CONFIG == 100

    def test_max_lines_dependency_exists(self):
        """MAX_LINES_DEPENDENCY should be exported for reading dependency files."""
        from src.cli.config.defaults import MAX_LINES_DEPENDENCY
        assert MAX_LINES_DEPENDENCY is not None
        assert isinstance(MAX_LINES_DEPENDENCY, int)

    def test_max_lines_dependency_value(self):
        """MAX_LINES_DEPENDENCY should be 50."""
        from src.cli.config.defaults import MAX_LINES_DEPENDENCY
        assert MAX_LINES_DEPENDENCY == 50

    def test_max_test_results_exists(self):
        """MAX_TEST_RESULTS should be exported for test file listing."""
        from src.cli.config.defaults import MAX_TEST_RESULTS
        assert MAX_TEST_RESULTS is not None
        assert isinstance(MAX_TEST_RESULTS, int)

    def test_max_test_results_value(self):
        """MAX_TEST_RESULTS should be 20."""
        from src.cli.config.defaults import MAX_TEST_RESULTS
        assert MAX_TEST_RESULTS == 20


class TestTruncationDefaults:
    """Tests for content truncation threshold default values."""

    def test_truncate_priority_file_exists(self):
        """TRUNCATE_PRIORITY_FILE should be exported."""
        from src.cli.config.defaults import TRUNCATE_PRIORITY_FILE
        assert TRUNCATE_PRIORITY_FILE is not None
        assert isinstance(TRUNCATE_PRIORITY_FILE, int)

    def test_truncate_priority_file_value(self):
        """TRUNCATE_PRIORITY_FILE should be 3000."""
        from src.cli.config.defaults import TRUNCATE_PRIORITY_FILE
        assert TRUNCATE_PRIORITY_FILE == 3000

    def test_truncate_file_content_exists(self):
        """TRUNCATE_FILE_CONTENT should be exported."""
        from src.cli.config.defaults import TRUNCATE_FILE_CONTENT
        assert TRUNCATE_FILE_CONTENT is not None
        assert isinstance(TRUNCATE_FILE_CONTENT, int)

    def test_truncate_file_content_value(self):
        """TRUNCATE_FILE_CONTENT should be 2000."""
        from src.cli.config.defaults import TRUNCATE_FILE_CONTENT
        assert TRUNCATE_FILE_CONTENT == 2000

    def test_truncate_research_large_exists(self):
        """TRUNCATE_RESEARCH_LARGE should be exported."""
        from src.cli.config.defaults import TRUNCATE_RESEARCH_LARGE
        assert TRUNCATE_RESEARCH_LARGE is not None
        assert isinstance(TRUNCATE_RESEARCH_LARGE, int)

    def test_truncate_research_large_value(self):
        """TRUNCATE_RESEARCH_LARGE should be 1500."""
        from src.cli.config.defaults import TRUNCATE_RESEARCH_LARGE
        assert TRUNCATE_RESEARCH_LARGE == 1500

    def test_truncate_research_medium_exists(self):
        """TRUNCATE_RESEARCH_MEDIUM should be exported."""
        from src.cli.config.defaults import TRUNCATE_RESEARCH_MEDIUM
        assert TRUNCATE_RESEARCH_MEDIUM is not None
        assert isinstance(TRUNCATE_RESEARCH_MEDIUM, int)

    def test_truncate_research_medium_value(self):
        """TRUNCATE_RESEARCH_MEDIUM should be 1000."""
        from src.cli.config.defaults import TRUNCATE_RESEARCH_MEDIUM
        assert TRUNCATE_RESEARCH_MEDIUM == 1000

    def test_truncate_error_message_exists(self):
        """TRUNCATE_ERROR_MESSAGE should be exported."""
        from src.cli.config.defaults import TRUNCATE_ERROR_MESSAGE
        assert TRUNCATE_ERROR_MESSAGE is not None
        assert isinstance(TRUNCATE_ERROR_MESSAGE, int)

    def test_truncate_error_message_value(self):
        """TRUNCATE_ERROR_MESSAGE should be 500."""
        from src.cli.config.defaults import TRUNCATE_ERROR_MESSAGE
        assert TRUNCATE_ERROR_MESSAGE == 500


class TestPreviewLengthDefaults:
    """Tests for string preview truncation default values."""

    def test_preview_standard_exists(self):
        """PREVIEW_STANDARD should be exported."""
        from src.cli.config.defaults import PREVIEW_STANDARD
        assert PREVIEW_STANDARD is not None
        assert isinstance(PREVIEW_STANDARD, int)

    def test_preview_standard_value(self):
        """PREVIEW_STANDARD should be 50."""
        from src.cli.config.defaults import PREVIEW_STANDARD
        assert PREVIEW_STANDARD == 50

    def test_preview_short_exists(self):
        """PREVIEW_SHORT should be exported."""
        from src.cli.config.defaults import PREVIEW_SHORT
        assert PREVIEW_SHORT is not None
        assert isinstance(PREVIEW_SHORT, int)

    def test_preview_short_value(self):
        """PREVIEW_SHORT should be 40."""
        from src.cli.config.defaults import PREVIEW_SHORT
        assert PREVIEW_SHORT == 40

    def test_preview_conclusion_exists(self):
        """PREVIEW_CONCLUSION should be exported."""
        from src.cli.config.defaults import PREVIEW_CONCLUSION
        assert PREVIEW_CONCLUSION is not None
        assert isinstance(PREVIEW_CONCLUSION, int)

    def test_preview_conclusion_value(self):
        """PREVIEW_CONCLUSION should be 200."""
        from src.cli.config.defaults import PREVIEW_CONCLUSION
        assert PREVIEW_CONCLUSION == 200


class TestRateLimitThresholds:
    """Tests for rate limit warning threshold default values."""

    def test_rate_limit_warning_exists(self):
        """RATE_LIMIT_WARNING should be exported (75% threshold)."""
        from src.cli.config.defaults import RATE_LIMIT_WARNING
        assert RATE_LIMIT_WARNING is not None
        assert isinstance(RATE_LIMIT_WARNING, (int, float))

    def test_rate_limit_warning_value(self):
        """RATE_LIMIT_WARNING should be 0.75 (75%)."""
        from src.cli.config.defaults import RATE_LIMIT_WARNING
        assert RATE_LIMIT_WARNING == 0.75

    def test_rate_limit_critical_exists(self):
        """RATE_LIMIT_CRITICAL should be exported (90% threshold)."""
        from src.cli.config.defaults import RATE_LIMIT_CRITICAL
        assert RATE_LIMIT_CRITICAL is not None
        assert isinstance(RATE_LIMIT_CRITICAL, (int, float))

    def test_rate_limit_critical_value(self):
        """RATE_LIMIT_CRITICAL should be 0.90 (90%)."""
        from src.cli.config.defaults import RATE_LIMIT_CRITICAL
        assert RATE_LIMIT_CRITICAL == 0.90

    def test_cache_hit_good_exists(self):
        """CACHE_HIT_GOOD should be exported (50% threshold)."""
        from src.cli.config.defaults import CACHE_HIT_GOOD
        assert CACHE_HIT_GOOD is not None
        assert isinstance(CACHE_HIT_GOOD, (int, float))

    def test_cache_hit_good_value(self):
        """CACHE_HIT_GOOD should be 0.50 (50%)."""
        from src.cli.config.defaults import CACHE_HIT_GOOD
        assert CACHE_HIT_GOOD == 0.50


class TestDisplayDefaults:
    """Tests for display-related default values."""

    def test_progress_bar_width_exists(self):
        """PROGRESS_BAR_WIDTH should be exported."""
        from src.cli.config.defaults import PROGRESS_BAR_WIDTH
        assert PROGRESS_BAR_WIDTH is not None
        assert isinstance(PROGRESS_BAR_WIDTH, int)

    def test_progress_bar_width_value(self):
        """PROGRESS_BAR_WIDTH should be 20."""
        from src.cli.config.defaults import PROGRESS_BAR_WIDTH
        assert PROGRESS_BAR_WIDTH == 20

    def test_max_display_messages_exists(self):
        """MAX_DISPLAY_MESSAGES should be exported."""
        from src.cli.config.defaults import MAX_DISPLAY_MESSAGES
        assert MAX_DISPLAY_MESSAGES is not None
        assert isinstance(MAX_DISPLAY_MESSAGES, int)

    def test_max_display_messages_value(self):
        """MAX_DISPLAY_MESSAGES should be 4."""
        from src.cli.config.defaults import MAX_DISPLAY_MESSAGES
        assert MAX_DISPLAY_MESSAGES == 4

    def test_separator_width_standard_exists(self):
        """SEPARATOR_WIDTH_STANDARD should be exported."""
        from src.cli.config.defaults import SEPARATOR_WIDTH_STANDARD
        assert SEPARATOR_WIDTH_STANDARD is not None
        assert isinstance(SEPARATOR_WIDTH_STANDARD, int)

    def test_separator_width_standard_value(self):
        """SEPARATOR_WIDTH_STANDARD should be 50."""
        from src.cli.config.defaults import SEPARATOR_WIDTH_STANDARD
        assert SEPARATOR_WIDTH_STANDARD == 50

    def test_separator_width_wide_exists(self):
        """SEPARATOR_WIDTH_WIDE should be exported."""
        from src.cli.config.defaults import SEPARATOR_WIDTH_WIDE
        assert SEPARATOR_WIDTH_WIDE is not None
        assert isinstance(SEPARATOR_WIDTH_WIDE, int)

    def test_separator_width_wide_value(self):
        """SEPARATOR_WIDTH_WIDE should be 60."""
        from src.cli.config.defaults import SEPARATOR_WIDTH_WIDE
        assert SEPARATOR_WIDTH_WIDE == 60

    def test_separator_width_narrow_exists(self):
        """SEPARATOR_WIDTH_NARROW should be exported."""
        from src.cli.config.defaults import SEPARATOR_WIDTH_NARROW
        assert SEPARATOR_WIDTH_NARROW is not None
        assert isinstance(SEPARATOR_WIDTH_NARROW, int)

    def test_separator_width_narrow_value(self):
        """SEPARATOR_WIDTH_NARROW should be 40."""
        from src.cli.config.defaults import SEPARATOR_WIDTH_NARROW
        assert SEPARATOR_WIDTH_NARROW == 40


class TestCommandDefaults:
    """Tests for command-related default values."""

    def test_max_iterations_exists(self):
        """MAX_ITERATIONS should be exported."""
        from src.cli.config.defaults import MAX_ITERATIONS
        assert MAX_ITERATIONS is not None
        assert isinstance(MAX_ITERATIONS, int)

    def test_max_iterations_value(self):
        """MAX_ITERATIONS should be 10."""
        from src.cli.config.defaults import MAX_ITERATIONS
        assert MAX_ITERATIONS == 10


class TestDefaultsValueRanges:
    """Tests to verify defaults are within reasonable ranges."""

    def test_temperature_values_valid(self):
        """Temperature values should be between 0 and 1."""
        from src.cli.config.defaults import TEMPERATURE_LOW, TEMPERATURE_DEFAULT
        assert 0 <= TEMPERATURE_LOW <= 1
        assert 0 <= TEMPERATURE_DEFAULT <= 1

    def test_token_limits_positive(self):
        """Token limits should be positive integers."""
        from src.cli.config.defaults import MAX_TOKENS_QUERY, MAX_TOKENS_SUMMARY
        assert MAX_TOKENS_QUERY > 0
        assert MAX_TOKENS_SUMMARY > 0

    def test_truncation_thresholds_ordered(self):
        """Truncation thresholds should follow logical order."""
        from src.cli.config.defaults import (
            TRUNCATE_ERROR_MESSAGE,
            TRUNCATE_RESEARCH_MEDIUM,
            TRUNCATE_RESEARCH_LARGE,
            TRUNCATE_FILE_CONTENT,
            TRUNCATE_PRIORITY_FILE
        )
        # Larger contexts get higher limits
        assert TRUNCATE_ERROR_MESSAGE < TRUNCATE_RESEARCH_MEDIUM
        assert TRUNCATE_RESEARCH_MEDIUM < TRUNCATE_RESEARCH_LARGE
        assert TRUNCATE_RESEARCH_LARGE < TRUNCATE_FILE_CONTENT
        assert TRUNCATE_FILE_CONTENT < TRUNCATE_PRIORITY_FILE

    def test_rate_limit_thresholds_ordered(self):
        """Rate limit thresholds should be in logical order."""
        from src.cli.config.defaults import RATE_LIMIT_WARNING, RATE_LIMIT_CRITICAL
        assert RATE_LIMIT_WARNING < RATE_LIMIT_CRITICAL

    def test_separator_widths_ordered(self):
        """Separator widths should be in logical order."""
        from src.cli.config.defaults import (
            SEPARATOR_WIDTH_NARROW,
            SEPARATOR_WIDTH_STANDARD,
            SEPARATOR_WIDTH_WIDE
        )
        assert SEPARATOR_WIDTH_NARROW < SEPARATOR_WIDTH_STANDARD
        assert SEPARATOR_WIDTH_STANDARD < SEPARATOR_WIDTH_WIDE


class TestAllDefaultsExport:
    """Tests for convenient exports."""

    def test_all_temperatures_dict_exists(self):
        """TEMPERATURES dict should provide all temperature values."""
        from src.cli.config.defaults import TEMPERATURES
        assert TEMPERATURES is not None
        assert isinstance(TEMPERATURES, dict)
        assert 'low' in TEMPERATURES
        assert 'default' in TEMPERATURES

    def test_all_truncation_dict_exists(self):
        """TRUNCATION_LIMITS dict should provide all truncation values."""
        from src.cli.config.defaults import TRUNCATION_LIMITS
        assert TRUNCATION_LIMITS is not None
        assert isinstance(TRUNCATION_LIMITS, dict)

    def test_all_separator_widths_dict_exists(self):
        """SEPARATOR_WIDTHS dict should provide all separator widths."""
        from src.cli.config.defaults import SEPARATOR_WIDTHS
        assert SEPARATOR_WIDTHS is not None
        assert isinstance(SEPARATOR_WIDTHS, dict)
        assert 'narrow' in SEPARATOR_WIDTHS
        assert 'standard' in SEPARATOR_WIDTHS
        assert 'wide' in SEPARATOR_WIDTHS
