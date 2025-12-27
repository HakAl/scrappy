"""
Pydantic models for structured LLM responses.

These models define the expected output format for LLM calls,
enabling automatic validation and type safety.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """High-level task categories for execution routing."""

    DIRECT_COMMAND = "direct_command"    # Simple shell commands, no agent loop
    CODE_GENERATION = "code_generation"  # Full agent with planning and tools
    RESEARCH = "research"                # Fast provider, lightweight research
    CONVERSATION = "conversation"        # Simple Q&A, no execution needed


class TaskClassification(BaseModel):
    """
    Classifies the user intent into a task category.

    Used by the task router to determine which execution strategy
    should handle the user's request.

    Note: Field descriptions are used by Instructor as LLM context.
    Keep them short and factual. Behavioral instructions go in
    the system prompt, not here.
    """

    task_type: TaskType = Field(
        ...,
        description="RESEARCH, CODE_GENERATION, DIRECT_COMMAND, or CONVERSATION"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="0.0 to 1.0"
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation"
    )


class AgentAction(BaseModel):
    """
    Next action for the agent to take.

    Represents the agent's decision about what tool to use
    and with what parameters.
    """

    thought: str = Field(description="Reasoning about what to do next")
    tool: str = Field(description="Name of the tool to use")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Parameters to pass to the tool"
    )


class ResearchResult(BaseModel):
    """
    Result of a research/information gathering task.

    Used when the agent needs to gather and summarize information.
    """

    summary: str = Field(description="Summary of findings")
    sources: list[str] = Field(
        default_factory=list, description="List of sources consulted"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in the findings (0-1)"
    )
    follow_up_needed: bool = Field(
        default=False, description="Whether more research is needed"
    )
    follow_up_questions: list[str] = Field(
        default_factory=list, description="Questions that need answering"
    )


class CodeChangeResult(BaseModel):
    """
    Result of a code change operation.

    Used when the agent modifies code files.
    """

    files_changed: list[str] = Field(description="List of files that were modified")
    summary: str = Field(description="Summary of changes made")
    tests_needed: bool = Field(
        default=False, description="Whether new tests should be added"
    )
    review_notes: Optional[str] = Field(
        default=None, description="Notes for code review"
    )
