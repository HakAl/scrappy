"""
Behavior tests for user interaction implementations.

Tests the three interaction strategies:
- CLIUserInteraction: Delegates to IO
- TUIUserInteraction: Uses bridge for modal dialogs
- AutoApproveInteraction: Returns defaults with logging

Per CLAUDE.md: Focus on behavior tests that prove features work.
"""

import pytest
from unittest.mock import MagicMock, Mock
import threading

from src.cli.user_interaction import (
    CLIUserInteraction,
    TUIUserInteraction,
    AutoApproveInteraction,
    get_user_interaction,
)
from tests.helpers import MockIO


class TestCLIUserInteraction:
    """Test CLI mode interaction - delegates to IO interface."""

    def test_confirm_delegates_to_io_with_default_false(self):
        """Should pass confirm call through to IO."""
        io = MockIO(confirmations=[True])
        interaction = CLIUserInteraction(io)

        result = interaction.confirm("Proceed?", default=False)

        assert result is True

    def test_confirm_returns_io_default_when_no_preset(self):
        """Should return default when no confirmations preset."""
        io = MockIO(confirmations=[])
        interaction = CLIUserInteraction(io)

        result = interaction.confirm("Continue?", default=True)

        assert result is True

    def test_confirm_with_explicit_false(self):
        """Should return False when confirmation is explicitly False."""
        io = MockIO(confirmations=[False])
        interaction = CLIUserInteraction(io)

        result = interaction.confirm("Delete file?", default=True)

        assert result is False

    def test_prompt_delegates_to_io(self):
        """Should pass prompt call through to IO."""
        io = MockIO(inputs=["user input"])
        interaction = CLIUserInteraction(io)

        result = interaction.prompt("Enter name:")

        assert result == "user input"

    def test_prompt_returns_default_when_no_input(self):
        """Should return default when no inputs preset."""
        io = MockIO(inputs=[])
        interaction = CLIUserInteraction(io)

        result = interaction.prompt("Enter path:", default="/tmp")

        assert result == "/tmp"

    def test_multiple_confirms_in_sequence(self):
        """Should consume confirmations in order."""
        io = MockIO(confirmations=[True, False, True])
        interaction = CLIUserInteraction(io)

        r1 = interaction.confirm("First?")
        r2 = interaction.confirm("Second?")
        r3 = interaction.confirm("Third?")

        assert r1 is True
        assert r2 is False
        assert r3 is True

    def test_multiple_prompts_in_sequence(self):
        """Should consume inputs in order."""
        io = MockIO(inputs=["first", "second", "third"])
        interaction = CLIUserInteraction(io)

        r1 = interaction.prompt("Q1:")
        r2 = interaction.prompt("Q2:")
        r3 = interaction.prompt("Q3:")

        assert r1 == "first"
        assert r2 == "second"
        assert r3 == "third"


class TestTUIUserInteraction:
    """Test TUI mode interaction - uses bridge for modals."""

    def test_confirm_calls_bridge_blocking_confirm(self):
        """Should delegate confirm to bridge.blocking_confirm."""
        bridge = MagicMock()
        bridge.blocking_confirm.return_value = True
        interaction = TUIUserInteraction(bridge)

        result = interaction.confirm("Proceed?", default=False)

        bridge.blocking_confirm.assert_called_once_with("Proceed?")
        assert result is True

    def test_confirm_with_false_result(self):
        """Should return False from bridge."""
        bridge = MagicMock()
        bridge.blocking_confirm.return_value = False
        interaction = TUIUserInteraction(bridge)

        result = interaction.confirm("Delete?", default=True)

        assert result is False

    def test_prompt_calls_bridge_blocking_prompt(self):
        """Should delegate prompt to bridge.blocking_prompt."""
        bridge = MagicMock()
        bridge.blocking_prompt.return_value = "user input"
        interaction = TUIUserInteraction(bridge)

        result = interaction.prompt("Enter name:", default="default")

        bridge.blocking_prompt.assert_called_once_with("Enter name:", default="default")
        assert result == "user input"

    def test_prompt_with_empty_default(self):
        """Should pass empty default to bridge."""
        bridge = MagicMock()
        bridge.blocking_prompt.return_value = ""
        interaction = TUIUserInteraction(bridge)

        result = interaction.prompt("Input:")

        bridge.blocking_prompt.assert_called_once_with("Input:", default="")
        assert result == ""


