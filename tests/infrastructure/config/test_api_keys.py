"""
Unit tests for API key configuration service.

Tests ApiKeyConfig dataclass and ApiKeyConfigService with in-memory persistence.
"""

import pytest
from typing import Dict, Optional, Any

from src.infrastructure.config.api_keys import (
    ApiKeyConfig,
    ApiKeyConfigService,
)


class InMemoryPersistence:
    """
    Test double for PersistenceProtocol.

    Implements in-memory storage for testing without file I/O.
    """

    def __init__(self):
        self.data: Optional[Dict[str, Any]] = None

    def load(self) -> Optional[Dict[str, Any]]:
        """Load data from memory."""
        return self.data

    def save(self, data: Dict[str, Any]) -> None:
        """Save data to memory."""
        self.data = data

    def exists(self) -> bool:
        """Check if data exists."""
        return self.data is not None

    def clear(self) -> None:
        """Clear stored data."""
        self.data = None


class TestApiKeyConfig:
    """Tests for ApiKeyConfig dataclass."""

    def test_empty_config_valid(self):
        """Empty config should validate successfully."""
        config = ApiKeyConfig()
        config.validate()  # Should not raise

    def test_empty_config_has_empty_dict(self):
        """Empty config should have empty api_keys dict."""
        config = ApiKeyConfig()
        assert config.api_keys == {}

    def test_set_and_get_key(self):
        """set_key() and get_key() should work correctly."""
        config = ApiKeyConfig()
        config.set_key("CEREBRAS_API_KEY", "test-key-123")
        assert config.get_key("CEREBRAS_API_KEY") == "test-key-123"

    def test_get_key_returns_none_for_missing(self):
        """get_key() should return None for missing keys."""
        config = ApiKeyConfig()
        assert config.get_key("NONEXISTENT_KEY") is None

    def test_has_key_returns_false_for_empty(self):
        """has_key() should return False for unconfigured keys."""
        config = ApiKeyConfig()
        assert not config.has_key("CEREBRAS_API_KEY")

    def test_has_key_returns_true_for_configured(self):
        """has_key() should return True for configured keys."""
        config = ApiKeyConfig()
        config.set_key("CEREBRAS_API_KEY", "test-key")
        assert config.has_key("CEREBRAS_API_KEY")

    def test_has_key_returns_false_for_empty_string(self):
        """has_key() should return False for empty string keys."""
        config = ApiKeyConfig()
        config.set_key("EMPTY_KEY", "")
        assert not config.has_key("EMPTY_KEY")

    def test_has_key_returns_false_for_whitespace_only(self):
        """has_key() should return False for whitespace-only keys."""
        config = ApiKeyConfig()
        config.set_key("WHITESPACE_KEY", "   ")
        assert not config.has_key("WHITESPACE_KEY")

    def test_validate_rejects_invalid_env_var_name(self):
        """validate() should reject invalid environment variable names."""
        config = ApiKeyConfig(api_keys={"": "some-key"})
        with pytest.raises(ValueError, match="Invalid env var name"):
            config.validate()

    def test_validate_rejects_non_string_key(self):
        """validate() should reject non-string API keys."""
        config = ApiKeyConfig(api_keys={"SOME_KEY": 123})
        with pytest.raises(ValueError, match="must be string"):
            config.validate()

    def test_to_dict_serializes_correctly(self):
        """to_dict() should serialize to dictionary."""
        config = ApiKeyConfig()
        config.set_key("GROQ_API_KEY", "gsk_xyz")
        config.set_key("GEMINI_API_KEY", "AIza_abc")

        result = config.to_dict()

        assert result == {
            "api_keys": {
                "GROQ_API_KEY": "gsk_xyz",
                "GEMINI_API_KEY": "AIza_abc",
            }
        }

    def test_from_dict_deserializes_correctly(self):
        """from_dict() should create instance from dictionary."""
        data = {
            "api_keys": {
                "GROQ_API_KEY": "gsk_xyz",
                "GEMINI_API_KEY": "AIza_abc",
            }
        }

        config = ApiKeyConfig.from_dict(data)

        assert config.get_key("GROQ_API_KEY") == "gsk_xyz"
        assert config.get_key("GEMINI_API_KEY") == "AIza_abc"

    def test_from_dict_validates_on_creation(self):
        """from_dict() should validate config on creation."""
        data = {
            "api_keys": {
                "": "invalid",  # Empty env var name
            }
        }

        with pytest.raises(ValueError, match="Invalid env var name"):
            ApiKeyConfig.from_dict(data)


