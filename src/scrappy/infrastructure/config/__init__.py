"""
Configuration infrastructure for the application.

Provides a protocol-based, dependency-injectable configuration system
with support for environment-specific configs, validation, and multiple
loading sources (env vars, files, dicts).

Usage:
    # Define a config
    from dataclasses import dataclass
    from infrastructure.config import BaseConfig, Environment

    @dataclass
    class DatabaseConfig(BaseConfig):
        host: str = "localhost"
        port: int = 5432
        database: str = "myapp"

        def validate(self) -> None:
            super().validate()
            if self.port < 1 or self.port > 65535:
                raise ValueError(f"Invalid port: {self.port}")

    # Load config
    from infrastructure.config import ConfigLoader

    loader = ConfigLoader()
    config_data = loader.load_from_file("config.json", Environment.PRODUCTION)
    config = DatabaseConfig.from_dict(config_data)

    # Validate
    config.validate()

    # Use config
    print(f"Connecting to {config.host}:{config.port}")
"""

from .protocols import (
    ConfigProtocol,
    ConfigLoaderProtocol,
    ConfigValidatorProtocol,
    ConfigSourceProtocol,
    Environment,
)
from .base import BaseConfig, EnvironmentConfig
from .validator import ConfigValidator, default_validator
from .loader import ConfigLoader, default_loader

__all__ = [
    # Protocols
    'ConfigProtocol',
    'ConfigLoaderProtocol',
    'ConfigValidatorProtocol',
    'ConfigSourceProtocol',
    'Environment',
    # Base classes
    'BaseConfig',
    'EnvironmentConfig',
    # Implementations
    'ConfigValidator',
    'ConfigLoader',
    # Default instances
    'default_validator',
    'default_loader',
]
