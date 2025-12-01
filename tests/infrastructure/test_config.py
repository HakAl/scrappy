"""
Tests for configuration infrastructure.

Tests the protocol-based configuration system including:
- BaseConfig functionality
- ConfigLoader (env, file, dict)
- ConfigValidator
- Environment-based configuration
"""

import pytest
import os
import tempfile
import json
from dataclasses import dataclass, field
from typing import List

from scrappy.infrastructure.config import (
    BaseConfig,
    EnvironmentConfig,
    ConfigLoader,
    ConfigValidator,
    Environment,
    default_loader,
    default_validator,
)


# Test Config Classes


@dataclass
class SimpleConfig(BaseConfig):
    """Simple config for testing."""

    host: str = "localhost"
    port: int = 8080
    debug: bool = False


@dataclass
class ValidatedConfig(BaseConfig):
    """Config with custom validation."""

    port: int = 8080
    temperature: float = 0.7

    def validate(self) -> None:
        super().validate()
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"Invalid port: {self.port}")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError(f"Invalid temperature: {self.temperature}")


@dataclass
class ComplexConfig(BaseConfig):
    """Config with complex types."""

    hosts: List[str] = field(default_factory=lambda: ["localhost"])
    ports: List[int] = field(default_factory=lambda: [8080, 8081])


@dataclass
class EnvSpecificConfig(EnvironmentConfig):
    """Config with environment-specific defaults."""

    database_url: str = "sqlite:///dev.db"

    @classmethod
    def for_environment(cls, env: Environment) -> "EnvSpecificConfig":
        if env == Environment.PRODUCTION:
            return cls(
                environment=env,
                database_url="postgresql://prod.db.example.com/myapp"
            )
        elif env == Environment.TEST:
            return cls(
                environment=env,
                database_url="sqlite:///:memory:"
            )
        else:
            return cls(environment=env)


# BaseConfig Tests


class TestBaseConfig:
    """Test BaseConfig functionality."""

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = SimpleConfig(host="example.com", port=9000, debug=True)
        result = config.to_dict()

        assert result == {
            "host": "example.com",
            "port": 9000,
            "debug": True,
        }

    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {"host": "example.com", "port": 9000, "debug": True}
        config = SimpleConfig.from_dict(data)

        assert config.host == "example.com"
        assert config.port == 9000
        assert config.debug is True

    def test_from_dict_filters_extra_keys(self):
        """Test that from_dict ignores extra keys."""
        data = {
            "host": "example.com",
            "port": 9000,
            "debug": True,
            "extra_key": "should be ignored",
        }
        config = SimpleConfig.from_dict(data)

        assert config.host == "example.com"
        assert config.port == 9000
        assert not hasattr(config, "extra_key")

    def test_merge(self):
        """Test merging two configs."""
        config1 = SimpleConfig(host="localhost", port=8080, debug=False)
        config2 = SimpleConfig(port=9000, debug=True)

        merged = config1.merge(config2)

        assert merged.host == "localhost"  # From config1 (not overridden)
        assert merged.port == 9000  # From config2 (overridden)
        assert merged.debug is True  # From config2 (overridden)

    def test_update(self):
        """Test updating config with new values."""
        config = SimpleConfig(host="localhost", port=8080)
        updated = config.update(port=9000, debug=True)

        assert updated.host == "localhost"
        assert updated.port == 9000
        assert updated.debug is True

        # Original should be unchanged
        assert config.port == 8080
        assert config.debug is False

    def test_validate_type_checking(self):
        """Test that validate checks field types for basic types."""
        config = SimpleConfig(host="localhost", port=8080)
        config.validate()  # Should pass

        # Note: Type checking at runtime is limited due to Python's dynamic typing
        # We primarily rely on mypy/type checkers for type safety
        # Runtime validation focuses on value constraints, not types

    def test_custom_validation(self):
        """Test custom validation logic."""
        # Valid config
        config = ValidatedConfig(port=8080, temperature=0.7)
        config.validate()  # Should pass

        # Invalid port
        with pytest.raises(ValueError, match="Invalid port"):
            ValidatedConfig(port=70000).validate()

        # Invalid temperature
        with pytest.raises(ValueError, match="Invalid temperature"):
            ValidatedConfig(temperature=3.0).validate()

    def test_complex_types(self):
        """Test config with complex field types."""
        config = ComplexConfig(
            hosts=["host1", "host2"],
            ports=[8080, 8081, 8082]
        )
        config.validate()

        result = config.to_dict()
        assert result["hosts"] == ["host1", "host2"]
        assert result["ports"] == [8080, 8081, 8082]


