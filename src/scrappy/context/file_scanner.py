"""
File scanning and categorization for codebase analysis.
"""

import os
import time
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
        skip_dirs: Optional[set] = None,
        timeout_ms: int = 500,
        max_files: int = 10000
    ) -> dict:
        """
        Scan project directory for source files.

        Args:
            project_path: Path to project root (string or Path object)
            extensions_by_category: Optional custom extension mapping
            skip_dirs: Optional custom set of directories to skip
            timeout_ms: Maximum time to spend scanning in milliseconds (default: 500ms)
            max_files: Maximum number of files to scan before bailing (default: 10000)

        Returns:
            Dict mapping category names to lists of relative file paths

        Note:
            If timeout or file limit exceeded, returns partial results.
            Check logs for warnings about incomplete scans.
        """
        project_path = Path(project_path)

        # Use defaults if not provided
        if extensions_by_category is None:
            extensions_by_category, _ = get_extensions_config()
        if skip_dirs is None:
            skip_dirs = get_paths_config()

        # Initialize result with all categories
        files: dict[str, list[str]] = {k: [] for k in extensions_by_category}

        # Handle nonexistent path
        if not project_path.exists():
            return files

        # Handle file instead of directory
        if project_path.is_file():
            return files

        # Start timing for timeout guard
        start_time = time.time()
        timeout_sec = timeout_ms / 1000.0
        total_files_scanned = 0
        hit_timeout = False
        hit_file_limit = False

        for root, dirs, filenames in os.walk(project_path):
            # Check timeout guard
            elapsed = time.time() - start_time
            if elapsed > timeout_sec:
                hit_timeout = True
                break

            # Check file limit guard
            if total_files_scanned >= max_files:
                hit_file_limit = True
                break
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

                # Increment file counter
                total_files_scanned += 1

                # Check file limit again (inner loop check for precision)
                if total_files_scanned > max_files:
                    hit_file_limit = True
                    break

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

            # Check if we broke out of inner loop due to file limit
            if hit_file_limit:
                break

        # Log warnings if guards were triggered
        if hit_timeout:
            import logging
            logging.warning(
                f"FileScanner: timeout after {elapsed:.2f}s, "
                f"scanned {total_files_scanned} files (partial results)"
            )
        if hit_file_limit:
            import logging
            logging.warning(
                f"FileScanner: file limit ({max_files}) exceeded, "
                f"returning partial results"
            )

        return files
