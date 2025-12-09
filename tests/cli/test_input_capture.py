"""Tests for InputCaptureManager - tests behavior, not implementation."""

import pytest
from unittest.mock import Mock

from scrappy.cli.input_capture import InputCaptureManager, InputRequest


class TestInputCaptureManager:
    """Unit tests for InputCaptureManager."""

    @pytest.fixture
    def mock_bridge(self):
        """Create mock bridge for testing."""
        bridge = Mock()
        bridge.provide_result = Mock()
        return bridge

    @pytest.fixture
    def manager(self, mock_bridge):
        """Create manager with mock bridge."""
        return InputCaptureManager(mock_bridge)

    # --- State Transition Tests ---

    def test_initially_not_capturing(self, manager):
        """Manager starts in non-capturing state."""
        assert manager.is_capturing is False

    def test_enter_capture_mode_sets_capturing(self, manager):
        """Entering capture mode sets is_capturing to True."""
        manager.enter_capture_mode("id1", "Question?", "confirm")
        assert manager.is_capturing is True

    def test_exit_capture_mode_clears_capturing(self, manager):
        """Exiting capture mode clears is_capturing."""
        manager.enter_capture_mode("id1", "Question?", "confirm")
        manager.exit_capture_mode()
        assert manager.is_capturing is False

    def test_current_type_returns_capture_type(self, manager):
        """current_type property returns the type of current capture."""
        assert manager.current_type is None
        manager.enter_capture_mode("id1", "Question?", "confirm")
        assert manager.current_type == "confirm"
        manager.exit_capture_mode()
        manager.enter_capture_mode("id2", "Name?", "prompt")
        assert manager.current_type == "prompt"

    # --- Confirm Input Parsing Tests ---



    # --- Prompt Input Tests ---




    # --- Cancel Tests ---




    # --- Defensive Null Check Tests (Bug 3 Fix) ---





    # --- Queue Tests (Concurrent Prompts) ---

    def test_second_prompt_queued_when_capturing(self, manager):
        """Second prompt is queued, not immediately active."""
        manager.enter_capture_mode("id1", "First?", "confirm")
        manager.enter_capture_mode("id2", "Second?", "prompt")

        # Still on first prompt
        assert manager.is_capturing is True
        # Verify we're still on first prompt by checking current_type
        assert manager.current_type == "confirm"

    def test_exit_returns_queued_request(self, manager, mock_bridge):
        """Exiting capture mode returns next queued request."""
        manager.enter_capture_mode("id1", "First?", "confirm")
        manager.enter_capture_mode("id2", "Second?", "prompt", default="default")

        # Handle first and exit
        manager.handle_captured_input("y")
        next_request = manager.exit_capture_mode()

        assert next_request is not None
        assert next_request.prompt_id == "id2"
        assert next_request.input_type == "prompt"
        assert next_request.default == "default"
        assert next_request.message == "Second?"

    def test_exit_returns_none_when_queue_empty(self, manager, mock_bridge):
        """Exiting with empty queue returns None."""
        manager.enter_capture_mode("id1", "Question?", "confirm")
        manager.handle_captured_input("y")
        next_request = manager.exit_capture_mode()

        assert next_request is None

    def test_multiple_queued_requests_returned_in_order(self, manager, mock_bridge):
        """Multiple queued requests are returned in FIFO order."""
        manager.enter_capture_mode("id1", "First?", "confirm")
        manager.enter_capture_mode("id2", "Second?", "prompt")
        manager.enter_capture_mode("id3", "Third?", "confirm")

        # Handle first
        manager.handle_captured_input("y")
        second = manager.exit_capture_mode()
        assert second.prompt_id == "id2"

        # Re-enter for second
        manager.enter_capture_mode(second.prompt_id, second.message, second.input_type, second.default)
        manager.handle_captured_input("value")
        third = manager.exit_capture_mode()
        assert third.prompt_id == "id3"

        # Re-enter for third
        manager.enter_capture_mode(third.prompt_id, third.message, third.input_type, third.default)
        manager.handle_captured_input("n")
        fourth = manager.exit_capture_mode()
        assert fourth is None


class TestInputRequest:
    """Tests for InputRequest dataclass."""

    def test_input_request_creation(self):
        """InputRequest can be created with all fields."""
        request = InputRequest(
            prompt_id="id1",
            message="Enter name:",
            input_type="prompt",
            default="Guest"
        )
        assert request.prompt_id == "id1"
        assert request.message == "Enter name:"
        assert request.input_type == "prompt"
        assert request.default == "Guest"

    def test_input_request_default_empty(self):
        """InputRequest defaults to empty string for default."""
        request = InputRequest(
            prompt_id="id1",
            message="Continue?",
            input_type="confirm"
        )
        assert request.default == ""