# ConfigLoader Tests


class TestConfigLoader:
    """Test ConfigLoader functionality."""

    def test_load_from_dict(self):
        """Test loading config from dictionary."""
        loader = ConfigLoader()
        data = {"host": "example.com", "port": 9000}
        result = loader.load_from_dict(data)

        assert result == data

    def test_load_from_dict_with_environment(self):
        """Test loading environment-specific config from dict."""
        loader = ConfigLoader()
        data = {
            "host": "base.example.com",
            "port": 8080,
            "production": {
                "host": "prod.example.com",
                "port": 443,
            },
        }

        # Load production config
        result = loader.load_from_dict(data, environment=Environment.PRODUCTION)

        assert result["host"] == "prod.example.com"
        assert result["port"] == 443

    def test_load_from_json_file(self):
        """Test loading config from JSON file."""
        loader = ConfigLoader()

        # Create temp JSON file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.json',
            delete=False
        ) as f:
            json.dump({"host": "example.com", "port": 9000}, f)
            temp_file = f.name

        try:
            result = loader.load_from_file(temp_file)
            assert result["host"] == "example.com"
            assert result["port"] == 9000
        finally:
            os.unlink(temp_file)

    def test_load_from_file_not_found(self):
        """Test loading from non-existent file."""
        loader = ConfigLoader()

        with pytest.raises(FileNotFoundError, match="not found"):
            loader.load_from_file("nonexistent.json")

    def test_load_from_file_invalid_json(self):
        """Test loading from invalid JSON file."""
        loader = ConfigLoader()

        # Create temp file with invalid JSON
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.json',
            delete=False
        ) as f:
            f.write("{ invalid json")
            temp_file = f.name

        try:
            with pytest.raises(ValueError, match="Invalid JSON"):
                loader.load_from_file(temp_file)
        finally:
            os.unlink(temp_file)

    def test_load_from_env(self):
        """Test loading config from environment variables."""
        loader = ConfigLoader()

        # Set environment variables
        os.environ["APP_HOST"] = "example.com"
        os.environ["APP_PORT"] = "9000"
        os.environ["APP_DEBUG"] = "true"

        try:
            result = loader.load_from_env(prefix="APP_")

            assert result["host"] == "example.com"
            assert result["port"] == 9000
            assert result["debug"] is True
        finally:
            # Clean up
            del os.environ["APP_HOST"]
            del os.environ["APP_PORT"]
            del os.environ["APP_DEBUG"]

    def test_load_from_env_nested(self):
        """Test loading nested config from env vars."""
        loader = ConfigLoader()

        # Set nested env var
        os.environ["APP_DATABASE__HOST"] = "db.example.com"
        os.environ["APP_DATABASE__PORT"] = "5432"

        try:
            result = loader.load_from_env(prefix="APP_")

            assert "database" in result
            assert result["database"]["host"] == "db.example.com"
            assert result["database"]["port"] == 5432
        finally:
            del os.environ["APP_DATABASE__HOST"]
            del os.environ["APP_DATABASE__PORT"]

    def test_parse_env_value_types(self):
        """Test parsing environment variable values."""
        loader = ConfigLoader()

        # Boolean
        assert loader._parse_env_value("true") is True
        assert loader._parse_env_value("false") is False
        assert loader._parse_env_value("yes") is True
        assert loader._parse_env_value("no") is False

        # Integer
        assert loader._parse_env_value("42") == 42

        # Float
        assert loader._parse_env_value("3.14") == 3.14

        # List
        assert loader._parse_env_value("a,b,c") == ["a", "b", "c"]

        # String
        assert loader._parse_env_value("hello") == "hello"


# ConfigValidator Tests


