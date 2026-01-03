"""
LangGraph agent assembly and entry point.

Wires all nodes and edges into a StateGraph for agent execution.

Graph Structure:
    START -> think -> execute -> (conditional)
                         |
             +-----------+-----------+-----------+
             |           |           |           |
          verify      confirm      error        end
             |           |           |
             +-----------+-----------+
                         |
                      think

Features:
- Entry point: think (no separate classify)
- Conditional edges from execute using edges.should_continue()
- Error node handles tool failures, routes back to think
- Compiled with MemorySaver checkpointer
- interrupt_before=["confirm"] for human-in-the-loop
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional, Protocol, runtime_checkable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from scrappy.graph.edges import RouteDestination, should_continue
from scrappy.graph.nodes import (
    confirm_node,
    error_node,
    execute_node,
    think_node,
    verify_node,
)
from scrappy.graph.state import AgentState
from scrappy.graph.tools import ToolAdapter, ToolAdapterProtocol
from scrappy.graph.tracing import get_langfuse_callback

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMServiceProtocol(Protocol):
    """Protocol for LLM service used by think node."""

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> tuple[Any, dict]:
        """Sync completion call."""
        ...


def _wrap_think_node(
    llm_service: LLMServiceProtocol,
    tool_adapter: Optional[ToolAdapterProtocol],
) -> Any:
    """
    Create a wrapped think node with injected dependencies.

    LangGraph nodes receive only state. We use a closure to inject
    the LLM service and tool adapter.

    Args:
        llm_service: LLM service for completions
        tool_adapter: Tool adapter for schemas

    Returns:
        Node function compatible with LangGraph
    """
    def wrapped(state: AgentState) -> AgentState:
        return think_node(state, llm_service, tool_adapter)
    return wrapped


def _wrap_execute_node(
    tool_adapter: ToolAdapterProtocol,
) -> Any:
    """
    Create a wrapped execute node with injected dependencies.

    Args:
        tool_adapter: Tool adapter for execution

    Returns:
        Node function compatible with LangGraph
    """
    def wrapped(state: AgentState) -> AgentState:
        return execute_node(state, tool_adapter)
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


def _route_after_execute(state: AgentState) -> RouteDestination:
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


def build_graph(
    llm_service: LLMServiceProtocol,
    tool_adapter: Optional[ToolAdapterProtocol] = None,
    checkpointer: Optional[MemorySaver] = None,
    run_mypy_check: bool = True,
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
        llm_service: LLM service for think node
        tool_adapter: Tool adapter for execute node (default: create default)
        checkpointer: MemorySaver for checkpointing (default: create new)
        run_mypy_check: Whether to run mypy in verify node

    Returns:
        Compiled StateGraph ready for execution
    """
    # Default tool adapter if not provided
    if tool_adapter is None:
        tool_adapter = ToolAdapter.create_default()

    # Default checkpointer if not provided
    if checkpointer is None:
        checkpointer = MemorySaver()

    # Create the state graph builder
    builder: StateGraph[AgentState] = StateGraph(AgentState)

    # Add nodes with wrapped functions that have dependencies injected
    builder.add_node("think", _wrap_think_node(llm_service, tool_adapter))
    builder.add_node("execute", _wrap_execute_node(tool_adapter))
    builder.add_node("verify", _wrap_verify_node(run_mypy_check))
    builder.add_node("confirm", confirm_node)
    builder.add_node("error", error_node)

    # Set entry point to think
    builder.set_entry_point("think")

    # Add edge from think to execute
    # (think produces tool calls, execute runs them)
    builder.add_edge("think", "execute")

    # Add conditional edges from execute
    # This is the main routing logic after tool execution
    builder.add_conditional_edges(
        "execute",
        _route_after_execute,
        {
            "think": "think",
            "verify": "verify",
            "confirm": "confirm",
            "error": "error",
            "end": END,
        },
    )

    # Add edges from verify back to think
    # (after verification, continue reasoning)
    builder.add_edge("verify", "think")

    # Add edges from confirm back to think
    # (after confirmation processed, continue or abort based on state.done)
    builder.add_edge("confirm", "think")

    # Add edges from error back to think
    # (after error processing, retry with error context)
    builder.add_edge("error", "think")

    # Compile with checkpointer and interrupt support
    compiled = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["confirm"],
    )

    # Add Langfuse tracing if configured
    langfuse_handler = get_langfuse_callback()
    if langfuse_handler:
        compiled = compiled.with_config({"callbacks": [langfuse_handler]})
        logger.debug("Langfuse tracing enabled for graph")

    logger.debug("Agent graph compiled successfully")

    return compiled


def run_agent(
    task: str,
    working_dir: str,
    llm_service: LLMServiceProtocol,
    tool_adapter: Optional[ToolAdapterProtocol] = None,
    checkpointer: Optional[MemorySaver] = None,
    thread_id: Optional[str] = None,
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
        llm_service: LLM service for completions
        tool_adapter: Tool adapter (default: create default)
        checkpointer: MemorySaver for checkpointing (default: create new)
        thread_id: Thread ID for checkpointing (default: generate UUID)

    Returns:
        Final AgentState after execution completes
    """
    # Create initial state
    initial_state = AgentState.create_initial(task, working_dir)

    # Build and compile graph
    graph = build_graph(
        llm_service=llm_service,
        tool_adapter=tool_adapter,
        checkpointer=checkpointer,
    )

    # Generate thread ID if not provided
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    # Config for checkpointing
    # Note: recursion_limit counts TOTAL node invocations, not iterations.
    # With think->execute pattern, each iteration = 2 nodes.
    # MAX_ITERATIONS (from edges.py) = 50, so need at least 100 nodes.
    # Set to 150 to allow for error recovery loops.
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 150,
    }

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
    llm_service: LLMServiceProtocol,
    tool_adapter: Optional[ToolAdapterProtocol] = None,
    run_mypy_check: bool = True,
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
        llm_service: LLM service for completions
        tool_adapter: Tool adapter (default: create default)
        run_mypy_check: Whether to run mypy in verify node

    Returns:
        Tuple of (compiled_graph, checkpointer)

    Example:
        graph, checkpointer = create_agent_runner(llm_service)
        config = {"configurable": {"thread_id": "my-session"}}

        # Start execution
        state = AgentState.create_initial(task, working_dir)
        result = graph.invoke(state, config)

        # Check if interrupted at confirm
        snapshot = graph.get_state(config)
        if snapshot.next == ("confirm",):
            # Handle confirmation
            user_response = get_user_confirmation()
            graph.update_state(config, {"confirmation_response": user_response})
            result = graph.invoke(None, config)  # Resume
    """
    checkpointer = MemorySaver()

    graph = build_graph(
        llm_service=llm_service,
        tool_adapter=tool_adapter,
        checkpointer=checkpointer,
        run_mypy_check=run_mypy_check,
    )

    return graph, checkpointer
