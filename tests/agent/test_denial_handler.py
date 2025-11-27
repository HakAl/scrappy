"""Tests for denial handler implementations."""

import pytest
from src.agent.denial_handler import (
    InteractiveDenialHandler,
    AutoStopDenialHandler,
    ContinueDenialHandler,
)
from src.agent.types import DenialHandlerResult
from tests.helpers import StubAgentUI


class TestInteractiveDenialHandler:
    """Tests for InteractiveDenialHandler."""

    def test_user_confirms_stop_returns_should_stop_true(self):
        """When user confirms stop, should_stop is True."""
        ui = StubAgentUI(prompt_confirm_responses=[True])
        handler = InteractiveDenialHandler(ui)

        result = handler.handle_denial("write_file", denial_count=1)

        assert result.should_stop is True
        assert "stopped by user" in result.message.lower()

    def test_user_declines_stop_returns_should_stop_false(self):
        """When user declines stop, should_stop is False."""
        ui = StubAgentUI(prompt_confirm_responses=[False])
        handler = InteractiveDenialHandler(ui)

        result = handler.handle_denial("write_file", denial_count=1)

        assert result.should_stop is False
        assert "different approach" in result.message.lower()

    def test_prompt_message_includes_action_name(self):
        """Prompt should mention the action that was denied."""
        ui = StubAgentUI(prompt_confirm_responses=[False])
        handler = InteractiveDenialHandler(ui)

        handler.handle_denial("run_command", denial_count=1)

        messages = ui.get_shown_messages()
        assert any("run_command" in msg for msg in messages)

    def test_returns_denial_handler_result_type(self):
        """Handler should return DenialHandlerResult dataclass."""
        ui = StubAgentUI(prompt_confirm_responses=[False])
        handler = InteractiveDenialHandler(ui)

        result = handler.handle_denial("write_file", denial_count=1)

        assert isinstance(result, DenialHandlerResult)


class TestAutoStopDenialHandler:
    """Tests for AutoStopDenialHandler."""

    def test_stops_after_max_denials(self):
        """Should stop after reaching max denials."""
        handler = AutoStopDenialHandler(max_denials=3)

        result = handler.handle_denial("write_file", denial_count=3)

        assert result.should_stop is True

    def test_stops_when_over_max_denials(self):
        """Should stop when over max denials."""
        handler = AutoStopDenialHandler(max_denials=3)

        result = handler.handle_denial("write_file", denial_count=5)

        assert result.should_stop is True

    def test_continues_before_max_denials(self):
        """Should continue before reaching max denials."""
        handler = AutoStopDenialHandler(max_denials=3)

        result = handler.handle_denial("write_file", denial_count=2)

        assert result.should_stop is False

    def test_message_includes_denial_count(self):
        """Message should include current denial count."""
        handler = AutoStopDenialHandler(max_denials=5)

        result = handler.handle_denial("write_file", denial_count=2)

        assert "2/5" in result.message

    def test_stop_message_includes_denial_count(self):
        """Stop message should include final denial count."""
        handler = AutoStopDenialHandler(max_denials=3)

        result = handler.handle_denial("write_file", denial_count=3)

        assert "3" in result.message

    def test_default_max_denials_is_three(self):
        """Default max denials should be 3."""
        handler = AutoStopDenialHandler()

        # Should continue at 2
        result = handler.handle_denial("write_file", denial_count=2)
        assert result.should_stop is False

        # Should stop at 3
        result = handler.handle_denial("write_file", denial_count=3)
        assert result.should_stop is True


class TestContinueDenialHandler:
    """Tests for ContinueDenialHandler."""

    def test_always_returns_should_stop_false(self):
        """Should always return should_stop=False."""
        handler = ContinueDenialHandler()

        # Even with many denials
        result = handler.handle_denial("write_file", denial_count=100)

        assert result.should_stop is False

    def test_message_asks_for_different_approach(self):
        """Message should ask for different approach."""
        handler = ContinueDenialHandler()

        result = handler.handle_denial("write_file", denial_count=1)

        assert "different approach" in result.message.lower()

    def test_message_includes_action_name(self):
        """Message should include the denied action name."""
        handler = ContinueDenialHandler()

        result = handler.handle_denial("run_command", denial_count=1)

        assert "run_command" in result.message


class TestDenialHandlerProtocolCompliance:
    """Tests verifying protocol compliance."""

    def test_interactive_handler_implements_protocol(self):
        """InteractiveDenialHandler should implement DenialHandlerProtocol."""
        from src.agent.protocols import DenialHandlerProtocol

        ui = StubAgentUI()
        handler = InteractiveDenialHandler(ui)

        # Protocol check - has required method
        assert hasattr(handler, 'handle_denial')
        assert callable(handler.handle_denial)

    def test_auto_stop_handler_implements_protocol(self):
        """AutoStopDenialHandler should implement DenialHandlerProtocol."""
        from src.agent.protocols import DenialHandlerProtocol

        handler = AutoStopDenialHandler()

        # Protocol check - has required method
        assert hasattr(handler, 'handle_denial')
        assert callable(handler.handle_denial)

    def test_continue_handler_implements_protocol(self):
        """ContinueDenialHandler should implement DenialHandlerProtocol."""
        from src.agent.protocols import DenialHandlerProtocol

        handler = ContinueDenialHandler()

        # Protocol check - has required method
        assert hasattr(handler, 'handle_denial')
        assert callable(handler.handle_denial)
