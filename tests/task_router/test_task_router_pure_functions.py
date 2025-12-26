"""
Tests for pure functions extracted from TaskRouter.

These tests verify the pure calculation/decision logic that has been
separated from side effects (I/O, logging, external calls).

Following TDD: these tests are written first to define expected behavior.
"""
import pytest
from dataclasses import dataclass

from scrappy.task_router.classifier import ClassifiedTask, TaskType
from scrappy.task_router.config import ClarificationConfig


# Import the pure functions module (will be created)
from scrappy.task_router.pure_functions import (
    has_action_indicators,
    has_conflicting_signals,
    should_escalate_confidence,
    create_escalated_task,
    needs_clarification,
    determine_execution_action,
    build_classification_metadata,
)


@dataclass
class FakeClarificationConfig:
    """Test double for ClarificationConfigProtocol."""
    confidence_threshold: float = 0.7
    high_confidence_bypass: float = 0.9


class TestHasActionIndicators:
    """Tests for has_action_indicators pure function."""

    @pytest.mark.unit
    def test_case_insensitive(self):
        """Should be case insensitive."""
        assert has_action_indicators("CREATE a file") is True
        assert has_action_indicators("Write Some Code") is True


class TestHasConflictingSignals:
    """Tests for has_conflicting_signals pure function."""

    @pytest.mark.unit
    def test_explain_with_create(self):
        """Should detect conflict between explain and create."""
        text = "explain how to create a file"
        assert has_conflicting_signals(text, TaskType.RESEARCH) is True

    @pytest.mark.unit
    def test_describe_with_build(self):
        """Should detect conflict between describe and build."""
        text = "describe how to build an API"
        assert has_conflicting_signals(text, TaskType.RESEARCH) is True

    @pytest.mark.unit
    def test_question_with_action(self):
        """Should detect conflict in question with action verb."""
        text = "can you create a config file?"
        assert has_conflicting_signals(text, TaskType.RESEARCH) is True

    @pytest.mark.unit
    def test_pure_explanation_no_conflict(self):
        """Should not find conflict in pure explanation."""
        text = "explain dependency injection"
        assert has_conflicting_signals(text, TaskType.RESEARCH) is False

    @pytest.mark.unit
    def test_pure_action_no_conflict(self):
        """Should not find conflict in pure action."""
        text = "create a config file"
        assert has_conflicting_signals(text, TaskType.CODE_GENERATION) is False

    @pytest.mark.unit
    def test_action_classified_as_research_is_conflict(self):
        """Action text classified as RESEARCH is a conflict."""
        text = "create a new user model"
        assert has_conflicting_signals(text, TaskType.RESEARCH) is True


class TestShouldEscalateConfidence:
    """Tests for should_escalate_confidence pure function."""

    @pytest.mark.unit
    def test_low_confidence_with_action_escalates(self):
        """Low confidence RESEARCH with action words should escalate."""
        task = ClassifiedTask(
            original_input="create something",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Low confidence"
        )
        assert should_escalate_confidence(task, threshold=0.7) is True

    @pytest.mark.unit
    def test_high_confidence_no_escalation(self):
        """High confidence tasks should not escalate."""
        task = ClassifiedTask(
            original_input="create something",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="High confidence"
        )
        assert should_escalate_confidence(task, threshold=0.7) is False

    @pytest.mark.unit
    def test_low_confidence_no_action_no_escalation(self):
        """Low confidence without action indicators should not escalate."""
        task = ClassifiedTask(
            original_input="explain python",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Low confidence"
        )
        assert should_escalate_confidence(task, threshold=0.7) is False

    @pytest.mark.unit
    def test_code_generation_no_escalation(self):
        """CODE_GENERATION tasks should never escalate."""
        task = ClassifiedTask(
            original_input="write code",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.4,
            reasoning="Low confidence"
        )
        assert should_escalate_confidence(task, threshold=0.7) is False

    @pytest.mark.unit
    def test_conversation_no_escalation(self):
        """CONVERSATION tasks should never escalate."""
        task = ClassifiedTask(
            original_input="hello",
            task_type=TaskType.CONVERSATION,
            confidence=0.4,
            reasoning="Low confidence"
        )
        assert should_escalate_confidence(task, threshold=0.7) is False

    @pytest.mark.unit
    def test_custom_threshold(self):
        """Should respect custom threshold."""
        task = ClassifiedTask(
            original_input="create file",
            task_type=TaskType.RESEARCH,
            confidence=0.6,
            reasoning="Medium confidence"
        )
        # Below 0.8 threshold, has action
        assert should_escalate_confidence(task, threshold=0.8) is True
        # Above 0.5 threshold
        assert should_escalate_confidence(task, threshold=0.5) is False


