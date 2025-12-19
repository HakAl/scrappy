# Multi-Provider LLM Agent Team
# Extensible framework for orchestrating LLM agents across multiple providers

__version__ = "0.1.0"

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
