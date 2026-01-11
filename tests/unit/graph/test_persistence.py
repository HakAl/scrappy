"""Tests for graph persistence integration."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from scrappy.graph.persistence import (
    create_persistent_agent_state,
    load_history_into_state,
    persist_new_messages,
)
from scrappy.graph.state import AgentState, Message
from scrappy.infrastructure.persistence import ConversationStoreProtocol


class FakeConversationStore:
    """Fake conversation store for testing."""

    def __init__(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        last_message_time: Optional[datetime] = None,
    ) -> None:
        self._messages = messages or []
        self._last_message_time = last_message_time
        self._added_messages: List[Dict[str, Any]] = []
        self._next_id = 1

    def get_recent(self, token_budget: int = 8000) -> List[Dict[str, Any]]:
        """Return stored messages."""
        return self._messages.copy()

    def get_last_message_time(self) -> Optional[datetime]:
        """Return configured last message time."""
        return self._last_message_time

    def add_message(self, message: Dict[str, Any]) -> int:
        """Record added message and return ID."""
        self._added_messages.append(message)
        msg_id = self._next_id
        self._next_id += 1
        return msg_id

    def clear(self) -> None:
        """Clear messages."""
        self._messages = []
        self._added_messages = []

    def get_stats(self) -> Dict[str, Any]:
        """Return stats."""
        return {"message_count": len(self._messages)}

    def close(self) -> None:
        """No-op close."""
        pass


class TestLoadHistoryIntoState:
    """Tests for load_history_into_state function."""

    def test_returns_empty_state_when_no_store(self) -> None:
        """Loading without store returns state with no messages."""
        state = load_history_into_state(
            conversation_store=None,
            task="test task",
            working_dir="/test/dir",
        )

        assert state.input == "test task"
        assert state.original_task == "test task"
        assert state.working_dir == "/test/dir"
        assert len(state.messages) == 0

    def test_returns_empty_state_when_store_empty(self) -> None:
        """Loading from empty store returns state with no messages."""
        store = FakeConversationStore(messages=[])

        state = load_history_into_state(
            conversation_store=store,
            task="test task",
            working_dir="/test/dir",
        )

        assert len(state.messages) == 0

    def test_loads_messages_from_store(self) -> None:
        """Messages from store are loaded into state."""
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        store = FakeConversationStore(
            messages=messages,
            last_message_time=datetime.now(timezone.utc),  # Recent, not stale
        )

        state = load_history_into_state(
            conversation_store=store,
            task="test task",
            working_dir="/test/dir",
        )

        assert len(state.messages) == 2
        assert state.messages[0]["role"] == "user"
        assert state.messages[0]["content"] == "hello"
        assert state.messages[1]["role"] == "assistant"
        assert state.messages[1]["content"] == "hi there"

    def test_injects_stale_message_when_session_stale(self) -> None:
        """Stale session injects context message before history."""
        messages = [
            {"role": "user", "content": "old message"},
        ]
        # 5 hours ago is stale (threshold is 4 hours)
        stale_time = datetime.now(timezone.utc) - timedelta(hours=5)
        store = FakeConversationStore(
            messages=messages,
            last_message_time=stale_time,
        )

        state = load_history_into_state(
            conversation_store=store,
            task="test task",
            working_dir="/test/dir",
        )

        # Should have stale message + original message
        assert len(state.messages) == 2
        assert state.messages[0]["role"] == "system"
        assert "previous session" in state.messages[0]["content"].lower()
        assert state.messages[1]["role"] == "user"
        assert state.messages[1]["content"] == "old message"

    def test_preserves_tool_calls_in_messages(self) -> None:
        """Tool calls are preserved when loading messages."""
        tool_calls = [{"type": "function", "id": "tc1", "function": {"name": "test_tool", "arguments": "{}"}}]
        messages = [
            {"role": "assistant", "content": "calling tool", "tool_calls": tool_calls},
            {"role": "tool", "content": "result", "tool_call_id": "tc1"},
        ]
        store = FakeConversationStore(
            messages=messages,
            last_message_time=datetime.now(timezone.utc),
        )

        state = load_history_into_state(
            conversation_store=store,
            task="test task",
            working_dir="/test/dir",
        )

        assert len(state.messages) == 2
        assert state.messages[0]["tool_calls"] == tool_calls
        assert state.messages[1]["tool_call_id"] == "tc1"

    def test_handles_store_exception_gracefully(self) -> None:
        """Exceptions from store are logged and empty state returned."""
        store = MagicMock(spec=ConversationStoreProtocol)
        store.get_recent.side_effect = Exception("Database error")

        state = load_history_into_state(
            conversation_store=store,
            task="test task",
            working_dir="/test/dir",
        )

        # Should return empty state, not raise
        assert len(state.messages) == 0


class TestPersistNewMessages:
    """Tests for persist_new_messages function."""

    def test_returns_zero_when_no_store(self) -> None:
        """Persisting without store returns 0."""
        state = AgentState(
            input="test",
            original_task="test",
            working_dir="/test",
            messages=[Message(role="user", content="hello")],
        )

        count = persist_new_messages(
            conversation_store=None,
            final_state=state,
            original_message_count=0,
        )

        assert count == 0

    def test_returns_zero_when_no_new_messages(self) -> None:
        """No new messages means nothing persisted."""
        store = FakeConversationStore()
        state = AgentState(
            input="test",
            original_task="test",
            working_dir="/test",
            messages=[Message(role="user", content="original")],
        )

        count = persist_new_messages(
            conversation_store=store,
            final_state=state,
            original_message_count=1,  # Same as current count
        )

        assert count == 0
        assert len(store._added_messages) == 0

    def test_persists_new_messages_only(self) -> None:
        """Only messages after original_message_count are persisted."""
        store = FakeConversationStore()
        state = AgentState(
            input="test",
            original_task="test",
            working_dir="/test",
            messages=[
                Message(role="user", content="original"),
                Message(role="assistant", content="response 1"),
                Message(role="user", content="followup"),
                Message(role="assistant", content="response 2"),
            ],
        )

        count = persist_new_messages(
            conversation_store=store,
            final_state=state,
            original_message_count=1,  # Only first message was original
        )

        assert count == 3
        assert len(store._added_messages) == 3
        assert store._added_messages[0]["content"] == "response 1"
        assert store._added_messages[1]["content"] == "followup"
        assert store._added_messages[2]["content"] == "response 2"

    def test_handles_add_message_failure(self) -> None:
        """Failures in add_message are logged but don't stop processing."""
        store = MagicMock(spec=ConversationStoreProtocol)
        store.add_message.side_effect = Exception("Insert failed")

        state = AgentState(
            input="test",
            original_task="test",
            working_dir="/test",
            messages=[
                Message(role="user", content="original"),
                Message(role="assistant", content="response"),
            ],
        )

        count = persist_new_messages(
            conversation_store=store,
            final_state=state,
            original_message_count=1,
        )

        # Should return 0 (failed) but not raise
        assert count == 0


