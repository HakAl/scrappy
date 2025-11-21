"""
Behavior tests for CLI rate limiter functionality.

Tests actual behavior of rate limit display and management, not implementation details.
Focuses on:
- Timestamp parsing edge cases
- User-facing display output
- Reset confirmation workflows
- Error handling
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.cli.rate_limiter import RateLimiter
from src.infrastructure.formatters.rate_limit_formatter import extract_time_from_timestamp
from tests.helpers import MockIO


class TestTimestampParsing:
    """Test timestamp parsing handles various ISO 8601 formats correctly."""











class TestRateLimiterDisplay:
    """Test rate limiter displays usage data correctly."""

    def test_shows_no_data_message_when_no_usage_exists(self):
        """Should display helpful message when no tracking data exists."""
        orchestrator = MagicMock()
        orchestrator.get_rate_limit_status.return_value = {
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {}
        }
        orchestrator.context.project_path = Path('/test')

        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits("", io=io)

        output = io.get_output()
        assert "No usage data recorded yet" in output
        assert "Rate limits will be tracked" in output
        assert ".llm_rate_limits.json" in output

    def test_displays_provider_usage_data(self):
        """Should show requests and tokens for providers."""
        orchestrator = MagicMock()
        orchestrator.get_rate_limit_status.return_value = {
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 100,
                    'total_tokens_today': 50000,
                    'total_requests_month': 500,
                    'by_model': {}
                }
            }
        }
        orchestrator.check_rate_limit_warnings.return_value = []
        orchestrator.context.project_path = Path('/test')

        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits("", io=io)

        output = io.get_output()
        assert "OPENAI" in output
        assert "100 requests" in output
        assert "50,000 tokens" in output

    def test_filters_display_by_provider_name(self):
        """Should show only specified provider when filtered."""
        orchestrator = MagicMock()
        orchestrator.get_rate_limit_status.return_value = {
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {
                'openai': {'total_requests_today': 100, 'total_tokens_today': 1000, 'total_requests_month': 200, 'by_model': {}},
                'anthropic': {'total_requests_today': 50, 'total_tokens_today': 500, 'total_requests_month': 100, 'by_model': {}}
            }
        }
        orchestrator.check_rate_limit_warnings.return_value = []
        orchestrator.context.project_path = Path('/test')

        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits("openai", io=io)

        output = io.get_output()
        assert "OPENAI" in output
        assert "ANTHROPIC" not in output

    def test_shows_warning_when_provider_filter_not_found(self):
        """Should warn user when filtered provider doesn't exist."""
        orchestrator = MagicMock()
        orchestrator.get_rate_limit_status.return_value = {
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {'openai': {'total_requests_today': 1, 'total_tokens_today': 1, 'total_requests_month': 1, 'by_model': {}}}
        }

        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits("nonexistent", io=io)

        output = io.get_output()
        assert "not found" in output.lower()

    def test_displays_warnings_when_approaching_limits(self):
        """Should prominently display warnings for high usage."""
        orchestrator = MagicMock()
        orchestrator.get_rate_limit_status.return_value = {
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {
                'openai': {'total_requests_today': 1, 'total_tokens_today': 1, 'total_requests_month': 1, 'by_model': {}}
            }
        }
        orchestrator.check_rate_limit_warnings.return_value = [
            "OpenAI: 90% of daily requests used",
            "Anthropic: Approaching token limit"
        ]
        orchestrator.context.project_path = Path('/test')

        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits("", io=io)

        output = io.get_output()
        assert "WARNINGS" in output
        assert "90%" in output


