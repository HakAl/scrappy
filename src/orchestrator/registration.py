"""
Provider registration for the orchestrator.

Handles auto-registration of all known providers with status tracking.
"""

from typing import Dict

try:
    from ..providers import (
        ProviderRegistry,
        GroqProvider,
        CohereProvider,
        GeminiProvider,
        CerebrasProvider,
        GitHubModelsProvider,
    )
except ImportError:
    from providers import (
        ProviderRegistry,
        GroqProvider,
        CohereProvider,
        GeminiProvider,
        CerebrasProvider,
        GitHubModelsProvider,
    )

from .output import OutputInterface
from .protocols import ProviderRegistryProtocol  # For type hints (Dependency Inversion)


class ProviderRegistrar:
    """Handles provider auto-registration."""

    def __init__(self, registry: ProviderRegistryProtocol, output: OutputInterface):
        """
        Initialize the registrar.

        Args:
            registry: Provider registry to register providers with (ProviderRegistryProtocol for DI)
            output: Output interface for status messages
        """
        self.registry = registry
        self.output = output

    def auto_register_all(self) -> Dict[str, bool]:
        """
        Attempt to register all known providers.

        Returns:
            Dict mapping provider name to registration success status
        """
        results = {}

        # Try GitHub Models (RECOMMENDED BRAIN - GPT-4o with 10K RPD)
        results['github_models'] = self._try_register(
            'GitHub Models',
            'github_models',
            GitHubModelsProvider,
            "GitHub Models provider registered (GPT-4o: 10K RPD, 10M TPD)"
        )

        # Try Cerebras (primary workhorse - highest quota)
        results['cerebras'] = self._try_register(
            'Cerebras',
            'cerebras',
            CerebrasProvider,
            "Cerebras provider registered (14,400 RPD)"
        )

        # Try Groq (secondary)
        results['groq'] = self._try_register(
            'Groq',
            'groq',
            GroqProvider,
            "Groq provider registered (7,000 RPD)"
        )

        # Try Gemini (with auto-fallback)
        results['gemini'] = self._try_register(
            'Gemini',
            'gemini',
            GeminiProvider,
            "Gemini provider registered (auto-fallback enabled)"
        )

        # Try Cohere (limited - embeddings only)
        results['cohere'] = self._try_register(
            'Cohere',
            'cohere',
            CohereProvider,
            "Cohere provider registered (1,000/month - use sparingly)"
        )

        return results

    def _try_register(
        self,
        display_name: str,
        key: str,
        provider_class,
        success_message: str
    ) -> bool:
        """
        Try to register a single provider.

        Args:
            display_name: Human-readable name for messages
            key: Internal key for the provider
            provider_class: Provider class to instantiate
            success_message: Message to display on success

        Returns:
            True if registration succeeded, False otherwise
        """
        try:
            provider = provider_class()
            self.registry.register(provider)
            self.output.success(success_message)
            return True
        except Exception as e:
            self.output.error(f"{display_name} provider unavailable: {e}")
            return False
