"""
Conversation persistence using SQLite.

Provides transparent, automatic conversation storage with token-budgeted
recall and staleness detection. Messages are persisted immediately to prevent
data loss on crashes.
"""

import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)

# Stale session threshold
STALE_THRESHOLD = timedelta(hours=4)

# ANSI escape sequence pattern (SGR, cursor movement, OSC sequences)
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\].*?\x07|\x1b[PX^_].*?\x1b\\')


def strip_ansi(text: str) -> str:
    """
    Remove ANSI escape codes from text before storage.

    Args:
        text: Text that may contain ANSI escape sequences

    Returns:
        Text with ANSI codes stripped
    """
    return ANSI_PATTERN.sub('', text)


def get_or_create_project_id(scrappy_dir: Path) -> str:
    """
    Load existing project ID or generate new one.

    Project IDs are UUIDs stored in .scrappy/config.json. They survive
    directory renames, moves, and symlink variations, providing stable
    project identity.

    Args:
        scrappy_dir: Path to .scrappy/ directory

    Returns:
        UUID string for this project
    """
    config_file = scrappy_dir / "config.json"

    if config_file.exists():
        try:
            with open(config_file) as f:
                data = json.load(f)
                return data["project_id"]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Corrupted config.json, generating new project ID: {e}")
            # Fall through to generate new ID

    # First run or corrupted config - generate new UUID
    project_id = str(uuid.uuid4())
    scrappy_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(config_file, "w") as f:
            json.dump({"project_id": project_id}, f)
    except OSError as e:
        logger.warning(f"Could not write config.json: {e}")
        # Continue with generated ID even if write fails

    return project_id


def check_session_staleness(last_message_time: Optional[datetime]) -> bool:
    """
    Returns True if session is stale (> 4 hours since last message).

    Args:
        last_message_time: UTC datetime of last message (timezone-aware)

    Returns:
        True if session is stale or no previous messages exist
    """
    if last_message_time is None:
        return False

    now_utc = datetime.now(timezone.utc)

    # Ensure last_message_time is timezone-aware
    if last_message_time.tzinfo is None:
        last_message_time = last_message_time.replace(tzinfo=timezone.utc)

    return now_utc - last_message_time > STALE_THRESHOLD


def format_stale_separator(last_time: datetime) -> str:
    """
    Format the visual separator for stale sessions.

    Converts UTC time to local time for display.

    Args:
        last_time: UTC datetime of last message

    Returns:
        Formatted separator string
    """
    local_time = last_time.replace(tzinfo=timezone.utc).astimezone()
    return f"--- Previous session ({local_time.strftime('%b %d, %I:%M %p')}) ---"


def get_stale_context_message() -> Dict[str, str]:
    """
    Get system message for stale session context.

    Used to inject context when loading conversation history from
    a previous session (>4 hours ago). Helps LLM understand that
    the user may be starting a new workflow.

    Returns:
        System message dict
    """
    return {
        "role": "system",
        "content": "Note: The following conversation happened in a previous session. The user may be starting a new workflow."
    }


class ConversationStoreProtocol(Protocol):
    """Protocol for conversation persistence."""

    def add_message(self, message: Dict[str, Any]) -> int:
        """
        Add a message to the conversation. Returns message ID.

        Args:
            message: Full message dict with 'role', 'content', and optionally
                    'tool_calls' (for assistant) or 'tool_call_id' (for tool role)

        Returns:
            Message ID (rowid) or -1 on failure
        """
        ...

    def get_recent(self, token_budget: int = 8000) -> List[Dict[str, Any]]:
        """
        Load recent messages up to token budget.

        Returns:
            List of message dicts with full structure (role, content, tool_calls, etc)
        """
        ...

    def get_last_message_time(self) -> Optional[datetime]:
        """Get timestamp of most recent message (for staleness check)."""
        ...

    def clear(self) -> None:
        """Clear all messages for current project."""
        ...

    def get_stats(self) -> Dict[str, Any]:
        """Return message count, token estimate, oldest/newest timestamps."""
        ...

    def close(self) -> None:
        """Close the database connection. Call on shutdown."""
        ...


