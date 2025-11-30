# Configuration Infrastructure

## Overview

This document describes the centralized configuration infrastructure that provides:
- **Protocol-based design** for dependency injection and testing
- **Environment-specific configuration** (development, test, production)
- **Validation with clear error messages**
- **Multiple loading sources** (files, environment variables, dictionaries)
- **Type-safe configuration** with dataclasses

## Architecture

The configuration infrastructure follows SOLID principles:

```
infrastructure/config/
├── protocols.py          # ConfigProtocol, ConfigLoaderProtocol, etc.
├── base.py              # BaseConfig, EnvironmentConfig
├── loader.py            # ConfigLoader implementation
├── validator.py         # ConfigValidator implementation
└── __init__.py          # Public API
```

### Key Components

1. **Protocols** (`protocols.py`)
   - `ConfigProtocol`: Base protocol for all configs
   - `ConfigLoaderProtocol`: Protocol for loading configuration
   - `ConfigValidatorProtocol`: Protocol for validation
   - `Environment`: Enum for environment types (dev/test/prod)

2. **Base Classes** (`base.py`)
   - `BaseConfig`: Base class for all configs
   - `EnvironmentConfig`: Base for environment-specific configs

3. **Loader** (`loader.py`)
   - `ConfigLoader`: Loads config from env vars, files, or dicts
   - Supports JSON, YAML, and TOML formats

4. **Validator** (`validator.py`)
   - `ConfigValidator`: Validates config values
   - Provides clear, actionable error messages

## Usage

### Defining a Configuration

```python
from dataclasses import dataclass, field
from typing import List
from infrastructure.config import BaseConfig

@dataclass
class MyConfig(BaseConfig):
    """My application configuration."""

    # Simple fields
    host: str = "localhost"
    port: int = 8080
    debug: bool = False

    # Complex fields
    allowed_hosts: List[str] = field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )

    def validate(self) -> None:
        """Custom validation logic."""
        super().validate()

        # Validate port range
        if self.port < 1 or self.port > 65535:
            raise ValueError(
                f"Port must be between 1 and 65535, got {self.port}"
            )

        # Validate at least one allowed host
        if not self.allowed_hosts:
            raise ValueError("Must have at least one allowed host")
```

### Loading Configuration

#### From Dictionary

```python
from infrastructure.config import ConfigLoader

loader = ConfigLoader()
data = {"host": "example.com", "port": 443, "debug": True}
config_data = loader.load_from_dict(data)
config = MyConfig.from_dict(config_data)
config.validate()
```

#### From Environment Variables

```python
# Set environment variables:
# APP_HOST=example.com
# APP_PORT=443
# APP_DEBUG=true

loader = ConfigLoader()
config_data = loader.load_from_env(prefix="APP_")
config = MyConfig.from_dict(config_data)
```

#### From JSON File

```json
{
  "host": "example.com",
  "port": 443,
  "debug": true
}
```

```python
loader = ConfigLoader()
config_data = loader.load_from_file("config.json")
config = MyConfig.from_dict(config_data)
```

### Environment-Based Configuration

```python
from infrastructure.config import EnvironmentConfig, Environment

@dataclass
class DatabaseConfig(EnvironmentConfig):
    """Database configuration with environment-specific defaults."""

    host: str = "localhost"
    port: int = 5432
    database: str = "myapp"

    @classmethod
    def for_environment(cls, env: Environment) -> "DatabaseConfig":
        if env == Environment.PRODUCTION:
            return cls(
                environment=env,
                host="prod.db.example.com",
                database="myapp_prod"
            )
        elif env == Environment.TEST:
            return cls(
                environment=env,
                host="localhost",
                database="myapp_test"
            )
        else:
            return cls(environment=env)

# Usage
config = DatabaseConfig.for_environment(Environment.PRODUCTION)
```

### Config File with Environment Sections

```json
{
  "host": "localhost",
  "port": 8080,
  "production": {
    "host": "prod.example.com",
    "port": 443
  },
  "test": {
    "host": "test.example.com",
    "port": 8081
  }
}
```

```python
# Load production config
loader = ConfigLoader()
config_data = loader.load_from_file(
    "config.json",
    environment=Environment.PRODUCTION
)
config = MyConfig.from_dict(config_data)
# config.host == "prod.example.com"
# config.port == 443
```

### Validation

