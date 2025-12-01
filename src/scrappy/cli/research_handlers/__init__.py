"""
Research handlers for smart query functionality.

Each handler is responsible for executing research for a specific query intent.
"""

from .base import ResearchHandler
from .registry import ResearchHandlerRegistry, create_default_registry

__all__ = [
    'ResearchHandler',
    'ResearchHandlerRegistry',
    'create_default_registry',
]
