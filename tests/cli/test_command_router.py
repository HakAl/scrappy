"""
Tests for CommandRouter.

Tests command routing, handler dispatch, and individual command handlers.
"""

import json

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from scrappy.cli.command_router import CommandRouter
from scrappy.cli.io_interface import TestIO
from scrappy.cli.validators.command import CommandValidationResult
from scrappy.orchestrator.core import AgentOrchestrator
from scrappy.orchestrator.memory import WorkingMemory
from scrappy.orchestrator.model_selection import (
    ModelSelectionService,
    ModelSelectionType,
)
from scrappy.orchestrator.session import SessionManager


FAST_MODEL = "groq/llama-3.1-8b-instant"
CHAT_MODEL = "groq/llama-3.3-70b-versatile"
INSTRUCT_MODEL = "cerebras/gpt-oss-120b"


def make_selection_service(
    default_type: ModelSelectionType = ModelSelectionType.CHAT,
) -> ModelSelectionService:
    """Build a real selection service with one known model per tier."""
    return ModelSelectionService(
        configured_models={FAST_MODEL, CHAT_MODEL, INSTRUCT_MODEL},
        model_priorities={
            ModelSelectionType.FAST: [FAST_MODEL],
            ModelSelectionType.CHAT: [CHAT_MODEL],
            ModelSelectionType.INSTRUCT: [INSTRUCT_MODEL],
        },
        default_selection_type=default_type,
    )


class MockTheme:
    """Mock theme for TestIO."""
    primary = "blue"
    success = "green"
    warning = "yellow"
    error = "red"
    info = "cyan"
    accent = "magenta"


@pytest.fixture
def mock_io():
    """Create TestIO with mock theme."""
    io = TestIO()
    io.theme = MockTheme()
    return io


@pytest.fixture
def mock_orchestrator():
    """Create mock orchestrator."""
    orch = Mock()
    orch.llm_service = Mock()
    return orch


@pytest.fixture
def mock_session_saver():
    """Create mock session saver seam."""
    saver = Mock()
    saver.save_session.return_value = "/tmp/session.json"
    return saver


@pytest.fixture
def mock_model_selection():
    """Create mock model selection service."""
    selection = Mock()
    selection.select.return_value = "openai/gpt-4"
    selection.get_default_type.return_value = ModelSelectionType.FAST
    return selection


@pytest.fixture
def mock_session_context():
    """Create mock session context."""
    ctx = Mock()
    ctx.auto_save = True
    ctx.verbose_mode = False
    ctx.conversation_history = []
    return ctx


@pytest.fixture
def mock_display():
    """Create mock display."""
    return Mock()


@pytest.fixture
def mock_session_mgr():
    """Create mock session manager."""
    return Mock()


@pytest.fixture
def mock_codebase():
    """Create mock codebase analysis."""
    return Mock()


@pytest.fixture
def mock_tasks():
    """Create mock task execution."""
    return Mock()


@pytest.fixture
def mock_agent_mgr():
    """Create mock agent manager."""
    return Mock()


@pytest.fixture
def router(
    mock_io,
    mock_orchestrator,
    mock_session_context,
    mock_display,
    mock_session_mgr,
    mock_codebase,
    mock_tasks,
    mock_agent_mgr,
    mock_session_saver,
    mock_model_selection,
):
    """Create CommandRouter with all mock dependencies."""
    return CommandRouter(
        io=mock_io,
        orchestrator=mock_orchestrator,
        session_context=mock_session_context,
        display=mock_display,
        session_mgr=mock_session_mgr,
        codebase=mock_codebase,
        tasks=mock_tasks,
        agent_mgr=mock_agent_mgr,
        session_saver=mock_session_saver,
        model_selection=mock_model_selection,
    )


class TestRouteDispatch:
    """Tests for route() method dispatch logic."""

    def test_route_valid_command_to_handler(self, router, mock_display):
        """Valid command routes to correct handler."""
        result = router.route("/help", "")

        assert result is True
        mock_display.show_help.assert_called_once()

    def test_route_returns_handler_result(self, router):
        """route() returns the handler's return value."""
        # /quit returns False to exit
        result = router.route("/quit", "")
        assert result is False

    def test_route_unknown_command_shows_warning(self, router, mock_io):
        """Unknown command shows warning and returns True."""
        result = router.route("/unknown", "")

        assert result is True
        output = mock_io.get_output()
        assert "Unknown command" in output

    def test_route_invalid_command_shows_error(self, router, mock_io):
        """Invalid command shows error message."""
        with patch("scrappy.cli.command_router.validate_command") as mock_validate:
            mock_validate.return_value = CommandValidationResult(
                is_valid=False,
                error="Command too long"
            )

            result = router.route("/toolongcommand", "x" * 6000)

            assert result is True
            output = mock_io.get_output()
            assert "Invalid command" in output


