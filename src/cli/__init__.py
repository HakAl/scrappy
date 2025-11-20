"""
CLI package for the LLM Agent Team.
Provides a modular command-line interface with separated concerns.
"""

from .core import CLI
from .display import CLIDisplay
from .session import CLISessionManager
from .codebase import CLICodebaseAnalysis
from .tasks import CLITaskExecution
from .multiprovider import CLIMultiProvider
from .smart_query import CLISmartQuery
from .agent_manager import CLIAgentManager
from .commands import cli, main
from .protocols import (
    CLIHandlerProtocol,
    DisplayFormatterProtocol,
    InputValidatorProtocol,
)
from .io_interface import CLIIOProtocol

__all__ = [
    # Implementations
    'CLI',
    'CLIDisplay',
    'CLISessionManager',
    'CLICodebaseAnalysis',
    'CLITaskExecution',
    'CLIMultiProvider',
    'CLISmartQuery',
    'CLIAgentManager',
    'cli',
    'main',
    # Protocols
    'CLIHandlerProtocol',
    'CLIIOProtocol',
    'DisplayFormatterProtocol',
    'InputValidatorProtocol',
]
