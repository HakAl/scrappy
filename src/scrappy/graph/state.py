"""
Agent state model for LangGraph orchestration.

This Pydantic model represents the complete state of the agent during execution.
It is designed to be:
- Fully JSON-serializable (for SqliteSaver persistence)
- Immutable-friendly (LangGraph prefers state updates via new instances)
- Comprehensive (captures all context needed for any node)
"""

from typing import Any, Literal, Optional
from typing_extensions import NotRequired, TypedDict
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FunctionCall(TypedDict):
    """Function details within a tool call (OpenAI format)."""

    name: str
    arguments: str


class ToolCall(TypedDict):
    """
    OpenAI-format tool call structure.

    This matches the standard format used by OpenAI, Groq, Cerebras, and other
    LLM providers. Using the standard format avoids conversion bugs and ensures
    messages can be sent directly to any provider.

    Example:
        {
            "type": "function",
            "id": "call_abc123",
            "function": {
                "name": "read_file",
                "arguments": "{\"path\": \"/tmp/foo.txt\"}"
            }
        }
    """

    type: str  # Always "function" for now
    id: str
    function: FunctionCall


class Message(TypedDict):
    """OpenAI-format message structure."""

    role: str
    content: str
    tool_calls: NotRequired[list[ToolCall]]
    tool_call_id: NotRequired[str]


class PendingConfirmation(TypedDict):
    """Data awaiting human confirmation."""

    type: str
    command: NotRequired[str]
    file_path: NotRequired[str]
    content: NotRequired[str]


class ToolResult(TypedDict):
    """Result of a tool execution."""

    name: str
    result: NotRequired[str]
    error: NotRequired[str]
    metadata: NotRequired[dict[str, object]]


class AgentState(BaseModel):
    """
    Complete state of the LangGraph agent.

    This state is passed between nodes and persisted at checkpoints.
    All fields must be JSON-serializable for SqliteSaver compatibility.

    Attributes:
        input: Current user input being processed
        original_task: Preserved original task (unchanged during execution)
        messages: Conversation history as list of message dicts
        iteration: Current iteration count (safety limit)
        done: Whether the agent has completed its task
        error_count: Number of consecutive errors (for retry logic)
        last_error: Last error message (for error node context)
        current_tier: Model tier being used ("fast" or "quality")
        files_changed: List of file paths modified in this session
        working_dir: Current working directory for file operations
        checkpoint: Optional checkpoint identifier for resumption
        pending_confirmation: Data for human-in-the-loop confirmation
        tool_results: Recent tool execution results (separate from messages)
    """

    # Core - what we're working on
    input: str = Field(
        description="Current user input being processed"
    )
    original_task: str = Field(
        description="Preserved original task, unchanged during execution"
    )
    messages: list[Message] = Field(
        default_factory=list,
        description="Conversation history as OpenAI-format message dicts"
    )

    # Execution tracking
    iteration: int = Field(
        default=0,
        description="Current iteration count for safety limits"
    )
    done: bool = Field(
        default=False,
        description="Whether the agent has completed its task"
    )
    error_count: int = Field(
        default=0,
        description="Number of consecutive errors for retry logic"
    )
    last_error: Optional[str] = Field(
        default=None,
        description="Last error message for error node context"
    )

    # Model selection
    current_tier: Literal["fast", "quality"] = Field(
        default="quality",
        description="Model tier: 'fast' for speed, 'quality' for complex tasks (default: quality for better tool following)"
    )

    # File tracking
    files_changed: list[str] = Field(
        default_factory=list,
        description="List of file paths modified in this session"
    )
    files_verified: bool = Field(
        default=True,
        description="Whether files_changed have been verified (resets to False when files change)"
    )
    working_dir: str = Field(
        default=".",
        description="Current working directory for file operations"
    )

    @field_validator("working_dir")
    @classmethod
    def validate_working_dir(cls, v: str) -> str:
        """Validate working_dir is a non-empty string."""
        if not v or not v.strip():
            raise ValueError("working_dir cannot be empty or whitespace-only")
        return v

    # Checkpointing
    checkpoint: Optional[str] = Field(
        default=None,
        description="Optional checkpoint identifier for session resumption"
    )

    # Human-in-the-loop
    pending_confirmation: Optional[PendingConfirmation] = Field(
        default=None,
        description="Data awaiting human confirmation (command, file overwrite, etc.)"
    )
    confirmation_response: Optional[bool] = Field(
        default=None,
        description="Response to pending_confirmation (True=confirmed, False=denied, None=pending)"
    )

    # Tool results (separate from messages for easier access)
    tool_results: list[ToolResult] = Field(
        default_factory=list,
        description="Recent tool execution results"
    )

    # Pending tool calls for UX display (set by execute node)
    pending_tool_calls: list[ToolCall] = Field(
        default_factory=list,
        description="Tool calls from last assistant message, for UX display"
    )

    # Pydantic configuration
    model_config = ConfigDict(
        # Keep strict for JSON serialization (no arbitrary types)
        arbitrary_types_allowed=False,
        # Validate on assignment for safety
        validate_assignment=True,
    )

    def model_dump_json_safe(self) -> dict[str, Any]:
        """
        Dump state to a JSON-safe dictionary.

        This ensures all nested structures are JSON-serializable,
        which is required for SqliteSaver persistence.

        Returns:
            JSON-serializable dictionary representation of state
        """
        return self.model_dump(mode="json")

    @classmethod
    def create_initial(cls, task: str, working_dir: str = ".") -> "AgentState":
        """
        Create initial state for a new agent run.

        Args:
            task: The user's task/query
            working_dir: Working directory for file operations

        Returns:
            Fresh AgentState ready for execution
        """
        return cls(
            input=task,
            original_task=task,
            working_dir=working_dir,
        )
