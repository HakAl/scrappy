"""
Provider registration for the orchestrator.

Handles auto-registration of all known providers with status tracking.
"""

from typing import Dict

try:
    from ..providers import ProviderRegistry
except ImportError:
    from providers import ProviderRegistry

from .output import BaseOutputProtocol
from .protocols import ProviderRegistryProtocol
from .provider_definitions import PROVIDERS


class ProviderRegistrar:
    """Handles provider auto-registration."""

    def __init__(self, registry: ProviderRegistryProtocol, output: BaseOutputProtocol):
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

        for name, info in PROVIDERS.items():
            display_name = name.replace('_', ' ').title()
            success_message = f"{display_name} provider registered ({info.quota})"
            results[name] = self._try_register(
                display_name,
                name,
                info.provider_class,
                success_message
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
