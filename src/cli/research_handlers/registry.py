"""
Registry for research handlers.
"""

from typing import Dict, List, Optional

from .base import QueryIntent, ResearchHandler


class ResearchHandlerRegistry:
    """Registry that maps intents to their handlers."""

    def __init__(self):
        """Initialize empty registry."""
        self._handlers: Dict[QueryIntent, ResearchHandler] = {}

    def register(self, handler: ResearchHandler) -> None:
        """
        Register a handler for its intent.

        Args:
            handler: Handler to register
        """
        self._handlers[handler.intent] = handler

    def get_handler(self, intent: QueryIntent) -> Optional[ResearchHandler]:
        """
        Get handler for an intent.

        Args:
            intent: The query intent

        Returns:
            Handler if registered, None otherwise
        """
        return self._handlers.get(intent)

    def list_intents(self) -> List[QueryIntent]:
        """
        List all registered intents.

        Returns:
            List of registered QueryIntent values
        """
        return list(self._handlers.keys())


def create_default_registry() -> ResearchHandlerRegistry:
    """
    Create a registry with all default handlers pre-registered.

    Returns:
        ResearchHandlerRegistry with all standard handlers
    """
    from .file_structure import FileStructureHandler
    from .code_search import CodeSearchHandler
    from .code_explanation import CodeExplanationHandler
    from .git_history import GitHistoryHandler
    from .dependency_info import DependencyInfoHandler
    from .architecture import ArchitectureHandler
    from .bug_investigation import BugInvestigationHandler
    from .testing import TestingHandler
    from .configuration import ConfigurationHandler
    from .security import SecurityHandler
    from .documentation import DocumentationHandler

    registry = ResearchHandlerRegistry()

    # Register all handlers
    registry.register(FileStructureHandler())
    registry.register(CodeSearchHandler())
    registry.register(CodeExplanationHandler())
    registry.register(GitHistoryHandler())
    registry.register(DependencyInfoHandler())
    registry.register(ArchitectureHandler())
    registry.register(BugInvestigationHandler())
    registry.register(TestingHandler())
    registry.register(ConfigurationHandler())
    registry.register(SecurityHandler())
    registry.register(DocumentationHandler())

    return registry
