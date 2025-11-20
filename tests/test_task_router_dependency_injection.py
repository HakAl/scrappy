"""
Tests for TaskRouter dependency injection.

Verifies that all dependencies can be passed explicitly through the constructor,
enabling better testability and flexibility.
"""

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
        )

        result = router.route("test")

        # Assert - all injected dependencies should be the custom ones
        assert router.classifier is custom_classifier
        assert router.metrics_collector is custom_metrics
        assert router.provider_resolver is custom_resolver

        # And they should all have been used
        custom_classifier.classify.assert_called_once()
        custom_metrics.update.assert_called_once()



class TestDependencyInjectionEnablesTestability:
    """Test that dependency injection improves testability."""

    def test_can_verify_classifier_calls_without_side_effects(self):
        """Should be able to test classification behavior in isolation."""
        # Arrange
        call_tracker = []

        custom_classifier = Mock(spec=TaskClassifier)
        def track_classify(input_text):
            call_tracker.append(input_text)
            return ClassifiedTask(
                original_input=input_text,
                task_type=TaskType.CONVERSATION,
                confidence=0.9,
                reasoning="Tracked"
            )
        custom_classifier.classify.side_effect = track_classify

        router = TaskRouter(
            classifier=custom_classifier,
            output_handler=NullOutputHandler(),
            intent_clarifier=NullClarifier(),
        )

        # Act
        router.route("first task")
        router.route("second task")

        # Assert
        assert call_tracker == ["first task", "second task"]

    def test_can_inject_metrics_for_verification(self):
        """Should be able to verify metrics updates without real execution."""
        # Arrange
        update_calls = []

        custom_metrics = Mock(spec=MetricsCollector)
        custom_metrics.get_metrics.return_value = RouterMetrics()

        def track_update(task, result):
            update_calls.append({
                "task_type": task.task_type,
                "success": result.success
            })
        custom_metrics.update.side_effect = track_update

        router = TaskRouter(
            metrics_collector=custom_metrics,
            output_handler=NullOutputHandler(),
            intent_clarifier=NullClarifier(),
        )

        # Act
        router.route("hello")

        # Assert
        assert len(update_calls) == 1
        assert update_calls[0]["task_type"] == TaskType.CONVERSATION
        assert update_calls[0]["success"] is True
