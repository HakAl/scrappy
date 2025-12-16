"""
API key configuration service.

Provides protocol-based configuration management for API keys with proper
dependency injection and no direct file I/O in business logic.

Architecture:
- ApiKeyConfig: Dataclass for API key data
- ApiKeyConfigServiceProtocol: Protocol defining the service interface
- ApiKeyConfigService: Implementation using PersistenceProtocol
- create_api_key_service: Factory function for production use
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol

from .base import BaseConfig
from ..persistence.protocols import PersistenceProtocol
from ..validation import validate_api_key, validate_env_var_name


class ApiKeyValidationError(ValueError):
    """Raised when API key validation fails."""
    pass


@dataclass
class ApiKeyConfig(BaseConfig):
    """
    Configuration for API keys - stored in ~/.scrappy/config.json

    This is a pure data class with no I/O operations.
    All persistence is handled by ApiKeyConfigService.
    """
    api_keys: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        """
        Validate API key config.

        Raises:
            ValueError: If configuration is invalid
        """
        super().validate()

        # Keys must be non-empty strings
        for env_var, key in self.api_keys.items():
            if not isinstance(env_var, str) or not env_var:
                raise ValueError(f"Invalid env var name: {env_var}")
            if not isinstance(key, str):
                raise ValueError(f"API key for {env_var} must be string")

    def get_key(self, env_var: str) -> Optional[str]:
        """
        Get API key by environment variable name.

        Args:
            env_var: Environment variable name

        Returns:
            API key value or None if not found
        """
        return self.api_keys.get(env_var)

    def set_key(self, env_var: str, key: str) -> None:
        """
        Set API key for environment variable.

        Args:
            env_var: Environment variable name
            key: API key value
        """
        self.api_keys[env_var] = key

    def has_key(self, env_var: str) -> bool:
        """
        Check if key exists and is non-empty.

        Args:
            env_var: Environment variable name

        Returns:
            True if key exists and is non-empty
        """
        key = self.api_keys.get(env_var)
        return bool(key and key.strip())


class ApiKeyConfigServiceProtocol(Protocol):
    """
    Protocol for API key configuration service.

    Enables dependency injection and testing without real file I/O.
    """

    def load(self) -> ApiKeyConfig:
        """
        Load API key config from storage.

        Returns:
            ApiKeyConfig instance
        """
        ...

    def save(self, config: ApiKeyConfig) -> None:
        """
        Save API key config to storage.

        Args:
            config: Configuration to save
        """
        ...

    def get_key(self, env_var: str) -> Optional[str]:
        """
        Get API key by env var name.

        Args:
            env_var: Environment variable name

        Returns:
            API key value or None if not found
        """
        ...

    def set_key(self, env_var: str, key: str) -> None:
        """
        Set API key and save immediately.

        Args:
            env_var: Environment variable name
            key: API key value
        """
        ...

    def has_any_key(self, env_vars: list[str]) -> bool:
        """
        Check if any of the env vars have keys configured.

        Args:
            env_vars: List of environment variable names to check

        Returns:
            True if any of the variables have configured keys
        """
        ...


class ApiKeyConfigService:
    """
    Service for managing API key configuration.

    Uses PersistenceProtocol for storage - no direct file I/O.
    Follows dependency injection pattern for testability.

    Design Principles:
    - Single Responsibility: Only manages API key config
    - Dependency Inversion: Depends on PersistenceProtocol abstraction
    - Open/Closed: Extensible via different persistence implementations

    Example:
        # Production use
        from scrappy.infrastructure.persistence.json_persistence import JSONPersistence
        persistence = JSONPersistence("~/.scrappy/config.json")
        service = ApiKeyConfigService(persistence)

        # Testing use
        from tests.helpers import InMemoryPersistence
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence)
    """

    def __init__(self, persistence: PersistenceProtocol):
        """
        Initialize with persistence backend.

        Args:
            persistence: Storage backend (JSONPersistence for prod, InMemory for tests)

        Notes:
            - Constructor has NO side effects
            - Does not load config automatically
            - Config is lazy-loaded on first access
        """
        self._persistence = persistence
        self._config: Optional[ApiKeyConfig] = None

    def load(self) -> ApiKeyConfig:
        """
        Load config from persistence.

        Returns:
            ApiKeyConfig instance (creates empty config if none exists)
        """
        data = self._persistence.load()
        if data is None:
            self._config = ApiKeyConfig()
        else:
            self._config = ApiKeyConfig.from_dict(data)
        return self._config

    def reload(self) -> ApiKeyConfig:
        """
        Force reload config from persistence, clearing any cached state.

        Use this after external changes to the config file (e.g., wizard saved keys).

        Returns:
            ApiKeyConfig instance freshly loaded from disk
        """
        self._config = None
        return self.load()

    def save(self, config: ApiKeyConfig) -> None:
        """
        Save config to persistence.

        Args:
            config: Configuration to save

        Raises:
            ValueError: If config validation fails
        """
        config.validate()
        self._persistence.save(config.to_dict())
        self._config = config

    def get_key(self, env_var: str) -> Optional[str]:
        """
        Get API key by env var name.

        Lazy-loads config on first access.

        Args:
            env_var: Environment variable name

        Returns:
            API key value or None if not found
        """
        if self._config is None:
            self.load()
        return self._config.get_key(env_var)

    def set_key(self, env_var: str, key: str) -> None:
        """
        Set API key and save immediately.

        Validates both env_var name and key value before storage.
        Lazy-loads config if not already loaded.

        Args:
            env_var: Environment variable name
            key: API key value

        Raises:
            ApiKeyValidationError: If env_var or key validation fails
        """
        # Validate environment variable name
        env_result = validate_env_var_name(env_var)
        if not env_result.is_valid:
            raise ApiKeyValidationError(f"Invalid env var name: {env_result.error}")

        # Validate API key
        key_result = validate_api_key(key)
        if not key_result.is_valid:
            raise ApiKeyValidationError(f"Invalid API key: {key_result.error}")

        if self._config is None:
            self.load()
        # Use sanitized values
        self._config.set_key(env_result.sanitized_value, key_result.sanitized_value)
        self.save(self._config)

    def has_any_key(self, env_vars: list[str]) -> bool:
        """
        Check if any of the env vars have keys configured.

        Lazy-loads config on first access.

        Args:
            env_vars: List of environment variable names to check

        Returns:
            True if any of the variables have configured keys
        """
        if self._config is None:
            self.load()
        return any(self._config.has_key(ev) for ev in env_vars)


def create_api_key_service() -> ApiKeyConfigService:
    """
    Factory function to create ApiKeyConfigService with default persistence.

    Creates service backed by JSONPersistence at USER_CONFIG_FILE.

    Returns:
        ApiKeyConfigService backed by JSONPersistence at USER_CONFIG_FILE

    Design:
    - Centralizes production configuration
    - Hides infrastructure details from callers
    - Enables easy testing via optional dependency injection
    """
    from ..persistence.json_persistence import JSONPersistence
    from ...cli.config.paths import USER_CONFIG_FILE

    persistence = JSONPersistence(str(USER_CONFIG_FILE))
    return ApiKeyConfigService(persistence)
