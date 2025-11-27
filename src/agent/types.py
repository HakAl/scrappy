"""
Type definitions for the Code Agent.

Contains all dataclasses used in the agent's operation.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, TYPE_CHECKING

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
