"""
Unit tests for the Confirm node.

Tests the human-in-the-loop confirmation step including:
- Processing confirmed responses
- Processing denied responses
- Abort behavior for different confirmation types
- Message formatting
- State cleanup after confirmation
- Edge cases (no pending, no response)
"""

from typing import Optional

from scrappy.graph.state import AgentState, Message, PendingConfirmation
from scrappy.graph.nodes.confirm import (
    confirm_node,
    create_pending_confirmation,
    should_abort_on_denial,
    format_confirmation_message,
    build_confirmation_message,
    build_denial_message,
    ABORT_ON_DENIAL_TYPES,
)


# =============================================================================
# Test Helpers
# =============================================================================


def create_test_state(
    input_text: str = "Test task",
    working_dir: str = "/tmp/test",
    messages: Optional[list[Message]] = None,
    pending_confirmation: Optional[PendingConfirmation] = None,
    confirmation_response: Optional[bool] = None,
    done: bool = False,
) -> AgentState:
    """Create a test AgentState with confirmation fields."""
    return AgentState(
        input=input_text,
        original_task=input_text,
        working_dir=working_dir,
        messages=messages or [],
        pending_confirmation=pending_confirmation,
        confirmation_response=confirmation_response,
        done=done,
    )


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestShouldAbortOnDenial:
    """Tests for should_abort_on_denial helper."""

    def test_command_aborts(self):
        """Command type should abort on denial."""
        assert should_abort_on_denial("command") is True

    def test_dangerous_command_aborts(self):
        """Dangerous command type should abort on denial."""
        assert should_abort_on_denial("dangerous_command") is True

    def test_destructive_operation_aborts(self):
        """Destructive operation type should abort on denial."""
        assert should_abort_on_denial("destructive_operation") is True

    def test_file_overwrite_does_not_abort(self):
        """File overwrite type should NOT abort on denial (can try different approach)."""
        assert should_abort_on_denial("file_overwrite") is False

    def test_unknown_type_does_not_abort(self):
        """Unknown types should NOT abort by default."""
        assert should_abort_on_denial("unknown_type") is False
        assert should_abort_on_denial("custom") is False


class TestFormatConfirmationMessage:
    """Tests for format_confirmation_message helper."""

    def test_command_confirmed(self):
        """Format command confirmed message."""
        details: PendingConfirmation = {"type": "command", "command": "ls -la"}
        msg = format_confirmation_message("command", True, details)
        assert "confirmed" in msg
        assert "ls -la" in msg

    def test_command_denied(self):
        """Format command denied message."""
        details: PendingConfirmation = {"type": "command", "command": "rm file.txt"}
        msg = format_confirmation_message("command", False, details)
        assert "denied" in msg
        assert "rm file.txt" in msg

    def test_dangerous_command_includes_warning(self):
        """Format dangerous command message."""
        details: PendingConfirmation = {"type": "dangerous_command", "command": "rm -rf /"}
        msg = format_confirmation_message("dangerous_command", False, details)
        assert "denied" in msg
        assert "dangerous" in msg
        assert "rm -rf /" in msg

    def test_file_overwrite(self):
        """Format file overwrite message."""
        details: PendingConfirmation = {"type": "file_overwrite", "file_path": "/etc/config"}
        msg = format_confirmation_message("file_overwrite", True, details)
        assert "confirmed" in msg
        assert "overwrite" in msg
        assert "/etc/config" in msg

    def test_destructive_operation(self):
        """Format destructive operation message."""
        details: PendingConfirmation = {"type": "destructive_operation", "content": "Delete database"}
        msg = format_confirmation_message("destructive_operation", False, details)
        assert "denied" in msg
        assert "destructive" in msg
        assert "Delete database" in msg

    def test_unknown_type(self):
        """Format unknown type message."""
        msg = format_confirmation_message("custom_type", True, None)
        assert "confirmed" in msg
        assert "custom_type" in msg

    def test_missing_details(self):
        """Handle missing details gracefully."""
        msg = format_confirmation_message("command", True, None)
        assert "confirmed" in msg
        assert "unknown" in msg.lower() or "command" in msg.lower()


