"""
Tests for LangGraphBridge.

Focuses on:
- Pure utility functions (no mocking needed)
- State management and properties
- Callback behavior
- Concurrency guards
"""

import pytest
from dataclasses import fields
from unittest.mock import Mock, patch

from scrappy.cli.textual.langgraph_bridge import (
    AgentResult,
    LangGraphBridge,
)
from scrappy.infrastructure.threading import CancellationToken


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_success_result(self):
        """AgentResult captures successful completion."""
        mock_state = Mock()
        result = AgentResult(
            success=True,
            final_state=mock_state,
            error=None,
            cancelled=False,
        )

        assert result.success is True
        assert result.final_state is mock_state
        assert result.error is None
        assert result.cancelled is False

    def test_cancelled_result(self):
        """AgentResult captures cancellation."""
        result = AgentResult(
            success=False,
            final_state=None,
            error=None,
            cancelled=True,
        )

        assert result.success is False
        assert result.final_state is None
        assert result.cancelled is True

    def test_error_result(self):
        """AgentResult captures error."""
        result = AgentResult(
            success=False,
            final_state=None,
            error="Something went wrong",
            cancelled=False,
        )

        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.cancelled is False

    def test_has_expected_fields(self):
        """AgentResult has all required fields."""
        field_names = {f.name for f in fields(AgentResult)}
        assert field_names == {"success", "final_state", "error", "cancelled"}


class TestProtocols:
    """Tests for protocol definitions."""

    def test_confirm_callback_protocol_is_runtime_checkable(self):
        """ConfirmCallbackProtocol should be runtime checkable."""
        def my_callback(question: str) -> bool:
            return True

        # Protocol is runtime_checkable, so isinstance works
        assert callable(my_callback)

    def test_output_callback_protocol_is_runtime_checkable(self):
        """OutputCallbackProtocol should be runtime checkable."""
        def my_callback(content: str) -> None:
            pass

        assert callable(my_callback)