class TestExitCommands:
    """Tests for exit command handlers."""

    def test_quit_returns_false(self, router):
        """_handle_exit returns False to exit loop."""
        result = router._handle_exit("")
        assert result is False

    def test_exit_shows_goodbye(self, router, mock_io):
        """Exit shows goodbye message."""
        router._handle_exit("")

        output = mock_io.get_output()
        assert "Goodbye" in output

    def test_exit_handles_save_error(self, router, mock_session_saver, mock_io):
        """Exit handles session save error gracefully."""
        mock_session_saver.save_session.side_effect = Exception("Save failed")

        result = router._handle_exit("")

        assert result is False  # Still exits
        # Error should be reported but not crash
        # The warning utility should be called

    def test_exit_passes_history_to_session_saver(
        self, router, mock_session_saver, mock_session_context
    ):
        """_handle_exit hands the real conversation history to the seam."""
        history = [{"role": "user", "content": "hi"}]
        mock_session_context.conversation_history = history

        router._handle_exit("")

        mock_session_saver.save_session.assert_called_once_with(history)


class TestDisplayCommands:
    """Tests for display command handlers."""

    def test_help_shows_help(self, router, mock_display):
        """_handle_help calls display.show_help."""
        result = router._handle_help("")

        assert result is True
        mock_display.show_help.assert_called_once()

    def test_status_shows_status(self, router, mock_display):
        """_handle_status calls display.show_status."""
        result = router._handle_status("")

        assert result is True
        mock_display.show_status.assert_called_once()

    def test_usage_shows_usage(self, router, mock_display):
        """_handle_usage calls display.show_usage."""
        result = router._handle_usage("")

        assert result is True
        mock_display.show_usage.assert_called_once()

    def test_models_lists_models(self, router, mock_display):
        """_handle_models calls display.list_models."""
        result = router._handle_models("openai")

        assert result is True
        mock_display.list_models.assert_called_once_with("openai")


class TestModelCommand:
    """Tests for /model command."""

    def test_model_fast_sets_default_type_fast(self, router, mock_model_selection):
        """Setting fast tier sets the session default to FAST."""
        router._handle_model("fast")

        mock_model_selection.set_default_type.assert_called_once_with(
            ModelSelectionType.FAST
        )

    def test_model_chat_sets_default_type_chat(self, router, mock_model_selection):
        """Setting chat tier sets the session default to CHAT."""
        router._handle_model("chat")

        mock_model_selection.set_default_type.assert_called_once_with(
            ModelSelectionType.CHAT
        )

    def test_model_instruct_sets_default_type_chat(self, router, mock_model_selection):
        """Setting instruct tier keeps the CHAT session default (quirk preserved)."""
        router._handle_model("instruct")

        mock_model_selection.set_default_type.assert_called_once_with(
            ModelSelectionType.CHAT
        )

    def test_model_quality_backwards_compat(self, router, mock_model_selection):
        """'quality' tier maps to the CHAT default for backwards compat."""
        router._handle_model("quality")

        mock_model_selection.set_default_type.assert_called_once_with(
            ModelSelectionType.CHAT
        )

    def test_model_no_arg_shows_current(self, router, mock_io, mock_model_selection):
        """No argument shows current tier."""
        mock_model_selection.get_default_type.return_value = ModelSelectionType.CHAT

        router._handle_model("")

        output = mock_io.get_output()
        assert "Current tier" in output

    def test_model_display_success_shows_model_id(
        self, router, mock_io, mock_model_selection
    ):
        """Tier switch success displays the selected model id."""
        mock_model_selection.select.return_value = "anthropic/claude-3"

        router._handle_model("chat")

        output = mock_io.get_output()
        assert "  Using: anthropic/claude-3\n" in output

    def test_model_display_failure_shows_warning(
        self, router, mock_io, mock_model_selection
    ):
        """Model command handles selection error gracefully."""
        mock_model_selection.select.side_effect = Exception("No key")

        result = router._handle_model("fast")

        assert result is True  # Still returns True
        output = mock_io.get_output()
        assert "Warning: Could not determine model - No key" in output


