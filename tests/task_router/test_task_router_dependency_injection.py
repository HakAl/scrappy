"""
Tests for TaskRouter dependency injection.

Verifies that all dependencies can be passed explicitly through the constructor,
enabling better testability and flexibility.
"""

import warnings

import pytest
from unittest.mock import Mock, MagicMock
from pathlib import Path

from src.task_router import (
    TaskRouter,
    TaskClassifier,
    ClassifiedTask,
    TaskType,
    NullOutputHandler,
    NullClarifier,
    InputValidator,
    ClarificationConfig,
)
from src.task_router.metrics_collector import MetricsCollector, RouterMetrics
from src.task_router.provider_resolver import ProviderResolver
from tests.helpers import ConfigurableTestOrchestrator


class TestTaskRouterDependencyInjection:
    """Test that TaskRouter accepts all dependencies through constructor."""

    def test_accepts_custom_classifier(self):
        """TaskRouter should accept a custom classifier via constructor."""
        # Arrange
        custom_classifier = Mock(spec=TaskClassifier)
        custom_classifier.classify.return_value = ClassifiedTask(
            original_input="test input",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="Custom classifier result"
        )

        # Act
        router = TaskRouter(
            classifier=custom_classifier,
            output_handler=NullOutputHandler(),
            intent_clarifier=NullClarifier(),
            clarification_config=ClarificationConfig(),
        )

        # Assert - the custom classifier should be used
        assert router.classifier is custom_classifier

    def test_accepts_custom_metrics_collector(self):
        """TaskRouter should accept a custom metrics collector via constructor."""
        # Arrange
        custom_metrics = Mock(spec=MetricsCollector)
        custom_metrics.get_metrics.return_value = RouterMetrics()

        # Act
        router = TaskRouter(
            metrics_collector=custom_metrics,
            output_handler=NullOutputHandler(),
            intent_clarifier=NullClarifier(),
            clarification_config=ClarificationConfig(),
        )

        # Assert
        assert router.metrics_collector is custom_metrics

    def test_accepts_custom_provider_resolver(self):
        """TaskRouter should accept a custom provider resolver via constructor."""
        # Arrange
        custom_resolver = Mock(spec=ProviderResolver)
        custom_resolver.resolve.return_value = ("custom_provider", "custom_model")

        # Act
        router = TaskRouter(
            provider_resolver=custom_resolver,
            output_handler=NullOutputHandler(),
            intent_clarifier=NullClarifier(),
            clarification_config=ClarificationConfig(),
        )

        # Assert
        assert router.provider_resolver is custom_resolver





class TestInjectedClassifierIsUsed:
    """Test that injected classifier is actually used during routing."""


    def test_classification_result_determines_strategy(self):
        """Injected classifier's result should determine which strategy executes."""
        # Arrange
        custom_classifier = Mock(spec=TaskClassifier)

        # Configure to return CODE_GENERATION
        custom_classifier.classify.return_value = ClassifiedTask(
            original_input="do something",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.9,
            reasoning="Forced CODE_GENERATION"
        )

        orchestrator = ConfigurableTestOrchestrator(
            response_content='{"thought": "test", "action": "complete", "is_complete": true, "result": "done"}'
        )

        router = TaskRouter(
            orchestrator=orchestrator,
            classifier=custom_classifier,
            output_handler=NullOutputHandler(),
            intent_clarifier=NullClarifier(),
            clarification_config=ClarificationConfig(),
        )

        # Act
        result = router.route("do something")

        # Assert - classification metadata should reflect the injected classifier's decision
        assert result.metadata["classification"]["type"] == "code_generation"


class TestInjectedMetricsCollectorIsUsed:
    """Test that injected metrics collector is actually used."""


    def test_get_metrics_returns_from_injected_collector(self):
        """get_metrics should delegate to the injected metrics collector."""
        # Arrange
        expected_metrics = RouterMetrics(
            total_tasks=42,
            success_rate=0.95,
            avg_execution_time=1.5
        )
        custom_metrics = Mock(spec=MetricsCollector)
        custom_metrics.get_metrics.return_value = expected_metrics

        router = TaskRouter(
            metrics_collector=custom_metrics,
            output_handler=NullOutputHandler(),
            intent_clarifier=NullClarifier(),
            clarification_config=ClarificationConfig(),
        )

        # Act
        metrics = router.get_metrics()

        # Assert
        assert metrics is expected_metrics
        custom_metrics.get_metrics.assert_called_once()


