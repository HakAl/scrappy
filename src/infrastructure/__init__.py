"""
Infrastructure protocols module.

Provides abstract interfaces for external dependencies and infrastructure concerns.
Enables dependency injection and testability by abstracting file system, HTTP,
environment variables, and configuration.
"""

from .protocols import (
    FileSystemProtocol,
    HTTPClientProtocol,
    EnvironmentProtocol,
    ConfigLoaderProtocol,
)

__all__ = [
    "FileSystemProtocol",
    "HTTPClientProtocol",
    "EnvironmentProtocol",
    "ConfigLoaderProtocol",
]
