"""
Configuration schema definitions.

Provides dataclasses for configuration values loaded from yaml/json/toml files.
All config classes implement their corresponding Protocol for type safety.

DEPRECATION NOTICE:
ClarificationConfig has been moved to src.task_router.config.
Import from there instead of this module. This re-export will be removed
in a future version.
"""

import warnings


def __getattr__(name: str):
    """Lazy import with deprecation warning for moved classes."""
    if name == "ClarificationConfig":
        warnings.warn(
            "Importing ClarificationConfig from src.config.schema is deprecated. "
            "Import from src.task_router.config instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from src.task_router.config import ClarificationConfig
        return ClarificationConfig

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
