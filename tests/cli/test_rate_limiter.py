"""
Tests for rate_limiter.py - Rate limit tracking split from session.py.

Tests verify behavior of rate limit display commands:
- Show rate limit status
- Filter by provider
- Reset tracking data
- Display warnings
- Format usage percentages with colors
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestRateLimiterShowStatus:
    """Tests for showing rate limit status (no args)."""

    def test_show_status_displays_header(self):
        """Should display rate limit header."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        assert "Rate Limit" in output

    def test_show_status_displays_last_reset_times(self):
        """Should display last daily and monthly reset times."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        assert "Daily Reset:" in output or "Last Daily Reset:" in output

    def test_show_status_no_data_shows_message(self):
        """Should show informative message when no usage data exists."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {}
        }
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        assert "No usage data" in output or "no" in output.lower()

    def test_show_status_displays_tracking_file_location(self):
        """Should display the tracking file path."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.context.project_path = Path('/my/project')
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        assert "Tracking File:" in output or "File:" in output


class TestRateLimiterProviderDisplay:
    """Tests for displaying provider-specific rate limit data."""

    def test_displays_provider_name(self):
        """Should display provider name in uppercase."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
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
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        assert "OPENAI:" in output

    def test_displays_daily_usage(self):
        """Should display today's request and token counts."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'anthropic': {
                    'total_requests_today': 42,
                    'total_tokens_today': 12345,
                    'total_requests_month': 200,
                    'by_model': {}
                }
            }
        }
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        assert "42" in output
        assert "12,345" in output or "12345" in output
        assert "Today:" in output

    def test_displays_monthly_usage(self):
        """Should display this month's request count."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'gemini': {
                    'total_requests_today': 10,
                    'total_tokens_today': 5000,
                    'total_requests_month': 1234,
                    'by_model': {}
                }
            }
        }
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        assert "1234" in output or "1,234" in output
        assert "Month:" in output

    def test_displays_quotas_when_limits_exist(self):
        """Should display quota information when limits are configured."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 100,
                    'total_tokens_today': 50000,
                    'total_requests_month': 500,
                    'limits': {
                        'requests_per_day': 1000,
                        'requests_per_month': 10000,
                        'tokens_per_day': 100000
                    },
                    'remaining': {
                        'usage_today': 100,
                        'requests_remaining_today': 900,
                        'usage_this_month': 500,
                        'requests_remaining_month': 9500,
                        'tokens_today': 50000
                    },
                    'by_model': {}
                }
            }
        }
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        assert "Quotas:" in output
        assert "Daily Requests:" in output

    def test_displays_model_breakdown(self):
        """Should display usage breakdown by model."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
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
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        assert "By Model:" in output
        assert "gpt-4" in output
        assert "gpt-3.5-turbo" in output


