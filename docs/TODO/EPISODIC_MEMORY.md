# Phase 2: Episodic Memory (Smart Recall)

## Problem

For long conversations (500+ messages), loading recent history via token budget isn't enough. Users ask things like:
- "What was that curl command from earlier?"
- "What did we discuss yesterday about auth?"
- "Remember when we fixed the config issue?"

Current system only loads last ~8k tokens. Older context is lost.

## Solution

Episodic memory: vector-indexed conversation history with hybrid search (semantic + keyword), separate from codebase RAG to prevent pollution.

---

## Architecture Overview

```
                    +------------------+
                    |  ConversationStore  |  (SQLite - Phase 1/1.5)
                    |  - messages table   |
                    |  - indexed_at col   |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
              v                             v
+-------------+------------+    +-----------+-----------+
| Short-term Memory        |    | Long-term Memory      |
| (Active Context)         |    | (Episodic RAG)        |
+---------------------------+    +-----------------------+
| - Token-budgeted recall  |    | - LanceDB table:      |
| - Last ~20 messages      |    |   conversation_chunks |
| - Loaded on startup      |    | - Hybrid search       |
+---------------------------+    | - Temporal filtering  |
                                +-----------------------+
                                           |
                                           v
                              +------------+------------+
                              | RecallConversationTool  |
                              | - Agent can search past |
                              | - FTS + Vector hybrid   |
                              +-------------------------+
```

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector DB | LanceDB (existing) | Already integrated, hybrid search works |
| Namespace | Separate table `conversation_chunks` | Prevents codebase RAG pollution |
| Chunking | Enriched Q+A pairs | Context-aware, not orphaned snippets |
| Consolidation trigger | On conversation close | Not during active session |
| Hybrid search | RRF merge (vector + FTS) | Best of semantic + exact match |
| Temporal filtering | Timestamp metadata in LanceDB | Enables "yesterday", "last week" queries |
| Fallback | FTS-only if vector unavailable | Graceful degradation |

---

## Protocols (Define First)

```python
# src/scrappy/cli/episodic_memory/protocols.py

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Protocol, Set


class TimeRange(Enum):
    """Supported time range filters for episodic search."""
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_WEEK = "last_week"
    LAST_MONTH = "last_month"
    ALL_TIME = "all_time"


@dataclass
class ConversationChunk:
    """A chunk of conversation history for embedding."""
    id: str                      # "project_id:msg_start_id:msg_end_id"
    project_id: str
    timestamp: float             # Unix timestamp of first message in chunk
    content: str                 # Enriched text (see chunking strategy)
    context_summary: str         # "Topic: auth, Files: main.py, config.py"
    message_ids: List[int]       # Source message IDs for traceability


@dataclass
class EpisodicSearchResult:
    """Result from episodic memory search."""
    chunks: List[Dict]           # [{content, timestamp, score, context_summary}]
    search_type: str             # "hybrid", "vector_only", "fts_only"
    query: str


@dataclass
class ConsolidationResult:
    """Result from memory consolidation."""
    chunks_created: int
    messages_processed: int
    already_indexed: int
    errors: List[str]


class ConversationChunkerProtocol(Protocol):
    """
    Chunks conversation messages into embeddable units.

    Unlike code chunking, conversation chunking must:
    - Group Q+A pairs (never orphan a question from its answer)
    - Enrich with context (active files, topics discussed)
    - Handle tool call sequences as atomic units
    """

    def chunk(
        self,
        messages: List[Dict],
        project_id: str,
    ) -> List[ConversationChunk]:
        """
        Chunk messages into embeddable conversation units.

        Args:
            messages: List of message dicts from ConversationStore
            project_id: Project identifier for chunk IDs

        Returns:
            List of ConversationChunk objects ready for embedding
        """
        ...


class EpisodicMemoryProtocol(Protocol):
    """
    Vector storage for conversation history.

    Separate from codebase semantic search to prevent pollution.
    Supports hybrid search (vector + FTS) with temporal filtering.
    """

    def index_chunks(self, chunks: List[ConversationChunk]) -> int:
        """
        Index conversation chunks into vector DB.

        Args:
            chunks: Chunks to index

        Returns:
            Number of chunks successfully indexed
        """
        ...

    def search(
        self,
        query: str,
        time_range: Optional[TimeRange] = None,
        max_results: int = 10,
    ) -> EpisodicSearchResult:
        """
        Search episodic memory with optional temporal filtering.

        Args:
            query: Search query (semantic + keyword)
            time_range: Optional time filter
            max_results: Maximum chunks to return

        Returns:
            EpisodicSearchResult with ranked chunks
        """
        ...

    def is_indexed(self) -> bool:
        """Check if episodic memory has any indexed content."""
        ...

    def clear(self) -> None:
        """Clear all episodic memory for current project."""
        ...


class MemoryConsolidatorProtocol(Protocol):
    """
    Consolidates conversation history into episodic memory.

    Reads unindexed messages from SQLite, chunks them,
    embeds them, and marks them as indexed.
    """

    def consolidate(self) -> ConsolidationResult:
        """
        Consolidate unindexed messages into episodic memory.

        Should be called on conversation close, not during active session.

        Returns:
            ConsolidationResult with stats
        """
        ...

    def get_unindexed_count(self) -> int:
        """Get count of messages not yet indexed."""
        ...
```

