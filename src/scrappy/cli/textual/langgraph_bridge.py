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
from typing import TYPE_CHECKING, Any, Optional, Protocol, runtime_checkable

from textual import work
from textual.worker import Worker, WorkerCancelled, get_current_worker

from scrappy.protocols.activity import ActivityState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from textual.app import App

    from scrappy.graph.agent import LLMServiceProtocol
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
        llm_service: LLM service for agent completions
        tool_adapter: Tool adapter for agent tool execution
    """

    def __init__(
        self,
        app: "App",
        bridge: "ThreadSafeAsyncBridge",
        output_adapter: "TextualOutputAdapter",
        llm_service: "LLMServiceProtocol",
        tool_adapter: Optional["ToolAdapterProtocol"] = None,
    ) -> None:
        """
        Initialize the LangGraph bridge.

        Args:
            app: Textual app instance (needed for @work decorator context)
            bridge: ThreadSafeAsyncBridge for blocking confirmations
            output_adapter: TextualOutputAdapter for thread-safe output
            llm_service: LLM service for agent completions
            tool_adapter: Optional tool adapter (default: create default)
        """
        self.app = app
        self._bridge = bridge
        self._output_adapter = output_adapter
        self._llm_service = llm_service
        self._tool_adapter = tool_adapter

        # Track current worker for cancellation
        self._current_worker: Optional[Worker[AgentResult]] = None

        # Concurrency guard - prevent multiple simultaneous runs
        self._is_running: bool = False

        # Track start time for elapsed time updates
        self._start_time: float = 0.0

        # Track working directory for diff display
        self._working_dir: str = ""

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

        Returns:
            True if cancelled, False otherwise
        """
        try:
            worker = get_current_worker()
            return worker.is_cancelled
        except Exception:
            # Not running in a worker context
            return False

    def _output_tool_executions(self, node_output: dict[str, Any]) -> None:
        """
        Output tool execution info from execute node output.

        Displays tool calls in format: [tool] name: key_param
        Truncates long paths (>50 chars) with ellipsis.
        Shows git diff for file-modifying tools.

        Args:
            node_output: The execute node's output dict containing state updates
        """
        tool_calls = node_output.get("pending_tool_calls", [])
        tool_results = node_output.get("tool_results", [])

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

            # Add blank line between tool calls for visual separation
            if i > 0:
                self._output_callback("\n")

            # Format output with bullet and styled tool name
            if key_param:
                self._output_callback(f"[dim]>[/dim] [bold]{name}[/bold]: {key_param}\n")
            else:
                self._output_callback(f"[dim]>[/dim] [bold]{name}[/bold]\n")

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

            # Show diff for file-modifying tools
            if name in file_write_tools and self._working_dir:
                file_path = self._get_file_path_from_args(args)
                if file_path:
                    self._output_file_diff(file_path)

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
    ) -> AgentResult:
        """
        Run the agent synchronously (for use inside worker thread).

        This method is designed to be called from within a @work(thread=True)
        decorated method. It runs the LangGraph agent with human-in-the-loop
        support, routing confirmations through the UI bridge.

        Uses graph.stream() instead of graph.invoke() to allow cancellation
        checks between node executions.

        Args:
            task: The user's task/query
            working_dir: Working directory for file operations
            thread_id: Optional thread ID for checkpointing (default: generate UUID)

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

        # Capture current worker for cancellation support
        try:
            self._current_worker = get_current_worker()
        except Exception:
            pass  # Not running in worker context

        # Generate thread ID if not provided
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        try:
            # Create agent runner with HITL support
            graph, checkpointer = create_agent_runner(
                llm_service=self._llm_service,
                tool_adapter=self._tool_adapter,
            )

            # Create initial state
            initial_state = AgentState.create_initial(task, working_dir)

            # Configure graph execution
            # Note: recursion_limit counts TOTAL node invocations, not iterations.
            # With think->execute pattern, each iteration = 2 nodes.
            # MAX_ITERATIONS=50 means up to 100+ nodes (including error/verify nodes).
            # Set to 150 to allow for error recovery loops without hitting the limit.
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 150,
            }

            logger.info("Starting agent run for task: %s", task[:100])
            self._output_callback(f"Task: {task}\n")

            # Start timing, set working dir, and show initial activity
            self._start_time = time.time()
            self._working_dir = working_dir
            self._post_activity(ActivityState.THINKING)

            # Use stream() instead of invoke() to allow cancellation between nodes
            final_state = self._run_with_streaming(
                graph, initial_state, config, AgentState
            )

            if final_state is None:
                # Cancelled
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

            # Check if agent actually completed successfully
            # done=False means it hit iteration limit without completing
            # last_error set means there were unrecoverable errors
            is_success = final_state.done and final_state.last_error is None

            # Output completion summary
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
            # Clear activity indicator
            self._post_activity(ActivityState.IDLE)
            self._start_time = 0.0
            self._working_dir = ""
            # Clear running state to allow new runs
            self._is_running = False
            self._current_worker = None

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
                # Check for cancellation after each node
                if self._check_cancellation():
                    logger.info("Agent run cancelled by user (during stream)")
                    return None

                # Extract state from event
                # Event format: {node_name: state_dict}
                for node_name, node_output in event.items():
                    if isinstance(node_output, dict):
                        # Update current state from node output
                        try:
                            current_state = state_class(**node_output)
                        except Exception:
                            # Node output might be partial, get full state
                            pass

                        # Output tool executions when execute node completes
                        if node_name == "execute":
                            self._output_tool_executions(node_output)

                    # Update activity indicator based on node
                    if node_name == "think":
                        self._post_activity(ActivityState.THINKING)
                    elif node_name == "execute":
                        self._post_activity(ActivityState.TOOL_EXECUTION)
                    elif node_name == "verify":
                        self._post_activity(ActivityState.THINKING, "verifying")
                    elif node_name == "error":
                        self._post_activity(ActivityState.THINKING, "recovering")

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
    ) -> AgentResult:
        """
        Run the agent in a Textual worker thread.

        This method uses @work(thread=True) to run in a background thread pool.
        It handles the full agent execution lifecycle including:
        - Human-in-the-loop confirmations via ThreadSafeAsyncBridge
        - Streaming output via TextualOutputAdapter
        - Cancellation via Worker state checks

        Args:
            task: The user's task/query
            working_dir: Working directory for file operations
            thread_id: Optional thread ID for checkpointing

        Returns:
            AgentResult with success status and final state
        """
        return self.run_agent(task, working_dir, thread_id)

    async def run_agent_async(
        self,
        task: str,
        working_dir: str,
        thread_id: Optional[str] = None,
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

        Returns:
            AgentResult with success status and final state
        """
        # Run in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.run_agent,
            task,
            working_dir,
            thread_id,
        )

    def cancel(self) -> None:
        """
        Cancel the current agent run if any.

        This signals the worker to stop at the next cancellation check point.
        The agent will stop gracefully and return a cancelled result.
        """
        if self._current_worker is not None:
            self._current_worker.cancel()
            logger.info("Agent run cancellation requested")

    @property
    def is_running(self) -> bool:
        """
        Check if an agent run is currently in progress.

        Returns:
            True if agent is running, False otherwise
        """
        return self._is_running
