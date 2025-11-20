"""
Comprehensive tests for the RateLimitTracker.

Tests persistence, reset logic, quota calculations, and error tracking.
"""

import pytest
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, AsyncMock

from src.orchestrator.rate_limiter import RateLimitTracker
from src.providers.base import ProviderLimits


class TestRateLimitTrackerInitialization:
    """Tests for RateLimitTracker initialization."""

    @pytest.mark.unit
    def test_initialization_without_file(self):
        """Test initialization without persistence file."""
        tracker = RateLimitTracker()

        assert tracker.tracker_file is None
        assert 'providers' in tracker._usage
        assert 'last_reset' in tracker._usage
        assert 'created_at' in tracker._usage
        assert tracker._usage['providers'] == {}

    @pytest.mark.unit
    def test_initialization_with_nonexistent_file(self, tmp_path):
        """Test initialization with non-existent file path."""
        tracker_path = tmp_path / "tracker.json"
        tracker = RateLimitTracker(str(tracker_path))

        assert tracker.tracker_file == tracker_path
        assert 'providers' in tracker._usage
        assert tracker._usage['providers'] == {}

    @pytest.mark.unit
    def test_initialization_loads_existing_file(self, tmp_path):
        """Test initialization loads existing tracker file."""
        tracker_path = tmp_path / "tracker.json"

        # Create existing tracker data
        existing_data = {
            'providers': {
                'groq': {
                    'llama-3.1-8b-instant': {
                        'requests_today': 5,
                        'requests_this_month': 50,
                        'tokens_today': 1000,
                        'tokens_this_month': 10000,
                        'input_tokens_today': 400,
                        'output_tokens_today': 600,
                        'total_requests': 100,
                        'total_tokens': 20000,
                        'last_request': '2025-11-15T10:00:00',
                        'errors': []
                    }
                }
            },
            'last_reset': {
                'daily': datetime.now().date().isoformat(),
                'monthly': datetime.now().strftime('%Y-%m')
            },
            'created_at': '2025-11-01T00:00:00'
        }

        tracker_path.write_text(json.dumps(existing_data))

        tracker = RateLimitTracker(str(tracker_path))

        assert tracker._usage['providers']['groq']['llama-3.1-8b-instant']['requests_today'] == 5
        assert tracker._usage['providers']['groq']['llama-3.1-8b-instant']['total_requests'] == 100

    @pytest.mark.unit
    def test_initialization_handles_corrupted_file(self, tmp_path):
        """Test initialization handles corrupted JSON file."""
        tracker_path = tmp_path / "tracker.json"
        tracker_path.write_text("not valid json {{{")

        tracker = RateLimitTracker(str(tracker_path))

        # Should initialize empty on corruption
        assert 'providers' in tracker._usage
        assert tracker._usage['providers'] == {}

    @pytest.mark.unit
    def test_empty_initialization_structure(self):
        """Test that empty initialization has correct structure."""
        tracker = RateLimitTracker()

        assert 'providers' in tracker._usage
        assert 'last_reset' in tracker._usage
        assert 'daily' in tracker._usage['last_reset']
        assert 'monthly' in tracker._usage['last_reset']
        assert 'created_at' in tracker._usage


class TestRecordRequest:
    """Tests for recording API requests."""

    @pytest.mark.unit
    def test_record_successful_request(self):
        """Test recording a successful request."""
        tracker = RateLimitTracker()

        tracker.record_request(
            provider='groq',
            model='llama-3.1-8b-instant',
            input_tokens=100,
            output_tokens=50
        )

        usage = tracker.get_usage('groq', 'llama-3.1-8b-instant')

        assert usage['requests_today'] == 1
        assert usage['requests_this_month'] == 1
        assert usage['total_requests'] == 1
        assert usage['tokens_today'] == 150
        assert usage['tokens_this_month'] == 150
        assert usage['total_tokens'] == 150
        assert usage['input_tokens_today'] == 100
        assert usage['output_tokens_today'] == 50
        assert usage['last_request'] is not None
        assert usage['errors'] == []

    @pytest.mark.unit
    def test_record_multiple_requests(self):
        """Test recording multiple requests accumulates correctly."""
        tracker = RateLimitTracker()

        tracker.record_request('groq', 'llama-3.1-8b-instant', 100, 50)
        tracker.record_request('groq', 'llama-3.1-8b-instant', 200, 100)
        tracker.record_request('groq', 'llama-3.1-8b-instant', 50, 25)

        usage = tracker.get_usage('groq', 'llama-3.1-8b-instant')

        assert usage['requests_today'] == 3
        assert usage['total_requests'] == 3
        assert usage['tokens_today'] == 525  # 150 + 300 + 75
        assert usage['input_tokens_today'] == 350  # 100 + 200 + 50
        assert usage['output_tokens_today'] == 175  # 50 + 100 + 25

    @pytest.mark.unit
    def test_record_request_with_error(self):
        """Test recording a failed request with error message."""
        tracker = RateLimitTracker()

        tracker.record_request(
            provider='cohere',
            model='command-r-08-2024',
            input_tokens=100,
            output_tokens=0,
            success=False,
            error_message='Rate limit exceeded'
        )

        usage = tracker.get_usage('cohere', 'command-r-08-2024')

        assert usage['requests_today'] == 1
        assert len(usage['errors']) == 1
        assert usage['errors'][0]['message'] == 'Rate limit exceeded'
        assert 'timestamp' in usage['errors'][0]

    @pytest.mark.unit
    def test_error_list_truncation(self):
        """Test that error list is truncated to last 10 errors."""
        tracker = RateLimitTracker()

        # Record 15 failed requests
        for i in range(15):
            tracker.record_request(
                'groq', 'model',
                success=False,
                error_message=f'Error {i}'
            )

        usage = tracker.get_usage('groq', 'model')

        assert len(usage['errors']) == 10
        # Should keep the last 10 errors (5-14)
        assert usage['errors'][0]['message'] == 'Error 5'
        assert usage['errors'][-1]['message'] == 'Error 14'

    @pytest.mark.unit
    def test_error_message_truncation(self):
        """Test that long error messages are truncated."""
        tracker = RateLimitTracker()

        long_error = 'x' * 500  # 500 character error message
        tracker.record_request(
            'groq', 'model',
            success=False,
            error_message=long_error
        )

        usage = tracker.get_usage('groq', 'model')

        assert len(usage['errors'][0]['message']) == 200

    @pytest.mark.unit
    def test_record_request_multiple_providers(self):
        """Test recording requests for multiple providers."""
        tracker = RateLimitTracker()

        tracker.record_request('groq', 'llama-model', 100, 50)
        tracker.record_request('cohere', 'command-r', 200, 100)
        tracker.record_request('gemini', 'gemini-pro', 150, 75)

        assert tracker.get_usage('groq', 'llama-model')['requests_today'] == 1
        assert tracker.get_usage('cohere', 'command-r')['requests_today'] == 1
        assert tracker.get_usage('gemini', 'gemini-pro')['requests_today'] == 1

    @pytest.mark.unit
    def test_record_request_persists_to_file(self, tmp_path):
        """Test that recording a request saves to file."""
        tracker_path = tmp_path / "tracker.json"
        tracker = RateLimitTracker(str(tracker_path))

        tracker.record_request('groq', 'model', 100, 50)

        # File should exist and contain the data
        assert tracker_path.exists()

        saved_data = json.loads(tracker_path.read_text())
        assert saved_data['providers']['groq']['model']['requests_today'] == 1

    @pytest.mark.unit
    def test_record_request_default_values(self):
        """Test recording request with default token values."""
        tracker = RateLimitTracker()

        tracker.record_request('groq', 'model')

        usage = tracker.get_usage('groq', 'model')
        assert usage['tokens_today'] == 0
        assert usage['input_tokens_today'] == 0
        assert usage['output_tokens_today'] == 0
        assert usage['requests_today'] == 1


