"""Runtime transcript model for TUI rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, NewType

from rich.console import RenderableType

EntryId = NewType("EntryId", int)


@dataclass(frozen=True)
class TranscriptEntry:
    """A semantic transcript entry before terminal-width rendering."""

    id: EntryId
    renderable: RenderableType
    kind: str = "system"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


class TranscriptModel:
    """Append-only runtime transcript source with stable entry identity."""

    def __init__(self) -> None:
        self._entries: list[TranscriptEntry] = []
        self._id_to_index: dict[EntryId, int] = {}
        self._next_id = 1

    def __len__(self) -> int:
        """Return the number of transcript entries."""
        return len(self._entries)

    def append(
        self,
        renderable: RenderableType,
        *,
        kind: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> EntryId:
        """Append an entry and return its stable id."""
        entry_id = EntryId(self._next_id)
        self._next_id += 1
        entry = TranscriptEntry(
            id=entry_id,
            renderable=renderable,
            kind=kind,
            metadata=dict(metadata or {}),
        )
        self._id_to_index[entry_id] = len(self._entries)
        self._entries.append(entry)
        return entry_id

    def clear(self) -> None:
        """Clear all entries without reusing future ids."""
        self._entries.clear()
        self._id_to_index.clear()

    def entries(self) -> tuple[TranscriptEntry, ...]:
        """Return entries in display order."""
        return tuple(self._entries)

    def entry_ids(self) -> tuple[EntryId, ...]:
        """Return entry ids in display order."""
        return tuple(entry.id for entry in self._entries)

    def get(self, entry_id: EntryId) -> TranscriptEntry | None:
        """Return an entry by id, if still retained."""
        index = self._id_to_index.get(entry_id)
        if index is None:
            return None
        return self._entries[index]

    def first_id(self) -> EntryId | None:
        """Return the first retained entry id."""
        if not self._entries:
            return None
        return self._entries[0].id

    def trim_through(self, entry_id: EntryId) -> tuple[EntryId, ...]:
        """Remove entries from the start through entry_id."""
        index = self._id_to_index.get(entry_id)
        if index is None:
            return ()

        removed = self._entries[: index + 1]
        self._entries = self._entries[index + 1 :]
        self._rebuild_index()
        return tuple(entry.id for entry in removed)

    def trim_to_last(self, retained_count: int) -> tuple[EntryId, ...]:
        """Keep only the last retained_count entries."""
        if retained_count < 0:
            retained_count = 0
        overflow = len(self._entries) - retained_count
        if overflow <= 0:
            return ()

        removed = self._entries[:overflow]
        self._entries = self._entries[overflow:]
        self._rebuild_index()
        return tuple(entry.id for entry in removed)

    def _rebuild_index(self) -> None:
        """Rebuild the id lookup after trimming."""
        self._id_to_index = {
            entry.id: index for index, entry in enumerate(self._entries)
        }