---

## Schema Changes

### SQLite Addition (marker column)

```sql
-- Migration: Add indexed_at column to track what's been embedded
ALTER TABLE messages ADD COLUMN indexed_at TIMESTAMP;

-- Index for efficient "get unindexed" queries
CREATE INDEX IF NOT EXISTS idx_messages_unindexed
    ON messages(project_id, indexed_at)
    WHERE indexed_at IS NULL;
```

### LanceDB Schema (new table)

```python
class ConversationChunkSchema(LanceModel):
    """Schema for conversation chunks in LanceDB."""
    id: str                    # "project_id:msg_start:msg_end"
    project_id: str            # For multi-project filtering
    timestamp: float           # Unix timestamp for temporal queries
    content: str               # Enriched chunk text
    context_summary: str       # Brief context description
    message_ids: str           # JSON array of source message IDs
    vector: Vector(384)        # Same 384-dim as codebase (BGE-small)
```

---

## Chunking Strategy (Enriched Q+A Pairs)

### The Problem: Lost Context

Raw chunking loses context:
```
# BAD: Orphaned chunk
"IndexError on line 5"
# Embedding is vague - what file? what context?
```

### Solution: Enriched Chunks

```python
class ConversationChunker:
    """
    Chunks conversations into context-rich embeddable units.

    Strategy:
    1. Group by conversation turns (User Q + Assistant A)
    2. Keep tool call sequences atomic
    3. Prepend context summary to each chunk
    4. Skip very short/empty exchanges
    """

    MIN_CHUNK_LENGTH = 50  # Skip trivial exchanges
    MAX_CHUNK_LENGTH = 2000  # Prevent huge chunks

    def chunk(
        self,
        messages: List[Dict],
        project_id: str,
    ) -> List[ConversationChunk]:
        chunks = []
        current_turn = []
        current_context = ConversationContext()

        for msg in messages:
            # Track context (files mentioned, topics)
            current_context.update(msg)

            # Only flush when USER speaks AFTER ASSISTANT (not on every user message)
            # This prevents orphaned chunks when user sends consecutive messages
            is_user = msg['role'] == 'user'
            last_was_assistant = current_turn and current_turn[-1]['role'] != 'user'

            if is_user and last_was_assistant:
                # Flush the completed Q+A pair
                chunk = self._create_chunk(current_turn, current_context, project_id)
                if chunk:
                    chunks.append(chunk)
                # Start new turn
                current_turn = [msg]
            else:
                # Append to current buffer (groups consecutive user msgs or assistant+tool runs)
                current_turn.append(msg)

        # Flush final turn
        if current_turn:
            chunk = self._create_chunk(current_turn, current_context, project_id)
            if chunk:
                chunks.append(chunk)

        return chunks

    def _create_chunk(
        self,
        turn: List[Dict],
        context: ConversationContext,
        project_id: str,
    ) -> Optional[ConversationChunk]:
        """Create enriched chunk from a conversation turn."""

        # Build content with context prefix
        content_parts = []

        # Add context header if available
        if context.active_files or context.topics:
            header = self._format_context_header(context)
            content_parts.append(header)

        # Add messages
        for msg in turn:
            role = msg['role'].upper()
            text = msg.get('content', '')
            if text:
                content_parts.append(f"{role}: {text}")

            # Include tool calls summary (not full JSON)
            if msg.get('tool_calls'):
                tools = [tc['function']['name'] for tc in msg['tool_calls']]
                content_parts.append(f"[Tools used: {', '.join(tools)}]")

        content = '\n'.join(content_parts)

        # Skip if too short
        if len(content) < self.MIN_CHUNK_LENGTH:
            return None

        # Truncate if too long
        if len(content) > self.MAX_CHUNK_LENGTH:
            content = content[:self.MAX_CHUNK_LENGTH] + "..."

        # Extract message IDs
        msg_ids = [m.get('id') for m in turn if m.get('id')]

        return ConversationChunk(
            id=f"{project_id}:{msg_ids[0]}:{msg_ids[-1]}" if msg_ids else f"{project_id}:{uuid4()}",
            project_id=project_id,
            timestamp=turn[0].get('created_at', time.time()),
            content=content,
            context_summary=context.summarize(),
            message_ids=msg_ids,
        )

    def _format_context_header(self, context: ConversationContext) -> str:
        """Format context as chunk header."""
        parts = []
        if context.active_files:
            parts.append(f"Files: {', '.join(context.active_files[:3])}")
        if context.topics:
            parts.append(f"Topic: {', '.join(context.topics[:2])}")
        return f"[Context: {'; '.join(parts)}]" if parts else ""


class ConversationContext:
    """Tracks conversation context for chunk enrichment."""

    def __init__(self):
        self.active_files: Set[str] = set()
        self.topics: Set[str] = set()

    def update(self, message: Dict) -> None:
        """Extract context signals from message."""
        content = message.get('content', '')

        # Extract file paths mentioned
        file_patterns = re.findall(r'[\w/\\]+\.\w{1,5}', content)
        self.active_files.update(file_patterns[-5:])  # Keep recent

        # Extract topics from tool calls
        if message.get('tool_calls'):
            for tc in message['tool_calls']:
                name = tc.get('function', {}).get('name', '')
                if name:
                    self.topics.add(name.replace('_', ' '))

    def summarize(self) -> str:
        """Create brief context summary."""
        parts = []
        if self.active_files:
            parts.append(f"Files: {', '.join(list(self.active_files)[:3])}")
        if self.topics:
            parts.append(f"Topics: {', '.join(list(self.topics)[:3])}")
        return "; ".join(parts) if parts else "General discussion"
```

