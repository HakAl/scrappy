"""Tests for orchestrator Pydantic models."""

import pytest
from pydantic import ValidationError

from scrappy.orchestrator.models import (
    TaskType,
    TaskClassification,
    AgentAction,
    ResearchResult,
    CodeChangeResult,
)


class TestTaskType:
    """Tests for TaskType enum."""

    def test_has_expected_values(self):
        """TaskType has all expected task categories."""
        assert TaskType.DIRECT_COMMAND == "direct_command"
        assert TaskType.CODE_GENERATION == "code_generation"
        assert TaskType.RESEARCH == "research"
        assert TaskType.CONVERSATION == "conversation"

    def test_is_string_enum(self):
        """TaskType values are strings for serialization."""
        for task_type in TaskType:
            assert isinstance(task_type.value, str)

    def test_all_values_unique(self):
        """All TaskType values are unique."""
        values = [t.value for t in TaskType]
        assert len(values) == len(set(values))


class TestTaskClassification:
    """Tests for TaskClassification model."""

    def test_valid_classification(self):
        """Creates valid TaskClassification with all required fields."""
        classification = TaskClassification(
            task_type=TaskType.CODE_GENERATION,
            confidence=0.85,
            reasoning="User asked to write a function",
        )
        assert classification.task_type == TaskType.CODE_GENERATION
        assert classification.confidence == 0.85
        assert classification.reasoning == "User asked to write a function"

    def test_confidence_lower_bound(self):
        """Confidence must be >= 0.0."""
        with pytest.raises(ValidationError) as exc_info:
            TaskClassification(
                task_type=TaskType.RESEARCH,
                confidence=-0.1,
                reasoning="test",
            )
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_confidence_upper_bound(self):
        """Confidence must be <= 1.0."""
        with pytest.raises(ValidationError) as exc_info:
            TaskClassification(
                task_type=TaskType.RESEARCH,
                confidence=1.1,
                reasoning="test",
            )
        assert "less than or equal to 1" in str(exc_info.value)

    def test_confidence_at_bounds(self):
        """Confidence accepts boundary values 0.0 and 1.0."""
        low = TaskClassification(
            task_type=TaskType.CONVERSATION,
            confidence=0.0,
            reasoning="uncertain",
        )
        high = TaskClassification(
            task_type=TaskType.DIRECT_COMMAND,
            confidence=1.0,
            reasoning="certain",
        )
        assert low.confidence == 0.0
        assert high.confidence == 1.0

    def test_task_type_from_string(self):
        """TaskType can be provided as string value."""
        classification = TaskClassification(
            task_type="code_generation",
            confidence=0.9,
            reasoning="test",
        )
        assert classification.task_type == TaskType.CODE_GENERATION


class TestAgentAction:
    """Tests for AgentAction model."""

    def test_valid_action_with_parameters(self):
        """Creates valid AgentAction with all fields."""
        action = AgentAction(
            thought="I need to read the file first",
            tool="read_file",
            parameters={"path": "src/main.py", "encoding": "utf-8"},
        )
        assert action.thought == "I need to read the file first"
        assert action.tool == "read_file"
        assert action.parameters == {"path": "src/main.py", "encoding": "utf-8"}

    def test_parameters_default_to_empty_dict(self):
        """Parameters defaults to empty dict if not provided."""
        action = AgentAction(
            thought="Simple action",
            tool="list_files",
        )
        assert action.parameters == {}

    def test_parameters_accepts_nested_structures(self):
        """Parameters can contain nested dicts and lists."""
        action = AgentAction(
            thought="Complex operation",
            tool="batch_process",
            parameters={
                "files": ["a.py", "b.py"],
                "options": {"recursive": True, "depth": 3},
            },
        )
        assert action.parameters["files"] == ["a.py", "b.py"]
        assert action.parameters["options"]["recursive"] is True


class TestResearchResult:
    """Tests for ResearchResult model."""

    def test_valid_research_result(self):
        """Creates valid ResearchResult with all fields."""
        result = ResearchResult(
            summary="Found 3 relevant articles",
            sources=["arxiv.org", "github.com"],
            confidence=0.75,
            follow_up_needed=True,
            follow_up_questions=["What about edge cases?"],
        )
        assert result.summary == "Found 3 relevant articles"
        assert len(result.sources) == 2
        assert result.confidence == 0.75
        assert result.follow_up_needed is True
        assert len(result.follow_up_questions) == 1

    def test_default_values(self):
        """ResearchResult uses sensible defaults."""
        result = ResearchResult(
            summary="Basic findings",
            confidence=0.5,
        )
        assert result.sources == []
        assert result.follow_up_needed is False
        assert result.follow_up_questions == []


class TestCodeChangeResult:
    """Tests for CodeChangeResult model."""

    def test_valid_code_change_result(self):
        """Creates valid CodeChangeResult with all fields."""
        result = CodeChangeResult(
            files_changed=["src/main.py", "tests/test_main.py"],
            summary="Added new feature X",
            tests_needed=True,
            review_notes="Please check the edge case handling",
        )
        assert len(result.files_changed) == 2
        assert result.summary == "Added new feature X"
        assert result.tests_needed is True
        assert result.review_notes == "Please check the edge case handling"

    def test_default_values(self):
        """CodeChangeResult uses sensible defaults."""
        result = CodeChangeResult(
            files_changed=["file.py"],
            summary="Minor fix",
        )
        assert result.tests_needed is False
        assert result.review_notes is None

    def test_empty_files_changed_allowed(self):
        """Empty files_changed list is allowed (no changes made)."""
        result = CodeChangeResult(
            files_changed=[],
            summary="No changes needed",
        )
        assert result.files_changed == []
