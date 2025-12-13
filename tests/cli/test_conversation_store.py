"""
Tests for conversation_store.py - Conversation persistence.

Tests verify behavior of conversation storage operations:
- Adding messages and persistence
- Retrieving recent messages with token budget
- Staleness detection
- Error handling and graceful degradation
- ANSI stripping
"""

import pytest
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.scrappy.cli.conversation_store import (
    ConversationStore,
    strip_ansi,
    get_or_create_project_id,
    check_session_staleness,
    format_stale_separator,
    STALE_THRESHOLD,
)


class TestStripAnsi:
    """Tests for ANSI escape code stripping."""

    def test_strips_color_codes(self):
        """Should remove SGR color codes from text."""
        text = "\x1b[32mGreen text\x1b[0m"
        result = strip_ansi(text)
        assert result == "Green text"

    def test_strips_multiple_color_codes(self):
        """Should remove all color codes from text with multiple codes."""
        text = "\x1b[31mRed\x1b[0m and \x1b[32mGreen\x1b[0m"
        result = strip_ansi(text)
        assert result == "Red and Green"

    def test_strips_cursor_movement_codes(self):
        """Should remove cursor movement codes."""
        text = "\x1b[2JCleared\x1b[H"
        result = strip_ansi(text)
        assert result == "Cleared"

    def test_preserves_plain_text(self):
        """Should leave plain text unchanged."""
        text = "No ANSI codes here"
        result = strip_ansi(text)
        assert result == "No ANSI codes here"

    def test_handles_empty_string(self):
        """Should handle empty string without error."""
        result = strip_ansi("")
        assert result == ""

    def test_strips_complex_sequences(self):
        """Should handle complex ANSI sequences with parameters."""
        text = "\x1b[1;31;40mBold Red on Black\x1b[0m"
        result = strip_ansi(text)
        assert result == "Bold Red on Black"