---

## Hybrid Search with RRF

Reuse existing RRF pattern from LanceDB provider:

```python
class EpisodicMemoryProvider:
    """
    LanceDB-based episodic memory with hybrid search.

    Reuses existing infrastructure:
    - Same EmbeddingFunctionProtocol (FastEmbed)
    - Same hybrid search pattern
    - Same file locking
    """

    TABLE_NAME = "conversation_chunks"

    def __init__(
        self,
        project_path: Path,
        embedding_func: Optional[EmbeddingFunctionProtocol] = None,
    ):
        self._project_path = project_path
        self._db_path = project_path / ".scrappy" / "lancedb"
        self._embedding_func = embedding_func
        self._db = None

    def search(
        self,
        query: str,
        time_range: Optional[TimeRange] = None,
        max_results: int = 10,
    ) -> EpisodicSearchResult:
        """
        Hybrid search: vector similarity + FTS keyword matching.

        Uses Reciprocal Rank Fusion to merge results.
        """
        self._ensure_db()

        if not self._table_exists():
            return EpisodicSearchResult(chunks=[], search_type="none", query=query)

        table = self._db.open_table(self.TABLE_NAME)

        # Generate query embedding
        query_vector = self._embedding_func.generate_embeddings([query])[0]

        # Build search with optional temporal filter
        search = table.search(query_vector, query_type="hybrid").text(query)

        if time_range and time_range != TimeRange.ALL_TIME:
            timestamp_filter = self._time_range_to_filter(time_range)
            search = search.where(timestamp_filter)

        try:
            results = search.limit(max_results).to_list()
            search_type = "hybrid"
        except Exception as e:
            # Fallback to vector-only if FTS fails
            logger.warning(f"Hybrid search failed ({e}), falling back to vector")
            results = table.search(query_vector, query_type="vector").limit(max_results).to_list()
            search_type = "vector_only"

        chunks = [
            {
                'content': r['content'],
                'timestamp': r['timestamp'],
                'score': r.get('_score', 0.0),
                'context_summary': r['context_summary'],
            }
            for r in results
        ]

        return EpisodicSearchResult(chunks=chunks, search_type=search_type, query=query)

    def _time_range_to_filter(self, time_range: TimeRange) -> str:
        """Convert TimeRange enum to LanceDB filter expression."""
        now = time.time()

        thresholds = {
            TimeRange.TODAY: now - 86400,           # 24 hours
            TimeRange.YESTERDAY: now - 172800,      # 48 hours
            TimeRange.LAST_WEEK: now - 604800,      # 7 days
            TimeRange.LAST_MONTH: now - 2592000,    # 30 days
        }

        threshold = thresholds.get(time_range, 0)
        return f"timestamp > {threshold}"
```

