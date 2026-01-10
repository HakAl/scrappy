"""
Configuration loading protocols.

Defines abstract interfaces for configuration loading from external sources.
These protocols enable dependency injection for testability and flexibility.
"""

from typing import Any, Dict, Protocol


class ConfigLoaderProtocol(Protocol):
    """
    Abstract interface for loading configuration from external sources.

    This protocol enables:
    - Testing with mock loaders (no file I/O)
    - Different config sources (file, environment, remote)
    - Caching and validation strategies

    Implementations:
    - FileConfigLoader: Loads from YAML/JSON files
    - EnvironmentConfigLoader: Loads from environment variables
    - CompositeConfigLoader: Combines multiple sources
    """

    def load(self) -> Dict[str, Any]:
        """
        Load and return configuration dictionary.

        Returns:
            Configuration data as a dictionary. Returns empty dict
            if no configuration is found (as opposed to raising).

        Raises:
            ConfigLoadError: If the config file exists but cannot be
                read or parsed (I/O error, syntax error, etc.)
        """
        ...


class ConfigLoadError(Exception):
    """
    Raised when configuration cannot be loaded.

    This error is raised for:
    - File I/O errors (permission denied, etc.)
    - Parse errors (invalid YAML/JSON syntax)
    - Unsupported file formats

    This is NOT raised for:
    - Missing config file (returns empty dict instead)
    """

    pass
