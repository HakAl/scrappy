"""
Tests for RateLimitPolicy.

Tests the rate limit reset policy logic that determines when to reset
daily and monthly counters.
"""
import pytest
from datetime import date

from scrappy.orchestrator.rate_limiting.policy import RateLimitPolicy


class TestRateLimitPolicyInit:
    """Tests for RateLimitPolicy initialization."""

    @pytest.mark.unit
    def test_init_with_default_date(self):
        """Policy should use today's date by default."""
        policy = RateLimitPolicy()
        # Can't easily test default, but should not raise
        assert policy is not None

    @pytest.mark.unit
    def test_init_with_custom_date(self):
        """Policy should accept a custom date for testing."""
        custom_date = date(2024, 6, 15)
        policy = RateLimitPolicy(today=custom_date)
        assert policy._today == custom_date


class TestResetNeeded:
    """Tests for reset_needed method."""

    @pytest.mark.unit
    def test_daily_reset_needed_when_different_date(self):
        """Daily reset should be needed when last reset date differs."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        last_reset_info = {
            "daily": "2024-06-14",
            "monthly": "2024-06",
        }

        result = policy.reset_needed(last_reset_info)

        assert result["daily"] is True
        assert result["monthly"] is False

    @pytest.mark.unit
    def test_daily_reset_not_needed_when_same_date(self):
        """Daily reset should not be needed when last reset is today."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        last_reset_info = {
            "daily": "2024-06-15",
            "monthly": "2024-06",
        }

        result = policy.reset_needed(last_reset_info)

        assert result["daily"] is False
        assert result["monthly"] is False

    @pytest.mark.unit
    def test_monthly_reset_needed_when_different_month(self):
        """Monthly reset should be needed when month differs."""
        policy = RateLimitPolicy(today=date(2024, 7, 1))
        last_reset_info = {
            "daily": "2024-07-01",
            "monthly": "2024-06",
        }

        result = policy.reset_needed(last_reset_info)

        assert result["daily"] is False
        assert result["monthly"] is True

    @pytest.mark.unit
    def test_both_resets_needed_new_month_new_day(self):
        """Both resets should be needed at start of new month."""
        policy = RateLimitPolicy(today=date(2024, 7, 1))
        last_reset_info = {
            "daily": "2024-06-30",
            "monthly": "2024-06",
        }

        result = policy.reset_needed(last_reset_info)

        assert result["daily"] is True
        assert result["monthly"] is True

    @pytest.mark.unit
    def test_neither_reset_needed_when_current(self):
        """No resets needed when last reset info is current."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        last_reset_info = {
            "daily": "2024-06-15",
            "monthly": "2024-06",
        }

        result = policy.reset_needed(last_reset_info)

        assert result["daily"] is False
        assert result["monthly"] is False

    @pytest.mark.unit
    def test_reset_needed_with_missing_daily_key(self):
        """Daily reset should be needed when key is missing."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        last_reset_info = {
            "monthly": "2024-06",
        }

        result = policy.reset_needed(last_reset_info)

        assert result["daily"] is True
        assert result["monthly"] is False

    @pytest.mark.unit
    def test_reset_needed_with_missing_monthly_key(self):
        """Monthly reset should be needed when key is missing."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        last_reset_info = {
            "daily": "2024-06-15",
        }

        result = policy.reset_needed(last_reset_info)

        assert result["daily"] is False
        assert result["monthly"] is True

    @pytest.mark.unit
    def test_reset_needed_with_empty_dict(self):
        """Both resets should be needed with empty last_reset_info."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        last_reset_info = {}

        result = policy.reset_needed(last_reset_info)

        assert result["daily"] is True
        assert result["monthly"] is True

    @pytest.mark.unit
    def test_reset_needed_year_boundary(self):
        """Both resets needed at year boundary."""
        policy = RateLimitPolicy(today=date(2025, 1, 1))
        last_reset_info = {
            "daily": "2024-12-31",
            "monthly": "2024-12",
        }

        result = policy.reset_needed(last_reset_info)

        assert result["daily"] is True
        assert result["monthly"] is True


