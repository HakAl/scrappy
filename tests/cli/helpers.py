"""
Test helpers for CLI tests.

Provides mock implementations for testing without file I/O.
"""

from typing import Optional, Dict, Any


class MockApiKeyConfigService:
    """
    Mock implementation of ApiKeyConfigServiceProtocol for testing.

    Provides in-memory API key storage for testing without file I/O.
    """

    def __init__(self):
        """Initialize with empty key storage."""
        self.keys: Dict[str, str] = {}
        self.load_called = False
        self.save_called = False
        self.saved_config = None

    def load(self):
        """Mock load - returns in-memory config."""
        from scrappy.infrastructure.config.api_keys import ApiKeyConfig
        self.load_called = True
        return ApiKeyConfig(api_keys=self.keys.copy())

    def save(self, config) -> None:
        """Mock save - stores config in memory."""
        self.save_called = True
        self.saved_config = config
        self.keys = config.api_keys.copy()

    def get_key(self, env_var: str) -> Optional[str]:
        """Get API key by env var name."""
        return self.keys.get(env_var)

    def set_key(self, env_var: str, key: str) -> None:
        """Set API key and save."""
        self.keys[env_var] = key
        self.save_called = True

    def has_any_key(self, env_vars: list[str]) -> bool:
        """Check if any of the env vars have keys configured."""
        return any(env_var in self.keys and self.keys[env_var] for env_var in env_vars)


class MockLLMService:
    """
    Mock implementation of LLMServiceProtocol for testing.

    Provides configurable validate_key behavior for wizard testing.
    """

    def __init__(self, validate_key_result: tuple[bool, Optional[str]] = (True, None)):
        """Initialize with default validate_key result."""
        self._validate_key_result = validate_key_result
        self.validate_key_calls: list[tuple[str, str]] = []

    def validate_key(self, model: str, api_key: str, timeout: float = 10.0) -> tuple[bool, Optional[str]]:
        """Mock validate_key - returns configured result."""
        self.validate_key_calls.append((model, api_key))
        return self._validate_key_result

    def set_validate_key_result(self, success: bool, error: Optional[str] = None) -> None:
        """Configure what validate_key should return."""
        self._validate_key_result = (success, error)
