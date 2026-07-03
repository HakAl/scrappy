# Multi-Provider LLM Agent Team
# Extensible framework for orchestrating LLM agents across multiple providers
#
# NOTE: This module uses lazy imports to avoid 2s+ startup delay.
# Heavy imports (orchestrator, providers) are only loaded when accessed.

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("scrappy-ai")
except PackageNotFoundError:
    # Package not installed (e.g., running from source)
    __version__ = "dev"


# Lazy imports for heavy modules - only loaded when accessed
def __getattr__(name: str):
    """Lazy load heavy imports to avoid startup delay."""
    if name in ('OrchestratorAdapter', 'AgentOrchestratorAdapter',
                'LLMResponse', 'ContextProvider', 'NullContext'):
        from .orchestrator.protocols import ContextProvider, OrchestratorAdapter
        from .orchestrator.provider_types import LLMResponse
        from .orchestrator_adapter import AgentOrchestratorAdapter, NullContext
        # Cache in module globals for subsequent access
        globals().update({
            'OrchestratorAdapter': OrchestratorAdapter,
            'AgentOrchestratorAdapter': AgentOrchestratorAdapter,
            'LLMResponse': LLMResponse,
            'ContextProvider': ContextProvider,
            'NullContext': NullContext,
        })
        return globals()[name]
    raise AttributeError(f"module 'scrappy' has no attribute '{name}'")


__all__ = [
    '__version__',
    'OrchestratorAdapter',
    'AgentOrchestratorAdapter',
    'LLMResponse',
    'ContextProvider',
    'NullContext'
]
