#!/usr/bin/env python3
"""
Command-line interface for the LLM Agent Team orchestrator.

This module re-exports from the modular CLI package for backward compatibility.
The actual implementation is in the src/cli/ package.
"""

# Re-export everything from the cli package
from cli import (
    CLI,
    CLIDisplay,
    CLISessionManager,
    CLICodebaseAnalysis,
    CLITaskExecution,
    CLIMultiProvider,
    CLISmartQuery,
    CLIAgentManager,
    cli,
    main,
)

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

if __name__ == "__main__":
    main()
