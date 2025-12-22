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
            "still need to fix the edge cases",
        ]

        for phrase in incomplete_phrases:
            result = validator.validate(
                tools_executed=['write_file'],
                task_description="Complete the task",
                result_text=f"Done with first part. {phrase}",
            )
            assert not result.allow_completion, f"Should block: {phrase}"

    def test_detects_comment_style_todo(self, validator):
        """Detects TODO in comment format."""
        comment_styles = [
            "# TODO fix this later",
            "// TODO: implement error handling",
            "/* TODO add validation */",
        ]

        for comment in comment_styles:
            result = validator.validate(
                tools_executed=['write_file'],
                task_description="Create a file",
                result_text=f"Created file with {comment}",
            )
            assert not result.allow_completion, f"Should block: {comment}"

    def test_case_insensitive_detection(self, validator):
        """Incomplete indicators are detected case-insensitively."""
        result = validator.validate(
            tools_executed=['write_file'],
            task_description="Create a file",
            result_text="Created file with todo: finish this later",
        )

        assert not result.allow_completion

    def test_no_false_positive_on_todo_mention(self, validator):
        """Does NOT block when TODO is mentioned but not as a marker."""
        false_positive_cases = [
            "I fixed all the TODO items",
            "Addressed the FIXME you mentioned",
            "Resolved the TODO from the previous review",
            "The TODO list is now complete",
        ]

        for text in false_positive_cases:
            result = validator.validate(
                tools_executed=['write_file'],
                task_description="Fix issues",
                result_text=text,
            )
            assert result.allow_completion, f"Should NOT block: {text}"

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

    def test_allows_completion_with_sufficient_investigation(self, validator):
        """Completion allowed when sufficient investigation work performed."""
        # 3+ investigation actions should be enough
        result = validator.validate(
            tools_executed=['read_file', 'read_file', 'search_files'],
            task_description="Check if site is accessible",
            result_text="Site is already accessible, no changes needed.",
        )

        assert result.allow_completion
        assert "validated" in result.reason.lower()

    def test_blocks_insufficient_investigation(self, validator):
        """Completion blocked when investigation work is insufficient."""
        # Only 2 investigation actions - not enough
        result = validator.validate(
            tools_executed=['read_file', 'read_file'],
            task_description="Check the configuration",
            result_text="Config looks fine.",
        )

        assert not result.allow_completion
        assert "No meaningful actions" in result.reason

    def test_mixed_investigation_actions_count(self, validator):
        """Different investigation actions all count toward threshold."""
        result = validator.validate(
            tools_executed=['read_file', 'grep_search', 'list_directory'],
            task_description="Investigate the codebase structure",
            result_text="Codebase follows standard structure.",
        )

        assert result.allow_completion

    def test_investigation_threshold_is_three(self, validator):
        """Exactly 3 investigation actions meets the threshold."""
        # Exactly 3 should pass
        result_pass = validator.validate(
            tools_executed=['read_file', 'read_file', 'read_file'],
            task_description="Review files",
            result_text="Files look good.",
        )
        assert result_pass.allow_completion

        # 2 should fail
        result_fail = validator.validate(
            tools_executed=['read_file', 'read_file'],
            task_description="Review files",
            result_text="Files look good.",
        )
        assert not result_fail.allow_completion


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
