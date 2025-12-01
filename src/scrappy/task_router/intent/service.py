"""
Intent service facade.

Coordinates intent classification, entity extraction, and action resolution
into a single pipeline.
"""

from typing import Optional
from ..protocols import (
    IntentServiceProtocol,
    IntentClassifierProtocol,
    EntityExtractorProtocol,
    ActionResolverProtocol,
    Action,
)
from .classifier import RegexIntentClassifier
from .entities import RegexEntityExtractor
from .actions import DefaultActionResolver


class IntentService(IntentServiceProtocol):
    """
    Intent service facade.

    Coordinates intent classification, entity extraction, and action
    resolution into a single pipeline. This is the main entry point
    for intent processing.

    Dependencies are injected via constructor, following the Dependency
    Inversion Principle. Default implementations are provided via factory
    methods.

    Example:
        service = IntentService(
            classifier=RegexIntentClassifier(),
            extractor=RegexEntityExtractor(),
            resolver=DefaultActionResolver()
        )
        action = service.process_query("show me the file structure")
        assert action.tool == 'FileSystem'
    """

    def __init__(
        self,
        classifier: Optional[IntentClassifierProtocol] = None,
        extractor: Optional[EntityExtractorProtocol] = None,
        resolver: Optional[ActionResolverProtocol] = None,
    ):
        """
        Initialize intent service with dependencies.

        Args:
            classifier: Intent classifier (defaults to RegexIntentClassifier)
            extractor: Entity extractor (defaults to RegexEntityExtractor)
            resolver: Action resolver (defaults to DefaultActionResolver)
        """
        self.classifier = classifier if classifier is not None else self._create_default_classifier()
        self.extractor = extractor if extractor is not None else self._create_default_extractor()
        self.resolver = resolver if resolver is not None else self._create_default_resolver()

    def process_query(self, query: str) -> Action:
        """
        Full pipeline: classify intent -> extract entities -> resolve to action.

        This is the main entry point for processing user queries.

        Process:
        1. Classify the intent using the classifier
        2. Extract entities using the extractor
        3. Resolve to concrete action using the resolver

        Args:
            query: User's query string

        Returns:
            Action object ready to be executed
        """
        intent_result = self.classifier.classify(query)

        entities = self.extractor.extract(query)

        action = self.resolver.resolve(intent_result, entities)

        return action

    def _create_default_classifier(self) -> IntentClassifierProtocol:
        """
        Create default intent classifier.

        Factory method for default classifier implementation.

        Returns:
            RegexIntentClassifier instance
        """
        return RegexIntentClassifier()

    def _create_default_extractor(self) -> EntityExtractorProtocol:
        """
        Create default entity extractor.

        Factory method for default extractor implementation.

        Returns:
            RegexEntityExtractor instance
        """
        return RegexEntityExtractor()

    def _create_default_resolver(self) -> ActionResolverProtocol:
        """
        Create default action resolver.

        Factory method for default resolver implementation.

        Returns:
            DefaultActionResolver instance
        """
        return DefaultActionResolver()
