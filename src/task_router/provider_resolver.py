"""
Provider hint resolution utility.

Resolves provider hints (fast, quality, etc.) to actual provider names and models.
"""

from typing import Optional, Tuple, Any


class ProviderResolver:
    """
    Utility for resolving provider hints to actual provider names and models.

    Provider hints are semantic descriptors like "fast", "quality", "high_volume"
    that map to specific providers and models based on availability and characteristics.

    Priority ordering:
    - Fast hints: cerebras > groq > gemini (no specific model)
    - Quality hints: cerebras (70B) > groq (70B) > gemini (default)

    Usage:
        resolver = ProviderResolver(orchestrator)
        provider, model = resolver.resolve("fast")
        # Returns: ("cerebras", None) if cerebras is available

    Args:
        orchestrator: LLM orchestrator with providers attribute
        use_provider_selector: Whether to try using ProviderSelector (default: True)
    """

    def __init__(
        self,
        orchestrator: Optional[Any] = None,
        use_provider_selector: bool = True
    ):
        """
        Initialize provider resolver.

        Args:
            orchestrator: Orchestrator instance with providers attribute
            use_provider_selector: Whether to attempt using ProviderSelector
        """
        self.orchestrator = orchestrator
        self.use_provider_selector = use_provider_selector

    def resolve(self, hint: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve provider hint to actual provider name and model.

        Args:
            hint: Provider hint ("fast", "quality", "high_volume", "general") or None

        Returns:
            Tuple of (provider_name, model_name) or (None, None) if no resolution

        Examples:
            >>> resolver = ProviderResolver(orchestrator)
            >>> resolver.resolve("fast")
            ("cerebras", None)

            >>> resolver.resolve("quality")
            ("cerebras", "llama-3.3-70b")
        """
        # Validate inputs
        if not hint or not self.orchestrator:
            return (None, None)

        # Handle non-string hints
        if not isinstance(hint, str):
            return (None, None)

        # Try ProviderSelector first if enabled
        if self.use_provider_selector:
            result = self._try_provider_selector(hint)
            if result != (None, None):
                return result

        # Fallback to simple mapping
        return self._resolve_with_simple_mapping(hint)

    def _try_provider_selector(self, hint: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Try to use ProviderSelector for resolution.

        Args:
            hint: Provider hint

        Returns:
            Tuple of (provider_name, model_name) or (None, None) if failed
        """
        try:
            if hasattr(self.orchestrator, 'providers'):
                from ..orchestrator.provider_selector import ProviderSelector
                selector = ProviderSelector(self.orchestrator.providers)
                return selector.select_for_task(hint)
        except Exception:
            # Silently fall back to simple mapping
            pass

        return (None, None)

    def _resolve_with_simple_mapping(self, hint: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve provider using simple hint-to-provider mapping.

        Args:
            hint: Provider hint

        Returns:
            Tuple of (provider_name, model_name) or (None, None)
        """
        # Get available providers
        available = self._get_available_providers()

        # Map hints to providers
        if hint in ['fast', 'high_volume', 'general']:
            return self._resolve_fast_hint(available)
        elif hint == 'quality':
            return self._resolve_quality_hint(available)

        # Unknown hint
        return (None, None)

    def _get_available_providers(self) -> list:
        """
        Get list of available providers from orchestrator.

        Returns:
            List of provider names, or empty list if unavailable
        """
        try:
            if hasattr(self.orchestrator, 'providers'):
                if hasattr(self.orchestrator.providers, 'list_available'):
                    return self.orchestrator.providers.list_available()
        except Exception:
            pass

        return []

    def _resolve_fast_hint(self, available: list) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve fast/high_volume/general hints.

        Prefers: cerebras > groq > gemini

        Args:
            available: List of available provider names

        Returns:
            Tuple of (provider_name, None) or (None, None)
        """
        # Priority: cerebras > groq > gemini
        if 'cerebras' in available:
            return ('cerebras', None)
        elif 'groq' in available:
            return ('groq', None)
        elif 'gemini' in available:
            return ('gemini', None)

        return (None, None)

    def _resolve_quality_hint(self, available: list) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve quality hint.

        Uses 70B models when available.
        Prefers: cerebras (70B) > groq (70B) > gemini

        Args:
            available: List of available provider names

        Returns:
            Tuple of (provider_name, model_name) or (None, None)
        """
        # Priority with specific models
        if 'cerebras' in available:
            return ('cerebras', 'llama-3.3-70b')
        elif 'groq' in available:
            return ('groq', 'llama-3.3-70b-versatile')
        elif 'gemini' in available:
            return ('gemini', None)

        return (None, None)
