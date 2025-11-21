"""
Configuration loader implementation.

Loads configuration from environment variables, files, and dictionaries.
Supports environment-specific configuration (dev/test/prod).
"""

import os
import json
from typing import Any, Dict, Optional
from pathlib import Path

from .protocols import Environment


class ConfigLoader:
    """
    Loads configuration from various sources.

    Implements ConfigLoaderProtocol.

    Supports loading from:
    - Environment variables
    - JSON files
    - YAML files (if PyYAML is installed)
    - TOML files (if tomli/tomllib is installed)
    - Dictionaries
    """

    def load_from_env(
        self,
        prefix: str = "",
        environment: Optional[Environment] = None
    ) -> Dict[str, Any]:
        """
        Load configuration from environment variables.

        Environment variables are converted to config keys:
        - Removes prefix
        - Converts to lowercase
        - Replaces __ with nested dicts

        Example:
            APP_DATABASE__HOST=localhost -> {"database": {"host": "localhost"}}

        Args:
            prefix: Prefix for environment variables (e.g., "APP_")
            environment: Target environment (filters env-specific vars)

        Returns:
            Dictionary of configuration values
        """
        config: Dict[str, Any] = {}

        for key, value in os.environ.items():
            # Skip if doesn't have prefix
            if prefix and not key.startswith(prefix):
                continue

            # Remove prefix
            config_key = key[len(prefix):] if prefix else key

            # Convert to lowercase
            config_key = config_key.lower()

            # Handle nested keys (KEY__NESTED -> key.nested)
            if '__' in config_key:
                parts = config_key.split('__')
                current = config
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = self._parse_env_value(value)
            else:
                config[config_key] = self._parse_env_value(value)

        return config

    def load_from_file(
        self,
        file_path: str,
        environment: Optional[Environment] = None
    ) -> Dict[str, Any]:
        """
        Load configuration from file.

        Supports JSON, YAML, and TOML formats based on file extension.

        Args:
            file_path: Path to configuration file
            environment: Target environment (loads env-specific section)

        Returns:
            Dictionary of configuration values

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid or unsupported
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {file_path}\n"
                f"Please ensure the file exists."
            )

        # Determine format from extension
        suffix = path.suffix.lower()

        if suffix == '.json':
            data = self._load_json(path)
        elif suffix in ('.yaml', '.yml'):
            data = self._load_yaml(path)
        elif suffix == '.toml':
            data = self._load_toml(path)
        else:
            raise ValueError(
                f"Unsupported configuration file format: {suffix}\n"
                f"Supported formats: .json, .yaml, .yml, .toml"
            )

        # Extract environment-specific config if specified
        if environment:
            env_key = environment.value
            if env_key in data:
                # Merge environment-specific with base config
                base_config = {k: v for k, v in data.items() if k not in Environment.__members__.values()}
                env_config = data[env_key]
                return {**base_config, **env_config}

        return data

    def load_from_dict(
        self,
        data: Dict[str, Any],
        environment: Optional[Environment] = None
    ) -> Dict[str, Any]:
        """
        Load configuration from dictionary.

        Args:
            data: Configuration dictionary
            environment: Target environment (loads env-specific section)

        Returns:
            Dictionary of configuration values
        """
        # Extract environment-specific config if specified
        if environment:
            env_key = environment.value
            if env_key in data:
                # Merge environment-specific with base config
                base_config = {k: v for k, v in data.items() if k not in Environment.__members__.values()}
                env_config = data[env_key]
                return {**base_config, **env_config}

        return data.copy()

    def _load_json(self, path: Path) -> Dict[str, Any]:
        """
        Load JSON configuration file.

        Args:
            path: Path to JSON file

        Returns:
            Configuration dictionary

        Raises:
            ValueError: If JSON is invalid
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON in configuration file: {path}\n"
                f"Error: {e}\n"
                f"Please ensure the file contains valid JSON."
            )

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """
        Load YAML configuration file.

        Args:
            path: Path to YAML file

        Returns:
            Configuration dictionary

        Raises:
            ImportError: If PyYAML is not installed
            ValueError: If YAML is invalid
        """
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required to load YAML configuration files.\n"
                "Install it with: pip install pyyaml"
            )

        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(
                f"Invalid YAML in configuration file: {path}\n"
                f"Error: {e}\n"
                f"Please ensure the file contains valid YAML."
            )

    def _load_toml(self, path: Path) -> Dict[str, Any]:
        """
        Load TOML configuration file.

        Args:
            path: Path to TOML file

        Returns:
            Configuration dictionary

        Raises:
            ImportError: If tomli/tomllib is not available
            ValueError: If TOML is invalid
        """
        try:
            # Python 3.11+ has tomllib in stdlib
            import tomllib
        except ImportError:
            try:
                # Fallback to tomli for older Python versions
                import tomli as tomllib
            except ImportError:
                raise ImportError(
                    "tomli is required to load TOML configuration files on Python < 3.11.\n"
                    "Install it with: pip install tomli"
                )

        try:
            with open(path, 'rb') as f:
                return tomllib.load(f)
        except Exception as e:
            raise ValueError(
                f"Invalid TOML in configuration file: {path}\n"
                f"Error: {e}\n"
                f"Please ensure the file contains valid TOML."
            )

    def _parse_env_value(self, value: str) -> Any:
        """
        Parse environment variable value to appropriate type.

        Handles:
        - Booleans: "true"/"false" (case-insensitive)
        - Numbers: integers and floats
        - Lists: comma-separated values
        - Strings: everything else

        Args:
            value: Environment variable value

        Returns:
            Parsed value
        """
        # Boolean
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False

        # Number
        try:
            # Try int first
            if '.' not in value:
                return int(value)
            # Then float
            return float(value)
        except ValueError:
            pass

        # List (comma-separated)
        if ',' in value:
            return [item.strip() for item in value.split(',')]

        # String
        return value


# Default loader instance
default_loader = ConfigLoader()
