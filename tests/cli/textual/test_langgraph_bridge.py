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
from scrappy.cli.textual.tui_events import TasksUpdated, TranscriptAppendText
from scrappy.cli.textual.tui_events import MetricsUpdated
from scrappy.graph.state import AgentState
from scrappy.infrastructure.threading import CancellationToken


class RecordingTuiEventSink:
    """Event sink double that records typed TUI events."""

    def __init__(self) -> None:
        self.events: list[object] = []

    def post_event(self, event: object) -> None:
        self.events.append(event)

    def flush(self, timeout: float = 5.0) -> bool:
        return True


def create_app_with_sink() -> Mock:
    """Create an app double with a typed event sink."""
    app = Mock()
    app.tui_event_sink = RecordingTuiEventSink()
    return app


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
        assert field_names == {
            "success",
            "final_state",
            "error",
            "cancelled",
            "suggestion",
        }


class TestTruncateResult:
    """Tests for _truncate_result method."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        app = create_app_with_sink()
        thread_bridge = Mock()
        output_adapter = Mock()
        orchestrator = Mock()
        tool_adapter = Mock()

        return LangGraphBridge(
            app=app,
            bridge=thread_bridge,
            output_adapter=output_adapter,
            orchestrator=orchestrator,
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
            orchestrator=Mock(),
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

    def test_write_files_extracts_summary(self, bridge):
        """write_files summarizes the batch using the first path and count."""
        result = bridge._extract_key_param(
            "write_files",
            {"files": [{"path": "a.py"}, {"path": "b.py"}]},
        )
        assert result == "a.py (+1 more)"

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

    def test_empty_args_returns_empty(self, bridge):
        """Empty args dict returns empty string."""
        result = bridge._extract_key_param("write_file", {})
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


class FakeSnapshot:
    """Minimal snapshot object for graph.get_state()."""

    def __init__(self, values: dict, next_nodes=None) -> None:
        self.values = values
        self.next = next_nodes


class FakeGraph:
    """Minimal graph stub for _run_with_streaming tests."""

    def __init__(self, event, final_state: dict) -> None:
        self._event = event
        self._final_state = final_state
        self.get_state_calls = 0

    def stream(self, input_state, config):
        yield self._event

    def get_state(self, config):
        self.get_state_calls += 1
        return FakeSnapshot(values=self._final_state)

    def update_state(self, config, values):
        pass


class TestRunWithStreaming:
    """Tests for _run_with_streaming handling AgentState events."""

    def test_posts_metrics_from_agent_state_event(self):
        """AgentState events should trigger metrics updates."""
        app = create_app_with_sink()
        bridge = LangGraphBridge(
            app=app,
            bridge=Mock(),
            output_adapter=Mock(),
            orchestrator=Mock(),
            tool_adapter=Mock(),
        )
        state = AgentState(
            input="Hello",
            original_task="Hello",
            last_input_tokens=10,
            last_output_tokens=20,
            last_model_display="gemini: gemma",
        )
        graph = FakeGraph({"think": state}, state.model_dump())

        bridge._run_with_streaming(graph, state, config={}, state_class=AgentState)

        assert app.tui_event_sink.events
        message = app.tui_event_sink.events[-1]
        assert isinstance(message, MetricsUpdated)
        assert message.provider_display == "gemini: gemma"
        assert message.input_tokens == 10
        assert message.output_tokens == 20

    def test_posts_trace_chain_as_provider_display(self):
        """Fallback trace chain is visible through the TUI metrics status path."""
        app = create_app_with_sink()
        bridge = LangGraphBridge(
            app=app,
            bridge=Mock(),
            output_adapter=Mock(),
            orchestrator=Mock(),
            tool_adapter=Mock(),
        )
        state = AgentState(
            input="Hello",
            original_task="Hello",
            last_input_tokens=10,
            last_output_tokens=20,
            last_model_display="groq: kimi-k2-instruct",
            last_trace_chain="cerebras(deprecated)->groq: moonshotai/kimi-k2-instruct",
        )
        graph = FakeGraph({"think": state}, state.model_dump())

        bridge._run_with_streaming(graph, state, config={}, state_class=AgentState)

        metrics_messages = [
            event
            for event in app.tui_event_sink.events
            if isinstance(event, MetricsUpdated)
        ]
        assert metrics_messages[-1].provider_display == (
            "cerebras(deprecated)->groq: moonshotai/kimi-k2-instruct"
        )

    def test_clean_run_replaces_previous_trace_chain_display(self):
        """A later clean model display replaces an earlier fallback breadcrumb."""
        app = create_app_with_sink()
        bridge = LangGraphBridge(
            app=app,
            bridge=Mock(),
            output_adapter=Mock(),
            orchestrator=Mock(),
            tool_adapter=Mock(),
        )
        fallback_state = AgentState(
            input="Hello",
            original_task="Hello",
            last_model_display="groq: kimi-k2-instruct",
            last_trace_chain="cerebras(deprecated)->groq: moonshotai/kimi-k2-instruct",
        )
        clean_state = AgentState(
            input="Hello again",
            original_task="Hello again",
            last_model_display="gemini: gemma",
            last_trace_chain=None,
        )

        bridge._run_with_streaming(
            FakeGraph({"think": fallback_state}, fallback_state.model_dump()),
            fallback_state,
            config={},
            state_class=AgentState,
        )
        bridge._run_with_streaming(
            FakeGraph({"think": clean_state}, clean_state.model_dump()),
            clean_state,
            config={},
            state_class=AgentState,
        )

        metrics_messages = [
            event
            for event in app.tui_event_sink.events
            if isinstance(event, MetricsUpdated)
        ]
        assert metrics_messages[-1].provider_display == "gemini: gemma"

    def test_posts_metrics_from_partial_state_dict(self):
        """Partial dict events should fall back to snapshot state."""
        app = create_app_with_sink()
        bridge = LangGraphBridge(
            app=app,
            bridge=Mock(),
            output_adapter=Mock(),
            orchestrator=Mock(),
            tool_adapter=Mock(),
        )
        state = AgentState(
            input="Hello",
            original_task="Hello",
            last_input_tokens=5,
            last_output_tokens=6,
            last_model_display="gemini: gemma",
        )
        graph = FakeGraph({"think": {"last_input_tokens": 1}}, state.model_dump())

        bridge._run_with_streaming(graph, state, config={}, state_class=AgentState)

        assert graph.get_state_calls >= 1
        assert app.tui_event_sink.events


class TestGetFilePathFromArgs:
    """Tests for _get_file_path_from_args method."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        return LangGraphBridge(
            app=Mock(),
            bridge=Mock(),
            output_adapter=Mock(),
            orchestrator=Mock(),
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
            orchestrator=Mock(),
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
            orchestrator=Mock(),
            tool_adapter=Mock(),
        )  # Should not raise

    def test_cancel_with_token_cancels_token(self, bridge):
        """cancel() cancels the token."""
        bridge._cancellation_token = CancellationToken()
        bridge.cancel()
        assert bridge._cancellation_token.is_cancelled is True

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
            orchestrator=Mock(),
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
            orchestrator=Mock(),
            tool_adapter=Mock(),
        )
        return bridge

    def test_fallback_when_no_handler(self, bridge):
        """Falls back to direct confirm when handler not set."""
        bridge._confirmation_handler = None
        bridge._bridge.blocking_confirm_yna.return_value = "y"

        result = bridge._tool_confirm_callback(
            "write_file", "Write to test.py", {"path": "test.py"}
        )

        assert result is True
        bridge._bridge.blocking_confirm_yna.assert_called_once_with("Write to test.py?")

    def test_fallback_returns_false_on_no(self, bridge):
        """Fallback returns False when user responds 'n'."""
        bridge._confirmation_handler = None
        bridge._bridge.blocking_confirm_yna.return_value = "n"

        result = bridge._tool_confirm_callback(
            "write_file", "Write to test.py", {"path": "test.py"}
        )

        assert result is False

    def test_delegates_to_handler(self, bridge):
        """Delegates to confirmation handler when set."""
        mock_handler = Mock()
        mock_handler.confirm_tool.return_value = True
        bridge._confirmation_handler = mock_handler

        result = bridge._tool_confirm_callback(
            "write_file", "Write to test.py", {"path": "test.py", "content": "data"}
        )

        assert result is True
        mock_handler.confirm_tool.assert_called_once_with(
            "write_file", "Write to test.py", {"path": "test.py", "content": "data"}
        )

    def test_handler_returns_false(self, bridge):
        """Returns False when handler denies."""
        mock_handler = Mock()
        mock_handler.confirm_tool.return_value = False
        bridge._confirmation_handler = mock_handler

        result = bridge._tool_confirm_callback(
            "write_file", "Write to test.py", {"path": "test.py"}
        )

        assert result is False


