"""
JSON persistence implementation.

Provides synchronous and asynchronous JSON file persistence with error handling.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...cli.protocols import BaseOutputProtocol

try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False


class JSONPersistence:
    """
    JSON file persistence with error handling.

    Provides both synchronous and asynchronous JSON save/load operations.
    Handles file I/O errors gracefully and logs errors via OutputInterface.

    Design:
    - Single Responsibility: Only handles JSON serialization and file I/O
    - Dependency Injection: Requires file path and optional output interface
    - Error Handling: Graceful degradation (returns None on load errors)
    - No Side Effects: Constructor only assigns dependencies

    Example:
        from orchestrator.output import ConsoleOutput

        output = ConsoleOutput()
        storage = JSONPersistence("cache.json", output=output)

        # Save data
        storage.save({"key": "value"})

        # Load data
        data = storage.load()  # Returns None if file doesn't exist

        # Async operations
        await storage.save_async({"key": "value"})
        data = await storage.load_async()
    """

    def __init__(
        self,
        file_path: str,
        output: Optional['BaseOutputProtocol'] = None,
        indent: int = 2,
        encoding: str = 'utf-8'
    ):
        """
        Initialize JSON persistence.

        Args:
            file_path: Path to JSON file
            output: Optional output interface for error logging
            indent: JSON indentation for pretty printing (default: 2)
            encoding: File encoding (default: utf-8)

        Notes:
            - Constructor has NO side effects (no file I/O)
            - File path can be relative or absolute
            - Parent directories created automatically on save
        """
        self.file_path = Path(file_path)
        self.output = output or self._create_null_output()
        self.indent = indent
        self.encoding = encoding

    def _create_null_output(self) -> 'BaseOutputProtocol':
        """Create a null output that discards messages."""
        from ...orchestrator.output import NullOutput
        return NullOutput()

    def load(self) -> Optional[Dict[str, Any]]:
        """
        Load data from JSON file (synchronous).

        Returns:
            Loaded data dictionary, or None if file doesn't exist or load fails

        Notes:
            - Returns None on any error (missing file, corrupted JSON, permission error)
            - Logs errors via output interface
            - Does not raise exceptions
        """
        try:
            if not self.file_path.exists():
                return None

            with open(self.file_path, 'r', encoding=self.encoding) as f:
                return json.load(f)

        except json.JSONDecodeError as e:
            self.output.error(f"JSON decode failed for {self.file_path}: {e}")
            return None
        except Exception as e:
            self.output.error(f"Failed to load {self.file_path}: {e}")
            return None

    def save(self, data: Dict[str, Any]) -> None:
        """
        Save data to JSON file (synchronous).

        Args:
            data: Dictionary to save as JSON

        Notes:
            - Creates parent directories automatically
            - Logs errors via output interface
            - Does not raise exceptions
        """
        try:
            # Create parent directories if needed
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.file_path, 'w', encoding=self.encoding) as f:
                json.dump(data, f, indent=self.indent)

        except Exception as e:
            self.output.error(f"Failed to save {self.file_path}: {e}")

    async def load_async(self) -> Optional[Dict[str, Any]]:
        """
        Load data from JSON file (asynchronous).

        Returns:
            Loaded data dictionary, or None if file doesn't exist or load fails

        Notes:
            - Falls back to synchronous load if aiofiles not available
            - Returns None on any error
            - Logs errors via output interface
        """
        if not AIOFILES_AVAILABLE:
            return self.load()

        try:
            if not self.file_path.exists():
                return None

            async with aiofiles.open(self.file_path, 'r', encoding=self.encoding) as f:
                content = await f.read()
                return json.loads(content)

        except json.JSONDecodeError as e:
            self.output.error(f"JSON decode failed for {self.file_path}: {e}")
            return None
        except Exception as e:
            self.output.error(f"Failed to load {self.file_path}: {e}")
            return None

    async def save_async(self, data: Dict[str, Any]) -> None:
        """
        Save data to JSON file (asynchronous).

        Args:
            data: Dictionary to save as JSON

        Notes:
            - Falls back to synchronous save if aiofiles not available
            - Creates parent directories automatically
            - Logs errors via output interface
        """
        if not AIOFILES_AVAILABLE:
            self.save(data)
            return

        try:
            # Create parent directories if needed
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(self.file_path, 'w', encoding=self.encoding) as f:
                await f.write(json.dumps(data, indent=self.indent))

        except Exception as e:
            self.output.error(f"Failed to save {self.file_path}: {e}")

    def exists(self) -> bool:
        """
        Check if JSON file exists.

        Returns:
            True if file exists, False otherwise
        """
        return self.file_path.exists()

    def clear(self) -> None:
        """
        Delete JSON file.

        Notes:
            - Does nothing if file doesn't exist
            - Logs errors via output interface
        """
        try:
            if self.file_path.exists():
                self.file_path.unlink()
        except Exception as e:
            self.output.error(f"Failed to delete {self.file_path}: {e}")

    async def clear_async(self) -> None:
        """
        Asynchronously delete JSON file.

        Notes:
            - Currently uses synchronous delete (fast operation)
            - Could be made truly async if needed
        """
        self.clear()
