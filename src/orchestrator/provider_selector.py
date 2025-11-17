"""
Provider selection and routing logic.

Automatically selects the best provider based on task requirements.
"""

from typing import Optional

try:
    from ..providers import ProviderRegistry
except ImportError:
    from providers import ProviderRegistry


class ProviderSelector:
    """
    Handles intelligent provider selection based on task requirements.

    Routing priorities:
    - Cerebras: Primary (14,400 RPD) - fast, high-volume
    - Groq: Secondary (7,000 RPD) - fast, reliable
    - Gemini: Fallback with auto-fallback
    - Cohere: Limited (1,000/month) - embeddings only
    """

    def __init__(self, registry: ProviderRegistry, verbose: bool = False):
        """
        Initialize provider selector.

        Args:
            registry: Provider registry to select from
            verbose: Enable verbose selection logging
        """
        self.registry = registry
        self.verbose = verbose
        self._selection_log = []

    def _log(self, message: str, level: str = "INFO"):
        """Log selection decision with optional verbose output."""
        entry = f"[{level}] {message}"
        self._selection_log.append(entry)
        if self.verbose:
            print(f"  {entry}")

    def get_selection_log(self) -> list[str]:
        """Get the selection decision log."""
        return self._selection_log.copy()

    def clear_selection_log(self):
        """Clear the selection log."""
        self._selection_log.clear()

    def select_for_task(self, task_type: str = 'general') -> tuple[str, Optional[str]]:
        """
        Select the best provider and model for a task type.

        Args:
            task_type: Type of task
                - 'fast': Quick response needed
                - 'quality': Best quality needed
                - 'high_volume': Many requests expected
                - 'embed': Embedding task
                - 'general': General task

        Returns:
            Tuple of (provider_name, model_name or None for default)

        Raises:
            RuntimeError: If no providers available
        """
        self._log(f"Selecting provider for task type: {task_type}")
        available = self.registry.list_available()

        if not available:
            self._log("No providers available!", "ERROR")
            raise RuntimeError("No providers available!")

        self._log(f"Available providers: {', '.join(available)}")

        if task_type in ['fast', 'high_volume', 'general']:
            # Prefer Cerebras (14,400 RPD), then Groq (7,000 RPD)
            if 'cerebras' in available:
                provider = self.registry.get('cerebras')
                model = provider.get_model_for_task(task_type)
                self._log(f"Selected cerebras (14,400 RPD) - highest quota for {task_type}", "SELECTED")
                return ('cerebras', model)
            elif 'groq' in available:
                provider = self.registry.get('groq')
                model = provider.get_model_for_task(task_type)
                self._log(f"Selected groq (7,000 RPD) - cerebras unavailable", "SELECTED")
                return ('groq', model)
            elif 'gemini' in available:
                self._log("Selected gemini - cerebras/groq unavailable", "SELECTED")
                return ('gemini', None)

        elif task_type == 'quality':
            # Use best available large model
            if 'cerebras' in available:
                self._log("Selected cerebras with llama-3.3-70b for quality", "SELECTED")
                return ('cerebras', 'llama-3.3-70b')
            elif 'groq' in available:
                self._log("Selected groq with llama-3.3-70b-versatile for quality", "SELECTED")
                return ('groq', 'llama-3.3-70b-versatile')
            elif 'gemini' in available:
                self._log("Selected gemini for quality", "SELECTED")
                return ('gemini', None)

        elif task_type == 'embed' and 'cohere' in available:
            self._log("Selected cohere for embeddings (1,000/month limit!)", "WARN")
            print("WARNING: Using Cohere. This counts toward 1,000/month limit!")
            return ('cohere', None)

        # Fallback: use first available provider
        self._log(f"Fallback: using {available[0]} (first available)", "SELECTED")
        return (available[0], None)

    def recommend(self, requirements: dict) -> str:
        """
        Recommend best provider based on detailed requirements.

        Args:
            requirements: Dict with keys like:
                - 'speed': 'fast' | 'moderate' | 'slow'
                - 'quality': 'moderate' | 'good' | 'excellent'
                - 'budget_sensitive': bool
                - 'task_count': int (how many similar tasks)

        Returns:
            Recommended provider name

        Raises:
            RuntimeError: If no providers available
        """
        available = self.registry.list_available()

        if not available:
            raise RuntimeError("No providers available!")

        # Budget sensitive -> prefer high-quota providers
        if requirements.get('budget_sensitive', True):
            if 'cerebras' in available:
                return 'cerebras'
            if 'groq' in available:
                return 'groq'

        # High volume -> high-quota providers
        if requirements.get('task_count', 1) > 10:
            if 'cerebras' in available:
                return 'cerebras'
            if 'groq' in available:
                return 'groq'

        # Speed priority -> Cerebras or Groq
        if requirements.get('speed') == 'fast':
            if 'cerebras' in available:
                return 'cerebras'
            if 'groq' in available:
                return 'groq'

        # Quality priority and willing to use quota -> Cohere (but expensive)
        if requirements.get('quality') == 'excellent':
            if 'cohere' in available and not requirements.get('budget_sensitive', True):
                return 'cohere'

        # Default to first available (typically Cerebras)
        return available[0]

    def setup_brain(self, preferred_provider: Optional[str] = None) -> tuple[str, object]:
        """
        Set up the orchestrator's reasoning brain.

        Priority: specified > cerebras > groq > gemini > any available

        Args:
            preferred_provider: Preferred provider name (optional)

        Returns:
            Tuple of (provider_name, provider_instance)

        Raises:
            RuntimeError: If no providers available
        """
        self._log("Setting up orchestrator brain")
        available = self.registry.list_available()

        if not available:
            self._log("No providers available for brain!", "ERROR")
            raise RuntimeError("No providers available for orchestrator brain")

        self._log(f"Available providers: {', '.join(available)}")

        # Use specified provider if available
        if preferred_provider:
            self._log(f"User requested provider: {preferred_provider}")
            if preferred_provider in available:
                provider = self.registry.get(preferred_provider)
                self._log(f"Using user-specified brain: {preferred_provider}", "SELECTED")
                return (preferred_provider, provider)
            else:
                self._log(f"Requested provider {preferred_provider} not available, using auto-selection", "WARN")

        # Default priority: cerebras > groq > gemini
        # NOTE: GitHub Models excluded due to aggressive rate limiting (crashes after ~10 requests)
        # GitHub Models is NOT suitable for orchestrator brain or agent planner roles
        priority = ['cerebras', 'groq', 'gemini']
        self._log(f"Auto-selection priority: {' > '.join(priority)}")

        for provider_name in priority:
            if provider_name in available:
                provider = self.registry.get(provider_name)
                reason = self._get_brain_selection_reason(provider_name)
                self._log(f"Auto-selected brain: {provider_name} ({reason})", "SELECTED")
                return (provider_name, provider)
            else:
                self._log(f"Skipping {provider_name} - not available")

        # Fallback to first available
        provider_name = available[0]
        provider = self.registry.get(provider_name)
        self._log(f"Fallback brain: {provider_name} (first available)", "SELECTED")
        return (provider_name, provider)

    def _get_brain_selection_reason(self, provider_name: str) -> str:
        """Get human-readable reason for brain selection."""
        reasons = {
            'cerebras': '14,400 RPD - highest daily quota',
            'groq': '7,000 RPD - fast and reliable',
            'gemini': 'auto-fallback enabled',
            'cohere': '1,000/month - limited quota',
            'github_models': '10K RPD but aggressive rate limiting'
        }
        return reasons.get(provider_name, 'available')

    def get_provider_for_fallback(self, exclude: list[str] = None) -> Optional[str]:
        """
        Get a fallback provider, excluding specified ones.

        Args:
            exclude: List of provider names to exclude

        Returns:
            Provider name or None if no fallback available
        """
        exclude = exclude or []
        available = self.registry.list_available()

        # Priority order for fallback
        priority = ['cerebras', 'groq', 'gemini']

        for provider_name in priority:
            if provider_name in available and provider_name not in exclude:
                return provider_name

        # Try any available provider not in exclude list
        for provider_name in available:
            if provider_name not in exclude:
                return provider_name

        return None
