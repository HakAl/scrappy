"""
LLM Agent Orchestrator Package

Provides coordination layer for multi-provider LLM agent teams.

Architecture:
    Claude Code (complex reasoning) <-- Human/Orchestrator
           |
           v
    Orchestrator (this package)
           |
    +------+------+------+
    |      |      |      |
    v      v      v      v
   Groq  Cohere  [Future providers...]
  (fast) (embed) (OpenRouter, HuggingFace, etc.)

The orchestrator:
1. Maintains a registry of available providers
2. Routes tasks to appropriate providers based on task type
3. Tracks usage and rate limits across providers
4. Provides fallback strategies when limits are hit

NOTE: This module uses lazy imports to avoid 2s+ startup delay.
Import directly from submodules for best performance:
    from scrappy.orchestrator.core import AgentOrchestrator
    from scrappy.orchestrator.protocols import CacheProtocol
"""

# Define what's exported - actual imports are lazy
__all__ = [
    # Core implementations
    'AgentOrchestrator',
    'create_orchestrator',
    'ResponseCache',
    'RateLimitTracker',
    'WorkingMemory',
    'SessionManager',
    'TaskExecutor',
    'ProviderSelector',
    'ContextManager',
    # Protocols
    'Orchestrator',
    'CacheProtocol',
    'RateLimitTrackerProtocol',
    'SessionManagerProtocol',
    'ProviderSelectorProtocol',
    'ProviderRegistryProtocol',
    'WorkingMemoryProtocol',
    'BaseOutputProtocol',
    'ContextProvider',
    'OrchestratorAdapter',
    'DelegationManagerProtocol',
    'TaskExecutorProtocol',
    'BackgroundTaskManagerProtocol',
    'UsageReporterProtocol',
    'StatusReporterProtocol',
    'ContextManagerProtocol',
]

# Mapping of names to their source modules
_LAZY_IMPORTS = {
    # Core implementations
    'AgentOrchestrator': '.core',
    'create_orchestrator': '.core',
    'ResponseCache': '.cache',
    'RateLimitTracker': '.rate_limiting',
    'WorkingMemory': '.memory',
    'SessionManager': '.session',
    'TaskExecutor': '.task_executor',
    'ProviderSelector': '.provider_selector',
    'ContextManager': '.context_coordinator',  # aliased from ContextCoordinator
    # Protocols
    'Orchestrator': '.protocols',
    'CacheProtocol': '.protocols',
    'RateLimitTrackerProtocol': '.protocols',
    'SessionManagerProtocol': '.protocols',
    'ProviderSelectorProtocol': '.protocols',
    'ProviderRegistryProtocol': '.protocols',
    'WorkingMemoryProtocol': '.protocols',
    'BaseOutputProtocol': '.protocols',
    'ContextProvider': '.protocols',
    'OrchestratorAdapter': '.protocols',
    # Manager protocols
    'DelegationManagerProtocol': '.manager_protocols',
    'TaskExecutorProtocol': '.manager_protocols',
    'BackgroundTaskManagerProtocol': '.manager_protocols',
    'UsageReporterProtocol': '.manager_protocols',
    'StatusReporterProtocol': '.manager_protocols',
    'ContextManagerProtocol': '.manager_protocols',
}


def __getattr__(name: str):
    """Lazy load imports to avoid startup delay."""
    if name in _LAZY_IMPORTS:
        module_name = _LAZY_IMPORTS[name]
        import importlib
        module = importlib.import_module(module_name, __package__)

        # Handle the ContextManager alias
        if name == 'ContextManager':
            value = getattr(module, 'ContextCoordinator')
        else:
            value = getattr(module, name)

        # Cache in globals for subsequent access
        globals()[name] = value
        return value

    raise AttributeError(f"module 'scrappy.orchestrator' has no attribute '{name}'")
