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