```python
from infrastructure.config import ConfigValidator

validator = ConfigValidator()

# Validate required fields
validator.validate_required(
    {"host": "localhost"},
    required_keys=["host", "port"]  # Raises ValueError
)

# Validate types
validator.validate_type(
    value=8080,
    expected_type=int,
    field_name="port"
)

# Validate ranges
validator.validate_range(
    value=8080,
    min_value=1,
    max_value=65535,
    field_name="port"
)

# Validate allowed values
validator.validate_one_of(
    value="production",
    allowed_values=["development", "test", "production"],
    field_name="environment"
)

# Additional validation methods
validator.validate_positive(value=10, field_name="count")
validator.validate_non_negative(value=0, field_name="offset")
validator.validate_non_empty(value="hello", field_name="name")
validator.validate_path_exists(value="/path/to/file", field_name="config_path")
validator.validate_url(value="https://api.example.com", field_name="endpoint", require_https=True)
```

## Migrated Configurations

### AgentConfig (`src/agent_config.py`)

Migrated to extend `BaseConfig`:
- Added comprehensive validation
- Maintains all existing fields
- Backward compatible

```python
from src.agent_config import AgentConfig

config = AgentConfig()
config.validate()  # Validates all constraints
```

### OrchestratorConfig (`src/orchestrator/config.py`)

Migrated to extend `BaseConfig`:
- Provider configuration now in dataclass
- Legacy constants maintained for backward compatibility
- Added validation for provider lists

```python
from src.orchestrator.config import OrchestratorConfig

config = OrchestratorConfig()
reason = config.get_provider_reason("cerebras")
# "14,400 RPD - highest daily quota"
```

### CLIConfig (`src/cli/cli_config.py`)

Consolidated from multiple config modules:
- `src/cli/config/defaults.py`
- `src/cli/config/extensions.py`
- `src/cli/config/paths.py`
- `src/cli/config/patterns.py`

```python
from src.cli.cli_config import CLIConfig

config = CLIConfig()
config.validate()

# Access consolidated config
extensions = config.get_extensions_by_category()
truncation = config.get_truncation_limits()
temperatures = config.get_temperatures()
```

## Testing

Comprehensive test suite in `tests/infrastructure/test_config.py`:

```bash
# Run config tests
python -m pytest tests/infrastructure/test_config.py -v

# Run with coverage
python -m pytest tests/infrastructure/test_config.py --cov=src/infrastructure/config
```

### Test Coverage

- BaseConfig functionality (to_dict, from_dict, merge, update, validate)
- ConfigLoader (env vars, files, dicts, environment-specific loading)
- ConfigValidator (required, type, range, one_of, non_empty)
- EnvironmentConfig (environment-specific defaults)
- Integration tests (end-to-end workflows)

## Migration Guide

### For Existing Code

1. **Import the new base class:**
   ```python
   from infrastructure.config import BaseConfig
   ```

2. **Extend BaseConfig:**
   ```python
   @dataclass
   class YourConfig(BaseConfig):
       # Your fields here
       pass
   ```

3. **Add validation:**
   ```python
   def validate(self) -> None:
       super().validate()
       # Your custom validation
   ```

4. **Load and validate:**
   ```python
   config = YourConfig.from_dict(data)
   config.validate()
   ```

### For New Code

1. Start with `BaseConfig` or `EnvironmentConfig`
2. Define fields with type hints
3. Add custom validation in `validate()` method
4. Use `ConfigLoader` to load from various sources
5. Call `validate()` after loading

## Best Practices

1. **Always call super().validate()** in custom validation
2. **Provide clear error messages** in validation
3. **Use factory functions** for complex default values
4. **Document configuration fields** with docstrings
5. **Test your config validation** with edge cases
6. **Use Environment enum** for environment-specific behavior

## Error Messages

The configuration infrastructure provides clear, actionable error messages:

```
ValueError: Missing required configuration keys: database_url, api_key
Please provide values for: database_url, api_key
```

```
TypeError: Configuration field 'port' must be int, got str: '8080'
Please provide a valid int value.
```

```
ValueError: Configuration field 'port' must be >= 1, got 0
Please provide a value >= 1.
```

## Future Enhancements

Potential improvements:
- Add support for remote config sources (e.g., config servers)
- Add config encryption for sensitive values
- Add config schema validation with JSON Schema
- Add config hot-reloading
- Add config versioning and migration

## References

- [CLAUDE.md](../CLAUDE.md) - Architectural guidelines
