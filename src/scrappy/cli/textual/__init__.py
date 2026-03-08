"""
Textual TUI package for Scrappy CLI.

This package provides the Textual-based terminal user interface components.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

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
    "MetricsUpdate",
    "TasksUpdated",
    "CLIReady",
    "CancelRequested",
    # Status components
    "ProgressIndicator",
    "TokenCounter",
    "ProviderStatus",
    "MetricsStatus",
    "PromptDisplay",
    "SemanticStatusComponent",
    "ActivityIndicator",
    "StatusBar",
]

_EXPORTS = {
    "ScrappyApp": (".app", "ScrappyApp"),
    "ThreadSafeAsyncBridge": (".bridge", "ThreadSafeAsyncBridge"),
    "TextualOutputAdapter": (".output_adapter", "TextualOutputAdapter"),
    "WriteOutput": (".messages", "WriteOutput"),
    "WriteRenderable": (".messages", "WriteRenderable"),
    "RequestInlineInput": (".messages", "RequestInlineInput"),
    "IndexingProgress": (".messages", "IndexingProgress"),
    "ActivityStateChange": (".messages", "ActivityStateChange"),
    "MetricsUpdate": (".messages", "MetricsUpdate"),
    "TasksUpdated": (".messages", "TasksUpdated"),
    "CLIReady": (".messages", "CLIReady"),
    "CancelRequested": (".messages", "CancelRequested"),
    "ProgressIndicator": (".status_components", "ProgressIndicator"),
    "TokenCounter": (".status_components", "TokenCounter"),
    "ProviderStatus": (".status_components", "ProviderStatus"),
    "MetricsStatus": (".status_components", "MetricsStatus"),
    "PromptDisplay": (".status_components", "PromptDisplay"),
    "SemanticStatusComponent": (".status_components", "SemanticStatusComponent"),
    "ActivityIndicator": (".status_components", "ActivityIndicator"),
    "StatusBar": (".status_components", "StatusBar"),
}


def __getattr__(name: str) -> Any:
    """Lazily load Textual exports to avoid package import cycles."""
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy exports in introspection."""
    return sorted(set(globals()) | set(__all__))
