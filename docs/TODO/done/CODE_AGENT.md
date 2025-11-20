# CODE_AGENT Refactoring Plan (Updated)

`src/agent/core.py` is still doing too much. It handles high-level orchestration, UI rendering, shell command heuristics, tool execution, safety checks, and duplicate detection - all in 1,336 lines.

## Current State Analysis

### What's Already in Place ✅

**Dependency Injection Infrastructure:**
- Constructor accepts optional dependencies (lines 77-90)
- Factory methods for default implementations
- Good foundation for protocol-based design

**Existing Protocols in `protocols.py`:**
- `AuditLoggerProtocol` - audit logging abstraction
- `ResponseParserProtocol` - response parsing abstraction
- `PromptBuilderProtocol` - prompt construction abstraction
- `ToolRegistryProtocol` - tool registration abstraction
- `ToolContextProtocol` - tool execution context
- `CheckpointManagerProtocol` - git checkpointing
- `PlatformUtilsProtocol` - platform detection/translation

**Existing Types (`types.py`):**
- `AgentThought` - LLM response wrapper
- `AgentAction` - parsed action representation
- `ActionResult` - execution result
- `EvaluationResult` - task completion evaluation
- `ConversationState` - conversation state tracking

**Existing Adapters:**
- `platform_adapter.py` - concrete implementations of `PlatformUtilsProtocol`
  - `RealPlatformUtils` - real platform detection
  - `MockPlatformUtils` - test double for platform operations

**Existing I/O Protocol:**
- `CLIIOProtocol` in `src/cli/io_interface.py` - already abstracts CLI operations
- `ClickIO` - real implementation
- `TestIO` - test double

**Existing Response Parsers:**
- `JSONResponseParser` - parses JSON responses
- `NativeToolCallParser` - parses native tool calls
- `UnifiedResponseParser` - auto-detects format

### What's Still a Problem ❌

**`core.py` is still a monolith (1,336 lines) with mixed responsibilities:**

1. **UI/Presentation Logic** (lines 346-407):
   - `_show_thinking()`, `_show_tool_request()`, `_show_command()`
   - `_show_error()`, `_show_result()`, `_show_warning()`
   - `_show_progress()`, `_show_provider_status()`, `_show_rule()`

2. **Safety & Validation** (embedded in `_execute` at lines 885-914):
   - User confirmation logic (lines 885-900)
   - Duplicate action detection (lines 903-914)
   - Retry pattern detection (lines 917-924)
   - Failed command tracking (lines 936-981)

3. **Tool Execution** (embedded in `_execute` at line 933):
   - Direct tool calling mixed with safety and UI
   - Special handling for `run_command` (lines 929-932)

4. **Action Coordination** (entire `_execute` method, lines 817-1008):
   - ~190 lines doing everything: parsing errors, safety, confirmation,
     duplicate detection, retry patterns, execution, result display, audit logging

**Missing Protocols:**
- `AgentUIProtocol` - agent-specific UI operations
- `SafetyCheckerProtocol` - action safety validation
- `DuplicateDetectorProtocol` - duplicate/retry detection
- `ToolRunnerProtocol` - tool execution abstraction
- `ActionExecutorProtocol` - action execution coordination

---

## The Updated Plan

**Philosophy: Build on What Exists, Extract What's Mixed**

We already have:
- ✅ Dependency injection framework
- ✅ Many protocols defined
- ✅ CLIIOProtocol for basic I/O
- ✅ PlatformUtilsProtocol and adapters
- ✅ Type definitions

We need to:
1. **Define Missing Protocols** - add agent-specific protocols to `protocols.py`
2. **Extract UI Logic** - create `AgentUI` class that wraps `CLIIOProtocol`
3. **Extract Safety Logic** - create `SafetyChecker` for action validation
4. **Extract Duplicate Detection** - create `DuplicateDetector` for redundancy checking
5. **Extract Tool Execution** - create `ToolRunner` for pure execution
6. **Extract Action Coordination** - create `ActionExecutor` to orchestrate the flow
7. **Simplify Core** - `CodeAgent` becomes thin coordinator of Think-Plan-Execute

### New File Structure

```text
scrappy/src/agent/
├── core.py                # (Modified) Thin Think-Plan-Execute coordinator
├── protocols.py           # (Modified) Add 5 new agent protocols
├── ui.py                  # (New) Agent-specific UI operations
├── safety_checker.py      # (New) Action safety validation
├── duplicate_detector.py  # (New) Duplicate/retry detection
├── tool_runner.py         # (New) Pure tool execution
├── action_executor.py     # (New) Execution coordination
├── types.py               # (Existing) Type definitions
├── audit.py               # (Existing) Audit logging
├── response_parser.py     # (Existing) Response parsing
├── system_prompt_builder.py # (Existing) Prompt building
├── platform_adapter.py    # (Existing) Platform utilities
└── checkpoint.py          # (Existing) Git checkpointing
```

---

## Step 0: Define Missing Protocols (MUST DO FIRST)

Add these protocols to `src/agent/protocols.py` (after existing protocols):