class TestRunAgentConcurrencyGuard:
    """Tests for run_agent concurrency guard."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        return LangGraphBridge(
            app=Mock(),
            bridge=Mock(),
            output_adapter=Mock(),
            orchestrator=Mock(),
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
        app = create_app_with_sink()
        bridge = LangGraphBridge(
            app=app,
            bridge=Mock(),
            output_adapter=Mock(),
            orchestrator=Mock(),
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

        task_events = [
            event
            for event in bridge.app.tui_event_sink.events
            if isinstance(event, TasksUpdated)
        ]
        assert len(task_events) == 1
        assert len(task_events[0].tasks) == 2

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


class TestMetricsUpdates:
    """Tests for metrics update tracking."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        app = create_app_with_sink()
        return LangGraphBridge(
            app=app,
            bridge=Mock(),
            output_adapter=Mock(),
            orchestrator=Mock(),
            tool_adapter=Mock(),
        )

    def test_metrics_update_accumulates_session_total(self, bridge):
        """Session total increments with each metrics update."""
        bridge._post_metrics_update(
            provider_display="gemini: gemma",
            input_tokens=100,
            output_tokens=200,
        )

        first_message = bridge.app.tui_event_sink.events[0]
        assert isinstance(first_message, MetricsUpdated)
        assert first_message.session_total == 300
        assert first_message.provider_display == "gemini: gemma"
        assert first_message.input_tokens == 100
        assert first_message.output_tokens == 200

        bridge._post_metrics_update(
            provider_display="gemini: gemma",
            input_tokens=50,
            output_tokens=150,
        )

        second_message = bridge.app.tui_event_sink.events[1]
        assert second_message.session_total == 500

    def test_metrics_update_does_not_increment_without_tokens(self, bridge):
        """Session total stays unset when tokens are not provided."""
        bridge._post_metrics_update(provider_display="gemini: gemma")

        message = bridge.app.tui_event_sink.events[0]
        assert isinstance(message, MetricsUpdated)
        assert message.session_total is None


