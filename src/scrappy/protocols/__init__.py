"""
Protocol definitions for the scrappy orchestration system.

This module defines the contracts (protocols) that components must follow.
All protocols use structural subtyping (PEP 544) for maximum flexibility.
"""

from .delegation import (
    LLMRequest,
    PromptAugmenterProtocol,
    CacheProtocol,
    RetryOrchestratorProtocol,
    BatchSchedulerProtocol,
    ProviderRegistryProtocol,
    RateLimitTrackerProtocol,
    ContextProviderProtocol,
    WorkingMemoryProtocol,
    OutputInterfaceProtocol,
    ProviderSelectorProtocol,
)

from .output import (
    BaseOutputProtocol,
    FormattedOutputProtocol,
    RichRenderableProtocol,
)

__all__ = [
    # Delegation protocols
    'LLMRequest',
    'PromptAugmenterProtocol',
    'CacheProtocol',
    'RetryOrchestratorProtocol',
    'BatchSchedulerProtocol',
    'ProviderRegistryProtocol',
    'RateLimitTrackerProtocol',
    'ContextProviderProtocol',
    'WorkingMemoryProtocol',
    'OutputInterfaceProtocol',
    'ProviderSelectorProtocol',
    # Output protocols
    'BaseOutputProtocol',
    'FormattedOutputProtocol',
    'RichRenderableProtocol',
]