class TestGetUsage:
    """Tests for retrieving usage statistics."""

    @pytest.mark.unit
    def test_get_usage_for_specific_model(self):
        """Test getting usage for a specific model."""
        tracker = RateLimitTracker()
        tracker.record_request('groq', 'model-a', 100, 50)
        tracker.record_request('groq', 'model-b', 200, 100)

        usage = tracker.get_usage('groq', 'model-a')

        assert usage['tokens_today'] == 150
        assert usage['requests_today'] == 1

    @pytest.mark.unit
    def test_get_usage_for_all_models(self):
        """Test getting usage for all models of a provider."""
        tracker = RateLimitTracker()
        tracker.record_request('groq', 'model-a', 100, 50)
        tracker.record_request('groq', 'model-b', 200, 100)

        usage = tracker.get_usage('groq')

        assert 'model-a' in usage
        assert 'model-b' in usage
        assert usage['model-a']['tokens_today'] == 150
        assert usage['model-b']['tokens_today'] == 300

    @pytest.mark.unit
    def test_get_usage_nonexistent_provider(self):
        """Test getting usage for nonexistent provider returns empty dict."""
        tracker = RateLimitTracker()

        usage = tracker.get_usage('nonexistent')

        assert usage == {}

    @pytest.mark.unit
    def test_get_usage_nonexistent_model(self):
        """Test getting usage for nonexistent model returns empty dict."""
        tracker = RateLimitTracker()
        tracker.record_request('groq', 'model-a', 100, 50)

        usage = tracker.get_usage('groq', 'nonexistent')

        assert usage == {}


class TestDailyReset:
    """Tests for daily reset functionality."""

    @pytest.mark.unit
    def test_daily_reset_clears_daily_counters(self, tmp_path):
        """Test that daily reset clears daily counters."""
        tracker_path = tmp_path / "tracker.json"

        # Create tracker with yesterday's date
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
        existing_data = {
            'providers': {
                'groq': {
                    'model': {
                        'requests_today': 10,
                        'requests_this_month': 100,
                        'tokens_today': 5000,
                        'tokens_this_month': 50000,
                        'input_tokens_today': 2000,
                        'output_tokens_today': 3000,
                        'total_requests': 200,
                        'total_tokens': 100000,
                        'last_request': None,
                        'errors': []
                    }
                }
            },
            'last_reset': {
                'daily': yesterday,
                'monthly': datetime.now().strftime('%Y-%m')
            },
            'created_at': '2025-11-01T00:00:00'
        }

        tracker_path.write_text(json.dumps(existing_data))

        # Loading should trigger reset check
        tracker = RateLimitTracker(str(tracker_path))

        usage = tracker.get_usage('groq', 'model')

        # Daily counters should be reset
        assert usage['requests_today'] == 0
        assert usage['tokens_today'] == 0
        assert usage['input_tokens_today'] == 0
        assert usage['output_tokens_today'] == 0

        # Monthly and total should be preserved
        assert usage['requests_this_month'] == 100
        assert usage['tokens_this_month'] == 50000
        assert usage['total_requests'] == 200
        assert usage['total_tokens'] == 100000

    @pytest.mark.unit
    def test_daily_reset_updates_last_reset_date(self, tmp_path):
        """Test that daily reset updates the last reset date."""
        tracker_path = tmp_path / "tracker.json"
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()

        existing_data = {
            'providers': {},
            'last_reset': {
                'daily': yesterday,
                'monthly': datetime.now().strftime('%Y-%m')
            },
            'created_at': '2025-11-01T00:00:00'
        }

        tracker_path.write_text(json.dumps(existing_data))
        tracker = RateLimitTracker(str(tracker_path))

        assert tracker._usage['last_reset']['daily'] == datetime.now().date().isoformat()