class TestSessionCommands:
    """Tests for session-related command handlers."""

    def test_context_delegates(self, router, mock_session_mgr):
        """_handle_context delegates to session_mgr."""
        result = router._handle_context("show")

        assert result is True
        mock_session_mgr.manage_context.assert_called_once_with("show")

    def test_cache_delegates(self, router, mock_session_mgr):
        """_handle_cache delegates to session_mgr."""
        result = router._handle_cache("clear")

        assert result is True
        mock_session_mgr.manage_cache.assert_called_once_with("clear")

    def test_session_delegates(self, router, mock_session_mgr):
        """_handle_session delegates to session_mgr."""
        result = router._handle_session("save")

        assert result is True
        mock_session_mgr.manage_session.assert_called_once_with("save")

    def test_limits_delegates(self, router, mock_session_mgr):
        """_handle_limits delegates to session_mgr."""
        result = router._handle_limits("")

        assert result is True
        mock_session_mgr.show_rate_limits.assert_called_once_with("")


class TestTaskCommands:
    """Tests for task-related command handlers."""

    def test_plan_no_args_shows_usage(self, router, mock_io):
        """_handle_plan with no args shows usage."""
        result = router._handle_plan("")

        assert result is True
        output = mock_io.get_output()
        assert "Usage:" in output

    def test_plan_starts_on_confirm(self, router, mock_tasks, mock_io):
        """_handle_plan starts plan when user confirms."""
        mock_tasks.plan_task.return_value = ["step1", "step2"]
        mock_io._confirmations = [True]

        router._handle_plan("build a feature")

        assert router.state_manager.plan_active is True

    def test_reason_no_args_shows_usage(self, router, mock_io):
        """_handle_reason with no args shows usage."""
        result = router._handle_reason("")

        assert result is True
        output = mock_io.get_output()
        assert "Usage:" in output


class TestAgentCommand:
    """Tests for /agent command."""

    def test_agent_no_args_shows_usage(self, router, mock_io):
        """_handle_agent with no args shows usage."""
        result = router._handle_agent("")

        assert result is True
        output = mock_io.get_output()
        assert "Usage:" in output

    @patch("scrappy.cli.command_router.check_agent_dependencies")
    def test_agent_fails_on_missing_deps(self, mock_deps, router, mock_io, mock_agent_mgr):
        """_handle_agent fails when dependencies missing."""
        mock_deps.return_value = (False, ["Missing langgraph"])

        result = router._handle_agent("do something")

        assert result is True
        mock_agent_mgr.run_agent.assert_not_called()
        output = mock_io.get_output()
        assert "missing dependencies" in output.lower()

    @patch("scrappy.cli.command_router.check_agent_dependencies")
    @patch("scrappy.cli.command_router.check_optional_dependencies")
    def test_agent_parses_dry_run_flag(
        self, mock_optional, mock_deps, router, mock_agent_mgr
    ):
        """_handle_agent parses --dry-run flag and extracts task."""
        mock_deps.return_value = (True, [])
        mock_optional.return_value = []

        router._handle_agent("--dry-run do something")

        mock_agent_mgr.run_agent.assert_called_once()
        call_args = mock_agent_mgr.run_agent.call_args
        # First positional arg is the task with flag stripped
        assert call_args[0][0] == "do something"
        # dry_run flag is True
        assert call_args[1]["dry_run"] is True

    @patch("scrappy.cli.command_router.check_agent_dependencies")
    @patch("scrappy.cli.command_router.check_optional_dependencies")
    def test_agent_parses_verbose_flag(
        self, mock_optional, mock_deps, router, mock_agent_mgr
    ):
        """_handle_agent parses --verbose flag and extracts task."""
        mock_deps.return_value = (True, [])
        mock_optional.return_value = []

        router._handle_agent("--verbose do something")

        mock_agent_mgr.run_agent.assert_called_once()
        call_args = mock_agent_mgr.run_agent.call_args
        # First positional arg is the task with flag stripped
        assert call_args[0][0] == "do something"
        # verbose flag is True
        assert call_args[1]["verbose"] is True


class TestExploreCommand:
    """Tests for /explore command."""

    def test_explore_delegates(self, router, mock_codebase):
        """_handle_explore delegates to codebase."""
        result = router._handle_explore("src/")

        assert result is True
        mock_codebase.explore_codebase.assert_called_once_with("src/")


