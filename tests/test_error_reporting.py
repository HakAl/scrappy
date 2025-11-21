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
    def test_save_cache_with_invalid_path_reports_error(self, tmp_path, sample_response):
        """Test that saving to invalid path reports error."""
        output = CapturingOutput()

        # Create a directory and try to use it as a file path (will fail on write)
        invalid_path = tmp_path / "somedir"
        invalid_path.mkdir()

        cache = ResponseCache(
            cache_file=str(invalid_path),  # Directory, not a file
            output=output
        )

        cache.put(sample_response, "test prompt", "model")

        # Verify error was reported
        errors = output.get_by_level('error')
        assert len(errors) > 0, "Expected error when saving to invalid path"

    @pytest.mark.unit
    def test_save_cache_continues_after_error(self, tmp_path, sample_response):
        """Test that cache operations continue despite write errors.

        Even when file write fails, in-memory cache should still work.
        """
        output = CapturingOutput()

        # Create a directory and try to use it as a file path (will fail on write)
        invalid_path = tmp_path / "another_dir"
        invalid_path.mkdir()

        cache = ResponseCache(
            cache_file=str(invalid_path),  # Directory, not a file
            output=output
        )

        # Put should succeed in memory despite file write failure
        cache.put(sample_response, "test prompt", "model")

        # Get should still work
        result = cache.get("test-provider", "test prompt", model="model")
        assert result is not None
        assert result.content == "Test response"


