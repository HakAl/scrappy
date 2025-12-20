"""Tests for completion validation."""

import pytest

from scrappy.agent.completion_validator import (
    CompletionValidator,
    CompletionValidation,
)


class TestCompletionValidator:
    """Tests for CompletionValidator."""

    @pytest.fixture
    def validator(self):
        """Create validator with default meaningful actions."""
        return CompletionValidator(
            meaningful_actions={'write_file', 'run_command', 'apply_diff'}
        )

    def test_blocks_completion_without_meaningful_work(self, validator):
        """Completion blocked when no meaningful actions performed."""
        result = validator.validate(
            tools_executed=['read_file', 'list_files'],
            task_description="Create a test file",
            result_text=None,
        )

        assert not result.allow_completion
        assert "No meaningful actions" in result.reason
        assert len(result.suggestions) > 0

    def test_allows_completion_with_meaningful_work(self, validator):
        """Completion allowed when meaningful actions performed."""
        result = validator.validate(
            tools_executed=['read_file', 'write_file'],
            task_description="Create a test file",
            result_text="Created test.py",
        )

        assert result.allow_completion
        assert "validated" in result.reason.lower()

    def test_allows_completion_on_second_attempt(self, validator):
        """Completion allowed on second attempt even without meaningful work."""
        result = validator.validate(
            tools_executed=['read_file', 'list_files'],
            task_description="Investigate the codebase",
            result_text=None,
            complete_attempts=1,
        )

        assert result.allow_completion
        assert "prior attempt" in result.reason.lower()

    def test_blocks_on_first_attempt_only(self, validator):
        """First attempt (complete_attempts=0) is blocked without meaningful work."""
        result = validator.validate(
            tools_executed=['read_file'],
            task_description="Create a file",
            result_text=None,
            complete_attempts=0,
        )

        assert not result.allow_completion

    def test_detects_todo_in_result(self, validator):
        """Detects TODO marker in completion message."""
        result = validator.validate(
            tools_executed=['write_file'],
            task_description="Create a file",
            result_text="Created file with TODO: implement the rest",
        )

        assert not result.allow_completion
        assert "TODO" in result.reason

    def test_detects_fixme_in_result(self, validator):
        """Detects FIXME marker in completion message."""
        result = validator.validate(
            tools_executed=['write_file'],
            task_description="Fix the bug",
            result_text="Fixed part of it. FIXME: edge cases remain",
        )

        assert not result.allow_completion
        assert "FIXME" in result.reason

    def test_detects_incomplete_phrases(self, validator):
        """Detects phrases indicating incomplete work."""
        incomplete_phrases = [
            "will implement later",
            "need to add more tests",
            "remaining work includes",
            "still need to fix",
        ]

        for phrase in incomplete_phrases:
            result = validator.validate(
                tools_executed=['write_file'],
                task_description="Complete the task",
                result_text=f"Done with first part. {phrase}",
            )
            assert not result.allow_completion, f"Should block: {phrase}"

    def test_case_insensitive_detection(self, validator):
        """Incomplete indicators are detected case-insensitively."""
        result = validator.validate(
            tools_executed=['write_file'],
            task_description="Create a file",
            result_text="Created file with todo items remaining",
        )

        assert not result.allow_completion

    def test_allows_clean_completion(self, validator):
        """Allows completion when result text is clean."""
        result = validator.validate(
            tools_executed=['write_file', 'run_command'],
            task_description="Create and test the feature",
            result_text="Successfully created feature and all tests pass.",
        )

        assert result.allow_completion

    def test_empty_tools_list_blocks(self, validator):
        """Empty tools list blocks completion."""
        result = validator.validate(
            tools_executed=[],
            task_description="Do something",
            result_text=None,
        )

        assert not result.allow_completion
        assert "No meaningful actions" in result.reason

    def test_none_result_text_allowed_with_meaningful_work(self, validator):
        """None result text is fine if meaningful work was done."""
        result = validator.validate(
            tools_executed=['run_command'],
            task_description="Run the build",
            result_text=None,
        )

        assert result.allow_completion


class TestCompletionValidation:
    """Tests for CompletionValidation dataclass."""

    def test_default_suggestions_empty(self):
        """Suggestions default to empty list."""
        validation = CompletionValidation(
            allow_completion=True,
            reason="Test"
        )

        assert validation.suggestions == []

    def test_with_suggestions(self):
        """Suggestions can be provided."""
        validation = CompletionValidation(
            allow_completion=False,
            reason="Incomplete",
            suggestions=["Do X", "Do Y"]
        )

        assert len(validation.suggestions) == 2
        assert "Do X" in validation.suggestions