class TestAutoApproveInteraction:
    """Test fallback auto-approve interaction - returns defaults with logging."""

    def test_confirm_returns_default_true(self):
        """Should return default when default is True."""
        io = MockIO()
        interaction = AutoApproveInteraction(io)

        result = interaction.confirm("Create checkpoint?", default=True)

        assert result is True

    def test_confirm_returns_default_false(self):
        """Should return default when default is False."""
        io = MockIO()
        interaction = AutoApproveInteraction(io)

        result = interaction.confirm("Run in dry-run?", default=False)

        assert result is False

    def test_confirm_logs_decision(self):
        """Should log auto-approve decision."""
        io = MockIO()
        interaction = AutoApproveInteraction(io)

        interaction.confirm("Proceed with changes?", default=True)

        output = io.get_output()
        assert "[Auto-approved:" in output
        assert "Proceed with changes?" in output
        assert "Yes" in output

    def test_confirm_logs_no_decision(self):
        """Should log auto-deny decision."""
        io = MockIO()
        interaction = AutoApproveInteraction(io)

        interaction.confirm("Delete file?", default=False)

        output = io.get_output()
        assert "[Auto-approved:" in output
        assert "No" in output

    def test_prompt_returns_default(self):
        """Should return default value."""
        io = MockIO()
        interaction = AutoApproveInteraction(io)

        result = interaction.prompt("Enter path:", default="/output.txt")

        assert result == "/output.txt"

    def test_prompt_returns_empty_string_default(self):
        """Should return empty string when default is empty."""
        io = MockIO()
        interaction = AutoApproveInteraction(io)

        result = interaction.prompt("Enter optional:")

        assert result == ""

    def test_prompt_logs_decision(self):
        """Should log auto-input decision."""
        io = MockIO()
        interaction = AutoApproveInteraction(io)

        interaction.prompt("Enter filename:", default="output.log")

        output = io.get_output()
        assert "[Auto-input:" in output
        assert "Enter filename:" in output
        assert "'output.log'" in output

    def test_prompt_logs_empty_default(self):
        """Should show (empty) for empty default in log."""
        io = MockIO()
        interaction = AutoApproveInteraction(io)

        interaction.prompt("Enter something:")

        output = io.get_output()
        assert "(empty)" in output


class TestGetUserInteraction:
    """Test factory function for creating appropriate interaction handler."""

    def test_returns_cli_interaction_when_not_tui(self):
        """Should return CLIUserInteraction in CLI mode."""
        io = MockIO()
        # MockIO doesn't have is_tui_mode, so it defaults to not TUI

        interaction = get_user_interaction(io)

        assert isinstance(interaction, CLIUserInteraction)

    def test_returns_tui_interaction_when_bridge_provided(self):
        """Should return TUIUserInteraction when bridge is provided."""
        io = MagicMock()
        io.is_tui_mode = True
        bridge = MagicMock()

        # Mock mode_utils.is_tui_mode to return True
        from unittest.mock import patch
        with patch('src.cli.mode_utils.is_tui_mode', return_value=True):
            interaction = get_user_interaction(io, bridge)

        assert isinstance(interaction, TUIUserInteraction)

    def test_returns_auto_approve_when_tui_without_bridge(self):
        """Should return AutoApproveInteraction for TUI mode without bridge."""
        io = MagicMock()

        from unittest.mock import patch
        with patch('src.cli.mode_utils.is_tui_mode', return_value=True):
            interaction = get_user_interaction(io)  # No bridge

        assert isinstance(interaction, AutoApproveInteraction)

    def test_cli_mode_ignores_bridge(self):
        """Should return CLIUserInteraction even if bridge provided in CLI mode."""
        io = MockIO()
        bridge = MagicMock()

        # CLI mode (is_tui_mode returns False)
        interaction = get_user_interaction(io, bridge)

        # Should still be CLI because mode is CLI
        assert isinstance(interaction, CLIUserInteraction)


