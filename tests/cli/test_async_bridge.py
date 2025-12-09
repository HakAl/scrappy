"""Tests for ThreadSafeAsyncBridge - tests behavior, not implementation."""

import pytest
from unittest.mock import Mock

from scrappy.cli.textual_app import ThreadSafeAsyncBridge


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


