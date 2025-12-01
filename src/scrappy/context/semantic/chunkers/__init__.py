"""
Intelligent code chunking strategies.

This subpackage provides AST-aware chunking for supported languages,
with fallback to line-based chunking for unsupported ones.

Main classes:
- PythonASTChunker: Python-specific AST-based chunking
- CompositeCodeChunker: Routes files to appropriate language chunkers
"""

from .python_chunker import PythonASTChunker
from .composite_chunker import CompositeCodeChunker

__all__ = [
    "PythonASTChunker",
    "CompositeCodeChunker",
]
