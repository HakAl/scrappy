"""
Context package for codebase exploration and management.

This package provides components for:
- File scanning
- Project type detection
- Git history reading
- Context caching
- Platform detection
- Semantic search management
- Context augmentation
"""

from .codebase_context import CodebaseContext
from .file_scanner import FileScanner
from .cache import ContextCache
from .project_detector import ProjectDetector
from .git_history import GitHistoryReader
from .semantic_manager import SemanticSearchManager, NullSemanticSearchManager
from .augmenter import ContextAugmenter, NullContextAugmenter
from .protocols import (
    CodebaseContextProtocol,
    ProjectDetectorProtocol,
    FileScannerProtocol,
    GitHistoryProtocol,
    SemanticSearchManagerProtocol,
    ContextAugmenterProtocol,
)

__all__ = [
    # Implementations
    'CodebaseContext',
    'FileScanner',
    'ContextCache',
    'ProjectDetector',
    'GitHistoryReader',
    'SemanticSearchManager',
    'NullSemanticSearchManager',
    'ContextAugmenter',
    'NullContextAugmenter',
    # Protocols
    'CodebaseContextProtocol',
    'ProjectDetectorProtocol',
    'FileScannerProtocol',
    'GitHistoryProtocol',
    'SemanticSearchManagerProtocol',
    'ContextAugmenterProtocol',
]
