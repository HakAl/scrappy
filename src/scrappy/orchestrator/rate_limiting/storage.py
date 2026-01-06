"""Rate limit data persistence."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional

try:
    import aiofiles
    _AIO = True
except ImportError:
    _AIO = False

from .protocols import FileSystemProtocol


class FileSystemAdapter:
    """Standard file system implementation."""

    def exists(self, path: Path) -> bool:
        return path.exists()

    def read_text(self, path: Path, encoding: str = "utf-8") -> str:
        return path.read_text(encoding=encoding)

    def write_text(self, path: Path, content: str, encoding: str = "utf-8") -> None:
        path.write_text(content, encoding=encoding)

    def mkdir(self, path: Path, parents: bool = False, exist_ok: bool = False) -> None:
        path.mkdir(parents=parents, exist_ok=exist_ok)

    def unlink(self, path: Path) -> None:
        path.unlink()


class RateLimitStorage:
    """
    Persistent storage for rate limit data.

    Single responsibility: Load and save usage data.
    No business logic, no calculations, no decisions.
    """

    def __init__(
        self,
        file_path: Optional[Path],
        file_system: FileSystemProtocol,
    ):
        """
        Initialize storage.

        Args:
            file_path: Path to storage file (None = no persistence)
            file_system: File system abstraction for I/O
        """
        self.path = file_path
        self._fs = file_system

    def load(self) -> dict[str, Any]:
        """Load usage data from disk."""
        if not self.path or not self._fs.exists(self.path):
            return {}

        try:
            content = self._fs.read_text(self.path)
            return json.loads(content)
        except Exception:
            # Corrupted file - start fresh
            return {}

    def save(self, data: dict[str, Any]) -> None:
        """Save usage data to disk."""
        if not self.path:
            return

        # Ensure parent directory exists
        if self.path.parent:
            self._fs.mkdir(self.path.parent, parents=True, exist_ok=True)

        content = json.dumps(data, indent=2)
        self._fs.write_text(self.path, content)

    async def load_async(self) -> dict[str, Any]:
        """Load usage data asynchronously."""
        if not _AIO:
            return self.load()

        if not self.path or not self._fs.exists(self.path):
            return {}

        try:
            async with aiofiles.open(self.path, encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception:
            return {}

    async def save_async(self, data: dict[str, Any]) -> None:
        """Save usage data asynchronously."""
        if not _AIO:
            return self.save(data)

        if not self.path:
            return

        # Ensure parent directory exists (sync is fine here)
        if self.path.parent:
            self._fs.mkdir(self.path.parent, parents=True, exist_ok=True)

        content = json.dumps(data, indent=2)
        async with aiofiles.open(self.path, "w", encoding="utf-8") as f:
            await f.write(content)
