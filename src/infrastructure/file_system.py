"""
File system implementations for FileSystemProtocol.

Provides concrete implementations for file system operations:
- RealFileSystem: Adapter for actual file system via pathlib.Path
- InMemoryFileSystem: In-memory implementation for testing without I/O
"""

from pathlib import Path
from typing import List, Dict
import shutil


class RealFileSystem:
    """
    Real file system adapter using pathlib.Path.

    Provides production file system operations using Python's pathlib module.
    All paths are resolved to absolute paths for consistency.

    Thread-safety: Individual operations are thread-safe via the OS.
    Concurrent modifications to the same file may result in race conditions.

    Example:
        fs = RealFileSystem()
        fs.write_text("output.txt", "hello world")
        content = fs.read_text("output.txt")
    """

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read file contents as text."""
        return Path(path).read_text(encoding=encoding)

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        """Write text content to file, creating parent directories if needed."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding=encoding)

    def read_bytes(self, path: str) -> bytes:
        """Read file contents as bytes."""
        return Path(path).read_bytes()

    def write_bytes(self, path: str, content: bytes) -> None:
        """Write binary content to file, creating parent directories if needed."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        return Path(path).exists()

    def is_file(self, path: str) -> bool:
        """Check if path is a file."""
        return Path(path).is_file()

    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        return Path(path).is_dir()

    def mkdir(self, path: str, parents: bool = False, exist_ok: bool = False) -> None:
        """Create directory."""
        Path(path).mkdir(parents=parents, exist_ok=exist_ok)

    def list_dir(self, path: str) -> List[str]:
        """List directory contents, returning names only (not full paths)."""
        dir_path = Path(path)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        return [item.name for item in dir_path.iterdir()]

    def glob(self, pattern: str) -> List[str]:
        """Find files matching glob pattern."""
        # Determine base path and pattern
        if "/" in pattern or "\\" in pattern:
            # Pattern includes path components
            base = Path(pattern).parts[0] if pattern.startswith(("/", "\\")) else Path.cwd()
            search_path = Path(pattern).parent if not pattern.startswith(("**", "*")) else Path.cwd()
        else:
            # Simple pattern, search from current directory
            search_path = Path.cwd()

        results = list(search_path.glob(pattern))
        return [str(p) for p in results]

    def delete(self, path: str) -> None:
        """Delete file or empty directory."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        if file_path.is_dir():
            file_path.rmdir()  # Only works for empty directories
        else:
            file_path.unlink()

    def delete_tree(self, path: str) -> None:
        """Recursively delete directory and all contents."""
        dir_path = Path(path)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        shutil.rmtree(dir_path)

    def resolve(self, path: str) -> str:
        """Resolve path to absolute path."""
        return str(Path(path).resolve())

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
    In-memory file system for testing without real I/O.

    Stores all files and directories in memory using dictionaries.
    Simulates file system behavior including directory hierarchies,
    file/directory distinction, and error conditions.

    Thread-safety: Not thread-safe. Use separate instances per thread.

    Limitations:
    - Does not persist across instances
    - Glob patterns have limited support (basic wildcards only)
    - No symbolic links support
    - No file permissions or attributes

    Example:
        fs = InMemoryFileSystem()
        fs.write_text("test.txt", "hello")
        assert fs.read_text("test.txt") == "hello"
        assert fs.exists("test.txt")
    """

    def __init__(self) -> None:
        """Initialize empty in-memory file system."""
        self._files: Dict[str, bytes] = {}
        self._directories: set = {"/"}

    def _normalize_path(self, path: str) -> str:
        """Normalize path to consistent format (absolute, forward slashes)."""
        # Always use forward slashes for in-memory file system
        normalized = path.replace("\\", "/")

        # Convert to absolute if relative (doesn't start with /)
        if not normalized.startswith("/"):
            normalized = "/" + normalized

        # Remove trailing slash except for root
        if normalized != "/" and normalized.endswith("/"):
            normalized = normalized.rstrip("/")

        # Resolve . and .. components
        parts = []
        for part in normalized.split("/"):
            if part == "." or part == "":
                continue
            elif part == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(part)

        return "/" + "/".join(parts) if parts else "/"

    def _ensure_parent_exists(self, path: str) -> None:
        """Ensure parent directory exists for given path."""
        normalized = self._normalize_path(path)
        parent = self._get_parent(normalized)
        if parent and parent != normalized:
            if parent not in self._directories:
                raise FileNotFoundError(f"Parent directory does not exist: {parent}")

    def _get_parent(self, path: str) -> str:
        """Get parent directory path."""
        if path == "/":
            return "/"
        parts = path.rstrip("/").split("/")
        if len(parts) <= 1:
            return "/"
        return "/".join(parts[:-1]) or "/"

    def _create_parent_dirs(self, path: str) -> None:
        """Create all parent directories for given path."""
        normalized = self._normalize_path(path)
        parts = [p for p in normalized.split("/") if p]
        for i in range(len(parts)):
            dir_path = "/" + "/".join(parts[:i]) if i > 0 else "/"
            self._directories.add(dir_path)

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read file contents as text."""
        normalized = self._normalize_path(path)
        if normalized not in self._files:
            raise FileNotFoundError(f"File not found: {path}")
        return self._files[normalized].decode(encoding)

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        """Write text content to file, creating parent directories."""
        normalized = self._normalize_path(path)
        self._create_parent_dirs(normalized)
        self._files[normalized] = content.encode(encoding)
        # Remove from directories if it was there
        self._directories.discard(normalized)

    def read_bytes(self, path: str) -> bytes:
        """Read file contents as bytes."""
        normalized = self._normalize_path(path)
        if normalized not in self._files:
            raise FileNotFoundError(f"File not found: {path}")
        return self._files[normalized]

    def write_bytes(self, path: str, content: bytes) -> None:
        """Write binary content to file, creating parent directories."""
        normalized = self._normalize_path(path)
        self._create_parent_dirs(normalized)
        self._files[normalized] = content
        # Remove from directories if it was there
        self._directories.discard(normalized)

    def exists(self, path: str) -> bool:
        """Check if path exists (file or directory)."""
        normalized = self._normalize_path(path)
        return normalized in self._files or normalized in self._directories

    def is_file(self, path: str) -> bool:
        """Check if path is a file."""
        normalized = self._normalize_path(path)
        return normalized in self._files

    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        normalized = self._normalize_path(path)
        return normalized in self._directories

    def mkdir(self, path: str, parents: bool = False, exist_ok: bool = False) -> None:
        """Create directory."""
        normalized = self._normalize_path(path)

        # Check if already exists
        if normalized in self._directories:
            if not exist_ok:
                raise FileExistsError(f"Directory already exists: {path}")
            return

        # Check if path exists as file
        if normalized in self._files:
            raise FileExistsError(f"Path exists as file: {path}")

        # Check parent exists
        parent = self._get_parent(normalized)
        if parent != normalized and parent not in self._directories:
            if parents:
                self.mkdir(parent, parents=True, exist_ok=True)
            else:
                raise FileNotFoundError(f"Parent directory does not exist: {parent}")

        self._directories.add(normalized)

    def list_dir(self, path: str) -> List[str]:
        """List directory contents, returning names only."""
        normalized = self._normalize_path(path)

        if normalized not in self._directories:
            if normalized in self._files:
                raise NotADirectoryError(f"Not a directory: {path}")
            raise FileNotFoundError(f"Directory not found: {path}")

        # Find all immediate children
        children = set()
        prefix = normalized if normalized == "/" else normalized + "/"

        # Check files
        for file_path in self._files:
            if file_path.startswith(prefix):
                relative = file_path[len(prefix):]
                if "/" not in relative:  # Immediate child only
                    children.add(relative)

        # Check directories
        for dir_path in self._directories:
            if dir_path != normalized and dir_path.startswith(prefix):
                relative = dir_path[len(prefix):]
                if "/" not in relative:  # Immediate child only
                    children.add(relative)

        return sorted(children)

    def glob(self, pattern: str) -> List[str]:
        """
        Find files matching glob pattern.

        Supports basic patterns:
        - * matches any characters except /
        - ** matches any characters including /
        - ? matches single character

        Limited implementation suitable for testing.
        """
        import fnmatch

        normalized_pattern = self._normalize_path(pattern)

        results = []

        # Check against files
        for file_path in self._files:
            if fnmatch.fnmatch(file_path, normalized_pattern):
                results.append(file_path)

        # For ** patterns, need to handle specially
        if "**" in pattern:
            # Match any file that contains the non-** parts
            parts = normalized_pattern.split("**")
            for file_path in self._files:
                match = True
                for part in parts:
                    if part and part not in file_path:
                        match = False
                        break
                if match:
                    results.append(file_path)

        return sorted(set(results))

    def delete(self, path: str) -> None:
        """Delete file or empty directory."""
        normalized = self._normalize_path(path)

        if normalized not in self._files and normalized not in self._directories:
            raise FileNotFoundError(f"Path not found: {path}")

        if normalized in self._directories:
            # Check if directory is empty
            prefix = normalized if normalized == "/" else normalized + "/"
            for file_path in self._files:
                if file_path.startswith(prefix):
                    raise OSError(f"Directory not empty: {path}")
            for dir_path in self._directories:
                if dir_path != normalized and dir_path.startswith(prefix):
                    raise OSError(f"Directory not empty: {path}")
            self._directories.remove(normalized)
        else:
            del self._files[normalized]

    def delete_tree(self, path: str) -> None:
        """Recursively delete directory and all contents."""
        normalized = self._normalize_path(path)

        if normalized not in self._directories:
            if normalized in self._files:
                raise NotADirectoryError(f"Not a directory: {path}")
            raise FileNotFoundError(f"Directory not found: {path}")

        # Delete all files and subdirectories under this path
        prefix = normalized if normalized == "/" else normalized + "/"

        # Delete files
        files_to_delete = [f for f in self._files if f.startswith(prefix)]
        for file_path in files_to_delete:
            del self._files[file_path]

        # Delete directories
        dirs_to_delete = [d for d in self._directories if d != normalized and d.startswith(prefix)]
        for dir_path in dirs_to_delete:
            self._directories.remove(dir_path)

        # Delete the directory itself
        self._directories.remove(normalized)

    def resolve(self, path: str) -> str:
        """Resolve path to absolute path."""
        return self._normalize_path(path)

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
        # Use Path for joining, then normalize
        result = Path(parts[0])
        for part in parts[1:]:
            result = result / part
        return self._normalize_path(str(result))

    def clear(self) -> None:
        """Clear all files and directories (useful for test cleanup)."""
        self._files.clear()
        self._directories.clear()
        self._directories.add("/")