class TestClearCommand:
    """Tests for /clear command."""

    def test_clear_clears_history(self, router, mock_session_context, mock_io):
        """_handle_clear clears conversation history."""
        # Use a real list to test clear behavior
        history_list = [{"role": "user", "content": "hi"}]
        mock_session_context.conversation_history = history_list

        result = router._handle_clear("")

        assert result is True
        assert len(history_list) == 0  # List should be empty after clear

    def test_clear_shows_confirmation(self, router, mock_io, mock_session_context):
        """_handle_clear shows confirmation message."""
        mock_session_context.conversation_history = []

        router._handle_clear("")

        output = mock_io.get_output()
        assert "cleared" in output.lower()


class TestHistoryCommand:
    """Tests for /history command."""

    def test_history_empty_shows_warning(self, router, mock_io, mock_session_context):
        """_handle_history shows warning when empty."""
        mock_session_context.conversation_history = []

        result = router._handle_history("")

        assert result is True
        output = mock_io.get_output()
        assert "No conversation history" in output

    def test_history_shows_messages(self, router, mock_io, mock_session_context):
        """_handle_history shows messages."""
        mock_session_context.conversation_history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

        router._handle_history("")

        output = mock_io.get_output()
        assert "hello" in output
        assert "hi there" in output

    def test_history_limits_to_n(self, router, mock_io, mock_session_context):
        """_handle_history limits to n messages."""
        mock_session_context.conversation_history = [
            {"role": "user", "content": f"msg{i}"} for i in range(20)
        ]

        router._handle_history("5")

        output = mock_io.get_output()
        assert "5 of 20" in output

    def test_history_invalid_count_shows_error(self, router, mock_io, mock_session_context):
        """_handle_history shows error for invalid count."""
        mock_session_context.conversation_history = [{"role": "user", "content": "hi"}]

        router._handle_history("abc")

        output = mock_io.get_output()
        assert "Invalid count" in output

    def test_history_zero_count_shows_error(self, router, mock_io, mock_session_context):
        """_handle_history rejects zero or negative count."""
        mock_session_context.conversation_history = [{"role": "user", "content": "hi"}]

        router._handle_history("0")

        output = mock_io.get_output()
        assert "positive number" in output

    def test_history_truncates_long_messages(self, router, mock_io, mock_session_context):
        """_handle_history truncates long messages."""
        mock_session_context.conversation_history = [
            {"role": "user", "content": "x" * 500}
        ]

        router._handle_history("")

        output = mock_io.get_output()
        assert "..." in output


class TestAutoexecCommand:
    """Tests for /autoexec command."""

    def test_autoexec_toggles_state(self, router, mock_io):
        """_handle_autoexec toggles auto_execute_tasks."""
        initial = router.state_manager.auto_execute_tasks

        router._handle_autoexec("")

        assert router.state_manager.auto_execute_tasks != initial

    def test_autoexec_shows_status(self, router, mock_io):
        """_handle_autoexec shows current status."""
        router._handle_autoexec("")

        output = mock_io.get_output()
        assert "Auto-execute" in output


class TestVerboseCommand:
    """Tests for /verbose command."""

    def test_verbose_toggles_state(self, router, mock_session_context):
        """_handle_verbose toggles verbose_mode."""
        mock_session_context.verbose_mode = False

        router._handle_verbose("")

        assert mock_session_context.verbose_mode is True

    def test_verbose_shows_status(self, router, mock_io, mock_session_context):
        """_handle_verbose shows current status."""
        mock_session_context.verbose_mode = False

        router._handle_verbose("")

        output = mock_io.get_output()
        assert "Verbose mode" in output


class TestTasksCommand:
    """Tests for /tasks command."""

    def test_tasks_no_plan_shows_warning(self, router, mock_io):
        """_handle_tasks shows warning when no plan."""
        router.state_manager.plan_active = False

        result = router._handle_tasks("")

        assert result is True
        output = mock_io.get_output()
        assert "No active plan" in output


class TestSetupCommand:
    """Tests for /setup command."""

    def test_setup_uses_wizard_callback_if_set(self, router):
        """_handle_setup uses TUI callback when set."""
        mock_callback = Mock()
        router.set_setup_wizard_callback(mock_callback)

        result = router._handle_setup("")

        assert result is True
        mock_callback.assert_called_once()