class TestMonthlyReset:
    """Tests for monthly reset functionality."""

    @pytest.mark.unit
    def test_monthly_reset_clears_monthly_counters(self, tmp_path):
        """Test that monthly reset clears monthly counters."""
        tracker_path = tmp_path / "tracker.json"

        # Create tracker with last month's date
        last_month = (datetime.now() - timedelta(days=35)).strftime('%Y-%m')
        existing_data = {
            'providers': {
                'groq': {
                    'model': {
                        'requests_today': 10,
                        'requests_this_month': 100,
                        'tokens_today': 5000,
                        'tokens_this_month': 50000,
                        'input_tokens_today': 2000,
                        'output_tokens_today': 3000,
                        'total_requests': 200,
                        'total_tokens': 100000,
                        'last_request': None,
                        'errors': []
                    }
                }
            },
            'last_reset': {
                'daily': datetime.now().date().isoformat(),
                'monthly': last_month
            },
            'created_at': '2025-11-01T00:00:00'
        }

        tracker_path.write_text(json.dumps(existing_data))
        tracker = RateLimitTracker(str(tracker_path))

        usage = tracker.get_usage('groq', 'model')

        # Monthly counters should be reset
        assert usage['requests_this_month'] == 0
        assert usage['tokens_this_month'] == 0

        # Total should be preserved
        assert usage['total_requests'] == 200
        assert usage['total_tokens'] == 100000


class TestQuotaCalculations:
    """Tests for remaining quota calculations."""

    @pytest.mark.unit
    def test_get_remaining_quota_with_all_limits(self):
        """Test quota calculation with all limit types."""
        tracker = RateLimitTracker()
        tracker.record_request('groq', 'model', 1000, 500)
        tracker.record_request('groq', 'model', 1000, 500)

        limits = ProviderLimits(
            requests_per_minute=30,
            requests_per_day=100,
            requests_per_month=1000,
            tokens_per_minute=10000,
            tokens_per_day=50000
        )

        remaining = tracker.get_remaining_quota('groq', 'model', limits)

        assert remaining['requests_remaining_today'] == 98  # 100 - 2
        assert remaining['requests_remaining_month'] == 998  # 1000 - 2
        assert remaining['tokens_remaining_today'] == 47000  # 50000 - 3000
        assert remaining['tokens_remaining_minute'] == 10000
        assert remaining['usage_today'] == 2
        assert remaining['tokens_today'] == 3000
        assert remaining['usage_this_month'] == 2

    @pytest.mark.unit
    def test_get_remaining_quota_no_limits(self):
        """Test quota calculation when no limits are set."""
        tracker = RateLimitTracker()
        tracker.record_request('groq', 'model', 1000, 500)

        limits = ProviderLimits()  # No limits set

        remaining = tracker.get_remaining_quota('groq', 'model', limits)

        assert remaining['requests_remaining_today'] is None
        assert remaining['requests_remaining_month'] is None
        assert remaining['tokens_remaining_today'] is None
        assert remaining['usage_today'] == 1
        assert remaining['tokens_today'] == 1500

    @pytest.mark.unit
    def test_get_remaining_quota_at_limit(self):
        """Test quota calculation when at limit."""
        tracker = RateLimitTracker()

        # Use up all requests
        for _ in range(10):
            tracker.record_request('groq', 'model', 100, 50)

        limits = ProviderLimits(requests_per_day=10)

        remaining = tracker.get_remaining_quota('groq', 'model', limits)

        assert remaining['requests_remaining_today'] == 0

    @pytest.mark.unit
    def test_get_remaining_quota_over_limit(self):
        """Test quota calculation when over limit (should return 0)."""
        tracker = RateLimitTracker()

        # Go over limit
        for _ in range(15):
            tracker.record_request('groq', 'model', 100, 50)

        limits = ProviderLimits(requests_per_day=10)

        remaining = tracker.get_remaining_quota('groq', 'model', limits)

        # Should return 0, not negative
        assert remaining['requests_remaining_today'] == 0

    @pytest.mark.unit
    def test_get_remaining_quota_for_new_provider(self):
        """Test quota calculation for provider with no usage."""
        tracker = RateLimitTracker()

        limits = ProviderLimits(requests_per_day=100, tokens_per_day=50000)

        remaining = tracker.get_remaining_quota('new_provider', 'new_model', limits)

        assert remaining['requests_remaining_today'] == 100
        assert remaining['tokens_remaining_today'] == 50000
        assert remaining['usage_today'] == 0
        assert remaining['tokens_today'] == 0


