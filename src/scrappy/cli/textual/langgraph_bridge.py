"""
LangGraph-Textual bridge for running agent in worker thread.

This module provides LangGraphBridge which bridges the LangGraph async
execution model to Textual's worker pattern. It allows running the
LangGraph agent in a background thread while routing confirmations
through the UI and streaming output to the chat log.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Protocol, runtime_checkable

from textual import work
from textual.worker import Worker, WorkerCancelled, get_current_worker

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

        Extracts tool names from tool_results and displays them to the user.

        Args:
            node_output: The execute node's output dict containing state updates
        """
        tool_results = node_output.get("tool_results", [])
        if not tool_results:
            return

        for result in tool_results:
            if isinstance(result, dict):
                name = result.get("name", "unknown")
                self._output_callback(f"[Tool: {name}]\n")
                # Show brief error if any
                if result.get("error"):
                    error_preview = str(result["error"])[:100]
                    self._output_callback(f"  Error: {error_preview}\n")

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

            # Use stream() instead of invoke() to allow cancellation between nodes
            final_state = self._run_with_streaming(
                graph, initial_state, config, AgentState
            )

            if final_state is None:
                # Cancelled
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

            # Output diagnostic info if there was an error
            if final_state.last_error:
                self._output_callback(f"\nLast error: {final_state.last_error}\n")

            logger.debug("run_agent: returning success=%s", is_success)
            return AgentResult(
                success=is_success,
                final_state=final_state,
                error=final_state.last_error,
                cancelled=False,
            )

        except WorkerCancelled:
            logger.info("Agent run cancelled via WorkerCancelled")
            return AgentResult(
                success=False,
                final_state=None,
                error=None,
                cancelled=True,
            )
        except Exception as e:
            logger.exception("Agent run failed: %s", e)
            return AgentResult(
                success=False,
                final_state=None,
                error=str(e),
                cancelled=False,
            )
        finally:
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
