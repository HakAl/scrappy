"""
Unit tests for API key configuration service.

Tests ApiKeyConfig dataclass and ApiKeyConfigService with in-memory persistence.
"""

from typing import Dict, Optional, Any

from scrappy.infrastructure.config.api_keys import (
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
  # Should not raise

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
            },
            "disclaimer_acknowledged": False,
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



class TestApiKeyConfigService:
    """Tests for ApiKeyConfigService."""

    def test_load_creates_empty_config_when_no_data(self):
        """load() should create empty config when persistence has no data."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence, provider_env_vars=())

        # Disable env migration for this test
        config = service.load(migrate_env=False)

        assert config.api_keys == {}

    def test_load_returns_existing_config(self):
        """load() should return existing config from persistence."""
        persistence = InMemoryPersistence()
        persistence.data = {
            "api_keys": {
                "CEREBRAS_API_KEY": "test-key"
            }
        }
        service = ApiKeyConfigService(persistence, provider_env_vars=())

        config = service.load()

        assert config.get_key("CEREBRAS_API_KEY") == "test-key"

    def test_save_persists_config(self):
        """save() should persist config to storage."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence, provider_env_vars=())

        config = ApiKeyConfig()
        config.set_key("GROQ_API_KEY", "gsk_test")
        service.save(config)

        assert persistence.data == {
            "api_keys": {
                "GROQ_API_KEY": "gsk_test"
            },
            "disclaimer_acknowledged": False,
        }


    def test_get_key_lazy_loads_config(self):
        """get_key() should lazy-load config on first access."""
        persistence = InMemoryPersistence()
        persistence.data = {
            "api_keys": {
                "CEREBRAS_API_KEY": "test-key"
            }
        }
        service = ApiKeyConfigService(persistence, provider_env_vars=())

        # Don't call load() explicitly
        result = service.get_key("CEREBRAS_API_KEY")

        assert result == "test-key"

    def test_get_key_returns_none_for_missing(self):
        """get_key() should return None for unconfigured keys."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence, provider_env_vars=())

        result = service.get_key("NONEXISTENT_KEY")

        assert result is None

    def test_set_key_saves_immediately(self):
        """set_key() should save config immediately."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence, provider_env_vars=())

        # Use a valid key (min 10 chars, no placeholders)
        service.set_key("CEREBRAS_API_KEY", "csk_abc123xyz789")

        # Verify it was saved to persistence
        assert persistence.data["api_keys"]["CEREBRAS_API_KEY"] == "csk_abc123xyz789"

    def test_set_key_lazy_loads_config(self):
        """set_key() should lazy-load config if not already loaded."""
        persistence = InMemoryPersistence()
        persistence.data = {
            "api_keys": {
                "EXISTING_KEY": "existing-value-123"
            }
        }
        service = ApiKeyConfigService(persistence, provider_env_vars=())

        # Don't call load() explicitly - use valid key
        service.set_key("NEW_KEY", "new-value-123456")

        # Both keys should be present
        assert persistence.data["api_keys"]["EXISTING_KEY"] == "existing-value-123"
        assert persistence.data["api_keys"]["NEW_KEY"] == "new-value-123456"

    def test_has_any_key_returns_false_when_empty(self):
        """has_any_key() should return False when no keys configured."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence, provider_env_vars=())

        result = service.has_any_key(["CEREBRAS_API_KEY", "GROQ_API_KEY"])

        assert not result


    def test_has_any_key_returns_false_when_different_keys_configured(self):
        """has_any_key() should return False when different keys configured."""
        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence, provider_env_vars=())
        # Use valid key
        service.set_key("OTHER_KEY", "other-key-123456")

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
        service = ApiKeyConfigService(persistence, provider_env_vars=())

        # Don't call load() explicitly
        result = service.has_any_key(["CEREBRAS_API_KEY", "GROQ_API_KEY"])

        assert result


class TestEnvMigration:
    """Tests for environment variable migration behavior."""

    def test_load_migrates_env_vars_to_config(self, monkeypatch):
        """load() should migrate valid API keys from env vars to config."""
        # Set up env var
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_1234567890")

        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence, provider_env_vars=("GROQ_API_KEY",))

        # Load with migration
        config = service.load(migrate_env=True)

        # Key should be migrated to config
        assert config.get_key("GROQ_API_KEY") == "gsk_test_key_1234567890"
        # Should be persisted
        assert persistence.data["api_keys"]["GROQ_API_KEY"] == "gsk_test_key_1234567890"

    def test_load_does_not_overwrite_existing_config(self, monkeypatch):
        """load() should not overwrite keys already in config."""
        # Set up env var with different value
        monkeypatch.setenv("GROQ_API_KEY", "env_key_12345678")

        persistence = InMemoryPersistence()
        persistence.data = {
            "api_keys": {
                "GROQ_API_KEY": "config_key_existing"
            }
        }
        service = ApiKeyConfigService(persistence, provider_env_vars=("GROQ_API_KEY",))

        # Load with migration
        config = service.load(migrate_env=True)

        # Should keep config value, not env value
        assert config.get_key("GROQ_API_KEY") == "config_key_existing"

    def test_load_skips_invalid_env_keys(self, monkeypatch):
        """load() should skip env vars with invalid API keys."""
        # Set up invalid env var (too short)
        monkeypatch.setenv("GROQ_API_KEY", "short")

        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence, provider_env_vars=("GROQ_API_KEY",))

        # Load with migration
        config = service.load(migrate_env=True)

        # Key should NOT be migrated
        assert config.get_key("GROQ_API_KEY") is None

    def test_load_skips_migration_when_disabled(self, monkeypatch):
        """load(migrate_env=False) should not migrate env vars."""
        # Set up env var
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_1234567890")

        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence, provider_env_vars=("GROQ_API_KEY",))

        # Load without migration
        config = service.load(migrate_env=False)

        # Key should NOT be migrated
        assert config.get_key("GROQ_API_KEY") is None

    def test_migrate_returns_count_of_migrated_keys(self, monkeypatch):
        """_migrate_from_env() should return count of migrated keys."""
        # Set up two env vars
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_1234567890")
        monkeypatch.setenv("CEREBRAS_API_KEY", "csk_test_key_1234567890")

        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence, provider_env_vars=())
        service.load(migrate_env=False)  # Load without migration

        # Migrate manually
        count = service._migrate_from_env(["GROQ_API_KEY", "CEREBRAS_API_KEY"])

        assert count == 2

    def test_migrate_only_counts_new_keys(self, monkeypatch):
        """_migrate_from_env() should not count already-existing keys."""
        # Set up env var
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_1234567890")

        persistence = InMemoryPersistence()
        persistence.data = {
            "api_keys": {
                "GROQ_API_KEY": "existing_config_key"
            }
        }
        service = ApiKeyConfigService(persistence, provider_env_vars=())
        service.load(migrate_env=False)  # Load without migration

        # Migrate manually
        count = service._migrate_from_env(["GROQ_API_KEY"])

        # Should not count the already-existing key
        assert count == 0

    def test_explicit_empty_override_migrates_nothing(self, monkeypatch):
        """_migrate_from_env(()) must not fall back to constructor defaults."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_1234567890")

        persistence = InMemoryPersistence()
        service = ApiKeyConfigService(persistence, provider_env_vars=("GROQ_API_KEY",))
        service.load(migrate_env=False)

        count = service._migrate_from_env(())

        assert count == 0
        assert service.get_key("GROQ_API_KEY") is None
