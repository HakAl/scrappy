`src/agent/core.py` is doing too much. It handles high-level orchestration, low-level UI rendering, shell command heuristics, tool execution, and safety checks.

Here is a plan to decompose `CodeAgent` into focused, single-responsibility components adhering to SOLID principles and the protocol-first design pattern.

### The Plan

**Philosophy: Protocol First, Then Implementation**

Following CLAUDE.md strictly, we MUST define protocols before writing any concrete classes.

1.  **Define Protocols**: Create all interface contracts first (Step 0)
2.  **Write Tests**: Test the contracts with test doubles
3.  **Extract UI/Presentation**: Move all `_show_*` methods to a focused UI class
4.  **Extract Safety & Validation**: Separate safety checking and duplicate detection
5.  **Extract Tool Execution**: Pure tool running logic
6.  **Extract Action Coordination**: Orchestrate safety → validation → execution flow
7.  **Simplify Core**: `CodeAgent` becomes a thin coordinator managing "Think-Plan-Execute" loop

### New File Structure

```text
scrappy/src/agent/
├── core.py                # (Modified) High-level Think-Plan-Execute loop only
├── protocols.py           # (Modified) Add new protocols
├── ui.py                  # (New) Handles Rich output and formatting
├── safety_checker.py      # (New) Action safety validation
├── duplicate_detector.py  # (New) Duplicate action detection
├── tool_runner.py         # (New) Pure tool execution
├── action_executor.py     # (New) Coordinates safety → validation → execution
└── ... (existing files)
```

---

### Step 0: Define Protocols (MUST DO FIRST)

Before writing ANY concrete classes, define the contracts in `src/agent/protocols.py`.

**Add these protocols to the existing `protocols.py` file:**

```python
"""
Agent component protocols.
Define contracts before implementing concrete classes.
"""
from typing import Protocol, Dict, Any, Optional
from .types import AgentAction, ActionResult, ConversationState

class IOProtocol(Protocol):
    """Contract for I/O operations (Click, Rich, etc.)."""
    def secho(self, message: str, fg: Optional[str] = None, bold: bool = False) -> None: ...
    def echo(self, message: str) -> None: ...
    def confirm(self, message: str, default: bool = False) -> bool: ...
    # Optional Rich features (check with hasattr in implementations)
    # def panel(self, content: str, title: str, border_style: str) -> None: ...
    # def table(self, headers: list, rows: list, title: str) -> None: ...
    # def syntax(self, code: str, language: str) -> None: ...
    # def rule(self, title: Optional[str]) -> None: ...

class AgentUIProtocol(Protocol):
    """Contract for agent user interface."""
    def show_thinking(self, text: str) -> None: ...
    def show_tool_request(self, tool_name: str, params: Dict[str, Any]) -> None: ...
    def show_command(self, command: str) -> None: ...
    def show_error(self, message: str) -> None: ...
    def show_result(self, result: str, title: str = "Result", is_error: bool = False) -> None: ...
    def show_warning(self, message: str) -> None: ...
    def show_progress(self, message: str) -> None: ...
    def show_provider_status(self, provider: str, message: str, color: str = "cyan") -> None: ...
    def show_rule(self, title: Optional[str] = None) -> None: ...
    def prompt_confirm(self, message: str = "Allow?", default: bool = False) -> bool: ...

class SafetyCheckerProtocol(Protocol):
    """Contract for action safety validation."""
    def is_safe_action(self, action: AgentAction) -> bool:
        """Returns True if action is safe and doesn't require confirmation."""
        ...

    def requires_confirmation(self, action: AgentAction, auto_confirm: bool) -> bool:
        """Returns True if action requires user confirmation."""
        ...

class DuplicateDetectorProtocol(Protocol):
    """Contract for detecting duplicate or redundant actions."""
    def check_duplicate(self, action: AgentAction, state: ConversationState) -> tuple[bool, str]:
        """
        Returns (is_duplicate, warning_message).
        If is_duplicate is True, warning_message explains why.
        """
        ...

class ToolRunnerProtocol(Protocol):
    """Contract for executing tool operations."""
    def run_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Execute a tool and return its output as a string."""
        ...

class ActionExecutorProtocol(Protocol):
    """Contract for coordinating action execution flow."""
    def execute(
        self,
        action: AgentAction,
        state: ConversationState,
        dry_run: bool = False
    ) -> ActionResult:
        """
        Orchestrates: Safety check -> Duplicate check -> Tool execution.
        Returns ActionResult with success status and output.
        """
        ...
```