```python
# =============================================================================
# Agent Component Protocols
# =============================================================================

@runtime_checkable
class AgentUIProtocol(Protocol):
    """
    Protocol for agent user interface operations.

    Abstracts agent-specific UI operations (thinking display, tool requests,
    results, errors) from the underlying I/O mechanism (CLIIOProtocol).

    Implementations:
    - AgentUI: Rich-enhanced UI for production
    - TestAgentUI: Minimal UI for testing

    Example:
        def show_action(ui: AgentUIProtocol, action: str, params: dict) -> None:
            ui.show_tool_request(action, params)
            ui.show_progress(f"Executing {action}...")
    """

    def show_thinking(self, text: str) -> None:
        """
        Display agent thinking/reasoning.

        Args:
            text: Thought text to display
        """
        ...

    def show_tool_request(self, tool_name: str, params: Dict[str, Any]) -> None:
        """
        Display tool invocation request.

        Args:
            tool_name: Name of tool being invoked
            params: Tool parameters
        """
        ...

    def show_command(self, command: str) -> None:
        """
        Display shell command being executed.

        Args:
            command: Shell command text
        """
        ...

    def show_error(self, message: str) -> None:
        """
        Display error message.

        Args:
            message: Error message text
        """
        ...

    def show_result(
        self,
        result: str,
        title: str = "Result",
        is_error: bool = False
    ) -> None:
        """
        Display action result.

        Args:
            result: Result text/output
            title: Display title
            is_error: Whether result represents an error
        """
        ...

    def show_warning(self, message: str) -> None:
        """
        Display warning message.

        Args:
            message: Warning message text
        """
        ...

    def show_progress(self, message: str) -> None:
        """
        Display progress/status message.

        Args:
            message: Progress message text
        """
        ...

    def show_provider_status(
        self,
        provider: str,
        message: str,
        color: str = "cyan"
    ) -> None:
        """
        Display provider-specific status.

        Args:
            provider: Provider name (e.g., "OpenAI", "Gemini")
            message: Status message
            color: Display color
        """
        ...

    def show_rule(self, title: Optional[str] = None) -> None:
        """
        Display horizontal rule separator.

        Args:
            title: Optional title for rule
        """
        ...

    def prompt_confirm(
        self,
        message: str = "Allow?",
        default: bool = False
    ) -> bool:
        """
        Prompt user for confirmation.

        Args:
            message: Confirmation prompt text
            default: Default value if user presses enter

        Returns:
            True if user confirmed, False otherwise
        """
        ...


@runtime_checkable
class SafetyCheckerProtocol(Protocol):
    """
    Protocol for action safety validation.

    Abstracts safety checking to enable testing with controlled
    safety policies and support different safety strategies.

    Implementations:
    - SafetyChecker: Default safety rules (read-only operations safe)
    - PermissiveSafetyChecker: All operations safe (for testing)
    - StrictSafetyChecker: No operations safe (for testing)

    Example:
        def should_confirm(checker: SafetyCheckerProtocol, action: AgentAction) -> bool:
            if checker.is_safe_action(action):
                return False  # No confirmation needed
            return checker.requires_confirmation(action, auto_confirm=False)
    """

    def is_safe_action(self, action: Any) -> bool:
        """
        Check if action is safe to auto-execute.

        Safe actions are typically read-only operations like reading files,
        listing directories, or viewing git status.

        Args:
            action: AgentAction to check

        Returns:
            True if action is safe, False otherwise
        """
        ...

    def requires_confirmation(self, action: Any, auto_confirm: bool) -> bool:
        """
        Check if action requires user confirmation.

        Takes into account both action safety and auto_confirm flag.

        Args:
            action: AgentAction to check
            auto_confirm: Whether auto-confirm mode is enabled

        Returns:
            True if confirmation required, False otherwise
        """
        ...


@runtime_checkable
class DuplicateDetectorProtocol(Protocol):
    """
    Protocol for detecting duplicate or redundant actions.

    Abstracts duplicate detection to enable testing with controlled
    detection logic and support different retry strategies.

    Implementations:
    - DuplicateDetector: Full duplicate/retry detection with state tracking
    - NoDuplicateDetector: Never detects duplicates (for testing)
    - StrictDuplicateDetector: Detects all repeats (for testing)

    Example:
        def check_action(detector: DuplicateDetectorProtocol, action, state) -> bool:
            is_dup, warning = detector.check_duplicate(action, state)
            if is_dup:
                logger.warning(warning)
                return False  # Don't execute
            return True
    """

    def check_duplicate(
        self,
        action: Any,
        state: Any
    ) -> tuple[bool, str]:
        """
        Check if action is duplicate or should be blocked.

        Checks for:
        - Exact action duplicates in recent history
        - Repeated failed commands (retry loops)
        - Failed approach patterns (same strategy failing repeatedly)

        Args:
            action: AgentAction to check
            state: ConversationState with action history

        Returns:
            Tuple of (is_duplicate, warning_message).
            If is_duplicate is True, warning_message explains why.
        """
        ...


@runtime_checkable
class ToolRunnerProtocol(Protocol):
    """
    Protocol for executing tool operations.

    Abstracts tool execution to enable testing with mock tools
    and support different execution strategies.

    Implementations:
    - ToolRunner: Full tool execution with registry integration
    - MockToolRunner: Returns preset results for testing
    - LoggingToolRunner: Logs all tool calls (for debugging)

    Example:
        def run_action(runner: ToolRunnerProtocol, action: AgentAction) -> str:
            result = runner.run_tool(action.action, action.parameters)
            return result
    """

    def run_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """
        Execute a tool and return its output.

        Args:
            tool_name: Name of tool to execute
            parameters: Tool-specific parameters

        Returns:
            Tool output as string

        Raises:
            ValueError: If tool not found
            Exception: If tool execution fails
        """
        ...


@runtime_checkable
class ActionExecutorProtocol(Protocol):
    """
    Protocol for coordinating action execution flow.

    Abstracts execution coordination to enable testing with controlled
    execution flow and support different execution strategies.

    Implementations:
    - ActionExecutor: Full coordination (safety → duplicate → execution)
    - DryRunExecutor: Simulates execution without running tools
    - LoggingExecutor: Logs all steps without execution

    Example:
        def execute_action(
            executor: ActionExecutorProtocol,
            action: AgentAction,
            state: ConversationState
        ) -> ActionResult:
            return executor.execute(action, state, dry_run=False)
    """

    def execute(
        self,
        action: Any,
        state: Any,
        dry_run: bool = False
    ) -> Any:
        """
        Orchestrate action execution flow.

        Flow:
        1. Check safety and get user confirmation if needed
        2. Check for duplicate/retry patterns
        3. Execute tool if approved and not duplicate
        4. Return ActionResult with execution details

        Args:
            action: AgentAction to execute
            state: ConversationState with history
            dry_run: If True, simulate execution without running tools

        Returns:
            ActionResult with execution details
        """
        ...
```

**Why these protocols?**

1. **Testability**: Each component testable in isolation with test doubles
2. **Separation of Concerns**: Each protocol represents ONE responsibility
3. **Dependency Inversion**: Core depends on abstractions, not concretions
4. **Flexibility**: Swap implementations (e.g., RichUI vs SimpleUI)

---

## Step 1: Write Tests for New Protocols

**Create `tests/agent/test_agent_components.py`:**