class TestBuildConfirmationMessage:
    """Tests for build_confirmation_message helper."""

    def test_returns_system_message(self):
        """Should return a system message."""
        details: PendingConfirmation = {"type": "command", "command": "echo hello"}
        msg = build_confirmation_message("command", details)
        assert msg["role"] == "system"
        assert "Proceeding" in msg["content"]


class TestBuildDenialMessage:
    """Tests for build_denial_message helper."""

    def test_abort_type_says_aborted(self):
        """Denial of abort-type should say 'aborted'."""
        details: PendingConfirmation = {"type": "command", "command": "rm file"}
        msg = build_denial_message("command", details)
        assert msg["role"] == "system"
        assert "aborted" in msg["content"].lower()

    def test_non_abort_type_suggests_different_approach(self):
        """Denial of non-abort type should suggest different approach."""
        details: PendingConfirmation = {"type": "file_overwrite", "file_path": "/file"}
        msg = build_denial_message("file_overwrite", details)
        assert msg["role"] == "system"
        assert "different approach" in msg["content"].lower()


class TestCreatePendingConfirmation:
    """Tests for create_pending_confirmation helper."""

    def test_command_type(self):
        """Create command confirmation."""
        pending = create_pending_confirmation("command", command="ls -la")
        assert pending["type"] == "command"
        assert pending["command"] == "ls -la"
        assert "file_path" not in pending
        assert "content" not in pending

    def test_file_overwrite_type(self):
        """Create file overwrite confirmation."""
        pending = create_pending_confirmation("file_overwrite", file_path="/etc/config")
        assert pending["type"] == "file_overwrite"
        assert pending["file_path"] == "/etc/config"
        assert "command" not in pending

    def test_destructive_operation_type(self):
        """Create destructive operation confirmation."""
        pending = create_pending_confirmation(
            "destructive_operation",
            content="Delete all user data",
        )
        assert pending["type"] == "destructive_operation"
        assert pending["content"] == "Delete all user data"

    def test_dangerous_command_type(self):
        """Create dangerous command confirmation."""
        pending = create_pending_confirmation(
            "dangerous_command",
            command="sudo rm -rf /",
        )
        assert pending["type"] == "dangerous_command"
        assert pending["command"] == "sudo rm -rf /"


# =============================================================================
# Confirm Node Tests
# =============================================================================


class TestConfirmNodePassthrough:
    """Tests for confirm_node when no confirmation is pending."""

    def test_no_pending_confirmation(self):
        """Should pass through when no pending confirmation."""
        state = create_test_state(pending_confirmation=None)

        result = confirm_node(state)

        # State should be unchanged
        assert result.pending_confirmation is None
        assert result.confirmation_response is None
        assert result.done is False
        assert len(result.messages) == 0


class TestConfirmNodeConfirmed:
    """Tests for confirm_node when user confirms."""

    def test_command_confirmed_continues(self):
        """Confirmed command should clear pending and continue."""
        pending: PendingConfirmation = {"type": "command", "command": "ls -la"}
        state = create_test_state(
            pending_confirmation=pending,
            confirmation_response=True,
        )

        result = confirm_node(state)

        # Pending should be cleared
        assert result.pending_confirmation is None
        assert result.confirmation_response is None
        # Should NOT abort
        assert result.done is False
        # Should add confirmation message
        assert len(result.messages) == 1
        assert result.messages[0]["role"] == "system"
        assert "confirmed" in result.messages[0]["content"].lower()
        assert "Proceeding" in result.messages[0]["content"]

    def test_file_overwrite_confirmed(self):
        """Confirmed file overwrite should continue."""
        pending: PendingConfirmation = {"type": "file_overwrite", "file_path": "/config"}
        state = create_test_state(
            pending_confirmation=pending,
            confirmation_response=True,
        )

        result = confirm_node(state)

        assert result.pending_confirmation is None
        assert result.done is False
        assert len(result.messages) == 1

    def test_preserves_existing_messages(self):
        """Should preserve existing messages when adding confirmation."""
        existing: list[Message] = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        pending: PendingConfirmation = {"type": "command", "command": "echo"}
        state = create_test_state(
            messages=existing,
            pending_confirmation=pending,
            confirmation_response=True,
        )

        result = confirm_node(state)

        assert len(result.messages) == 3
        assert result.messages[0] == existing[0]
        assert result.messages[1] == existing[1]
        assert result.messages[2]["role"] == "system"