class TestGetOrCreateProjectId:
    """Tests for project ID generation and persistence."""

    def test_creates_new_project_id_when_no_config_exists(self):
        """Should generate new UUID when config.json doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            project_id = get_or_create_project_id(scrappy_dir)

            # Should be a valid UUID format
            assert len(project_id) == 36
            assert project_id.count('-') == 4

    def test_creates_config_file_with_project_id(self):
        """Should write project_id to config.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            project_id = get_or_create_project_id(scrappy_dir)

            config_file = scrappy_dir / "config.json"
            assert config_file.exists()

            import json
            with open(config_file) as f:
                data = json.load(f)
                assert data["project_id"] == project_id

    def test_returns_existing_project_id_when_config_exists(self):
        """Should return existing project_id from config.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            scrappy_dir.mkdir(parents=True)

            # Create config with known project ID
            import json
            config_file = scrappy_dir / "config.json"
            expected_id = "12345678-1234-1234-1234-123456789abc"
            with open(config_file, "w") as f:
                json.dump({"project_id": expected_id}, f)

            # Should return existing ID
            project_id = get_or_create_project_id(scrappy_dir)
            assert project_id == expected_id

    def test_generates_new_id_when_config_corrupted(self):
        """Should generate new ID when config.json is corrupted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            scrappy_dir.mkdir(parents=True)

            # Create corrupted config
            config_file = scrappy_dir / "config.json"
            with open(config_file, "w") as f:
                f.write("invalid json{")

            # Should generate new ID
            project_id = get_or_create_project_id(scrappy_dir)
            assert len(project_id) == 36

    def test_generates_new_id_when_config_missing_project_id_key(self):
        """Should generate new ID when config.json doesn't have project_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            scrappy_dir.mkdir(parents=True)

            # Create config without project_id key
            import json
            config_file = scrappy_dir / "config.json"
            with open(config_file, "w") as f:
                json.dump({"other_key": "value"}, f)

            # Should generate new ID
            project_id = get_or_create_project_id(scrappy_dir)
            assert len(project_id) == 36


class TestCheckSessionStaleness:
    """Tests for session staleness detection."""

    def test_returns_false_when_no_last_message(self):
        """Should return False when there are no previous messages."""
        result = check_session_staleness(None)
        assert result is False

    def test_returns_true_when_last_message_over_threshold(self):
        """Should return True when last message is older than 4 hours."""
        last_time = datetime.now(timezone.utc) - timedelta(hours=5)
        result = check_session_staleness(last_time)
        assert result is True

    def test_returns_false_when_last_message_within_threshold(self):
        """Should return False when last message is within 4 hours."""
        last_time = datetime.now(timezone.utc) - timedelta(hours=2)
        result = check_session_staleness(last_time)
        assert result is False

    def test_handles_exact_threshold_boundary(self):
        """Should handle the exact 4-hour boundary correctly."""
        # Just over threshold
        last_time = datetime.now(timezone.utc) - STALE_THRESHOLD - timedelta(seconds=1)
        assert check_session_staleness(last_time) is True

        # Just under threshold
        last_time = datetime.now(timezone.utc) - STALE_THRESHOLD + timedelta(seconds=1)
        assert check_session_staleness(last_time) is False

    def test_handles_naive_datetime(self):
        """Should handle naive datetime by assuming UTC."""
        # Naive datetime (no timezone)
        last_time = datetime.now() - timedelta(hours=5)
        result = check_session_staleness(last_time)
        # Should still work (treats as UTC)
        assert isinstance(result, bool)


class TestFormatStaleSeparator:
    """Tests for stale session separator formatting."""

    def test_formats_separator_with_date_and_time(self):
        """Should format separator with readable date and time."""
        last_time = datetime(2024, 12, 10, 14, 30, tzinfo=timezone.utc)
        result = format_stale_separator(last_time)

        assert "Previous session" in result
        assert "Dec 10" in result
        # Time will be in local timezone, just verify format structure
        assert "---" in result

    def test_includes_dashes_for_visual_separation(self):
        """Should include dashes for visual separation."""
        last_time = datetime.now(timezone.utc)
        result = format_stale_separator(last_time)

        assert result.startswith("---")
        assert result.endswith("---")


class TestConversationStoreCreate:
    """Tests for ConversationStore factory method."""

    def test_create_returns_store_instance(self):
        """Should return ConversationStore instance on success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            assert store is not None
            assert isinstance(store, ConversationStore)
            store.close()

    def test_create_initializes_database(self):
        """Should create database file in .scrappy directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            db_path = scrappy_dir / "conversations.db"
            assert db_path.exists()
            store.close()

    def test_create_creates_messages_table(self):
        """Should create messages table with correct schema."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Verify table exists and has correct columns
            cursor = store._conn.execute("PRAGMA table_info(messages)")
            columns = {row[1] for row in cursor.fetchall()}

            assert "id" in columns
            assert "project_id" in columns
            assert "role" in columns
            assert "content" in columns
            assert "created_at" in columns

            store.close()

    def test_create_creates_schema_version_table(self):
        """Should create schema_version table for migrations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Verify schema version table exists
            cursor = store._conn.execute(
                "SELECT version FROM schema_version"
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == 1

            store.close()


class TestConversationStoreAddMessage:
    """Tests for adding messages to conversation store."""

    def test_add_message_returns_message_id(self):
        """Should return positive message ID on successful insert."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            msg_id = store.add_message("user", "Hello")
            assert msg_id > 0

            store.close()

    def test_add_message_persists_to_database(self):
        """Should persist message to database immediately."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            store.add_message("user", "Test message")

            # Verify message is in database
            cursor = store._conn.execute(
                "SELECT role, content FROM messages WHERE project_id = ?",
                (store._project_id,)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "user"
            assert row[1] == "Test message"

            store.close()

    def test_add_message_strips_ansi_codes(self):
        """Should strip ANSI codes before storing content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            store.add_message("assistant", "\x1b[32mGreen text\x1b[0m")

            # Verify ANSI codes are stripped
            cursor = store._conn.execute(
                "SELECT content FROM messages WHERE project_id = ?",
                (store._project_id,)
            )
            row = cursor.fetchone()
            assert row[0] == "Green text"

            store.close()

    def test_add_message_stores_user_role(self):
        """Should store user role messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            msg_id = store.add_message("user", "User input")
            assert msg_id > 0

            store.close()

    def test_add_message_stores_assistant_role(self):
        """Should store assistant role messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            msg_id = store.add_message("assistant", "Assistant response")
            assert msg_id > 0

            store.close()

    def test_add_message_skips_system_role(self):
        """Should skip system role messages and return -1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            msg_id = store.add_message("system", "System message")
            assert msg_id == -1

            # Verify no message was stored
            cursor = store._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE project_id = ?",
                (store._project_id,)
            )
            count = cursor.fetchone()[0]
            assert count == 0

            store.close()

    def test_add_message_skips_tool_role(self):
        """Should skip tool role messages and return -1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            msg_id = store.add_message("tool", "Tool result")
            assert msg_id == -1

            store.close()

    def test_add_message_handles_empty_content(self):
        """Should handle empty content without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            msg_id = store.add_message("user", "")
            assert msg_id > 0

            store.close()

    def test_add_message_increments_message_id(self):
        """Should increment message ID for each new message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            id1 = store.add_message("user", "First")
            id2 = store.add_message("assistant", "Second")
            id3 = store.add_message("user", "Third")

            assert id2 > id1
            assert id3 > id2

            store.close()