class TestLimitWarnings:
    """Tests for approaching limit warnings."""

    @pytest.mark.unit
    def test_no_warnings_when_far_from_limit(self):
        """Test no warnings when usage is far from limit."""
        tracker = RateLimitTracker()
        tracker.record_request('groq', 'model', 100, 50)  # 1 request, 150 tokens

        limits = ProviderLimits(
            requests_per_day=100,
            requests_per_month=1000,
            tokens_per_day=50000
        )

        warnings = tracker.is_limit_approaching('groq', 'model', limits)

        assert warnings['approaching_daily_request_limit'] is False
        assert warnings['approaching_monthly_request_limit'] is False
        assert warnings['approaching_daily_token_limit'] is False
        assert warnings['message'] is None

    @pytest.mark.unit
    def test_warning_when_approaching_daily_request_limit(self):
        """Test warning when approaching daily request limit."""
        tracker = RateLimitTracker()

        # Use 95 out of 100 requests
        for _ in range(95):
            tracker.record_request('groq', 'model', 10, 5)

        limits = ProviderLimits(requests_per_day=100)

        warnings = tracker.is_limit_approaching('groq', 'model', limits, threshold=0.1)

        assert warnings['approaching_daily_request_limit'] is True
        assert '5 requests remaining today' in warnings['message']

    @pytest.mark.unit
    def test_warning_when_approaching_monthly_request_limit(self):
        """Test warning when approaching monthly request limit."""
        tracker = RateLimitTracker()

        # Simulate being at 95 of 100 monthly requests
        tracker._ensure_provider_model('groq', 'model')
        tracker._usage['providers']['groq']['model']['requests_this_month'] = 95

        limits = ProviderLimits(requests_per_month=100)

        warnings = tracker.is_limit_approaching('groq', 'model', limits, threshold=0.1)

        assert warnings['approaching_monthly_request_limit'] is True
        assert '5 requests remaining this month' in warnings['message']

    @pytest.mark.unit
    def test_warning_when_approaching_daily_token_limit(self):
        """Test warning when approaching daily token limit."""
        tracker = RateLimitTracker()

        # Use 9500 out of 10000 tokens
        tracker.record_request('groq', 'model', 5000, 4500)

        limits = ProviderLimits(tokens_per_day=10000)

        warnings = tracker.is_limit_approaching('groq', 'model', limits, threshold=0.1)

        assert warnings['approaching_daily_token_limit'] is True
        assert '500 tokens remaining today' in warnings['message']

    @pytest.mark.unit
    def test_multiple_warnings(self):
        """Test multiple warnings in single check."""
        tracker = RateLimitTracker()

        # Set up to trigger multiple warnings
        tracker._ensure_provider_model('groq', 'model')
        tracker._usage['providers']['groq']['model']['requests_today'] = 95
        tracker._usage['providers']['groq']['model']['requests_this_month'] = 950
        tracker._usage['providers']['groq']['model']['tokens_today'] = 9500

        limits = ProviderLimits(
            requests_per_day=100,
            requests_per_month=1000,
            tokens_per_day=10000
        )

        warnings = tracker.is_limit_approaching('groq', 'model', limits, threshold=0.1)

        assert warnings['approaching_daily_request_limit'] is True
        assert warnings['approaching_monthly_request_limit'] is True
        assert warnings['approaching_daily_token_limit'] is True
        assert 'groq/model' in warnings['message']

    @pytest.mark.unit
    def test_custom_threshold(self):
        """Test warning with custom threshold."""
        tracker = RateLimitTracker()

        # Use 80 out of 100 requests
        for _ in range(80):
            tracker.record_request('groq', 'model', 10, 5)

        limits = ProviderLimits(requests_per_day=100)

        # Should not warn at 10% threshold (20 remaining is > 10)
        warnings_10 = tracker.is_limit_approaching('groq', 'model', limits, threshold=0.1)
        assert warnings_10['approaching_daily_request_limit'] is False

        # Should warn at 25% threshold (20 remaining is < 25)
        warnings_25 = tracker.is_limit_approaching('groq', 'model', limits, threshold=0.25)
        assert warnings_25['approaching_daily_request_limit'] is True


class TestUsageSummary:
    """Tests for usage summary functionality."""

    @pytest.mark.unit
    def test_get_all_usage_summary_empty(self):
        """Test summary with no usage."""
        tracker = RateLimitTracker()

        summary = tracker.get_all_usage_summary()

        assert 'last_reset' in summary
        assert 'providers' in summary
        assert summary['providers'] == {}

    @pytest.mark.unit
    def test_get_all_usage_summary_with_data(self):
        """Test summary with usage data."""
        tracker = RateLimitTracker()

        tracker.record_request('groq', 'llama-3.1-8b', 100, 50)
        tracker.record_request('groq', 'llama-3.3-70b', 200, 100)
        tracker.record_request('cohere', 'command-r', 150, 75)

        summary = tracker.get_all_usage_summary()

        assert 'groq' in summary['providers']
        assert 'cohere' in summary['providers']

        groq_summary = summary['providers']['groq']
        assert groq_summary['total_requests_today'] == 2
        assert groq_summary['total_tokens_today'] == 450  # 150 + 300
        assert 'llama-3.1-8b' in groq_summary['models']
        assert 'llama-3.3-70b' in groq_summary['models']

        cohere_summary = summary['providers']['cohere']
        assert cohere_summary['total_requests_today'] == 1
        assert cohere_summary['total_tokens_today'] == 225

    @pytest.mark.unit
    def test_get_all_usage_summary_by_model(self):
        """Test that summary includes per-model breakdown."""
        tracker = RateLimitTracker()

        tracker.record_request('groq', 'model-a', 100, 50)
        tracker.record_request('groq', 'model-b', 200, 100)

        summary = tracker.get_all_usage_summary()

        by_model = summary['providers']['groq']['by_model']

        assert by_model['model-a']['requests_today'] == 1
        assert by_model['model-a']['tokens_today'] == 150
        assert by_model['model-b']['requests_today'] == 1
        assert by_model['model-b']['tokens_today'] == 300