---

## Memory Consolidator

```python
class MemoryConsolidator:
    """
    Consolidates conversation history into episodic memory.

    Lifecycle:
    1. Called on conversation close (not during active session)
    2. Reads unindexed messages from SQLite
    3. Chunks into Q+A pairs with context enrichment
    4. Embeds and stores in LanceDB
    5. Marks messages as indexed in SQLite
    """

    def __init__(
        self,
        conversation_store: ConversationStoreProtocol,
        episodic_memory: EpisodicMemoryProtocol,
        chunker: ConversationChunkerProtocol,
    ):
        self._store = conversation_store
        self._memory = episodic_memory
        self._chunker = chunker

    def consolidate(self) -> ConsolidationResult:
        """Consolidate unindexed messages into episodic memory."""
        errors = []

        # 1. Get unindexed messages
        unindexed = self._store.get_unindexed_messages()

        if not unindexed:
            return ConsolidationResult(
                chunks_created=0,
                messages_processed=0,
                already_indexed=0,
                errors=[],
            )

        # 2. Chunk messages
        try:
            chunks = self._chunker.chunk(unindexed, self._store.project_id)
        except Exception as e:
            errors.append(f"Chunking failed: {e}")
            return ConsolidationResult(0, 0, 0, errors)

        # 3. Index chunks
        try:
            indexed_count = self._memory.index_chunks(chunks)
        except Exception as e:
            errors.append(f"Indexing failed: {e}")
            return ConsolidationResult(0, len(unindexed), 0, errors)

        # 4. Mark messages as indexed
        message_ids = [m['id'] for m in unindexed if m.get('id')]
        try:
            self._store.mark_as_indexed(message_ids)
        except Exception as e:
            errors.append(f"Failed to mark indexed: {e}")

        return ConsolidationResult(
            chunks_created=indexed_count,
            messages_processed=len(unindexed),
            already_indexed=0,
            errors=errors,
        )
```

---

## RecallConversationTool (Agent Interface)

