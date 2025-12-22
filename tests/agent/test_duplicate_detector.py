"""
Tests for DuplicateDetector.

Tests the duplicate action detection logic that prevents infinite loops
and redundant operations.
"""
import pytest

from scrappy.agent.duplicate_detector import DuplicateDetector
from scrappy.agent.types import AgentAction, ConversationState


class TestDuplicateDetectorSkipActions:
    """Tests for actions that should never be flagged as duplicates."""

    @pytest.mark.unit
    def test_read_file_never_duplicate(self):
        """read_file should never be flagged as duplicate (normal to re-read)."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.last_action = {"action": "read_file", "parameters": {"path": "test.py"}}

        action = AgentAction(
            action="read_file",
            parameters={"path": "test.py"},
            thought="Reading file again",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False
        assert msg == ""

    @pytest.mark.unit
    def test_write_file_never_duplicate(self):
        """write_file should never be flagged as duplicate (normal to overwrite)."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.last_action = {
            "action": "write_file",
            "parameters": {"path": "test.py", "content": "code"}
        }

        action = AgentAction(
            action="write_file",
            parameters={"path": "test.py", "content": "code"},
            thought="Writing again",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False
        assert msg == ""

    @pytest.mark.unit
    def test_task_never_duplicate(self):
        """task should never be flagged as duplicate (internal tracking)."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.last_action = {"action": "task", "parameters": {"operation": "update"}}

        action = AgentAction(
            action="task",
            parameters={"operation": "update"},
            thought="Updating task",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False

    @pytest.mark.unit
    def test_skip_list_includes_expected_actions(self):
        """Verify SKIP_DUPLICATE_CHECK includes all file and search operations."""
        expected = {
            'read_file', 'write_file', 'list_files', 'list_directory',
            'search_code', 'find_exact_text', 'codebase_search',
            'git_status', 'git_diff', 'task'
        }
        assert expected.issubset(DuplicateDetector.SKIP_DUPLICATE_CHECK)


class TestDuplicateDetectorBasics:
    """Basic duplicate detection tests."""

    @pytest.mark.unit
    def test_no_duplicate_when_history_empty(self):
        """First action should never be duplicate."""
        detector = DuplicateDetector()
        state = ConversationState()
        action = AgentAction(
            action="read_file",
            parameters={"path": "test.py"},
            thought="Reading file",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False
        assert msg == ""

    @pytest.mark.unit
    def test_duplicate_when_matches_last_action(self):
        """Action matching last_action should be duplicate."""
        detector = DuplicateDetector()
        state = ConversationState()
        # Use an action NOT in SKIP_DUPLICATE_CHECK (read_file is skipped)
        state.last_action = {
            "action": "api_call",
            "parameters": {"endpoint": "/test"}
        }

        action = AgentAction(
            action="api_call",
            parameters={"endpoint": "/test"},
            thought="Calling API again",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is True
        assert "already attempted recently" in msg

    @pytest.mark.unit
    def test_not_duplicate_when_different_action(self):
        """Different action name should not be duplicate."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.last_action = {
            "action": "read_file",
            "parameters": {"path": "test.py"}
        }

        action = AgentAction(
            action="write_file",
            parameters={"path": "test.py"},
            thought="Writing file",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False

    @pytest.mark.unit
    def test_not_duplicate_when_different_parameters(self):
        """Same action with different parameters should not be duplicate."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.last_action = {
            "action": "read_file",
            "parameters": {"path": "test.py"}
        }

        action = AgentAction(
            action="read_file",
            parameters={"path": "other.py"},
            thought="Reading different file",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False


class TestDuplicateDetectorHistory:
    """Tests for action history lookback."""

    @pytest.mark.unit
    def test_duplicate_in_action_history(self):
        """Action in recent history should be duplicate."""
        detector = DuplicateDetector()
        state = ConversationState()
        # Use api_call which is NOT in SKIP_DUPLICATE_CHECK
        state.action_history = [
            {"action": "api_call", "parameters": {"endpoint": "/a"}},
            {"action": "api_call", "parameters": {"endpoint": "/b"}},
        ]

        action = AgentAction(
            action="api_call",
            parameters={"endpoint": "/a"},
            thought="Calling /a again",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is True

    @pytest.mark.unit
    def test_not_duplicate_outside_lookback_window(self):
        """Action outside lookback window should not be duplicate."""
        detector = DuplicateDetector()
        state = ConversationState()

        # Fill history beyond lookback window (3)
        state.action_history = [
            {"action": "read_file", "parameters": {"path": "old.py"}},  # Outside window
            {"action": "write_file", "parameters": {"path": "a.py"}},
            {"action": "write_file", "parameters": {"path": "b.py"}},
            {"action": "write_file", "parameters": {"path": "c.py"}},
        ]

        # Try to repeat the old action (outside window)
        action = AgentAction(
            action="read_file",
            parameters={"path": "old.py"},
            thought="Reading old file",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False

    @pytest.mark.unit
    def test_lookback_window_size(self):
        """Verify lookback window is exactly 3."""
        detector = DuplicateDetector()
        assert detector.LOOKBACK_WINDOW == 3

    @pytest.mark.unit
    def test_duplicate_at_edge_of_window(self):
        """Action at edge of lookback window should be duplicate."""
        detector = DuplicateDetector()
        state = ConversationState()

        # Put target action exactly at window boundary
        # Use api_call which is NOT in SKIP_DUPLICATE_CHECK
        state.action_history = [
            {"action": "api_call", "parameters": {"endpoint": "/target"}},  # 3rd from end
            {"action": "api_call", "parameters": {"endpoint": "/a"}},
            {"action": "api_call", "parameters": {"endpoint": "/b"}},
        ]

        action = AgentAction(
            action="api_call",
            parameters={"endpoint": "/target"},
            thought="Calling target again",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is True


class TestDuplicateDetectorCommandFailures:
    """Tests for command failure tracking."""

    @pytest.mark.unit
    def test_command_not_blocked_with_no_failures(self):
        """Command with no failure history should not be blocked."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.failed_commands = []

        action = AgentAction(
            action="run_command",
            parameters={"command": "pytest tests/"},
            thought="Running tests",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False

    @pytest.mark.unit
    def test_command_not_blocked_under_threshold(self):
        """Command with fewer than MAX failures should not be blocked."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.failed_commands = [
            {"command": "pytest tests/", "error": "failed"},
            {"command": "pytest tests/", "error": "failed again"},
        ]

        action = AgentAction(
            action="run_command",
            parameters={"command": "pytest tests/"},
            thought="Running tests",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False

    @pytest.mark.unit
    def test_command_blocked_at_threshold(self):
        """Command with MAX failures should be blocked."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.failed_commands = [
            {"command": "pytest tests/", "error": "failed 1"},
            {"command": "pytest tests/", "error": "failed 2"},
            {"command": "pytest tests/", "error": "failed 3"},
        ]

        action = AgentAction(
            action="run_command",
            parameters={"command": "pytest tests/"},
            thought="Running tests",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is True
        assert "failed 3 times" in msg
        assert "infinite loop" in msg

    @pytest.mark.unit
    def test_command_blocked_over_threshold(self):
        """Command with more than MAX failures should be blocked."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.failed_commands = [
            {"command": "npm test", "error": "failed"},
            {"command": "npm test", "error": "failed"},
            {"command": "npm test", "error": "failed"},
            {"command": "npm test", "error": "failed"},
            {"command": "npm test", "error": "failed"},
        ]

        action = AgentAction(
            action="run_command",
            parameters={"command": "npm test"},
            thought="Running tests",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is True
        assert "failed 5 times" in msg

    @pytest.mark.unit
    def test_different_command_not_blocked(self):
        """Different command should not be affected by other failures."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.failed_commands = [
            {"command": "pytest tests/", "error": "failed"},
            {"command": "pytest tests/", "error": "failed"},
            {"command": "pytest tests/", "error": "failed"},
        ]

        # Different command
        action = AgentAction(
            action="run_command",
            parameters={"command": "npm test"},
            thought="Running npm tests",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False

    @pytest.mark.unit
    def test_max_command_failures_constant(self):
        """Verify MAX_COMMAND_FAILURES is 3."""
        detector = DuplicateDetector()
        assert detector.MAX_COMMAND_FAILURES == 3

    @pytest.mark.unit
    def test_failure_check_only_for_run_command(self):
        """Failure counting should only apply to run_command actions."""
        detector = DuplicateDetector()
        state = ConversationState()

        # Even with failed_commands, non-run_command actions aren't checked
        state.failed_commands = [
            {"command": "test.py", "error": "failed"},
            {"command": "test.py", "error": "failed"},
            {"command": "test.py", "error": "failed"},
        ]

        action = AgentAction(
            action="read_file",
            parameters={"path": "test.py"},
            thought="Reading file",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False


class TestDuplicateDetectorEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.unit
    def test_missing_last_action_attribute(self):
        """Should handle state without last_action."""
        detector = DuplicateDetector()
        state = ConversationState()
        # Don't set last_action

        action = AgentAction(
            action="read_file",
            parameters={"path": "test.py"},
            thought="Reading",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False

    @pytest.mark.unit
    def test_missing_action_history_attribute(self):
        """Should handle state without action_history."""
        detector = DuplicateDetector()
        state = ConversationState()
        # action_history exists by default as empty list

        action = AgentAction(
            action="read_file",
            parameters={"path": "test.py"},
            thought="Reading",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False

    @pytest.mark.unit
    def test_missing_failed_commands_attribute(self):
        """Should handle state without failed_commands."""
        detector = DuplicateDetector()
        state = ConversationState()
        # failed_commands exists by default as empty list

        action = AgentAction(
            action="run_command",
            parameters={"command": "pytest"},
            thought="Running",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False

    @pytest.mark.unit
    def test_empty_command_parameter(self):
        """Should handle empty command parameter."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.failed_commands = [
            {"command": "", "error": "failed"},
            {"command": "", "error": "failed"},
            {"command": "", "error": "failed"},
        ]

        action = AgentAction(
            action="run_command",
            parameters={"command": ""},
            thought="Empty command",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        # Empty command returns 0 count, so not blocked
        assert is_dup is False

    @pytest.mark.unit
    def test_missing_command_parameter(self):
        """Should handle missing command parameter."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.failed_commands = [
            {"command": "pytest", "error": "failed"},
            {"command": "pytest", "error": "failed"},
            {"command": "pytest", "error": "failed"},
        ]

        action = AgentAction(
            action="run_command",
            parameters={},  # No command key
            thought="No command",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False

    @pytest.mark.unit
    def test_none_last_action(self):
        """Should handle None last_action."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.last_action = None

        action = AgentAction(
            action="read_file",
            parameters={"path": "test.py"},
            thought="Reading",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False

    @pytest.mark.unit
    def test_complex_parameters_matching(self):
        """Should correctly match complex nested parameters."""
        detector = DuplicateDetector()
        state = ConversationState()
        # Use api_call which is NOT in SKIP_DUPLICATE_CHECK
        state.last_action = {
            "action": "api_call",
            "parameters": {
                "endpoint": "/submit",
                "body": {"data": "value", "nested": {"key": 1}}
            }
        }

        # Exact same parameters
        action = AgentAction(
            action="api_call",
            parameters={
                "endpoint": "/submit",
                "body": {"data": "value", "nested": {"key": 1}}
            },
            thought="Calling API again",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is True

    @pytest.mark.unit
    def test_complex_parameters_not_matching(self):
        """Different complex parameters should not match."""
        detector = DuplicateDetector()
        state = ConversationState()
        state.last_action = {
            "action": "write_file",
            "parameters": {
                "path": "test.py",
                "content": "def foo():\n    pass"
            }
        }

        # Different content
        action = AgentAction(
            action="write_file",
            parameters={
                "path": "test.py",
                "content": "def bar():\n    return 1"
            },
            thought="Writing different content",
            is_complete=False
        )

        is_dup, msg = detector.check_duplicate(action, state)

        assert is_dup is False


class TestDuplicateDetectorIntegration:
    """Integration-style tests simulating real agent behavior."""

    @pytest.mark.unit
    def test_agent_retry_loop_detected(self):
        """Simulate agent retrying same failed command."""
        detector = DuplicateDetector()
        state = ConversationState()

        command = "python -m pytest tests/"
        action = AgentAction(
            action="run_command",
            parameters={"command": command},
            thought="Running tests",
            is_complete=False
        )

        # First attempt - allowed
        is_dup, _ = detector.check_duplicate(action, state)
        assert is_dup is False
        state.failed_commands.append({"command": command, "error": "exit 1"})
        state.action_history.append({"action": "run_command", "parameters": {"command": command}})
        state.last_action = {"action": "run_command", "parameters": {"command": command}}

        # Second attempt - duplicate (same as last)
        is_dup, _ = detector.check_duplicate(action, state)
        assert is_dup is True

        # Clear last_action to simulate intervening action
        state.last_action = {"action": "read_file", "parameters": {"path": "test.py"}}
        state.action_history.append({"action": "read_file", "parameters": {"path": "test.py"}})

        # Third attempt after intervening action - still in history
        is_dup, _ = detector.check_duplicate(action, state)
        assert is_dup is True  # Still in lookback window

    @pytest.mark.unit
    def test_command_failure_accumulation(self):
        """Simulate command failing multiple times with variations."""
        detector = DuplicateDetector()
        state = ConversationState()

        command = "npm test"

        # Fail 1
        state.failed_commands.append({"command": command, "error": "test failed"})

        # Fail 2
        state.failed_commands.append({"command": command, "error": "still failing"})

        action = AgentAction(
            action="run_command",
            parameters={"command": command},
            thought="Try again",
            is_complete=False
        )

        # After 2 failures - still allowed
        is_dup, _ = detector.check_duplicate(action, state)
        assert is_dup is False

        # Fail 3
        state.failed_commands.append({"command": command, "error": "failed again"})

        # After 3 failures - blocked
        is_dup, msg = detector.check_duplicate(action, state)
        assert is_dup is True
        assert "3 times" in msg