```python
"""
Tests for extracted agent components.
Uses test doubles to verify behavior without concrete dependencies.
"""
import pytest
from src.agent.types import AgentAction, ActionResult, ConversationState


# =============================================================================
# Test Doubles
# =============================================================================

class TestAgentUI:
    """Test double for AgentUIProtocol."""

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

    def show_provider_status(self, provider: str, message: str, color: str = "cyan") -> None:
        pass

    def show_rule(self, title: str = None) -> None:
        pass

    def prompt_confirm(self, message: str = "Allow?", default: bool = False) -> bool:
        self.confirmations_requested.append(message)
        if self.confirmation_responses:
            return self.confirmation_responses.pop(0)
        return default


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

    def __init__(self, default_result: str = "Success"):
        self.default_result = default_result
        self.calls = []
        self.results = {}

    def set_result(self, tool_name: str, result: str) -> None:
        """Configure result for specific tool."""
        self.results[tool_name] = result

    def run_tool(self, tool_name: str, parameters: dict) -> str:
        self.calls.append((tool_name, parameters))
        return self.results.get(tool_name, self.default_result)


# =============================================================================
# ActionExecutor Tests (Integration of Components)
# =============================================================================

def test_executor_runs_safe_action_without_confirmation():
    """Safe actions should execute without user confirmation."""
    # Arrange
    from src.agent.action_executor import ActionExecutor

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
    from src.agent.action_executor import ActionExecutor

    ui = TestAgentUI()
    ui.confirmation_responses = [True]  # User approves
    safety = StrictSafetyChecker()
    duplicate = NoDuplicateDetector()
    runner = MockToolRunner(default_result="File written")

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
    from src.agent.action_executor import ActionExecutor

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
    from src.agent.action_executor import ActionExecutor

    ui = TestAgentUI()
    safety = StrictSafetyChecker()
    duplicate = NoDuplicateDetector()
    runner = MockToolRunner()

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
    from src.agent.action_executor import ActionExecutor

    ui = TestAgentUI()
    safety = PermissiveSafetyChecker()
    duplicate = NoDuplicateDetector()
    runner = MockToolRunner()

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


# =============================================================================
# SafetyChecker Tests
# =============================================================================

def test_safety_checker_marks_read_operations_as_safe():
    """Read-only operations should be marked safe."""
    from src.agent.safety_checker import SafetyChecker

    checker = SafetyChecker()

    safe_actions = [
        AgentAction("", "read_file", {"path": "test.py"}, False),
        AgentAction("", "list_files", {"directory": "."}, False),
        AgentAction("", "search_code", {"pattern": "def"}, False),
        AgentAction("", "git_status", {}, False),
        AgentAction("", "git_diff", {}, False),
    ]

    for action in safe_actions:
        assert checker.is_safe_action(action) is True


def test_safety_checker_marks_write_operations_as_unsafe():
    """Write/modification operations should be marked unsafe."""
    from src.agent.safety_checker import SafetyChecker

    checker = SafetyChecker()

    unsafe_actions = [
        AgentAction("", "write_file", {"path": "test.py"}, False),
        AgentAction("", "delete_file", {"path": "old.py"}, False),
        AgentAction("", "run_command", {"command": "npm install"}, False),
    ]

    for action in unsafe_actions:
        assert checker.is_safe_action(action) is False


# =============================================================================
# DuplicateDetector Tests
# =============================================================================

def test_duplicate_detector_finds_exact_duplicates():
    """Should detect exact action duplicates in recent history."""
    from src.agent.duplicate_detector import DuplicateDetector

    detector = DuplicateDetector()

    action = AgentAction("", "read_file", {"path": "test.py"}, False)

    # Empty history - not a duplicate
    state = ConversationState(action_history=[])
    is_dup, msg = detector.check_duplicate(action, state)
    assert is_dup is False

    # Same action in recent history - is duplicate
    state.action_history = [
        {"action": "read_file", "parameters": {"path": "test.py"}}
    ]
    is_dup, msg = detector.check_duplicate(action, state)
    assert is_dup is True
    assert "already attempted" in msg.lower()


def test_duplicate_detector_tracks_command_failures():
    """Should block commands that have failed multiple times."""
    from src.agent.duplicate_detector import DuplicateDetector

    detector = DuplicateDetector()

    action = AgentAction("", "run_command", {"command": "npm test"}, False)

    # First failure - allow
    state = ConversationState(
        failed_commands=[
            {"command": "npm test", "error": "Exit 1", "approach": "npm_test"}
        ]
    )
    is_dup, msg = detector.check_duplicate(action, state)
    assert is_dup is False

    # Third failure - block
    state.failed_commands = [
        {"command": "npm test", "error": "Exit 1", "approach": "npm_test"},
        {"command": "npm test", "error": "Exit 1", "approach": "npm_test"},
        {"command": "npm test", "error": "Exit 1", "approach": "npm_test"},
    ]
    is_dup, msg = detector.check_duplicate(action, state)
    assert is_dup is True
    assert "failed" in msg.lower()


# Move additional component tests to separate files as needed
```

---

## Step 2: Create `src/agent/ui.py`

Extract all UI logic from `core.py`:

