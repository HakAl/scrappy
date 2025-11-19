"""
Centralized configuration loading for the context module.

Consolidates all configuration imports with fallbacks to avoid duplication
across file_scanner.py and codebase_context.py.
"""

from typing import Dict, List, Set, Tuple


def get_truncation_defaults() -> Dict[str, int]:
    """
    Load truncation limit defaults from config.

    Returns:
        Dict with keys: 'research_large', 'error_message', 'priority_file'
    """
    try:
        from src.cli.config.defaults import (
            TRUNCATE_RESEARCH_LARGE,
            TRUNCATE_ERROR_MESSAGE,
            TRUNCATE_PRIORITY_FILE,
        )
    except ImportError:
        try:
            from cli.config.defaults import (
                TRUNCATE_RESEARCH_LARGE,
                TRUNCATE_ERROR_MESSAGE,
                TRUNCATE_PRIORITY_FILE,
            )
        except ImportError:
            # Fallback values if imports fail
            TRUNCATE_RESEARCH_LARGE = 1500
            TRUNCATE_ERROR_MESSAGE = 500
            TRUNCATE_PRIORITY_FILE = 3000

    return {
        'research_large': TRUNCATE_RESEARCH_LARGE,
        'error_message': TRUNCATE_ERROR_MESSAGE,
        'priority_file': TRUNCATE_PRIORITY_FILE,
    }


def get_extensions_config() -> Tuple[Dict[str, List[str]], List[str]]:
    """
    Load file extension categories and entry point files from config.

    Returns:
        Tuple of (extensions_by_category dict, entry_point_files list)
    """
    try:
        from src.cli.config.extensions import EXTENSIONS_BY_CATEGORY, ENTRY_POINT_FILES
    except ImportError:
        try:
            from cli.config.extensions import EXTENSIONS_BY_CATEGORY, ENTRY_POINT_FILES
        except ImportError:
            # Fallback values if imports fail
            EXTENSIONS_BY_CATEGORY = {
                'python': ['.py'],
                'javascript': ['.js', '.jsx', '.ts', '.tsx'],
                'web': ['.html', '.css', '.scss'],
                'config': ['.json', '.yaml', '.yml', '.toml', '.ini'],
                'docs': ['.md', '.rst', '.txt'],
                'other': []
            }
            ENTRY_POINT_FILES = [
                'main.py', '__main__.py', 'app.py', 'cli.py', 'setup.py'
            ]

    return EXTENSIONS_BY_CATEGORY, ENTRY_POINT_FILES


def get_paths_config() -> Set[str]:
    """
    Load skip directories from config.

    Returns:
        Set of directory names to skip during scanning
    """
    try:
        from src.cli.config.paths import SKIP_DIRS
    except ImportError:
        try:
            from cli.config.paths import SKIP_DIRS
        except ImportError:
            # Fallback values if imports fail
            SKIP_DIRS = {
                '.git', '__pycache__', 'node_modules', '.venv',
                'venv', 'env', '.env', 'dist', 'build'
            }

    return SKIP_DIRS
