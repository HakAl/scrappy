"""
Persistence integration for LangGraph agent.

Bridges ConversationStore (SQLite persistence) with AgentState (graph state).
Provides helpers to load history at start and persist new messages after runs.

Usage:
    from scrappy.graph.persistence import load_history_into_state, persist_new_messages

    # Load history into initial state
    state = load_history_into_state(conversation_store, task, working_dir)

    # Run agent...
    result = run_agent(...)

    # Persist new messages (those added during this run)
    persist_new_messages(conversation_store, result, original_message_count)
"""

from typing import Optional

from scrappy.graph.state import AgentState, Message
from scrappy.infrastructure.logging import get_logger
from scrappy.persistence import (
    ConversationStoreProtocol,
    check_session_staleness,
    get_stale_context_message,
)

logger = get_logger(__name__)


def load_history_into_state(
    conversation_store: Optional[ConversationStoreProtocol],
    task: str,
    working_dir: str,
    token_budget: int = 8000,
) -> AgentState:
    """
    Create initial AgentState with conversation history loaded.

    Loads recent messages from ConversationStore (if available) and
    creates an initial state with that history. Handles staleness
    detection and injects context message if session is stale.

    Args:
        conversation_store: Optional ConversationStore for history loading
        task: The user's task/query
        working_dir: Working directory for file operations
        token_budget: Max tokens for history loading (default: 8000)

    Returns:
        AgentState with messages populated from history
    """
    messages: list[Message] = []
    is_stale = False

    if conversation_store is not None:
        try:
            # Load recent messages within token budget
            loaded = conversation_store.get_recent(token_budget=token_budget)

            if loaded:
                # Check staleness
                last_time = conversation_store.get_last_message_time()
                if check_session_staleness(last_time):
                    is_stale = True
                    # Inject system message about stale context
                    stale_msg = get_stale_context_message()
                    messages.append({
                        "role": stale_msg["role"],
                        "content": stale_msg["content"],
                    })
                    logger.info("Session is stale, injected context message")

                # Add loaded history
                for msg in loaded:
                    message: Message = {
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", ""),
                    }
                    # Only add optional fields if present (NotRequired in TypedDict)
                    if msg.get("tool_calls"):
                        message["tool_calls"] = msg["tool_calls"]
                    if msg.get("tool_call_id"):
                        message["tool_call_id"] = msg["tool_call_id"]
                    messages.append(message)

                logger.info(
                    "Loaded %d messages from conversation history (stale=%s)",
                    len(loaded),
                    is_stale,
                )

        except (OSError, IOError) as e:
            # Storage/file system errors - expected for persistence layer
            logger.warning("Storage error loading conversation history: %s", e)
            # Continue with empty history
        except (TypeError, ValueError, KeyError) as e:
            # Data parsing/serialization errors - expected for message handling
            logger.warning("Data error loading conversation history: %s", e)
            # Continue with empty history
        except Exception as e:
            # Unexpected error - log with type for debugging
            logger.warning("Unexpected error loading conversation history: %s: %s", type(e).__name__, e)
            # Continue with empty history

    # Create initial state with loaded messages
    return AgentState(
        input=task,
        original_task=task,
        working_dir=working_dir,
        messages=messages,
    )


def persist_new_messages(
    conversation_store: Optional[ConversationStoreProtocol],
    final_state: AgentState,
    original_message_count: int,
) -> int:
    """
    Persist new messages from agent run to ConversationStore.

    Only persists messages added during this run (after original_message_count).
    This avoids re-persisting messages that were already in the store.

    Args:
        conversation_store: ConversationStore for persistence (or None to skip)
        final_state: Final AgentState after agent run
        original_message_count: Number of messages before agent run started

    Returns:
        Number of messages persisted
    """
    if conversation_store is None:
        return 0

    new_messages = final_state.messages[original_message_count:]
    persisted_count = 0

    for msg in new_messages:
        try:
            # Convert Message TypedDict to dict for ConversationStore
            msg_dict = dict(msg)
            result = conversation_store.add_message(msg_dict)
            if result > 0:
                persisted_count += 1
        except (OSError, IOError) as e:
            # Storage/file system errors - expected for persistence layer
            logger.warning("Storage error persisting message: %s", e)
        except (TypeError, ValueError, KeyError) as e:
            # Data serialization errors - expected for message handling
            logger.warning("Data error persisting message: %s", e)
        except Exception as e:
            # Unexpected error - log with type for debugging
            logger.warning("Unexpected error persisting message: %s: %s", type(e).__name__, e)

    if persisted_count > 0:
        logger.info("Persisted %d new messages to conversation store", persisted_count)

    return persisted_count


def create_persistent_agent_state(
    conversation_store: Optional[ConversationStoreProtocol],
    task: str,
    working_dir: str,
    token_budget: int = 8000,
) -> tuple[AgentState, int]:
    """
    Create initial state with history and return message count for later persistence.

    Convenience function that combines load_history_into_state with tracking
    the original message count for persist_new_messages.

    Args:
        conversation_store: Optional ConversationStore
        task: The user's task/query
        working_dir: Working directory for file operations
        token_budget: Max tokens for history loading

    Returns:
        Tuple of (initial_state, original_message_count)

    Example:
        store = ConversationStore.create(scrappy_dir)
        state, count = create_persistent_agent_state(store, task, working_dir)

        # Run agent
        result = run_agent_with_state(state, ...)

        # Persist new messages
        persist_new_messages(store, result, count)
    """
    state = load_history_into_state(
        conversation_store=conversation_store,
        task=task,
        working_dir=working_dir,
        token_budget=token_budget,
    )
    return state, len(state.messages)
