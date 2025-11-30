"""
Single source of truth for provider configuration.

This module centralizes all provider-related configuration that was previously
scattered across provider_selector.py and rate_limiter.py.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from src.infrastructure.config import BaseConfig


@dataclass
class ProviderInfo:
    """Information about a provider."""

    quota: str
    description: str


@dataclass
class OrchestratorConfig(BaseConfig):
    """Configuration for the orchestrator and provider management."""

    # Provider priority order for general use
    # Note: Providers with supports_agent_role=False are filtered out for brain/agent roles
    provider_priority: List[str] = field(
        default_factory=lambda: ['cerebras', 'groq', 'gemini', 'cohere', 'github_models']
    )

    # Detailed provider information
    provider_info: Dict[str, ProviderInfo] = field(
        default_factory=lambda: {
            'cerebras': ProviderInfo(
                quota='14,400 RPD',
                description='highest daily quota',
            ),
            'groq': ProviderInfo(
                quota='7,000 RPD',
                description='fast and reliable',
            ),
            'gemini': ProviderInfo(
                quota='varies',
                description='auto-fallback enabled',
            ),
            'cohere': ProviderInfo(
                quota='1,000/month',
                description='limited quota - embeddings only',
            ),
            'github_models': ProviderInfo(
                quota='10K RPD',
                description='general use only - not for agent/brain roles',
            ),
        }
    )

    # Task-specific provider preferences
    # Order matters - first available provider in list is selected
    task_preferences: Dict[str, List[str]] = field(
        default_factory=lambda: {
            'planning': ['cerebras', 'groq', 'gemini'],
            'execution': ['cerebras', 'groq', 'gemini'],
            'quick': ['cerebras', 'groq'],
            'general': ['cerebras', 'groq', 'gemini'],
        }
    )

    # Default priority for brain selection (excludes problematic providers)
    brain_priority: List[str] = field(
        default_factory=lambda: ['cerebras', 'groq', 'gemini']
    )

    # Fallback priority (same as brain for now)
    fallback_priority: List[str] = field(
        default_factory=lambda: ['cerebras', 'groq', 'gemini']
    )

    def get_provider_reason(self, provider_name: str) -> str:
        """
        Get human-readable reason for provider selection.

        Args:
            provider_name: Name of the provider

        Returns:
            Description string explaining why this provider was selected
        """
        if provider_name not in self.provider_info:
            return 'available'

        info = self.provider_info[provider_name]
        return f"{info.quota} - {info.description}"

    def validate(self) -> None:
        """
        Validate OrchestratorConfig values.

        Raises:
            ValueError: If configuration is invalid
        """
        super().validate()

        # Validate provider lists are not empty
        if not self.provider_priority:
            raise ValueError("provider_priority cannot be empty")

        if not self.brain_priority:
            raise ValueError("brain_priority cannot be empty")

        if not self.fallback_priority:
            raise ValueError("fallback_priority cannot be empty")

        # Validate task preferences
        if not self.task_preferences:
            raise ValueError("task_preferences cannot be empty")

        for task, providers in self.task_preferences.items():
            if not providers:
                raise ValueError(f"task_preferences['{task}'] cannot be empty")

def get_provider_reason(provider_name: str) -> str:
    """
    Get human-readable reason for provider selection.

    DEPRECATED: Use OrchestratorConfig.get_provider_reason() instead.

    Args:
        provider_name: Name of the provider

    Returns:
        Description string explaining why this provider was selected
    """
    return _default_config.get_provider_reason(provider_name)