class TestCreateEscalatedTask:
    """Tests for create_escalated_task pure function."""

    @pytest.mark.unit
    def test_changes_type_to_code_generation(self):
        """Should change task type to CODE_GENERATION."""
        task = ClassifiedTask(
            original_input="create file",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )
        escalated = create_escalated_task(task)
        assert escalated.task_type == TaskType.CODE_GENERATION

    @pytest.mark.unit
    def test_preserves_original_input(self):
        """Should preserve original input."""
        task = ClassifiedTask(
            original_input="create file",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )
        escalated = create_escalated_task(task)
        assert escalated.original_input == "create file"

    @pytest.mark.unit
    def test_preserves_confidence(self):
        """Should preserve confidence score."""
        task = ClassifiedTask(
            original_input="create file",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )
        escalated = create_escalated_task(task)
        assert escalated.confidence == 0.4

    @pytest.mark.unit
    def test_updates_reasoning(self):
        """Should update reasoning to indicate escalation."""
        task = ClassifiedTask(
            original_input="create file",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )
        escalated = create_escalated_task(task)
        assert "escalat" in escalated.reasoning.lower()
        assert "research" in escalated.reasoning.lower()

    @pytest.mark.unit
    def test_returns_new_instance(self):
        """Should return a new instance, not mutate original."""
        task = ClassifiedTask(
            original_input="create file",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )
        escalated = create_escalated_task(task)
        # Original should be unchanged
        assert task.task_type == TaskType.RESEARCH
        assert task.reasoning == "Original"
        # Escalated should be different
        assert escalated is not task


class TestNeedsClarification:
    """Tests for needs_clarification pure function (backwards compatibility with float)."""

    @pytest.mark.unit
    def test_low_confidence_needs_clarification(self):
        """Low confidence should need clarification."""
        task = ClassifiedTask(
            original_input="do something",
            task_type=TaskType.RESEARCH,
            confidence=0.3,
            reasoning="Low confidence"
        )
        assert needs_clarification(task, 0.65) is True

    @pytest.mark.unit
    def test_high_confidence_no_clarification(self):
        """High confidence should not need clarification."""
        task = ClassifiedTask(
            original_input="explain python",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="High confidence"
        )
        assert needs_clarification(task, 0.65) is False

    @pytest.mark.unit
    def test_conflicting_signals_need_clarification(self):
        """Conflicting signals should need clarification."""
        task = ClassifiedTask(
            original_input="explain how to create a file",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="Has both explain and create"
        )
        assert needs_clarification(task, 0.65) is True

    @pytest.mark.unit
    def test_action_classified_as_research_needs_clarification(self):
        """Action verb classified as RESEARCH should need clarification."""
        task = ClassifiedTask(
            original_input="create a new model",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="Classified as research"
        )
        assert needs_clarification(task, 0.65) is True

    @pytest.mark.unit
    def test_question_with_action_needs_clarification(self):
        """Question with action verb should need clarification."""
        task = ClassifiedTask(
            original_input="can you create a file?",
            task_type=TaskType.RESEARCH,
            confidence=0.7,
            reasoning="Has question mark and create"
        )
        assert needs_clarification(task, 0.65) is True


