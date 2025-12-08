"""
Provider selection and routing logic.

Automatically selects the best provider based on task requirements.
"""

from typing import Optional, List, Tuple

try:
    from ..providers import ProviderRegistry
    from ..providers.base import ModelType, SpeedRank, QualityRank
except ImportError:
    from providers import ProviderRegistry
    from providers.base import ModelType, SpeedRank, QualityRank

from .output import BaseOutputProtocol, ConsoleOutput
from .config import OrchestratorConfig
from .protocols import ProviderRegistryProtocol  # For type hints (Dependency Inversion)
from .model_selection import ModelSelectionType


class ProviderSelector:
    """
    Handles intelligent provider selection based on task requirements.

    Routing priorities:
    - Cerebras: Primary (14,400 RPD) - fast, high-volume
    - Groq: Secondary (7,000 RPD) - fast, reliable
    - Gemini: Fallback with auto-fallback
    - Cohere: Limited (1,000/month) - embeddings only
    """

    def __init__(
        self,
        registry: ProviderRegistryProtocol,
        verbose: bool = False,
        output: Optional[BaseOutputProtocol] = None,
        config: Optional[OrchestratorConfig] = None
    ):
        """
        Initialize provider selector.

        Args:
            registry: Provider registry to select from (ProviderRegistryProtocol for DI)
            verbose: Enable verbose selection logging
            output: Output interface for messages (default: ConsoleOutput)
            config: OrchestratorConfig instance (creates default if None)
        """
        self.registry = registry
        self.verbose = verbose
        self.output = output or ConsoleOutput()
        self.config = config or OrchestratorConfig()
        self._selection_log = []

    def _log(self, message: str, level: str = "INFO"):
        """Log selection decision with optional verbose output."""
        entry = f"[{level}] {message}"
        self._selection_log.append(entry)
        if self.verbose:
            self.output.info(f"  {entry}")

    def get_selection_log(self) -> list[str]:
        """Get the selection decision log."""
        return self._selection_log.copy()

    def clear_selection_log(self):
        """Clear the selection log."""
        self._selection_log.clear()

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
        Set up the orchestrator's reasoning brain using QUALITY selection.

        Priority: specified > QUALITY selection > config priority > any available

        Args:
            preferred_provider: Preferred provider name (optional)

        Returns:
            Tuple of (provider_name, provider_instance)

        Raises:
            RuntimeError: If no providers available
        """
        from .model_selection import ModelSelectionType

        self._log("Setting up orchestrator brain")
        available = self.registry.list_available()

        if not available:
            self._log("No providers available for brain!", "ERROR")
            raise RuntimeError("No providers available for orchestrator brain")

        self._log(f"Available providers: {', '.join(available)}")

        # Use specified provider if available and supports agent role
        if preferred_provider:
            self._log(f"User requested provider: {preferred_provider}")
            if preferred_provider in available:
                provider = self.registry.get(preferred_provider)
                # Check if provider supports agent/brain role
                if hasattr(provider, 'supports_agent_role') and not provider.supports_agent_role:
                    self._log(
                        f"{preferred_provider} does not support agent/brain roles (aggressive rate limiting)",
                        "WARN"
                    )
                    self._log("Falling back to auto-selection...", "WARN")
                else:
                    self._log(f"Using user-specified brain: {preferred_provider}", "SELECTED")
                    return (preferred_provider, provider)
            else:
                self._log(f"Requested provider {preferred_provider} not available, using auto-selection", "WARN")

        # Try QUALITY selection for best reasoning capability
        try:
            provider_name, model = self.get_model(ModelSelectionType.QUALITY)
            if provider_name:
                provider = self.registry.get(provider_name)
                # Verify provider supports agent/brain role
                if hasattr(provider, 'supports_agent_role') and not provider.supports_agent_role:
                    self._log(
                        f"{provider_name} selected by quality but does not support agent role, trying priority list",
                        "WARN"
                    )
                    raise RuntimeError("Provider doesn't support agent role")
                self._log(f"QUALITY selection: {provider_name}/{model} (best reasoning)", "SELECTED")
                return (provider_name, provider)
        except Exception as e:
            self._log(f"QUALITY selection failed: {e}, falling back to priority list", "WARN")

        # Fallback to priority from config - providers filtered by:
        # 1. supports_agent_role capability
        # 2. minimum context length for planner use (32k)
        MIN_CONTEXT_FOR_BRAIN = 32768
        priority = self.config.brain_priority
        self._log(f"Auto-selection priority: {' > '.join(priority)}")

        # First pass: try priority list with context constraint
        suitable_providers = self._get_providers_with_context(available, MIN_CONTEXT_FOR_BRAIN)

        for provider_name in priority:
            if provider_name in suitable_providers:
                provider = self.registry.get(provider_name)
                # Skip providers that don't support agent role
                if hasattr(provider, 'supports_agent_role') and not provider.supports_agent_role:
                    self._log(f"Skipping {provider_name} - does not support agent role")
                    continue
                reason = self._get_brain_selection_reason(provider_name)
                self._log(f"Auto-selected brain: {provider_name} ({reason}, context >= {MIN_CONTEXT_FOR_BRAIN})", "SELECTED")
                return (provider_name, provider)
            elif provider_name in available:
                self._log(f"Skipping {provider_name} - insufficient context window")
            else:
                self._log(f"Skipping {provider_name} - not available")

        # Second pass: relax context constraint if no suitable providers found
        self._log(f"No providers with >= {MIN_CONTEXT_FOR_BRAIN} context, relaxing constraint", "WARN")
        for provider_name in priority:
            if provider_name in available:
                provider = self.registry.get(provider_name)
                if hasattr(provider, 'supports_agent_role') and not provider.supports_agent_role:
                    continue
                reason = self._get_brain_selection_reason(provider_name)
                self._log(f"Auto-selected brain: {provider_name} ({reason}, WARNING: may have limited context)", "SELECTED")
                return (provider_name, provider)

        # Fallback to first available that supports agent role
        for provider_name in available:
            provider = self.registry.get(provider_name)
            if hasattr(provider, 'supports_agent_role') and not provider.supports_agent_role:
                continue
            self._log(f"Fallback brain: {provider_name} (first available)", "SELECTED")
            return (provider_name, provider)

        # Last resort - no agent-capable providers
        self._log("No providers available that support agent role!", "ERROR")
        raise RuntimeError("No providers available that support agent role")

    def _get_brain_selection_reason(self, provider_name: str) -> str:
        """Get human-readable reason for brain selection."""
        return self.config.get_provider_reason(provider_name)

    def get_provider_for_fallback(
        self,
        exclude: list[str] = None,
        selection_type: Optional[ModelSelectionType] = None,
        min_context: int = 0
    ) -> Optional[str]:
        """
        Get a fallback provider, excluding specified ones.

        When selection_type is provided, filters providers to those that have
        models meeting the selection criteria. This ensures fallback maintains
        quality/context requirements.

        Args:
            exclude: List of provider names to exclude
            selection_type: Optional selection type to filter by (QUALITY, FAST, etc.)
            min_context: Minimum context length required (only used with QUALITY)

        Returns:
            Provider name or None if no fallback available
        """
        exclude = exclude or []
        available = self.registry.list_available()

        # If selection_type provided, filter to providers with suitable models
        if selection_type == ModelSelectionType.QUALITY and min_context > 0:
            suitable_providers = self._get_providers_with_context(available, min_context)
            if suitable_providers:
                available = suitable_providers
                self._log(f"Fallback filtered to providers with >={min_context} context: {available}")

        # Priority order for fallback
        priority = self.config.fallback_priority

        for provider_name in priority:
            if provider_name in available and provider_name not in exclude:
                return provider_name

        # Try any available provider not in exclude list
        for provider_name in available:
            if provider_name not in exclude:
                return provider_name

        return None

    def _get_providers_with_context(self, available: list[str], min_context: int) -> list[str]:
        """
        Filter providers to those with at least one model meeting context requirement.

        Args:
            available: List of available provider names
            min_context: Minimum context length required

        Returns:
            Filtered list of provider names
        """
        suitable = []
        for provider_name in available:
            provider = self.registry.get(provider_name)
            for model_id in provider.available_models:
                info = provider.get_model_info(model_id)
                if info.context_length and info.context_length >= min_context:
                    suitable.append(provider_name)
                    break  # One suitable model is enough
        return suitable

    def select_for_planning(self) -> Tuple[str, str]:
        """
        Select best provider and model for planning/agent tasks.

        Prioritizes instruction-tuned models for better JSON compliance.

        Returns:
            Tuple of (provider_name, model_name)

        Raises:
            RuntimeError: If no providers available
        """
        self._log("Selecting provider for planning (prioritizing instruction-tuned models)")
        available = self.registry.list_available()

        if not available:
            self._log("No providers available!", "ERROR")
            raise RuntimeError("No providers available!")

        # Filter to only providers that support agent role
        agent_capable = []
        for name in available:
            provider = self.registry.get(name)
            if hasattr(provider, 'supports_agent_role') and not provider.supports_agent_role:
                self._log(f"Skipping {name} for planning - does not support agent role")
                continue
            agent_capable.append(name)

        if not agent_capable:
            self._log("No agent-capable providers available!", "ERROR")
            raise RuntimeError("No providers available that support agent role!")

        # First, try to find instruction-tuned models with high RPD
        best_provider = None
        best_model = None
        best_rpd = 0

        for provider_name in agent_capable:
            provider = self.registry.get(provider_name)

            # Check for instruction-tuned models
            if hasattr(provider, 'get_instruction_tuned_models'):
                instruct_models = provider.get_instruction_tuned_models()

                for model_id in instruct_models:
                    if hasattr(provider, 'get_model_info'):
                        info = provider.get_model_info(model_id)
                        rpd = info.rpd or 0

                        if rpd > best_rpd:
                            best_rpd = rpd
                            best_provider = provider_name
                            best_model = model_id

        if best_provider and best_model:
            self._log(f"Selected {best_provider}/{best_model} (instruction-tuned, {best_rpd} RPD)", "SELECTED")
            return (best_provider, best_model)

        # Fallback: try chat-tuned models
        self._log("No instruction-tuned models found, trying chat models", "WARN")
        for provider_name in agent_capable:
            provider = self.registry.get(provider_name)

            for model_id in provider.available_models:
                if hasattr(provider, 'get_model_info'):
                    info = provider.get_model_info(model_id)
                    if info.model_type == ModelType.CHAT:
                        rpd = info.rpd or 0
                        if rpd > best_rpd:
                            best_rpd = rpd
                            best_provider = provider_name
                            best_model = model_id

        if best_provider and best_model:
            self._log(f"Selected {best_provider}/{best_model} (chat model, {best_rpd} RPD)", "SELECTED")
            return (best_provider, best_model)

        # Last resort: use first agent-capable provider's default
        self._log("No instruction or chat models found, using default", "WARN")
        provider_name = agent_capable[0]
        provider = self.registry.get(provider_name)
        model = provider.available_models[0] if provider.available_models else None
        self._log(f"Fallback to {provider_name}/{model}", "SELECTED")
        return (provider_name, model)

    def get_best_instruct_model(self, provider_name: str) -> Optional[str]:
        """
        Get the best instruction-tuned model from a specific provider.

        Prioritizes models with higher RPD.

        Args:
            provider_name: Provider to check

        Returns:
            Model ID or None if no instruction-tuned models
        """
        if provider_name not in self.registry.list_available():
            return None

        provider = self.registry.get(provider_name)

        if not hasattr(provider, 'get_instruction_tuned_models'):
            return None

        instruct_models = provider.get_instruction_tuned_models()
        if not instruct_models:
            return None

        # Find model with highest RPD
        best_model = None
        best_rpd = 0

        for model_id in instruct_models:
            if hasattr(provider, 'get_model_info'):
                info = provider.get_model_info(model_id)
                rpd = info.rpd or 0
                if rpd > best_rpd:
                    best_rpd = rpd
                    best_model = model_id

        # If no RPD info, return first instruction-tuned model
        return best_model or instruct_models[0]

    def has_instruction_tuned_models(self) -> bool:
        """
        Check if any provider has instruction-tuned models.

        Returns:
            True if instruction-tuned models available
        """
        for provider_name in self.registry.list_available():
            provider = self.registry.get(provider_name)
            if hasattr(provider, 'get_instruction_tuned_models'):
                if provider.get_instruction_tuned_models():
                    return True
        return False

    def list_instruction_tuned_models(self) -> List[Tuple[str, str]]:
        """
        List all instruction-tuned models across all providers.

        Returns:
            List of (provider_name, model_id) tuples
        """
        result = []

        for provider_name in self.registry.list_available():
            provider = self.registry.get(provider_name)
            if hasattr(provider, 'get_instruction_tuned_models'):
                for model_id in provider.get_instruction_tuned_models():
                    result.append((provider_name, model_id))

        return result

    def get_model(self, selection_type: ModelSelectionType) -> tuple[str, str]:
        """
        Select provider and model based on selection type.

        Args:
            selection_type: What kind of model is needed

        Returns:
            Tuple of (provider_name, model_id)

        Raises:
            RuntimeError: If no providers available
        """
        self._log(f"Selecting model for: {selection_type.value}")
        available = self.registry.list_available()

        if not available:
            self._log("No providers available!", "ERROR")
            raise RuntimeError("No providers available!")

        self._log(f"Available providers: {', '.join(available)}")

        if selection_type == ModelSelectionType.FAST:
            return self._select_by_speed(available)
        elif selection_type == ModelSelectionType.QUALITY:
            return self._select_by_quality(available)
        elif selection_type == ModelSelectionType.INSTRUCT:
            return self._select_by_instruct(available)
        elif selection_type == ModelSelectionType.EMBED:
            return self._select_for_embed(available)

        # Fallback
        self._log(f"Unknown selection type, using first available", "WARN")
        return (available[0], None)

    def _select_by_speed(self, available: list[str]) -> tuple[str, str]:
        """Select fastest model with good quota."""
        candidates = []
        for provider_name in available:
            provider = self.registry.get(provider_name)
            for model_id in provider.available_models:
                info = provider.get_model_info(model_id)
                candidates.append((provider_name, model_id, info))

        speed_rank = {
            SpeedRank.ULTRA_FAST: 0,
            SpeedRank.VERY_FAST: 1,
            SpeedRank.FAST: 2,
            SpeedRank.MODERATE: 3,
            SpeedRank.SLOW: 4
        }
        candidates.sort(key=lambda x: (speed_rank.get(x[2].speed, 5), -(x[2].rpd or 0)))

        if candidates:
            best = candidates[0]
            self._log(f"Selected {best[0]}/{best[1]} (speed: {best[2].speed.value})", "SELECTED")
            return (best[0], best[1])

        self._log(f"No candidates, using {available[0]}", "WARN")
        return (available[0], None)

    def _select_by_quality(self, available: list[str], min_context: int = 32768) -> tuple[str, str]:
        """
        Select highest quality model with sufficient context length.

        Args:
            available: List of available provider names
            min_context: Minimum context length required (default 32k for planner use)

        Returns:
            Tuple of (provider_name, model_id)
        """
        candidates = []
        for provider_name in available:
            provider = self.registry.get(provider_name)
            for model_id in provider.available_models:
                info = provider.get_model_info(model_id)
                # Filter: must have >= min_context for planner role
                if info.context_length and info.context_length >= min_context:
                    candidates.append((provider_name, model_id, info))
                elif self.verbose:
                    self._log(
                        f"Skipping {provider_name}/{model_id} - context {info.context_length} < {min_context}"
                    )

        quality_rank = {
            QualityRank.EXCELLENT: 0,
            QualityRank.VERY_GOOD: 1,
            QualityRank.GOOD: 2,
            QualityRank.MODERATE: 3
        }
        candidates.sort(key=lambda x: (quality_rank.get(x[2].quality, 4), -(x[2].rpd or 0)))

        if candidates:
            best = candidates[0]
            self._log(
                f"Selected {best[0]}/{best[1]} (quality: {best[2].quality.value}, "
                f"context: {best[2].context_length})", "SELECTED"
            )
            return (best[0], best[1])

        # If no models meet min_context, relax constraint and log warning
        self._log(f"No models with {min_context} context, trying without filter", "WARN")
        candidates = []
        for provider_name in available:
            provider = self.registry.get(provider_name)
            for model_id in provider.available_models:
                info = provider.get_model_info(model_id)
                candidates.append((provider_name, model_id, info))

        candidates.sort(key=lambda x: (quality_rank.get(x[2].quality, 4), -(x[2].rpd or 0)))

        if candidates:
            best = candidates[0]
            self._log(
                f"Selected {best[0]}/{best[1]} (quality: {best[2].quality.value}, "
                f"WARNING: context {best[2].context_length} < {min_context})", "SELECTED"
            )
            return (best[0], best[1])

        self._log(f"No candidates, using {available[0]}", "WARN")
        return (available[0], None)

    def _select_by_instruct(self, available: list[str]) -> tuple[str, str]:
        """Select best instruction-tuned model."""
        candidates = []
        for provider_name in available:
            provider = self.registry.get(provider_name)
            for model_id in provider.available_models:
                info = provider.get_model_info(model_id)
                if info.is_instruction_tuned:
                    candidates.append((provider_name, model_id, info))

        # Sort by RPD (prefer high quota)
        candidates.sort(key=lambda x: -(x[2].rpd or 0))

        if candidates:
            best = candidates[0]
            self._log(f"Selected {best[0]}/{best[1]} (instruct, {best[2].rpd} RPD)", "SELECTED")
            return (best[0], best[1])

        # Fallback to quality if no instruct models
        self._log("No instruction-tuned models, falling back to quality", "WARN")
        return self._select_by_quality(available)

    def _select_for_embed(self, available: list[str]) -> tuple[str, str]:
        """Select embedding model."""
        if 'cohere' in available:
            self._log("Selected cohere for embeddings", "SELECTED")
            return ('cohere', None)

        self._log(f"No embedding provider, using {available[0]}", "WARN")
        return (available[0], None)