class ConversationStore:
    """
    SQLite-backed conversation persistence.

    IMPORTANT: Use the create() factory method, not __init__ directly.

    This class provides transparent conversation storage with:
    - Immediate writes (no data loss on crash)
    - Token-budgeted recall (prevents context stuffing)
    - Staleness detection (4-hour threshold)
    - ANSI stripping (clean storage)
    - Graceful degradation (logs errors, doesn't crash)
    """

    def __init__(self, conn: sqlite3.Connection, project_id: str):
        """
        Assign dependencies only. No I/O here.

        Args:
            conn: Already-opened SQLite connection.
            project_id: UUID string identifying this project.
        """
        self._conn = conn
        self._project_id = project_id

    @classmethod
    def create(cls, scrappy_dir: Path) -> Optional["ConversationStore"]:
        """
        Factory method that handles I/O and initialization.

        Args:
            scrappy_dir: Path to .scrappy/ directory in project root.

        Returns:
            Initialized ConversationStore ready for use, or None on failure.
        """
        try:
            # Ensure .scrappy directory exists
            scrappy_dir.mkdir(parents=True, exist_ok=True)

            # Get or create project UUID
            project_id = get_or_create_project_id(scrappy_dir)

            # Open database with WAL mode for crash safety
            db_path = scrappy_dir / "conversations.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA journal_mode=WAL;")

            store = cls(conn, project_id)
            store._init_schema()
            return store

        except (sqlite3.Error, OSError) as e:
            logger.warning(f"Could not initialize conversation store: {e}")
            return None

    def _init_schema(self) -> None:
        """Initialize database schema with schema versioning."""
        try:
            # Create messages table with Phase 1.5 columns (nullable)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    tool_calls TEXT,
                    tool_call_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index for efficient project-scoped queries
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_project_time
                    ON messages(project_id, created_at DESC)
            """)

            # Schema versioning for future migrations
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
            """)
            self._conn.execute("""
                INSERT OR IGNORE INTO schema_version (version) VALUES (1)
            """)

            self._conn.commit()

        except sqlite3.Error as e:
            logger.warning(f"Schema initialization failed: {e}")
            # Don't raise - graceful degradation

    def add_message(self, message: Dict[str, Any]) -> int:
        """
        Insert message immediately. Returns message ID.

        Accepts full message dict (standard LLM format) and extracts:
        - role: 'user', 'assistant', 'tool', or 'system'
        - content: Message text (ANSI codes stripped before storage)
        - tool_calls: For assistant messages (JSON-serialized)
        - tool_call_id: For tool result messages

        System messages are skipped (app state, not conversation state).

        Args:
            message: Full message dict with 'role', 'content', and optionally
                    'tool_calls' (for assistant) or 'tool_call_id' (for tool role)

        Returns:
            Message ID (rowid) or -1 on failure
        """
        try:
            role = message.get("role")
            content = message.get("content")

            # Skip system messages (app state, not conversation state)
            if role == "system":
                return -1

            # Skip messages without a role
            if not role:
                logger.warning("Message missing 'role' field, skipping")
                return -1

            # Strip ANSI codes from content if present
            clean_content = strip_ansi(content) if content else None

            # Extract tool_calls and serialize to JSON (for assistant messages)
            tool_calls = message.get("tool_calls")
            tool_calls_json = json.dumps(tool_calls) if tool_calls else None

            # Extract tool_call_id (for tool result messages)
            tool_call_id = message.get("tool_call_id")

            # Insert with all fields
            cursor = self._conn.execute("""
                INSERT INTO messages (project_id, role, content, tool_calls, tool_call_id)
                VALUES (?, ?, ?, ?, ?)
            """, (self._project_id, role, clean_content, tool_calls_json, tool_call_id))

            self._conn.commit()
            return cursor.lastrowid

        except sqlite3.Error as e:
            logger.warning(f"Failed to persist message: {e}")
            return -1

    def get_recent(self, token_budget: int = 8000) -> List[Dict[str, Any]]:
        """
        Load messages up to token budget for current project.

        Works backwards from newest, accumulating until budget hit.
        Uses len(content) // 3 as token estimate (conservative for code).
        Always includes at least the most recent message, even if it
        exceeds the budget.

        IMPORTANT: Atomic turn boundaries (Phase 1.5)
        Never splits tool call sequences. A sequence is:
        [assistant w/tool_calls] -> [tool result(s)...] -> [assistant response]

        If budget would split a sequence, excludes the entire sequence.

        Args:
            token_budget: Maximum tokens to load (default: 8000)

        Returns:
            List of message dicts with full structure (role, content, tool_calls, etc)
        """
        try:
            cursor = self._conn.execute("""
                SELECT id, role, content, tool_calls, tool_call_id, created_at
                FROM messages
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
            """, (self._project_id,))

            rows = cursor.fetchall()

            # Work backwards, accumulating messages until budget hit
            # Track tool call sequences for atomic boundaries
            messages = []
            tokens_used = 0
            in_tool_sequence = False
            tool_sequence_start_idx = None
            hit_budget_limit = False

            for i, (msg_id, role, content, tool_calls_json, tool_call_id, created_at) in enumerate(rows):
                # Estimate tokens (conservative for code-heavy content)
                message_tokens = len(content or '') // 3

                # Reconstruct full message dict
                message = {'role': role}

                # Add content if present
                if content:
                    message['content'] = content

                # Reconstruct tool_calls from JSON (for assistant messages)
                if tool_calls_json:
                    try:
                        message['tool_calls'] = json.loads(tool_calls_json)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse tool_calls JSON for message {msg_id}")

                # Add tool_call_id (for tool result messages)
                if tool_call_id:
                    message['tool_call_id'] = tool_call_id

                # Always include the most recent message
                if i == 0:
                    messages.append(message)
                    tokens_used += message_tokens

                    # Check if we're starting inside a tool sequence
                    # If most recent message is a tool result or assistant with tool_calls, we're in a sequence
                    if role == 'tool' or (role == 'assistant' and tool_calls_json):
                        in_tool_sequence = True
                        tool_sequence_start_idx = 0

                    continue

                # Atomic turn boundary logic (Phase 1.5)
                # Track tool call sequences:
                # - tool result messages (role='tool') are part of a sequence
                # - assistant messages with tool_calls start a sequence
                # - assistant messages without tool_calls end a sequence

                if in_tool_sequence:
                    # We're in a tool sequence, must include this message
                    messages.append(message)
                    tokens_used += message_tokens

                    # Check if this message ends the sequence
                    if role == 'assistant' and tool_calls_json:
                        # This is the assistant message that initiated the tool calls
                        # Sequence is complete
                        in_tool_sequence = False
                        tool_sequence_start_idx = None
                    # If role is 'tool', continue the sequence (more tool results)
                    # If role is 'assistant' without tool_calls, this shouldn't happen
                    # (would mean incomplete sequence, but include it anyway)
                    elif role == 'assistant' and not tool_calls_json:
                        # Unexpected: assistant response without tool_calls inside sequence
                        # End sequence here
                        in_tool_sequence = False
                        tool_sequence_start_idx = None
                else:
                    # Not in a sequence, check budget
                    if tokens_used + message_tokens > token_budget:
                        # Would exceed budget
                        hit_budget_limit = True

                        # If this message starts a tool sequence, we can't include it
                        # Check if next messages (earlier in time) are tool results
                        if role == 'tool' or (role == 'assistant' and tool_calls_json):
                            # This is a tool result or tool call initiation, which means we're about to enter
                            # a sequence. We must exclude this and all following messages
                            # to maintain atomic boundary
                            break

                        # Otherwise, just stop here
                        break

                    # Add message
                    messages.append(message)
                    tokens_used += message_tokens

                    # Check if this message starts a new tool sequence
                    # (going backwards in time)
                    if role == 'tool' or (role == 'assistant' and tool_calls_json):
                        in_tool_sequence = True
                        tool_sequence_start_idx = len(messages) - 1

            # If we ended while in a tool sequence AND we hit the budget limit,
            # remove the partial sequence. If we just ran out of messages
            # (reached the oldest message), keep the partial sequence.
            if in_tool_sequence and tool_sequence_start_idx is not None and hit_budget_limit:
                # Remove all messages from sequence start to end
                messages = messages[:tool_sequence_start_idx]

            # Reverse to chronological order
            return list(reversed(messages))

        except sqlite3.Error as e:
            logger.warning(f"Failed to load recent messages: {e}")
            return []

    def get_last_message_time(self) -> Optional[datetime]:
        """
        Get timestamp of most recent message (for staleness check).

        Returns UTC datetime for consistent timezone handling.

        Returns:
            UTC datetime of last message, or None if no messages exist
        """
        try:
            cursor = self._conn.execute("""
                SELECT created_at
                FROM messages
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (self._project_id,))

            row = cursor.fetchone()
            if row is None:
                return None

            # Parse SQLite timestamp (UTC)
            timestamp_str = row[0]
            dt = datetime.fromisoformat(timestamp_str)

            # Ensure timezone-aware (SQLite CURRENT_TIMESTAMP is UTC)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt

        except (sqlite3.Error, ValueError) as e:
            logger.warning(f"Failed to get last message time: {e}")
            return None

    def clear(self) -> None:
        """Clear all messages for current project."""
        try:
            self._conn.execute("""
                DELETE FROM messages WHERE project_id = ?
            """, (self._project_id,))
            self._conn.commit()

        except sqlite3.Error as e:
            logger.warning(f"Failed to clear messages: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Return message count, token estimate, oldest/newest timestamps.

        Returns:
            Dict with 'message_count', 'estimated_tokens', 'oldest', 'newest' keys
        """
        try:
            cursor = self._conn.execute("""
                SELECT
                    COUNT(*) as count,
                    MIN(created_at) as oldest,
                    MAX(created_at) as newest,
                    SUM(LENGTH(COALESCE(content, ''))) as total_chars
                FROM messages
                WHERE project_id = ?
            """, (self._project_id,))

            row = cursor.fetchone()
            if row is None:
                return {
                    'message_count': 0,
                    'estimated_tokens': 0,
                    'oldest': None,
                    'newest': None
                }

            count, oldest, newest, total_chars = row

            return {
                'message_count': count or 0,
                'estimated_tokens': (total_chars or 0) // 3,
                'oldest': oldest,
                'newest': newest
            }

        except sqlite3.Error as e:
            logger.warning(f"Failed to get stats: {e}")
            return {
                'message_count': 0,
                'estimated_tokens': 0,
                'oldest': None,
                'newest': None
            }

    def close(self) -> None:
        """Close the database connection. Call on shutdown."""
        try:
            self._conn.close()
        except sqlite3.Error as e:
            logger.warning(f"Error closing database: {e}")