class TestNeedsClarificationWithConfig:
    """Tests for needs_clarification with ClarificationConfigProtocol."""

    @pytest.mark.unit
    def test_low_confidence_always_needs_clarification(self):
        """Confidence below threshold always needs clarification."""
        config = FakeClarificationConfig(
            confidence_threshold=0.7,
            high_confidence_bypass=0.9
        )
        task = ClassifiedTask(
            original_input="do something",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Low confidence"
        )
        assert needs_clarification(task, config) is True

    @pytest.mark.unit
    def test_high_confidence_bypasses_all_checks(self):
        """Confidence >= high_confidence_bypass skips conflicting signal checks."""
        config = FakeClarificationConfig(
            confidence_threshold=0.7,
            high_confidence_bypass=0.9
        )
        # This task has conflicting signals (question + action verb)
        # but 100% confidence should bypass the check
        task = ClassifiedTask(
            original_input="how to make google?",
            task_type=TaskType.RESEARCH,
            confidence=1.0,
            reasoning="100% confidence research"
        )
        assert needs_clarification(task, config) is False

    @pytest.mark.unit
    def test_high_confidence_with_action_verb_no_clarification(self):
        """High confidence RESEARCH with action verb should NOT clarify (the fix)."""
        config = FakeClarificationConfig(
            confidence_threshold=0.7,
            high_confidence_bypass=0.9
        )
        # This was the bug: "how to make google?" triggered clarification
        # even with 100% confidence because "make" is in strong_action_verbs
        task = ClassifiedTask(
            original_input="how to make google?",
            task_type=TaskType.RESEARCH,
            confidence=1.0,  # 100% confidence
            reasoning="High confidence research query"
        )
        # Should NOT need clarification because confidence >= high_confidence_bypass
        assert needs_clarification(task, config) is False

    @pytest.mark.unit
    def test_medium_confidence_with_conflicting_signals_needs_clarification(self):
        """Medium confidence with conflicting signals needs clarification."""
        config = FakeClarificationConfig(
            confidence_threshold=0.7,
            high_confidence_bypass=0.9
        )
        task = ClassifiedTask(
            original_input="explain how to create a file",
            task_type=TaskType.RESEARCH,
            confidence=0.8,  # Medium: >= 0.7 but < 0.9
            reasoning="Medium confidence"
        )
        # Should need clarification because in medium range AND has conflicting signals
        assert needs_clarification(task, config) is True

    @pytest.mark.unit
    def test_medium_confidence_without_conflicting_signals_no_clarification(self):
        """Medium confidence without conflicting signals should not clarify."""
        config = FakeClarificationConfig(
            confidence_threshold=0.7,
            high_confidence_bypass=0.9
        )
        task = ClassifiedTask(
            original_input="explain python decorators",
            task_type=TaskType.RESEARCH,
            confidence=0.8,  # Medium: >= 0.7 but < 0.9
            reasoning="Medium confidence"
        )
        # Should NOT need clarification because no conflicting signals
        assert needs_clarification(task, config) is False

    @pytest.mark.unit
    def test_at_high_confidence_threshold_no_clarification(self):
        """Exactly at high_confidence_bypass should not need clarification."""
        config = FakeClarificationConfig(
            confidence_threshold=0.7,
            high_confidence_bypass=0.9
        )
        task = ClassifiedTask(
            original_input="create a new file",
            task_type=TaskType.RESEARCH,
            confidence=0.9,  # Exactly at high_confidence_bypass
            reasoning="At threshold"
        )
        # Should NOT need clarification even with action verb
        assert needs_clarification(task, config) is False

    @pytest.mark.unit
    def test_just_below_high_confidence_with_conflict_needs_clarification(self):
        """Just below high_confidence_bypass with conflict should clarify."""
        config = FakeClarificationConfig(
            confidence_threshold=0.7,
            high_confidence_bypass=0.9
        )
        task = ClassifiedTask(
            original_input="create a new file",
            task_type=TaskType.RESEARCH,
            confidence=0.89,  # Just below high_confidence_bypass
            reasoning="Just below threshold"
        )
        # Should need clarification because < 0.9 AND has action verb
        assert needs_clarification(task, config) is True

    @pytest.mark.unit
    def test_with_real_clarification_config(self):
        """Test with real ClarificationConfig dataclass."""
        config = ClarificationConfig(
            confidence_threshold=0.7,
            high_confidence_bypass=0.9
        )
        task = ClassifiedTask(
            original_input="how to make google?",
            task_type=TaskType.RESEARCH,
            confidence=1.0,
            reasoning="High confidence"
        )
        # Should NOT need clarification
        assert needs_clarification(task, config) is False

    @pytest.mark.unit
    def test_backwards_compatibility_with_float(self):
        """Test that float parameter still works for backwards compatibility."""
        task = ClassifiedTask(
            original_input="explain python",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Low confidence"
        )
        # Using float directly should still work
        assert needs_clarification(task, 0.65) is True

    @pytest.mark.unit
    def test_custom_config_thresholds(self):
        """Test with custom threshold values."""
        # Stricter config: require higher confidence
        strict_config = FakeClarificationConfig(
            confidence_threshold=0.8,
            high_confidence_bypass=0.95
        )
        task = ClassifiedTask(
            original_input="create a file",
            task_type=TaskType.RESEARCH,
            confidence=0.75,
            reasoning="Would pass default config"
        )
        # Should need clarification with strict config (0.75 < 0.8)
        assert needs_clarification(task, strict_config) is True

        # Lenient config: accept lower confidence
        lenient_config = FakeClarificationConfig(
            confidence_threshold=0.5,
            high_confidence_bypass=0.8
        )
        task = ClassifiedTask(
            original_input="create a file",
            task_type=TaskType.RESEARCH,
            confidence=0.85,  # >= 0.8 high_confidence_bypass
            reasoning="High confidence"
        )
        # Should NOT need clarification with lenient config
        assert needs_clarification(task, lenient_config) is False

    @pytest.mark.unit
    def test_llm_classification_skips_conflicting_signal_check(self):
        """LLM classification should bypass conflicting signal checks."""
        config = FakeClarificationConfig(
            confidence_threshold=0.7,
            high_confidence_bypass=0.9
        )
        # Task with "add" action word that would normally trigger clarification
        # but was classified by LLM so should be trusted
        task = ClassifiedTask(
            original_input="name the top engineers and add a runner up",
            task_type=TaskType.RESEARCH,
            confidence=0.8,  # Medium confidence (would check for conflicts)
            reasoning="LLM semantic classification: User wants information (was CODE_GENERATION, confidence 0.80)"
        )
        # Should NOT need clarification because LLM was used
        assert needs_clarification(task, config) is False

    @pytest.mark.unit
    def test_non_llm_classification_still_checks_conflicts(self):
        """Rule-based classification should still check conflicting signals."""
        config = FakeClarificationConfig(
            confidence_threshold=0.7,
            high_confidence_bypass=0.9
        )
        # Same input but classified by rules (no "LLM semantic classification" in reasoning)
        task = ClassifiedTask(
            original_input="name the top engineers and add a runner up",
            task_type=TaskType.RESEARCH,
            confidence=0.8,  # Medium confidence
            reasoning="Pattern matched: question"  # Rule-based reasoning
        )
        # Should need clarification because "add" is a conflicting signal
        assert needs_clarification(task, config) is True


