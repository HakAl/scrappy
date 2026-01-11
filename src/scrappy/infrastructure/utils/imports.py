"""
Centralized import utilities for handling optional dependencies and fallback imports.

This module provides utilities to reduce import duplication across the codebase.
"""

import sys
from pathlib import Path
from typing import Any, Optional, Tuple


def safe_import(
    module_name: str,
    package_name: Optional[str] = None,
    install_name: Optional[str] = None
) -> Tuple[Any, bool]:
    """
    Safely import an optional module with helpful error message if missing.

    Args:
        module_name: The module to import (e.g., 'groq', 'aiofiles')
        package_name: Optional package name if different from module_name
        install_name: Optional pip package name if different from module_name

    Returns:
        Tuple of (module or None, is_available: bool)

    Example:
        groq, GROQ_AVAILABLE = safe_import('groq')
        aiofiles, AIOFILES_AVAILABLE = safe_import('aiofiles')
    """
    try:
        module = __import__(module_name)
        # Handle submodule imports (e.g., 'google.generativeai')
        for part in module_name.split('.')[1:]:
            module = getattr(module, part)
        return module, True
    except ImportError:
        return None, False


def require_import(
    module_name: str,
    package_name: Optional[str] = None,
    install_name: Optional[str] = None
) -> Any:
    """
    Import a module that is required, raising ImportError with helpful message if missing.

    Args:
        module_name: The module to import
        package_name: Optional package display name if different from module_name
        install_name: Optional pip package name if different from module_name

    Returns:
        The imported module

    Raises:
        ImportError: If module is not available, with helpful installation message

    Example:
        groq = require_import('groq')
        genai = require_import('google.generativeai', 'google-generativeai')
    """
    module, available = safe_import(module_name, package_name, install_name)
    if not available:
        pip_name = install_name or package_name or module_name
        raise ImportError(
            f"{package_name or module_name} package not installed. "
            f"Run: pip install {pip_name}"
        )
    return module


def setup_src_path() -> None:
    """
    Add the src directory to Python path for relative imports.

    This is used when running modules directly instead of as part of the package.
    """
    src_dir = str(Path(__file__).parent.parent.parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)


def setup_root_path() -> None:
    """
    Add the project root directory to Python path.

    This is used when running modules directly instead of as part of the package.
    """
    root_dir = str(Path(__file__).parent.parent.parent.parent)
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)


def import_with_fallback(
    primary_import: str,
    fallback_import: str,
    from_package: Optional[str] = None
) -> Any:
    """
    Try to import from primary location, falling back to alternative if needed.

    This handles the common pattern of trying relative imports first, then absolute.

    Args:
        primary_import: Primary import path (e.g., '..providers')
        fallback_import: Fallback import path (e.g., 'providers')
        from_package: Optional package context for relative imports

    Returns:
        The imported module

    Example:
        providers = import_with_fallback('..providers', 'providers')
    """
    try:
        if primary_import.startswith('.'):
            # This is a relative import, needs special handling
            parts = primary_import.lstrip('.').split('.')
            level = len(primary_import) - len(primary_import.lstrip('.'))
            module = __import__(
                parts[0] if parts else '',
                globals(),
                locals(),
                [parts[-1]] if len(parts) > 1 else [],
                level
            )
            for part in parts[1:]:
                module = getattr(module, part)
            return module
        else:
            return __import__(primary_import)
    except ImportError:
        setup_src_path()
        module = __import__(fallback_import)
        return module


# Pre-configured optional dependency checkers
def get_aiofiles():
    """Get aiofiles module if available."""
    return safe_import('aiofiles')


def get_httpx():
    """Get httpx module if available."""
    return safe_import('httpx')


def get_click():
    """Get click module if available."""
    return safe_import('click')


def get_beautifulsoup():
    """Get BeautifulSoup from bs4 if available."""
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup, True
    except ImportError:
        return None, False
