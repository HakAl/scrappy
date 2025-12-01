"""
File scanning and categorization for codebase analysis.
"""

import os
from pathlib import Path
from typing import Optional

from .config_loader import get_extensions_config, get_paths_config


class FileScanner:
    """
    Scans project directories and categorizes files by extension.

    Usage:
        scanner = FileScanner()
        file_index = scanner.scan_files("/path/to/project")
        # Returns: {'python': ['main.py', 'src/utils.py'], ...}
    """

    def scan_files(
        self,
        project_path,
        extensions_by_category: Optional[dict] = None,
        skip_dirs: Optional[set] = None
    ) -> dict:
        """
        Scan project directory for source files.

        Args:
            project_path: Path to project root (string or Path object)
            extensions_by_category: Optional custom extension mapping
            skip_dirs: Optional custom set of directories to skip

        Returns:
            Dict mapping category names to lists of relative file paths
        """
        project_path = Path(project_path)

        # Use defaults if not provided
        if extensions_by_category is None:
            extensions_by_category, _ = get_extensions_config()
        if skip_dirs is None:
            skip_dirs = get_paths_config()

        # Initialize result with all categories
        files = {k: [] for k in extensions_by_category}

        # Handle nonexistent path
        if not project_path.exists():
            return files

        # Handle file instead of directory
        if project_path.is_file():
            return files

        for root, dirs, filenames in os.walk(project_path):
            # Filter directories in-place to prevent descending into them
            dirs[:] = [
                d for d in dirs
                if d not in skip_dirs and not d.startswith('.')
            ]

            try:
                rel_root = Path(root).relative_to(project_path)
            except ValueError:
                continue

            for filename in filenames:
                # Skip hidden files
                if filename.startswith('.'):
                    continue

                # Build relative path
                if str(rel_root) != '.':
                    file_path = str(rel_root / filename)
                else:
                    file_path = filename

                # Get extension (case-insensitive)
                ext = Path(filename).suffix.lower()

                # Categorize file
                categorized = False
                for category, exts in extensions_by_category.items():
                    if ext in exts:
                        files[category].append(file_path)
                        categorized = True
                        break

                # Uncategorized files go to 'other'
                if not categorized:
                    files['other'].append(file_path)

        return files
