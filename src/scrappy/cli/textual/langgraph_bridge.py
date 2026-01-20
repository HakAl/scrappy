"""
LangGraph-Textual bridge for running agent in worker thread.

This module provides LangGraphBridge which bridges the LangGraph async
execution model to Textual's worker pattern. It allows running the
LangGraph agent in a background thread while routing confirmations
through the UI and streaming output to the chat log.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Protocol, runtime_checkable, cast

from textual import work
from textual.worker import Worker, WorkerCancelled, get_current_worker

from scrappy.context.agent_rules_loader import AgentRulesLoader
from scrappy.context.reminder_manager import ReminderManager
from scrappy.graph.run_context import AgentRunContext
from scrappy.infrastructure.threading import CancellationToken
from ..protocols import ActivityState, Task, TaskStatus
from .tool_confirmation import ToolConfirmationHandler
from .messages import MetricsUpdate

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from textual.app import App

    from scrappy.graph.protocols import StreamingOrchestratorProtocol
    from scrappy.graph.state import AgentState
    from scrappy.graph.tools import ToolAdapterProtocol

    from .bridge import ThreadSafeAsyncBridge
    from .output_adapter import TextualOutputAdapter

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result of an agent run."""

    success: bool
    """Whether the agent completed successfully."""

    final_state: Optional["AgentState"]
    """Final agent state, or None if cancelled/errored."""

    error: Optional[str]
    """Error message if failed, None otherwise."""

    cancelled: bool
    """Whether the run was cancelled."""


@runtime_checkable
class ConfirmCallbackProtocol(Protocol):
    """Protocol for confirmation callback."""

    def __call__(self, question: str) -> bool:
        """Ask user for confirmation, block until response."""
        ...


@runtime_checkable
class OutputCallbackProtocol(Protocol):
    """Protocol for output callback."""

    def __call__(self, content: str) -> None:
        """Output content to the UI."""
        ...


class _MetricsUnset:
    """Sentinel for optional metrics updates."""


_METRICS_UNSET = _MetricsUnset()