class TestConversationStoreGetRecent:
    """Tests for retrieving recent messages with token budget."""

    def test_get_recent_returns_empty_list_when_no_messages(self):
        """Should return empty list when no messages exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            messages = store.get_recent()
            assert messages == []

            store.close()

    def test_get_recent_returns_all_messages_within_budget(self):
        """Should return all messages when they fit within token budget."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            store.add_message("user", "Hello")
            store.add_message("assistant", "Hi there")
            store.add_message("user", "How are you?")

            messages = store.get_recent(token_budget=8000)
            store.close()

            assert len(messages) == 3
            # Messages returned in chronological order (oldest first)
            assert messages[0]["content"] == "Hello"
            assert messages[1]["content"] == "Hi there"
            assert messages[2]["content"] == "How are you?"

    def test_get_recent_limits_by_token_budget(self):
        """Should stop loading messages when token budget is exceeded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Add messages with known sizes
            # Each message ~10 chars = ~3 tokens
            for i in range(10):
                store.add_message("user", f"Message {i}")

            # Very small budget - should only get most recent
            messages = store.get_recent(token_budget=5)

            # Should at least get the most recent message
            assert len(messages) >= 1
            # Should not get all messages
            assert len(messages) < 10

            store.close()

    def test_get_recent_always_includes_most_recent_message(self):
        """Should always include most recent message even if it exceeds budget."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Add a very large message
            large_message = "x" * 10000  # ~3333 tokens
            store.add_message("user", large_message)

            # Budget smaller than message
            messages = store.get_recent(token_budget=100)

            # Should still include the message
            assert len(messages) == 1
            assert messages[0]["content"] == large_message

            store.close()

    def test_get_recent_returns_chronological_order(self):
        """Should return messages in chronological order (oldest first)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            store.add_message("user", "First")
            store.add_message("assistant", "Second")
            store.add_message("user", "Third")

            messages = store.get_recent()
            store.close()

            # Messages returned in chronological order (oldest first)
            # ORDER BY created_at DESC, id DESC ensures correct ordering
            # even when timestamps are identical
            assert messages[0]["content"] == "First"
            assert messages[1]["content"] == "Second"
            assert messages[2]["content"] == "Third"

    def test_get_recent_uses_conservative_token_estimate(self):
        """Should use len(content) // 3 for token estimation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # 900 chars = ~300 tokens
            msg1 = "x" * 900
            # 600 chars = ~200 tokens
            msg2 = "y" * 600

            store.add_message("user", msg1)
            store.add_message("user", msg2)

            # Budget of 250 tokens should fit one message but not both
            messages = store.get_recent(token_budget=250)
            store.close()

            # ORDER BY created_at DESC, id DESC returns newest (msg2) first
            # msg2 is always included (200 tokens)
            # msg1 would add 300 tokens, exceeding budget, so excluded
            assert len(messages) == 1
            assert messages[0]["content"] == msg2

    def test_get_recent_filters_by_project_id(self):
        """Should only return messages for current project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Add message for current project
            store.add_message("user", "My message")

            # Manually add message for different project
            store._conn.execute(
                "INSERT INTO messages (project_id, role, content) VALUES (?, ?, ?)",
                ("other-project-id", "user", "Other message")
            )
            store._conn.commit()

            messages = store.get_recent()

            # Should only get current project's message
            assert len(messages) == 1
            assert messages[0]["content"] == "My message"

            store.close()


class TestConversationStoreGetLastMessageTime:
    """Tests for retrieving last message timestamp."""

    def test_get_last_message_time_returns_none_when_no_messages(self):
        """Should return None when no messages exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            last_time = store.get_last_message_time()
            assert last_time is None

            store.close()

    def test_get_last_message_time_returns_datetime(self):
        """Should return datetime object for most recent message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            store.add_message("user", "Test")

            last_time = store.get_last_message_time()
            assert isinstance(last_time, datetime)

            store.close()

    def test_get_last_message_time_is_timezone_aware(self):
        """Should return timezone-aware datetime in UTC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            store.add_message("user", "Test")

            last_time = store.get_last_message_time()
            assert last_time.tzinfo is not None
            assert last_time.tzinfo == timezone.utc

            store.close()

    def test_get_last_message_time_returns_most_recent(self):
        """Should return timestamp of most recent message, not oldest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            import time

            store.add_message("user", "First")
            time.sleep(0.01)  # Small delay to ensure different timestamps
            store.add_message("user", "Second")

            last_time = store.get_last_message_time()

            # Verify it's very recent (within last second)
            now = datetime.now(timezone.utc)
            diff = now - last_time
            assert diff.total_seconds() < 1

            store.close()


class TestConversationStoreClear:
    """Tests for clearing conversation history."""

    def test_clear_removes_all_messages(self):
        """Should remove all messages for current project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            store.add_message("user", "Message 1")
            store.add_message("assistant", "Message 2")
            store.add_message("user", "Message 3")

            store.clear()

            messages = store.get_recent()
            assert messages == []

            store.close()

    def test_clear_only_affects_current_project(self):
        """Should only clear messages for current project, not others."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Add message for current project
            store.add_message("user", "My message")

            # Add message for different project
            store._conn.execute(
                "INSERT INTO messages (project_id, role, content) VALUES (?, ?, ?)",
                ("other-project-id", "user", "Other message")
            )
            store._conn.commit()

            store.clear()

            # Current project messages should be gone
            messages = store.get_recent()
            assert messages == []

            # Other project messages should still exist
            cursor = store._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE project_id = ?",
                ("other-project-id",)
            )
            count = cursor.fetchone()[0]
            assert count == 1

            store.close()

    def test_clear_allows_new_messages_after_clearing(self):
        """Should allow adding new messages after clearing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            store.add_message("user", "Before clear")
            store.clear()
            store.add_message("user", "After clear")

            messages = store.get_recent()
            assert len(messages) == 1
            assert messages[0]["content"] == "After clear"

            store.close()