**Why protocols first?**

1. **Testability**: Write tests with test doubles before concrete implementations exist
2. **Contract clarity**: Forces you to think about the interface, not implementation
3. **Dependency inversion**: Core depends on abstractions, not concretions
4. **Flexibility**: Swap implementations easily (e.g., RichUI vs SimpleUI)

---

### Step 1: Write Tests for Protocols

Before implementing, write tests using test doubles to verify the design.

**Create `tests/agent/test_action_executor.py`:**

```python
"""
Tests for ActionExecutor coordination logic.
Uses test doubles to verify behavior without concrete dependencies.
"""
from src.agent.types import AgentAction, ActionResult, ConversationState

class MockSafetyChecker:
    def __init__(self, safe_actions=None, require_confirm=False):
        self.safe_actions = safe_actions or []
        self.require_confirm = require_confirm

    def is_safe_action(self, action: AgentAction) -> bool:
        return action.action in self.safe_actions

    def requires_confirmation(self, action: AgentAction, auto_confirm: bool) -> bool:
        if auto_confirm:
            return False
        return self.require_confirm and not self.is_safe_action(action)

class MockDuplicateDetector:
    def __init__(self, is_duplicate=False, message=""):
        self.is_duplicate = is_duplicate
        self.message = message

    def check_duplicate(self, action, state):
        return (self.is_duplicate, self.message)

class MockToolRunner:
    def __init__(self, result="Success"):
        self.result = result
        self.called_with = None

    def run_tool(self, tool_name: str, parameters: dict) -> str:
        self.called_with = (tool_name, parameters)
        return self.result

class MockUI:
    def __init__(self):
        self.confirmations = []
        self.shown_requests = []
        self.shown_progress = []

    def prompt_confirm(self, message="Allow?", default=False):
        self.confirmations.append(message)
        return True

    def show_tool_request(self, tool_name, params):
        self.shown_requests.append((tool_name, params))

    def show_progress(self, message):
        self.shown_progress.append(message)

    def show_result(self, result, title="Result", is_error=False):
        pass

def test_executor_runs_safe_action_without_confirmation():
    """Safe actions should execute without user confirmation."""
    # Arrange
    safety = MockSafetyChecker(safe_actions=['read_file'])
    duplicate = MockDuplicateDetector()
    runner = MockToolRunner(result="File contents")
    ui = MockUI()

    # Create executor (will implement in Step 5)
    from src.agent.action_executor import ActionExecutor
    executor = ActionExecutor(safety, duplicate, runner, ui)

    action = AgentAction(action='read_file', parameters={'path': 'test.py'})
    state = ConversationState(messages=[], auto_confirm=False)

    # Act
    result = executor.execute(action, state)

    # Assert
    assert result.success is True
    assert result.output == "File contents"
    assert len(ui.confirmations) == 0  # No confirmation required
    assert runner.called_with == ('read_file', {'path': 'test.py'})

def test_executor_blocks_unsafe_action_without_confirmation():
    """Unsafe actions should require confirmation when auto_confirm=False."""
    # Test that executor requests confirmation for unsafe actions
    # ... (similar structure)

def test_executor_rejects_duplicate_action():
    """Duplicate actions should be rejected without execution."""
    # Test that duplicate detector prevents redundant operations
    # ... (similar structure)
```

**Why test first?**

- Proves the design works before writing implementation
- Defines expected behavior clearly
- Catches design flaws early
- Makes refactoring safer

---

### Step 2: Create `src/agent/ui.py`

This class abstracts *how* things are displayed from *what* the agent is doing.