class LangGraphBridge:
    """
    Bridge between LangGraph agent execution and Textual UI.

    This bridge allows running the LangGraph agent in a worker thread
    while properly routing:
    - Confirmations through ThreadSafeAsyncBridge (blocks worker, shows in UI)
    - Output through TextualOutputAdapter (thread-safe queue to UI)

    The bridge uses Textual's @work(thread=True) pattern to run the
    agent in a background thread pool, preventing UI freezes.

    Attributes:
        app: The Textual app instance
        bridge: ThreadSafeAsyncBridge for confirmation dialogs
        output_adapter: TextualOutputAdapter for streaming output
        orchestrator: Orchestrator for streaming completions with fallback
        tool_adapter: Tool adapter for agent tool execution
    """

    def __init__(
        self,
        app: "App",
        bridge: "ThreadSafeAsyncBridge",
        output_adapter: "TextualOutputAdapter",
        orchestrator: "StreamingOrchestratorProtocol",
        tool_adapter: "ToolAdapterProtocol",
    ) -> None:
        """
        Initialize the LangGraph bridge.

        Args:
            app: Textual app instance (needed for @work decorator context)
            bridge: ThreadSafeAsyncBridge for blocking confirmations
            output_adapter: TextualOutputAdapter for thread-safe output
            orchestrator: Orchestrator for streaming completions with fallback
            tool_adapter: Tool adapter for agent tool execution (required)
        """
        self.app = app
        self._bridge = bridge
        self._output_adapter = output_adapter
        self._orchestrator = orchestrator
        self._tool_adapter = tool_adapter

        # Track current worker for cancellation
        self._current_worker: Optional[Worker[AgentResult]] = None

        # Concurrency guard - prevent multiple simultaneous runs
        self._is_running: bool = False

        # Track start time for elapsed time updates
        self._start_time: float = 0.0

        # Track working directory for diff display
        self._working_dir: str = ""

        # Task progress tracking (rolling window)
        self._recent_tasks: list[Task] = []
        self._max_completed_tasks: int = 3  # Keep last N completed

        # Tool confirmation handler (created per run with working_dir)
        self._confirmation_handler: Optional[ToolConfirmationHandler] = None

        # Run context for current agent run (ephemeral)
        self._run_context: Optional[AgentRunContext] = None

        # Cancellation token for multi-press force cancel support (per-run)
        self._cancellation_token: Optional[CancellationToken] = None

        # Metrics tracking for status bar
        self._metrics_provider_display: Optional[str] = None
        self._metrics_input_tokens: Optional[int] = None
        self._metrics_output_tokens: Optional[int] = None
        self._metrics_context_percent: Optional[int] = None
        self._session_total_tokens: Optional[int] = None
        self._metrics_updated_this_run: bool = False


    def _post_activity(
        self,
        state: ActivityState,
        message: str = "",
    ) -> None:
        """
        Post activity state change to UI.

        Args:
            state: Activity state (THINKING, TOOL_EXECUTION, IDLE)
            message: Optional message to display
        """
        elapsed_ms = int((time.time() - self._start_time) * 1000) if self._start_time else 0
        self._output_adapter.post_activity(state, message, elapsed_ms)

    def _show_provider_status(self, tier: str) -> None:
        """Update provider display in the metrics status line."""
        try:
            self._post_metrics_update(provider_display=tier)
        except Exception:
            pass  # Screen might not be ready

    def _hide_provider_status(self) -> None:
        """Clear provider display in the metrics status line."""
        try:
            self._post_metrics_update(provider_display=None)
        except Exception:
            pass  # Screen might not be ready

    def _post_metrics_update(
        self,
        provider_display: Any = _METRICS_UNSET,
        input_tokens: Any = _METRICS_UNSET,
        output_tokens: Any = _METRICS_UNSET,
        context_percent: Any = _METRICS_UNSET,
    ) -> None:
        if provider_display is not _METRICS_UNSET:
            self._metrics_provider_display = provider_display
        if input_tokens is not _METRICS_UNSET:
            self._metrics_input_tokens = input_tokens
        if output_tokens is not _METRICS_UNSET:
            self._metrics_output_tokens = output_tokens
        if context_percent is not _METRICS_UNSET:
            self._metrics_context_percent = context_percent

        if input_tokens is not _METRICS_UNSET and output_tokens is not _METRICS_UNSET:
            if input_tokens is not None and output_tokens is not None:
                delta = input_tokens + output_tokens
                if self._session_total_tokens is None:
                    self._session_total_tokens = delta
                else:
                    self._session_total_tokens += delta
                self._metrics_updated_this_run = True

        try:
            logger.debug(
                "Posting MetricsUpdate: provider=%s, in=%s, out=%s, total=%s, ctx=%s",
                self._metrics_provider_display, self._metrics_input_tokens,
                self._metrics_output_tokens, self._session_total_tokens,
                self._metrics_context_percent
            )
            self.app.post_message(MetricsUpdate(
                provider_display=self._metrics_provider_display,
                input_tokens=self._metrics_input_tokens,
                output_tokens=self._metrics_output_tokens,
                session_total=self._session_total_tokens,
                context_percent=self._metrics_context_percent,
            ))
        except Exception as e:
            logger.debug("Failed to post MetricsUpdate: %s", e)

    def _confirm_callback(self, question: str) -> bool:
        """
        Confirmation callback that routes through ThreadSafeAsyncBridge.

        This is called from the worker thread when the agent needs
        human confirmation. It blocks until the user responds via the UI.

        Args:
            question: The confirmation question to ask

        Returns:
            True if confirmed, False if denied or shutdown
        """
        return self._bridge.blocking_confirm(question)

    def _tool_confirm_callback(
        self, tool_name: str, description: str, args: dict[str, Any]
    ) -> bool:
        """
        Confirmation callback for destructive tools.

        Called by ToolAdapter before executing destructive tools like
        write_file, run_command, etc. Delegates to ToolConfirmationHandler
        which displays tool info and diff preview before prompting.

        Args:
            tool_name: Name of the tool being executed
            description: Human-readable description of the operation
            args: Tool arguments (for displaying details and diff preview)

        Returns:
            True if user confirmed (y or a), False if denied (n)
        """
        if self._confirmation_handler is None:
            # Fallback if handler not initialized (shouldn't happen)
            response = self._bridge.blocking_confirm_yna(f"{description}?")
            return response in ("y", "a")

        return self._confirmation_handler.confirm_tool(tool_name, description, args)

    def _output_callback(self, content: str) -> None:
        """
        Output callback that routes through TextualOutputAdapter.

        This is called from the worker thread to stream output to the UI.
        The adapter uses a thread-safe queue consumed by the main thread.

        Args:
            content: The content to output
        """
        self._output_adapter.post_output(content)

    def _check_cancellation(self) -> bool:
        """
        Check if the current worker has been cancelled.

        Should be called periodically during long-running operations.
        Checks both the Textual worker state and our cancellation token.

        Returns:
            True if cancelled, False otherwise
        """
        # Check our cancellation token first (handles multi-press)
        if self._cancellation_token is not None and self._cancellation_token.is_cancelled:
            return True

        # Also check worker state (Textual's built-in cancellation)
        try:
            worker = get_current_worker()
            return worker.is_cancelled
        except Exception:
            # Not running in a worker context
            return False

    def _check_force_cancellation(self) -> bool:
        """
        Check if force cancellation has been requested (multiple escape presses).

        Force cancellation indicates user wants immediate termination,
        not graceful stop at next checkpoint.

        Returns:
            True if force cancelled, False otherwise
        """
        if self._cancellation_token is None:
            return False
        return self._cancellation_token.is_force_cancelled

    def _update_task_progress(self, tool_tasks: list[tuple[str, bool]]) -> None:
        """
        Update task progress widget with tool execution status.

        Maintains a rolling window showing current in-progress tool plus
        last N completed tools.

        Args:
            tool_tasks: List of (description, is_complete) tuples for tools
        """
        # Build new task list: completed tools first, then in-progress
        completed = []
        in_progress = []

        for desc, is_complete in tool_tasks:
            task = Task(
                description=desc,
                status=TaskStatus.DONE if is_complete else TaskStatus.IN_PROGRESS,
            )
            if is_complete:
                completed.append(task)
            else:
                in_progress.append(task)

        # Keep only last N completed + all in-progress
        recent_completed = completed[-self._max_completed_tasks:]
        self._recent_tasks = recent_completed + in_progress

        # Post update to TUI
        self._output_adapter.post_tasks_updated(self._recent_tasks)

    def _clear_task_progress(self) -> None:
        """Clear the task progress widget."""
        self._recent_tasks = []
        self._output_adapter.post_tasks_updated([])

    def _output_tool_executions(self, node_output: dict[str, Any]) -> None:
        """
        Output tool execution info from execute node output.

        Displays tool calls in format: [tool] name: key_param
        Truncates long paths (>50 chars) with ellipsis.
        Shows git diff for file-modifying tools.
        Updates task progress widget with completed tools.

        Args:
            node_output: The execute node's output dict containing state updates
        """
        tool_calls = node_output.get("pending_tool_calls", [])
        tool_results = node_output.get("tool_results", [])

        # Track completed tools for task widget
        completed_tools: list[str] = []

        if not tool_calls:
            return

        # File-modifying tools that should show diff
        file_write_tools = {"write_file", "edit_file", "create_file", "patch_file"}

        # Match tool calls with results by index
        for i, tool_call in enumerate(tool_calls):
            if not isinstance(tool_call, dict):
                continue

            func = tool_call.get("function", {})
            name = func.get("name", "unknown")
            raw_args = func.get("arguments", {})

            # Parse args if it's a JSON string
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    args = {}
            else:
                args = raw_args if raw_args else {}

            # Extract key parameter based on tool type
            key_param = self._extract_key_param(name, args)

            # Build task description for progress widget
            if key_param:
                task_desc = f"{name}: {key_param}"
            else:
                task_desc = name
            completed_tools.append(task_desc)

            # Add blank line between tool calls for visual separation
            if i > 0:
                self._output_callback("\n")

            # Format output with bullet and styled tool name
            # For run_command, use shell prompt style to show execution environment
            if name == "run_command":
                # Get executor type from result metadata
                exec_type = None
                if i < len(tool_results):
                    result = tool_results[i]
                    if isinstance(result, dict):
                        metadata = result.get("metadata", {})
                        if isinstance(metadata, dict):
                            exec_type = metadata.get("executor_type")

                # Shell prompt style: docker> or host>
                if exec_type == "docker":
                    prompt = "[cyan]docker>[/cyan]"
                elif exec_type == "host":
                    prompt = "[yellow]host>[/yellow]"
                else:
                    prompt = "[dim]>[/dim]"

                self._output_callback(f"{prompt} {key_param or '(no command)'}\n")
            elif key_param:
                self._output_callback(f"[dim]>[/dim] [bold]{name}[/bold]: {key_param}\n")
            else:
                self._output_callback(f"[dim]>[/dim] [bold]{name}[/bold]\n")

            # Show diff for file-modifying tools (before result)
            if name in file_write_tools and self._working_dir:
                file_path = self._get_file_path_from_args(args)
                if file_path:
                    self._output_file_diff(file_path)

            # Show result or error (from corresponding result)
            if i < len(tool_results):
                result = tool_results[i]
                if isinstance(result, dict):
                    if result.get("error"):
                        # Full error with prefix
                        error_msg = str(result["error"])[:200]
                        self._output_callback(f"  [red]error:[/red] {error_msg}\n")
                    elif result.get("result"):
                        # Truncate success result: first 3 lines or 200 chars
                        preview = self._truncate_result(str(result["result"]))
                        if preview:
                            self._output_callback(f"  [dim]{preview}[/dim]\n")

        # Update task progress widget with completed tools
        if completed_tools:
            # Add new completed tools to recent list
            for desc in completed_tools:
                self._recent_tasks.append(Task(
                    description=desc,
                    status=TaskStatus.DONE,
                ))
            # Keep only last N completed
            self._recent_tasks = self._recent_tasks[-self._max_completed_tasks:]
            self._output_adapter.post_tasks_updated(self._recent_tasks)

    def _truncate_result(self, result: str, max_lines: int = 3, max_chars: int = 200) -> str:
        """
        Truncate tool result for display.

        Args:
            result: Full result string
            max_lines: Maximum lines to show
            max_chars: Maximum characters to show

        Returns:
            Truncated result with ... if needed
        """
        if not result:
            return ""

        # Split into lines
        lines = result.strip().split("\n")

        # Take first N lines
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            truncated = "\n  ".join(lines) + "..."
        else:
            truncated = "\n  ".join(lines)

        # Also limit by chars
        if len(truncated) > max_chars:
            truncated = truncated[:max_chars - 3] + "..."

        return truncated

    def _output_completion_summary(
        self,
        success: bool,
        final_state: Optional["AgentState"],
        cancelled: bool = False,
        error: Optional[str] = None,
    ) -> None:
        """
        Output terse completion summary.

        Format:
        - Success: [complete] 3.4s - 2 files changed
        - Cancelled: [cancelled]
        - Failed: [failed] error message

        Args:
            success: Whether task completed successfully
            final_state: Final agent state (may be None)
            cancelled: Whether task was cancelled
            error: Error message if failed
        """
        elapsed_sec = time.time() - self._start_time if self._start_time else 0

        self._output_callback("\n")

        if cancelled:
            self._output_callback(f"[cancelled] {elapsed_sec:.1f}s\n")
            return

        if success and final_state:
            files = final_state.files_changed
            file_count = len(files)
            file_text = f"{file_count} file{'s' if file_count != 1 else ''} changed"
            self._output_callback(f"[complete] {elapsed_sec:.1f}s - {file_text}\n")

            # List files if any
            for f in files[:5]:  # Limit to 5 files
                self._output_callback(f"  + {f}\n")
            if len(files) > 5:
                self._output_callback(f"  ... and {len(files) - 5} more\n")
        else:
            # Failed
            error_msg = ""
            if final_state and final_state.last_error:
                error_msg = final_state.last_error[:100]
            elif error:
                error_msg = error[:100]
            self._output_callback(f"[failed] {elapsed_sec:.1f}s - {error_msg}\n")

    def _extract_key_param(self, tool_name: str, args: dict[str, Any]) -> str:
        """
        Extract the key parameter for a tool call.

        Args:
            tool_name: Name of the tool
            args: Tool arguments dict

        Returns:
            Key parameter value, truncated if >50 chars
        """
        # Map tool names to their key parameter
        key_param_map = {
            "write_file": "path",
            "read_file": "path",
            "read_files": "paths",
            "edit_file": "path",
            "run_command": "command",
            "list_files": "path",
            "list_directory": "path",
            "find_exact_text": "pattern",
            "codebase_search": "query",
            "search_files": "pattern",
            "complete": "result",
        }

        param_name = key_param_map.get(tool_name)
        if not param_name or param_name not in args:
            return ""

        value = str(args[param_name])

        # Truncate long values with ellipsis
        if len(value) > 50:
            return value[:47] + "..."

        return value

    def _get_file_path_from_args(self, args: dict[str, Any]) -> Optional[str]:
        """
        Extract file path from tool arguments.

        Handles multiple common parameter names for file paths.

        Args:
            args: Tool arguments dict

        Returns:
            File path string, or None if not found
        """
        # Try common parameter names for file paths
        file_path = (
            args.get("file_path")
            or args.get("path")
            or args.get("filepath")
            or args.get("file")
        )
        return str(file_path) if file_path else None

    def _output_file_diff(self, file_path: str) -> None:
        """
        Output git diff for a file.

        Args:
            file_path: Path to the file (relative or absolute)
        """
        from scrappy.infrastructure.git_diff import get_file_diff, format_diff_lines

        diff = get_file_diff(file_path, self._working_dir)
        if not diff:
            return

        lines = format_diff_lines(diff)
        if lines:
            # Indent each line for display
            formatted = "\n".join(f"  {line}" for line in lines)
            self._output_callback(f"{formatted}\n")

    def run_agent(
        self,
        task: str,
        working_dir: str,
        thread_id: Optional[str] = None,
        tier: str = "instruct",
    ) -> AgentResult:
        """
        Run the agent synchronously (for use inside worker thread).

        This method is designed to be called from within a @work(thread=True)
        decorated method. It runs the LangGraph agent with human-in-the-loop
        support, routing confirmations through the UI bridge.

        Uses graph.stream() instead of graph.invoke() to allow cancellation
        checks between node executions.

        Tool confirmation is enabled by default - user will be prompted
        before destructive operations (file writes, commands) with y/n/a
        options. Pressing 'a' allows all remaining operations for this run.

        Args:
            task: The user's task/query
            working_dir: Working directory for file operations
            thread_id: Optional thread ID for checkpointing (default: generate UUID)
            tier: Model tier to use ("chat" for conversation, "instruct" for agent)

        Returns:
            AgentResult with success status and final state
        """
        from scrappy.graph.agent import create_agent_runner
        from scrappy.graph.state import AgentState

        # Concurrency guard - reject if already running
        if self._is_running:
            logger.warning("Agent run rejected: another run is already in progress")
            return AgentResult(
                success=False,
                final_state=None,
                error="Another agent run is already in progress. Cancel it first.",
                cancelled=False,
            )

        # Mark as running
        self._is_running = True
        self._metrics_updated_this_run = False

        # Create confirmation handler for this run (needs working_dir)
        self._confirmation_handler = ToolConfirmationHandler(
            output_callback=self._output_callback,
            confirm_callback=self._bridge.blocking_confirm_yna,
            working_dir=working_dir,
        )

        # Always enable tool confirmation (default behavior)
        if hasattr(self._tool_adapter, "confirm_callback"):
            self._tool_adapter.confirm_callback = self._tool_confirm_callback  # type: ignore[union-attr]

        # Capture current worker for cancellation support
        try:
            self._current_worker = get_current_worker()
        except Exception:
            pass  # Not running in worker context

        # Generate thread ID if not provided
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        try:
            # Create ephemeral run context for this agent run
            self._run_context = AgentRunContext()
            self._run_context.set_status_callback(self._show_provider_status)

            # Load project rules from AGENTS.md or similar
            from pathlib import Path
            rules_loader = AgentRulesLoader()
            rules = rules_loader.load(Path(working_dir))
            if rules:
                rules_content = rules.get_combined_content()
                self._run_context.project_rules = rules_content
                logger.info(f"Loaded project rules from {rules.source_file}")

                # Create reminder manager for system reminders in tool results
                reminder_manager = ReminderManager()
                reminder_manager.set_project_rules(rules_content)
                self._run_context.reminder_manager = reminder_manager

            # Inject semantic search from codebase context if available
            if hasattr(self.app, '_codebase_context') and self.app._codebase_context:
                self._run_context.semantic_search = self.app._codebase_context.get_search_provider()

            # Create fresh cancellation token for this run and wire to context
            self._cancellation_token = CancellationToken()
            self._run_context.cancellation_token = self._cancellation_token

            # Create agent runner with HITL support
            # Tools always available - LLM decides whether to use them
            # Orchestrator handles model selection and fallback internally
            graph, checkpointer = create_agent_runner(
                orchestrator=self._orchestrator,
                tool_adapter=self._tool_adapter,
            )

            # Create initial state with tier selection
            initial_state = AgentState.create_initial(task, working_dir)
            initial_state = initial_state.model_copy(update={"current_tier": tier})

            # Configure graph execution
            # Note: recursion_limit counts TOTAL node invocations, not iterations.
            # With think->execute pattern, each iteration = 2 nodes.
            # MAX_ITERATIONS=50 means up to 100+ nodes (including error/verify nodes).
            # Set to 150 to allow for error recovery loops without hitting the limit.
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "run_context": self._run_context,
                },
                "recursion_limit": 150,
            }

            logger.info("Starting agent run for task: %s", task[:100])

            # For agent mode, show task header. For chat, skip (just stream response)
            if tier != "chat":
                self._output_callback(f"Task: {task}\n")

            # Start timing, set working dir, and show initial activity
            self._start_time = time.time()
            self._working_dir = working_dir
            self._post_activity(ActivityState.THINKING)
            # Metrics will be updated after first LLM call with actual model

            # Use stream() instead of invoke() to allow cancellation between nodes
            final_state = self._run_with_streaming(
                graph, initial_state, config, AgentState
            )

            if final_state is None:
                # Cancelled during streaming
                if self._run_context is not None:
                    try:
                        self._run_context.on_cancel()
                    except Exception:
                        pass
                    self._run_context = None
                self._output_completion_summary(
                    success=False,
                    final_state=None,
                    cancelled=True,
                )
                return AgentResult(
                    success=False,
                    final_state=None,
                    error=None,
                    cancelled=True,
                )

            logger.info(
                "Agent run completed: done=%s, iterations=%d, last_error=%s",
                final_state.done,
                final_state.iteration,
                final_state.last_error,
            )
            logger.debug("run_agent: preparing AgentResult")

            if not self._metrics_updated_this_run:
                input_tokens = final_state.last_input_tokens
                output_tokens = final_state.last_output_tokens
                model_display = final_state.last_model_display
                trace_chain = final_state.last_trace_chain
                logger.debug(
                    "Final state metrics: input=%s, output=%s, model=%s, trace=%s",
                    input_tokens, output_tokens, model_display, trace_chain
                )
                # Always post final metrics - even if tokens are None,
                # we want to show the provider name. The UI shows "--" for None values.
                provider_display = trace_chain or model_display
                self._post_metrics_update(
                    provider_display=provider_display,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    context_percent=final_state.last_context_percent,
                )

            # Check if agent actually completed successfully
            # done=False means it hit iteration limit without completing
            # last_error set means there were unrecoverable errors
            is_success = final_state.done and final_state.last_error is None

            # Output based on tier
            if tier == "chat":
                # Chat mode: output the response content
                for msg in reversed(final_state.messages):
                    if msg.get("role") == "assistant":
                        # Use `or ""` because .get() returns None if key exists with None value
                        content = msg.get("content") or ""
                        if content:
                            self._output_callback(f"{content}\n")
                            break
            else:
                # Agent mode: show completion summary
                self._output_completion_summary(
                    success=is_success,
                    final_state=final_state,
                )

            logger.debug("run_agent: returning success=%s", is_success)
            return AgentResult(
                success=is_success,
                final_state=final_state,
                error=final_state.last_error,
                cancelled=False,
            )

        except WorkerCancelled:
            logger.info("Agent run cancelled via WorkerCancelled")
            # Clean up run context on cancellation
            if self._run_context is not None:
                try:
                    self._run_context.on_cancel()
                except Exception:
                    pass
                self._run_context = None
            self._output_completion_summary(
                success=False,
                final_state=None,
                cancelled=True,
            )
            return AgentResult(
                success=False,
                final_state=None,
                error=None,
                cancelled=True,
            )
        except Exception as e:
            logger.exception("Agent run failed: %s", e)
            self._output_completion_summary(
                success=False,
                final_state=None,
                error=str(e),
            )
            return AgentResult(
                success=False,
                final_state=None,
                error=str(e),
                cancelled=False,
            )
        finally:
            # Clean up run context (file cache, cancel callbacks)
            if self._run_context is not None:
                try:
                    self._run_context.on_complete(success=True)
                except Exception:
                    pass  # Best effort cleanup
                self._run_context = None

            # Clear cancellation token
            self._cancellation_token = None

            # Clear confirmation handler
            self._confirmation_handler = None

            # Clear activity indicator
            self._post_activity(ActivityState.IDLE)
            self._start_time = 0.0
            self._working_dir = ""
            # Clear task progress widget
            self._clear_task_progress()
            # Clear running state to allow new runs
            self._is_running = False
            self._current_worker = None
            # Clean up tool resources (e.g., Docker containers)
            # Note: Per-run cleanup ensures containers are stopped after each task.
            # The tool_adapter is owned by the app and reused across runs.
            if hasattr(self._tool_adapter, 'cleanup'):
                try:
                    self._tool_adapter.cleanup()
                except Exception:
                    pass  # Best effort cleanup

    def _run_with_streaming(
        self,
        graph: "CompiledStateGraph",
        initial_state: "AgentState",
        config: dict[str, Any],
        state_class: type,
    ) -> Optional["AgentState"]:
        """
        Run graph with streaming to allow mid-execution cancellation.

        Uses graph.stream() which yields after each node, allowing us to
        check for cancellation between nodes instead of waiting for the
        entire graph to complete.

        Args:
            graph: Compiled LangGraph state graph
            initial_state: Initial agent state
            config: Graph execution config
            state_class: AgentState class for type conversion

        Returns:
            Final AgentState, or None if cancelled
        """
        # Track the latest state from streaming
        current_state: Optional["AgentState"] = None
        input_state: Optional["AgentState"] = initial_state

        while True:
            # Check for cancellation before starting/resuming
            if self._check_cancellation():
                logger.info("Agent run cancelled by user (before stream)")
                return None

            # Stream through graph nodes
            # input_state is the initial state for first run, None for resume
            for event in graph.stream(input_state, config):  # type: ignore[arg-type]
                # Log every event received
                logger.debug("Stream event received: %s", list(event.keys()) if event else "empty")

                # Check for cancellation after each node
                if self._check_cancellation():
                    logger.info("Agent run cancelled by user (during stream)")
                    return None

                # Extract state from event
                # Event format: {node_name: state_dict}
                for node_name, node_output in event.items():
                    logger.debug("Processing node: %s, output_type: %s", node_name, type(node_output).__name__)
                    node_data: Optional[dict[str, Any]] = None
                    if isinstance(node_output, dict):
                        node_data = node_output
                    elif isinstance(node_output, state_class):
                        node_data = cast(Any, node_output).model_dump()
                    else:
                        model_dump = getattr(node_output, "model_dump", None)
                        if callable(model_dump):
                            try:
                                node_data = model_dump()
                            except Exception:
                                node_data = None

                    if node_data is not None:
                        try:
                            current_state = state_class(**node_data)
                            logger.debug("State constructed from node_data: model=%s, in=%s, out=%s",
                                getattr(current_state, 'last_model_display', 'MISSING'),
                                getattr(current_state, 'last_input_tokens', 'MISSING'),
                                getattr(current_state, 'last_output_tokens', 'MISSING'))
                        except Exception as e:
                            logger.debug("State construction failed: %s, trying get_state", e)
                            # Node output might be partial, get full state
                            if node_name == "think":
                                try:
                                    snapshot = graph.get_state(config)  # type: ignore[arg-type]
                                    if snapshot.values:
                                        current_state = state_class(**snapshot.values)
                                        logger.debug("State from get_state: model=%s, in=%s, out=%s",
                                            getattr(current_state, 'last_model_display', 'MISSING'),
                                            getattr(current_state, 'last_input_tokens', 'MISSING'),
                                            getattr(current_state, 'last_output_tokens', 'MISSING'))
                                except Exception as e2:
                                    logger.debug("get_state also failed: %s", e2)

                        # Output tool executions when execute node completes
                        if node_name == "execute":
                            self._output_tool_executions(node_data)
                    elif isinstance(node_output, state_class):
                        current_state = node_output
                    elif node_name == "think":
                        try:
                            snapshot = graph.get_state(config)  # type: ignore[arg-type]
                            if snapshot.values:
                                current_state = state_class(**snapshot.values)
                        except Exception:
                            pass

                    # Update activity indicator based on node
                    if node_name == "think":
                        self._post_activity(ActivityState.THINKING)
                    elif node_name == "execute":
                        self._post_activity(ActivityState.TOOL_EXECUTION)
                    elif node_name == "verify":
                        self._post_activity(ActivityState.THINKING, "verifying")
                    elif node_name == "error":
                        # Show error category if available for better UX
                        error_msg = "recovering"
                        if current_state is not None:
                            category = getattr(current_state, "error_category", None)
                            if category:
                                error_msg = f"recovering ({category})"
                        self._post_activity(ActivityState.THINKING, error_msg)

                    # Update metrics from state after think node completes
                    if node_name == "think" and current_state is not None:
                        input_tokens = getattr(current_state, "last_input_tokens", None)
                        output_tokens = getattr(current_state, "last_output_tokens", None)
                        model_display = getattr(current_state, "last_model_display", None)
                        trace_chain = getattr(current_state, "last_trace_chain", None)
                        logger.debug(
                            "Think node metrics: input=%s, output=%s, model=%s, trace=%s",
                            input_tokens, output_tokens, model_display, trace_chain
                        )
                        # Always post metrics after think node - even if tokens are None,
                        # we want to show the provider name. The UI shows "--" for None values.
                        provider_display = trace_chain or model_display
                        self._post_metrics_update(
                            provider_display=provider_display,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            context_percent=getattr(current_state, "last_context_percent", None),
                            )

                    logger.debug("Node %s completed", node_name)

            # After stream completes, check if we're interrupted at confirm
            snapshot = graph.get_state(config)  # type: ignore[arg-type]

            if snapshot.next and "confirm" in snapshot.next:
                # Handle confirmation interrupt
                state_dict = snapshot.values
                pending = state_dict.get("pending_confirmation")

                if pending:
                    # Format confirmation question
                    confirm_type = pending.get("type", "action")
                    if confirm_type == "command":
                        question = f"Execute command: {pending.get('command', '?')}?"
                    elif confirm_type == "file":
                        question = f"Modify file: {pending.get('file_path', '?')}?"
                    else:
                        question = f"Confirm {confirm_type}?"

                    # Block for user response via UI
                    confirmed = self._confirm_callback(question)

                    # Update state with response
                    graph.update_state(
                        config,  # type: ignore[arg-type]
                        {"confirmation_response": confirmed},
                    )

                # Resume from interrupt - set input to None to continue
                input_state = None
            else:
                # Not interrupted, execution complete
                break

        # Get final state from snapshot
        snapshot = graph.get_state(config)  # type: ignore[arg-type]
        if snapshot.values:
            try:
                return state_class(**snapshot.values)
            except Exception:
                pass

        return current_state

    @work(thread=True)
    def run_agent_in_worker(
        self,
        task: str,
        working_dir: str,
        thread_id: Optional[str] = None,
        tier: str = "instruct",
    ) -> Worker[AgentResult]:
        """
        Run the agent in a Textual worker thread.

        This method uses @work(thread=True) to run in a background thread pool.
        It handles the full agent execution lifecycle including:
        - Human-in-the-loop confirmations via ThreadSafeAsyncBridge
        - Streaming output via TextualOutputAdapter
        - Cancellation via Worker state checks

        Note: The @work decorator wraps this method to return a Worker object
        immediately. The actual AgentResult is accessed via worker.result
        after the worker completes.

        Args:
            task: The user's task/query
            working_dir: Working directory for file operations
            thread_id: Optional thread ID for checkpointing
            tier: Model tier to use ("chat" for conversation, "instruct" for agent)

        Returns:
            Worker[AgentResult]: Worker object that provides the AgentResult via
            worker.result after completion.
        """
        return cast(Worker[AgentResult], self.run_agent(task, working_dir, thread_id, tier))

    async def run_agent_async(
        self,
        task: str,
        working_dir: str,
        thread_id: Optional[str] = None,
        tier: str = "instruct",
    ) -> AgentResult:
        """
        Run the agent asynchronously.

        This method runs the agent synchronously in a thread pool executor
        to avoid blocking the event loop.

        Note: For Textual integration, prefer run_agent_in_worker() which
        uses the proper @work decorator pattern.

        Args:
            task: The user's task/query
            working_dir: Working directory for file operations
            thread_id: Optional thread ID for checkpointing
            tier: Model tier to use ("chat" for conversation, "instruct" for agent)

        Returns:
            AgentResult with success status and final state
        """
        # Run in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.run_agent(task, working_dir, thread_id, tier),
        )

    def cancel(self) -> None:
        """
        Cancel the current agent run if any.

        First call: graceful cancellation at next checkpoint.
        Second+ call: force cancellation for immediate stop.

        This signals the worker to stop at the next cancellation check point.
        The agent will stop gracefully and return a cancelled result.
        """
        # Use our cancellation token for multi-press tracking
        if self._cancellation_token is not None:
            self._cancellation_token.cancel()
            count = self._cancellation_token.cancel_count
            if count >= 2:
                logger.info(f"Force cancellation requested (press #{count})")
            else:
                logger.info("Agent run cancellation requested")

        # Also cancel the worker (Textual's mechanism)
        if self._current_worker is not None:
            self._current_worker.cancel()

    @property
    def is_running(self) -> bool:
        """
        Check if an agent run is currently in progress.

        Returns:
            True if agent is running, False otherwise
        """
        return self._is_running

    @property
    def is_force_cancelled(self) -> bool:
        """
        Check if force cancellation was requested (multiple escape presses).

        Returns:
            True if user pressed escape 2+ times, False otherwise
        """
        return self._check_force_cancellation()
