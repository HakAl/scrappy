"""
CLI package for the LLM Agent Team.
Provides a modular command-line interface with separated concerns.

Uses lazy imports to avoid circular import issues with orchestrator.
"""

from typing import TYPE_CHECKING

# Protocols can be imported eagerly - they don't trigger circular imports
from .protocols import (
    CLIHandlerProtocol,
    DisplayFormatterProtocol,
    InputValidatorProtocol,
    CLIIOProtocol,
)

__all__ = [
    # Implementations (lazy loaded)
    'CLI',
    'CLIDisplay',
    'CLISessionManager',
    'CLICodebaseAnalysis',
    'CLITaskExecution',
    'CLIAgentManager',
    'cli',
    'main',
    # Protocols (eager loaded)
    'CLIHandlerProtocol',
    'CLIIOProtocol',
    'DisplayFormatterProtocol',
    'InputValidatorProtocol',
]

# Lazy import mapping to avoid circular imports
_LAZY_IMPORTS = {
    'CLI': '.core',
    'CLIDisplay': '.display',
    'CLISessionManager': '.session',
    'CLICodebaseAnalysis': '.codebase',
    'CLITaskExecution': '.tasks',
    'CLIAgentManager': '.agent_manager',
    'cli': '.commands',
    'main': '.commands',
}


def __getattr__(name: str):
    """Lazy import handler to avoid circular imports."""
    if name in _LAZY_IMPORTS:
        import importlib
        module_name = _LAZY_IMPORTS[name]
        module = importlib.import_module(module_name, __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    # For static type checkers, provide the types
    from .core import CLI
    from .display import CLIDisplay
    from .session import CLISessionManager
    from .codebase import CLICodebaseAnalysis
    from .tasks import CLITaskExecution
    from .agent_manager import CLIAgentManager
    from .commands import cli, main
