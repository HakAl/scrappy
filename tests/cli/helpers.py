"""
Test helpers for CLI tests.

Provides mock implementations for testing without file I/O.
"""

from typing import Optional, Dict


class MockApiKeyConfigService:
    """
    Mock implementation of ApiKeyConfigServiceProtocol for testing.

    Provides in-memory API key storage for testing without file I/O.

    Every protocol call is appended to ``calls``, so a test can assert WHICH
    reads a consumer performed and not merely that some key was returned.
    """

    def __init__(self, keys: Optional[Dict[str, str]] = None):
        """Initialize with optional preset key storage.

        Args:
            keys: Preset env var to key mapping (default: empty).
        """
        self.keys: Dict[str, str] = dict(keys) if keys else {}
        self.calls: list[str] = []
        self.load_called = False
        self.save_called = False
        self.saved_config = None
        self._disclaimer_acknowledged = True  # Default to True for tests

    def load(self):
        """Mock load - returns in-memory config."""
        from scrappy.infrastructure.config.api_keys import ApiKeyConfig
        self.calls.append("load")
        self.load_called = True
        return ApiKeyConfig(api_keys=self.keys.copy())

    def reload(self):
        """Mock reload - re-reads the in-memory config, as the real service does."""
        self.calls.append("reload")
        return self.load()

    def save(self, config) -> None:
        """Mock save - stores config in memory."""
        self.calls.append("save")
        self.save_called = True
        self.saved_config = config
        self.keys = config.api_keys.copy()

    def get_key(self, env_var: str) -> Optional[str]:
        """Get API key by env var name."""
        self.calls.append("get_key")
        return self.keys.get(env_var)

    def set_key(self, env_var: str, key: str) -> None:
        """Set API key and save."""
        self.calls.append("set_key")
        self.keys[env_var] = key
        self.save_called = True

    def has_any_key(self, env_vars: list[str]) -> bool:
        """Check if any of the env vars have keys configured."""
        self.calls.append("has_any_key")
        return any(env_var in self.keys and self.keys[env_var] for env_var in env_vars)

    def is_disclaimer_acknowledged(self) -> bool:
        """Check if disclaimer has been acknowledged."""
        self.calls.append("is_disclaimer_acknowledged")
        return self._disclaimer_acknowledged

    def acknowledge_disclaimer(self) -> None:
        """Mark disclaimer as acknowledged."""
        self.calls.append("acknowledge_disclaimer")
        self._disclaimer_acknowledged = True


class MockKeyValidationService:
    """
    Mock for API key validation in wizard testing.

    Provides configurable validate_key behavior. For LLM completion mocks,
    use MockLLMService from tests.helpers instead.
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


# Backwards compatibility alias
MockLLMService = MockKeyValidationService
