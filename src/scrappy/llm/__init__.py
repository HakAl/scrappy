"""
Structured LLM output models.

Provides Pydantic models for structured LLM responses.
"""

from scrappy.llm.models import (
    TaskType,
    TaskClassification,
    AgentAction,
    ResearchResult,
    CodeChangeResult,
)

__all__ = [
    "TaskType",
    "TaskClassification",
    "AgentAction",
    "ResearchResult",
    "CodeChangeResult",
]
