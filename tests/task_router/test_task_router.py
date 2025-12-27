"""
Tests for TaskRouter - task routing and execution strategies.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import time

from scrappy.task_router.router import TaskRouter
from scrappy.task_router.classifier import TaskClassifier, ClassifiedTask, TaskType
from scrappy.task_router.config import ClarificationConfig
from scrappy.task_router.strategies import ExecutionResult
from scrappy.task_router.intent_clarifier import NullClarifier
from scrappy.llm.models import TaskClassification as LLMTaskClassification
from scrappy.llm.models import TaskType as LLMTaskType


class TestConfidenceEscalation:
    """Tests for confidence-based task escalation."""

    @pytest.fixture
    def router(self, default_clarification_config):
        return TaskRouter(orchestrator=None, verbose=False, clarification_config=default_clarification_config)

    @pytest.mark.unit
    def test_low_confidence_research_with_action_word_escalates(self, router):
        """Test that low confidence research with action words escalates."""
        task = ClassifiedTask(
            original_input="create something",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Low confidence"
        )

        escalated = router._apply_confidence_escalation(task)
        # Should escalate to CODE_GENERATION because of 'create'
        assert escalated.task_type == TaskType.CODE_GENERATION

    @pytest.mark.unit
    def test_high_confidence_no_escalation(self, router):
        """Test that high confidence tasks don't escalate."""
        task = ClassifiedTask(
            original_input="explain python",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="High confidence"
        )

        escalated = router._apply_confidence_escalation(task)
        # Should stay as RESEARCH
        assert escalated.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_escalation_updates_reasoning(self, router):
        """Test that escalation updates the reasoning."""
        task = ClassifiedTask(
            original_input="write code",
            task_type=TaskType.RESEARCH,
            confidence=0.3,
            reasoning="Original reasoning here"
        )

        escalated = router._apply_confidence_escalation(task)
        # The reasoning should be updated to include escalation info
        assert "escalat" in escalated.reasoning.lower() or escalated.reasoning != "Original reasoning here"


class TestIntentClarification:
    """Tests for intent clarification detection."""

    @pytest.fixture
    def router(self, default_clarification_config):
        return TaskRouter(orchestrator=None, verbose=False, clarification_config=default_clarification_config)

    @pytest.mark.unit
    def test_conflicting_intent_high_confidence_no_clarification(self, router):
        """Test that high confidence bypasses conflicting signal checks.

        This is the Phase 2 fix: when classifier is highly confident (>= 0.9),
        we trust it and don't trigger clarification even with conflicting signals.
        """
        classifier = TaskClassifier()
        task = classifier.classify("explain how to create a file")
        # Classifier returns 1.0 confidence for this (research pattern)
        assert task.confidence >= 0.9, "Test assumes high confidence from classifier"
        needs_clarify = router._needs_intent_clarification(task)
        # High confidence (>= 0.9) should bypass conflicting signal check
        assert needs_clarify is False

    @pytest.mark.unit
    def test_conflicting_intent_medium_confidence_needs_clarification(self, router):
        """Test that medium confidence with conflicting signals needs clarification."""
        from dataclasses import replace
        classifier = TaskClassifier()
        task = classifier.classify("explain how to create a file")
        # Force medium confidence to test conflicting signal behavior
        task = replace(task, confidence=0.8)  # Medium: >= 0.7 but < 0.9
        needs_clarify = router._needs_intent_clarification(task)
        # 'explain' vs 'create' - conflicting signals with medium confidence
        assert needs_clarify is True

    @pytest.mark.unit
    def test_clear_action_no_clarification(self, router):
        """Test that clear actions don't need clarification."""
        classifier = TaskClassifier()
        task = classifier.classify("create requirements.txt")
        needs_clarify = router._needs_intent_clarification(task)
        assert needs_clarify is False

    @pytest.mark.unit
    def test_clear_question_no_clarification(self, router):
        """Test that clear questions don't need clarification."""
        classifier = TaskClassifier()
        task = classifier.classify("what is python?")
        needs_clarify = router._needs_intent_clarification(task)
        assert needs_clarify is False