class TestConversationStoreGetStats:
    """Tests for conversation statistics."""

    def test_get_stats_returns_zero_counts_when_empty(self):
        """Should return zero counts when no messages exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            stats = store.get_stats()

            assert stats["message_count"] == 0
            assert stats["estimated_tokens"] == 0
            assert stats["oldest"] is None
            assert stats["newest"] is None

            store.close()

    def test_get_stats_counts_messages(self):
        """Should count total messages for current project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            store.add_message("user", "Message 1")
            store.add_message("assistant", "Message 2")
            store.add_message("user", "Message 3")

            stats = store.get_stats()
            assert stats["message_count"] == 3

            store.close()

    def test_get_stats_estimates_tokens(self):
        """Should estimate tokens using len(content) // 3."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # 300 chars = ~100 tokens
            store.add_message("user", "x" * 300)
            # 600 chars = ~200 tokens
            store.add_message("assistant", "y" * 600)

            stats = store.get_stats()
            # Total = 900 chars = ~300 tokens
            assert stats["estimated_tokens"] == 300

            store.close()

    def test_get_stats_includes_oldest_timestamp(self):
        """Should include timestamp of oldest message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            import time

            store.add_message("user", "First")
            time.sleep(0.01)
            store.add_message("user", "Second")

            stats = store.get_stats()
            assert stats["oldest"] is not None

            store.close()

    def test_get_stats_includes_newest_timestamp(self):
        """Should include timestamp of newest message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            store.add_message("user", "Test")

            stats = store.get_stats()
            assert stats["newest"] is not None

            store.close()


class TestConversationStoreErrorHandling:
    """Tests for error handling and graceful degradation."""

    def test_add_message_returns_negative_on_error(self):
        """Should return -1 on database error without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Close connection to trigger error
            store._conn.close()

            msg_id = store.add_message("user", "This will fail")
            assert msg_id == -1

    def test_get_recent_returns_empty_on_error(self):
        """Should return empty list on database error without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Close connection to trigger error
            store._conn.close()

            messages = store.get_recent()
            assert messages == []

    def test_get_last_message_time_returns_none_on_error(self):
        """Should return None on database error without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Close connection to trigger error
            store._conn.close()

            last_time = store.get_last_message_time()
            assert last_time is None

    def test_get_stats_returns_zero_stats_on_error(self):
        """Should return zero stats on database error without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Close connection to trigger error
            store._conn.close()

            stats = store.get_stats()
            assert stats["message_count"] == 0
            assert stats["estimated_tokens"] == 0

    def test_clear_handles_error_gracefully(self):
        """Should handle errors during clear without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Close connection to trigger error
            store._conn.close()

            # Should not raise exception
            store.clear()

    def test_close_handles_error_gracefully(self):
        """Should handle errors during close without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Close twice to trigger error on second close
            store.close()
            store.close()  # Should not raise


class TestConversationStoreOrderingBug:
    """Tests demonstrating the ordering bug when timestamps are identical.

    BUG: get_recent() uses ORDER BY created_at DESC without id, causing
    non-deterministic ordering when messages share the same timestamp.

    EXPECTED: Messages should be returned in chronological order (oldest first)
    after the reverse operation, meaning insertion order should be preserved.

    ACTUAL: When timestamps are identical, SQLite returns rows in arbitrary
    order, breaking the chronological guarantee.
    """

    def test_get_recent_should_return_chronological_order_with_same_timestamps(self):
        """BUG: Messages with identical timestamps return in wrong order.

        This test inserts messages with the exact same timestamp to prove
        that the current implementation fails to maintain insertion order.

        The fix is to change the query from:
            ORDER BY created_at DESC
        to:
            ORDER BY created_at DESC, id DESC

        This ensures deterministic ordering even when timestamps collide.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Insert messages with IDENTICAL timestamps directly via SQL
            # This simulates rapid message insertion within the same second
            fixed_timestamp = "2024-12-10 10:00:00"

            store._conn.execute(
                "INSERT INTO messages (project_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (store._project_id, "user", "First message", fixed_timestamp)
            )
            store._conn.execute(
                "INSERT INTO messages (project_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (store._project_id, "assistant", "Second message", fixed_timestamp)
            )
            store._conn.execute(
                "INSERT INTO messages (project_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (store._project_id, "user", "Third message", fixed_timestamp)
            )
            store._conn.commit()

            messages = store.get_recent()
            store.close()

            # EXPECTED behavior: chronological order (oldest first)
            # After querying DESC and reversing, we should get:
            # [First, Second, Third]

            assert len(messages) == 3

            # With ORDER BY created_at DESC, id DESC, messages are returned
            # in correct chronological order (oldest first)
            assert messages[0]["content"] == "First message"
            assert messages[1]["content"] == "Second message"
            assert messages[2]["content"] == "Third message"

    def test_demonstrates_fix_with_id_ordering(self):
        """Demonstrates that adding ORDER BY id DESC fixes the bug.

        This test manually queries with the correct ordering to show
        what the expected behavior should be.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"
            store = ConversationStore.create(scrappy_dir)

            # Insert messages with identical timestamps
            fixed_timestamp = "2024-12-10 10:00:00"

            store._conn.execute(
                "INSERT INTO messages (project_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (store._project_id, "user", "First", fixed_timestamp)
            )
            store._conn.execute(
                "INSERT INTO messages (project_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (store._project_id, "assistant", "Second", fixed_timestamp)
            )
            store._conn.execute(
                "INSERT INTO messages (project_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (store._project_id, "user", "Third", fixed_timestamp)
            )
            store._conn.commit()

            # Query with the CORRECT ordering (what the fix should use)
            cursor = store._conn.execute("""
                SELECT role, content
                FROM messages
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
            """, (store._project_id,))

            rows = cursor.fetchall()

            # With id DESC, newest id comes first: Third, Second, First
            # After reversing (as get_recent does), we get: First, Second, Third
            messages = [{"role": r[0], "content": r[1]} for r in reversed(rows)]

            store.close()

            # This is the CORRECT chronological order
            assert messages[0]["content"] == "First"
            assert messages[1]["content"] == "Second"
            assert messages[2]["content"] == "Third"


class TestConversationStoreMultipleProjects:
    """Tests for multi-project isolation."""

    def test_different_projects_have_different_ids(self):
        """Should generate different project IDs for different directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir1 = Path(tmpdir) / "project1" / ".scrappy"
            scrappy_dir2 = Path(tmpdir) / "project2" / ".scrappy"

            store1 = ConversationStore.create(scrappy_dir1)
            store2 = ConversationStore.create(scrappy_dir2)

            assert store1._project_id != store2._project_id

            store1.close()
            store2.close()

    def test_projects_share_database_but_isolated_data(self):
        """Should allow multiple projects to share database file with isolated data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"

            # Create two stores pointing to same database
            store1 = ConversationStore.create(scrappy_dir)
            project_id_1 = store1._project_id
            store1.add_message("user", "Project 1 message")
            store1.close()

            # Create new store with different project ID
            # (Simulate by directly creating with different project_id)
            conn = sqlite3.connect(str(scrappy_dir / "conversations.db"))
            store2 = ConversationStore(conn, "different-project-id")
            store2.add_message("user", "Project 2 message")

            # Each should only see their own messages
            messages1_conn = sqlite3.connect(str(scrappy_dir / "conversations.db"))
            store1_check = ConversationStore(messages1_conn, project_id_1)
            messages1 = store1_check.get_recent()

            messages2 = store2.get_recent()

            assert len(messages1) == 1
            assert messages1[0]["content"] == "Project 1 message"

            assert len(messages2) == 1
            assert messages2[0]["content"] == "Project 2 message"

            store1_check.close()
            store2.close()


class TestConversationHistoryRestoration:
    """Tests for conversation history restoration on startup.

    Verifies that conversation history is properly loaded from the store
    when creating a new session, enabling "Scrappy remembers" functionality.
    """

    def test_history_persists_across_store_instances(self):
        """History should be retrievable after store is closed and reopened.

        This simulates the startup scenario where we need to load
        previous conversation history from disk.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"

            # First session: add messages
            store1 = ConversationStore.create(scrappy_dir)
            store1.add_message("user", "Hello from first session")
            store1.add_message("assistant", "Hi there!")
            store1.add_message("user", "How are you?")
            store1.close()

            # Second session: load history (simulates app restart)
            store2 = ConversationStore.create(scrappy_dir)
            loaded_history = store2.get_recent(token_budget=8000)
            store2.close()

            # Should have all 3 messages in chronological order
            assert len(loaded_history) == 3
            assert loaded_history[0]["content"] == "Hello from first session"
            assert loaded_history[1]["content"] == "Hi there!"
            assert loaded_history[2]["content"] == "How are you?"

    def test_history_restoration_respects_token_budget(self):
        """Restoration should respect token budget, loading most recent messages.

        When conversation history exceeds token budget, only the most
        recent messages (up to budget) should be loaded.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"

            # First session: add many messages
            store1 = ConversationStore.create(scrappy_dir)
            for i in range(20):
                # Each message ~100 chars = ~33 tokens
                store1.add_message("user", f"Message {i}: " + "x" * 90)
            store1.close()

            # Second session: load with small budget
            store2 = ConversationStore.create(scrappy_dir)
            # Budget of 100 tokens should only fit ~3 messages
            loaded_history = store2.get_recent(token_budget=100)
            store2.close()

            # Should have fewer than all messages
            assert len(loaded_history) < 20
            # Should have at least 1 (most recent always included)
            assert len(loaded_history) >= 1
            # Most recent message should be included
            assert "Message 19" in loaded_history[-1]["content"]

    def test_new_messages_appended_to_restored_history(self):
        """New messages should be appended after restored history.

        Verifies that the conversation continues naturally after restoration.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            scrappy_dir = Path(tmpdir) / ".scrappy"

            # First session
            store1 = ConversationStore.create(scrappy_dir)
            store1.add_message("user", "First session message")
            store1.close()

            # Second session: load and add more
            store2 = ConversationStore.create(scrappy_dir)
            loaded = store2.get_recent()
            assert len(loaded) == 1

            # Add new message in second session
            store2.add_message("user", "Second session message")
            store2.close()

            # Third session: should see both
            store3 = ConversationStore.create(scrappy_dir)
            all_messages = store3.get_recent()
            store3.close()

            assert len(all_messages) == 2
            assert all_messages[0]["content"] == "First session message"
            assert all_messages[1]["content"] == "Second session message"