class TestInjectedProviderResolverIsUsed:
    """Test that injected provider resolver is actually used."""


    def test_resolved_provider_appears_in_result_metadata(self):
        """Provider resolution result should appear in execution metadata."""
        # Arrange
        custom_resolver = Mock(spec=ProviderResolver)
        custom_resolver.resolve.return_value = ("custom_provider", "custom_model")

        orchestrator = ConfigurableTestOrchestrator()

        router = TaskRouter(
            orchestrator=orchestrator,
            provider_resolver=custom_resolver,
            output_handler=NullOutputHandler(),
            intent_clarifier=NullClarifier(),
            clarification_config=ClarificationConfig(),
        )

        # Act
        result = router.route("what is python", provider="quality")

        # Assert
        assert result.metadata["classification"]["resolved_provider"] == "custom_provider"
        assert result.metadata["classification"]["resolved_model"] == "custom_model"


class TestAllDependenciesInjectedTogether:
    """Test injecting all dependencies at once."""

    def test_all_custom_dependencies_work_together(self):
        """All injected dependencies should work correctly together."""
        # Arrange
        custom_classifier = Mock(spec=TaskClassifier)
        custom_classifier.classify.return_value = ClassifiedTask(
            original_input="test",
            task_type=TaskType.CONVERSATION,
            confidence=0.99,
            reasoning="All custom"
        )

        custom_metrics = Mock(spec=MetricsCollector)
        custom_metrics.get_metrics.return_value = RouterMetrics(total_tasks=100)

        custom_resolver = Mock(spec=ProviderResolver)
        custom_resolver.resolve.return_value = (None, None)

        orchestrator = ConfigurableTestOrchestrator(
            response_content="Response"
        )

        # Act
        router = TaskRouter(
            orchestrator=orchestrator,
            classifier=custom_classifier,
            metrics_collector=custom_metrics,
            provider_resolver=custom_resolver,
            output_handler=NullOutputHandler(),
            intent_clarifier=NullClarifier(),
            clarification_config=ClarificationConfig(),
        )

        result = router.route("test")

        # Assert - all injected dependencies should be the custom ones
        assert router.classifier is custom_classifier
        assert router.metrics_collector is custom_metrics
        assert router.provider_resolver is custom_resolver

        # And they should all have been used
        custom_classifier.classify.assert_called_once()
        custom_metrics.update.assert_called_once()


class TestClarificationConfigDeprecationWarning:
    """Tests for deprecation warning when not passing explicit config."""

    def test_emits_warning_when_config_not_provided(self):
        """TaskRouter should emit deprecation warning when clarification_config is None."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            router = TaskRouter(
                output_handler=NullOutputHandler(),
                intent_clarifier=NullClarifier(),
                # clarification_config NOT provided
            )

            # Check warning was issued
            deprecation_warnings = [
                warning
                for warning in w
                if issubclass(warning.category, DeprecationWarning)
                and "confidence_threshold" in str(warning.message)
            ]
            assert len(deprecation_warnings) == 1
            assert "0.65" in str(deprecation_warnings[0].message)
            assert "0.7" in str(deprecation_warnings[0].message)

    def test_no_warning_when_config_provided(self):
        """TaskRouter should NOT emit warning when clarification_config is provided."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            router = TaskRouter(
                output_handler=NullOutputHandler(),
                intent_clarifier=NullClarifier(),
                clarification_config=ClarificationConfig(),  # Explicitly provided
            )

            # Check NO warning was issued for confidence_threshold
            deprecation_warnings = [
                warning
                for warning in w
                if issubclass(warning.category, DeprecationWarning)
                and "confidence_threshold" in str(warning.message)
            ]
            assert len(deprecation_warnings) == 0

    def test_uses_default_config_when_not_provided(self):
        """TaskRouter should use default ClarificationConfig when not provided."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            router = TaskRouter(
                output_handler=NullOutputHandler(),
                intent_clarifier=NullClarifier(),
            )

            # Default config should be used
            assert router.confidence_threshold == 0.7