class TestClearAndReset:
    """Tests for clearing and resetting tracker data."""

    @pytest.mark.unit
    def test_clear_resets_all_data(self):
        """Test that clear resets all tracking data."""
        tracker = RateLimitTracker()

        tracker.record_request('groq', 'model', 100, 50)
        tracker.record_request('cohere', 'model', 200, 100)

        tracker.clear()

        assert tracker._usage['providers'] == {}
        assert tracker.get_usage('groq') == {}
        assert tracker.get_usage('cohere') == {}

    @pytest.mark.unit
    def test_clear_deletes_tracker_file(self, tmp_path):
        """Test that clear deletes the tracker file."""
        tracker_path = tmp_path / "tracker.json"
        tracker = RateLimitTracker(str(tracker_path))

        tracker.record_request('groq', 'model', 100, 50)
        assert tracker_path.exists()

        tracker.clear()

        assert not tracker_path.exists()

    @pytest.mark.unit
    def test_reset_provider(self):
        """Test resetting a specific provider."""
        tracker = RateLimitTracker()

        tracker.record_request('groq', 'model', 100, 50)
        tracker.record_request('cohere', 'model', 200, 100)

        tracker.reset_provider('groq')

        assert tracker.get_usage('groq') == {}
        assert tracker.get_usage('cohere', 'model')['requests_today'] == 1

    @pytest.mark.unit
    def test_reset_nonexistent_provider(self):
        """Test resetting a nonexistent provider does nothing."""
        tracker = RateLimitTracker()
        tracker.record_request('groq', 'model', 100, 50)

        # Should not raise an error
        tracker.reset_provider('nonexistent')

        # Other data should be preserved
        assert tracker.get_usage('groq', 'model')['requests_today'] == 1

    @pytest.mark.unit
    def test_reset_provider_saves_to_file(self, tmp_path):
        """Test that reset_provider saves changes to file."""
        tracker_path = tmp_path / "tracker.json"
        tracker = RateLimitTracker(str(tracker_path))

        tracker.record_request('groq', 'model', 100, 50)
        tracker.record_request('cohere', 'model', 200, 100)

        tracker.reset_provider('groq')

        # Reload from file
        tracker2 = RateLimitTracker(str(tracker_path))

        assert tracker2.get_usage('groq') == {}
        assert tracker2.get_usage('cohere', 'model')['requests_today'] == 1


class TestAsyncMethods:
    """Tests for async methods."""

    @pytest.mark.asyncio
    async def test_record_request_async(self, tmp_path):
        """Test async request recording."""
        tracker_path = tmp_path / "tracker.json"
        tracker = RateLimitTracker(str(tracker_path))

        await tracker.record_request_async(
            'groq', 'model',
            input_tokens=100,
            output_tokens=50
        )

        usage = tracker.get_usage('groq', 'model')
        assert usage['requests_today'] == 1
        assert usage['tokens_today'] == 150

    @pytest.mark.asyncio
    async def test_record_request_async_with_error(self):
        """Test async request recording with error."""
        tracker = RateLimitTracker()

        await tracker.record_request_async(
            'groq', 'model',
            success=False,
            error_message='Test error'
        )

        usage = tracker.get_usage('groq', 'model')
        assert len(usage['errors']) == 1
        assert usage['errors'][0]['message'] == 'Test error'

    @pytest.mark.asyncio
    async def test_load_tracker_async(self, tmp_path):
        """Test async tracker loading."""
        tracker_path = tmp_path / "tracker.json"

        existing_data = {
            'providers': {
                'groq': {
                    'model': {
                        'requests_today': 5,
                        'requests_this_month': 50,
                        'tokens_today': 1000,
                        'tokens_this_month': 10000,
                        'input_tokens_today': 400,
                        'output_tokens_today': 600,
                        'total_requests': 100,
                        'total_tokens': 20000,
                        'last_request': None,
                        'errors': []
                    }
                }
            },
            'last_reset': {
                'daily': datetime.now().date().isoformat(),
                'monthly': datetime.now().strftime('%Y-%m')
            },
            'created_at': '2025-11-01T00:00:00'
        }

        tracker_path.write_text(json.dumps(existing_data))

        tracker = RateLimitTracker(str(tracker_path))
        await tracker._load_tracker_async()

        usage = tracker.get_usage('groq', 'model')
        assert usage['requests_today'] == 5


class TestPersistence:
    """Tests for file persistence."""

    @pytest.mark.unit
    def test_save_tracker_creates_file(self, tmp_path):
        """Test that saving creates the tracker file."""
        tracker_path = tmp_path / "new_tracker.json"
        tracker = RateLimitTracker(str(tracker_path))

        tracker.record_request('groq', 'model', 100, 50)

        assert tracker_path.exists()

        content = json.loads(tracker_path.read_text())
        assert 'providers' in content
        assert 'groq' in content['providers']

    @pytest.mark.unit
    def test_persistence_across_sessions(self, tmp_path):
        """Test that data persists across tracker instances."""
        tracker_path = tmp_path / "tracker.json"

        # Session 1
        tracker1 = RateLimitTracker(str(tracker_path))
        tracker1.record_request('groq', 'model', 100, 50)

        # Session 2 - new instance, same file
        tracker2 = RateLimitTracker(str(tracker_path))
        tracker2.record_request('groq', 'model', 200, 100)

        usage = tracker2.get_usage('groq', 'model')

        # Should have accumulated data from both sessions
        assert usage['requests_today'] == 2
        assert usage['tokens_today'] == 450

    @pytest.mark.unit
    def test_save_without_file_path(self):
        """Test that saving without file path does nothing."""
        tracker = RateLimitTracker()

        # Should not raise an error
        tracker._save_tracker()
        tracker.record_request('groq', 'model', 100, 50)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.unit
    def test_ensure_provider_model_creates_structure(self):
        """Test that _ensure_provider_model creates nested structure."""
        tracker = RateLimitTracker()

        tracker._ensure_provider_model('new_provider', 'new_model')

        assert 'new_provider' in tracker._usage['providers']
        assert 'new_model' in tracker._usage['providers']['new_provider']

        model_data = tracker._usage['providers']['new_provider']['new_model']
        assert model_data['requests_today'] == 0
        assert model_data['total_tokens'] == 0
        assert model_data['errors'] == []

    @pytest.mark.unit
    def test_check_and_reset_with_missing_last_reset(self):
        """Test reset check with missing last_reset data."""
        tracker = RateLimitTracker()

        # Remove last_reset to simulate corrupted data
        del tracker._usage['last_reset']

        # Current implementation doesn't handle this gracefully - it will raise KeyError
        # This test documents the current behavior
        with pytest.raises(KeyError):
            tracker._check_and_reset()

    @pytest.mark.unit
    def test_zero_token_request(self):
        """Test recording request with zero tokens."""
        tracker = RateLimitTracker()

        tracker.record_request('groq', 'model', 0, 0)

        usage = tracker.get_usage('groq', 'model')
        assert usage['requests_today'] == 1
        assert usage['tokens_today'] == 0

    @pytest.mark.unit
    def test_large_token_counts(self):
        """Test recording requests with large token counts."""
        tracker = RateLimitTracker()

        tracker.record_request('groq', 'model', 100000, 50000)

        usage = tracker.get_usage('groq', 'model')
        assert usage['tokens_today'] == 150000
        assert usage['input_tokens_today'] == 100000
        assert usage['output_tokens_today'] == 50000


