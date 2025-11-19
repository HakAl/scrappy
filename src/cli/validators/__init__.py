"""Input validation layer for CLI.

Provides validators for commands, paths, and providers with length limits,
empty checks, and character validation.

This package maintains backward compatibility - all public symbols can be
imported directly from src.cli.validators.
"""

from .base import ValidationError
from .command import CommandValidationResult, validate_command, VALID_COMMANDS, MAX_COMMAND_LENGTH
from .path import (
    PathValidationResult,
    validate_path,
    MAX_PATH_LENGTH,
    MAX_PATH_COMPONENT_LENGTH,
    WINDOWS_INVALID_CHARS,
    GLOB_CHARS_PATTERN,
)
from .provider import ProviderValidationResult, validate_provider, VALID_PROVIDERS, MAX_PROVIDER_LENGTH

__all__ = [
    'ValidationError',
    'CommandValidationResult', 'validate_command', 'VALID_COMMANDS',
    'PathValidationResult', 'validate_path',
    'ProviderValidationResult', 'validate_provider', 'VALID_PROVIDERS',
]