```python
"""
Agent UI implementation.

Handles all user interaction and console output formatting for the agent.
Wraps CLIIOProtocol to provide agent-specific display operations.
"""

from typing import Optional, Dict, Any
import json

from ..cli.io_interface import CLIIOProtocol
from .protocols import AgentUIProtocol


def safe_print(*args, **kwargs):
    """Safely handles Unicode encoding errors on Windows."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = ' '.join(str(arg) for arg in args)
        safe_text = text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        try:
            print(safe_text, **kwargs)
        except Exception:
            ascii_text = ''.join(c if ord(c) < 128 else '?' for c in text)
            print(ascii_text, **kwargs)
    except Exception:
        pass


class AgentUI:
    """
    Agent user interface implementation.

    Implements AgentUIProtocol by wrapping CLIIOProtocol and adding
    agent-specific formatting and Rich enhancements.

    Single Responsibility: Agent-specific UI operations
    Dependencies: CLIIOProtocol (injected)
    """

    def __init__(self, io: CLIIOProtocol):
        """
        Initialize agent UI.

        Args:
            io: CLI I/O interface (CLIIOProtocol)
        """
        self.io = io

    def show_thinking(self, text: str) -> None:
        """Display agent thinking/reasoning."""
        if not text or not text.strip():
            return

        # Use Rich panel if available
        if hasattr(self.io, 'panel'):
            self.io.panel(text, title="Thinking", border_style="blue")
        else:
            self.io.secho(f"\n[Thinking] {text}", fg="blue")

    def show_tool_request(self, tool_name: str, params: Dict[str, Any]) -> None:
        """Display tool invocation request."""
        # Use Rich table if available
        if hasattr(self.io, 'table'):
            headers = ["Property", "Value"]
            rows = [["Tool", tool_name]]
            for key, value in params.items():
                str_value = str(value)
                if len(str_value) > 100:
                    str_value = str_value[:100] + "..."
                rows.append([key, str_value])
            self.io.table(headers, rows, title="Tool Request")
        else:
            self.io.secho(f"\nTool: {tool_name}", fg="cyan", bold=True)
            self.io.echo(f"Parameters: {json.dumps(params, indent=2)}")

    def show_command(self, command: str) -> None:
        """Display shell command being executed."""
        # Use Rich syntax highlighting if available
        if hasattr(self.io, 'syntax'):
            self.io.syntax(command, language="shell")
        else:
            self.io.secho(f"$ {command}", fg="yellow")

    def show_error(self, message: str) -> None:
        """Display error message."""
        if hasattr(self.io, 'panel'):
            self.io.panel(message, title="Error", border_style="red")
        else:
            self.io.secho(f"\nError: {message}", fg="red")

    def show_result(
        self,
        result: str,
        title: str = "Result",
        is_error: bool = False
    ) -> None:
        """Display action result."""
        # Truncate very long output for display
        display_result = result[:2000] + "... [truncated]" if len(result) > 2000 else result

        color = "red" if is_error else "green"

        if hasattr(self.io, 'panel'):
            self.io.panel(display_result, title=title, border_style=color)
        else:
            self.io.secho(f"\n{title}: {display_result}", fg=color)

    def show_warning(self, message: str) -> None:
        """Display warning message."""
        if hasattr(self.io, 'panel'):
            self.io.panel(message, title="Warning", border_style="yellow")
        else:
            self.io.secho(f"\nWarning: {message}", fg="yellow")

    def show_progress(self, message: str) -> None:
        """Display progress/status message."""
        self.io.secho(message, fg="cyan")

    def show_provider_status(
        self,
        provider: str,
        message: str,
        color: str = "cyan"
    ) -> None:
        """Display provider-specific status."""
        self.io.secho(f"[{provider}] {message}", fg=color)

    def show_rule(self, title: Optional[str] = None) -> None:
        """Display horizontal rule separator."""
        if hasattr(self.io, 'rule'):
            self.io.rule(title)
        else:
            self.io.echo(f"\n{'='*60}")
            if title:
                self.io.echo(f" {title} ")

    def prompt_confirm(
        self,
        message: str = "Allow?",
        default: bool = False
    ) -> bool:
        """Prompt user for confirmation."""
        return self.io.confirm(message, default=default)
```

---

## Step 3: Create `src/agent/safety_checker.py`

Extract safety logic from `core.py`:

```python
"""
Safety checker for agent actions.

Determines which actions are safe to auto-execute vs require user confirmation.
"""

from typing import Set

from .types import AgentAction
from .protocols import SafetyCheckerProtocol


class SafetyChecker:
    """
    Action safety validator.

    Implements SafetyCheckerProtocol with default safety rules.

    Single Responsibility: Determine action safety
    Dependencies: None (pure logic)
    """

    # Actions that are read-only and safe to execute without confirmation
    SAFE_ACTIONS: Set[str] = {
        'read_file',
        'list_files',
        'list_directory',
        'search_code',
        'git_status',
        'git_diff',
        'get_context',
    }

    def is_safe_action(self, action: AgentAction) -> bool:
        """
        Check if action is safe to auto-execute.

        Safe actions are read-only operations that cannot modify state.

        Args:
            action: AgentAction to check

        Returns:
            True if action is safe, False otherwise
        """
        return action.action in self.SAFE_ACTIONS

    def requires_confirmation(self, action: AgentAction, auto_confirm: bool) -> bool:
        """
        Check if action requires user confirmation.

        Args:
            action: AgentAction to check
            auto_confirm: Whether auto-confirm mode is enabled

        Returns:
            True if confirmation required, False otherwise
        """
        # Auto-confirm mode disables all confirmations
        if auto_confirm:
            return False

        # 'complete' action never requires confirmation
        if action.action == 'complete':
            return False

        # Unsafe actions require confirmation
        return not self.is_safe_action(action)
```

---

## Step 4: Create `src/agent/duplicate_detector.py`

Extract duplicate detection logic:

```python
"""
Duplicate action detector.

Prevents the agent from repeating failed or redundant operations.
"""

from typing import Dict, List

from .types import AgentAction, ConversationState
from .protocols import DuplicateDetectorProtocol


class DuplicateDetector:
    """
    Duplicate and retry pattern detector.

    Implements DuplicateDetectorProtocol with state-aware detection.

    Single Responsibility: Detect duplicate/redundant actions
    Dependencies: None (pure logic)
    """

    LOOKBACK_WINDOW = 3  # Check last N actions for duplicates
    MAX_COMMAND_FAILURES = 3  # Block command after N failures

    def check_duplicate(
        self,
        action: AgentAction,
        state: ConversationState
    ) -> tuple[bool, str]:
        """
        Check if action is duplicate or should be blocked.

        Args:
            action: AgentAction to check
            state: ConversationState with action history

        Returns:
            Tuple of (is_duplicate, warning_message).
            If is_duplicate is True, warning_message explains why.
        """
        # Check if this exact action was recently executed
        if self._is_recent_duplicate(action, state):
            return (
                True,
                f"Action '{action.action}' with these parameters was already attempted recently."
            )

        # Check if command has failed multiple times
        if action.action == 'run_command':
            failure_count = self._count_command_failures(action, state)
            if failure_count >= self.MAX_COMMAND_FAILURES:
                return (
                    True,
                    f"Command has failed {failure_count} times. Stopping to avoid infinite loop."
                )

        return (False, "")

    def _is_recent_duplicate(
        self,
        action: AgentAction,
        state: ConversationState
    ) -> bool:
        """Check if action was executed in last N iterations."""
        if not hasattr(state, 'action_history'):
            return False

        recent_actions = state.action_history[-self.LOOKBACK_WINDOW:]

        for recent in recent_actions:
            # Compare action name and parameters
            if isinstance(recent, dict):
                if (recent.get('action') == action.action and
                    recent.get('parameters') == action.parameters):
                    return True
            elif hasattr(recent, 'action'):
                if (recent.action == action.action and
                    recent.parameters == action.parameters):
                    return True

        return False

    def _count_command_failures(
        self,
        action: AgentAction,
        state: ConversationState
    ) -> int:
        """Count how many times this specific command has failed."""
        if not hasattr(state, 'failed_commands'):
            return 0

        command = action.parameters.get('command', '')
        if not command:
            return 0

        # Count exact command matches in failed_commands
        count = 0
        for failure in state.failed_commands:
            if isinstance(failure, dict) and failure.get('command') == command:
                count += 1

        return count
```

---

## Step 5: Create `src/agent/tool_runner.py`

Extract tool execution logic:

```python
"""
Tool runner implementation.

Pure execution logic for running tools from the registry.
"""

from typing import Dict, Any, Callable

from ..agent_tools.tools import ToolRegistry, ToolContext
from ..agent_tools.tools.command_tool import ShellCommandExecutor
from .protocols import ToolRunnerProtocol


class ToolRunner:
    """
    Tool execution coordinator.

    Implements ToolRunnerProtocol with registry integration.

    Single Responsibility: Execute tools
    Dependencies: ToolRegistry, ShellCommandExecutor, ToolContext (injected)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        command_executor: ShellCommandExecutor,
        tool_context: ToolContext,
    ):
        """
        Initialize tool runner.

        Args:
            tool_registry: Registry of available tools
            command_executor: Executor for shell commands
            tool_context: Context for tool execution
        """
        self.tool_registry = tool_registry
        self.command_executor = command_executor
        self.tool_context = tool_context

        # Build tool mapping from registry
        self.tools: Dict[str, Callable] = {}
        for tool in self.tool_registry.list_all():
            # Create closure that captures tool instance and context
            def make_tool_wrapper(t):
                return lambda **kwargs: t.execute(self.tool_context, **kwargs)
            self.tools[tool.name] = make_tool_wrapper(tool)

        # Special handling for run_command
        self.tools['run_command'] = self._run_command_tool

    def run_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """
        Execute a tool and return its output.

        Args:
            tool_name: Name of tool to execute
            parameters: Tool-specific parameters

        Returns:
            Tool output as string

        Raises:
            ValueError: If tool not found
        """
        if tool_name not in self.tools:
            available = ', '.join(self.tools.keys())
            raise ValueError(
                f"Unknown tool: {tool_name}. Available tools: {available}"
            )

        try:
            result = self.tools[tool_name](**parameters)
            return str(result)
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def _run_command_tool(self, command: str, **kwargs) -> str:
        """
        Special handler for run_command with interactive CLI detection.

        Args:
            command: Shell command to execute

        Returns:
            Command output
        """
        # Check for interactive CLIs that need special handling
        interactive_patterns = ['npx', 'npm create', 'yarn create']
        needs_interaction = any(pattern in command for pattern in interactive_patterns)

        if needs_interaction:
            # Add --yes or equivalent flags
            if 'npx' in command and '--yes' not in command:
                command = command.replace('npx', 'npx --yes')

        # Delegate to command executor
        return self.command_executor.run(
            command,
            cwd=str(self.tool_context.get_project_root())
        )
```

---

## Step 6: Create `src/agent/action_executor.py`

Extract action execution coordination:

```python
"""
Action executor coordinator.

Orchestrates the flow: Safety check -> Duplicate check -> Tool execution -> Result.
"""

from typing import Optional

from .types import AgentAction, ActionResult, ConversationState
from .protocols import (
    ActionExecutorProtocol,
    SafetyCheckerProtocol,
    DuplicateDetectorProtocol,
    ToolRunnerProtocol,
    AgentUIProtocol,
)


class ActionExecutor:
    """
    Action execution coordinator.

    Implements ActionExecutorProtocol with full execution flow.

    Single Responsibility: Coordinate execution flow
    Dependencies: SafetyChecker, DuplicateDetector, ToolRunner, AgentUI (injected)
    """

    def __init__(
        self,
        safety_checker: SafetyCheckerProtocol,
        duplicate_detector: DuplicateDetectorProtocol,
        tool_runner: ToolRunnerProtocol,
        ui: AgentUIProtocol,
    ):
        """
        Initialize action executor.

        Args:
            safety_checker: Safety validation component
            duplicate_detector: Duplicate detection component
            tool_runner: Tool execution component
            ui: User interface component
        """
        self.safety = safety_checker
        self.duplicate_detector = duplicate_detector
        self.tool_runner = tool_runner
        self.ui = ui

    def execute(
        self,
        action: AgentAction,
        state: ConversationState,
        dry_run: bool = False
    ) -> ActionResult:
        """
        Orchestrate action execution flow.

        Flow:
        1. Display thinking
        2. Handle special cases (complete, retry_parse, unknown)
        3. Check safety and get confirmation if needed
        4. Check for duplicates/retry patterns
        5. Execute tool (unless dry-run)
        6. Display and return result

        Args:
            action: AgentAction to execute
            state: ConversationState with history
            dry_run: If True, simulate execution without running tools

        Returns:
            ActionResult with execution details
        """
        # Display thinking
        self.ui.show_thinking(action.thought)

        # Handle parse failure
        if action.action == 'retry_parse':
            return self._handle_parse_failure(action)

        # Handle 'complete' action
        if action.action == 'complete':
            return ActionResult(
                success=True,
                output=action.result_text or "Task completed",
                action='complete',
                parameters=action.parameters,
                approved=True,
                executed=True
            )

        # Handle unknown tool
        if action.action not in self.tool_runner.tools:
            return self._handle_unknown_tool(action)

        # 1. Safety & Confirmation
        if not self._check_safety_and_get_approval(action, state):
            return ActionResult(
                success=False,
                output="Action denied by user",
                action=action.action,
                parameters=action.parameters,
                approved=False,
                executed=False
            )

        # 2. Duplicate Detection
        is_duplicate, warning = self.duplicate_detector.check_duplicate(action, state)
        if is_duplicate:
            self.ui.show_warning(warning)
            return ActionResult(
                success=False,
                output=warning,
                action=action.action,
                parameters=action.parameters,
                approved=True,
                executed=False
            )

        # 3. Dry Run Check
        if dry_run:
            self.ui.show_progress(f"[DRY RUN] Would execute: {action.action}")
            return ActionResult(
                success=True,
                output="[DRY RUN] Not executed",
                action=action.action,
                parameters=action.parameters,
                approved=True,
                executed=False
            )

        # 4. Execution
        self.ui.show_progress(f"Executing: {action.action}")

        # Show command for run_command
        if action.action == 'run_command':
            cmd = action.parameters.get('command', '')
            if cmd:
                self.ui.show_command(cmd)

        try:
            output = self.tool_runner.run_tool(action.action, action.parameters)
            is_error = 'error' in output.lower() or 'failed' in output.lower()

            self.ui.show_result(output, is_error=is_error)

            return ActionResult(
                success=not is_error,
                output=output,
                action=action.action,
                parameters=action.parameters,
                approved=True,
                executed=True
            )

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.ui.show_error(error_msg)
            return ActionResult(
                success=False,
                output=error_msg,
                action=action.action,
                parameters=action.parameters,
                approved=True,
                executed=True
            )

    def _check_safety_and_get_approval(
        self,
        action: AgentAction,
        state: ConversationState
    ) -> bool:
        """
        Check safety and get user approval if needed.

        Returns:
            True if action is approved for execution, False otherwise
        """
        # Safe actions are auto-approved
        if self.safety.is_safe_action(action):
            self.ui.show_tool_request(action.action, action.parameters)
            self.ui.show_progress("Auto-approved (safe operation)")
            return True

        # Check if confirmation required
        if not self.safety.requires_confirmation(action, state.auto_confirm):
            return True

        # Ask user
        self.ui.show_tool_request(action.action, action.parameters)
        return self.ui.prompt_confirm("Allow this action?", default=False)

    def _handle_parse_failure(self, action: AgentAction) -> ActionResult:
        """Handle response parsing failure."""
        raw_response = action.parameters.get('raw_response', 'No response captured')
        self.ui.show_error(f"Response parsing failed. LLM returned:\n{raw_response[:300]}...")

        error_msg = (
            "Your previous response could not be parsed as JSON. "
            "You MUST respond with ONLY a valid JSON object (no other text). "
            "Use this exact format:\n"
            '{\n'
            '  "thought": "Your reasoning here",\n'
            '  "action": "tool_name",\n'
            '  "parameters": {"param": "value"},\n'
            '  "is_complete": false\n'
            '}\n'
            "Make sure all strings are properly quoted with double quotes."
        )

        return ActionResult(
            success=False,
            output=error_msg,
            action=action.action,
            parameters=action.parameters,
            approved=False,
            executed=False
        )

    def _handle_unknown_tool(self, action: AgentAction) -> ActionResult:
        """Handle unknown tool name."""
        available_tools = ', '.join(self.tool_runner.tools.keys())
        error_msg = f"Unknown action '{action.action}'. Available tools: {available_tools}"

        self.ui.show_error(error_msg)

        return ActionResult(
            success=False,
            output=error_msg,
            action=action.action,
            parameters=action.parameters,
            approved=False,
            executed=False
        )
```