class TestApplyReset:
    """Tests for apply_reset method."""

    def _create_usage_data(self):
        """Helper to create sample usage data."""
        return {
            "providers": {
                "openai": {
                    "gpt-4": {
                        "requests_today": 100,
                        "tokens_today": 50000,
                        "input_tokens_today": 30000,
                        "output_tokens_today": 20000,
                        "requests_this_month": 3000,
                        "tokens_this_month": 1500000,
                    },
                    "gpt-3.5-turbo": {
                        "requests_today": 200,
                        "tokens_today": 100000,
                        "input_tokens_today": 60000,
                        "output_tokens_today": 40000,
                        "requests_this_month": 6000,
                        "tokens_this_month": 3000000,
                    },
                },
                "anthropic": {
                    "claude-3-opus": {
                        "requests_today": 50,
                        "tokens_today": 25000,
                        "input_tokens_today": 15000,
                        "output_tokens_today": 10000,
                        "requests_this_month": 1500,
                        "tokens_this_month": 750000,
                    },
                },
            }
        }

    @pytest.mark.unit
    def test_apply_daily_reset_only(self):
        """Daily reset should zero daily counters only."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = self._create_usage_data()

        policy.apply_reset(usage, {"daily": True, "monthly": False})

        # Daily counters should be zero
        gpt4 = usage["providers"]["openai"]["gpt-4"]
        assert gpt4["requests_today"] == 0
        assert gpt4["tokens_today"] == 0
        assert gpt4["input_tokens_today"] == 0
        assert gpt4["output_tokens_today"] == 0

        # Monthly counters should be unchanged
        assert gpt4["requests_this_month"] == 3000
        assert gpt4["tokens_this_month"] == 1500000

    @pytest.mark.unit
    def test_apply_monthly_reset_only(self):
        """Monthly reset should zero monthly counters only."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = self._create_usage_data()

        policy.apply_reset(usage, {"daily": False, "monthly": True})

        # Daily counters should be unchanged
        gpt4 = usage["providers"]["openai"]["gpt-4"]
        assert gpt4["requests_today"] == 100
        assert gpt4["tokens_today"] == 50000

        # Monthly counters should be zero
        assert gpt4["requests_this_month"] == 0
        assert gpt4["tokens_this_month"] == 0

    @pytest.mark.unit
    def test_apply_both_resets(self):
        """Both daily and monthly counters should be zeroed."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = self._create_usage_data()

        policy.apply_reset(usage, {"daily": True, "monthly": True})

        gpt4 = usage["providers"]["openai"]["gpt-4"]
        assert gpt4["requests_today"] == 0
        assert gpt4["tokens_today"] == 0
        assert gpt4["input_tokens_today"] == 0
        assert gpt4["output_tokens_today"] == 0
        assert gpt4["requests_this_month"] == 0
        assert gpt4["tokens_this_month"] == 0

    @pytest.mark.unit
    def test_apply_no_resets(self):
        """No counters should be changed when both flags are False."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = self._create_usage_data()
        original_gpt4 = usage["providers"]["openai"]["gpt-4"].copy()

        policy.apply_reset(usage, {"daily": False, "monthly": False})

        gpt4 = usage["providers"]["openai"]["gpt-4"]
        assert gpt4["requests_today"] == original_gpt4["requests_today"]
        assert gpt4["tokens_today"] == original_gpt4["tokens_today"]
        assert gpt4["requests_this_month"] == original_gpt4["requests_this_month"]
        assert gpt4["tokens_this_month"] == original_gpt4["tokens_this_month"]

    @pytest.mark.unit
    def test_apply_reset_affects_all_providers(self):
        """Reset should affect all providers and models."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = self._create_usage_data()

        policy.apply_reset(usage, {"daily": True, "monthly": False})

        # Check OpenAI gpt-4
        assert usage["providers"]["openai"]["gpt-4"]["requests_today"] == 0

        # Check OpenAI gpt-3.5-turbo
        assert usage["providers"]["openai"]["gpt-3.5-turbo"]["requests_today"] == 0

        # Check Anthropic claude-3-opus
        assert usage["providers"]["anthropic"]["claude-3-opus"]["requests_today"] == 0

    @pytest.mark.unit
    def test_apply_reset_with_empty_providers(self):
        """Reset should handle empty providers dict gracefully."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = {"providers": {}}

        # Should not raise
        policy.apply_reset(usage, {"daily": True, "monthly": True})

        assert usage["providers"] == {}

    @pytest.mark.unit
    def test_apply_reset_with_missing_providers_key(self):
        """Reset should handle missing providers key gracefully."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = {}

        # Should not raise
        policy.apply_reset(usage, {"daily": True, "monthly": True})

        assert usage == {}


class TestResetDaily:
    """Tests for _reset_daily private method."""

    @pytest.mark.unit
    def test_reset_daily_clears_all_daily_counters(self):
        """All four daily counters should be reset to zero."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = {
            "providers": {
                "test": {
                    "model": {
                        "requests_today": 999,
                        "tokens_today": 888,
                        "input_tokens_today": 777,
                        "output_tokens_today": 666,
                        "requests_this_month": 555,  # Should not change
                    }
                }
            }
        }

        policy._reset_daily(usage)

        model_data = usage["providers"]["test"]["model"]
        assert model_data["requests_today"] == 0
        assert model_data["tokens_today"] == 0
        assert model_data["input_tokens_today"] == 0
        assert model_data["output_tokens_today"] == 0
        assert model_data["requests_this_month"] == 555  # Unchanged


