"""
Textual TUI package for Scrappy CLI.

This package provides the Textual-based terminal user interface components.
"""

from .app import ScrappyApp
from .bridge import ThreadSafeAsyncBridge
from .output_adapter import TextualOutputAdapter
from .messages import (
    WriteOutput,
    WriteRenderable,
    RequestInlineInput,
    IndexingProgress,
    ActivityStateChange,
    TasksUpdated,
    CLIReady,
)
from .status_components import (
    ProgressIndicator,
    TokenCounter,
    PromptDisplay,
    SemanticStatusComponent,
    ActivityIndicator,
    StatusBar,
)

__all__ = [
    # Main app
    "ScrappyApp",
    # Bridge
    "ThreadSafeAsyncBridge",
    # Output adapter
    "TextualOutputAdapter",
    # Messages
    "WriteOutput",
    "WriteRenderable",
    "RequestInlineInput",
    "IndexingProgress",
    "ActivityStateChange",
    "TasksUpdated",
    "CLIReady",
    # Status components
    "ProgressIndicator",
    "TokenCounter",
    "PromptDisplay",
    "SemanticStatusComponent",
    "ActivityIndicator",
    "StatusBar",
]