class TestConcurrentAccess:
    """Tests for concurrent access and race conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_async_writes_preserve_all_requests(self):
        """Test that concurrent async writes don't lose data."""
        import asyncio
        tracker = RateLimitTracker()

        async def record_batch(provider_suffix: str, count: int):
            for i in range(count):
                await tracker.record_request_async(
                    f'provider_{provider_suffix}',
                    'model',
                    input_tokens=10,
                    output_tokens=5
                )

        # Run 5 concurrent batches of 10 requests each
        await asyncio.gather(
            record_batch('a', 10),
            record_batch('b', 10),
            record_batch('c', 10),
            record_batch('d', 10),
            record_batch('e', 10),
        )

        # Verify all providers have correct counts
        for suffix in ['a', 'b', 'c', 'd', 'e']:
            usage = tracker.get_usage(f'provider_{suffix}', 'model')
            assert usage['requests_today'] == 10, f"provider_{suffix} lost requests"
            assert usage['tokens_today'] == 150, f"provider_{suffix} lost tokens"

    @pytest.mark.asyncio
    async def test_concurrent_writes_to_same_provider(self):
        """Test concurrent writes to same provider/model accumulate correctly."""
        import asyncio
        tracker = RateLimitTracker()

        async def record_one():
            await tracker.record_request_async('groq', 'model', 100, 50)

        # 20 concurrent requests to same provider
        await asyncio.gather(*[record_one() for _ in range(20)])

        usage = tracker.get_usage('groq', 'model')
        assert usage['requests_today'] == 20
        assert usage['tokens_today'] == 3000  # 20 * 150
        assert usage['total_requests'] == 20

    @pytest.mark.unit
    def test_sequential_rapid_writes_accumulate_correctly(self):
        """Test that rapid sequential writes don't lose data."""
        tracker = RateLimitTracker()

        # Simulate rapid-fire requests
        for i in range(100):
            tracker.record_request('groq', 'model', i, i * 2)

        usage = tracker.get_usage('groq', 'model')
        assert usage['requests_today'] == 100
        # Sum of i from 0 to 99 = 4950
        # Sum of i*2 from 0 to 99 = 9900
        # Total = 14850
        expected_tokens = sum(i + i * 2 for i in range(100))
        assert usage['tokens_today'] == expected_tokens
        assert usage['total_requests'] == 100


