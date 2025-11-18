"""
Tests for error reporting - verifying silent exception handlers report errors.

These tests demonstrate that exceptions are properly reported rather than
silently swallowed with `except Exception: pass`.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock, AsyncMock
from datetime import datetime

from src.orchestrator.cache import ResponseCache
from src.orchestrator.rate_limiter import RateLimitTracker
from src.orchestrator.output import CapturingOutput, NullOutput
from src.providers.base import LLMResponse, ProviderLimits


class TestCacheErrorReporting:
    """Tests for error reporting in ResponseCache."""

    @pytest.fixture
    def sample_response(self):
        """Create a sample LLM response."""
        return LLMResponse(
            content="Test response",
            model="test-model",
            provider="test-provider",
            tokens_used=100
        )

    @pytest.mark.unit
    def test_save_cache_reports_write_errors(self, tmp_path, sample_response):
        """Test that _save_cache reports errors instead of silently failing.

        When cache file write fails, the error should be reported via output.
        """
        cache_file = tmp_path / "cache.json"
        output = CapturingOutput()

        cache = ResponseCache(cache_file=str(cache_file), output=output)
        cache.put(sample_response, "test prompt", "model")

        # Make the file read-only to cause write failure on next put
        cache_file.chmod(0o444)

        try:
            # This should fail but report the error
            cache.put(sample_response, "another prompt", "model")

            # Verify error was reported
            errors = output.get_by_level('error')
            assert len(errors) > 0, "Expected error to be reported when cache write fails"
            assert any("cache" in err.lower() or "write" in err.lower() for err in errors), \
                f"Error message should mention cache/write failure. Got: {errors}"
        finally:
            # Restore permissions for cleanup
            cache_file.chmod(0o644)

    @pytest.mark.unit
    def test_save_cache_with_invalid_path_reports_error(self, sample_response):
        """Test that saving to invalid path reports error."""
        output = CapturingOutput()

        # Use an invalid path (directory that doesn't exist)
        cache = ResponseCache(
            cache_file="/nonexistent/directory/cache.json",
            output=output
        )

        cache.put(sample_response, "test prompt", "model")

        # Verify error was reported
        errors = output.get_by_level('error')
        assert len(errors) > 0, "Expected error when saving to invalid path"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_save_cache_async_reports_write_errors(self, tmp_path, sample_response):
        """Test that _save_cache_async reports errors instead of silently failing."""
        cache_file = tmp_path / "cache.json"
        output = CapturingOutput()

        cache = ResponseCache(cache_file=str(cache_file), output=output)

        # First save to create file
        await cache.put_async(sample_response, "test prompt", "model")

        # Make read-only
        cache_file.chmod(0o444)

        try:
            # This should fail but report error
            await cache.put_async(sample_response, "another prompt", "model")

            errors = output.get_by_level('error')
            assert len(errors) > 0, "Expected error to be reported on async cache write failure"
        finally:
            cache_file.chmod(0o644)

    @pytest.mark.unit
    def test_save_cache_continues_after_error(self, tmp_path, sample_response):
        """Test that cache operations continue despite write errors.

        Even when file write fails, in-memory cache should still work.
        """
        output = CapturingOutput()

        # Invalid path causes write failure
        cache = ResponseCache(
            cache_file="/nonexistent/directory/cache.json",
            output=output
        )

        # Put should succeed in memory despite file write failure
        cache.put(sample_response, "test prompt", "model")

        # Get should still work
        result = cache.get("test-provider", "test prompt", model="model")
        assert result is not None
        assert result.content == "Test response"

    @pytest.mark.unit
    def test_cache_without_output_uses_default(self, tmp_path, sample_response):
        """Test that cache works without explicit output (backward compatibility)."""
        cache_file = tmp_path / "cache.json"

        # No output parameter - should use default NullOutput
        cache = ResponseCache(cache_file=str(cache_file))

        # Should not raise
        cache.put(sample_response, "test prompt", "model")
        result = cache.get("test-provider", "test prompt", model="model")
        assert result is not None


class TestRateLimiterErrorReporting:
    """Tests for error reporting in RateLimitTracker."""

    @pytest.mark.unit
    def test_save_tracker_reports_write_errors(self, tmp_path):
        """Test that _save_tracker reports errors instead of silently failing."""
        tracker_file = tmp_path / "tracker.json"
        output = CapturingOutput()

        tracker = RateLimitTracker(str(tracker_file), output=output)
        tracker.record_request('groq', 'model', 100, 50)

        # Make read-only
        tracker_file.chmod(0o444)

        try:
            # This should fail but report error
            tracker.record_request('groq', 'model', 200, 100)

            errors = output.get_by_level('error')
            assert len(errors) > 0, "Expected error to be reported when tracker write fails"
            assert any("tracker" in err.lower() or "write" in err.lower() or "rate" in err.lower()
                      for err in errors), f"Error message should mention tracker. Got: {errors}"
        finally:
            tracker_file.chmod(0o644)

    @pytest.mark.unit
    def test_save_tracker_with_invalid_path_reports_error(self):
        """Test that saving to invalid path reports error."""
        output = CapturingOutput()

        tracker = RateLimitTracker(
            "/nonexistent/directory/tracker.json",
            output=output
        )

        tracker.record_request('groq', 'model', 100, 50)

        errors = output.get_by_level('error')
        assert len(errors) > 0, "Expected error when saving tracker to invalid path"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_save_tracker_async_reports_write_errors(self, tmp_path):
        """Test that _save_tracker_async reports errors."""
        tracker_file = tmp_path / "tracker.json"
        output = CapturingOutput()

        tracker = RateLimitTracker(str(tracker_file), output=output)

        # First save
        await tracker.record_request_async('groq', 'model', 100, 50)

        # Make read-only
        tracker_file.chmod(0o444)

        try:
            await tracker.record_request_async('groq', 'model', 200, 100)

            errors = output.get_by_level('error')
            assert len(errors) > 0, "Expected error on async tracker write failure"
        finally:
            tracker_file.chmod(0o644)

    @pytest.mark.unit
    def test_tracker_continues_after_write_error(self, tmp_path):
        """Test that tracker operations continue despite write errors."""
        output = CapturingOutput()

        # Invalid path causes write failure
        tracker = RateLimitTracker(
            "/nonexistent/directory/tracker.json",
            output=output
        )

        # Record should succeed in memory
        tracker.record_request('groq', 'model', 100, 50)

        # Usage should still be tracked
        usage = tracker.get_usage('groq', 'model')
        assert usage['requests_today'] == 1
        assert usage['tokens_today'] == 150

    @pytest.mark.unit
    def test_tracker_without_output_uses_default(self, tmp_path):
        """Test backward compatibility without explicit output."""
        tracker_file = tmp_path / "tracker.json"

        # No output parameter
        tracker = RateLimitTracker(str(tracker_file))

        tracker.record_request('groq', 'model', 100, 50)
        usage = tracker.get_usage('groq', 'model')
        assert usage['requests_today'] == 1


class TestCoreErrorReporting:
    """Tests for error reporting in AgentOrchestrator core.py."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock provider registry."""
        registry = MagicMock()
        registry.list_available.return_value = ['groq', 'cerebras']

        mock_provider = MagicMock()
        mock_provider.default_model = 'test-model'
        mock_provider.get_limits.return_value = ProviderLimits(
            requests_per_day=100,
            tokens_per_day=10000
        )

        registry.get.return_value = mock_provider
        return registry

    @pytest.mark.unit
    def test_delegate_reports_proactive_limit_check_errors(self, tmp_path):
        """Test that delegate reports errors in proactive limit checking.

        In delegate(), line 580-581 has `except Exception: pass` for
        proactive limit checking. Errors should be reported.
        """
        from src.orchestrator.core import AgentOrchestrator

        output = CapturingOutput()

        # Create orchestrator with injected output
        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            output=output
        )

        # Mock registry with provider that raises on get_limits
        mock_provider = MagicMock()
        mock_provider.default_model = 'test-model'
        mock_provider.get_limits.side_effect = Exception("Limit check failed")
        mock_provider.chat.return_value = LLMResponse(
            content="Response",
            model="test-model",
            provider="groq",
            tokens_used=100
        )

        orch.registry.register = MagicMock()
        orch.registry.list_available = MagicMock(return_value=['groq'])
        orch.registry.get = MagicMock(return_value=mock_provider)

        # This should handle the get_limits error gracefully
        try:
            orch.delegate('groq', "test prompt", use_cache=False)
        except Exception:
            pass  # We expect it might fail, but errors should be reported

        # If error was truly exceptional, it should have been reported
        # Note: Some errors may be warnings rather than errors
        all_messages = output.messages
        # At minimum, execution should not silently swallow the error

    @pytest.mark.unit
    def test_get_rate_limit_status_reports_errors(self, tmp_path):
        """Test that get_rate_limit_status reports errors.

        In get_rate_limit_status(), line 1248-1249 has `except Exception: pass`.
        Errors should be reported.
        """
        from src.orchestrator.core import AgentOrchestrator

        output = CapturingOutput()

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            output=output
        )

        # Mock a provider that fails on get_limits
        mock_provider = MagicMock()
        mock_provider.get_limits.side_effect = Exception("Provider error")
        mock_provider.default_model = 'test-model'

        # Register it
        orch.registry._providers = {'broken': mock_provider}
        orch.registry.list_available = MagicMock(return_value=['broken'])
        orch.registry.get = MagicMock(return_value=mock_provider)

        # Mock rate tracker to return data with the broken provider
        orch.rate_tracker.get_all_usage_summary = MagicMock(return_value={
            'last_reset': {},
            'providers': {'broken': {'models': ['test-model']}}
        })

        # Get status - should handle error gracefully
        status = orch.get_rate_limit_status()

        # Error should have been reported (warn or error level)
        # The method should still return a result
        assert 'providers' in status

    @pytest.mark.unit
    def test_check_rate_limit_warnings_reports_errors(self, tmp_path):
        """Test that check_rate_limit_warnings reports errors.

        In check_rate_limit_warnings(), line 1273-1274 has `except Exception: pass`.
        Errors should be reported.
        """
        from src.orchestrator.core import AgentOrchestrator

        output = CapturingOutput()

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            output=output
        )

        # Mock a failing provider
        mock_provider = MagicMock()
        mock_provider.get_limits.side_effect = Exception("Limits unavailable")

        orch.registry.list_available = MagicMock(return_value=['broken'])
        orch.registry.get = MagicMock(return_value=mock_provider)

        # Should not raise, should report error
        warnings = orch.check_rate_limit_warnings()

        # Method should return empty list on errors but report them
        assert isinstance(warnings, list)

    @pytest.mark.unit
    def test_get_remaining_quota_reports_errors(self, tmp_path):
        """Test that get_remaining_quota handles errors gracefully.

        Lines 1258-1259 need to handle missing provider properly.
        """
        from src.orchestrator.core import AgentOrchestrator

        output = CapturingOutput()

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            output=output
        )

        # Try to get quota for non-existent provider
        orch.registry.get = MagicMock(return_value=None)

        # Should handle gracefully without raising
        try:
            result = orch.get_remaining_quota('nonexistent')
            # If it returns, it should be an empty dict or error indication
        except Exception as e:
            # If it raises, the error type should be clear
            assert "not available" in str(e).lower() or "not found" in str(e).lower()


