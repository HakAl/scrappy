"""
Control tools for agent loop management.

These tools control agent behavior (completion, etc.) rather than
performing actions on the codebase.
"""

from .base import ToolBase, ToolParameter, ToolResult, ToolContext


class CompleteTool(ToolBase):
    """Tool to signal task completion."""

    @property
    def name(self) -> str:
        return "complete"

    @property
    def description(self) -> str:
        return "Mark the task as complete and provide final result."

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("result", str, "Final result or summary of completed task")
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        return ToolResult(True, kwargs["result"], metadata={"stop_loop": True})
