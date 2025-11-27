"""Tests for ThreadSafeAsyncBridge - tests behavior, not implementation."""

import pytest
from unittest.mock import Mock

from src.cli.textual_app import ThreadSafeAsyncBridge


class TestThreadSafeAsyncBridge:
    """Unit tests for ThreadSafeAsyncBridge."""

    @pytest.fixture
    def mock_app(self):
        """Create mock app for testing."""
        return Mock()

    @pytest.fixture
    def bridge(self, mock_app):
        """Create bridge instance for testing."""
        return ThreadSafeAsyncBridge(mock_app)

    # --- Defensive Check Tests (Bug 3 Fix) ---

    def test_provide_result_with_unknown_prompt_id_is_safe(self, bridge):
        """provide_result gracefully handles unknown/stale prompt IDs."""
        # Never registered this prompt ID
        # Should not raise KeyError
        bridge.provide_result("unknown-id-12345", "some result")

    def test_provide_result_with_already_cleaned_prompt_is_safe(self, bridge):
        """provide_result handles race condition where prompt was already cleaned up."""
        # Simulate the race condition scenario:
        # 1. Worker registers prompt, waits, then cleans up
        # 2. Main thread tries to provide_result with now-stale ID
        # This shouldn't crash
        bridge.provide_result("stale-prompt-id", True)
