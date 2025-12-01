"""
Provider registration for the orchestrator.

Handles auto-registration of all known providers with status tracking.

Design Principles:
- Uses ApiKeyConfigService for config (not os.environ)
- Dependency injection for testability
- No side effects in constructor
"""

from typing import Dict, Optional

try:
    from ..providers import ProviderRegistry
except ImportError:
    from providers import ProviderRegistry

from .output import BaseOutputProtocol
from .protocols import ProviderRegistryProtocol
from .provider_definitions import PROVIDERS


class ProviderRegistrar:
    """
    Handles provider auto-registration.

    Design:
    - Single Responsibility: Only registers providers
    - Dependency Injection: Takes ApiKeyConfigService via constructor
    - Testable: Can inject mock service
    """

    def __init__(
        self,
        registry: ProviderRegistryProtocol,
        output: BaseOutputProtocol,
        config_service: Optional['ApiKeyConfigServiceProtocol'] = None,
    ):
        """
        Initialize the registrar.

        Args:
            registry: Provider registry to register providers with
            output: Output interface for status messages
            config_service: API key config service (uses default if None)
        """
        self.registry = registry
        self.output = output
        self._config_service = config_service or self._create_default_config_service()

    def _create_default_config_service(self) -> 'ApiKeyConfigServiceProtocol':
        """Create default config service."""
        from src.infrastructure.config.api_keys import create_api_key_service
        return create_api_key_service()

    def auto_register_all(self) -> Dict[str, bool]:
        """
        Attempt to register all known providers.

        Gets API keys from config service (NOT os.environ).

        Returns:
            Dict mapping provider name to registration success status
        """
        results = {}

        for name, info in PROVIDERS.items():
            # Get key from config service (NOT os.environ)
            api_key = self._config_service.get_key(info.env_var)
            if not api_key:
                # No key configured, skip this provider
                results[name] = False
                continue

            display_name = name.replace('_', ' ').title()
            success_message = f"{display_name} provider registered ({info.quota})"
            results[name] = self._try_register(
                display_name,
                name,
                info.provider_class,
                success_message,
                api_key=api_key
            )

        return results

    def _try_register(
        self,
        display_name: str,
        key: str,
        provider_class,
        success_message: str,
        api_key: Optional[str] = None
    ) -> bool:
        """
        Try to register a single provider.

        Passes API key directly to provider constructor - NO os.environ.

        Args:
            display_name: Human-readable name for messages
            key: Internal key for the provider
            provider_class: Provider class to instantiate
            success_message: Message to display on success
            api_key: API key to pass to provider constructor

        Returns:
            True if registration succeeded, False otherwise
        """
        try:
            # Pass API key directly to provider constructor - NO os.environ pollution
            provider = provider_class(api_key=api_key) if api_key else provider_class()
            self.registry.register(provider)
            self.output.success(success_message)
            return True
        except Exception:
            # Silent failure - results dict tracks success/failure
            return False