class TestSetWizardCallback:
    """Tests for set_setup_wizard_callback method."""

    def test_sets_callback(self, router):
        """set_setup_wizard_callback stores callback."""
        callback = Mock()

        router.set_setup_wizard_callback(callback)

        assert router._setup_wizard_callback is callback


class TestHandleExistingTasks:
    """Tests for _handle_existing_tasks method."""

    @patch("scrappy.agent_tools.tools.task_tools.MarkdownTaskStorage")
    @patch("scrappy.infrastructure.paths.ScrappyPathProvider")
    def test_no_tasks_returns_true(self, mock_path_class, mock_storage_class, router, mock_io):
        """Returns True when no task file exists."""
        mock_path = Mock()
        mock_path.todo_file.return_value = Path("/tmp/todo.md")
        mock_path_class.return_value = mock_path

        mock_storage = Mock()
        mock_storage.exists.return_value = False
        mock_storage_class.return_value = mock_storage

        result = router._handle_existing_tasks(mock_io, clear_tasks=False)

        assert result is True

    @patch("scrappy.agent_tools.tools.task_tools.MarkdownTaskStorage")
    @patch("scrappy.infrastructure.paths.ScrappyPathProvider")
    def test_no_pending_tasks_returns_true(self, mock_path_class, mock_storage_class, router, mock_io):
        """Returns True when all tasks are done."""
        from scrappy.cli.protocols import TaskStatus

        mock_path = Mock()
        mock_path.todo_file.return_value = Path("/tmp/todo.md")
        mock_path_class.return_value = mock_path

        mock_storage = Mock()
        mock_storage.exists.return_value = True
        mock_task = Mock()
        mock_task.status = TaskStatus.DONE
        mock_storage.read_tasks.return_value = [mock_task]
        mock_storage_class.return_value = mock_storage

        result = router._handle_existing_tasks(mock_io, clear_tasks=False)

        assert result is True

    @patch("scrappy.agent_tools.tools.task_tools.MarkdownTaskStorage")
    @patch("scrappy.infrastructure.paths.ScrappyPathProvider")
    def test_clear_flag_clears_tasks(self, mock_path_class, mock_storage_class, router, mock_io):
        """clear_tasks=True clears without prompting."""
        from scrappy.cli.protocols import TaskStatus

        mock_path = Mock()
        mock_path.todo_file.return_value = Path("/tmp/todo.md")
        mock_path_class.return_value = mock_path

        mock_storage = Mock()
        mock_storage.exists.return_value = True
        mock_task = Mock()
        mock_task.status = TaskStatus.PENDING
        mock_storage.read_tasks.return_value = [mock_task]
        mock_storage_class.return_value = mock_storage

        result = router._handle_existing_tasks(mock_io, clear_tasks=True)

        # Verified existing tasks before clearing
        mock_storage.exists.assert_called_once()
        mock_storage.read_tasks.assert_called_once()
        # Cleared without prompting
        mock_storage.clear.assert_called_once()
        assert result is True
        # Confirmation message shown
        output = mock_io.get_output()
        assert "cleared" in output.lower()


class TestModelCommandCopyPins:
    """Characterization pins for /model command copy (PR-5).

    Uses a real ModelSelectionService so the "Using: {model_id}" line pins
    the actual selection surface: the user sees the concrete model id, not
    a group name.
    """

    @pytest.mark.parametrize(
        "arg, expected_lines",
        [
            (
                "fast",
                [
                    "Switched to FAST tier\n",
                    f"  Using: {FAST_MODEL}\n",
                    "  8B models, high throughput\n",
                ],
            ),
            (
                "chat",
                [
                    "Switched to CHAT tier\n",
                    f"  Using: {CHAT_MODEL}\n",
                    "  70B models, conversation\n",
                ],
            ),
            (
                "instruct",
                [
                    "Switched to INSTRUCT tier\n",
                    f"  Using: {INSTRUCT_MODEL}\n",
                    "  Instruction-tuned models (agent/tools)\n",
                ],
            ),
            (
                "quality",
                [
                    "Switched to QUALITY tier\n",
                    f"  Using: {CHAT_MODEL}\n",
                ],
            ),
        ],
    )
    def test_model_tier_switch_copy(self, router, mock_io, arg, expected_lines):
        """Tier switch prints the switch line and the real model id line."""
        router.model_selection = make_selection_service()

        result = router._handle_model(arg)

        assert result is True
        output = mock_io.get_output()
        for line in expected_lines:
            assert line in output

    def test_model_unknown_arg_usage_copy(self, router, mock_io):
        """Unknown argument shows the current tier and the usage line."""
        router.model_selection = make_selection_service(
            default_type=ModelSelectionType.FAST
        )

        result = router._handle_model("warp")

        assert result is True
        output = mock_io.get_output()
        assert "Current tier: FAST\n" in output
        assert f"  Using: {FAST_MODEL}\n" in output
        assert "Usage: /model fast | /model chat | /model instruct\n" in output


