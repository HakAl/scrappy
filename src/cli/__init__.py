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

__all__ = [
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
]