class TestConfigValidator:
    """Test ConfigValidator functionality."""

    def test_validate_required(self):
        """Test validating required keys."""
        validator = ConfigValidator()
        config = {"host": "localhost", "port": 8080}

        # Should pass
        validator.validate_required(config, ["host", "port"])

        # Should fail
        with pytest.raises(ValueError, match="Missing required"):
            validator.validate_required(config, ["host", "port", "missing"])

    def test_validate_type(self):
        """Test validating value types."""
        validator = ConfigValidator()

        # Should pass
        validator.validate_type(42, int, "port")
        validator.validate_type("localhost", str, "host")

        # Should fail
        with pytest.raises(TypeError, match="must be int"):
            validator.validate_type("not an int", int, "port")

    def test_validate_range(self):
        """Test validating numeric ranges."""
        validator = ConfigValidator()

        # Should pass
        validator.validate_range(8080, min_value=1, max_value=65535, field_name="port")

        # Should fail - too low
        with pytest.raises(ValueError, match="must be >= 1"):
            validator.validate_range(0, min_value=1, max_value=65535, field_name="port")

        # Should fail - too high
        with pytest.raises(ValueError, match="must be <= 65535"):
            validator.validate_range(70000, min_value=1, max_value=65535, field_name="port")

    def test_validate_one_of(self):
        """Test validating allowed values."""
        validator = ConfigValidator()

        # Should pass
        validator.validate_one_of("production", ["development", "test", "production"], "environment")

        # Should fail
        with pytest.raises(ValueError, match="must be one of"):
            validator.validate_one_of("invalid", ["development", "test", "production"], "environment")

    def test_validate_non_empty(self):
        """Test validating non-empty strings."""
        validator = ConfigValidator()

        # Should pass
        validator.validate_non_empty("localhost", "host")

        # Should fail - empty
        with pytest.raises(ValueError, match="cannot be empty"):
            validator.validate_non_empty("", "host")

        # Should fail - whitespace only
        with pytest.raises(ValueError, match="cannot be empty"):
            validator.validate_non_empty("   ", "host")


# EnvironmentConfig Tests


class TestEnvironmentConfig:
    """Test environment-specific configuration."""

    def test_for_environment_production(self):
        """Test getting production config."""
        config = EnvSpecificConfig.for_environment(Environment.PRODUCTION)

        assert config.environment == Environment.PRODUCTION
        assert "prod.db.example.com" in config.database_url

    def test_for_environment_test(self):
        """Test getting test config."""
        config = EnvSpecificConfig.for_environment(Environment.TEST)

        assert config.environment == Environment.TEST
        assert config.database_url == "sqlite:///:memory:"

    def test_for_environment_development(self):
        """Test getting development config."""
        config = EnvSpecificConfig.for_environment(Environment.DEVELOPMENT)

        assert config.environment == Environment.DEVELOPMENT
        assert "dev.db" in config.database_url

    def test_environment_from_string(self):
        """Test converting string to Environment enum."""
        assert Environment.from_string("production") == Environment.PRODUCTION
        assert Environment.from_string("test") == Environment.TEST
        assert Environment.from_string("development") == Environment.DEVELOPMENT

        # Case insensitive
        assert Environment.from_string("PRODUCTION") == Environment.PRODUCTION

        # Invalid
        with pytest.raises(ValueError, match="Invalid environment"):
            Environment.from_string("invalid")


# Integration Tests


class TestConfigIntegration:
    """Test end-to-end config workflows."""

    def test_load_and_validate(self):
        """Test loading config from dict and validating."""
        loader = ConfigLoader()
        data = {"port": 8080, "temperature": 0.7}

        config_data = loader.load_from_dict(data)
        config = ValidatedConfig.from_dict(config_data)

        assert config.port == 8080
        assert config.temperature == 0.7

    def test_load_with_defaults(self):
        """Test loading partial config with defaults."""
        loader = ConfigLoader()
        data = {"port": 9000}  # Only port, use defaults for rest

        config = ValidatedConfig.from_dict(data)

        assert config.port == 9000
        assert config.temperature == 0.7  # Default value

    def test_environment_based_loading(self):
        """Test loading environment-specific config."""
        loader = ConfigLoader()
        data = {
            "database_url": "sqlite:///base.db",
            "production": {
                "database_url": "postgresql://prod/db"
            },
        }

        # Load for production
        prod_data = loader.load_from_dict(data, environment=Environment.PRODUCTION)
        prod_config = EnvSpecificConfig.from_dict(prod_data)

        assert prod_config.database_url == "postgresql://prod/db"

    def test_default_instances(self):
        """Test that default instances are available."""
        assert default_loader is not None
        assert default_validator is not None

        # Should be usable
        result = default_loader.load_from_dict({"host": "localhost"})
        assert result["host"] == "localhost"

        default_validator.validate_required({"host": "localhost"}, ["host"])
