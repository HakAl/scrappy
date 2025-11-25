"""
Configuration loaders.

Provides implementations of ConfigLoaderProtocol for loading configuration
from various sources (files, environment, etc.).
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from .protocols import ConfigLoadError


class FileSystemProtocol(Protocol):
    """
    Protocol for file system operations.

    Enables testing without actual file I/O.
    """

    def exists(self, path: Path) -> bool:
        """Check if path exists."""
        ...

    def read_text(self, path: Path) -> str:
        """Read file contents as text."""
        ...


class RealFileSystem:
    """
    Real file system implementation using pathlib.

    Default implementation for production use.
    """

    def exists(self, path: Path) -> bool:
        """Check if path exists."""
        return path.exists()

    def read_text(self, path: Path) -> str:
        """Read file contents as text."""
        return path.read_text(encoding="utf-8")


class FileConfigLoader:
    """
    Loads configuration from YAML or JSON files.

    Supports:
    - .yaml, .yml (requires PyYAML)
    - .json

    Example:
        loader = FileConfigLoader(Path(".scrappy.yaml"))
        config = loader.load()
        clarification = ClarificationConfig.from_dict(
            config.get('clarification', {})
        )
    """

    def __init__(
        self,
        config_path: Path,
        file_system: Optional[FileSystemProtocol] = None,
    ) -> None:
        """
        Initialize file config loader.

        Args:
            config_path: Path to the configuration file.
            file_system: Injectable file system for testing.
                Defaults to RealFileSystem.
        """
        self._config_path = config_path
        self._file_system = file_system or RealFileSystem()

    def load(self) -> Dict[str, Any]:
        """
        Load configuration from file.

        Returns:
            Configuration dictionary. Returns empty dict if file
            does not exist.

        Raises:
            ConfigLoadError: If file exists but cannot be read/parsed.
        """
        if not self._file_system.exists(self._config_path):
            return {}

        try:
            content = self._file_system.read_text(self._config_path)
        except OSError as e:
            raise ConfigLoadError(
                f"Failed to read config file {self._config_path}: {e}"
            ) from e

        suffix = self._config_path.suffix.lower()

        if suffix in (".yaml", ".yml"):
            return self._parse_yaml(content)
        elif suffix == ".json":
            return self._parse_json(content)
        else:
            raise ConfigLoadError(
                f"Unsupported config file format: {suffix}. "
                f"Supported formats: .yaml, .yml, .json"
            )

    def _parse_yaml(self, content: str) -> Dict[str, Any]:
        """Parse YAML content."""
        try:
            import yaml
        except ImportError as e:
            raise ConfigLoadError(
                "PyYAML is required for YAML config files. "
                "Install it with: pip install pyyaml"
            ) from e

        try:
            result = yaml.safe_load(content)
            # Handle empty file
            if result is None:
                return {}
            if not isinstance(result, dict):
                raise ConfigLoadError(
                    f"Config file must contain a mapping, got {type(result).__name__}"
                )
            return result
        except yaml.YAMLError as e:
            raise ConfigLoadError(f"Invalid YAML in config file: {e}") from e

    def _parse_json(self, content: str) -> Dict[str, Any]:
        """Parse JSON content."""
        try:
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ConfigLoadError(
                    f"Config file must contain an object, got {type(result).__name__}"
                )
            return result
        except json.JSONDecodeError as e:
            raise ConfigLoadError(f"Invalid JSON in config file: {e}") from e


class ChainedConfigLoader:
    """
    Loads configuration from multiple sources in priority order.

    Later sources override earlier ones. Useful for loading defaults,
    then overriding with user config.

    Example:
        loader = ChainedConfigLoader([
            FileConfigLoader(Path("defaults.yaml")),
            FileConfigLoader(Path(".scrappy.yaml")),
        ])
        config = loader.load()
    """

    def __init__(self, loaders: list) -> None:
        """
        Initialize chained loader.

        Args:
            loaders: List of loaders in priority order (later overrides earlier).
        """
        self._loaders = loaders

    def load(self) -> Dict[str, Any]:
        """
        Load and merge configuration from all sources.

        Returns:
            Merged configuration dictionary.
        """
        result: Dict[str, Any] = {}
        for loader in self._loaders:
            config = loader.load()
            result = self._deep_merge(result, config)
        return result

    def _deep_merge(
        self, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deep merge two dictionaries.

        Args:
            base: Base dictionary.
            override: Dictionary to merge on top.

        Returns:
            New merged dictionary.
        """
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
