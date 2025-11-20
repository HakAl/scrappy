"""
Persistence protocols for data storage and retrieval.

Defines abstract interfaces for persisting structured data (JSON, etc.) with
error handling and async support. Built on top of FileSystemProtocol.
"""

from typing import Protocol, Dict, Any, Optional, TypeVar, Generic
from pathlib import Path


T = TypeVar('T')


class PersistenceProtocol(Protocol, Generic[T]):
    """
    Protocol for persisting structured data to storage.

    Abstracts data persistence operations to enable testing without real I/O.
    Handles serialization, deserialization, and error recovery automatically.

    Type parameter T represents the data type being persisted (typically Dict[str, Any]).

    Implementations:
    - JSONPersistence: Synchronous JSON file persistence
    - AsyncJSONPersistence: Asynchronous JSON file persistence with aiofiles
    - InMemoryPersistence: In-memory storage for testing

    Example:
        def save_cache(storage: PersistenceProtocol[Dict[str, Any]], data: Dict[str, Any]) -> None:
            storage.save(data)

        # In production
        save_cache(JSONPersistence("cache.json"), {"key": "value"})

        # In tests
        save_cache(InMemoryPersistence(), {"key": "value"})
    """

    def load(self) -> Optional[T]:
        """
        Load data from storage.

        Returns:
            Loaded data, or None if storage is empty or load fails

        Notes:
            - Should handle missing files gracefully (return None)
            - Should handle corrupted data gracefully (return None)
            - Should log errors via output interface if available
        """
        ...

    def save(self, data: T) -> None:
        """
        Save data to storage.

        Args:
            data: Data to persist

        Notes:
            - Should create parent directories if needed
            - Should handle write errors gracefully
            - Should log errors via output interface if available
        """
        ...

    def exists(self) -> bool:
        """
        Check if storage exists.

        Returns:
            True if storage exists, False otherwise
        """
        ...

    def clear(self) -> None:
        """
        Clear/delete storage.

        Notes:
            - Should handle missing storage gracefully (no error)
            - Should log errors via output interface if available
        """
        ...


class AsyncPersistenceProtocol(Protocol, Generic[T]):
    """
    Protocol for asynchronous data persistence.

    Same as PersistenceProtocol but with async methods.
    Useful for high-throughput applications that need non-blocking I/O.

    Implementations:
    - AsyncJSONPersistence: Async JSON file persistence with aiofiles
    - InMemoryAsyncPersistence: In-memory storage with async interface

    Example:
        async def save_cache(
            storage: AsyncPersistenceProtocol[Dict[str, Any]],
            data: Dict[str, Any]
        ) -> None:
            await storage.save_async(data)
    """

    async def load_async(self) -> Optional[T]:
        """
        Asynchronously load data from storage.

        Returns:
            Loaded data, or None if storage is empty or load fails
        """
        ...

    async def save_async(self, data: T) -> None:
        """
        Asynchronously save data to storage.

        Args:
            data: Data to persist
        """
        ...

    def exists(self) -> bool:
        """
        Check if storage exists (synchronous check is fine).

        Returns:
            True if storage exists, False otherwise
        """
        ...

    async def clear_async(self) -> None:
        """
        Asynchronously clear/delete storage.
        """
        ...
