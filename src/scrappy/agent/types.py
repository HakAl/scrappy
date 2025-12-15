"""
Type definitions for the Code Agent.

Contains all dataclasses used in the agent's operation.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..providers.base import LLMResponse


@dataclass
class AgentThought:
    """Result from the thinking stage (LLM response)."""
    raw_response: str
    provider: str
    iteration: int
    llm_response: Optional['LLMResponse'] = None  # Full response for native tool calls


@dataclass
class AgentAction:
    """Parsed action from the planning stage."""
    thought: str
    action: str
    parameters: Dict[str, object]
    is_complete: bool
    result_text: str = ""  # For completion results


@dataclass
class ActionResult:
    """Result from executing an action."""
    success: bool
    output: str
    action: str
    parameters: Dict[str, object]
    approved: bool
    executed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """Result from evaluating whether task is complete."""
    is_complete: bool
    should_continue: bool
    reason: str
    final_result: Optional[str] = None


@dataclass
class DenialHandlerResult:
    """Result from handling a user denial."""
    should_stop: bool
    message: str


@dataclass
class ConversationState:
    """Encapsulates the conversation state for the agent loop."""
    messages: List[Dict[str, str]] = field(default_factory=list)
    system_prompt: str = ""
    iteration: int = 0
    max_iterations: int = 10
    tools_executed: List[str] = field(default_factory=list)
    auto_confirm: bool = False
    # Track failed commands to force different strategies
    failed_commands: List[Dict[str, str]] = field(default_factory=list)  # List of {command, error, approach}
    retry_warnings: List[str] = field(default_factory=list)  # Warnings to inject into next prompt
    # Track action history for duplicate detection
    action_history: List[Dict[str, object]] = field(default_factory=list)  # List of {action, parameters}
    last_action: Optional[Dict[str, object]] = None  # Most recent action for quick duplicate check


@dataclass
class AgentContext:
    """Context for agent execution including system prompt and passive RAG data."""
    system_prompt: str
    active_tools: List[str]
    passive_rag_context: Optional[str] = None


@dataclass
class AgentEvent:
    """
    Streaming event from agent execution.

    During streaming agent execution, various events are emitted to provide
    real-time visibility into the agent's operation: thinking (LLM streaming),
    action execution, evaluation, and completion.

    Event types:
        - "thought_start": Agent begins thinking phase
        - "thought_token": Streaming token from LLM during thinking
        - "thought_end": Agent completes thinking phase
        - "action_start": Agent begins executing an action
        - "action_end": Agent completes action execution
        - "evaluation_start": Agent begins evaluating task completion
        - "evaluation_end": Agent completes evaluation
        - "complete": Agent task is complete
        - "error": Error occurred during execution

    Attributes:
        event_type: Type of event (see above)
        content: Text content for this event (tokens, messages, results)
        iteration: Current iteration number
        metadata: Additional event-specific data (action names, success flags, etc.)
    """
    event_type: str
    content: str = ""
    iteration: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
