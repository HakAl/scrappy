"""
Context package for codebase exploration and management.

This package provides components for:
- File scanning
- Project type detection
- Git history reading
- Context caching
- Platform detection
"""

from .codebase_context import CodebaseContext
from .file_scanner import FileScanner
from .cache import ContextCache
from .project_detector import ProjectDetector
from .platform import PlatformDetector
from .git_history import GitHistoryReader

__all__ = [
    'CodebaseContext',
    'FileScanner',
    'ContextCache',
    'ProjectDetector',
    'PlatformDetector',
    'GitHistoryReader',
]
