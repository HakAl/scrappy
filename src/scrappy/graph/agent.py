"""
LangGraph agent assembly and entry point.

Wires all nodes and edges into a StateGraph for agent execution.

Graph Structure:
    START -> think -> (conditional) -> execute -> (conditional)
                |                          |
                |              +-----------+-----------+-----------+
                |              |           |           |           |
                |           verify      confirm      error        end
                |              |           |           |
                |              +-----------+-----------+
                |                          |
                +-------------<------------+
                |
            error/end (if think failed)

Features:
- Entry point: think (no separate classify)
- Conditional edges from think using edges.route_after_think() (error bypass)
- Conditional edges from execute using edges.should_continue()
- Error node handles failures, routes back to think
- Compiled with MemorySaver checkpointer
- interrupt_before=["confirm"] for human-in-the-loop
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from scrappy.graph.edges import MAX_ITERATIONS, MAX_RETRIES, Route, route_after_think, should_continue
from scrappy.graph.nodes import (
    confirm_node,
    error_node,
    execute_node,
    think_node,
    verify_node,
)
from scrappy.graph.nodes.think_delegator import LiteLLMThinkDelegator
from scrappy.graph.protocols import ContextFactoryProtocol, StreamingOrchestratorProtocol, WorkingMemoryProtocol
from scrappy.graph.state import AgentState
from scrappy.graph.tools import ToolAdapterProtocol
from scrappy.graph.tracing import get_langfuse_callback
from scrappy.infrastructure.logging import get_logger

logger = get_logger(__name__)

# System directories that should never be used as working_dir
# These are dangerous because file operations would affect critical system files
FORBIDDEN_DIRECTORIES = frozenset({
    "/",
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/lib",
    "/lib64",
    "/proc",
    "/root",
    "/sbin",
    "/sys",
    "/usr",
    "/var",
    "C:\\",
    "C:\\Windows",
    "C:\\Windows\\System32",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
})


class WorkingDirectoryError(ValueError):
    """Raised when working_dir validation fails."""


def validate_working_dir(working_dir: str) -> Path:
    """
    Validate working directory for safety.

    Checks:
    - Path is not empty
    - Path exists
    - Path is a directory (not a file)
    - Path is not a critical system directory

    Args:
        working_dir: Path to validate

    Returns:
        Resolved Path object

    Raises:
        WorkingDirectoryError: If validation fails
    """
    if not working_dir or not working_dir.strip():
        raise WorkingDirectoryError("working_dir cannot be empty")

    try:
        path = Path(working_dir).resolve()
    except (OSError, ValueError) as e:
        raise WorkingDirectoryError(f"Invalid working_dir path: {e}") from e

    if not path.exists():
        raise WorkingDirectoryError(f"working_dir does not exist: {path}")

    if not path.is_dir():
        raise WorkingDirectoryError(f"working_dir is not a directory: {path}")

    # Check against forbidden system directories
    # Must check if path IS or is WITHIN any forbidden directory
    # (e.g., /etc/cron.d is within /etc and must be blocked)
    for forbidden in FORBIDDEN_DIRECTORIES:
        try:
            forbidden_path = Path(forbidden)
            if os.name == "nt":
                # Windows: case-insensitive comparison
                # Drive roots (e.g., C:\) should only block exact match
                # Subdirs (e.g., C:\Windows) should block containment
                is_drive_root = (
                    len(forbidden_path.parts) == 1
                    and len(forbidden_path.drive) > 0
                )
                if is_drive_root:
                    # Only block exact drive root match
                    if path.drive.lower() == forbidden_path.drive.lower() and len(path.parts) == 1:
                        raise WorkingDirectoryError(
                            f"working_dir cannot be system directory {forbidden}: {path}"
                        )
                else:
                    # Block if path is within forbidden subdirectory
                    path_parts = [p.lower() for p in path.parts]
                    forbidden_parts = [p.lower() for p in forbidden_path.parts]
                    if path_parts[:len(forbidden_parts)] == forbidden_parts:
                        raise WorkingDirectoryError(
                            f"working_dir cannot be within system directory {forbidden}: {path}"
                        )
            else:
                # Unix: use relative_to for proper path containment check
                try:
                    path.relative_to(forbidden_path)
                    raise WorkingDirectoryError(
                        f"working_dir cannot be within system directory {forbidden}: {path}"
                    )
                except ValueError:
                    pass  # path is not within forbidden - this is good
        except WorkingDirectoryError:
            raise  # Re-raise our own exceptions
        except (OSError, ValueError):
            continue  # Invalid forbidden path, skip

    return path


def _wrap_think_node(
    orchestrator: StreamingOrchestratorProtocol,
    tool_adapter: Optional[ToolAdapterProtocol],
    working_memory: Optional[WorkingMemoryProtocol] = None,
    context_factory: Optional[ContextFactoryProtocol] = None,
) -> Any:
    """
    Create a wrapped think node with injected dependencies.

    LangGraph nodes receive only state. We use a closure to inject
    the delegator and tool adapter.

    Args:
        orchestrator: Orchestrator for streaming completions with fallback
        tool_adapter: Tool adapter for schemas
        working_memory: Optional working memory for session context
        context_factory: Optional factory for RAG context augmentation

    Returns:
        Node function compatible with LangGraph
    """
    from langgraph.types import RunnableConfig
    from typing import Optional as Opt

    # Create delegator that uses the orchestrator for streaming completions
    delegator = LiteLLMThinkDelegator(orchestrator)

    def wrapped(state: AgentState, config: Opt[RunnableConfig] = None) -> AgentState:
        # Extract run_context from config if present (for cancellation support)
        run_context = None
        if config is not None:
            configurable = config.get("configurable")
            if configurable is not None:
                run_context = configurable.get("run_context")

        return think_node(
            state,
            delegator,
            tool_adapter,
            working_memory=working_memory,
            context_factory=context_factory,
            run_context=run_context,
        )
    return wrapped


def _wrap_execute_node(
    tool_adapter: ToolAdapterProtocol,
    context_factory: Optional[Any] = None,
    working_memory: Optional[WorkingMemoryProtocol] = None,
) -> Any:
    """
    Create a wrapped execute node with injected dependencies.

    Args:
        tool_adapter: Tool adapter for execution
        context_factory: Optional factory for creating ToolContext
        working_memory: Optional working memory for tracking tool results

    Returns:
        Node function compatible with LangGraph
    """
    from langgraph.types import RunnableConfig

    def wrapped(state: AgentState, config: RunnableConfig) -> AgentState:
        # Extract run_context from config if present
        run_context = None
        if config and "configurable" in config:
            run_context = config["configurable"].get("run_context")

        return execute_node(
            state, tool_adapter, context_factory, working_memory, run_context=run_context
        )
    return wrapped


def _wrap_verify_node(run_mypy_check: bool = True) -> Any:
    """
    Create a wrapped verify node with configuration.

    Args:
        run_mypy_check: Whether to run mypy (can be slow)

    Returns:
        Node function compatible with LangGraph
    """
    def wrapped(state: AgentState) -> AgentState:
        return verify_node(state, run_mypy_check=run_mypy_check)
    return wrapped


def _route_after_execute(state: AgentState) -> Route:
    """
    Route after execute node using should_continue logic.

    This is the conditional edge function that determines where to go
    after execute node completes.

    Args:
        state: Current agent state

    Returns:
        Destination node name
    """
    return should_continue(state)


def _route_after_error(state: AgentState) -> Route:
    """
    Route after error node.

    Checks MAX_RETRIES and MAX_ITERATIONS before routing back to think.
    This prevents wasting an LLM call when we're about to terminate anyway.

    Args:
        state: Current agent state

    Returns:
        Route.END if limits reached, Route.THINK otherwise
    """
    if state.error_count >= MAX_RETRIES:
        return Route.END
    if state.iteration >= MAX_ITERATIONS:
        return Route.END
    return Route.THINK


def _route_after_confirm(state: AgentState) -> Route:
    """
    Route after confirm node.

    Checks done flag and MAX_ITERATIONS before routing back to think.
    This prevents wasting an LLM call when we're about to terminate anyway.

    Args:
        state: Current agent state

    Returns:
        Route.END if done or iteration limit reached, Route.THINK otherwise
    """
    if state.done:
        return Route.END
    if state.iteration >= MAX_ITERATIONS:
        return Route.END
    return Route.THINK


def _route_after_verify(state: AgentState) -> Route:
    """
    Route after verify node.

    Checks MAX_ITERATIONS before routing back to think.
    This prevents wasting an LLM call when we're about to terminate anyway.

    Args:
        state: Current agent state

    Returns:
        Route.END if iteration limit reached, Route.THINK otherwise
    """
    if state.iteration >= MAX_ITERATIONS:
        return Route.END
    return Route.THINK


def build_graph(
    orchestrator: StreamingOrchestratorProtocol,
    tool_adapter: ToolAdapterProtocol,
    checkpointer: Optional[MemorySaver] = None,
    run_mypy_check: bool = True,
    enable_hitl: bool = True,
    context_factory: Optional[Any] = None,
    working_memory: Optional[WorkingMemoryProtocol] = None,
    rag_context_factory: Optional[ContextFactoryProtocol] = None,
) -> CompiledStateGraph:
    """
    Build and compile the agent graph.

    Assembles all nodes and edges into a StateGraph, then compiles
    with checkpointing and interrupt support.

    Graph Structure:
        START -> think -> execute -> (conditional routing)
                             |
                 +-----------+-----------+-----------+
                 |           |           |           |
              verify      confirm      error        end
                 |           |           |
                 +-----------+-----------+
                             |
                          think

    Args:
        orchestrator: Orchestrator for streaming completions with fallback
        tool_adapter: Tool adapter for execute node (required)
        checkpointer: MemorySaver for checkpointing (default: create new)
        run_mypy_check: Whether to run mypy in verify node
        enable_hitl: Whether to enable human-in-the-loop interrupts at confirm
                     node. Set False for autonomous execution (default: True)
        context_factory: Factory for creating ToolContext (default: uses agent_tools ToolContext)
        working_memory: Optional working memory for session context and tool tracking
        rag_context_factory: Factory for RAG context augmentation in think node

    Returns:
        Compiled StateGraph ready for execution
    """
    # Default checkpointer if not provided
    if checkpointer is None:
        checkpointer = MemorySaver()

    # Create the state graph builder
    builder: StateGraph[AgentState] = StateGraph(AgentState)

    # Add nodes with wrapped functions that have dependencies injected
    builder.add_node("think", _wrap_think_node(orchestrator, tool_adapter, working_memory, rag_context_factory))
    builder.add_node("execute", _wrap_execute_node(tool_adapter, context_factory, working_memory))
    builder.add_node("verify", _wrap_verify_node(run_mypy_check))
    builder.add_node("confirm", confirm_node)
    builder.add_node("error", error_node)

    # Set entry point to think
    builder.set_entry_point("think")

    # Add conditional edge from think to execute (or error if think failed)
    # This allows think errors to route directly to error node without going through execute
    builder.add_conditional_edges(
        "think",
        route_after_think,
        {
            Route.EXECUTE: "execute",
            Route.ERROR: "error",
            Route.END: END,
        },
    )

    # Add conditional edges from execute
    # This is the main routing logic after tool execution
    builder.add_conditional_edges(
        "execute",
        _route_after_execute,
        {
            Route.THINK: "think",
            Route.VERIFY: "verify",
            Route.CONFIRM: "confirm",
            Route.ERROR: "error",
            Route.END: END,
        },
    )

    # Add conditional edges from verify
    # Design: verify routes to think on success or failure, but checks iteration limit.
    # When verify fails, it sets error_count and last_error, but the LLM in think
    # sees the error in messages and can reason about how to fix it.
    # Check MAX_ITERATIONS before routing to think to avoid exceeding limit.
    builder.add_conditional_edges(
        "verify",
        _route_after_verify,
        {
            Route.THINK: "think",
            Route.END: END,
        },
    )

    # Add conditional edges from confirm
    # Check done flag before routing to think to avoid wasting LLM call on abort
    builder.add_conditional_edges(
        "confirm",
        _route_after_confirm,
        {
            Route.THINK: "think",
            Route.END: END,
        },
    )

    # Add conditional edges from error
    # Check MAX_RETRIES before routing to think to avoid wasting LLM call
    builder.add_conditional_edges(
        "error",
        _route_after_error,
        {
            Route.THINK: "think",
            Route.END: END,
        },
    )

    # Compile with checkpointer and interrupt support
    # Only interrupt at confirm node if HITL is enabled
    interrupt_nodes = ["confirm"] if enable_hitl else []
    compiled = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_nodes,
    )

    # Note: Langfuse callbacks are added at runtime in run_agent() config
    # to avoid mutation issues when callers pass their own callbacks
    logger.debug("Agent graph compiled successfully")

    return compiled


def run_agent(
    task: str,
    working_dir: str,
    orchestrator: StreamingOrchestratorProtocol,
    tool_adapter: Optional[ToolAdapterProtocol] = None,
    checkpointer: Optional[MemorySaver] = None,
    thread_id: Optional[str] = None,
    working_memory: Optional[WorkingMemoryProtocol] = None,
) -> AgentState:
    """
    Run the agent on a task.

    This is the main entry point for agent execution. It creates
    initial state, builds the graph, and runs until completion.

    Note: For human-in-the-loop support, use build_graph() directly
    and handle interrupts manually. This function runs to completion
    without confirmation prompts.

    Args:
        task: The user's task/query
        working_dir: Working directory for file operations
        orchestrator: Orchestrator for streaming completions with fallback
        tool_adapter: Tool adapter (default: create default)
        checkpointer: MemorySaver for checkpointing (default: create new)
        thread_id: Thread ID for checkpointing (default: generate UUID)
        working_memory: Optional working memory for session context and tool tracking

    Returns:
        Final AgentState after execution completes

    Raises:
        WorkingDirectoryError: If working_dir validation fails
    """
    # Validate working_dir for safety before any operations
    validated_path = validate_working_dir(working_dir)
    logger.debug("Working directory validated: %s", validated_path)

    # Create initial state with validated path
    initial_state = AgentState.create_initial(task, str(validated_path))

    # Build and compile graph
    # Disable HITL - run_agent runs to completion without interrupts
    graph = build_graph(
        orchestrator=orchestrator,
        tool_adapter=tool_adapter,
        checkpointer=checkpointer,
        enable_hitl=False,
        working_memory=working_memory,
    )

    # Generate thread ID if not provided
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    # Config for checkpointing
    # Note: recursion_limit counts TOTAL node invocations, not iterations.
    # With think->execute pattern, each iteration = 2 nodes.
    # MAX_ITERATIONS (from edges.py) = 50, so need at least 100 nodes.
    # Set to 150 to allow for error recovery loops.
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 150,
    }

    # Add Langfuse tracing at runtime (not compile time) to avoid callback mutation
    langfuse_handler = get_langfuse_callback()
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        logger.debug("Langfuse tracing enabled for agent run")

    # Use context binding for correlated logs across the entire agent run
    with logger.context(thread_id=thread_id, task_summary=task[:50]):
        logger.info("Starting agent run for task: %s", task[:100])

        # Run the graph
        # Note: This will pause at confirm nodes due to interrupt_before
        # For full HITL support, caller should use build_graph() directly
        result = graph.invoke(initial_state, config)  # type: ignore[arg-type]

        # Result is a dict, convert back to AgentState
        if isinstance(result, dict):
            final_state = AgentState(**result)
        else:
            final_state = result

        logger.info(
            "Agent run completed: done=%s, iterations=%d",
            final_state.done,
            final_state.iteration,
        )

    return final_state


def create_agent_runner(
    orchestrator: StreamingOrchestratorProtocol,
    tool_adapter: ToolAdapterProtocol,
    run_mypy_check: bool = True,
    enable_hitl: bool = True,
    working_memory: Optional[WorkingMemoryProtocol] = None,
    rag_context_factory: Optional[ContextFactoryProtocol] = None,
) -> tuple[CompiledStateGraph, MemorySaver]:
    """
    Create an agent runner with shared checkpointer.

    Use this when you need to:
    - Handle human-in-the-loop confirmations
    - Resume from checkpoints
    - Access graph state during execution

    Returns both the compiled graph and checkpointer so caller can:
    1. Call graph.invoke(state, config) to start
    2. Detect interrupts via graph.get_state(config)
    3. Update state via graph.update_state(config, updates)
    4. Resume via graph.invoke(None, config)

    Args:
        orchestrator: Orchestrator for streaming completions with fallback
        tool_adapter: Tool adapter (default: create default)
        run_mypy_check: Whether to run mypy in verify node
        enable_hitl: Whether to enable human-in-the-loop interrupts (default: True)
        working_memory: Optional working memory for session context and tool tracking
        rag_context_factory: Factory for RAG context augmentation in think node

    Returns:
        Tuple of (compiled_graph, checkpointer)

    Example:
        graph, checkpointer = create_agent_runner(orchestrator)
        config = {"configurable": {"thread_id": "my-session"}}

        # Start execution
        state = AgentState.create_initial(task, working_dir)
        result = graph.invoke(state, config)

        # Check if interrupted at confirm
        snapshot = graph.get_state(config)
        if snapshot.next == (CONFIRM,):
            # Handle confirmation
            user_response = get_user_confirmation()
            graph.update_state(config, {"confirmation_response": user_response})
            result = graph.invoke(None, config)  # Resume
    """
    checkpointer = MemorySaver()

    graph = build_graph(
        orchestrator=orchestrator,
        tool_adapter=tool_adapter,
        checkpointer=checkpointer,
        run_mypy_check=run_mypy_check,
        enable_hitl=enable_hitl,
        working_memory=working_memory,
        rag_context_factory=rag_context_factory,
    )

    return graph, checkpointer
