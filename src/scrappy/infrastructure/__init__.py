"""
Infrastructure module.

Provides shared infrastructure components across all application layers:
- Protocols: Abstract interfaces for external dependencies (file system, HTTP, etc.)
- Exceptions: Unified exception hierarchy with recovery actions
- Error Recovery: Retry, circuit breaker, and fallback strategies
- File System: Real and in-memory file system implementations

Enables dependency injection, testability, and consistent error handling.
"""

from .protocols import (
    FileSystemProtocol,
    HTTPClientProtocol,
    EnvironmentProtocol,
    ConfigLoaderProtocol,
)
from .file_system import (
    RealFileSystem,
    InMemoryFileSystem,
)

# Exception and error recovery are available via submodules:
# - infrastructure.exceptions
# - infrastructure.error_recovery

__all__ = [
    "FileSystemProtocol",
    "HTTPClientProtocol",
    "EnvironmentProtocol",
    "ConfigLoaderProtocol",
    "RealFileSystem",
    "InMemoryFileSystem",
]