class TestCreatePersistentAgentState:
    """Tests for create_persistent_agent_state convenience function."""

    def test_returns_state_and_message_count(self) -> None:
        """Returns tuple of state and original message count."""
        messages = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
        ]
        store = FakeConversationStore(
            messages=messages,
            last_message_time=datetime.now(timezone.utc),
        )

        state, count = create_persistent_agent_state(
            conversation_store=store,
            task="test task",
            working_dir="/test/dir",
        )

        assert state.input == "test task"
        assert len(state.messages) == 2
        assert count == 2

    def test_empty_store_returns_zero_count(self) -> None:
        """Empty store returns count of 0."""
        store = FakeConversationStore(messages=[])

        state, count = create_persistent_agent_state(
            conversation_store=store,
            task="test task",
            working_dir="/test/dir",
        )

        assert len(state.messages) == 0
        assert count == 0

    def test_stale_session_count_includes_stale_message(self) -> None:
        """Count includes the injected stale session message."""
        messages = [{"role": "user", "content": "old"}]
        stale_time = datetime.now(timezone.utc) - timedelta(hours=5)
        store = FakeConversationStore(
            messages=messages,
            last_message_time=stale_time,
        )

        state, count = create_persistent_agent_state(
            conversation_store=store,
            task="test task",
            working_dir="/test/dir",
        )

        # Stale message + original message
        assert len(state.messages) == 2
        assert count == 2

    def test_none_store_returns_empty_state(self) -> None:
        """None store returns empty state with count 0."""
        state, count = create_persistent_agent_state(
            conversation_store=None,
            task="test task",
            working_dir="/test/dir",
        )

        assert len(state.messages) == 0
        assert count == 0
