"""
Tests for intent clarifier implementations.

These tests verify:
- Concrete implementations satisfy IntentClarifierProtocol
- Clarifier behavior is correct
"""
import pytest

from scrappy.task_router.classifier import ClassifiedTask, TaskType
from scrappy.task_router.intent_clarifier import (
    AutoClarifier,
    InteractiveClarifier,
    NullClarifier,
)
from scrappy.task_router.protocols import IntentClarifierProtocol


class TestIntentClarifierProtocolCompliance:
    """Tests for protocol compliance."""

    @pytest.mark.unit
    def test_interactive_clarifier_satisfies_protocol(self):
        """InteractiveClarifier should satisfy IntentClarifierProtocol."""
        clarifier = InteractiveClarifier()
        assert isinstance(clarifier, IntentClarifierProtocol)

    @pytest.mark.unit
    def test_auto_clarifier_satisfies_protocol(self):
        """AutoClarifier should satisfy IntentClarifierProtocol."""
        clarifier = AutoClarifier()
        assert isinstance(clarifier, IntentClarifierProtocol)

    @pytest.mark.unit
    def test_null_clarifier_satisfies_protocol(self):
        """NullClarifier should satisfy IntentClarifierProtocol."""
        clarifier = NullClarifier()
        assert isinstance(clarifier, IntentClarifierProtocol)


class TestNullClarifier:
    """Tests for NullClarifier behavior."""

    @pytest.mark.unit
    def test_returns_task_unchanged(self):
        """NullClarifier should return the task unchanged."""
        clarifier = NullClarifier()
        task = ClassifiedTask(
            original_input="test query",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="test",
        )

        result = clarifier.clarify(task)

        assert result is task  # Same object


class TestAutoClarifier:
    """Tests for AutoClarifier behavior."""

    @pytest.mark.unit
    def test_escalates_by_default(self):
        """AutoClarifier should escalate to CODE_GENERATION by default."""
        clarifier = AutoClarifier()
        task = ClassifiedTask(
            original_input="test query",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="test",
        )

        result = clarifier.clarify(task)

        assert result.task_type == TaskType.CODE_GENERATION
        assert "Auto-escalated" in result.reasoning

    @pytest.mark.unit
    def test_keeps_when_configured(self):
        """AutoClarifier with 'keep' should not change task type."""
        clarifier = AutoClarifier(default_action="keep")
        task = ClassifiedTask(
            original_input="test query",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="test",
        )

        result = clarifier.clarify(task)

        assert result.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_does_not_escalate_code_generation(self):
        """AutoClarifier should not change tasks already CODE_GENERATION."""
        clarifier = AutoClarifier()
        task = ClassifiedTask(
            original_input="test query",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.5,
            reasoning="test",
        )

        result = clarifier.clarify(task)

        assert result.task_type == TaskType.CODE_GENERATION
        # Should not have "Auto-escalated" in reasoning since it wasn't escalated
        assert result.reasoning == "test"

    @pytest.mark.unit
    def test_rejects_invalid_action(self):
        """AutoClarifier should reject invalid default_action."""
        with pytest.raises(ValueError):
            AutoClarifier(default_action="invalid")
