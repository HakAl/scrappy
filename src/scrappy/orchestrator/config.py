"""
Single source of truth for provider configuration.

This module centralizes all provider-related configuration.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from scrappy.infrastructure.config import BaseConfig
from .provider_definitions import (
    PROVIDERS,
    get_provider_priority,
    get_brain_priority,
    get_task_providers,
)


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
        default_factory=get_provider_priority
    )

    # Detailed provider information
    provider_info: Dict[str, ProviderInfo] = field(
        default_factory=lambda: {
            name: ProviderInfo(
                quota=info.quota,
                description=info.description,
            )
            for name, info in PROVIDERS.items()
        }
    )

    # Task-specific provider preferences
    # Order matters - first available provider in list is selected
    task_preferences: Dict[str, List[str]] = field(
        default_factory=lambda: {
            'planning': get_task_providers('planning'),
            'execution': get_task_providers('execution'),
            'quick': get_task_providers('quick'),
            'general': get_task_providers('general'),
        }
    )

    # Default priority for brain selection (excludes problematic providers)
    brain_priority: List[str] = field(
        default_factory=get_brain_priority
    )

    # Fallback priority (same as brain for now)
    fallback_priority: List[str] = field(
        default_factory=get_brain_priority
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