class TestApiKeyConfigService:
    """Tests for ApiKeyConfigService."""

    def test_load_creates_empty_config_when_no_data(self):
        """load() should create empty config when persistence has no data."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence)

        config = service.load()

        assert config.api_keys == {}

    def test_load_returns_existing_config(self):
        """load() should return existing config from persistence."""
        persistence = InMemoryPersistence()
        persistence.data = {
            "api_keys": {
                "CEREBRAS_API_KEY": "test-key"
            }
        }
        service = ApiKeyConfigService(persistence)

        config = service.load()

        assert config.get_key("CEREBRAS_API_KEY") == "test-key"

    def test_save_persists_config(self):
        """save() should persist config to storage."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence)

        config = ApiKeyConfig()
        config.set_key("GROQ_API_KEY", "gsk_test")
        service.save(config)

        assert persistence.data == {
            "api_keys": {
                "GROQ_API_KEY": "gsk_test"
            }
        }

    def test_save_validates_config(self):
        """save() should validate config before saving."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence)

        # Create invalid config
        config = ApiKeyConfig(api_keys={"": "invalid"})

        with pytest.raises(ValueError, match="Invalid env var name"):
            service.save(config)

    def test_get_key_lazy_loads_config(self):
        """get_key() should lazy-load config on first access."""
        persistence = InMemoryPersistence()
        persistence.data = {
            "api_keys": {
                "CEREBRAS_API_KEY": "test-key"
            }
        }
        service = ApiKeyConfigService(persistence)

        # Don't call load() explicitly
        result = service.get_key("CEREBRAS_API_KEY")

        assert result == "test-key"

    def test_get_key_returns_none_for_missing(self):
        """get_key() should return None for unconfigured keys."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence)

        result = service.get_key("NONEXISTENT_KEY")

        assert result is None

    def test_set_key_saves_immediately(self):
        """set_key() should save config immediately."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence)

        service.set_key("CEREBRAS_API_KEY", "test-key")

        # Verify it was saved to persistence
        assert persistence.data["api_keys"]["CEREBRAS_API_KEY"] == "test-key"

    def test_set_key_lazy_loads_config(self):
        """set_key() should lazy-load config if not already loaded."""
        persistence = InMemoryPersistence()
        persistence.data = {
            "api_keys": {
                "EXISTING_KEY": "existing-value"
            }
        }
        service = ApiKeyConfigService(persistence)

        # Don't call load() explicitly
        service.set_key("NEW_KEY", "new-value")

        # Both keys should be present
        assert persistence.data["api_keys"]["EXISTING_KEY"] == "existing-value"
        assert persistence.data["api_keys"]["NEW_KEY"] == "new-value"

    def test_has_any_key_returns_false_when_empty(self):
        """has_any_key() should return False when no keys configured."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence)

        result = service.has_any_key(["CEREBRAS_API_KEY", "GROQ_API_KEY"])

        assert not result

    def test_has_any_key_returns_true_when_one_configured(self):
        """has_any_key() should return True when at least one key configured."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence)
        service.set_key("GROQ_API_KEY", "test-key")

        result = service.has_any_key(["CEREBRAS_API_KEY", "GROQ_API_KEY"])

        assert result

    def test_has_any_key_returns_false_when_different_keys_configured(self):
        """has_any_key() should return False when different keys configured."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence)
        service.set_key("OTHER_KEY", "test-key")

        result = service.has_any_key(["CEREBRAS_API_KEY", "GROQ_API_KEY"])

        assert not result

    def test_has_any_key_lazy_loads_config(self):
        """has_any_key() should lazy-load config on first access."""
        persistence = InMemoryPersistence()
        persistence.data = {
            "api_keys": {
                "GROQ_API_KEY": "test-key"
            }
        }
        service = ApiKeyConfigService(persistence)

        # Don't call load() explicitly
        result = service.has_any_key(["CEREBRAS_API_KEY", "GROQ_API_KEY"])

        assert result


class TestCreateApiKeyService:
    """Tests for create_api_key_service() factory function."""

    def test_factory_creates_service(self):
        """Factory should create ApiKeyConfigService instance."""
        from src.infrastructure.config.api_keys import create_api_key_service

        service = create_api_key_service()

        # Should be able to use service
        assert service is not None
        # Should lazy-load without errors
        service.get_key("SOME_KEY")
