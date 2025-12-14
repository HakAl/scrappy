"""
Provider hint resolution utility.

Resolves ModelSelectionType to LiteLLM model groups.

After LiteLLM integration:
- Selection types map directly to model groups ("fast", "quality")
- No ProviderSelector needed - Router handles provider selection/fallback
- Model is always None - Router picks the actual model within the group
"""

from typing import Optional, Tuple

from ..orchestrator.model_selection import ModelSelectionType, SELECTION_TYPE_TO_GROUP


class ProviderResolver:
    """
    Resolves selection types to LiteLLM model groups.

    Simplified: No longer needs ProviderSelector or orchestrator reference.
    Selection types map directly to model groups - the LiteLLM Router
    handles provider selection, fallback, and rate limiting internally.

    Model Groups:
    - "fast": 8B models, speed priority (Groq/Cerebras)
    - "quality": 70B+ models, 32k+ context (Gemini/Groq 70B)
    """

    def __init__(self, orchestrator=None):
        """
        Initialize provider resolver.

        Args:
            orchestrator: Orchestrator instance (kept for backward compatibility, not used)
        """
        # Orchestrator param kept for backward compatibility but not used
        pass

    def resolve(
        self,
        selection_type: Optional[ModelSelectionType]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve selection type to model group.

        Args:
            selection_type: What kind of model is needed

        Returns:
            Tuple of (model_group, None) - model is None because
            LiteLLM Router selects the actual model within the group
        """
        if selection_type is None:
            return (None, None)

        group = SELECTION_TYPE_TO_GROUP.get(selection_type, "fast")
        return (group, None)  # Model is None - Router picks actual model