class TestClearTaskProgress:
    """Tests for _clear_task_progress method."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge with mocked dependencies."""
        app = create_app_with_sink()
        bridge = LangGraphBridge(
            app=app,
            bridge=Mock(),
            output_adapter=Mock(),
            orchestrator=Mock(),
            tool_adapter=Mock(),
        )
        # Add some tasks
        bridge._recent_tasks = [Mock(), Mock()]
        return bridge

    def test_clears_task_list(self, bridge):
        """Clears the recent tasks list."""
        bridge._clear_task_progress()

        assert bridge._recent_tasks == []
        task_events = [
            event
            for event in bridge.app.tui_event_sink.events
            if isinstance(event, TasksUpdated)
        ]
        assert len(task_events) == 1
        assert task_events[0].tasks == []


class TestOutputCallback:
    """Tests for worker output routing."""

    def test_output_callback_posts_transcript_text(self):
        """Agent output should route through the typed TUI event sink."""
        app = create_app_with_sink()
        bridge = LangGraphBridge(
            app=app,
            bridge=Mock(),
            output_adapter=Mock(),
            orchestrator=Mock(),
            tool_adapter=Mock(),
        )

        bridge._output_callback("hello")

        assert app.tui_event_sink.events == [TranscriptAppendText(content="hello")]


def make_failed_state(
    last_error: str,
    error_suggestion: "str | None" = None,
) -> AgentState:
    """Build a terminal failed AgentState for display/plumbing tests."""
    return AgentState.create_initial("task", "/tmp").model_copy(
        update={
            "done": True,
            "last_error": last_error,
            "error_suggestion": error_suggestion,
        }
    )


class TestFailureSuggestionDisplay:
    """PR-4 Option D: the suggestion channel reaches the failed summary."""

    @pytest.fixture
    def app_and_bridge(self):
        app = create_app_with_sink()
        bridge = LangGraphBridge(
            app=app,
            bridge=Mock(),
            output_adapter=Mock(),
            orchestrator=Mock(),
            tool_adapter=Mock(),
        )
        return app, bridge

    def _transcript_text(self, app) -> str:
        return "".join(
            event.content
            for event in app.tui_event_sink.events
            if isinstance(event, TranscriptAppendText)
        )

    def test_failed_summary_renders_untruncated_suggestion_line(
        self, app_and_bridge
    ):
        app, bridge = app_and_bridge
        state = make_failed_state(
            last_error="Rate limit exceeded for groq",
            error_suggestion="Wait 30s or add another provider API key.",
        )

        bridge._output_completion_summary(success=False, final_state=state)

        text = self._transcript_text(app)
        assert "[failed]" in text
        assert "  Suggestion: Wait 30s or add another provider API key.\n" in text

    def test_failed_summary_has_no_suggestion_line_when_absent(
        self, app_and_bridge
    ):
        app, bridge = app_and_bridge
        state = make_failed_state(last_error="Tool execution failed")

        bridge._output_completion_summary(success=False, final_state=state)

        text = self._transcript_text(app)
        assert "[failed]" in text
        assert "Suggestion:" not in text

    def test_run_agent_failure_result_carries_suggestion(
        self, app_and_bridge, tmp_path
    ):
        """AgentResult.suggestion is populated from final_state.error_suggestion."""
        app, bridge = app_and_bridge
        final_state = make_failed_state(
            last_error="Rate limit exceeded for groq",
            error_suggestion="Wait 30s or add another provider API key.",
        )
        bridge._run_with_streaming = Mock(return_value=final_state)

        with patch(
            "scrappy.graph.agent.create_agent_runner",
            return_value=(Mock(), Mock()),
        ):
            result = bridge.run_agent("task", str(tmp_path))

        assert result.success is False
        assert result.error == "Rate limit exceeded for groq"
        assert result.suggestion == "Wait 30s or add another provider API key."
