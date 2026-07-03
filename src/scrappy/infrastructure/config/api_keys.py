"""
API key configuration service.

Provides protocol-based configuration management for API keys with proper
dependency injection and no direct file I/O in business logic.

Architecture:
- ApiKeyConfig: Dataclass for API key data
- ApiKeyConfigServiceProtocol: Protocol defining the service interface
- ApiKeyConfigService: Implementation using PersistenceProtocol
- create_api_key_service: Factory function for production use

Environment Variable Migration:
- On load(), API keys from environment variables are automatically migrated
  to the config file if not already present
- This ensures consistent behavior regardless of entry point (TUI, CLI, etc.)
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from .base import BaseConfig
from ..persistence.protocols import PersistenceProtocol
from ..validation import validate_api_key, validate_env_var_name

logger = logging.getLogger(__name__)

# Known provider API key environment variables
# Used for automatic migration from env vars to config
PROVIDER_ENV_VARS = [
    "CEREBRAS_API_KEY",
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "SAMBANOVA_API_KEY",
]


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
    disclaimer_acknowledged: bool = False

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

    def reload(self) -> ApiKeyConfig:
        """
        Reload API key config from storage.

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

    def is_disclaimer_acknowledged(self) -> bool:
        """
        Check if user has acknowledged the disclaimer.

        Returns:
            True if disclaimer was acknowledged
        """
        ...

    def acknowledge_disclaimer(self) -> None:
        """
        Mark disclaimer as acknowledged and save.
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

    def load(self, migrate_env: bool = True) -> ApiKeyConfig:
        """
        Load config from persistence and optionally migrate env vars.

        Automatically migrates API keys from environment variables to the
        config file if not already present. This ensures consistent behavior
        regardless of entry point (TUI, CLI, one-off commands).

        Args:
            migrate_env: If True (default), migrate keys from environment
                variables to config. Set False to skip migration (for testing).

        Returns:
            ApiKeyConfig instance (creates empty config if none exists)
        """
        data = self._persistence.load()
        if data is None:
            self._config = ApiKeyConfig()
        else:
            self._config = ApiKeyConfig.from_dict(data)

        # Migrate any API keys from environment variables
        if migrate_env:
            self._migrate_from_env()

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

    def _loaded_config(self) -> ApiKeyConfig:
        """Return the config, lazy-loading it on first access."""
        if self._config is None:
            return self.load()
        return self._config

    def get_key(self, env_var: str) -> Optional[str]:
        """
        Get API key by env var name.

        Lazy-loads config on first access.

        Args:
            env_var: Environment variable name

        Returns:
            API key value or None if not found
        """
        return self._loaded_config().get_key(env_var)

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

        config = self._loaded_config()
        # Use sanitized values
        config.set_key(env_result.sanitized, key_result.sanitized)
        self.save(config)

    def has_any_key(self, env_vars: list[str]) -> bool:
        """
        Check if any of the env vars have keys configured.

        Lazy-loads config on first access.

        Args:
            env_vars: List of environment variable names to check

        Returns:
            True if any of the variables have configured keys
        """
        config = self._loaded_config()
        return any(config.has_key(ev) for ev in env_vars)

    def is_disclaimer_acknowledged(self) -> bool:
        """
        Check if user has acknowledged the disclaimer.

        Lazy-loads config on first access.

        Returns:
            True if disclaimer was acknowledged
        """
        return self._loaded_config().disclaimer_acknowledged

    def acknowledge_disclaimer(self) -> None:
        """
        Mark disclaimer as acknowledged and save immediately.
        """
        config = self._loaded_config()
        config.disclaimer_acknowledged = True
        self.save(config)

    def _migrate_from_env(self, env_vars: Optional[List[str]] = None) -> int:
        """
        Migrate API keys from environment variables to config.

        For each environment variable, if a valid key is found and not already
        in the config, it is migrated (saved to config file). This allows users
        with .env files to have their keys automatically persisted.

        Args:
            env_vars: List of env var names to check. Defaults to PROVIDER_ENV_VARS.

        Returns:
            Number of keys migrated (not including already-configured keys)
        """
        if self._config is None:
            return 0

        env_vars = env_vars or PROVIDER_ENV_VARS
        migrated = []
        skipped = []

        for env_var in env_vars:
            env_value = os.environ.get(env_var)
            if not env_value:
                continue

            # Validate the env value before migrating
            validation_result = validate_api_key(env_value)
            if not validation_result.is_valid:
                skipped.append((env_var, validation_result.error))
                logger.warning(
                    f"Skipping invalid {env_var} from environment: {validation_result.error}"
                )
                continue

            # Only migrate if not already in config
            if not self._config.has_key(env_var):
                try:
                    # Set key directly on config (skip re-validation in set_key)
                    self._config.set_key(env_var, validation_result.sanitized)
                    migrated.append(env_var)
                except Exception as e:
                    logger.warning(f"Failed to migrate {env_var}: {e}")

        # Save if any keys were migrated
        if migrated:
            try:
                self.save(self._config)
                logger.info(
                    f"Migrated {len(migrated)} API key(s) from environment: {', '.join(migrated)}"
                )
            except Exception as e:
                logger.warning(f"Failed to save migrated keys: {e}")
                return 0

        if skipped:
            logger.warning(f"Skipped {len(skipped)} invalid key(s) from environment")

        return len(migrated)


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