class TestUserInteractionIntegration:
    """Integration tests for interaction patterns."""

    def test_cli_interaction_behaves_like_direct_io(self):
        """CLI interaction should behave identically to direct IO calls."""
        io1 = MockIO(inputs=["test"], confirmations=[True])
        io2 = MockIO(inputs=["test"], confirmations=[True])

        interaction = CLIUserInteraction(io1)

        # Via interaction
        r1 = interaction.confirm("Q?")
        r2 = interaction.prompt("P:")

        # Via direct IO
        r3 = io2.confirm("Q?")
        r4 = io2.prompt("P:")

        assert r1 == r3
        assert r2 == r4

    def test_auto_approve_provides_safe_defaults_for_agent(self):
        """AutoApprove should use safe defaults for agent workflow."""
        io = MockIO()
        interaction = AutoApproveInteraction(io)

        # Typical agent workflow questions:
        dry_run = interaction.confirm("Run in dry-run mode?", default=False)
        checkpoint = interaction.confirm("Create git checkpoint?", default=True)
        save_log = interaction.confirm("Save audit log?", default=False)
        rollback = interaction.confirm("Rollback to checkpoint?", default=False)

        # Safe defaults:
        # - Not dry-run (user wants action)
        # - Create checkpoint (safety)
        # - Don't auto-save log (avoid clutter)
        # - Don't auto-rollback (preserve changes)
        assert dry_run is False
        assert checkpoint is True
        assert save_log is False
        assert rollback is False


class TestBridgeWiring:
    """Tests for bridge wiring in TUI mode - Phase 2 of agent bug cleanup."""

    def test_reinitialize_handlers_creates_tui_interaction(self):
        """CLI.reinitialize_handlers_with_bridge should create TUI-aware handlers."""
        from unittest.mock import MagicMock, patch

        # Create a mock CLI with the necessary attributes
        mock_orchestrator = MagicMock()
        mock_io = MagicMock()
        mock_io.is_tui_mode = True
        mock_bridge = MagicMock()

        # Import and test the reinitialization logic directly
        with patch('src.cli.mode_utils.is_tui_mode', return_value=True):
            interaction = get_user_interaction(mock_io, mock_bridge)

        assert isinstance(interaction, TUIUserInteraction)
        assert interaction._bridge is mock_bridge

    def test_agent_manager_receives_tui_interaction_after_reinitialize(self):
        """After reinitialization, CLIAgentManager should have TUI interaction."""
        from unittest.mock import MagicMock, patch
        from src.cli.agent_manager import CLIAgentManager

        mock_orchestrator = MagicMock()
        mock_io = MagicMock()
        mock_io.is_tui_mode = True
        mock_bridge = MagicMock()

        with patch('src.cli.mode_utils.is_tui_mode', return_value=True):
            interaction = get_user_interaction(mock_io, mock_bridge)

        agent_mgr = CLIAgentManager(mock_orchestrator, mock_io, interaction)

        assert isinstance(agent_mgr._interaction, TUIUserInteraction)

    def test_multiprovider_receives_tui_interaction_after_reinitialize(self):
        """After reinitialization, CLIMultiProvider should have TUI interaction."""
        from unittest.mock import MagicMock, patch
        from src.cli.multiprovider import CLIMultiProvider

        mock_orchestrator = MagicMock()
        mock_io = MagicMock()
        mock_io.is_tui_mode = True
        mock_bridge = MagicMock()

        with patch('src.cli.mode_utils.is_tui_mode', return_value=True):
            interaction = get_user_interaction(mock_io, mock_bridge)

        multiprovider = CLIMultiProvider(mock_orchestrator, mock_io, interaction)

        assert isinstance(multiprovider._interaction, TUIUserInteraction)

    def test_initial_handlers_have_cli_interaction_without_bridge(self):
        """Before bridge wiring, handlers should have CLI/AutoApprove interaction."""
        from src.cli.agent_manager import CLIAgentManager

        mock_orchestrator = MagicMock()
        io = MockIO()

        # No bridge provided - should default to CLIUserInteraction
        agent_mgr = CLIAgentManager(mock_orchestrator, io)

        assert isinstance(agent_mgr._interaction, CLIUserInteraction)

    def test_tui_interaction_uses_bridge_for_confirm(self):
        """TUI interaction should call bridge.blocking_confirm for confirmations."""
        mock_bridge = MagicMock()
        mock_bridge.blocking_confirm.return_value = True

        interaction = TUIUserInteraction(mock_bridge)
        result = interaction.confirm("Create checkpoint?", default=True)

        mock_bridge.blocking_confirm.assert_called_once_with("Create checkpoint?")
        assert result is True

    def test_tui_interaction_uses_bridge_for_prompt(self):
        """TUI interaction should call bridge.blocking_prompt for prompts."""
        mock_bridge = MagicMock()
        mock_bridge.blocking_prompt.return_value = "user response"

        interaction = TUIUserInteraction(mock_bridge)
        result = interaction.prompt("Enter task:", default="")

        mock_bridge.blocking_prompt.assert_called_once_with("Enter task:", default="")
        assert result == "user response"
