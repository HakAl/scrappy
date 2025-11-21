"""
Global CLIConfig factory and instance management.

Provides centralized configuration loading with support for:
- File-based configuration (JSON/YAML/TOML)
- Environment variables
- Default configuration
- Dependency injection
"""

import os
from pathlib import Path
from typing import Optional

from src.cli.cli_config import CLIConfig
from src.infrastructure.config import ConfigLoader, Environment


class CLIConfigFactory:
    """
    Factory for creating and managing CLIConfig instances.

    Supports loading from multiple sources with priority:
    1. Explicitly provided file path
    2. Environment variable (CLI_CONFIG_PATH)
    3. Default config files (.scrappy.json, .scrappy.yaml, .scrappy.toml)
    4. Default CLIConfig values
    """

    DEFAULT_CONFIG_FILES = [
        '.scrappy.json',
        '.scrappy.yaml',
        '.scrappy.yml',
        '.scrappy.toml',
        'scrappy.json',
        'scrappy.yaml',
        'scrappy.yml',
        'scrappy.toml',
    ]

    def __init__(self, loader: Optional[ConfigLoader] = None):
        """
        Initialize factory.

        Args:
            loader: Config loader (uses default if not provided)
        """
        self.loader = loader or ConfigLoader()
        self._cached_config: Optional[CLIConfig] = None

    def create_default(self) -> CLIConfig:
        """
        Create CLIConfig with default values.

        Returns:
            CLIConfig with default values
        """
        config = CLIConfig()
        config.validate()
        return config

    def create_from_file(
        self,
        file_path: str,
        environment: Optional[Environment] = None,
    ) -> CLIConfig:
        """
        Create CLIConfig from file.

        Args:
            file_path: Path to configuration file
            environment: Optional environment for env-specific config

        Returns:
            CLIConfig loaded from file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        data = self.loader.load_from_file(file_path, environment)
        config = CLIConfig.from_dict(data)
        config.validate()
        return config

    def create_from_env(
        self,
        prefix: str = "CLI_",
        environment: Optional[Environment] = None,
    ) -> CLIConfig:
        """
        Create CLIConfig from environment variables.

        Environment variables should be prefixed (default: CLI_).
        Example: CLI_TEMPERATURE_DEFAULT=0.8

        Args:
            prefix: Prefix for environment variables
            environment: Optional environment filter

        Returns:
            CLIConfig with values from environment
        """
        data = self.loader.load_from_env(prefix, environment)

        # Start with defaults and merge env values
        default = self.create_default()
        if data:
            config = default.merge(CLIConfig.from_dict(data))
        else:
            config = default

        config.validate()
        return config

    def create(
        self,
        config_path: Optional[str] = None,
        environment: Optional[Environment] = None,
        use_env: bool = True,
    ) -> CLIConfig:
        """
        Create CLIConfig with intelligent source detection.

        Priority order:
        1. Explicit config_path parameter
        2. CLI_CONFIG_PATH environment variable
        3. Default config files in current directory
        4. Environment variables (if use_env=True)
        5. Default values

        Args:
            config_path: Optional path to config file
            environment: Optional environment for env-specific config
            use_env: Whether to load from environment variables

        Returns:
            CLIConfig instance
        """
        # Start with default config
        config = self.create_default()

        # Try to find config file
        file_to_load: Optional[Path] = None

        # 1. Explicit path
        if config_path:
            file_to_load = Path(config_path)

        # 2. Environment variable
        elif 'CLI_CONFIG_PATH' in os.environ:
            file_to_load = Path(os.environ['CLI_CONFIG_PATH'])

        # 3. Default config files
        else:
            for filename in self.DEFAULT_CONFIG_FILES:
                candidate = Path.cwd() / filename
                if candidate.exists():
                    file_to_load = candidate
                    break

        # Load from file if found
        if file_to_load and file_to_load.exists():
            try:
                file_config = self.create_from_file(str(file_to_load), environment)
                config = config.merge(file_config)
            except Exception:
                # If file load fails, continue with defaults
                pass

        # 4. Merge environment variables
        if use_env:
            try:
                env_config = self.create_from_env(environment=environment)
                config = config.merge(env_config)
            except Exception:
                # If env load fails, continue with current config
                pass

        config.validate()
        return config

    def get_or_create(
        self,
        config_path: Optional[str] = None,
        environment: Optional[Environment] = None,
        use_cache: bool = True,
    ) -> CLIConfig:
        """
        Get cached config or create new one.

        Args:
            config_path: Optional path to config file
            environment: Optional environment
            use_cache: Whether to use cached config

        Returns:
            CLIConfig instance
        """
        if use_cache and self._cached_config is not None:
            return self._cached_config

        config = self.create(config_path, environment)

        if use_cache:
            self._cached_config = config

        return config

    def clear_cache(self) -> None:
        """Clear cached config instance."""
        self._cached_config = None


# Global factory instance
_factory = CLIConfigFactory()


# Global config instance (lazy-loaded)
_global_config: Optional[CLIConfig] = None


def get_config(
    config_path: Optional[str] = None,
    environment: Optional[Environment] = None,
    reload: bool = False,
) -> CLIConfig:
    """
    Get global CLIConfig instance.

    This is the main entry point for accessing CLI configuration.

    Args:
        config_path: Optional path to config file
        environment: Optional environment
        reload: Force reload config (ignore cache)

    Returns:
        Global CLIConfig instance

    Example:
        config = get_config()
        temperature = config.temperature_default
        max_tokens = config.max_tokens_query
    """
    global _global_config

    if reload or _global_config is None:
        _global_config = _factory.create(config_path, environment)

    return _global_config


def set_config(config: CLIConfig) -> None:
    """
    Set global CLIConfig instance.

    Useful for testing or when you want to use a custom config.

    Args:
        config: CLIConfig instance to use globally
    """
    global _global_config
    _global_config = config


def reset_config() -> None:
    """
    Reset global config to default.

    Useful for testing.
    """
    global _global_config
    _global_config = None
    _factory.clear_cache()