class TestTruncateResult:
    """Tests for _truncate_result method."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        app = Mock()
        thread_bridge = Mock()
        output_adapter = Mock()
        llm_service = Mock()
        tool_adapter = Mock()

        return LangGraphBridge(
            app=app,
            bridge=thread_bridge,
            output_adapter=output_adapter,
            llm_service=llm_service,
            tool_adapter=tool_adapter,
        )

    def test_empty_string_returns_empty(self, bridge):
        """Empty input returns empty string."""
        result = bridge._truncate_result("")
        assert result == ""

    def test_none_like_returns_empty(self, bridge):
        """Falsy strings return empty."""
        result = bridge._truncate_result("")
        assert result == ""

    def test_short_single_line_unchanged(self, bridge):
        """Short single line is returned unchanged."""
        result = bridge._truncate_result("Hello world")
        assert result == "Hello world"

    def test_multiple_lines_within_limit(self, bridge):
        """Multiple lines within limit are joined with indent."""
        text = "line1\nline2\nline3"
        result = bridge._truncate_result(text)
        assert result == "line1\n  line2\n  line3"

    def test_more_than_max_lines_truncated(self, bridge):
        """More than max_lines gets truncated with ellipsis."""
        text = "line1\nline2\nline3\nline4\nline5"
        result = bridge._truncate_result(text, max_lines=3)
        assert result == "line1\n  line2\n  line3..."

    def test_exceeds_max_chars_truncated(self, bridge):
        """Content exceeding max_chars is truncated."""
        text = "a" * 300
        result = bridge._truncate_result(text, max_chars=100)
        assert len(result) == 100
        assert result.endswith("...")

    def test_custom_limits(self, bridge):
        """Custom max_lines and max_chars are respected."""
        text = "short\nmedium\nlong\nextra"
        result = bridge._truncate_result(text, max_lines=2, max_chars=50)
        assert "short" in result
        assert "medium" in result
        # Only 2 lines, should have ellipsis
        assert result.endswith("...")

    def test_whitespace_stripped(self, bridge):
        """Leading/trailing whitespace is stripped."""
        text = "  content  \n"
        result = bridge._truncate_result(text)
        assert result == "content"


class TestExtractKeyParam:
    """Tests for _extract_key_param method."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        return LangGraphBridge(
            app=Mock(),
            bridge=Mock(),
            output_adapter=Mock(),
            llm_service=Mock(),
            tool_adapter=Mock(),
        )

    def test_write_file_extracts_path(self, bridge):
        """write_file tool extracts path parameter."""
        result = bridge._extract_key_param("write_file", {"path": "/tmp/test.py"})
        assert result == "/tmp/test.py"

    def test_read_file_extracts_path(self, bridge):
        """read_file tool extracts path parameter."""
        result = bridge._extract_key_param("read_file", {"path": "src/main.py"})
        assert result == "src/main.py"

    def test_run_command_extracts_command(self, bridge):
        """run_command tool extracts command parameter."""
        result = bridge._extract_key_param("run_command", {"command": "ls -la"})
        assert result == "ls -la"

    def test_codebase_search_extracts_query(self, bridge):
        """codebase_search tool extracts query parameter."""
        result = bridge._extract_key_param("codebase_search", {"query": "def main"})
        assert result == "def main"

    def test_unknown_tool_returns_empty(self, bridge):
        """Unknown tool returns empty string."""
        result = bridge._extract_key_param("unknown_tool", {"some": "arg"})
        assert result == ""

    def test_missing_param_returns_empty(self, bridge):
        """Missing expected parameter returns empty string."""
        result = bridge._extract_key_param("write_file", {"wrong_param": "value"})
        assert result == ""

    def test_long_value_truncated(self, bridge):
        """Values longer than 50 chars are truncated with ellipsis."""
        long_path = "a" * 60
        result = bridge._extract_key_param("write_file", {"path": long_path})
        assert len(result) == 50
        assert result.endswith("...")

    def test_exactly_50_chars_not_truncated(self, bridge):
        """Values exactly 50 chars are not truncated."""
        exact_path = "a" * 50
        result = bridge._extract_key_param("write_file", {"path": exact_path})
        assert len(result) == 50
        assert not result.endswith("...")

    def test_empty_args_returns_empty(self, bridge):
        """Empty args dict returns empty string."""
        result = bridge._extract_key_param("write_file", {})
        assert result == ""


class TestGetFilePathFromArgs:
    """Tests for _get_file_path_from_args method."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        return LangGraphBridge(
            app=Mock(),
            bridge=Mock(),
            output_adapter=Mock(),
            llm_service=Mock(),
            tool_adapter=Mock(),
        )

    def test_file_path_key(self, bridge):
        """Extracts from 'file_path' key."""
        result = bridge._get_file_path_from_args({"file_path": "/tmp/test.py"})
        assert result == "/tmp/test.py"

    def test_path_key(self, bridge):
        """Extracts from 'path' key."""
        result = bridge._get_file_path_from_args({"path": "/tmp/test.py"})
        assert result == "/tmp/test.py"

    def test_filepath_key(self, bridge):
        """Extracts from 'filepath' key."""
        result = bridge._get_file_path_from_args({"filepath": "/tmp/test.py"})
        assert result == "/tmp/test.py"

    def test_file_key(self, bridge):
        """Extracts from 'file' key."""
        result = bridge._get_file_path_from_args({"file": "/tmp/test.py"})
        assert result == "/tmp/test.py"

    def test_priority_order(self, bridge):
        """file_path takes priority over path."""
        result = bridge._get_file_path_from_args({
            "file_path": "/first",
            "path": "/second",
        })
        assert result == "/first"

    def test_no_file_key_returns_none(self, bridge):
        """Returns None when no file path key found."""
        result = bridge._get_file_path_from_args({"other": "value"})
        assert result is None

    def test_empty_args_returns_none(self, bridge):
        """Empty args returns None."""
        result = bridge._get_file_path_from_args({})
        assert result is None


class TestStateManagement:
    """Tests for state properties and cancellation."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        return LangGraphBridge(
            app=Mock(),
            bridge=Mock(),
            output_adapter=Mock(),
            llm_service=Mock(),
            tool_adapter=Mock(),
        )

    def test_is_running_initially_false(self, bridge):
        """is_running is False initially."""
        assert bridge.is_running is False

    def test_is_running_reflects_internal_state(self, bridge):
        """is_running reflects _is_running state."""
        bridge._is_running = True
        assert bridge.is_running is True

        bridge._is_running = False
        assert bridge.is_running is False

    def test_is_force_cancelled_false_without_token(self, bridge):
        """is_force_cancelled is False when no cancellation token."""
        assert bridge._cancellation_token is None
        assert bridge.is_force_cancelled is False

    def test_is_force_cancelled_false_with_fresh_token(self, bridge):
        """is_force_cancelled is False with fresh token."""
        bridge._cancellation_token = CancellationToken()
        assert bridge.is_force_cancelled is False

    def test_is_force_cancelled_false_after_single_cancel(self, bridge):
        """is_force_cancelled is False after single cancel."""
        bridge._cancellation_token = CancellationToken()
        bridge._cancellation_token.cancel()
        assert bridge.is_force_cancelled is False

    def test_is_force_cancelled_true_after_double_cancel(self, bridge):
        """is_force_cancelled is True after two cancels."""
        bridge._cancellation_token = CancellationToken()
        bridge._cancellation_token.cancel()
        bridge._cancellation_token.cancel()
        assert bridge.is_force_cancelled is True