```python
class RecallConversationTool(BaseTool):
    """
    Agent tool for searching conversation history.

    Provides two modes:
    1. Semantic search: "What did we discuss about authentication?"
    2. Recent fetch: "Show me the last 5 messages"
    """

    name = "recall_conversation"
    description = """Search past conversation history for relevant context.

Use this when you need to:
- Find a command or code snippet from earlier in the conversation
- Recall what was discussed about a topic
- Reference earlier decisions or context

Arguments:
- query: What to search for (semantic search)
- time_range: Optional filter - "today", "yesterday", "last_week", "last_month"
- last_n: Instead of search, get the N most recent messages
"""

    def __init__(
        self,
        episodic_memory: EpisodicMemoryProtocol,
        conversation_store: ConversationStoreProtocol,
    ):
        self._memory = episodic_memory
        self._store = conversation_store

    def execute(
        self,
        ctx: ToolContext,
        query: Optional[str] = None,
        time_range: Optional[str] = None,
        last_n: Optional[int] = None,
    ) -> ToolResult:
        # Mode 1: Recent messages (direct SQLite fetch)
        if last_n:
            messages = self._store.get_recent(limit=last_n)
            return ToolResult(
                success=True,
                output=self._format_messages(messages),
            )

        # Mode 2: Semantic search
        if not query:
            return ToolResult(
                success=False,
                output="Either 'query' or 'last_n' is required",
            )

        # Parse time range
        time_filter = None
        if time_range:
            try:
                time_filter = TimeRange(time_range.lower())
            except ValueError:
                pass  # Ignore invalid, search all time

        # Search BOTH indexed (vector DB) AND unindexed (current session)
        # This closes the "active context gap" where recent messages aren't indexed yet

        # 1. Search unindexed messages first (current session, not yet consolidated)
        active_matches = self._search_active_session(query)

        # 2. Search indexed history if available
        if self._memory.is_indexed():
            history_result = self._memory.search(query, time_range=time_filter)
            history_chunks = history_result.chunks
        else:
            history_chunks = []

        # 3. Merge results (active session first for recency)
        if not active_matches and not history_chunks:
            return ToolResult(
                success=True,
                output=f"No relevant conversation history found for: {query}",
            )

        return ToolResult(
            success=True,
            output=self._format_merged_results(active_matches, history_chunks),
        )

    def _search_active_session(self, query: str) -> List[Dict]:
        """Search unindexed messages (current session, not yet consolidated)."""
        # Use efficient SQL LIKE search instead of loading all into memory
        return self._store.search_text(query, limit=5)

    def _format_merged_results(
        self,
        active: List[Dict],
        history: List[Dict],
    ) -> str:
        """Format merged results from active session and history."""
        lines = []

        if active:
            lines.append(f"=== Current Session ({len(active)} matches) ===\n")
            lines.append(self._format_messages(active))
            lines.append("")

        if history:
            lines.append(f"=== History ({len(history)} matches) ===\n")
            for i, chunk in enumerate(history, 1):
                timestamp = datetime.fromtimestamp(chunk['timestamp'])
                lines.append(f"--- [{i}] {timestamp.strftime('%b %d, %H:%M')} ---")
                lines.append(f"Context: {chunk['context_summary']}")
                lines.append(chunk['content'])
                lines.append("")

        return '\n'.join(lines)

    def _format_search_results(self, result: EpisodicSearchResult) -> str:
        """Format search results for LLM consumption."""
        lines = [f"Found {len(result.chunks)} relevant conversation chunks:\n"]

        for i, chunk in enumerate(result.chunks, 1):
            timestamp = datetime.fromtimestamp(chunk['timestamp'])
            lines.append(f"--- [{i}] {timestamp.strftime('%b %d, %H:%M')} ---")
            lines.append(f"Context: {chunk['context_summary']}")
            lines.append(chunk['content'])
            lines.append("")

        return '\n'.join(lines)

    def _format_messages(self, messages: List[Dict]) -> str:
        """Format raw messages for LLM consumption."""
        lines = []
        for msg in messages:
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content', '')[:500]  # Truncate long messages
            lines.append(f"{role}: {content}")
        return '\n'.join(lines)
```

---

## Integration Points

### 1. Consolidation Triggers (Startup + Shutdown)

Consolidation runs at **both** startup and shutdown for resilience:
- **Startup:** Catches messages from crashed sessions (idempotent, safe to re-run)
- **Shutdown:** Normal path for graceful exit

Chunk IDs are deterministic (`project_id:msg_start:msg_end`), so re-indexing is a no-op.

```python
# In interactive.py or session management

def on_startup(session_context: SessionContext):
    """Called during initialization - consolidate any orphaned messages from crashes."""
    consolidator = session_context.get_memory_consolidator()
    if consolidator and consolidator.get_unindexed_count() > 0:
        # Run in background thread to avoid blocking startup
        threading.Thread(
            target=_background_consolidate,
            args=(consolidator,),
            daemon=True,
        ).start()

def _background_consolidate(consolidator: MemoryConsolidatorProtocol):
    """Background consolidation (startup recovery)."""
    try:
        result = consolidator.consolidate()
        if result.chunks_created > 0:
            logger.info(f"Startup recovery: consolidated {result.chunks_created} chunks")
    except Exception as e:
        logger.warning(f"Background consolidation failed: {e}")

def on_conversation_close(session_context: SessionContext):
    """Called when user exits or session times out."""
    consolidator = session_context.get_memory_consolidator()
    if consolidator:
        result = consolidator.consolidate()
        if result.chunks_created > 0:
            logger.info(f"Consolidated {result.chunks_created} conversation chunks")
```

### 2. Tool Registration

```python
# In tool registry setup

def register_episodic_tools(
    registry: ToolRegistry,
    episodic_memory: EpisodicMemoryProtocol,
    conversation_store: ConversationStoreProtocol,
):
    """Register episodic memory tools when available."""
    if episodic_memory.is_indexed():
        recall_tool = RecallConversationTool(episodic_memory, conversation_store)
        registry.register(recall_tool)
```

### 3. SQLite Schema Migration

```python
# In ConversationStore._init_schema()

def _migrate_to_v2(self):
    """Add indexed_at column for episodic memory tracking."""
    try:
        self._conn.execute("ALTER TABLE messages ADD COLUMN indexed_at TIMESTAMP")
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_unindexed
            ON messages(project_id, indexed_at) WHERE indexed_at IS NULL
        """)
        self._conn.execute("UPDATE schema_version SET version = 2")
        self._conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
```

