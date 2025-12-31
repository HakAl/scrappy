"""
LangGraph-based agent orchestration.

This module replaces the hand-rolled state machine in task_router/ and agent/
with a LangGraph StateGraph implementation.

Key components:
- state.py: AgentState Pydantic model
- nodes/: Graph node implementations (think, execute, verify, confirm, error)
- edges.py: Conditional routing logic
- agent.py: Graph assembly and entry point
- tracing.py: Langfuse observability integration
"""

# Entry point will be added in Task 1.8
# from .agent import run_agent