class TestDateBoundaryCrossings:
    """Tests for date and time boundary edge cases."""

    @pytest.mark.unit
    def test_daily_reset_on_date_change(self, tmp_path):
        """Test that daily counters reset when date changes."""
        tracker_path = tmp_path / "tracker.json"

        # Create tracker with yesterday's date
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
        existing_data = {
            'providers': {
                'groq': {
                    'model': {
                        'requests_today': 50,
                        'requests_this_month': 500,
                        'tokens_today': 10000,
                        'tokens_this_month': 100000,
                        'input_tokens_today': 4000,
                        'output_tokens_today': 6000,
                        'total_requests': 1000,
                        'total_tokens': 200000,
                        'last_request': None,
                        'errors': []
                    }
                }
            },
            'last_reset': {
                'daily': yesterday,
                'monthly': datetime.now().strftime('%Y-%m')
            },
            'created_at': '2025-01-01T00:00:00'
        }

        tracker_path.write_text(json.dumps(existing_data))
        tracker = RateLimitTracker(str(tracker_path))

        usage = tracker.get_usage('groq', 'model')

        # Daily counters should be reset
        assert usage['requests_today'] == 0
        assert usage['tokens_today'] == 0
        assert usage['input_tokens_today'] == 0
        assert usage['output_tokens_today'] == 0

        # Monthly and total should be preserved
        assert usage['requests_this_month'] == 500
        assert usage['total_requests'] == 1000
        assert usage['total_tokens'] == 200000

    @pytest.mark.unit
    def test_monthly_reset_on_month_change(self, tmp_path):
        """Test that monthly counters reset when month changes."""
        tracker_path = tmp_path / "tracker.json"

        # Create tracker with last month's date
        today = datetime.now()
        if today.month == 1:
            last_month = f"{today.year - 1}-12"
        else:
            last_month = f"{today.year}-{today.month - 1:02d}"

        existing_data = {
            'providers': {
                'groq': {
                    'model': {
                        'requests_today': 50,
                        'requests_this_month': 500,
                        'tokens_today': 10000,
                        'tokens_this_month': 100000,
                        'input_tokens_today': 4000,
                        'output_tokens_today': 6000,
                        'total_requests': 1000,
                        'total_tokens': 200000,
                        'last_request': None,
                        'errors': []
                    }
                }
            },
            'last_reset': {
                'daily': (datetime.now() - timedelta(days=1)).date().isoformat(),
                'monthly': last_month
            },
            'created_at': '2025-01-01T00:00:00'
        }

        tracker_path.write_text(json.dumps(existing_data))
        tracker = RateLimitTracker(str(tracker_path))

        usage = tracker.get_usage('groq', 'model')

        # Both daily and monthly should be reset
        assert usage['requests_today'] == 0
        assert usage['requests_this_month'] == 0
        assert usage['tokens_today'] == 0
        assert usage['tokens_this_month'] == 0

        # Total should be preserved
        assert usage['total_requests'] == 1000
        assert usage['total_tokens'] == 200000

    @pytest.mark.unit
    def test_request_during_day_transition_triggers_reset(self, tmp_path):
        """Test that recording a request after midnight triggers daily reset."""
        tracker_path = tmp_path / "tracker.json"
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()

        existing_data = {
            'providers': {
                'groq': {
                    'model': {
                        'requests_today': 100,
                        'requests_this_month': 500,
                        'tokens_today': 20000,
                        'tokens_this_month': 100000,
                        'input_tokens_today': 8000,
                        'output_tokens_today': 12000,
                        'total_requests': 1000,
                        'total_tokens': 200000,
                        'last_request': None,
                        'errors': []
                    }
                }
            },
            'last_reset': {
                'daily': yesterday,
                'monthly': datetime.now().strftime('%Y-%m')
            },
            'created_at': '2025-01-01T00:00:00'
        }

        tracker_path.write_text(json.dumps(existing_data))
        tracker = RateLimitTracker(str(tracker_path))

        # Record a new request - this should reset daily counters first
        tracker.record_request('groq', 'model', 50, 25)

        usage = tracker.get_usage('groq', 'model')

        # Should only have the one new request
        assert usage['requests_today'] == 1
        assert usage['tokens_today'] == 75
        # Monthly should accumulate
        assert usage['requests_this_month'] == 501
        # Total should accumulate
        assert usage['total_requests'] == 1001

    @pytest.mark.unit
    def test_multiple_providers_reset_independently(self, tmp_path):
        """Test that all providers reset on day change."""
        tracker_path = tmp_path / "tracker.json"
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()

        existing_data = {
            'providers': {
                'groq': {
                    'model': {
                        'requests_today': 100,
                        'requests_this_month': 500,
                        'tokens_today': 20000,
                        'tokens_this_month': 100000,
                        'input_tokens_today': 8000,
                        'output_tokens_today': 12000,
                        'total_requests': 1000,
                        'total_tokens': 200000,
                        'last_request': None,
                        'errors': []
                    }
                },
                'cerebras': {
                    'llama': {
                        'requests_today': 200,
                        'requests_this_month': 800,
                        'tokens_today': 30000,
                        'tokens_this_month': 150000,
                        'input_tokens_today': 10000,
                        'output_tokens_today': 20000,
                        'total_requests': 2000,
                        'total_tokens': 400000,
                        'last_request': None,
                        'errors': []
                    }
                }
            },
            'last_reset': {
                'daily': yesterday,
                'monthly': datetime.now().strftime('%Y-%m')
            },
            'created_at': '2025-01-01T00:00:00'
        }

        tracker_path.write_text(json.dumps(existing_data))
        tracker = RateLimitTracker(str(tracker_path))

        # Both providers should have daily counters reset
        groq_usage = tracker.get_usage('groq', 'model')
        cerebras_usage = tracker.get_usage('cerebras', 'llama')

        assert groq_usage['requests_today'] == 0
        assert cerebras_usage['requests_today'] == 0
        assert groq_usage['tokens_today'] == 0
        assert cerebras_usage['tokens_today'] == 0

        # Totals should be preserved
        assert groq_usage['total_requests'] == 1000
        assert cerebras_usage['total_requests'] == 2000