class TestConfirmNodeDenied:
    """Tests for confirm_node when user denies."""

    def test_command_denied_aborts(self):
        """Denied command should abort (set done=True)."""
        pending: PendingConfirmation = {"type": "command", "command": "rm file"}
        state = create_test_state(
            pending_confirmation=pending,
            confirmation_response=False,
        )

        result = confirm_node(state)

        # Pending should be cleared
        assert result.pending_confirmation is None
        assert result.confirmation_response is None
        # Should abort for command type
        assert result.done is True
        # Should add denial message
        assert len(result.messages) == 1
        assert "denied" in result.messages[0]["content"].lower()
        assert "aborted" in result.messages[0]["content"].lower()

    def test_dangerous_command_denied_aborts(self):
        """Denied dangerous command should abort."""
        pending: PendingConfirmation = {"type": "dangerous_command", "command": "sudo rm -rf /"}
        state = create_test_state(
            pending_confirmation=pending,
            confirmation_response=False,
        )

        result = confirm_node(state)

        assert result.done is True
        assert "aborted" in result.messages[0]["content"].lower()

    def test_destructive_operation_denied_aborts(self):
        """Denied destructive operation should abort."""
        pending: PendingConfirmation = {"type": "destructive_operation", "content": "Delete"}
        state = create_test_state(
            pending_confirmation=pending,
            confirmation_response=False,
        )

        result = confirm_node(state)

        assert result.done is True

    def test_file_overwrite_denied_does_not_abort(self):
        """Denied file overwrite should NOT abort (try different approach)."""
        pending: PendingConfirmation = {"type": "file_overwrite", "file_path": "/config"}
        state = create_test_state(
            pending_confirmation=pending,
            confirmation_response=False,
        )

        result = confirm_node(state)

        # Should NOT abort
        assert result.done is False
        # But should still clear pending
        assert result.pending_confirmation is None
        # Message should suggest different approach
        assert "different approach" in result.messages[0]["content"].lower()


class TestConfirmNodeEdgeCases:
    """Edge case tests for confirm_node."""

    def test_pending_but_no_response_treats_as_denied(self):
        """Pending confirmation with no response should be treated as denied (safety)."""
        pending: PendingConfirmation = {"type": "command", "command": "rm file"}
        state = create_test_state(
            pending_confirmation=pending,
            confirmation_response=None,  # No response!
        )

        result = confirm_node(state)

        # Should treat as denied for safety
        assert result.done is True
        assert result.pending_confirmation is None
        assert "denied" in result.messages[0]["content"].lower()

    def test_unknown_confirmation_type(self):
        """Unknown confirmation type should be handled gracefully."""
        pending: PendingConfirmation = {"type": "custom_unknown_type"}
        state = create_test_state(
            pending_confirmation=pending,
            confirmation_response=True,
        )

        result = confirm_node(state)

        # Should not crash
        assert result.pending_confirmation is None
        assert result.done is False
        assert len(result.messages) == 1

    def test_unknown_type_denied_does_not_abort(self):
        """Unknown type denied should NOT abort by default."""
        pending: PendingConfirmation = {"type": "custom_unknown_type"}
        state = create_test_state(
            pending_confirmation=pending,
            confirmation_response=False,
        )

        result = confirm_node(state)

        # Unknown types don't abort
        assert result.done is False
        assert result.pending_confirmation is None


class TestAbortOnDenialTypes:
    """Verify ABORT_ON_DENIAL_TYPES constant."""

    def test_contains_expected_types(self):
        """Should contain the expected abort types."""
        assert "command" in ABORT_ON_DENIAL_TYPES
        assert "dangerous_command" in ABORT_ON_DENIAL_TYPES
        assert "destructive_operation" in ABORT_ON_DENIAL_TYPES

    def test_does_not_contain_file_overwrite(self):
        """File overwrite should NOT be an abort type."""
        assert "file_overwrite" not in ABORT_ON_DENIAL_TYPES
