"""
Single source of truth for provider definitions.

This module centralizes all provider configuration in one place.
Used for setup wizard display and status reporting.

NOTE: Concrete provider classes have been removed in favor of LiteLLM integration.
Routing is now handled by LiteLLM Router with model groups ("fast", "quality").
See orchestrator/litellm_config.py for model group definitions.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field


AGENT_PROVIDER_GUIDANCE = (
    "Recommended for agent work: Cerebras first, Groq second. "
    "Gemini is overflow when you need extra free-tier capacity."
)

SETUP_PROVIDER_GUIDANCE = (
    "Best results: start with Cerebras, add Groq next. "
    "Gemini is useful overflow when free-tier capacity matters."
)


@dataclass
class ProviderDefinition:
    """Provider definition for display and configuration purposes."""
    quota: str
    description: str
    env_var: str
    console_url: str
    priority: int = 0
    supports_brain: bool = True
    task_types: List[str] = field(default_factory=list)


# Provider metadata for setup wizard and status display
# NOTE: Actual routing is handled by LiteLLM Router (see litellm_config.py)
PROVIDERS: Dict[str, ProviderDefinition] = {
    'cerebras': ProviderDefinition(
        quota='14,400 RPD',
        description='best default for agent work',
        env_var='CEREBRAS_API_KEY',
        console_url='cloud.cerebras.ai',
        priority=1,
        supports_brain=True,
        task_types=['planning', 'execution', 'quick', 'general'],
    ),
    'groq': ProviderDefinition(
        quota='7,000 RPD',
        description='fast fallback for agent work',
        env_var='GROQ_API_KEY',
        console_url='console.groq.com/keys',
        priority=2,
        supports_brain=True,
        task_types=['planning', 'execution', 'quick', 'general'],
    ),
    'gemini': ProviderDefinition(
        quota='varies',
        description='overflow option when free-tier capacity matters',
        env_var='GEMINI_API_KEY',
        console_url='aistudio.google.com/apikey',
        priority=3,
        supports_brain=True,
        task_types=['planning', 'execution', 'quick', 'general'],
    ),
    'sambanova': ProviderDefinition(
        quota='varies',
        description='optional extra capacity',
        env_var='SAMBANOVA_API_KEY',
        console_url='cloud.sambanova.ai',
        priority=4,
        supports_brain=True,
        task_types=['planning', 'execution', 'quick', 'general'],
    ),
}


def get_all_provider_names() -> List[str]:
    """All known provider names."""
    return list(PROVIDERS.keys())


def get_provider_priority() -> List[str]:
    """All providers sorted by priority (lowest number = highest priority)."""
    return sorted(PROVIDERS.keys(), key=lambda k: PROVIDERS[k].priority)


def get_brain_priority() -> List[str]:
    """Only providers that can be used as brain, sorted by priority."""
    return [k for k in get_provider_priority() if PROVIDERS[k].supports_brain]


def get_task_providers(task_type: str) -> List[str]:
    """Get providers for a task type, sorted by priority."""
    return [k for k in get_provider_priority()
            if task_type in PROVIDERS[k].task_types]


def get_env_var(name: str) -> Optional[str]:
    """Get environment variable name for a provider."""
    if name in PROVIDERS:
        return PROVIDERS[name].env_var
    return None


def get_provider_info(name: str) -> Optional[ProviderDefinition]:
    """Get full provider definition by name."""
    return PROVIDERS.get(name)
