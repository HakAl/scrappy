"""
Tests for extracted agent components.

Uses test doubles to verify behavior without concrete dependencies.
"""
import pytest
from scrappy.agent.types import AgentAction, ActionResult, ConversationState
from scrappy.agent_tools.tools.base import ToolResult


# =============================================================================
# Test Doubles
# =============================================================================

class TestAgentUI:
    """Test double for AgentUIProtocol."""
    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(self):
        self.shown_thinking = []
        self.shown_tool_requests = []
        self.shown_commands = []
        self.shown_errors = []
        self.shown_results = []
        self.shown_warnings = []
        self.shown_progress = []
        self.confirmations_requested = []
        self.confirmation_responses = []

    def show_thinking(self, text: str) -> None:
        self.shown_thinking.append(text)

    def show_tool_request(self, tool_name: str, params: dict) -> None:
        self.shown_tool_requests.append((tool_name, params))

    def show_command(self, command: str) -> None:
        self.shown_commands.append(command)

    def show_error(self, message: str) -> None:
        self.shown_errors.append(message)

    def show_result(self, result: str, title: str = "Result", is_error: bool = False) -> None:
        self.shown_results.append((result, title, is_error))

    def show_warning(self, message: str) -> None:
        self.shown_warnings.append(message)

    def show_progress(self, message: str) -> None:
        self.shown_progress.append(message)

    def show_diff_preview(self, path: str, diff_lines: list, max_lines: int = 30) -> None:
        pass  # No-op for tests

    def show_provider_status(self, provider: str, message: str, color: str = "cyan") -> None:
        pass

    def show_rule(self, title: str = None) -> None:
        pass

    def prompt_confirm(self, message: str = "Allow?", default: bool = False) -> bool:
        self.confirmations_requested.append(message)
        if self.confirmation_responses:
            return self.confirmation_responses.pop(0)
        return default

    def prompt_action_confirm(self, message: str = "Allow this action?") -> str:
        """Test double for action confirmation with allow-all option."""
        self.confirmations_requested.append(message)
        if self.confirmation_responses:
            response = self.confirmation_responses.pop(0)
            # Convert bool to string for backward compat with existing tests
            if isinstance(response, bool):
                return 'y' if response else 'n'
            return response
        return 'n'  # Default deny

    def confirm_batch(self, actions: list) -> bool:
        """Test double for batch confirmation."""
        self.confirmations_requested.append(("batch", actions))
        if self.confirmation_responses:
            return self.confirmation_responses.pop(0)
        return False  # Default deny for safety


class PermissiveSafetyChecker:
    """Test double - all actions are safe."""

    def is_safe_action(self, action: AgentAction) -> bool:
        return True

    def requires_confirmation(self, action: AgentAction, auto_confirm: bool) -> bool:
        return False


class StrictSafetyChecker:
    """Test double - no actions are safe."""

    def is_safe_action(self, action: AgentAction) -> bool:
        return False

    def requires_confirmation(self, action: AgentAction, auto_confirm: bool) -> bool:
        return not auto_confirm


class NoDuplicateDetector:
    """Test double - never detects duplicates."""

    def check_duplicate(self, action: AgentAction, state: ConversationState) -> tuple[bool, str]:
        return (False, "")


class AlwaysDuplicateDetector:
    """Test double - always detects duplicates."""

    def __init__(self, warning: str = "Duplicate detected"):
        self.warning = warning

    def check_duplicate(self, action: AgentAction, state: ConversationState) -> tuple[bool, str]:
        return (True, self.warning)


class MockToolRunner:
    """Test double - returns preset results."""

    def __init__(self, default_result: str = "Success", default_success: bool = True):
        self.default_result = default_result
        self.default_success = default_success
        self.calls = []
        self.results = {}
        self.tools = {"read_file": lambda **kw: ToolResult(success=True, output=self.default_result)}  # Mock tools dict

    def set_result(self, tool_name: str, result: str, success: bool = True) -> None:
        """Configure result for specific tool."""
        self.results[tool_name] = ToolResult(success=success, output=result)

    def run_tool(self, tool_name: str, parameters: dict) -> ToolResult:
        self.calls.append((tool_name, parameters))
        return self.results.get(tool_name, ToolResult(success=self.default_success, output=self.default_result))


# =============================================================================
# ActionExecutor Tests (Integration of Components)
# =============================================================================