---

## Step 7: Refactor `src/agent/core.py`

Simplify to thin coordinator using extracted components:

**Key changes:**
1. Remove all `_show_*` methods (lines 346-407) - replaced by `AgentUI`
2. Remove `_check_duplicate_action` (lines 534-584) - replaced by `DuplicateDetector`
3. Remove `_check_retry_pattern` (lines 519-532) - moved to `DuplicateDetector`
4. Remove `_categorize_command_approach` (lines 504-517) - moved to `DuplicateDetector`
5. Simplify `_execute` (lines 817-1008) - replaced by `ActionExecutor.execute()`
6. Update `__init__` to create/inject new components

**Simplified `core.py` structure:**

```python
"""
Core Code Agent implementation.

Thin coordinator for the Think-Plan-Execute loop.
"""

import json
from pathlib import Path
from typing import Optional, Union, Any

from ..agent_config import AgentConfig
from ..agent_tools.tools import ToolRegistry, ToolContext
from ..agent_tools.tools.command_tool import ShellCommandExecutor
from ..orchestrator_adapter import OrchestratorAdapter, AgentOrchestratorAdapter
from ..cli.io_interface import CLIIOProtocol, ClickIO

from .types import AgentThought, AgentAction, ActionResult, EvaluationResult, ConversationState
from .audit import AuditLogger
from .response_parser import UnifiedResponseParser
from .system_prompt_builder import SystemPromptBuilder
from .platform_adapter import RealPlatformUtils

# Import new components
from .ui import AgentUI
from .safety_checker import SafetyChecker
from .duplicate_detector import DuplicateDetector
from .tool_runner import ToolRunner
from .action_executor import ActionExecutor

# Import protocols
from .protocols import (
    AgentUIProtocol,
    SafetyCheckerProtocol,
    DuplicateDetectorProtocol,
    ToolRunnerProtocol,
    ActionExecutorProtocol,
    AuditLoggerProtocol,
    ResponseParserProtocol,
    PlatformUtilsProtocol,
)


class CodeAgent:
    """
    AI-powered code agent with tool use and safety features.

    Single Responsibility: Coordinate Think-Plan-Execute loop
    Dependencies: All injected via constructor

    Key features:
    - Human-in-the-loop confirmation for unsafe operations
    - Duplicate/retry detection
    - Audit logging of all actions
    - Multi-provider orchestration
    - Injectable component system
    """

    def __init__(
        self,
        orchestrator: Union[OrchestratorAdapter, object],
        project_path: Optional[str] = None,
        config: Optional[AgentConfig] = None,
        # Core dependencies
        io: Optional[CLIIOProtocol] = None,
        ui: Optional[AgentUIProtocol] = None,
        tool_registry: Optional[ToolRegistry] = None,
        tool_context: Optional[ToolContext] = None,
        # Component dependencies
        safety_checker: Optional[SafetyCheckerProtocol] = None,
        duplicate_detector: Optional[DuplicateDetectorProtocol] = None,
        tool_runner: Optional[ToolRunnerProtocol] = None,
        action_executor: Optional[ActionExecutorProtocol] = None,
        # Infrastructure dependencies
        command_executor: Optional[ShellCommandExecutor] = None,
        platform_utils: Optional[PlatformUtilsProtocol] = None,
        audit_logger: Optional[AuditLoggerProtocol] = None,
        response_parser: Optional[ResponseParserProtocol] = None,
    ):
        """
        Initialize the code agent with dependency injection.

        Args:
            orchestrator: OrchestratorAdapter or AgentOrchestrator
            project_path: Root directory for operations (default: cwd)
            config: Agent configuration (uses defaults if not provided)
            io: CLI I/O interface
            ui: Agent UI component
            tool_registry: Tool registry
            tool_context: Tool execution context
            safety_checker: Safety validation component
            duplicate_detector: Duplicate detection component
            tool_runner: Tool execution component
            action_executor: Action execution coordinator
            command_executor: Shell command executor
            platform_utils: Platform utilities
            audit_logger: Audit logger
            response_parser: Response parser
        """
        self.config = config or AgentConfig()
        self.project_root = str(Path(project_path or ".").resolve())

        # Setup orchestrator
        if isinstance(orchestrator, OrchestratorAdapter):
            self.adapter = orchestrator
        else:
            self.adapter = AgentOrchestratorAdapter(orchestrator)

        # Setup I/O (lowest level)
        self.io = io or self._create_default_io()

        # Setup infrastructure
        self.platform_utils = platform_utils or self._create_default_platform_utils()
        self._command_executor = command_executor or self._create_default_command_executor()
        self._audit_logger = audit_logger or self._create_default_audit_logger()
        self._response_parser = response_parser or self._create_default_response_parser()

        # Setup tool infrastructure
        self.tool_context = tool_context or self._create_default_tool_context()
        self.tool_registry = tool_registry or self._create_default_tool_registry()

        # Setup UI (wraps io)
        self.ui = ui or AgentUI(self.io)

        # Setup execution components (in dependency order)
        self._safety_checker = safety_checker or SafetyChecker()
        self._duplicate_detector = duplicate_detector or DuplicateDetector()
        self._tool_runner = tool_runner or ToolRunner(
            tool_registry=self.tool_registry,
            command_executor=self._command_executor,
            tool_context=self.tool_context,
        )
        self.executor = action_executor or ActionExecutor(
            safety_checker=self._safety_checker,
            duplicate_detector=self._duplicate_detector,
            tool_runner=self._tool_runner,
            ui=self.ui,
        )

    # Factory methods (unchanged, just cleaned up)
    def _create_default_io(self) -> CLIIOProtocol:
        """Create default I/O interface (ClickIO)."""
        return ClickIO()

    def _create_default_platform_utils(self) -> PlatformUtilsProtocol:
        """Create default platform utilities."""
        return RealPlatformUtils()

    def _create_default_command_executor(self) -> ShellCommandExecutor:
        """Create default command executor."""
        return ShellCommandExecutor()

    def _create_default_audit_logger(self) -> AuditLoggerProtocol:
        """Create default audit logger."""
        return AuditLogger()

    def _create_default_response_parser(self) -> ResponseParserProtocol:
        """Create default response parser."""
        return UnifiedResponseParser()

    def _create_default_tool_context(self) -> ToolContext:
        """Create default tool context."""
        return ToolContext(
            orchestrator=self.adapter,
            project_root=Path(self.project_root),
            config=self.config.to_dict(),
        )

    def _create_default_tool_registry(self) -> ToolRegistry:
        """Create default tool registry."""
        from ..agent_tools.registry_factory import create_default_registry
        return create_default_registry()

    @property
    def audit_log(self):
        """Accessor for audit log (backward compatibility)."""
        return self._audit_logger.get_history()

    def run(
        self,
        task: str,
        max_iterations: int = 10,
        auto_confirm: bool = False
    ) -> dict:
        """
        Run the agent on a task.

        Coordinates Think -> Plan -> Execute -> Evaluate loop.

        Args:
            task: Task description
            max_iterations: Maximum iterations
            auto_confirm: Skip confirmations if True

        Returns:
            Result dictionary with success status and details
        """
        self.ui.show_rule("Agent Task")
        self.ui.show_progress("Building context...")

        # Build initial prompt
        prompt_builder = SystemPromptBuilder(
            orchestrator=self.adapter,
            tool_registry=self.tool_registry,
            platform_utils=self.platform_utils,
        )
        system_prompt = prompt_builder.build(task=task)

        # Initialize conversation state
        state = ConversationState(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': task}
            ],
            system_prompt=system_prompt,
            max_iterations=max_iterations,
            auto_confirm=auto_confirm,
            iteration=0,
            action_history=[],
            failed_commands=[],
            retry_warnings=[],
        )

        try:
            while state.iteration < state.max_iterations:
                state.iteration += 1

                # 1. Think (call LLM)
                thought = self._think(state)

                # 2. Plan (parse response into action)
                action = self._plan_action(thought)

                # 3. Execute (delegated to ActionExecutor)
                result = self.executor.execute(
                    action,
                    state,
                    dry_run=self.config.dry_run
                )

                # 4. Evaluate (check if complete)
                evaluation = self._evaluate(action, result, state)

                # 5. Update State (add to conversation history)
                self._update_conversation(state, thought, action, result)

                # Check for completion
                if evaluation.is_complete:
                    return self._finish(True, evaluation.final_result, state)

                if not evaluation.should_continue:
                    return self._finish(False, evaluation.reason, state)

            return self._finish(False, f"Max iterations ({max_iterations}) reached", state)

        except KeyboardInterrupt:
            self.ui.show_warning("Agent interrupted by user.")
            return self._finish(False, "Interrupted", state)

    def _think(self, state: ConversationState) -> AgentThought:
        """Call LLM to get next thought/action."""
        self.ui.show_provider_status(
            self.adapter.current_provider,
            "Thinking...",
            color="cyan"
        )

        response = self.adapter.delegate(
            messages=state.messages,
            tools=self.tool_registry.to_openai_format(),
        )

        return AgentThought(
            raw_response=response.get('content', ''),
            provider=self.adapter.current_provider,
            iteration=state.iteration,
            llm_response=response.get('llm_response'),
        )

    def _plan_action(self, thought: AgentThought) -> AgentAction:
        """Parse thought into concrete action."""
        parse_result = self._response_parser.parse(thought.raw_response)

        # Extract action from parse result
        if parse_result.actions:
            first_action = parse_result.actions[0]
            return AgentAction(
                thought=parse_result.thoughts[0] if parse_result.thoughts else "",
                action=first_action.get('action', 'error'),
                parameters=first_action.get('parameters', {}),
                is_complete=first_action.get('is_complete', False),
                result_text=first_action.get('result', ''),
            )

        # Parse failure
        return AgentAction(
            thought="Parse failure",
            action='retry_parse',
            parameters={'raw_response': thought.raw_response},
            is_complete=False,
        )

    def _evaluate(
        self,
        action: AgentAction,
        result: ActionResult,
        state: ConversationState
    ) -> EvaluationResult:
        """Evaluate if task is complete or should continue."""
        if action.action == 'complete' or action.is_complete:
            return EvaluationResult(
                is_complete=True,
                should_continue=False,
                reason="Task marked complete",
                final_result=result.output,
            )

        if not result.success and not result.approved:
            return EvaluationResult(
                is_complete=False,
                should_continue=False,
                reason="Action denied by user",
            )

        return EvaluationResult(
            is_complete=False,
            should_continue=True,
            reason="",
        )

    def _update_conversation(
        self,
        state: ConversationState,
        thought: AgentThought,
        action: AgentAction,
        result: ActionResult
    ) -> None:
        """Update conversation history with latest interaction."""
        # Add assistant message
        state.messages.append({
            'role': 'assistant',
            'content': thought.raw_response,
        })

        # Add tool result
        state.messages.append({
            'role': 'user',
            'content': f"Tool Result: {result.output}",
        })

        # Track action history for duplicate detection
        state.action_history.append({
            'action': action.action,
            'parameters': action.parameters,
        })

        # Track command failures
        if action.action == 'run_command' and not result.success:
            command = action.parameters.get('command', '')
            state.failed_commands.append({
                'command': command,
                'error': result.output[:200],
                'approach': self._categorize_approach(command),
                'iteration': state.iteration,
            })

        # Audit logging
        self._audit_logger.log_action(
            action=action.action,
            metadata={
                'parameters': action.parameters,
                'approved': result.approved,
                'executed': result.executed,
            }
        )
        self._audit_logger.log_result(
            result=result.output,
            success=result.success,
            metadata={'action': action.action}
        )

    def _categorize_approach(self, command: str) -> str:
        """Categorize command approach for retry detection."""
        # Simple categorization (can be moved to DuplicateDetector if needed)
        if 'npm create' in command or 'npx create' in command:
            return 'npm_create_project'
        elif 'curl' in command and 'download' in command.lower():
            return 'curl_download'
        elif 'Invoke-WebRequest' in command:
            return 'powershell_download'
        elif 'npm install' in command:
            return 'npm_install'
        elif 'npm test' in command:
            return 'npm_test'
        else:
            return 'other'

    def _finish(self, success: bool, result: str, state: ConversationState) -> dict:
        """Finalize agent run and return results."""
        if success:
            self.ui.show_result(result, title="Task Complete", is_error=False)
        else:
            self.ui.show_warning(f"Task incomplete: {result}")

        return {
            'success': success,
            'result': result,
            'iterations': state.iteration,
            'audit_log': self.audit_log,
        }

    def get_audit_log(self) -> list:
        """Get audit log (backward compatibility)."""
        return self._audit_logger.get_history()

    def save_audit_log(self, path: str = ".agent_audit.json"):
        """Save audit log to file (backward compatibility)."""
        import json
        with open(path, 'w') as f:
            json.dump(self.audit_log, f, indent=2)
```