```python
"""
Agent UI implementation.
Handles all user interaction and console output formatting.
"""
from typing import Optional, Dict, Any
import json
from .protocols import AgentUIProtocol, IOProtocol

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
    """Implements AgentUIProtocol with Rich/Click formatting."""

    def __init__(self, io: IOProtocol):
        self.io = io

    def show_thinking(self, text: str) -> None:
        if not text or not text.strip():
            return
        if hasattr(self.io, 'panel'):
            self.io.panel(text, title="Thinking", border_style="blue")
        else:
            self.io.secho(f"[Thinking] {text}", fg="blue")

    def show_tool_request(self, tool_name: str, params: Dict[str, Any]) -> None:
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
            self.io.secho(f"Tool: {tool_name}", fg="cyan", bold=True)
            self.io.echo(f"Parameters: {json.dumps(params, indent=2)}")

    def show_command(self, command: str) -> None:
        if hasattr(self.io, 'syntax'):
            self.io.syntax(command, language="shell")
        else:
            self.io.secho(f"$ {command}", fg="yellow")

    def show_error(self, message: str) -> None:
        if hasattr(self.io, 'panel'):
            self.io.panel(message, title="Error", border_style="red")
        else:
            self.io.secho(f"Error: {message}", fg="red")

    def show_result(self, result: str, title: str = "Result", is_error: bool = False) -> None:
        color = "red" if is_error else "green"
        if hasattr(self.io, 'panel'):
            # Truncate very long output for display
            display_result = result[:2000] + "... [truncated]" if len(result) > 2000 else result
            self.io.panel(display_result, title=title, border_style=color)
        else:
            self.io.secho(f"{title}: {result}", fg=color)

    def show_warning(self, message: str) -> None:
        if hasattr(self.io, 'panel'):
            self.io.panel(message, title="Warning", border_style="yellow")
        else:
            self.io.secho(f"Warning: {message}", fg="yellow")

    def show_progress(self, message: str) -> None:
        self.io.secho(message, fg="cyan")

    def show_provider_status(self, provider: str, message: str, color: str = "cyan") -> None:
        self.io.secho(f"[{provider}] {message}", fg=color)

    def show_rule(self, title: Optional[str] = None) -> None:
        if hasattr(self.io, 'rule'):
            self.io.rule(title)
        else:
            self.io.echo(f"\n{'='*60}")
            if title:
                self.io.echo(f" {title} ")

    def prompt_confirm(self, message: str = "Allow?", default: bool = False) -> bool:
        return self.io.confirm(message, default=default)
```

### Step 3: Create `src/agent/safety_checker.py`

Single responsibility: Determine if an action is safe or requires confirmation.

```python
"""
Safety checker for agent actions.
Determines which actions are safe to auto-execute vs require user confirmation.
"""
from typing import Set
from .types import AgentAction
from .protocols import SafetyCheckerProtocol

class SafetyChecker:
    """Implements SafetyCheckerProtocol for action safety validation."""

    # Actions that are read-only and safe to execute without confirmation
    SAFE_ACTIONS: Set[str] = {
        'read_file',
        'list_files',
        'search_code',
        'git_status',
        'git_diff',
        'get_context',
    }

    def is_safe_action(self, action: AgentAction) -> bool:
        """Returns True if action is safe and doesn't require confirmation."""
        return action.action in self.SAFE_ACTIONS

    def requires_confirmation(self, action: AgentAction, auto_confirm: bool) -> bool:
        """Returns True if action requires user confirmation."""
        if auto_confirm:
            return False
        if action.action == 'complete':
            return False
        return not self.is_safe_action(action)
```

---

### Step 4: Create `src/agent/duplicate_detector.py`

Single responsibility: Detect duplicate or redundant actions.

```python
"""
Duplicate action detector.
Prevents the agent from repeating failed or redundant operations.
"""
from typing import Optional
from .types import AgentAction, ConversationState
from .protocols import DuplicateDetectorProtocol

class DuplicateDetector:
    """Implements DuplicateDetectorProtocol for redundancy detection."""

    def check_duplicate(self, action: AgentAction, state: ConversationState) -> tuple[bool, str]:
        """
        Returns (is_duplicate, warning_message).
        If is_duplicate is True, warning_message explains why.
        """
        # Check if this exact action was recently executed
        if self._is_recent_duplicate(action, state):
            return (True, f"Action '{action.action}' with these parameters was already attempted recently.")

        # Check if command has failed multiple times
        if action.action == 'run_command':
            failure_count = self._count_command_failures(action, state)
            if failure_count >= 3:
                return (True, f"Command has failed {failure_count} times. Stopping to avoid infinite loop.")

        return (False, "")

    def _is_recent_duplicate(self, action: AgentAction, state: ConversationState) -> bool:
        """Check if action was executed in last N iterations."""
        LOOKBACK_WINDOW = 3
        recent_actions = state.action_history[-LOOKBACK_WINDOW:] if hasattr(state, 'action_history') else []

        for recent_action in recent_actions:
            if (recent_action.action == action.action and
                recent_action.parameters == action.parameters):
                return True
        return False

    def _count_command_failures(self, action: AgentAction, state: ConversationState) -> int:
        """Count how many times this specific command has failed."""
        if not hasattr(state, 'command_failures'):
            return 0

        command = action.parameters.get('command', '')
        return state.command_failures.get(command, 0)
```