class TestDetermineExecutionAction:
    """Tests for determine_execution_action pure function."""

    @pytest.mark.unit
    def test_conversation_auto_executes(self):
        """CONVERSATION tasks should auto-execute."""
        action = determine_execution_action(
            task_type=TaskType.CONVERSATION,
            auto_confirm=False,
            command=None,
            is_safe=True
        )
        assert action == "execute"

    @pytest.mark.unit
    def test_research_auto_executes(self):
        """RESEARCH tasks should auto-execute."""
        action = determine_execution_action(
            task_type=TaskType.RESEARCH,
            auto_confirm=False,
            command=None,
            is_safe=True
        )
        assert action == "execute"

    @pytest.mark.unit
    def test_code_generation_auto_executes(self):
        """CODE_GENERATION tasks should auto-execute (has own approval)."""
        action = determine_execution_action(
            task_type=TaskType.CODE_GENERATION,
            auto_confirm=False,
            command=None,
            is_safe=True
        )
        assert action == "execute"

    @pytest.mark.unit
    def test_direct_command_with_auto_confirm(self):
        """DIRECT_COMMAND with auto_confirm should execute."""
        action = determine_execution_action(
            task_type=TaskType.DIRECT_COMMAND,
            auto_confirm=True,
            command="ls -la",
            is_safe=True
        )
        assert action == "execute"

    @pytest.mark.unit
    def test_direct_command_needs_confirmation(self):
        """DIRECT_COMMAND without auto_confirm should need confirmation."""
        action = determine_execution_action(
            task_type=TaskType.DIRECT_COMMAND,
            auto_confirm=False,
            command="ls -la",
            is_safe=True
        )
        assert action == "confirm"

    @pytest.mark.unit
    def test_unsafe_command_blocked(self):
        """Unsafe commands should be blocked."""
        action = determine_execution_action(
            task_type=TaskType.DIRECT_COMMAND,
            auto_confirm=True,
            command="rm -rf /",
            is_safe=False
        )
        assert action == "block"


