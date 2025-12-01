"""
Centralized configuration loading for the context module.

Uses CLIConfig instead of direct imports for better dependency management
and configuration flexibility.
"""

from typing import Dict, List, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from scrappy.cli.cli_config import CLIConfig


def get_truncation_defaults(config: "CLIConfig" = None) -> Dict[str, int]:
    """
    Load truncation limit defaults from config.

    Args:
        config: Optional CLIConfig instance (uses global config if not provided)

    Returns:
        Dict with keys: 'research_large', 'error_message', 'priority_file'
    """
    if config is None:
        # Lazy import to avoid circular dependency
        from scrappy.cli.config_factory import get_config
        config = get_config()

    return config.get_truncation_limits()


def get_extensions_config(config: "CLIConfig" = None) -> Tuple[Dict[str, List[str]], List[str]]:
    """
    Load file extension categories and entry point files from config.

    Args:
        config: Optional CLIConfig instance (uses global config if not provided)

    Returns:
        Tuple of (extensions_by_category dict, entry_point_files list)
    """
    if config is None:
        # Lazy import to avoid circular dependency
        from scrappy.cli.config_factory import get_config
        config = get_config()

    extensions_by_category = config.get_extensions_by_category()
    entry_point_files = config.entry_point_files

    return extensions_by_category, entry_point_files


def get_paths_config(config: "CLIConfig" = None) -> Set[str]:
    """
    Load skip directories from config.

    Args:
        config: Optional CLIConfig instance (uses global config if not provided)

    Returns:
        Set of directory names to skip during scanning
    """
    if config is None:
        # Lazy import to avoid circular dependency
        from scrappy.cli.config_factory import get_config
        config = get_config()

    return config.skip_directories