class TestResetMonthly:
    """Tests for _reset_monthly private method."""

    @pytest.mark.unit
    def test_reset_monthly_clears_all_monthly_counters(self):
        """Both monthly counters should be reset to zero."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = {
            "providers": {
                "test": {
                    "model": {
                        "requests_today": 100,  # Should not change
                        "tokens_today": 50,  # Should not change
                        "requests_this_month": 3000,
                        "tokens_this_month": 1500000,
                    }
                }
            }
        }

        policy._reset_monthly(usage)

        model_data = usage["providers"]["test"]["model"]
        assert model_data["requests_this_month"] == 0
        assert model_data["tokens_this_month"] == 0
        assert model_data["requests_today"] == 100  # Unchanged
        assert model_data["tokens_today"] == 50  # Unchanged


class TestRateLimitPolicyIntegration:
    """Integration tests for realistic usage scenarios."""

    @pytest.mark.unit
    def test_new_day_same_month_workflow(self):
        """Simulate starting a new day within the same month."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = {
            "providers": {
                "openai": {
                    "gpt-4": {
                        "requests_today": 100,
                        "tokens_today": 50000,
                        "input_tokens_today": 30000,
                        "output_tokens_today": 20000,
                        "requests_this_month": 1000,
                        "tokens_this_month": 500000,
                    }
                }
            }
        }
        last_reset_info = {
            "daily": "2024-06-14",
            "monthly": "2024-06",
        }

        # Check what needs reset
        which = policy.reset_needed(last_reset_info)
        assert which["daily"] is True
        assert which["monthly"] is False

        # Apply the reset
        policy.apply_reset(usage, which)

        # Verify
        gpt4 = usage["providers"]["openai"]["gpt-4"]
        assert gpt4["requests_today"] == 0  # Reset
        assert gpt4["tokens_today"] == 0  # Reset
        assert gpt4["requests_this_month"] == 1000  # Preserved
        assert gpt4["tokens_this_month"] == 500000  # Preserved

    @pytest.mark.unit
    def test_new_month_workflow(self):
        """Simulate starting a new month."""
        policy = RateLimitPolicy(today=date(2024, 7, 1))
        usage = {
            "providers": {
                "anthropic": {
                    "claude-3-opus": {
                        "requests_today": 50,
                        "tokens_today": 25000,
                        "input_tokens_today": 15000,
                        "output_tokens_today": 10000,
                        "requests_this_month": 1500,
                        "tokens_this_month": 750000,
                    }
                }
            }
        }
        last_reset_info = {
            "daily": "2024-06-30",
            "monthly": "2024-06",
        }

        # Check what needs reset
        which = policy.reset_needed(last_reset_info)
        assert which["daily"] is True
        assert which["monthly"] is True

        # Apply the reset
        policy.apply_reset(usage, which)

        # All counters should be zero
        claude = usage["providers"]["anthropic"]["claude-3-opus"]
        assert claude["requests_today"] == 0
        assert claude["tokens_today"] == 0
        assert claude["input_tokens_today"] == 0
        assert claude["output_tokens_today"] == 0
        assert claude["requests_this_month"] == 0
        assert claude["tokens_this_month"] == 0

    @pytest.mark.unit
    def test_same_day_no_reset_workflow(self):
        """Simulate multiple calls on the same day - no reset needed."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = {
            "providers": {
                "openai": {
                    "gpt-4": {
                        "requests_today": 50,
                        "tokens_today": 25000,
                        "input_tokens_today": 15000,
                        "output_tokens_today": 10000,
                        "requests_this_month": 500,
                        "tokens_this_month": 250000,
                    }
                }
            }
        }
        last_reset_info = {
            "daily": "2024-06-15",
            "monthly": "2024-06",
        }

        # Check what needs reset
        which = policy.reset_needed(last_reset_info)
        assert which["daily"] is False
        assert which["monthly"] is False

        # Apply (should do nothing)
        original_data = usage["providers"]["openai"]["gpt-4"].copy()
        policy.apply_reset(usage, which)

        # Everything should be unchanged
        gpt4 = usage["providers"]["openai"]["gpt-4"]
        assert gpt4 == original_data

    @pytest.mark.unit
    def test_fresh_start_no_history(self):
        """Simulate first run with no previous reset info."""
        policy = RateLimitPolicy(today=date(2024, 6, 15))
        usage = {
            "providers": {
                "openai": {
                    "gpt-4": {
                        "requests_today": 0,
                        "tokens_today": 0,
                        "input_tokens_today": 0,
                        "output_tokens_today": 0,
                        "requests_this_month": 0,
                        "tokens_this_month": 0,
                    }
                }
            }
        }
        last_reset_info = {}  # No previous history

        # Check what needs reset
        which = policy.reset_needed(last_reset_info)
        assert which["daily"] is True  # Missing key means reset needed
        assert which["monthly"] is True  # Missing key means reset needed

        # Apply the reset (counters already zero, but operation should succeed)
        policy.apply_reset(usage, which)

        gpt4 = usage["providers"]["openai"]["gpt-4"]
        assert gpt4["requests_today"] == 0
        assert gpt4["requests_this_month"] == 0