class TestRateLimiterColorCoding:
    """Tests for usage percentage color coding."""

    def test_low_usage_styled_green(self):
        """Should style usage <75% in green."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 50,
                    'total_tokens_today': 25000,
                    'total_requests_month': 500,
                    'limits': {
                        'requests_per_day': 1000
                    },
                    'remaining': {
                        'usage_today': 50,
                        'requests_remaining_today': 950
                    },
                    'by_model': {}
                }
            }
        }
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        styled = io.get_styled_outputs()
        # Should have green styling for low usage
        green_with_pct = [s for s in styled if s['fg'] == 'green' and '%' in s['text']]
        assert len(green_with_pct) > 0

    def test_medium_usage_styled_yellow(self):
        """Should style usage 75-90% in yellow."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 800,
                    'total_tokens_today': 80000,
                    'total_requests_month': 500,
                    'limits': {
                        'requests_per_day': 1000
                    },
                    'remaining': {
                        'usage_today': 800,
                        'requests_remaining_today': 200
                    },
                    'by_model': {}
                }
            }
        }
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        styled = io.get_styled_outputs()
        # Should have yellow styling for medium usage (80%)
        yellow_with_pct = [s for s in styled if s['fg'] == 'yellow' and '%' in s['text']]
        assert len(yellow_with_pct) > 0

    def test_high_usage_styled_red(self):
        """Should style usage >90% in red."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 950,
                    'total_tokens_today': 95000,
                    'total_requests_month': 500,
                    'limits': {
                        'requests_per_day': 1000
                    },
                    'remaining': {
                        'usage_today': 950,
                        'requests_remaining_today': 50
                    },
                    'by_model': {}
                }
            }
        }
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        styled = io.get_styled_outputs()
        # Should have red styling for high usage (95%)
        red_with_pct = [s for s in styled if s['fg'] == 'red' and '%' in s['text']]
        assert len(red_with_pct) > 0


class TestRateLimiterWarnings:
    """Tests for rate limit warning display."""

    def test_displays_warnings_when_present(self):
        """Should display warnings when rate limits are approaching."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            "OpenAI: 90% of daily requests used",
            "Anthropic: Approaching token limit"
        ]
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
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        assert "WARNINGS:" in output
        assert "90%" in output

    def test_warnings_styled_red(self):
        """Should style warnings in red."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'test': {
                    'total_requests_today': 1,
                    'total_tokens_today': 100,
                    'total_requests_month': 1,
                    'by_model': {}
                }
            }
        }
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        styled = io.get_styled_outputs()
        red_warnings = [s for s in styled if s['fg'] == 'red' and 'WARNING' in s['text']]
        assert len(red_warnings) > 0


class TestRateLimiterFilterByProvider:
    """Tests for filtering rate limits by provider."""

    def test_filter_shows_only_specified_provider(self):
        """Should show only the specified provider when filtering."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 100,
                    'total_tokens_today': 50000,
                    'total_requests_month': 500,
                    'by_model': {}
                },
                'anthropic': {
                    'total_requests_today': 50,
                    'total_tokens_today': 25000,
                    'total_requests_month': 200,
                    'by_model': {}
                }
            }
        }
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="openai", io=io)

        output = io.get_output()
        assert "OPENAI:" in output
        assert "ANTHROPIC:" not in output

    def test_filter_unknown_provider_shows_message(self):
        """Should show message when filtered provider not found."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
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
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="unknown", io=io)

        output = io.get_output()
        assert "not found" in output.lower()


class TestRateLimiterReset:
    """Tests for reset tracking data commands."""

    def test_reset_all_prompts_for_confirmation(self):
        """Should prompt for confirmation before resetting all data."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
        limiter = RateLimiter(orchestrator)
        io = MockIO(confirmations=[False])

        limiter.show_rate_limits(args="reset", io=io)

        # Should have asked for confirmation
        assert io._confirm_index == 1

    def test_reset_all_confirmed_calls_reset(self):
        """Should reset all tracking data when confirmed."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
        reset_called = []
        limiter = RateLimiter(orchestrator)
        io = MockIO(confirmations=[True])

        limiter.show_rate_limits(args="reset", io=io)

        assert reset_called == [None]
        output = io.get_output()
        assert "reset" in output.lower()

    def test_reset_specific_provider(self):
        """Should reset only specific provider when specified."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
        reset_called = []
        limiter = RateLimiter(orchestrator)
        io = MockIO(confirmations=[True])

        limiter.show_rate_limits(args="reset openai", io=io)

        assert reset_called == ["openai"]
        output = io.get_output()
        assert "openai" in output.lower()

    def test_reset_cancelled_does_not_reset(self):
        """Should not reset data when confirmation is declined."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
        reset_called = []
        limiter = RateLimiter(orchestrator)
        io = MockIO(confirmations=[False])

        limiter.show_rate_limits(args="reset", io=io)

        assert reset_called == []


class TestRateLimiterTimeFormatting:
    """Tests for timestamp formatting in display."""

    def test_formats_last_request_time(self):
        """Should format last request time nicely."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 100,
                    'total_tokens_today': 50000,
                    'total_requests_month': 500,
                    'by_model': {
                        'gpt-4': {
                            'requests_today': 100,
                            'tokens_today': 50000,
                            'last_request': '2024-01-01T14:30:45.123456'
                        }
                    }
                }
            }
        }
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        # Should show time portion, not full ISO timestamp
        assert "14:30:45" in output

    def test_handles_never_used_model(self):
        """Should handle models that have never been used."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
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
        limiter = RateLimiter(orchestrator)
        io = MockIO()

        limiter.show_rate_limits(args="", io=io)

        output = io.get_output()
        assert "never" in output.lower()


class TestRateLimiterDefaultIO:
    """Tests for default IO behavior."""

    def test_uses_rich_io_when_io_not_provided(self):
        """Should use RichIO as default when io parameter is None."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
        limiter = RateLimiter(orchestrator)

        try:
            with patch('src.cli.rate_limiter.RichIO') as mock_rich:
                mock_io = MockIO()
                mock_rich.return_value = mock_io
                limiter.show_rate_limits(args="", io=None)
        except ImportError:
            pass