class TestBuildClassificationMetadata:
    """Tests for build_classification_metadata pure function."""

    @pytest.mark.unit
    def test_builds_complete_metadata(self):
        """Should build complete metadata dictionary."""
        task = ClassifiedTask(
            original_input="test input",
            task_type=TaskType.RESEARCH,
            confidence=0.85,
            complexity_score=3,
            reasoning="Test reasoning",
            suggested_provider="fast",
            override_provider="cerebras"
        )
        metadata = build_classification_metadata(task, "cerebras", "llama-8b")

        assert metadata["type"] == "research"
        assert metadata["confidence"] == 0.85
        assert metadata["complexity"] == 3
        assert metadata["reasoning"] == "Test reasoning"
        assert metadata["suggested_provider"] == "fast"
        assert metadata["override_provider"] == "cerebras"
        assert metadata["resolved_provider"] == "cerebras"
        assert metadata["resolved_model"] == "llama-8b"

    @pytest.mark.unit
    def test_handles_none_providers(self):
        """Should handle None provider values."""
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="Test"
        )
        metadata = build_classification_metadata(task, None, None)

        assert metadata["resolved_provider"] is None
        assert metadata["resolved_model"] is None

    @pytest.mark.unit
    def test_detects_llm_classification(self):
        """Should detect when LLM classification was used."""
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="LLM semantic classification: determined this is research"
        )
        metadata = build_classification_metadata(task, "cerebras", None)

        assert metadata["used_llm_classification"] is True

    @pytest.mark.unit
    def test_detects_no_llm_classification(self):
        """Should detect when LLM classification was not used."""
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Rule-based classification"
        )
        metadata = build_classification_metadata(task, "cerebras", None)

        assert metadata["used_llm_classification"] is False


class TestPureFunctionIntegration:
    """Integration tests for pure functions working together."""

    @pytest.mark.unit
    def test_escalation_flow(self):
        """Test the full escalation decision flow."""
        # Create a low-confidence task with action indicator
        task = ClassifiedTask(
            original_input="write a python script",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Detected pattern"
        )

        # Check if it should escalate
        if should_escalate_confidence(task, threshold=0.7):
            escalated = create_escalated_task(task)
            assert escalated.task_type == TaskType.CODE_GENERATION
        else:
            pytest.fail("Task should have escalated")

    @pytest.mark.unit
    def test_clarification_flow(self):
        """Test the clarification decision flow."""
        # Create ambiguous task
        task = ClassifiedTask(
            original_input="explain how to create a REST API",
            task_type=TaskType.RESEARCH,
            confidence=0.7,
            reasoning="Has both explain and create"
        )

        # Should need clarification due to conflicting signals
        # (confidence 0.7 is in medium range: >= 0.65 and < 0.9)
        assert needs_clarification(task, 0.65) is True

    @pytest.mark.unit
    def test_execution_decision_flow(self):
        """Test the execution permission flow."""
        # Safe command with auto-confirm
        action = determine_execution_action(
            task_type=TaskType.DIRECT_COMMAND,
            auto_confirm=True,
            command="echo hello",
            is_safe=True
        )
        assert action == "execute"

        # Unsafe command
        action = determine_execution_action(
            task_type=TaskType.DIRECT_COMMAND,
            auto_confirm=True,
            command="rm -rf /",
            is_safe=False
        )
        assert action == "block"
