"""
File system implementations.

Provides concrete implementations of FileSystemProtocol for different
storage backends and testing scenarios.
"""

from pathlib import Path
from typing import Optional

from .protocols import FileSystemProtocol


class RealFileSystem:
    """
    Real file system implementation using pathlib.

    Provides standard file system operations for production use.
    """

    def read_file(self, path: str) -> str:
        """
        Read file contents.

        Args:
            path: File path to read

        Returns:
            File contents as string

        Raises:
            FileNotFoundError: If file does not exist
            PermissionError: If file cannot be read
        """
        return Path(path).read_text(encoding='utf-8')

    def write_file(self, path: str, content: str) -> None:
        """
        Write content to file.

        Args:
            path: File path to write
            content: Content to write

        Raises:
            PermissionError: If file cannot be written
        """
        Path(path).write_text(content, encoding='utf-8')

    def exists(self, path: str) -> bool:
        """
        Check if path exists.

        Args:
            path: Path to check

        Returns:
            True if path exists, False otherwise
        """
        return Path(path).exists()

    def is_file(self, path: str) -> bool:
        """
        Check if path is a file.

        Args:
            path: Path to check

        Returns:
            True if path is a file, False otherwise
        """
        return Path(path).is_file()

    def is_dir(self, path: str) -> bool:
        """
        Check if path is a directory.

        Args:
            path: Path to check

        Returns:
            True if path is a directory, False otherwise
        """
        return Path(path).is_dir()

    def mkdir(self, path: str, parents: bool = False, exist_ok: bool = False) -> None:
        """
        Create directory.

        Args:
            path: Directory path to create
            parents: Create parent directories if needed
            exist_ok: Don't raise error if directory exists

        Raises:
            FileExistsError: If directory exists and exist_ok is False
        """
        Path(path).mkdir(parents=parents, exist_ok=exist_ok)

    def resolve(self, path: str) -> Path:
        """
        Resolve path to absolute path.

        Args:
            path: Path to resolve

        Returns:
            Resolved absolute path
        """
        return Path(path).resolve()

    def join_path(self, *parts: str) -> str:
        """
        Join path components.

        Args:
            *parts: Path components to join

        Returns:
            Joined path as string
        """
        if not parts:
            return ""
        result = Path(parts[0])
        for part in parts[1:]:
            result = result / part
        return str(result)


class InMemoryFileSystem:
    """
    In-memory file system for testing.

    Stores files in a dictionary for fast, isolated testing without
    touching the real file system.
    """

    def __init__(self):
        """Initialize empty in-memory file system."""
        self._files: dict[str, str] = {}
        self._dirs: set[str] = {'/'}

    def read_file(self, path: str) -> str:
        """
        Read file contents from memory.

        Args:
            path: File path to read

        Returns:
            File contents as string

        Raises:
            FileNotFoundError: If file does not exist
        """
        normalized = self._normalize_path(path)
        if normalized not in self._files:
            raise FileNotFoundError(f"File not found: {path}")
        return self._files[normalized]

    def write_file(self, path: str, content: str) -> None:
        """
        Write content to memory.

        Args:
            path: File path to write
            content: Content to write
        """
        normalized = self._normalize_path(path)
        self._files[normalized] = content
        # Ensure parent directories exist
        parent = str(Path(normalized).parent)
        if parent and parent != '.':
            self._dirs.add(parent)

    def exists(self, path: str) -> bool:
        """
        Check if path exists in memory.

        Args:
            path: Path to check

        Returns:
            True if path exists, False otherwise
        """
        normalized = self._normalize_path(path)
        return normalized in self._files or normalized in self._dirs

    def is_file(self, path: str) -> bool:
        """
        Check if path is a file in memory.

        Args:
            path: Path to check

        Returns:
            True if path is a file, False otherwise
        """
        normalized = self._normalize_path(path)
        return normalized in self._files

    def is_dir(self, path: str) -> bool:
        """
        Check if path is a directory in memory.

        Args:
            path: Path to check

        Returns:
            True if path is a directory, False otherwise
        """
        normalized = self._normalize_path(path)
        return normalized in self._dirs

    def mkdir(self, path: str, parents: bool = False, exist_ok: bool = False) -> None:
        """
        Create directory in memory.

        Args:
            path: Directory path to create
            parents: Create parent directories if needed
            exist_ok: Don't raise error if directory exists

        Raises:
            FileExistsError: If directory exists and exist_ok is False
        """
        normalized = self._normalize_path(path)
        if normalized in self._dirs and not exist_ok:
            raise FileExistsError(f"Directory already exists: {path}")

        if parents:
            # Create all parent directories
            parts = Path(normalized).parts
            current = ""
            for part in parts:
                current = str(Path(current) / part) if current else part
                self._dirs.add(current)
        else:
            self._dirs.add(normalized)

    def resolve(self, path: str) -> Path:
        """
        Resolve path (in-memory implementation).

        Args:
            path: Path to resolve

        Returns:
            Path object (not fully resolved, just converted)
        """
        return Path(self._normalize_path(path))

    def join_path(self, *parts: str) -> str:
        """
        Join path components.

        Args:
            *parts: Path components to join

        Returns:
            Joined path as string
        """
        if not parts:
            return ""
        result = Path(parts[0])
        for part in parts[1:]:
            result = result / part
        return str(result)

    def _normalize_path(self, path: str) -> str:
        """Normalize path for consistent storage."""
        return str(Path(path))