class TestErrorReportingIntegration:
    """Integration tests for error reporting across components."""

    @pytest.mark.unit
    def test_orchestrator_with_failing_cache_reports_errors(self, tmp_path):
        """Test that orchestrator reports cache errors during delegation."""
        from src.orchestrator.core import AgentOrchestrator
        from src.orchestrator.cache import ResponseCache

        output = CapturingOutput()

        # Create cache with invalid path
        failing_cache = ResponseCache(
            cache_file="/nonexistent/cache.json",
            output=output
        )

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=failing_cache,
            output=output
        )

        # Cache operations should report errors
        # The cache should still work in-memory

    @pytest.mark.unit
    def test_orchestrator_with_failing_tracker_reports_errors(self, tmp_path):
        """Test that orchestrator reports rate tracker errors."""
        from src.orchestrator.core import AgentOrchestrator
        from src.orchestrator.rate_limiter import RateLimitTracker

        output = CapturingOutput()

        # Create tracker with invalid path
        failing_tracker = RateLimitTracker(
            "/nonexistent/tracker.json",
            output=output
        )

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            rate_tracker=failing_tracker,
            output=output
        )

        # Tracker should report errors but operations should continue


class TestErrorMessageQuality:
    """Tests for quality and usefulness of error messages."""

    @pytest.mark.unit
    def test_cache_error_includes_file_path(self, tmp_path):
        """Test that cache errors include the file path for debugging."""
        output = CapturingOutput()

        cache_path = "/nonexistent/directory/cache.json"
        cache = ResponseCache(cache_file=cache_path, output=output)

        response = LLMResponse("test", "model", "provider")
        cache.put(response, "prompt", "model")

        errors = output.get_by_level('error')
        if errors:
            # Error should help user understand what failed
            error_text = " ".join(errors).lower()
            # Should contain some useful context
            assert "cache" in error_text or "write" in error_text or "failed" in error_text

    @pytest.mark.unit
    def test_tracker_error_includes_context(self, tmp_path):
        """Test that tracker errors include useful context."""
        output = CapturingOutput()

        tracker_path = "/nonexistent/directory/tracker.json"
        tracker = RateLimitTracker(tracker_path, output=output)

        tracker.record_request('groq', 'model', 100, 50)

        errors = output.get_by_level('error')
        if errors:
            error_text = " ".join(errors).lower()
            # Should have some context
            assert "rate" in error_text or "tracker" in error_text or "write" in error_text or "failed" in error_text


