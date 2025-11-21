"""
Tests for ClassifiedTask immutability.

These tests verify that ClassifiedTask is a frozen dataclass that:
1. Cannot be mutated after creation
2. Can create modified copies using dataclasses.replace()
3. Is hashable (can be used in sets and as dict keys)
4. Maintains equality semantics
"""

import pytest
from dataclasses import FrozenInstanceError, replace

from src.task_router.classifier import ClassifiedTask, TaskType



class TestClassifiedTaskReplace:
    """Tests for creating modified copies using dataclasses.replace()."""

    @pytest.fixture
    def sample_task(self):
        """Create a sample ClassifiedTask for testing."""
        return ClassifiedTask(
            original_input="test input",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="Test reasoning"
        )

    @pytest.mark.unit
    def test_replace_task_type(self, sample_task):
        """Test creating a copy with different task_type."""
        modified = replace(sample_task, task_type=TaskType.CODE_GENERATION)

        # Original unchanged
        assert sample_task.task_type == TaskType.RESEARCH
        # New instance has updated value
        assert modified.task_type == TaskType.CODE_GENERATION
        # Other fields preserved
        assert modified.original_input == sample_task.original_input
        assert modified.confidence == sample_task.confidence
        assert modified.reasoning == sample_task.reasoning

    @pytest.mark.unit
    def test_replace_confidence(self, sample_task):
        """Test creating a copy with different confidence."""
        modified = replace(sample_task, confidence=1.0)

        assert sample_task.confidence == 0.8
        assert modified.confidence == 1.0
        assert modified.task_type == sample_task.task_type

    @pytest.mark.unit
    def test_replace_reasoning(self, sample_task):
        """Test creating a copy with different reasoning."""
        new_reasoning = "User clarified intent"
        modified = replace(sample_task, reasoning=new_reasoning)

        assert sample_task.reasoning == "Test reasoning"
        assert modified.reasoning == new_reasoning

    @pytest.mark.unit
    def test_replace_multiple_fields(self, sample_task):
        """Test creating a copy with multiple fields changed."""
        modified = replace(
            sample_task,
            task_type=TaskType.CODE_GENERATION,
            confidence=1.0,
            reasoning="User confirmed action"
        )

        assert modified.task_type == TaskType.CODE_GENERATION
        assert modified.confidence == 1.0
        assert modified.reasoning == "User confirmed action"
        assert modified.original_input == sample_task.original_input

    @pytest.mark.unit
    def test_replace_provider_fields(self, sample_task):
        """Test replacing provider-related fields."""
        modified = replace(
            sample_task,
            suggested_provider="quality",
            override_provider="fast"
        )

        assert modified.suggested_provider == "quality"
        assert modified.override_provider == "fast"

    @pytest.mark.unit
    def test_replace_returns_new_instance(self, sample_task):
        """Test that replace() returns a new instance, not the same object."""
        modified = replace(sample_task, confidence=0.9)

        assert modified is not sample_task
        assert id(modified) != id(sample_task)


class TestClassifiedTaskHashability:
    """Tests for hashability of frozen ClassifiedTask."""

    @pytest.mark.unit

    @pytest.mark.unit
    def test_task_can_be_used_in_set(self):
        """Test that ClassifiedTask can be added to a set."""
        task1 = ClassifiedTask(
            original_input="test1",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )
        task2 = ClassifiedTask(
            original_input="test2",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.9,
            reasoning="test"
        )

        task_set = {task1, task2}
        assert len(task_set) == 2
        assert task1 in task_set
        assert task2 in task_set

    @pytest.mark.unit
    def test_task_can_be_dict_key(self):
        """Test that ClassifiedTask can be used as dictionary key."""
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )

        task_dict = {task: "some value"}
        assert task_dict[task] == "some value"


class TestClassifiedTaskEquality:
    """Tests for equality comparisons of ClassifiedTask."""

    @pytest.mark.unit
    def test_equal_tasks_are_equal(self):
        """Test that tasks with same values are equal."""
        task1 = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )
        task2 = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )

        assert task1 == task2

    @pytest.mark.unit
    def test_different_tasks_not_equal(self):
        """Test that tasks with different values are not equal."""
        task1 = ClassifiedTask(
            original_input="test1",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )
        task2 = ClassifiedTask(
            original_input="test2",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )

        assert task1 != task2

    @pytest.mark.unit
    def test_replaced_task_not_equal_to_original(self):
        """Test that a replaced task is not equal to original if values differ."""
        original = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )
        modified = replace(original, confidence=0.9)

        assert original != modified


class TestClassifiedTaskConstruction:
    """Tests that verify ClassifiedTask can be properly constructed."""

    @pytest.mark.unit
    def test_construct_with_required_fields_only(self):
        """Test construction with only required fields."""
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )

        assert task.original_input == "test"
        assert task.task_type == TaskType.RESEARCH
        assert task.confidence == 0.8
        assert task.reasoning == "test"
        # Defaults applied
        assert task.extracted_command is None
        assert task.suggested_provider is None
        assert task.override_provider is None
        assert task.complexity_score == 1
        assert task.requires_planning is False
        assert task.requires_tools is False
        assert task.matched_patterns == ()
        assert task.extracted_files == ()
        assert task.extracted_directories == ()

    @pytest.mark.unit
    def test_construct_with_all_fields(self):
        """Test construction with all fields specified."""
        task = ClassifiedTask(
            original_input="git status",
            task_type=TaskType.DIRECT_COMMAND,
            confidence=0.95,
            reasoning="Matched git command pattern",
            extracted_command="git status",
            suggested_provider=None,
            override_provider="fast",
            complexity_score=1,
            requires_planning=False,
            requires_tools=False,
            matched_patterns=("git command",),
            extracted_files=(),
            extracted_directories=()
        )

        assert task.extracted_command == "git status"
        assert task.override_provider == "fast"
        assert task.matched_patterns == ("git command",)

    @pytest.mark.unit
    def test_construct_code_generation_task(self):
        """Test construction of a typical code generation task."""
        task = ClassifiedTask(
            original_input="create requirements.txt",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.85,
            reasoning="File creation pattern detected",
            suggested_provider="quality",
            complexity_score=5,
            requires_planning=True,
            requires_tools=True,
            extracted_files=("requirements.txt",)
        )

        assert task.task_type == TaskType.CODE_GENERATION
        assert task.suggested_provider == "quality"
        assert task.requires_planning is True
        assert "requirements.txt" in task.extracted_files