---

### Step 5: Create `src/agent/tool_runner.py`

Single responsibility: Execute tools and return their output.

```python
"""
Tool runner implementation.
Pure execution logic for running tools from the registry.
"""
from typing import Dict, Any, Callable, Optional
from .types import AgentAction
from .protocols import ToolRunnerProtocol, ToolRegistryProtocol, CommandExecutorProtocol

class ToolRunner:
    """Implements ToolRunnerProtocol for tool execution."""

    def __init__(
        self,
        tool_registry: ToolRegistryProtocol,
        command_executor: CommandExecutorProtocol,
        project_root: str,
    ):
        self.tool_registry = tool_registry
        self.command_executor = command_executor
        self.project_root = project_root

        # Build tool mapping from registry
        self.tools: Dict[str, Callable] = {}
        for tool in self.tool_registry.list_all():
            # Create a closure that captures the tool instance
            def make_tool_wrapper(t):
                return lambda **kwargs: t.execute(**kwargs)
            self.tools[tool.name] = make_tool_wrapper(tool)

        # Special handling for run_command
        self.tools['run_command'] = self._run_command_tool

    def run_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Execute a tool and return its output as a string."""
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        try:
            result = self.tools[tool_name](**parameters)
            return str(result)
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def _run_command_tool(self, command: str, **kwargs) -> str:
        """Special handler for run_command with interactive CLI detection."""
        # Check for interactive CLIs that need special handling
        interactive_patterns = ['npx', 'npm create', 'yarn create']
        needs_interaction = any(pattern in command for pattern in interactive_patterns)

        if needs_interaction:
            # Add --yes or equivalent flags
            if 'npx' in command and '--yes' not in command:
                command = command.replace('npx', 'npx --yes')

        # Delegate to command executor
        return self.command_executor.run(command, cwd=self.project_root)
```

---

### Step 6: Create `src/agent/action_executor.py`

