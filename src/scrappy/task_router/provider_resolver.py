"""
Provider hint resolution utility.

Resolves ModelSelectionType to actual provider names and models.
"""

from typing import Optional, Tuple

from ..orchestrator.model_selection import ModelSelectionType


class ProviderResolver:
    """
    Resolves selection types to provider/model tuples.

    Thin wrapper around ProviderSelector for TaskRouter integration.
    """

    def __init__(self, orchestrator=None):
        """
        Initialize provider resolver.

        Args:
            orchestrator: Orchestrator instance with provider_selector
        """
        self.orchestrator = orchestrator

    def resolve(
        self,
        selection_type: Optional[ModelSelectionType]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve selection type to provider and model.

        Args:
            selection_type: What kind of model is needed

        Returns:
            Tuple of (provider_name, model_name) or (None, None)
        """
        if selection_type is None or self.orchestrator is None:
            return (None, None)

        try:
            return self.orchestrator.provider_selector.get_model(selection_type)
        except (AttributeError, RuntimeError):
            return (None, None)