---

## Edge Cases & Fallbacks

| Scenario | Behavior |
|----------|----------|
| Vector DB unavailable | SQL LIKE search via `search_text()` |
| Empty conversation | No consolidation, tool returns "no history" |
| Very short messages ("ok", "yes") | Skipped during chunking (MIN_CHUNK_LENGTH) |
| Tool call sequences | Kept atomic, never split across chunks |
| Consecutive user messages | Grouped together, not orphaned as separate chunks |
| Message edited after indexing | Ignored (rare, complexity not worth it) |
| Concurrent consolidation | File locking prevents race conditions |
| Search before consolidation | Searches unindexed messages via SQL |
| Crash without graceful shutdown | Startup consolidation recovers orphaned messages |
| Search for recent (unindexed) content | Tool searches both indexed AND unindexed |

---

## Implementation Checklist

### Phase 2a: Foundation
- [ ] Add `indexed_at` column to messages table (migration)
- [ ] Create `ConversationStoreProtocol.get_unindexed_messages()`
- [ ] Create `ConversationStoreProtocol.mark_as_indexed()`
- [ ] Create `ConversationStoreProtocol.search_text(query, limit)` for efficient SQL LIKE search
- [ ] Create `episodic_memory/protocols.py` with all protocols

### Phase 2b: Chunking
- [ ] Implement `ConversationChunker` with fixed flush logic (user-after-assistant)
- [ ] Implement `ConversationContext` for enrichment
- [ ] Write tests for chunking edge cases:
  - [ ] Consecutive user messages (should group, not orphan)
  - [ ] Tool call sequences (atomic)
  - [ ] Empty/short messages (skip)
  - [ ] Long messages (truncate)

### Phase 2c: Vector Storage
- [ ] Implement `EpisodicMemoryProvider` (LanceDB table)
- [ ] Reuse existing `EmbeddingFunctionProtocol`
- [ ] Implement hybrid search with temporal filtering
- [ ] Write tests with mock embeddings

### Phase 2d: Consolidation
- [ ] Implement `MemoryConsolidator`
- [ ] Wire consolidation to conversation close (shutdown)
- [ ] Wire consolidation to startup (crash recovery, background thread)
- [ ] Ensure idempotency (deterministic chunk IDs)
- [ ] Write integration tests

### Phase 2e: Agent Tool
- [ ] Implement `RecallConversationTool`
- [ ] Search BOTH indexed (vector) AND unindexed (current session)
- [ ] Use `search_text()` for efficient fallback (not Python iteration)
- [ ] Register tool conditionally (when index exists)
- [ ] Write tool execution tests

### Phase 2f: Polish
- [ ] Add `/memory` command to show episodic stats
- [ ] Add `/memory consolidate` for manual trigger
- [ ] Test with real conversations
- [ ] Performance testing with 1000+ messages

## Future Enhancements

### Relative Time Filtering (Post-Phase 2)
The `TimeRange` enum works for common cases ("yesterday", "last_week"), but users sometimes ask:
- "What did we discuss **before** we switched to OAuth?"
- "Show me conversations from **last Tuesday**"

**Potential approach:** Accept freeform string, let LLM interpret and convert to timestamp range. Requires careful prompt engineering to avoid hallucinated dates. Defer until Phase 2 is stable.

### Phase 2g: Documentation
- [ ] Create `docs/behavior/EPISODIC_MEMORY.md` covering:
  - Overview (long-term semantic memory for conversations)
  - Architecture diagram (SQLite -> Chunker -> LanceDB -> RecallTool)
  - Components table (EpisodicMemoryProvider, ConversationChunker, MemoryConsolidator, RecallConversationTool)
  - LanceDB schema (conversation_chunks table)
  - Chunking strategy (enriched Q+A pairs, context headers)
  - Search modes (semantic, temporal filtering, fallback)
  - Consolidation lifecycle (when it runs, what triggers it)
  - Commands (`/memory`, `/memory consolidate`)
  - Cross-reference to CONVERSATION_HISTORY.md for short-term memory
- [ ] Update `docs/behavior/CONVERSATION_HISTORY.md` to reference EPISODIC_MEMORY.md
- [ ] Update `docs/ARCHITECTURE.md` if needed