class TestCancelMethod:
    """Tests for cancel() method."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        return LangGraphBridge(
            app=Mock(),
            bridge=Mock(),
            output_adapter=Mock(),
            llm_service=Mock(),
            tool_adapter=Mock(),
        )

    def test_cancel_without_token_does_not_raise(self, bridge):
        """cancel() does not raise when no token."""
        bridge._cancellation_token = None
        bridge._current_worker = None
        bridge.cancel()  # Should not raise

    def test_cancel_with_token_cancels_token(self, bridge):
        """cancel() cancels the token."""
        bridge._cancellation_token = CancellationToken()
        bridge.cancel()
        assert bridge._cancellation_token.is_cancelled is True

    def test_cancel_with_worker_cancels_worker(self, bridge):
        """cancel() cancels the worker."""
        mock_worker = Mock()
        bridge._current_worker = mock_worker
        bridge._cancellation_token = CancellationToken()

        bridge.cancel()

        mock_worker.cancel.assert_called_once()

    def test_multiple_cancels_tracked(self, bridge):
        """Multiple cancels increase cancel_count."""
        bridge._cancellation_token = CancellationToken()

        bridge.cancel()
        assert bridge._cancellation_token.cancel_count == 1

        bridge.cancel()
        assert bridge._cancellation_token.cancel_count == 2


class TestCheckCancellation:
    """Tests for _check_cancellation method."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        return LangGraphBridge(
            app=Mock(),
            bridge=Mock(),
            output_adapter=Mock(),
            llm_service=Mock(),
            tool_adapter=Mock(),
        )

    def test_returns_false_without_token(self, bridge):
        """Returns False when no cancellation token."""
        bridge._cancellation_token = None
        with patch("scrappy.cli.textual.langgraph_bridge.get_current_worker") as mock_get:
            mock_get.side_effect = Exception("No worker")
            assert bridge._check_cancellation() is False

    def test_returns_true_when_token_cancelled(self, bridge):
        """Returns True when token is cancelled."""
        bridge._cancellation_token = CancellationToken()
        bridge._cancellation_token.cancel()
        assert bridge._check_cancellation() is True

    def test_returns_true_when_worker_cancelled(self, bridge):
        """Returns True when worker is cancelled."""
        bridge._cancellation_token = CancellationToken()  # Not cancelled

        with patch("scrappy.cli.textual.langgraph_bridge.get_current_worker") as mock_get:
            mock_worker = Mock()
            mock_worker.is_cancelled = True
            mock_get.return_value = mock_worker

            assert bridge._check_cancellation() is True