class TestRateLimiterReset:
    """Test rate limit reset functionality with confirmation."""

    def test_resets_all_tracking_when_confirmed(self):
        """Should reset all data when user confirms."""
        orchestrator = MagicMock()
        limiter = RateLimiter(orchestrator)
        io = MockIO(confirmations=[True])

        limiter.show_rate_limits("reset", io=io)

        orchestrator.reset_rate_tracking.assert_called_once_with()
        output = io.get_output()
        assert "reset" in output.lower()


    def test_resets_specific_provider_when_confirmed(self):
        """Should reset only specified provider when confirmed."""
        orchestrator = MagicMock()
        limiter = RateLimiter(orchestrator)
        io = MockIO(confirmations=[True])

        limiter.show_rate_limits("reset openai", io=io)

        orchestrator.reset_rate_tracking.assert_called_once_with("openai")
        output = io.get_output()
        assert "openai" in output.lower()
        assert "reset" in output.lower()


class TestRateLimiterQuotaDisplay:
    """Test quota percentage display with color coding."""

    def test_shows_green_for_low_usage(self):
        """Should use green color for < 75% usage."""
        orchestrator = MagicMock()
        orchestrator.get_rate_limit_status.return_value = {
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 50,
                    'total_tokens_today': 25000,
                    'total_requests_month': 200,
                    'limits': {'requests_per_day': 100},
                    'remaining': {'usage_today': 50, 'requests_remaining_today': 50},
                    'by_model': {}
                }
            }
        }
        orchestrator.check_rate_limit_warnings.return_value = []
        orchestrator.context.project_path = Path('/test')

        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits("", io=io)

        # Check that percentage is shown with green ANSI code
        # ANSI green code is \x1b[32m
        output = io.get_output()
        assert '50.0%' in output  # 50/100 = 50%
        assert '\x1b[32m' in output  # Contains green color code

    def test_shows_red_for_high_usage(self):
        """Should use red color for >= 90% usage."""
        orchestrator = MagicMock()
        orchestrator.get_rate_limit_status.return_value = {
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 950,
                    'total_tokens_today': 95000,
                    'total_requests_month': 500,
                    'limits': {'requests_per_day': 1000},
                    'remaining': {'usage_today': 950, 'requests_remaining_today': 50},
                    'by_model': {}
                }
            }
        }
        orchestrator.check_rate_limit_warnings.return_value = []
        orchestrator.context.project_path = Path('/test')

        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits("", io=io)

        # Check for red ANSI code on high percentage (>= 90%)
        # ANSI red code is \x1b[31m
        output = io.get_output()
        assert '95.0%' in output  # 950/1000 = 95%
        assert '\x1b[31m' in output  # Contains red color code


class TestRateLimiterModelBreakdown:
    """Test per-model usage breakdown display."""

    def test_shows_per_model_usage_when_available(self):
        """Should display usage broken down by model."""
        orchestrator = MagicMock()
        orchestrator.get_rate_limit_status.return_value = {
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 100,
                    'total_tokens_today': 50000,
                    'total_requests_month': 500,
                    'by_model': {
                        'gpt-4': {
                            'requests_today': 50,
                            'tokens_today': 30000,
                            'last_request': '2024-01-01T12:30:00'
                        },
                        'gpt-3.5-turbo': {
                            'requests_today': 50,
                            'tokens_today': 20000,
                            'last_request': '2024-01-01T12:45:00'
                        }
                    }
                }
            }
        }
        orchestrator.check_rate_limit_warnings.return_value = []
        orchestrator.context.project_path = Path('/test')

        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits("", io=io)

        output = io.get_output()
        assert "gpt-4" in output
        assert "gpt-3.5-turbo" in output
        assert "12:30:00" in output  # Parsed timestamp
        assert "12:45:00" in output

    def test_shows_never_for_models_with_no_requests(self):
        """Should show 'never' for models that haven't been used."""
        orchestrator = MagicMock()
        orchestrator.get_rate_limit_status.return_value = {
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 0,
                    'total_tokens_today': 0,
                    'total_requests_month': 0,
                    'by_model': {
                        'gpt-4': {
                            'requests_today': 0,
                            'tokens_today': 0,
                            'last_request': 'never'
                        }
                    }
                }
            }
        }
        orchestrator.check_rate_limit_warnings.return_value = []
        orchestrator.context.project_path = Path('/test')

        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits("", io=io)

        output = io.get_output()
        assert "never" in output.lower()