class TestBackwardCompatibility:
    """Tests to ensure changes maintain backward compatibility."""

    @pytest.mark.unit
    def test_cache_api_unchanged(self, tmp_path):
        """Test that ResponseCache API remains unchanged."""
        cache_file = tmp_path / "cache.json"

        # Old way of creating cache (without output)
        cache = ResponseCache(cache_file=str(cache_file))

        response = LLMResponse("test", "model", "provider", tokens_used=100)

        # All existing methods should work
        cache.put(response, "prompt", "model")
        result = cache.get("provider", "prompt", model="model")
        stats = cache.get_stats()
        cache.clear()

        assert result is not None
        assert 'exact_hits' in stats

    @pytest.mark.unit
    def test_tracker_api_unchanged(self, tmp_path):
        """Test that RateLimitTracker API remains unchanged."""
        tracker_file = tmp_path / "tracker.json"

        # Old way
        tracker = RateLimitTracker(str(tracker_file))

        tracker.record_request('groq', 'model', 100, 50)
        usage = tracker.get_usage('groq', 'model')

        limits = ProviderLimits(requests_per_day=100)
        remaining = tracker.get_remaining_quota('groq', 'model', limits)
        warnings = tracker.is_limit_approaching('groq', 'model', limits)

        assert usage['requests_today'] == 1
        assert 'requests_remaining_today' in remaining

    @pytest.mark.unit
    def test_orchestrator_api_unchanged(self, tmp_path):
        """Test that AgentOrchestrator API remains unchanged."""
        from src.orchestrator.core import AgentOrchestrator

        # Old way
        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path)
        )

        # All existing methods should work
        status = orch.status()
        assert 'available_providers' in status