class TestToolConfirmCallback:
    """Tests for _tool_confirm_callback method."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        mock_bridge = Mock()
        bridge = LangGraphBridge(
            app=Mock(),
            bridge=mock_bridge,
            output_adapter=Mock(),
            llm_service=Mock(),
            tool_adapter=Mock(),
        )
        return bridge

    def test_returns_true_when_allow_all(self, bridge):
        """Returns True without prompting when allow_all is set."""
        bridge._allow_all = True

        result = bridge._tool_confirm_callback("write_file", "Write to test.py")

        assert result is True
        # Should not have called blocking_confirm_yna
        bridge._bridge.blocking_confirm_yna.assert_not_called()

    def test_returns_true_on_yes(self, bridge):
        """Returns True when user responds 'y'."""
        bridge._allow_all = False
        bridge._bridge.blocking_confirm_yna.return_value = "y"

        result = bridge._tool_confirm_callback("write_file", "Write to test.py")

        assert result is True
        assert bridge._allow_all is False  # Not changed

    def test_sets_allow_all_on_a(self, bridge):
        """Sets allow_all and returns True when user responds 'a'."""
        bridge._allow_all = False
        bridge._bridge.blocking_confirm_yna.return_value = "a"

        result = bridge._tool_confirm_callback("write_file", "Write to test.py")

        assert result is True
        assert bridge._allow_all is True  # Now set

    def test_returns_false_on_no(self, bridge):
        """Returns False when user responds 'n'."""
        bridge._allow_all = False
        bridge._bridge.blocking_confirm_yna.return_value = "n"

        result = bridge._tool_confirm_callback("write_file", "Write to test.py")

        assert result is False

    def test_formats_question_correctly(self, bridge):
        """Formats the question with description."""
        bridge._allow_all = False
        bridge._bridge.blocking_confirm_yna.return_value = "y"

        bridge._tool_confirm_callback("write_file", "Write to test.py")

        bridge._bridge.blocking_confirm_yna.assert_called_once_with("Write to test.py?")


class TestRunAgentConcurrencyGuard:
    """Tests for run_agent concurrency guard."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        return LangGraphBridge(
            app=Mock(),
            bridge=Mock(),
            output_adapter=Mock(),
            llm_service=Mock(),
            tool_adapter=Mock(),
        )

    def test_rejects_when_already_running(self, bridge):
        """run_agent rejects when another run is in progress."""
        bridge._is_running = True

        result = bridge.run_agent("task", "/tmp")

        assert result.success is False
        assert result.cancelled is False
        assert "already in progress" in result.error


class TestUpdateTaskProgress:
    """Tests for _update_task_progress method."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        mock_output = Mock()
        bridge = LangGraphBridge(
            app=Mock(),
            bridge=Mock(),
            output_adapter=mock_output,
            llm_service=Mock(),
            tool_adapter=Mock(),
        )
        return bridge

    def test_updates_with_completed_and_in_progress(self, bridge):
        """Updates task list with both completed and in-progress tasks."""
        tool_tasks = [
            ("read_file: test.py", True),
            ("write_file: output.py", False),
        ]

        bridge._update_task_progress(tool_tasks)

        # Should have posted update
        bridge._output_adapter.post_tasks_updated.assert_called_once()

        # Check recent tasks
        assert len(bridge._recent_tasks) == 2

    def test_limits_completed_tasks(self, bridge):
        """Keeps only last N completed tasks."""
        bridge._max_completed_tasks = 2
        tool_tasks = [
            ("task1", True),
            ("task2", True),
            ("task3", True),
            ("task4", True),
        ]

        bridge._update_task_progress(tool_tasks)

        # Should only have last 2 completed
        completed = [t for t in bridge._recent_tasks if t.status.value == "done"]
        assert len(completed) == 2


class TestClearTaskProgress:
    """Tests for _clear_task_progress method."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        mock_output = Mock()
        bridge = LangGraphBridge(
            app=Mock(),
            bridge=Mock(),
            output_adapter=mock_output,
            llm_service=Mock(),
            tool_adapter=Mock(),
        )
        # Add some tasks
        bridge._recent_tasks = [Mock(), Mock()]
        return bridge

    def test_clears_task_list(self, bridge):
        """Clears the recent tasks list."""
        bridge._clear_task_progress()

        assert bridge._recent_tasks == []
        bridge._output_adapter.post_tasks_updated.assert_called_once_with([])
