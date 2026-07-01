"""Tests for rate limit calculator."""

from scrappy.orchestrator.rate_limiting.calculator import RateLimitCalculator


class FakeProviderLimits:
    """Test double for provider limits."""
    def __init__(
        self,
        requests_per_day=None,
        requests_per_month=None,
        tokens_per_day=None,
        tokens_per_minute=None,
    ):
        self.requests_per_day = requests_per_day
        self.requests_per_month = requests_per_month
        self.tokens_per_day = tokens_per_day
        self.tokens_per_minute = tokens_per_minute


def test_remaining_with_no_usage():
    """Should return full limits when no usage."""
    calc = RateLimitCalculator()
    usage = {
        "requests_today": 0,
        "requests_this_month": 0,
        "tokens_today": 0,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        requests_per_month=1000,
        tokens_per_day=10000,
        tokens_per_minute=1000,
    )

    result = calc.remaining(usage, limits)

    assert result["requests_remaining_today"] == 100
    assert result["requests_remaining_month"] == 1000
    assert result["tokens_remaining_today"] == 10000
    assert result["tokens_remaining_minute"] == 1000


def test_remaining_with_partial_usage():
    """Should calculate remaining quota correctly."""
    calc = RateLimitCalculator()
    usage = {
        "requests_today": 30,
        "requests_this_month": 250,
        "tokens_today": 2500,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        requests_per_month=1000,
        tokens_per_day=10000,
    )

    result = calc.remaining(usage, limits)

    assert result["requests_remaining_today"] == 70
    assert result["requests_remaining_month"] == 750
    assert result["tokens_remaining_today"] == 7500


def test_remaining_never_goes_negative():
    """Should return 0, not negative, when usage exceeds limit."""
    calc = RateLimitCalculator()
    usage = {
        "requests_today": 150,
        "tokens_today": 15000,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        tokens_per_day=10000,
    )

    result = calc.remaining(usage, limits)

    assert result["requests_remaining_today"] == 0
    assert result["tokens_remaining_today"] == 0


def test_remaining_with_no_limits():
    """Should return None for unlimited quotas."""
    calc = RateLimitCalculator()
    usage = {"requests_today": 100}
    limits = FakeProviderLimits()  # All limits are None

    result = calc.remaining(usage, limits)

    assert result["requests_remaining_today"] is None
    assert result["requests_remaining_month"] is None
    assert result["tokens_remaining_today"] is None


def test_warnings_detects_approaching_daily_request_limit():
    """Should warn when approaching daily request limit."""
    calc = RateLimitCalculator()
    remaining = {
        "requests_remaining_today": 5,
        "requests_remaining_month": 500,
        "tokens_remaining_today": 5000,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        requests_per_month=1000,
        tokens_per_day=10000,
    )

    result = calc.warnings(remaining, limits, threshold=0.1)

    assert result["approaching_daily_request_limit"] is True
    assert "5 requests remaining today" in result["message"]


def test_warnings_detects_approaching_token_limit():
    """Should warn when approaching daily token limit."""
    calc = RateLimitCalculator()
    remaining = {
        "requests_remaining_today": 50,
        "tokens_remaining_today": 500,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        tokens_per_day=10000,
    )

    result = calc.warnings(remaining, limits, threshold=0.1)

    assert result["approaching_daily_token_limit"] is True
    assert "500 tokens remaining today" in result["message"]


def test_warnings_no_warning_when_plenty_remaining():
    """Should not warn when plenty of quota remaining."""
    calc = RateLimitCalculator()
    remaining = {
        "requests_remaining_today": 80,
        "tokens_remaining_today": 9000,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        tokens_per_day=10000,
    )

    result = calc.warnings(remaining, limits, threshold=0.1)

    assert result["approaching_daily_request_limit"] is False
    assert result["approaching_daily_token_limit"] is False
    assert result["message"] is None


def test_summarise_with_empty_usage():
    """Should handle empty usage data."""
    calc = RateLimitCalculator()
    usage = {"providers": {}, "last_reset": {"daily": "2024-01-01", "monthly": "2024-01"}}

    result = calc.summarise(usage)

    assert result["last_reset"] == {"daily": "2024-01-01", "monthly": "2024-01"}
    assert result["providers"] == {}


def test_summarise_with_multiple_providers():
    """Should summarize usage across multiple providers."""
    calc = RateLimitCalculator()
    usage = {
        "providers": {
            "openai": {
                "gpt-4": {
                    "requests_today": 10,
                    "tokens_today": 1000,
                    "requests_this_month": 100,
                    "last_request": "2024-01-01T12:00:00",
                },
                "gpt-3.5": {
                    "requests_today": 5,
                    "tokens_today": 500,
                    "requests_this_month": 50,
                    "last_request": "2024-01-01T11:00:00",
                },
            },
            "anthropic": {
                "claude-3": {
                    "requests_today": 20,
                    "tokens_today": 2000,
                    "requests_this_month": 200,
                    "last_request": "2024-01-01T13:00:00",
                },
            },
        },
        "last_reset": {"daily": "2024-01-01", "monthly": "2024-01"},
    }

    result = calc.summarise(usage)

    # OpenAI totals
    assert result["providers"]["openai"]["total_requests_today"] == 15
    assert result["providers"]["openai"]["total_tokens_today"] == 1500
    assert result["providers"]["openai"]["total_requests_month"] == 150
    assert result["providers"]["openai"]["models"] == ["gpt-4", "gpt-3.5"]

    # Anthropic totals
    assert result["providers"]["anthropic"]["total_requests_today"] == 20
    assert result["providers"]["anthropic"]["total_tokens_today"] == 2000
    assert result["providers"]["anthropic"]["total_requests_month"] == 200

    # By-model details
    assert result["providers"]["openai"]["by_model"]["gpt-4"]["requests_today"] == 10
    assert result["providers"]["openai"]["by_model"]["gpt-4"]["tokens_today"] == 1000