class TestLLMClassification:
    """Tests for LLM-based classification fallback."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator with delegate method."""
        orch = Mock()
        return orch

    @pytest.fixture
    def router_with_orchestrator(self, mock_orchestrator, default_clarification_config):
        """Create router with mock orchestrator."""
        return TaskRouter(
            orchestrator=mock_orchestrator,
            verbose=False,
            clarification_config=default_clarification_config
        )

    @pytest.mark.unit
    def test_llm_classification_calls_delegate_structured_with_fast_model(self, router_with_orchestrator, mock_orchestrator):
        """Test that LLM classification uses fast model group via delegate_structured."""
        # Setup mock response - returns TaskClassification object
        mock_classification = LLMTaskClassification(
            task_type=LLMTaskType.RESEARCH,
            confidence=0.9,
            reasoning="This is asking for information"
        )
        mock_orchestrator.delegate_structured.return_value = mock_classification

        # Create low-confidence task that would trigger LLM classification
        task = ClassifiedTask(
            original_input="name the top software engineers from 1950-2020",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.5,
            reasoning="Pattern matched 'add'"
        )

        # Call LLM classification
        result = router_with_orchestrator._classify_with_llm(task)

        # Verify delegate_structured was called
        mock_orchestrator.delegate_structured.assert_called_once()

        # Check the call used 'fast' provider
        call_kwargs = mock_orchestrator.delegate_structured.call_args
        assert call_kwargs.kwargs.get('provider_name') == 'fast'
        assert call_kwargs.kwargs.get('response_model') == LLMTaskClassification

    @pytest.mark.unit
    def test_llm_classification_reclassifies_to_research(self, router_with_orchestrator, mock_orchestrator):
        """Test that LLM can reclassify code_generation to research."""
        # Setup mock response - LLM says this is research
        mock_classification = LLMTaskClassification(
            task_type=LLMTaskType.RESEARCH,
            confidence=0.95,
            reasoning="User wants information about historical figures"
        )
        mock_orchestrator.delegate_structured.return_value = mock_classification

        # Create misclassified task
        task = ClassifiedTask(
            original_input="name the top software engineers from 1950-2020",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.5,
            reasoning="Pattern matched 'add'"
        )

        # Call LLM classification
        result = router_with_orchestrator._classify_with_llm(task)

        # Should be reclassified to RESEARCH
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.95
        assert "LLM semantic classification" in result.reasoning

    @pytest.mark.unit
    def test_llm_classification_keeps_original_when_uncertain(self, router_with_orchestrator, mock_orchestrator):
        """Test that uncertain LLM response keeps original classification."""
        # Setup mock response - LLM is uncertain
        mock_classification = LLMTaskClassification(
            task_type=LLMTaskType.RESEARCH,
            confidence=0.5,
            reasoning="Could be either"
        )
        mock_orchestrator.delegate_structured.return_value = mock_classification

        task = ClassifiedTask(
            original_input="some ambiguous input",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.5,
            reasoning="Original"
        )

        result = router_with_orchestrator._classify_with_llm(task)

        # Should keep original since LLM confidence < 0.7
        assert result.task_type == TaskType.CODE_GENERATION

    @pytest.mark.unit
    def test_llm_classification_handles_no_orchestrator(self, default_clarification_config):
        """Test that missing orchestrator returns original task."""
        router = TaskRouter(
            orchestrator=None,
            verbose=False,
            clarification_config=default_clarification_config
        )

        task = ClassifiedTask(
            original_input="test input",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Test"
        )

        result = router._classify_with_llm(task)

        # Should return original task unchanged
        assert result == task

    @pytest.mark.unit
    def test_llm_classification_handles_delegate_exception(self, router_with_orchestrator, mock_orchestrator):
        """Test that delegate exceptions are handled gracefully."""
        mock_orchestrator.delegate.side_effect = Exception("API error")

        task = ClassifiedTask(
            original_input="test input",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.5,
            reasoning="Test"
        )

        result = router_with_orchestrator._classify_with_llm(task)

        # Should return original task on error
        assert result.task_type == TaskType.CODE_GENERATION