Single responsibility: Coordinate the execution flow (safety → validation → execution).

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
    """Implements ActionExecutorProtocol for coordinated action execution."""

    def __init__(
        self,
        safety_checker: SafetyCheckerProtocol,
        duplicate_detector: DuplicateDetectorProtocol,
        tool_runner: ToolRunnerProtocol,
        ui: AgentUIProtocol,
    ):
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
        Orchestrates: Safety check -> Duplicate check -> Tool execution.
        Returns ActionResult with success status and output.
        """
        # Special case: 'complete' action
        if action.action == 'complete':
            return ActionResult(
                success=True,
                output=action.parameters.get('result', 'Task completed'),
                approved=True,
                executed=True,
                action='complete',
                parameters=action.parameters
            )

        # 1. Safety & Confirmation
        if not self._check_safety_and_get_approval(action, state):
            return ActionResult(
                success=False,
                output="Action denied by user",
                approved=False,
                executed=False,
                action=action.action,
                parameters=action.parameters
            )

        # 2. Duplicate Detection
        is_duplicate, warning = self.duplicate_detector.check_duplicate(action, state)
        if is_duplicate:
            self.ui.show_warning(warning)
            return ActionResult(
                success=False,
                output=warning,
                approved=True,
                executed=False,
                action=action.action,
                parameters=action.parameters
            )

        # 3. Dry Run Check
        if dry_run:
            self.ui.show_progress(f"[DRY RUN] Would execute: {action.action}")
            return ActionResult(
                success=True,
                output="[DRY RUN] Not executed",
                approved=True,
                executed=False,
                action=action.action,
                parameters=action.parameters
            )

        # 4. Execution
        self.ui.show_progress(f"Executing: {action.action}")

        try:
            output = self.tool_runner.run_tool(action.action, action.parameters)
            is_error = 'error' in output.lower() or 'failed' in output.lower()

            self.ui.show_result(output, is_error=is_error)

            return ActionResult(
                success=not is_error,
                output=output,
                approved=True,
                executed=True,
                action=action.action,
                parameters=action.parameters
            )

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.ui.show_error(error_msg)
            return ActionResult(
                success=False,
                output=error_msg,
                approved=True,
                executed=True,
                action=action.action,
                parameters=action.parameters
            )

    def _check_safety_and_get_approval(self, action: AgentAction, state: ConversationState) -> bool:
        """Returns True if action is approved for execution."""
        auto_confirm = state.auto_confirm if hasattr(state, 'auto_confirm') else False

        # Safe actions are auto-approved
        if self.safety.is_safe_action(action):
            self.ui.show_tool_request(action.action, action.parameters)
            self.ui.show_progress("Auto-approved (safe operation)")
            return True

        # Unsafe actions need confirmation (unless auto_confirm is True)
        if not self.safety.requires_confirmation(action, auto_confirm):
            return True

        # Ask user
        self.ui.show_tool_request(action.action, action.parameters)
        return self.ui.prompt_confirm("Allow this action?", default=False)
```

### Step 7: Refactor `src/agent/core.py`

The core agent becomes a thin coordinator focused on the Think-Plan-Execute loop.

```python
"""
Core Code Agent implementation.
Thin coordinator for the Think-Plan-Execute loop.
"""
from typing import Optional, Union
from pathlib import Path

from ..agent_config import AgentConfig
from ..orchestrator_adapter import OrchestratorAdapter, AgentOrchestratorAdapter
from .types import AgentThought, AgentAction, ConversationState, EvaluationResult, ActionResult
from .audit import AuditLogger
from .response_parser import UnifiedResponseParser
from .prompt_builder import PromptBuilder

# Import protocols
from .protocols import (
    IOProtocol,
    AgentUIProtocol,
    ActionExecutorProtocol,
    SafetyCheckerProtocol,
    DuplicateDetectorProtocol,
    ToolRunnerProtocol,
    ToolRegistryProtocol,
    CommandExecutorProtocol,
)

# Import concrete implementations
from .ui import AgentUI
from .safety_checker import SafetyChecker
from .duplicate_detector import DuplicateDetector
from .tool_runner import ToolRunner
from .action_executor import ActionExecutor

class CodeAgent:
    """
    High-level agent coordinator.
    Manages Think-Plan-Execute loop, delegates all other responsibilities.
    """

    def __init__(
        self,
        orchestrator: Union[OrchestratorAdapter, object],
        project_path: Optional[str] = None,
        config: Optional[AgentConfig] = None,
        # Injected dependencies (all protocols)
        io: Optional[IOProtocol] = None,
        ui: Optional[AgentUIProtocol] = None,
        tool_registry: Optional[ToolRegistryProtocol] = None,
        command_executor: Optional[CommandExecutorProtocol] = None,
        safety_checker: Optional[SafetyCheckerProtocol] = None,
        duplicate_detector: Optional[DuplicateDetectorProtocol] = None,
        tool_runner: Optional[ToolRunnerProtocol] = None,
        action_executor: Optional[ActionExecutorProtocol] = None,
        audit_logger: Optional[AuditLogger] = None,
        response_parser: Optional[UnifiedResponseParser] = None,
    ):
        self.config = config or AgentConfig()
        self.project_root = str(Path(project_path or ".").resolve())

        # Setup Orchestrator
        if isinstance(orchestrator, OrchestratorAdapter):
            self.adapter = orchestrator
        else:
            self.adapter = AgentOrchestratorAdapter(orchestrator)

        # Setup I/O
        self.io = io or self._create_default_io()
        self.ui = ui or AgentUI(self.io)

        # Setup tool infrastructure
        self.tool_registry = tool_registry or self._create_default_tool_registry()
        self._command_executor = command_executor or self._create_default_command_executor()

        # Setup execution components (in dependency order)
        self._safety_checker = safety_checker or SafetyChecker()
        self._duplicate_detector = duplicate_detector or DuplicateDetector()
        self._tool_runner = tool_runner or ToolRunner(
            tool_registry=self.tool_registry,
            command_executor=self._command_executor,
            project_root=self.project_root,
        )
        self.executor = action_executor or ActionExecutor(
            safety_checker=self._safety_checker,
            duplicate_detector=self._duplicate_detector,
            tool_runner=self._tool_runner,
            ui=self.ui,
        )

        # Setup other components
        self._audit_logger = audit_logger or AuditLogger()
        self._response_parser = response_parser or UnifiedResponseParser()

        # Provider selection
        self._setup_providers()

    def run(self, task: str, max_iterations: int = 10, auto_confirm: bool = False) -> dict:
        """
        Run the agent on a task.
        Coordinates Think -> Plan -> Execute -> Evaluate loop.
        """
        self.ui.show_rule("Agent Task")
        self.ui.show_progress("Building context...")

        # Build initial prompt
        prompt_builder = PromptBuilder(
            context=self.adapter.context,
            tool_registry=self.tool_registry
        )
        system_prompt = prompt_builder.build(
            task=task,
            use_native_tools=self._should_use_native_tools()
        )

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
            command_failures={},
        )

        try:
            while state.iteration < state.max_iterations:
                state.iteration += 1

                # 1. Think (call LLM)
                thought = self._think(state)

                # 2. Plan (parse response into action)
                action = self._plan_action(thought)

                # 3. Execute (delegated to ActionExecutor)
                result = self.executor.execute(action, state, dry_run=self.config.dry_run)

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
            content=response.get('content', ''),
            tool_calls=response.get('tool_calls', []),
            raw_response=response,
        )

    def _plan_action(self, thought: AgentThought) -> AgentAction:
        """Parse thought into concrete action."""
        return self._response_parser.parse(thought)

    def _evaluate(self, action: AgentAction, result: ActionResult, state: ConversationState) -> EvaluationResult:
        """Evaluate if task is complete or should continue."""
        if action.action == 'complete':
            return EvaluationResult(
                is_complete=True,
                should_continue=False,
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
            'content': thought.content,
            'tool_calls': thought.tool_calls,
        })

        # Add tool result
        state.messages.append({
            'role': 'tool',
            'content': result.output,
            'tool_call_id': action.tool_call_id if hasattr(action, 'tool_call_id') else None,
        })

        # Track action history for duplicate detection
        state.action_history.append(action)

        # Track command failures for retry logic
        if action.action == 'run_command' and not result.success:
            command = action.parameters.get('command', '')
            state.command_failures[command] = state.command_failures.get(command, 0) + 1

        # Audit logging
        self._audit_logger.log_action(action, result)

    def _finish(self, success: bool, result: str, state: ConversationState) -> dict:
        """Finalize agent run and return results."""
        self._audit_logger.mark_complete(success, result)

        if success:
            self.ui.show_result(result, title="Task Complete", is_error=False)
        else:
            self.ui.show_warning(f"Task incomplete: {result}")

        return {
            'success': success,
            'result': result,
            'iterations': state.iteration,
            'audit_log': self._audit_logger.get_log(),
        }

    # Factory methods for default dependencies
    def _create_default_io(self) -> IOProtocol:
        """Create default I/O interface (Click)."""
        import click
        return click  # Click already implements the protocol structurally

    def _create_default_tool_registry(self) -> ToolRegistryProtocol:
        """Create default tool registry."""
        from ..tools.registry import ToolRegistry
        return ToolRegistry()

    def _create_default_command_executor(self) -> CommandExecutorProtocol:
        """Create default command executor."""
        from ..execution.command_executor import CommandExecutor
        return CommandExecutor()

    def _should_use_native_tools(self) -> bool:
        """Determine if provider supports native tool calling."""
        return self.config.use_native_tools and self.adapter.supports_native_tools()

    def _setup_providers(self) -> None:
        """Setup provider selection logic."""
        # ... (existing provider setup code)
        pass
```

---

### Implementation Order

**CRITICAL: Follow this exact order to avoid breaking changes**

1. **Step 0**: Define all protocols in `protocols.py` (FIRST!)
2. **Step 1**: Write tests with test doubles for each component
3. **Step 2**: Implement `ui.py` (no dependencies on core)
4. **Step 3**: Implement `safety_checker.py` (no dependencies on core)
5. **Step 4**: Implement `duplicate_detector.py` (no dependencies on core)
6. **Step 5**: Implement `tool_runner.py` (depends on protocols only)
7. **Step 6**: Implement `action_executor.py` (depends on Steps 3-5)
8. **Step 7**: Refactor `core.py` to use new components
9. **Step 8**: Run all tests to ensure no regressions
10. **Step 9**: Update integration tests

---

### Testing Strategy

**Unit Tests (test behavior, not structure):**

- `test_ui.py`: Test output formatting (mock IOProtocol)
- `test_safety_checker.py`: Test safe vs unsafe action classification
- `test_duplicate_detector.py`: Test duplicate detection logic with various scenarios
- `test_tool_runner.py`: Test tool execution with mock tools
- `test_action_executor.py`: Test coordination flow (safety → duplicate → execution)

**Integration Tests:**

- `test_code_agent_integration.py`: Test full Think-Plan-Execute loop with real components
- Test edge cases: denied actions, duplicates, command failures, max iterations

**What to Test:**

✅ Test behavior:
- "Safe actions execute without confirmation"
- "Duplicate actions are rejected with warning"
- "Command failures are tracked and limited to 3 attempts"
- "UI shows correct output for errors vs success"

❌ Don't test structure:
- "ActionExecutor has a safety_checker attribute"
- "UI is initialized with io parameter"
- "ToolRunner has a tools dictionary"

---

### Benefits of This Refactoring

**Before (God Class):**
- `CodeAgent`: 850+ lines, 10+ responsibilities
- Hard to test (requires real file system, real LLM, real UI)
- Tight coupling (can't swap UI or execution logic)
- Hard to understand (UI mixed with business logic)

**After (Focused Components):**
- `CodeAgent`: ~200 lines, 1 responsibility (coordination)
- `AgentUI`: ~100 lines, 1 responsibility (display)
- `SafetyChecker`: ~30 lines, 1 responsibility (safety validation)
- `DuplicateDetector`: ~50 lines, 1 responsibility (redundancy detection)
- `ToolRunner`: ~80 lines, 1 responsibility (tool execution)
- `ActionExecutor`: ~120 lines, 1 responsibility (execution coordination)

**Total: ~580 lines across 6 focused classes vs 850+ lines in 1 god class**

**Testing improvements:**
- Each component testable in isolation with test doubles
- No need for real file system, LLM, or UI during unit tests
- Fast tests (no I/O operations)
- Clear test names that prove features work

**Maintainability improvements:**
- Change UI formatting? Edit only `ui.py`
- Change safety rules? Edit only `safety_checker.py`
- Change duplicate logic? Edit only `duplicate_detector.py`
- Add new tool? Edit only `tool_runner.py`
- Each file < 150 lines, easy to understand

**Flexibility improvements:**
- Swap implementations (e.g., RichUI vs SimpleUI)
- Test with mock components
- Reuse components in other contexts

---

### Migration Checklist

Before marking this refactoring complete, verify:

- [ ] All protocols defined in `protocols.py`
- [ ] All new classes implement their protocols
- [ ] No `Any` types in signatures (all typed with protocols)
- [ ] Tests written for each component (with test doubles)
- [ ] Tests prove behavior, not structure
- [ ] Integration tests pass
- [ ] No regressions in existing functionality
- [ ] Code coverage maintained or improved
- [ ] Each class < 200 lines
- [ ] Each class has single responsibility
- [ ] All dependencies injected via constructor
- [ ] No side effects in constructors
- [ ] Factory methods used for default dependencies

---

### Summary

This refactoring transforms a 850+ line god class into 6 focused components:

1. **Protocols** (contracts before implementation)
2. **AgentUI** (presentation logic)
3. **SafetyChecker** (safety validation)
4. **DuplicateDetector** (redundancy detection)
5. **ToolRunner** (pure execution)
6. **ActionExecutor** (execution coordination)
7. **CodeAgent** (high-level coordination)

**Result:** Better testability, maintainability, and flexibility while following SOLID principles and protocol-first design.