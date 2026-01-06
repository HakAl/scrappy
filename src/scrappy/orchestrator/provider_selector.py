"""
Provider selection and routing logic.

REDUCED SCOPE: After LiteLLM integration, this class only handles:
- setup_brain() -> returns "quality" (no longer scans providers)
- get_model() -> returns model groups for backward compatibility

Selection logic is now handled by:
- TaskRouter -> classifies as "fast" or "quality"
- LiteLLM Router -> handles fallback within group, retry, rate limits
"""

from typing import Optional, Tuple

from .model_selection import ModelSelectionType, SELECTION_TYPE_TO_GROUP
from .output import BaseOutputProtocol, ConsoleOutput
from .config import OrchestratorConfig
from .protocols import ProviderRegistryProtocol


class ProviderSelector:
    """
    REDUCED SCOPE: After LiteLLM integration, this class only handles:
    - setup_brain() -> returns "quality" (no longer scans providers)
    - get_model() -> returns model groups for backward compatibility
    - Status display helpers (if needed)

    Selection logic is now handled by:
    - TaskRouter -> classifies task complexity as "fast" or "quality"
    - LiteLLM Router -> handles provider fallback, retry, rate limits

    Model Groups (defined in litellm_config.py):
    - "fast": 8B models, speed priority (Groq 8B, Cerebras 8B)
    - "quality": 70B+ models, 32k+ context (Gemini, Groq 70B)
    """

    def __init__(
        self,
        registry: ProviderRegistryProtocol = None,
        verbose: bool = False,
        output: Optional[BaseOutputProtocol] = None,
        config: Optional[OrchestratorConfig] = None
    ):
        """
        Initialize provider selector.

        Args:
            registry: Provider registry (kept for backward compatibility, minimally used)
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

    def setup_brain(self, preferred_provider: Optional[str] = None) -> tuple[str, None]:
        """
        Return the model group to use for brain/reasoning.

        After LiteLLM integration, this returns "instruct" since
        brain tasks require instruction-tuned models with tool use support.

        Args:
            preferred_provider: Preferred provider name (mapped to group if legacy name)

        Returns:
            Tuple of (model_group, None) - model is None, Router picks actual model
        """
        self._log("Setting up orchestrator brain")

        # If user explicitly requested a provider, map to group
        if preferred_provider:
            self._log(f"User requested: {preferred_provider}")
            # Check if it's already a valid group name
            if preferred_provider in ("fast", "chat", "instruct"):
                self._log(f"Using model group: {preferred_provider}", "SELECTED")
                return (preferred_provider, None)
            # Legacy "quality" name maps to "instruct" for brain tasks
            if preferred_provider == "quality":
                self._log("Legacy 'quality' -> 'instruct' group", "SELECTED")
                return ("instruct", None)
            # Legacy provider name - map to instruct for brain tasks
            self._log(f"Legacy provider '{preferred_provider}' -> 'instruct' group", "SELECTED")
            return ("instruct", None)

        # Default: brain always uses instruct tier
        self._log("Auto-selected brain: instruct group", "SELECTED")
        return ("instruct", None)

    def get_model(self, selection_type: ModelSelectionType) -> tuple[str, None]:
        """
        Map selection type to model group.

        DEPRECATED: Use ProviderResolver.resolve() or pass group directly.
        Kept for backward compatibility during migration.

        Args:
            selection_type: What kind of model is needed

        Returns:
            Tuple of (model_group, None) - model is None, Router picks actual model

        Raises:
            RuntimeError: If selection_type is invalid
        """
        self._log(f"Selecting model for: {selection_type.value}")

        group = SELECTION_TYPE_TO_GROUP.get(selection_type)
        if group is None:
            self._log(f"Unknown selection type: {selection_type}, using 'fast'", "WARN")
            group = "fast"

        self._log(f"Mapped to model group: {group}", "SELECTED")
        return (group, None)

    def get_provider_for_fallback(
        self,
        exclude: list[str] = None,
        selection_type: Optional[ModelSelectionType] = None,
        min_context: int = 0
    ) -> Optional[str]:
        """
        Get a fallback provider.

        DEPRECATED: LiteLLM Router handles fallback internally.
        Returns the model group for compatibility.

        Args:
            exclude: List of provider names to exclude (ignored)
            selection_type: Optional selection type (used to determine group)
            min_context: Minimum context length required (ignored, baked into groups)

        Returns:
            Model group name ("fast" or "quality")
        """
        self._log("Fallback requested - LiteLLM Router handles this internally", "INFO")

        if selection_type:
            group = SELECTION_TYPE_TO_GROUP.get(selection_type, "fast")
        else:
            group = "fast"

        return group

    def select_for_planning(self) -> Tuple[str, None]:
        """
        Select model group for planning/agent tasks.

        DEPRECATED: Use setup_brain() or pass "instruct" directly.

        Returns:
            Tuple of ("instruct", None) - instruction-tuned models for planning
        """
        self._log("Planning tasks use instruct group", "SELECTED")
        return ("instruct", None)

    def recommend(self, requirements: dict) -> str:
        """
        Recommend model group based on requirements.

        Simplified: returns "fast" or "chat" based on requirements.

        Args:
            requirements: Dict with keys like:
                - 'speed': 'fast' | 'moderate' | 'slow'
                - 'quality': 'moderate' | 'good' | 'excellent'

        Returns:
            Model group name ("fast" or "chat")
        """
        # Quality priority -> chat group (70B models)
        if requirements.get('quality') == 'excellent':
            return 'chat'

        # Speed priority or default -> fast group
        if requirements.get('speed') == 'fast':
            return 'fast'

        # Default to fast for budget-sensitive
        if requirements.get('budget_sensitive', True):
            return 'fast'

        return 'fast'