**Result:**
- `core.py` reduced from **1,336 lines** to ~**400 lines**
- Single responsibility: Think-Plan-Execute coordination
- All responsibilities properly separated

---

## Implementation Order

**CRITICAL: Follow this exact order to avoid breaking changes**

1. ✅ **Step 0**: Define all protocols in `protocols.py` (FIRST!)
2. ✅ **Step 1**: Write tests with test doubles for each component
3. ✅ **Step 2**: Implement `ui.py` (no dependencies on core)
4. ✅ **Step 3**: Implement `safety_checker.py` (no dependencies on core)
5. ✅ **Step 4**: Implement `duplicate_detector.py` (no dependencies on core)
6. ✅ **Step 5**: Implement `tool_runner.py` (depends on existing infrastructure)
7. ✅ **Step 6**: Implement `action_executor.py` (depends on Steps 2-5)
8. ✅ **Step 7**: Refactor `core.py` to use new components
9. ✅ **Step 8**: Run all tests to ensure no regressions
10. ✅ **Step 9**: Update existing tests that directly test core.py internals

---

## Testing Strategy

**Unit Tests (test behavior, not structure):**

- `test_ui.py`: Test output formatting with TestIO
- `test_safety_checker.py`: Test safe/unsafe classification
- `test_duplicate_detector.py`: Test duplicate/retry detection with various scenarios
- `test_tool_runner.py`: Test tool execution with mock registry
- `test_action_executor.py`: Test coordination flow with test doubles