class TestQuitCopyPins:
    """Characterization pins for /quit output copy (PR-5)."""

    def test_quit_saved_display_copy(
        self, router, mock_io, mock_session_context, mock_display
    ):
        """Auto-save quit shows the saved path, message count, resume help, goodbye."""
        mock_session_context.conversation_history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]

        result = router._handle_exit("")

        assert result is False
        output = mock_io.get_output()
        assert "\nSession saved to: /tmp/session.json\n" in output
        assert "  Conversation: 2 messages\n" in output
        assert "Use 'llm-team --resume' to continue later.\n" in output
        assert "\nGoodbye!\n" in output
        mock_display.show_usage.assert_called_once()

    def test_quit_not_saved_warning_copy(
        self, router, mock_io, mock_session_saver, mock_session_context
    ):
        """Disabled auto-save quit shows the not-saved warning and manual-save hint."""
        mock_session_context.auto_save = False

        result = router._handle_exit("")

        assert result is False
        mock_session_saver.save_session.assert_not_called()
        output = mock_io.get_output()
        assert "\nSession not saved (auto-save disabled).\n" in output
        assert "Use '/session save' to manually save before quitting.\n" in output
        assert "\nGoodbye!\n" in output

    def test_quit_autosave_writes_real_history(self, mock_io, tmp_path):
        """FIXED (scrappy-9qf3): /quit autosave persists the real history.

        _handle_exit passes session_context.conversation_history through the
        session-saver seam, so the saved payload carries the real messages
        and the displayed count matches what was written.
        """
        orchestrator = AgentOrchestrator(
            output=Mock(),
            registry=Mock(),
            cache=Mock(),
            rate_tracker=Mock(),
            working_memory=WorkingMemory(),
            session_manager=SessionManager(tmp_path),
            usage_reporter=Mock(),
            status_reporter=Mock(),
            task_executor=Mock(),
            context_manager=Mock(),
            delegation_manager=Mock(),
            background_manager=Mock(),
        )
        session_context = Mock()
        session_context.auto_save = True
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ]
        session_context.conversation_history = history
        router = CommandRouter(
            io=mock_io,
            orchestrator=orchestrator,
            session_context=session_context,
            display=Mock(),
            session_mgr=Mock(),
            codebase=Mock(),
            tasks=Mock(),
            agent_mgr=Mock(),
            session_saver=orchestrator,
            model_selection=Mock(),
        )

        result = router._handle_exit("")

        assert result is False
        saved = json.loads((tmp_path / ".scrappy" / "session.json").read_text())
        # The fix: the saved payload carries the real history.
        assert saved["conversation_history"] == history
        # And the display reports the same message count.
        assert "  Conversation: 3 messages\n" in mock_io.get_output()


class TestSetupCliBranchPin:
    """Regression pin for the /setup CLI (non-TUI) branch (PR-5)."""

    @patch("scrappy.orchestrator.key_validator.create_key_validator")
    @patch("scrappy.cli.setup_wizard.SetupWizard")
    def test_setup_cli_branch_runs_wizard_then_refreshes_providers(
        self, mock_wizard_class, mock_create_validator, router, mock_io, mock_orchestrator
    ):
        """CLI /setup runs the wizard, then refreshes provider configuration."""
        order = []
        mock_wizard_class.return_value.run.side_effect = (
            lambda **kwargs: order.append("wizard_run")
        )
        mock_orchestrator.refresh_provider_configuration.side_effect = (
            lambda: order.append("refresh")
        )

        result = router._handle_setup("")

        assert result is True
        assert "Launching provider setup wizard...\n" in mock_io.get_output()
        mock_wizard_class.return_value.run.assert_called_once_with(allow_cancel=True)
        assert order == ["wizard_run", "refresh"]
