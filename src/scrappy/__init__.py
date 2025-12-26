# Multi-Provider LLM Agent Team
# Extensible framework for orchestrating LLM agents across multiple providers

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("scrappy-ai")
except PackageNotFoundError:
    # Package not installed (e.g., running from source)
    __version__ = "dev"

from .orchestrator_adapter import (
    OrchestratorAdapter,
    AgentOrchestratorAdapter,
    LLMResponse,
    ContextProvider,
    NullContext
)

__all__ = [
    '__version__',
    'OrchestratorAdapter',
    'AgentOrchestratorAdapter',
    'LLMResponse',
    'ContextProvider',
    'NullContext'
]
