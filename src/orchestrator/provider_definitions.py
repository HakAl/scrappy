"""
Single source of truth for provider definitions.

This module centralizes all provider configuration in one place.
Adding or removing a provider only requires updating the PROVIDERS dict below.
"""

from typing import Type, Dict, List, Optional
from dataclasses import dataclass, field

from src.providers.base import LLMProviderBase
from src.providers.groq_provider import GroqProvider
from src.providers.cerebras_provider import CerebrasProvider
from src.providers.gemini_provider import GeminiProvider
from src.providers.cohere_provider import CohereProvider
from src.providers.github_models_provider import GitHubModelsProvider


@dataclass
class ProviderDefinition:
    """Complete provider definition - single source of truth."""
    quota: str
    description: str
    env_var: str
    console_url: str
    provider_class: Type[LLMProviderBase]
    priority: int = 0
    supports_brain: bool = True
    task_types: List[str] = field(default_factory=list)


PROVIDERS: Dict[str, ProviderDefinition] = {
    'cerebras': ProviderDefinition(
        quota='14,400 RPD',
        description='highest daily quota',
        env_var='CEREBRAS_API_KEY',
        console_url='cloud.cerebras.ai',
        provider_class=CerebrasProvider,
        priority=1,
        supports_brain=True,
        task_types=['planning', 'execution', 'quick', 'general'],
    ),
    'groq': ProviderDefinition(
        quota='7,000 RPD',
        description='fast and reliable',
        env_var='GROQ_API_KEY',
        console_url='console.groq.com/keys',
        provider_class=GroqProvider,
        priority=2,
        supports_brain=True,
        task_types=['planning', 'execution', 'quick', 'general'],
    ),
    'gemini': ProviderDefinition(
        quota='varies',
        description='auto-fallback enabled',
        env_var='GEMINI_API_KEY',
        console_url='aistudio.google.com/apikey',
        provider_class=GeminiProvider,
        priority=3,
        supports_brain=True,
        task_types=['planning', 'execution', 'quick', 'general'],
    ),
    'github_models': ProviderDefinition(
        quota='10K RPD',
        description='general use only - not for agent/brain roles',
        env_var='GITHUB_API_KEY',
        console_url='github.com/settings/tokens',
        provider_class=GitHubModelsProvider,
        priority=4,
        supports_brain=False,
        task_types=['general'],
    ),
    'cohere': ProviderDefinition(
        quota='1,000/month',
        description='limited quota - embeddings only',
        env_var='COHERE_API_KEY',
        console_url='dashboard.cohere.com/api-keys',
        provider_class=CohereProvider,
        priority=99,
        supports_brain=False,
        task_types=[],
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


def get_provider_class(name: str) -> Optional[Type[LLMProviderBase]]:
    """Get provider class by name."""
    if name in PROVIDERS:
        return PROVIDERS[name].provider_class
    return None


def get_env_var(name: str) -> Optional[str]:
    """Get environment variable name for a provider."""
    if name in PROVIDERS:
        return PROVIDERS[name].env_var
    return None


def get_provider_info(name: str) -> Optional[ProviderDefinition]:
    """Get full provider definition by name."""
    return PROVIDERS.get(name)
