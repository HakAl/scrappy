"""
Provider status reporting for the orchestrator.

Handles presentation logic for displaying provider configuration and selection status.
"""

from typing import Optional

from src.orchestrator.protocols import OperationalOutputProtocol



class ProviderStatusReporter:
    """Reports provider status and selection information.

    Handles presentation logic for provider configuration display,
    separating it from the core orchestrator logic.
    """

    # Known providers in the system
    ALL_KNOWN_PROVIDERS = ['github_models', 'cerebras', 'groq', 'gemini', 'cohere']

    # Selection priority order
    SELECTION_PRIORITY = ['cerebras', 'groq', 'gemini']

    def __init__(
        self,
        registry,
        provider_selector,
        output: OperationalOutputProtocol,
        brain_name: Optional[str],
        verbose_selection: bool
    ):
        """Initialize the status reporter.

        Args:
            registry: Provider registry with list_available() method
            provider_selector: Selector with _get_brain_selection_reason() and get_selection_log()
            output: Output interface for displaying messages
            brain_name: Currently selected brain name
            verbose_selection: Whether to show detailed selection log
        """
        self._registry = registry
        self._selector = provider_selector
        self._output = output
        self._brain_name = brain_name
        self._verbose_selection = verbose_selection

    def print_status(self) -> None:
        """Print comprehensive provider status summary."""
        self._output.info("\n" + "=" * 60)
        self._output.info("PROVIDER CONFIGURATION SUMMARY")
        self._output.info("=" * 60)

        available = self._registry.list_available()

        self._output.info("\nProvider Status:")
        for provider_name in self.ALL_KNOWN_PROVIDERS:
            if provider_name in available:
                reason = self._selector._get_brain_selection_reason(provider_name)
                status_str = f"  [OK] {provider_name:<15} - {reason}"
            else:
                status_str = f"  [--] {provider_name:<15} - NOT AVAILABLE (missing API key or package)"
            self._output.info(status_str)

        self._output.info(f"\nSelected Brain: {self._brain_name}")
        if self._brain_name:
            reason = self._selector._get_brain_selection_reason(self._brain_name)
            self._output.info(f"Selection Reason: {reason}")

        self._output.info("\nSelection Priority: cerebras > groq > gemini")
        self._output.info("Use --brain <provider> to override auto-selection")

        if self._verbose_selection and self._selector.get_selection_log():
            self._output.info("\nSelection Log:")
            for entry in self._selector.get_selection_log():
                self._output.info(f"  {entry}")

        self._output.info("=" * 60 + "\n")

    def get_selection_info(self) -> dict:
        """Get detailed provider selection information.

        Returns:
            Dictionary containing:
                - available_providers: List of available provider names
                - all_known_providers: List of all known provider names
                - selected_brain: Currently selected brain name
                - selection_priority: List of providers in priority order
                - provider_details: Dict of provider name to availability info
                - selection_log: List of selection log entries
        """
        available = self._registry.list_available()

        provider_info = {}
        for provider_name in self.ALL_KNOWN_PROVIDERS:
            provider_info[provider_name] = {
                'available': provider_name in available,
                'reason': self._selector._get_brain_selection_reason(provider_name) if provider_name in available else 'not available'
            }

        return {
            'available_providers': available,
            'all_known_providers': self.ALL_KNOWN_PROVIDERS,
            'selected_brain': self._brain_name,
            'selection_priority': self.SELECTION_PRIORITY,
            'provider_details': provider_info,
            'selection_log': self._selector.get_selection_log()
        }
