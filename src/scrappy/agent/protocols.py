"""
Agent component protocols.

Defines abstract interfaces for agent components including audit logging,
response parsing, prompt building, tool management, and checkpointing.
"""

from typing import Protocol, Dict, Any, List, Optional, Tuple, runtime_checkable, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from .types import (
        AgentThought,
        AgentAction,
        ActionResult,
        EvaluationResult,
        ConversationState,
        AgentContext,
    )
    from ..agent_tools.tools.base import ToolResult


@runtime_checkable
class AuditLoggerProtocol(Protocol):
    """
    Protocol for audit logging.

    Abstracts audit logging to enable testing without file I/O
    and support different logging strategies.

    Implementations:
    - AuditLogger: File-based audit logging
    - InMemoryAuditLogger: In-memory logging for testing
    - NullAuditor: No-op auditor for testing

    Example:
        def log_action(auditor: AuditLoggerProtocol, action: str, result: Any) -> None:
            auditor.log_action(action, {"status": "success"})
            auditor.log_result(result)
    """

    def log_action(
        self,
        action: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an action.

        Args:
            action: Action description
            metadata: Optional action metadata
        """
        ...

    def log_result(
        self,
        result: Any,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log action result.

        Args:
            result: Result data
            success: Whether action succeeded
            metadata: Optional result metadata
        """
        ...

    def get_history(
        self,
        limit: Optional[int] = None,
        filter_by: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get audit history.

        Args:
            limit: Maximum entries to return
            filter_by: Filter criteria

        Returns:
            List of audit log entries
        """
        ...

    def export(self, format: str = "json") -> str:
        """
        Export audit log in specified format.

        Args:
            format: Export format (json, csv, etc.)

        Returns:
            Formatted audit log
        """
        ...

    def clear(self) -> None:
        """
        Clear audit log.
        """
        ...


@runtime_checkable
class ResponseParserProtocol(Protocol):
    """
    Protocol for response parsing.

    Abstracts LLM response parsing to enable testing with controlled
    responses and support different parsing strategies.

    Implementations:
    - UnifiedResponseParser: Auto-detects format (JSON/native tools)
    - JSONResponseParser: Parses JSON-formatted responses
    - NativeToolCallParser: Parses native tool call responses

    Example:
        def parse_response(parser: ResponseParserProtocol, text: str) -> ParseResult:
            result = parser.parse(text)
            return result
    """

    def parse(self, response_text: str) -> Any:
        """
        Parse LLM response into structured ParseResult.

        Args:
            response_text: Raw LLM response text

        Returns:
            ParseResult containing:
            - thought: Agent's reasoning
            - action: Tool to execute
            - parameters: Tool parameters
            - is_complete: Whether task is finished
            - result_text: Final result if complete
            - error: Error message if parsing failed
        """
        ...


@runtime_checkable
class ToolRegistryProtocol(Protocol):
    """
    Protocol for tool registry.

    Abstracts tool registration and execution to enable testing
    with mock tools and support different tool sets.

    Implementations:
    - ToolRegistry: Full tool registry with dynamic loading
    - TestToolRegistry: Registry with mock tools for testing
    - RestrictedToolRegistry: Registry with limited tool set

    Example:
        def execute_tool(registry: ToolRegistryProtocol, name: str, **kwargs: Any) -> Any:
            tool = registry.get(name)
            return registry.execute(tool, **kwargs)
    """

    def register(
        self,
        tool: Any,
        name: Optional[str] = None,
    ) -> None:
        """
        Register a tool.

        Args:
            tool: Tool object/function to register
            name: Tool name (uses tool.name if not provided)

        Raises:
            ValueError: If tool with same name already registered
        """
        ...

    def get(self, name: str) -> Optional[Any]:
        """
        Get tool by name.

        Args:
            name: Tool name

        Returns:
            Tool object/function, or None if not found
        """
        ...

    def list_all(self) -> List[Any]:
        """
        List all registered tools.

        Returns:
            List of tool objects
        """
        ...

    def execute(
        self,
        tool_name: str,
        context: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Execute tool with arguments.

        Args:
            tool_name: Name of tool to execute
            context: Tool execution context
            **kwargs: Tool-specific arguments

        Returns:
            Tool execution result
        """
        ...

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool.

        Args:
            name: Tool name

        Returns:
            True if tool was unregistered, False if not found
        """
        ...

    def exists(self, name: str) -> bool:
        """
        Check if tool is registered.

        Args:
            name: Tool name

        Returns:
            True if tool is registered, False otherwise
        """
        ...


@runtime_checkable
class ToolContextProtocol(Protocol):
    """
    Protocol for tool execution context.

    Abstracts tool context to enable testing with controlled
    environments and support different execution contexts.

    Implementations:
    - ToolContext: Full tool context with project awareness
    - TestToolContext: Minimal context for testing
    - RestrictedToolContext: Sandboxed context with restrictions

    Example:
        def get_project_path(ctx: ToolContextProtocol) -> Path:
            return ctx.get_project_root()
    """

    def get_project_root(self) -> Path:
        """
        Get project root directory.

        Returns:
            Project root path
        """
        ...

    def get_config(self) -> Dict[str, Any]:
        """
        Get agent configuration.

        Returns:
            Configuration dictionary
        """
        ...

    def is_dry_run(self) -> bool:
        """
        Check if in dry-run mode.

        Returns:
            True if dry-run mode enabled, False otherwise
        """
        ...

    def is_path_allowed(self, path: str) -> bool:
        """
        Check if path is within allowed scope.

        Args:
            path: Path to check

        Returns:
            True if path is allowed, False otherwise
        """
        ...

    def get_orchestrator(self) -> Any:
        """
        Get orchestrator instance.

        Returns:
            Orchestrator or adapter instance
        """
        ...


@runtime_checkable
class CheckpointManagerProtocol(Protocol):
    """
    Protocol for git checkpointing.

    Abstracts git checkpoint operations to enable testing without
    real git operations and support different checkpoint strategies.

    Implementations:
    - GitCheckpointManager: Real git-based checkpointing
    - InMemoryCheckpointManager: In-memory checkpoints for testing
    - NoOpCheckpointManager: No-op for testing

    Example:
        def save_state(mgr: CheckpointManagerProtocol, message: str) -> str:
            return mgr.create_checkpoint(message)

        def undo_changes(mgr: CheckpointManagerProtocol, checkpoint_id: str) -> None:
            mgr.rollback(checkpoint_id)
    """

    def create_checkpoint(
        self,
        message: str,
        files: Optional[List[str]] = None,
    ) -> str:
        """
        Create checkpoint of current state.

        Args:
            message: Checkpoint description
            files: Specific files to checkpoint (None for all changes)

        Returns:
            Checkpoint identifier (e.g., commit hash)
        """
        ...

    def rollback(self, checkpoint_id: str) -> None:
        """
        Rollback to checkpoint.

        Args:
            checkpoint_id: Checkpoint to rollback to

        Raises:
            ValueError: If checkpoint not found
        """
        ...

    def list_checkpoints(
        self,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        List available checkpoints.

        Args:
            limit: Maximum checkpoints to return

        Returns:
            List of checkpoint dictionaries containing:
            - id: Checkpoint identifier
            - message: Checkpoint description
            - timestamp: Creation time
            - files: List of files in checkpoint
        """
        ...

    def get_checkpoint_diff(
        self,
        checkpoint_id: str,
    ) -> str:
        """
        Get diff for checkpoint.

        Args:
            checkpoint_id: Checkpoint to get diff for

        Returns:
            Diff text
        """
        ...

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """
        Delete checkpoint.

        Args:
            checkpoint_id: Checkpoint to delete

        Returns:
            True if deleted, False if not found
        """
        ...


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

    def show_diff_preview(
        self,
        path: str,
        diff_lines: List[str],
        max_lines: int = 30
    ) -> None:
        """
        Display diff preview before file write.

        Args:
            path: File path being modified
            diff_lines: Lines from unified diff output
            max_lines: Maximum lines to show before truncating
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

    def confirm(self, message: str, default: bool = True) -> bool:
        """
        Prompt user for yes/no confirmation.

        Args:
            message: Question to ask user
            default: Default value if user just presses enter

        Returns:
            True if user confirms, False otherwise
        """
        ...

    def show_info(self, message: str) -> None:
        """
        Display informational message.

        Args:
            message: Message to display
        """
        ...

    def reset_step_counter(self) -> None:
        """
        Reset step counter for new task.

        Should be called at the start of each new agent task to
        ensure step numbering starts fresh.
        """
        ...

    def show_completion(self, result: str, success: bool = True) -> None:
        """
        Display task completion message.

        Args:
            result: Completion message/result text
            success: Whether the task completed successfully
        """
        ...

    def notify_tasks_updated(self, tasks: list) -> None:
        """
        Notify UI that agent tasks have been updated.

        Called when the task tool modifies tasks (add, update, delete, clear).
        Implementations should update any task progress display.

        Args:
            tasks: Current list of Task objects
        """
        ...

    def prompt_checkpoint(self, iteration: int, tools_count: int) -> str:
        """
        Prompt user at safety checkpoint with multiple options.

        Called every N iterations to give user control over long-running agents.
        Works even in auto-confirm mode as a safety net.

        Args:
            iteration: Current iteration number
            tools_count: Number of tools executed so far

        Returns:
            User's choice: 'c' (continue), 'g' (git checkpoint),
            'a' (allow all), 's' (stop)
        """
        ...

    def confirm_batch(
        self,
        actions: List[Tuple[str, Dict[str, Any]]],
    ) -> bool:
        """
        Display batch of actions in activity bar and prompt for approval.

        Used when LLM returns multiple tool calls. Shows a compact summary
        of all actions and asks for batch approval.

        Args:
            actions: List of (tool_name, parameters) tuples

        Returns:
            True if user approves all actions, False if denied
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

    def run_tool(self, tool_name: str, parameters: Dict[str, Any]) -> "ToolResult":
        """
        Execute a tool and return its result.

        Args:
            tool_name: Name of tool to execute
            parameters: Tool-specific parameters

        Returns:
            ToolResult with output, success status, and metadata

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


# =============================================================================
# Agent Loop Protocols (Phase 1 Refactoring)
# =============================================================================

@runtime_checkable
class AgentLoopProtocol(Protocol):
    """
    Protocol for coordinating the agent's think-plan-execute-evaluate cycle.

    Abstracts the core agent loop to enable testing with controlled
    execution flow and support different loop strategies.

    Implementations:
    - AgentLoop: Full agent loop with all stages
    - TestAgentLoop: Minimal loop for testing
    - SingleStepLoop: Executes only one iteration (for testing)

    Example:
        def run_task(loop: AgentLoopProtocol, task: str) -> EvaluationResult:
            state = ConversationState(...)
            return loop.run(task, state)
    """

    def run(
        self,
        task: str,
        state: "ConversationState",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the complete agent loop until completion or max iterations.

        Args:
            task: Task description to accomplish
            state: ConversationState to track progress
            dry_run: If True, simulate execution without actual changes

        Returns:
            Dict with completion status, result, and iteration count
        """
        ...

    def think(
        self,
        state: "ConversationState",
        context: "AgentContext",
    ) -> "AgentThought":
        """
        Generate the next thought/action from the LLM.

        Args:
            state: Current conversation state
            context: AgentContext with system prompt and active tools

        Returns:
            AgentThought containing raw LLM response
        """
        ...

    def plan(self, thought: "AgentThought") -> "AgentAction":
        """
        Parse the LLM response into a structured action.

        Args:
            thought: Raw thought from think()

        Returns:
            AgentAction with parsed action details
        """
        ...

    def execute(
        self,
        action: "AgentAction",
        state: "ConversationState",
    ) -> "ActionResult":
        """
        Execute the planned action (tool call).

        Args:
            action: Parsed action from plan()
            state: Current conversation state

        Returns:
            ActionResult with execution details
        """
        ...

    def evaluate(
        self,
        action: "AgentAction",
        result: "ActionResult",
        state: "ConversationState",
    ) -> "EvaluationResult":
        """
        Evaluate whether the task is complete.

        Args:
            action: The action that was planned
            result: The result of executing the action
            state: Current conversation state

        Returns:
            EvaluationResult indicating whether to continue
        """
        ...


@runtime_checkable
class ProviderSelectionStrategyProtocol(Protocol):
    """
    Protocol for selecting LLM providers for agent tasks.

    Abstracts provider selection to enable testing with controlled
    provider choices and support different selection strategies.

    Implementations:
    - DynamicProviderStrategy: Rate-limit-aware selection via orchestrator
    - StaticProviderStrategy: Fixed provider preferences from config
    - RoundRobinStrategy: Rotate through available providers

    Example:
        def get_provider(strategy: ProviderSelectionStrategyProtocol) -> str:
            provider = strategy.get_planner()
            if provider is None:
                raise ValueError("No provider available")
            return provider
    """

    def get_planner(self) -> Optional[str]:
        """
        Get recommended provider for planning/reasoning tasks.

        Returns:
            Provider name, or None if no provider available
        """
        ...

    def get_executor(self) -> Optional[str]:
        """
        Get recommended provider for execution tasks.

        Returns:
            Provider name, or None if no provider available
        """
        ...

    def supports_dynamic_selection(self) -> bool:
        """
        Check if strategy supports dynamic provider selection.

        Dynamic selection means the provider may change between calls
        based on rate limits, availability, or other factors.

        Returns:
            True if dynamic selection supported, False for static
        """
        ...


@runtime_checkable
class DenialHandlerProtocol(Protocol):
    """
    Protocol for handling user denials of actions.

    Abstracts denial handling to enable different strategies:
    - Ask user if they want to stop entirely
    - Track denial count and auto-stop
    - Continue with different approach (default behavior)

    Implementations:
    - InteractiveDenialHandler: Asks user if they want to stop
    - AutoStopDenialHandler: Stops after N denials
    - ContinueDenialHandler: Always continues (default behavior)

    Example:
        def handle_denial(handler: DenialHandlerProtocol, action: str) -> DenialHandlerResult:
            result = handler.handle_denial(action, denial_count=1)
            if result.should_stop:
                return stop_agent()
            else:
                continue_with_message(result.message)
    """

    def handle_denial(
        self,
        action: str,
        denial_count: int,
    ) -> Any:  # Returns DenialHandlerResult
        """
        Handle a user denial of an action.

        Args:
            action: The action that was denied
            denial_count: Number of times similar actions have been denied

        Returns:
            DenialHandlerResult with should_stop flag and message
        """
        ...


@runtime_checkable
class AgentContextFactoryProtocol(Protocol):
    """
    Protocol for building agent execution context.

    Abstracts context building to enable testing with controlled
    context generation and support different context strategies.

    Implementations:
    - AgentContextFactory: Full context building with passive RAG and tool filtering
    - TestAgentContextFactory: Minimal context for testing
    - StaticAgentContextFactory: Fixed context without dynamic RAG

    Example:
        def prepare_context(
            factory: AgentContextFactoryProtocol,
            task: str,
            base_prompt: str
        ) -> AgentContext:
            context = factory.build_context(task, base_prompt)
            return context
    """

    def build_context(
        self,
        task: str,
        base_system_prompt: str,
    ) -> "AgentContext":
        """
        Build agent execution context for a task.

        Context includes:
        - System prompt with passive RAG context injected
        - Active tools list (filtered based on semantic search availability)
        - Passive RAG context string (pre-computed relevant code snippets)

        Args:
            task: Task description to build context for
            base_system_prompt: Base system prompt template to augment

        Returns:
            AgentContext with system prompt, active tools, and passive RAG context
        """
        ...