def test_executor_runs_safe_action_without_confirmation():
    """Safe actions should execute without user confirmation."""
    # Arrange
    from scrappy.agent.action_executor import ActionExecutor

    ui = TestAgentUI()
    safety = PermissiveSafetyChecker()
    duplicate = NoDuplicateDetector()
    runner = MockToolRunner(default_result="File contents")

    executor = ActionExecutor(safety, duplicate, runner, ui)

    action = AgentAction(
        thought="Reading test file",
        action="read_file",
        parameters={"path": "test.py"},
        is_complete=False
    )
    state = ConversationState(auto_confirm=False)

    # Act
    result = executor.execute(action, state)

    # Assert
    assert result.success is True
    assert result.output == "File contents"
    assert result.approved is True
    assert result.executed is True
    assert len(ui.confirmations_requested) == 0  # No confirmation needed
    assert ("read_file", {"path": "test.py"}) in runner.calls


def test_executor_requests_confirmation_for_unsafe_action():
    """Unsafe actions should require confirmation when auto_confirm=False."""
    # Arrange
    from scrappy.agent.action_executor import ActionExecutor

    ui = TestAgentUI()
    ui.confirmation_responses = [True]  # User approves
    safety = StrictSafetyChecker()
    duplicate = NoDuplicateDetector()
    runner = MockToolRunner(default_result="File written")
    runner.tools["write_file"] = lambda **kw: "File written"  # Add write_file tool

    executor = ActionExecutor(safety, duplicate, runner, ui)

    action = AgentAction(
        thought="Writing configuration",
        action="write_file",
        parameters={"path": "config.json", "content": "{}"},
        is_complete=False
    )
    state = ConversationState(auto_confirm=False)

    # Act
    result = executor.execute(action, state)

    # Assert
    assert result.success is True
    assert result.approved is True
    assert result.executed is True
    assert len(ui.confirmations_requested) == 1  # Confirmation requested


def test_executor_blocks_duplicate_action():
    """Duplicate actions should be rejected without execution."""
    # Arrange
    from scrappy.agent.action_executor import ActionExecutor

    ui = TestAgentUI()
    safety = PermissiveSafetyChecker()
    duplicate = AlwaysDuplicateDetector("Action already attempted")
    runner = MockToolRunner()

    executor = ActionExecutor(safety, duplicate, runner, ui)

    action = AgentAction(
        thought="Reading file again",
        action="read_file",
        parameters={"path": "test.py"},
        is_complete=False
    )
    state = ConversationState()

    # Act
    result = executor.execute(action, state)

    # Assert
    assert result.success is False
    assert "already attempted" in result.output
    assert result.executed is False  # Never executed
    assert len(runner.calls) == 0  # Tool was not called
    assert len(ui.shown_warnings) == 1  # Warning shown


def test_executor_skips_confirmation_when_auto_confirm():
    """When auto_confirm=True, even unsafe actions skip confirmation."""
    # Arrange
    from scrappy.agent.action_executor import ActionExecutor

    ui = TestAgentUI()
    safety = StrictSafetyChecker()
    duplicate = NoDuplicateDetector()
    runner = MockToolRunner()
    runner.tools["delete_file"] = lambda **kw: "File deleted"

    executor = ActionExecutor(safety, duplicate, runner, ui)

    action = AgentAction(
        thought="Deleting file",
        action="delete_file",
        parameters={"path": "old.txt"},
        is_complete=False
    )
    state = ConversationState(auto_confirm=True)

    # Act
    result = executor.execute(action, state)

    # Assert
    assert result.success is True
    assert result.approved is True
    assert len(ui.confirmations_requested) == 0  # No confirmation


def test_executor_handles_dry_run_mode():
    """In dry-run mode, actions should not execute."""
    # Arrange
    from scrappy.agent.action_executor import ActionExecutor

    ui = TestAgentUI()
    safety = PermissiveSafetyChecker()
    duplicate = NoDuplicateDetector()
    runner = MockToolRunner()
    runner.tools["write_file"] = lambda **kw: "File written"

    executor = ActionExecutor(safety, duplicate, runner, ui)

    action = AgentAction(
        thought="Writing file",
        action="write_file",
        parameters={"path": "test.txt", "content": "data"},
        is_complete=False
    )
    state = ConversationState()

    # Act
    result = executor.execute(action, state, dry_run=True)

    # Assert
    assert result.success is True
    assert result.approved is True
    assert result.executed is False  # Not executed in dry-run
    assert len(runner.calls) == 0  # Tool was not called
    assert "[DRY RUN]" in result.output