class TestQuotaEnforcement:
    """Tests for quota checking and enforcement behavior."""

    @pytest.mark.unit
    def test_should_allow_request_when_under_quota(self):
        """Test that requests are allowed when under quota."""
        tracker = RateLimitTracker()
        tracker.record_request('groq', 'model', 100, 50)

        limits = ProviderLimits(requests_per_day=100, tokens_per_day=10000)
        remaining = tracker.get_remaining_quota('groq', 'model', limits)

        # 99 requests remaining, should allow
        assert remaining['requests_remaining_today'] == 99
        assert remaining['requests_remaining_today'] > 0

    @pytest.mark.unit
    def test_should_block_request_when_at_quota(self):
        """Test that quota shows zero when limit reached."""
        tracker = RateLimitTracker()

        # Use up exactly the quota
        for _ in range(100):
            tracker.record_request('groq', 'model', 10, 5)

        limits = ProviderLimits(requests_per_day=100)
        remaining = tracker.get_remaining_quota('groq', 'model', limits)

        # Should show 0 remaining
        assert remaining['requests_remaining_today'] == 0

    @pytest.mark.unit
    def test_should_block_request_when_over_quota(self):
        """Test that quota doesn't go negative when over limit."""
        tracker = RateLimitTracker()

        # Go over quota
        for _ in range(150):
            tracker.record_request('groq', 'model', 10, 5)

        limits = ProviderLimits(requests_per_day=100)
        remaining = tracker.get_remaining_quota('groq', 'model', limits)

        # Should show 0, not -50
        assert remaining['requests_remaining_today'] == 0
        # But usage should show actual count
        assert remaining['usage_today'] == 150

    @pytest.mark.unit
    def test_token_quota_reached_before_request_quota(self):
        """Test that token limit can be reached before request limit."""
        tracker = RateLimitTracker()

        # 10 requests with 2000 tokens each = 20000 tokens total
        for _ in range(10):
            tracker.record_request('groq', 'model', 1000, 1000)

        limits = ProviderLimits(requests_per_day=100, tokens_per_day=20000)
        remaining = tracker.get_remaining_quota('groq', 'model', limits)

        # Plenty of requests remaining
        assert remaining['requests_remaining_today'] == 90
        # But tokens are exhausted
        assert remaining['tokens_remaining_today'] == 0

    @pytest.mark.unit
    def test_monthly_quota_can_exhaust_before_daily(self):
        """Test monthly quota exhaustion with daily quota available."""
        tracker = RateLimitTracker()

        # Use up monthly quota over multiple days
        # Simulate by directly setting the monthly counter
        tracker._ensure_provider_model('groq', 'model')
        tracker._usage['providers']['groq']['model']['requests_this_month'] = 1000
        tracker._usage['providers']['groq']['model']['requests_today'] = 10

        limits = ProviderLimits(requests_per_day=100, requests_per_month=1000)
        remaining = tracker.get_remaining_quota('groq', 'model', limits)

        # Daily quota available
        assert remaining['requests_remaining_today'] == 90
        # Monthly quota exhausted
        assert remaining['requests_remaining_month'] == 0

    @pytest.mark.unit
    def test_is_limit_approaching_triggers_at_threshold(self):
        """Test that warnings trigger at exactly the threshold."""
        tracker = RateLimitTracker()

        # Use 91 out of 100 requests (9 remaining = 9% < 10% threshold)
        for _ in range(91):
            tracker.record_request('groq', 'model', 10, 5)

        limits = ProviderLimits(requests_per_day=100)
        warnings = tracker.is_limit_approaching('groq', 'model', limits, threshold=0.1)

        assert warnings['approaching_daily_request_limit'] is True
        assert 'Only 9 requests remaining today' in warnings['message']

    @pytest.mark.unit
    def test_is_limit_approaching_not_triggered_above_threshold(self):
        """Test that warnings don't trigger above threshold."""
        tracker = RateLimitTracker()

        # Use 89 out of 100 requests (11 remaining = 11% > 10% threshold)
        for _ in range(89):
            tracker.record_request('groq', 'model', 10, 5)

        limits = ProviderLimits(requests_per_day=100)
        warnings = tracker.is_limit_approaching('groq', 'model', limits, threshold=0.1)

        assert warnings['approaching_daily_request_limit'] is False
        assert warnings['message'] is None

    @pytest.mark.unit
    def test_quota_check_handles_multiple_limit_types_simultaneously(self):
        """Test tracking when multiple quota types are approaching limits."""
        tracker = RateLimitTracker()

        # Set up usage that approaches multiple limits
        tracker._ensure_provider_model('groq', 'model')
        model_data = tracker._usage['providers']['groq']['model']
        model_data['requests_today'] = 95  # 5 remaining of 100
        model_data['requests_this_month'] = 950  # 50 remaining of 1000
        model_data['tokens_today'] = 48000  # 2000 remaining of 50000

        limits = ProviderLimits(
            requests_per_day=100,
            requests_per_month=1000,
            tokens_per_day=50000
        )

        warnings = tracker.is_limit_approaching('groq', 'model', limits, threshold=0.1)

        # All limits should be flagged
        assert warnings['approaching_daily_request_limit'] is True
        assert warnings['approaching_monthly_request_limit'] is True
        assert warnings['approaching_daily_token_limit'] is True

        # Message should contain all warnings
        assert '5 requests remaining today' in warnings['message']
        assert '50 requests remaining this month' in warnings['message']
        assert '2000 tokens remaining today' in warnings['message']

    @pytest.mark.unit
    def test_quota_enforcement_with_real_decision_making(self):
        """Test using quota info to make real throttling decisions."""
        tracker = RateLimitTracker()

        # Simulate a rate limit enforcement function
        def should_allow_request(tracker, provider, model, limits, min_remaining=1):
            """Return True if request should be allowed."""
            remaining = tracker.get_remaining_quota(provider, model, limits)

            # Check all applicable limits
            if remaining['requests_remaining_today'] is not None:
                if remaining['requests_remaining_today'] < min_remaining:
                    return False

            if remaining['requests_remaining_month'] is not None:
                if remaining['requests_remaining_month'] < min_remaining:
                    return False

            if remaining['tokens_remaining_today'] is not None:
                if remaining['tokens_remaining_today'] < min_remaining:
                    return False

            return True

        limits = ProviderLimits(requests_per_day=3)

        # First two requests should be allowed
        assert should_allow_request(tracker, 'groq', 'model', limits) is True
        tracker.record_request('groq', 'model', 10, 5)

        assert should_allow_request(tracker, 'groq', 'model', limits) is True
        tracker.record_request('groq', 'model', 10, 5)

        # Third request - only 1 remaining, still allowed
        assert should_allow_request(tracker, 'groq', 'model', limits) is True
        tracker.record_request('groq', 'model', 10, 5)

        # Fourth request should be blocked (0 remaining)
        assert should_allow_request(tracker, 'groq', 'model', limits) is False