**Integration Tests:**

- `test_code_agent_integration.py`: Test full Think-Plan-Execute loop
- Test edge cases: denied actions, duplicates, failures, max iterations

**What to Test:**

✅ **Test behavior:**
- "Safe actions execute without confirmation"
- "Duplicate actions are rejected with warning"
- "Failed commands are tracked and blocked after 3 attempts"
- "UI shows correct output for errors vs success"

❌ **Don't test structure:**
- "ActionExecutor has a safety_checker attribute"
- "UI is initialized with io parameter"

---

## Migration Checklist

Before marking this refactoring complete, verify:

- [ ] All 5 new protocols defined in `protocols.py`
- [ ] All 5 new classes created and implement their protocols
- [ ] Tests written for each component (with test doubles)
- [ ] Tests prove behavior, not structure
- [ ] `core.py` refactored to use new components
- [ ] All existing tests still pass
- [ ] No regressions in existing functionality
- [ ] Each class < 300 lines
- [ ] Each class has single responsibility
- [ ] All dependencies injected via constructor
- [ ] No side effects in constructors
- [ ] Factory methods used for default dependencies

---

## Benefits

**Before:**
- `core.py`: 1,336 lines, 8+ responsibilities
- Hard to test (requires real I/O, real tools)
- Tight coupling (can't swap UI or execution logic)
- Hard to understand (UI mixed with business logic)

**After:**
- `core.py`: ~400 lines, 1 responsibility (coordination)
- `AgentUI`: ~120 lines, 1 responsibility (display)
- `SafetyChecker`: ~40 lines, 1 responsibility (safety validation)
- `DuplicateDetector`: ~80 lines, 1 responsibility (duplicate detection)
- `ToolRunner`: ~100 lines, 1 responsibility (tool execution)
- `ActionExecutor`: ~200 lines, 1 responsibility (execution coordination)

**Total: ~940 lines across 6 focused classes vs 1,336 lines in 1 monolith**

**Testing improvements:**
- Each component testable in isolation
- No real I/O needed during unit tests
- Fast tests
- Clear test names that prove features work

**Maintainability improvements:**
- Change UI? Edit only `ui.py`
- Change safety? Edit only `safety_checker.py`
- Change duplicate logic? Edit only `duplicate_detector.py`
- Each file < 300 lines, easy to understand

**Flexibility improvements:**
- Swap implementations (RichUI vs SimpleUI)
- Test with mock components
- Reuse components in other contexts

---

## Summary

This updated plan:

1. **Acknowledges existing progress** - Protocols, DI infrastructure, CLIIOProtocol, platform adapter
2. **Builds on what exists** - Uses CLIIOProtocol, wraps it with AgentUI
3. **Keeps architectural goals** - Extract UI, safety, duplicate detection, tool execution, coordination
4. **Provides clear steps** - Protocol → Test → Implement → Refactor
5. **Maintains SOLID principles** - Single Responsibility, Dependency Inversion, etc.

The refactoring will result in:
- **Better testability** - Each component testable in isolation
- **Better maintainability** - Each file < 300 lines, single responsibility
- **Better flexibility** - Swap implementations easily
- **Better understanding** - Clear separation of concerns
