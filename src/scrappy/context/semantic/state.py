"""
LanceDB-based index state persistence.

Single responsibility: Store and retrieve IndexState metadata in LanceDB.
"""

import json
import logging
from pathlib import Path
from typing import Optional

try:
    import lancedb
    from lancedb.pydantic import LanceModel
    from pydantic import Field
except ImportError:
    lancedb = None
    LanceModel = object

    def Field(**kwargs):  # type: ignore[no-redef]  # noqa: N802 - runtime fallback matching pydantic's Field API
        return None

from ..protocols import IndexState

logger = logging.getLogger(__name__)

# Metadata table name
META_TABLE_NAME = "_index_meta"


class IndexMetaSchema(LanceModel):
    """Schema for index metadata storage in LanceDB."""
    key: str = Field(description="Metadata key (always 'index_state')")
    data: str = Field(description="JSON-serialized IndexState")


class LanceDBIndexStateManager:
    """
    Persist and retrieve IndexState using LanceDB metadata table.

    Single responsibility: State persistence only.
    Uses a dedicated metadata table to store serialized IndexState.

    Args:
        db_path: Path to LanceDB database directory
    """

    def __init__(self, db_path: Path) -> None:
        """
        Initialize state manager.

        Args:
            db_path: Path to LanceDB database directory
        """
        if lancedb is None:
            raise ImportError("lancedb is required for LanceDBIndexStateManager")

        self._db_path = db_path
        self._db: Optional[lancedb.DBConnection] = None

    def _ensure_db(self) -> lancedb.DBConnection:
        """Ensure database connection is established."""
        if self._db is None:
            self._db_path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self._db_path)
        return self._db

    def load(self) -> Optional[IndexState]:
        """
        Load persisted IndexState from metadata table.

        Returns:
            IndexState if found, None if not exists or corrupted
        """
        try:
            db = self._ensure_db()

            # Check if metadata table exists
            table_names = db.table_names()
            if META_TABLE_NAME not in table_names:
                logger.debug(f"Metadata table '{META_TABLE_NAME}' does not exist")
                return None

            # Open metadata table
            table = db.open_table(META_TABLE_NAME)

            # Query for index_state key
            results = table.search().where("key = 'index_state'").limit(1).to_list()

            if not results:
                logger.debug("No index state found in metadata table")
                return None

            # Deserialize JSON data
            data_str = results[0]["data"]
            data = json.loads(data_str)

            # Reconstruct IndexState
            from datetime import datetime
            state = IndexState(
                last_indexed=datetime.fromisoformat(data["last_indexed"]),
                total_chunks=data["total_chunks"],
                total_files=data["total_files"],
                index_version=data["index_version"],
                file_hashes=data["file_hashes"],
            )

            logger.debug(f"Loaded index state: {state.total_chunks} chunks, {state.total_files} files")
            return state

        except Exception as e:
            logger.warning(f"Failed to load index state: {e}", exc_info=True)
            return None

    def save(self, state: IndexState) -> None:
        """
        Save IndexState to metadata table.

        Args:
            state: IndexState to persist
        """
        try:
            db = self._ensure_db()

            # Serialize state to JSON
            data = {
                "last_indexed": state.last_indexed.isoformat(),
                "total_chunks": state.total_chunks,
                "total_files": state.total_files,
                "index_version": state.index_version,
                "file_hashes": state.file_hashes,
            }
            data_str = json.dumps(data)

            # Prepare record
            record = {
                "key": "index_state",
                "data": data_str,
            }

            # Check if table exists
            table_names = db.table_names()
            if META_TABLE_NAME in table_names:
                # Table exists - update or insert
                table = db.open_table(META_TABLE_NAME)

                # Delete existing state (if any)
                # LanceDB doesn't have direct update, so delete + add
                try:
                    table.delete("key = 'index_state'")
                except Exception:
                    pass  # Ignore if no rows to delete

                # Add new state
                table.add([record])
            else:
                # Create new table with schema
                table = db.create_table(META_TABLE_NAME, schema=IndexMetaSchema)
                table.add([record])

            logger.debug(f"Saved index state: {state.total_chunks} chunks, {state.total_files} files")

        except Exception as e:
            logger.error(f"Failed to save index state: {e}", exc_info=True)
            raise

    def clear(self) -> None:
        """
        Clear persisted IndexState.

        Removes the index_state record from metadata table.
        """
        try:
            db = self._ensure_db()

            # Check if table exists
            table_names = db.table_names()
            if META_TABLE_NAME not in table_names:
                logger.debug("Metadata table does not exist, nothing to clear")
                return

            # Open table and delete state
            table = db.open_table(META_TABLE_NAME)
            table.delete("key = 'index_state'")

            logger.debug("Cleared index state")

        except Exception as e:
            logger.warning(f"Failed to clear index state: {e}", exc_info=True)
