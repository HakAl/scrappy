"""
Infrastructure utility functions.

Provides common utilities used across the infrastructure layer.
"""

from .imports import (
    safe_import,
    require_import,
    setup_src_path,
    setup_root_path,
    import_with_fallback,
    get_aiofiles,
    get_httpx,
    get_click,
    get_beautifulsoup,
)
from .errors import (
    ErrorFormatter,
    LogPrefix,
    raise_package_not_installed,
    raise_env_var_not_found,
    raise_model_not_supported,
    raise_provider_not_available,
    raise_no_providers_available,
    raise_operation_failed,
    is_rate_limit_error,
)

__all__ = [
    # Import utilities
    "safe_import",
    "require_import",
    "setup_src_path",
    "setup_root_path",
    "import_with_fallback",
    "get_aiofiles",
    "get_httpx",
    "get_click",
    "get_beautifulsoup",
    # Error utilities
    "ErrorFormatter",
    "LogPrefix",
    "raise_package_not_installed",
    "raise_env_var_not_found",
    "raise_model_not_supported",
    "raise_provider_not_available",
    "raise_no_providers_available",
    "raise_operation_failed",
    "is_rate_limit_error",
]
