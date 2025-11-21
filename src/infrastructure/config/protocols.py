"""
Configuration protocols for dependency injection and testing.

Following SOLID principles: define protocols first, then implementations.
This enables testing with test doubles and swapping implementations.
"""

from typing import Any, Dict, Optional, Protocol
from enum import Enum


class Environment(str, Enum):
    """Execution environment types."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"

    @classmethod
    def from_string(cls, value: str) -> "Environment":
        """
        Convert string to Environment enum.

        Args:
            value: Environment name (case-insensitive)

        Returns:
            Environment enum value

        Raises:
            ValueError: If value is not a valid environment
        """
        value_lower = value.lower()
        for env in cls:
            if env.value == value_lower:
                return env
        raise ValueError(
            f"Invalid environment: {value}. "
            f"Must be one of: {', '.join(e.value for e in cls)}"
        )


class ConfigProtocol(Protocol):
    """
    Protocol for all configuration objects.

    All config classes must implement this protocol to ensure
    they can be validated, merged, and serialized consistently.
    """

    def validate(self) -> None:
        """
        Validate configuration values.

        Raises:
            ValueError: If configuration is invalid with clear message
        """
        ...

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary representation of configuration
        """
        ...

    def merge(self, other: "ConfigProtocol") -> "ConfigProtocol":
        """
        Merge this config with another config.

        Other config values override this config's values.

        Args:
            other: Configuration to merge

        Returns:
            New configuration with merged values
        """
        ...


class ConfigLoaderProtocol(Protocol):
    """
    Protocol for configuration loaders.

    Enables loading configuration from different sources
    (environment variables, files, dictionaries, etc.)
    """

    def load_from_env(
        self,
        prefix: str = "",
        environment: Optional[Environment] = None
    ) -> Dict[str, Any]:
        """
        Load configuration from environment variables.

        Args:
            prefix: Prefix for environment variables (e.g., "APP_")
            environment: Target environment (dev/test/prod)

        Returns:
            Dictionary of configuration values
        """
        ...

    def load_from_file(
        self,
        file_path: str,
        environment: Optional[Environment] = None
    ) -> Dict[str, Any]:
        """
        Load configuration from file.

        Supports JSON, YAML, and TOML formats.

        Args:
            file_path: Path to configuration file
            environment: Target environment (dev/test/prod)

        Returns:
            Dictionary of configuration values

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        ...

    def load_from_dict(
        self,
        data: Dict[str, Any],
        environment: Optional[Environment] = None
    ) -> Dict[str, Any]:
        """
        Load configuration from dictionary.

        Args:
            data: Configuration dictionary
            environment: Target environment (dev/test/prod)

        Returns:
            Dictionary of configuration values
        """
        ...


class ConfigValidatorProtocol(Protocol):
    """
    Protocol for configuration validators.

    Validates configuration values and provides clear error messages.
    """

    def validate_required(
        self,
        config: Dict[str, Any],
        required_keys: list[str]
    ) -> None:
        """
        Validate that required keys are present.

        Args:
            config: Configuration dictionary
            required_keys: List of required keys

        Raises:
            ValueError: If required keys are missing with clear message
        """
        ...

    def validate_type(
        self,
        value: Any,
        expected_type: type,
        field_name: str
    ) -> None:
        """
        Validate that value is of expected type.

        Args:
            value: Value to validate
            expected_type: Expected type
            field_name: Name of field (for error messages)

        Raises:
            TypeError: If value is not of expected type with clear message
        """
        ...

    def validate_range(
        self,
        value: int | float,
        min_value: Optional[int | float],
        max_value: Optional[int | float],
        field_name: str
    ) -> None:
        """
        Validate that numeric value is within range.

        Args:
            value: Value to validate
            min_value: Minimum allowed value (inclusive)
            max_value: Maximum allowed value (inclusive)
            field_name: Name of field (for error messages)

        Raises:
            ValueError: If value is out of range with clear message
        """
        ...

    def validate_one_of(
        self,
        value: Any,
        allowed_values: list[Any],
        field_name: str
    ) -> None:
        """
        Validate that value is one of allowed values.

        Args:
            value: Value to validate
            allowed_values: List of allowed values
            field_name: Name of field (for error messages)

        Raises:
            ValueError: If value is not in allowed values with clear message
        """
        ...


class ConfigSourceProtocol(Protocol):
    """
    Protocol for configuration sources.

    Abstracts where configuration data comes from
    (files, environment, remote config service, etc.)
    """

    def read(self) -> Dict[str, Any]:
        """
        Read configuration from source.

        Returns:
            Configuration dictionary

        Raises:
            IOError: If source cannot be read
        """
        ...

    def write(self, config: Dict[str, Any]) -> None:
        """
        Write configuration to source.

        Args:
            config: Configuration dictionary

        Raises:
            IOError: If source cannot be written
        """
        ...

    def exists(self) -> bool:
        """
        Check if configuration source exists.

        Returns:
            True if source exists, False otherwise
        """
        ...
