"""
Confirm node for LangGraph agent.

Human-in-the-loop confirmation step using LangGraph's interrupt_before pattern.

This node works in tandem with graph compilation:
1. Graph is compiled with interrupt_before=["confirm"]
2. When graph reaches confirm node, it pauses BEFORE executing this node
3. CLI detects pause, reads state.pending_confirmation, prompts user
4. CLI calls graph.update_state() with confirmation_response
5. CLI resumes graph with graph.invoke(None, config)
6. THIS NODE then executes, processing the confirmation response

The node itself is simple - it just reads the response and updates state accordingly.
The "interrupt" is handled by LangGraph, not by this node.

Features:
- Processes confirmation responses after interrupt/resume cycle
- Supports command confirmation, file overwrite, etc.
- Handles denial (aborts or continues based on context)
- Clears pending_confirmation after processing
- Appends system message with confirmation result
- Langfuse tracing integration
"""

from typing import Literal, Optional

from scrappy.graph.state import AgentState, Message, PendingConfirmation
from scrappy.infrastructure.logging import get_logger

logger = get_logger(__name__)


# Confirmation types that abort the entire operation when denied
ABORT_ON_DENIAL_TYPES = frozenset({
    "command",
    "dangerous_command",
    "destructive_operation",
})


def format_confirmation_message(
    confirmation_type: str,
    confirmed: bool,
    details: Optional[PendingConfirmation] = None,
) -> str:
    """
    Format a human-readable message about the confirmation result.

    Args:
        confirmation_type: The type of confirmation (command, file_overwrite, etc.)
        confirmed: Whether the user confirmed or denied
        details: The full pending confirmation data

    Returns:
        Formatted message string
    """
    action = "confirmed" if confirmed else "denied"

    if confirmation_type == "command":
        command = details.get("command", "<unknown>") if details else "<unknown>"
        return f"User {action} command execution: {command}"

    elif confirmation_type == "dangerous_command":
        command = details.get("command", "<unknown>") if details else "<unknown>"
        return f"User {action} dangerous command: {command}"

    elif confirmation_type == "file_overwrite":
        file_path = details.get("file_path", "<unknown>") if details else "<unknown>"
        return f"User {action} file overwrite: {file_path}"

    elif confirmation_type == "destructive_operation":
        content = details.get("content", "<unknown>") if details else "<unknown>"
        return f"User {action} destructive operation: {content}"

    else:
        return f"User {action} {confirmation_type}"


def should_abort_on_denial(confirmation_type: str) -> bool:
    """
    Determine if denial of this confirmation type should abort the operation.

    Some operations (like file overwrite) can continue with a different approach.
    Others (like dangerous commands) should abort entirely.

    Args:
        confirmation_type: The type of confirmation

    Returns:
        True if denial should abort, False if operation can continue
    """
    return confirmation_type in ABORT_ON_DENIAL_TYPES


def build_denial_message(
    confirmation_type: str,
    details: Optional[PendingConfirmation] = None,
) -> Message:
    """
    Build a system message for when user denies a confirmation.

    Args:
        confirmation_type: The type of confirmation that was denied
        details: The full pending confirmation data

    Returns:
        System message explaining the denial
    """
    formatted = format_confirmation_message(confirmation_type, False, details)

    if should_abort_on_denial(confirmation_type):
        content = f"{formatted}. Operation aborted."
    else:
        content = f"{formatted}. Please try a different approach."

    return Message(role="system", content=content)


def build_confirmation_message(
    confirmation_type: str,
    details: Optional[PendingConfirmation] = None,
) -> Message:
    """
    Build a system message for when user confirms.

    Args:
        confirmation_type: The type of confirmation
        details: The full pending confirmation data

    Returns:
        System message noting the confirmation
    """
    formatted = format_confirmation_message(confirmation_type, True, details)
    return Message(role="system", content=f"{formatted}. Proceeding.")


def confirm_node(state: AgentState) -> AgentState:
    """
    Confirm node - processes human confirmation response.

    This node executes AFTER the interrupt/resume cycle:
    1. Graph was paused BEFORE this node (interrupt_before)
    2. CLI prompted user and got response
    3. CLI called graph.update_state() with confirmation_response
    4. CLI resumed graph with graph.invoke(None, config)
    5. NOW this node executes

    The node reads confirmation_response and pending_confirmation from state,
    then updates state accordingly:
    - If confirmed: clear pending, continue execution
    - If denied: clear pending, potentially abort (set done=True)

    Args:
        state: Current agent state with confirmation_response set

    Returns:
        Updated AgentState with confirmation processed
    """
    pending = state.pending_confirmation
    response = state.confirmation_response

    # No pending confirmation - nothing to do
    if pending is None:
        logger.debug("confirm_node: No pending confirmation, passing through")
        return state

    # Response not yet provided (shouldn't happen after resume, but be defensive)
    # This can occur if:
    # 1. Graph resumed without calling update_state() with confirmation_response
    # 2. State serialization/deserialization lost confirmation_response
    # 3. Race condition in HITL handling
    # Treating as denial is safe - user can retry if needed.
    if response is None:
        confirmation_type = pending.get("type", "unknown")
        logger.warning(
            "confirm_node: pending_confirmation (type=%s) exists but no confirmation_response. "
            "This may indicate the graph resumed without updating state. "
            "Treating as denial for safety. Pending details: %s",
            confirmation_type,
            pending,
        )
        # Treat as denial for safety
        response = False

    confirmation_type = pending.get("type", "unknown")
    logger.info(
        "confirm_node: Processing %s confirmation, response=%s",
        confirmation_type,
        "confirmed" if response else "denied",
    )

    # Build result message
    if response:
        result_message = build_confirmation_message(confirmation_type, pending)
    else:
        result_message = build_denial_message(confirmation_type, pending)

    # Determine if we should abort
    should_abort = not response and should_abort_on_denial(confirmation_type)

    # Build updated messages list
    new_messages = list(state.messages)
    new_messages.append(result_message)

    # Clear confirmation state and update
    # Use explicit type annotation to avoid mypy inference issues with mixed types
    update_dict: dict[str, object] = {
        "pending_confirmation": None,
        "confirmation_response": None,
        "messages": new_messages,
    }

    if should_abort:
        logger.info("confirm_node: Aborting due to denial of %s", confirmation_type)
        update_dict["done"] = True

    return state.model_copy(update=update_dict)  # type: ignore[arg-type]


def create_pending_confirmation(
    confirmation_type: Literal["command", "dangerous_command", "file_overwrite", "destructive_operation"],
    *,
    command: Optional[str] = None,
    file_path: Optional[str] = None,
    content: Optional[str] = None,
) -> PendingConfirmation:
    """
    Create a PendingConfirmation structure for requesting user confirmation.

    This is a helper for other nodes that need to trigger confirmation.
    They set pending_confirmation in state, and the graph routes to confirm node.

    Args:
        confirmation_type: Type of confirmation needed
        command: Command string (for command/dangerous_command types)
        file_path: File path (for file_overwrite type)
        content: Description of operation (for destructive_operation type)

    Returns:
        PendingConfirmation dict ready to be set in state

    Example:
        # In execute node, before running dangerous command:
        pending = create_pending_confirmation(
            "dangerous_command",
            command="rm -rf /tmp/data",
        )
        return state.model_copy(update={"pending_confirmation": pending})
    """
    pending: PendingConfirmation = {"type": confirmation_type}

    if command is not None:
        pending["command"] = command
    if file_path is not None:
        pending["file_path"] = file_path
    if content is not None:
        pending["content"] = content

    return pending
