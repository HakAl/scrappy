"""
LangGraph-based agent orchestration.

This module replaces the hand-rolled state machine in task_router/ and agent/
with a LangGraph StateGraph implementation.

Key components:
- state.py: AgentState Pydantic model
- tools.py: ToolAdapter for wrapping agent_tools registry
- nodes/: Graph node implementations (think, execute, verify, confirm, error)
- edges.py: Conditional routing logic
- agent.py: Graph assembly and entry point
- tracing.py: Langfuse observability integration
- persistence.py: ConversationStore integration helpers
"""

from scrappy.graph.agent import build_graph, create_agent_runner, run_agent
from scrappy.graph.persistence import (
    create_persistent_agent_state,
    load_history_into_state,
    persist_new_messages,
)
from scrappy.graph.tools import ToolAdapter, ToolAdapterProtocol

__all__ = [
    "ToolAdapter",
    "ToolAdapterProtocol",
    "build_graph",
    "create_agent_runner",
    "create_persistent_agent_state",
    "load_history_into_state",
    "persist_new_messages",
    "run_agent",
]