class TestClassifiedTaskWithTupleFields:
    """Tests for ClassifiedTask behavior with immutable tuple fields.

    Tuple fields ensure complete immutability and hashability.
    """

    @pytest.mark.unit
    def test_default_tuples_use_same_empty_tuple(self):
        """Test that default empty tuple fields may share the same empty tuple object.

        This is fine because empty tuples are immutable singletons in Python.
        """
        task1 = ClassifiedTask(
            original_input="test1",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )
        task2 = ClassifiedTask(
            original_input="test2",
            task_type=TaskType.RESEARCH,
            confidence=0.8,
            reasoning="test"
        )

        # Empty tuples are singletons, so they may be the same object
        # This is fine because tuples are immutable
        assert task1.matched_patterns == task2.matched_patterns == ()
        assert task1.extracted_files == task2.extracted_files == ()
        assert task1.extracted_directories == task2.extracted_directories == ()



class TestIntentClarifierCompatibility:
    """Tests that verify intent clarifiers work correctly with immutable ClassifiedTask.

    These tests ensure the refactored clarifiers use replace() properly.
    """

    @pytest.mark.unit
    def test_interactive_clarifier_returns_new_task_on_research_choice(self):
        """Test that InteractiveClarifier returns a new task when user chooses research."""
        from src.task_router.intent_clarifier import InteractiveClarifier

        # Mock input to return "1" (research)
        clarifier = InteractiveClarifier(
            input_fn=lambda _: "1",
            output_fn=lambda _: None
        )

        original = ClassifiedTask(
            original_input="create something",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.6,
            reasoning="Ambiguous"
        )

        result = clarifier.clarify(original)

        # Should return new instance with RESEARCH type
        assert result is not original
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 1.0
        assert "User clarified" in result.reasoning
        # Original unchanged
        assert original.task_type == TaskType.CODE_GENERATION
        assert original.confidence == 0.6

    @pytest.mark.unit
    def test_interactive_clarifier_returns_new_task_on_action_choice(self):
        """Test that InteractiveClarifier returns a new task when user chooses action."""
        from src.task_router.intent_clarifier import InteractiveClarifier

        # Mock input to return "2" (action)
        clarifier = InteractiveClarifier(
            input_fn=lambda _: "2",
            output_fn=lambda _: None
        )

        original = ClassifiedTask(
            original_input="explain requirements",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Ambiguous"
        )

        result = clarifier.clarify(original)

        # Should return new instance with CODE_GENERATION type
        assert result is not original
        assert result.task_type == TaskType.CODE_GENERATION
        assert result.confidence == 1.0
        # Original unchanged
        assert original.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_interactive_clarifier_keeps_original_on_choice_3(self):
        """Test that InteractiveClarifier returns original task when user chooses keep."""
        from src.task_router.intent_clarifier import InteractiveClarifier

        # Mock input to return "3" (keep)
        clarifier = InteractiveClarifier(
            input_fn=lambda _: "3",
            output_fn=lambda _: None
        )

        original = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Test"
        )

        result = clarifier.clarify(original)

        # Should return the same instance unchanged
        assert result is original

    @pytest.mark.unit
    def test_auto_clarifier_returns_new_task_on_escalate(self):
        """Test that AutoClarifier returns a new task when escalating."""
        from src.task_router.intent_clarifier import AutoClarifier

        clarifier = AutoClarifier(default_action="escalate")

        original = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Test"
        )

        result = clarifier.clarify(original)

        # Should return new instance with CODE_GENERATION type
        assert result is not original
        assert result.task_type == TaskType.CODE_GENERATION
        # Original unchanged
        assert original.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_auto_clarifier_keeps_code_generation(self):
        """Test that AutoClarifier keeps CODE_GENERATION tasks unchanged."""
        from src.task_router.intent_clarifier import AutoClarifier

        clarifier = AutoClarifier(default_action="escalate")

        original = ClassifiedTask(
            original_input="test",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.8,
            reasoning="Test"
        )

        result = clarifier.clarify(original)

        # Should return same instance since already CODE_GENERATION
        assert result is original

    @pytest.mark.unit
    def test_auto_clarifier_keep_action_returns_original(self):
        """Test that AutoClarifier with keep action returns original."""
        from src.task_router.intent_clarifier import AutoClarifier

        clarifier = AutoClarifier(default_action="keep")

        original = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Test"
        )

        result = clarifier.clarify(original)

        # Should return same instance
        assert result is original

    @pytest.mark.unit
    def test_null_clarifier_returns_original(self):
        """Test that NullClarifier returns original task unchanged."""
        from src.task_router.intent_clarifier import NullClarifier

        clarifier = NullClarifier()

        original = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Test"
        )

        result = clarifier.clarify(original)

        # Should return same instance
        assert result is original
