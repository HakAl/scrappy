"""
Tests for validation and error handling in CLI components.

Tests safe JSON/string parsing, timestamp validation, and fallback behavior.
These tests define the expected behavior for proper error handling.
"""

import pytest
from unittest.mock import Mock, MagicMock
from pathlib import Path

from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestTimestampParsing:
    """Tests for safe timestamp parsing in rate_limiter.py."""

    @pytest.mark.unit
    def test_parse_valid_iso_timestamp_with_fractional_seconds(self):
        """Test parsing a standard ISO timestamp with fractional seconds."""
        from src.cli.rate_limiter import RateLimiter

        # Setup mock orchestrator with valid timestamp
        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {
                'groq': {
                    'total_requests_today': 5,
                    'total_tokens_today': 1000,
                    'total_requests_month': 50,
                    'by_model': {
                        'llama-3.1-8b': {
                            'requests_today': 5,
                            'tokens_today': 1000,
                            'last_request': '2024-11-18T10:30:45.123456'
                        }
                    }
                }
            }
        })
        rate_limiter = RateLimiter(orchestrator)
        io = MockIO()

        # Should not raise an error
        rate_limiter.show_rate_limits("", io)

        output = io.get_output()
        assert "10:30:45" in output

    @pytest.mark.unit
    def test_parse_iso_timestamp_without_fractional_seconds(self):
        """Test parsing ISO timestamp without fractional seconds (e.g., 2024-11-18T10:30:45)."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {
                'groq': {
                    'total_requests_today': 5,
                    'total_tokens_today': 1000,
                    'total_requests_month': 50,
                    'by_model': {
                        'llama-3.1-8b': {
                            'requests_today': 5,
                            'tokens_today': 1000,
                            'last_request': '2024-11-18T10:30:45'
                        }
                    }
                }
            }
        })
        rate_limiter = RateLimiter(orchestrator)
        io = MockIO()

        # Should not raise an error - this currently fails with IndexError
        rate_limiter.show_rate_limits("", io)

        output = io.get_output()
        assert "10:30:45" in output

    @pytest.mark.unit
    def test_parse_iso_timestamp_with_z_suffix(self):
        """Test parsing ISO timestamp with Z (UTC) suffix (e.g., 2024-11-18T10:30:45Z)."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {
                'groq': {
                    'total_requests_today': 5,
                    'total_tokens_today': 1000,
                    'total_requests_month': 50,
                    'by_model': {
                        'llama-3.1-8b': {
                            'requests_today': 5,
                            'tokens_today': 1000,
                            'last_request': '2024-11-18T10:30:45Z'
                        }
                    }
                }
            }
        })
        rate_limiter = RateLimiter(orchestrator)
        io = MockIO()

        # Should not raise an error - this currently fails with IndexError
        rate_limiter.show_rate_limits("", io)

        output = io.get_output()
        assert "10:30:45" in output

    @pytest.mark.unit
    def test_parse_iso_timestamp_with_timezone_offset(self):
        """Test parsing ISO timestamp with timezone offset (e.g., 2024-11-18T10:30:45+05:00)."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {
                'groq': {
                    'total_requests_today': 5,
                    'total_tokens_today': 1000,
                    'total_requests_month': 50,
                    'by_model': {
                        'llama-3.1-8b': {
                            'requests_today': 5,
                            'tokens_today': 1000,
                            'last_request': '2024-11-18T10:30:45+05:00'
                        }
                    }
                }
            }
        })
        rate_limiter = RateLimiter(orchestrator)
        io = MockIO()

        # Should extract time portion correctly, not "+05:00"
        rate_limiter.show_rate_limits("", io)

        output = io.get_output()
        assert "10:30:45" in output
        # Should NOT contain the timezone offset as the time
        assert "+05:00" not in output.replace("2024-11-18T10:30:45+05:00", "")

    @pytest.mark.unit
    def test_parse_malformed_timestamp_gracefully(self):
        """Test that malformed timestamps are handled gracefully with fallback."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {
                'groq': {
                    'total_requests_today': 5,
                    'total_tokens_today': 1000,
                    'total_requests_month': 50,
                    'by_model': {
                        'llama-3.1-8b': {
                            'requests_today': 5,
                            'tokens_today': 1000,
                            'last_request': 'invalid-timestamp-format'
                        }
                    }
                }
            }
        })
        rate_limiter = RateLimiter(orchestrator)
        io = MockIO()

        # Should not raise an error - should fall back gracefully
        rate_limiter.show_rate_limits("", io)

        output = io.get_output()
        # Should display something, not crash
        assert "llama-3.1-8b" in output

    @pytest.mark.unit
    def test_parse_empty_timestamp_gracefully(self):
        """Test that empty timestamps are handled gracefully."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {
                'groq': {
                    'total_requests_today': 5,
                    'total_tokens_today': 1000,
                    'total_requests_month': 50,
                    'by_model': {
                        'llama-3.1-8b': {
                            'requests_today': 5,
                            'tokens_today': 1000,
                            'last_request': ''
                        }
                    }
                }
            }
        })
        rate_limiter = RateLimiter(orchestrator)
        io = MockIO()

        # Should not raise an error
        rate_limiter.show_rate_limits("", io)

        output = io.get_output()
        assert "llama-3.1-8b" in output

    @pytest.mark.unit
    def test_parse_none_timestamp_gracefully(self):
        """Test that None timestamps are handled gracefully."""
        from src.cli.rate_limiter import RateLimiter

        orchestrator = ConfigurableTestOrchestrator()
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {
                'groq': {
                    'total_requests_today': 5,
                    'total_tokens_today': 1000,
                    'total_requests_month': 50,
                    'by_model': {
                        'llama-3.1-8b': {
                            'requests_today': 5,
                            'tokens_today': 1000,
                            'last_request': None
                        }
                    }
                }
            }
        })
        rate_limiter = RateLimiter(orchestrator)
        io = MockIO()

        # Should not raise an error
        rate_limiter.show_rate_limits("", io)

        output = io.get_output()
        assert "llama-3.1-8b" in output
