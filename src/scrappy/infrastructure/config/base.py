"""
Base configuration class for all application configs.

Provides common functionality for validation, merging, and serialization.
All application-specific configs should extend BaseConfig.
"""

from dataclasses import dataclass, asdict, fields
from typing import Any, Dict, Optional, TypeVar
from copy import deepcopy

from .protocols import ConfigProtocol, Environment


T = TypeVar('T', bound='BaseConfig')


@dataclass
class BaseConfig:
    """
    Base configuration class.

    All application configs should extend this class to get:
    - Automatic validation
    - Serialization to/from dict
    - Config merging
    - Environment-based config support

    Example:
        @dataclass
        class MyConfig(BaseConfig):
            host: str = "localhost"
            port: int = 8080
            debug: bool = False

            def validate(self) -> None:
                super().validate()
                if self.port < 1 or self.port > 65535:
                    raise ValueError(f"Invalid port: {self.port}")
    """

    def validate(self) -> None:
        """
        Validate configuration values.

        Override this method in subclasses to add custom validation.
        Always call super().validate() first.

        Raises:
            ValueError: If configuration is invalid
            TypeError: If field has wrong type
        """
        # Validate all fields have correct types
        for field in fields(self):
            value = getattr(self, field.name)
            # Skip None values for Optional fields
            if value is None:
                continue

            # Get the expected type (handle Optional and generic types)
            expected_type = field.type

            # Handle Optional[Type] by extracting Type
            if hasattr(expected_type, '__origin__'):
                origin = expected_type.__origin__
                # For Optional types
                if origin is type(Optional):
                    expected_type = expected_type.__args__[0]
                    # Re-check origin after extracting from Optional
                    if hasattr(expected_type, '__origin__'):
                        origin = expected_type.__origin__
                    else:
                        origin = None

                # For generic types (List, Dict, Set, etc.), validate the origin type only
                # We can't use isinstance with subscripted generics, so we check the base type
                if origin is not None:
                    # Map generic origins to their runtime types
                    if origin is list:
                        base_type = list
                    elif origin is dict:
                        base_type = dict
                    elif origin is set:
                        base_type = set
                    elif origin is tuple:
                        base_type = tuple
                    else:
                        # For other generic types, skip validation
                        continue

                    if not isinstance(value, base_type):
                        raise TypeError(
                            f"Field '{field.name}' must be {base_type.__name__}, "
                            f"got {type(value).__name__}"
                        )
                    continue

            # Validate type for non-generic types
            try:
                if not isinstance(value, expected_type):
                    raise TypeError(
                        f"Field '{field.name}' must be {expected_type.__name__}, "
                        f"got {type(value).__name__}"
                    )
            except TypeError:
                # isinstance() failed - probably a complex type annotation
                # Skip validation for complex types
                continue

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary representation of configuration
        """
        return asdict(self)

    def merge(self: T, other: ConfigProtocol) -> T:
        """
        Merge this config with another config.

        Other config values override this config's values.
        Only non-None values from other config are used.

        Args:
            other: Configuration to merge

        Returns:
            New configuration with merged values
        """
        # Create a deep copy of this config
        merged_dict = deepcopy(self.to_dict())

        # Get other config as dict
        other_dict = other.to_dict()

        # Merge: other overrides this (but only non-None values)
        for key, value in other_dict.items():
            if value is not None:
                merged_dict[key] = value

        # Create new instance with merged values
        return type(self)(**merged_dict)

    @classmethod
    def from_dict(cls: type[T], data: Dict[str, Any]) -> T:
        """
        Create configuration from dictionary.

        Only uses keys that match config fields.
        Ignores extra keys in dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            Configuration instance

        Raises:
            TypeError: If required fields are missing
            ValueError: If validation fails
        """
        # Get valid field names
        valid_keys = {f.name for f in fields(cls)}

        # Filter to only valid keys
        filtered_data = {
            key: value
            for key, value in data.items()
            if key in valid_keys
        }

        # Create instance
        instance = cls(**filtered_data)

        # Validate
        instance.validate()

        return instance

    def update(self: T, **kwargs: Any) -> T:
        """
        Create new config with updated values.

        Args:
            **kwargs: Fields to update

        Returns:
            New configuration instance with updated values

        Raises:
            ValueError: If validation fails
        """
        # Get current config as dict
        config_dict = self.to_dict()

        # Update with new values
        config_dict.update(kwargs)

        # Create new instance
        return type(self).from_dict(config_dict)

    def __repr__(self) -> str:
        """
        String representation of config.

        Returns:
            String representation showing all fields
        """
        field_strs = []
        for field in fields(self):
            value = getattr(self, field.name)
            field_strs.append(f"{field.name}={value!r}")

        return f"{type(self).__name__}({', '.join(field_strs)})"


@dataclass
class EnvironmentConfig(BaseConfig):
    """
    Configuration that varies by environment.

    Subclass this for configs that need different values
    in dev/test/prod environments.

    Example:
        @dataclass
        class DatabaseConfig(EnvironmentConfig):
            host: str = "localhost"
            port: int = 5432

            @classmethod
            def for_environment(cls, env: Environment):
                if env == Environment.PRODUCTION:
                    return cls(host="prod.db.example.com", port=5432)
                elif env == Environment.TEST:
                    return cls(host="test.db.example.com", port=5432)
                else:
                    return cls(host="localhost", port=5432)
    """

    environment: Environment = Environment.DEVELOPMENT

    @classmethod
    def for_environment(cls: type[T], env: Environment) -> T:
        """
        Create config for specific environment.

        Override this method to provide environment-specific defaults.

        Args:
            env: Target environment

        Returns:
            Configuration for environment
        """
        return cls(environment=env)
