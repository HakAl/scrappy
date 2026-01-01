"""Unit tests for AgentState model."""

import json
import pytest

from scrappy.graph.state import AgentState


class TestAgentStateCreation:
    """Tests for AgentState creation and initialization."""

    def test_create_initial_state(self) -> None:
        """Test creating initial state with factory method."""
        state = AgentState.create_initial("Write hello world", "/tmp/project")

        assert state.input == "Write hello world"
        assert state.original_task == "Write hello world"
        assert state.working_dir == "/tmp/project"
        assert state.iteration == 0
        assert state.done is False
        assert state.error_count == 0
        assert state.messages == []
        assert state.files_changed == []
        assert state.current_tier == "fast"

    def test_create_with_defaults(self) -> None:
        """Test creating state with minimal required fields."""
        state = AgentState(input="test", original_task="test")

        assert state.input == "test"
        assert state.working_dir == "."
        assert state.current_tier == "fast"

    def test_all_fields_have_meaningful_descriptions(self) -> None:
        """Verify all fields have non-trivial documentation (>10 chars)."""
        for field_name, field_info in AgentState.model_fields.items():
            desc = field_info.description or ""
            assert len(desc) > 10, (
                f"Field '{field_name}' has trivial or missing description: '{desc}'"
            )


class TestAgentStateJsonSerialization:
    """Tests for JSON serialization (required for SqliteSaver)."""

    def test_json_round_trip(self) -> None:
        """Test state survives JSON serialization and deserialization."""
        original = AgentState.create_initial("test task", "/home/user/project")
        original = original.model_copy(update={
            "iteration": 5,
            "messages": [{"role": "user", "content": "hello"}],
            "files_changed": ["file1.py", "file2.py"],
            "last_error": "Something went wrong",
        })

        # Serialize to JSON string
        json_dict = original.model_dump_json_safe()
        json_str = json.dumps(json_dict)

        # Deserialize back
        parsed = json.loads(json_str)
        restored = AgentState(**parsed)

        # Verify all fields match
        assert restored.input == original.input
        assert restored.original_task == original.original_task
        assert restored.iteration == original.iteration
        assert restored.messages == original.messages
        assert restored.files_changed == original.files_changed
        assert restored.last_error == original.last_error

    def test_nested_dict_serialization(self) -> None:
        """Test nested dicts in messages serialize correctly."""
        state = AgentState(
            input="test",
            original_task="test",
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi", "tool_calls": [{"id": "1", "name": "read"}]},
            ],
            pending_confirmation={"type": "command", "command": "rm -rf /"},
        )

        json_dict = state.model_dump_json_safe()
        json_str = json.dumps(json_dict)  # Should not raise

        restored = AgentState(**json.loads(json_str))
        assert restored.messages == state.messages
        assert restored.pending_confirmation == state.pending_confirmation


class TestAgentStateUpdates:
    """Tests for state update patterns."""

    def test_immutable_style_update(self) -> None:
        """Test that model_copy creates new instance without mutating original."""
        original = AgentState.create_initial("task", ".")

        updated = original.model_copy(update={"iteration": 1, "done": True})

        # Original unchanged
        assert original.iteration == 0
        assert original.done is False

        # Updated has new values
        assert updated.iteration == 1
        assert updated.done is True

    def test_update_messages(self) -> None:
        """Test appending to messages list."""
        state = AgentState.create_initial("task", ".")

        new_messages = state.messages + [{"role": "user", "content": "new message"}]
        updated = state.model_copy(update={"messages": new_messages})

        assert len(updated.messages) == 1
        assert len(state.messages) == 0  # Original unchanged

    def test_update_files_changed(self) -> None:
        """Test tracking changed files."""
        state = AgentState.create_initial("task", ".")

        updated = state.model_copy(update={
            "files_changed": state.files_changed + ["new_file.py"]
        })

        assert "new_file.py" in updated.files_changed
        assert len(state.files_changed) == 0


class TestAgentStateValidation:
    """Tests for Pydantic validation."""

    def test_validate_on_assignment(self) -> None:
        """Test that invalid assignments raise errors."""
        state = AgentState.create_initial("task", ".")

        # This should work (valid tier)
        state.current_tier = "quality"
        assert state.current_tier == "quality"

    def test_required_fields(self) -> None:
        """Test that required fields must be provided."""
        with pytest.raises(Exception):  # ValidationError
            AgentState()  # Missing input and original_task


class TestAgentStateEdgeCases:
    """Edge case tests for unusual or boundary inputs."""

    def test_empty_task_string_is_allowed(self) -> None:
        """Empty task string is allowed (may be intentional)."""
        state = AgentState.create_initial("", "/tmp")
        assert state.input == ""
        assert state.original_task == ""

    def test_whitespace_only_task_is_allowed(self) -> None:
        """Whitespace-only task is allowed."""
        state = AgentState.create_initial("   ", "/tmp")
        assert state.input == "   "

    def test_unicode_in_task(self) -> None:
        """Unicode characters in task are handled correctly."""
        unicode_task = "Implement feature for users"
        state = AgentState.create_initial(unicode_task, "/tmp")
        assert state.input == unicode_task

    def test_emoji_in_task(self) -> None:
        """Emoji in task are handled correctly."""
        emoji_task = "Fix the bug in main.py"
        state = AgentState.create_initial(emoji_task, "/tmp")
        assert state.input == emoji_task

    def test_very_long_task_string(self) -> None:
        """Very long task strings are handled."""
        long_task = "x" * 10000
        state = AgentState.create_initial(long_task, "/tmp")
        assert len(state.input) == 10000

    def test_empty_working_dir_raises(self) -> None:
        """Empty working_dir should raise ValidationError."""
        with pytest.raises(Exception):  # ValidationError
            AgentState.create_initial("task", "")

    def test_whitespace_only_working_dir_raises(self) -> None:
        """Whitespace-only working_dir should raise ValidationError."""
        with pytest.raises(Exception):  # ValidationError
            AgentState.create_initial("task", "   ")

    def test_unicode_path_in_working_dir(self) -> None:
        """Unicode paths in working_dir are allowed."""
        state = AgentState.create_initial("task", "/home/user/project")
        assert "project" in state.working_dir

    def test_unicode_in_messages(self) -> None:
        """Unicode in message content is preserved."""
        state = AgentState(
            input="test",
            original_task="test",
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert state.messages[0]["content"] == "Hello"

    def test_newlines_in_task(self) -> None:
        """Newlines in task are preserved."""
        multiline = "Line 1\nLine 2\nLine 3"
        state = AgentState.create_initial(multiline, "/tmp")
        assert "\n" in state.input

    def test_null_bytes_in_task(self) -> None:
        """Null bytes in task are handled (though unusual)."""
        with_null = "before\x00after"
        state = AgentState.create_initial(with_null, "/tmp")
        assert "\x00" in state.input

    def test_message_with_empty_content(self) -> None:
        """Messages with empty content are allowed."""
        state = AgentState(
            input="test",
            original_task="test",
            messages=[{"role": "assistant", "content": ""}],
        )
        assert state.messages[0]["content"] == ""

    def test_tool_result_with_only_name(self) -> None:
        """Tool results with only name (no result or error) are valid."""
        state = AgentState(
            input="test",
            original_task="test",
            tool_results=[{"name": "test_tool"}],
        )
        assert state.tool_results[0]["name"] == "test_tool"

    def test_files_changed_with_special_chars(self) -> None:
        """Files with special characters in names are allowed."""
        state = AgentState(
            input="test",
            original_task="test",
            files_changed=["file with spaces.py", "file-with-dashes.py"],
        )
        assert len(state.files_changed) == 2

    def test_json_serialization_with_unicode(self) -> None:
        """JSON serialization preserves unicode correctly."""
        state = AgentState(
            input="Unicode test",
            original_task="Unicode test",
            messages=[{"role": "user", "content": "Hello world"}],
        )
        json_dict = state.model_dump_json_safe()
        json_str = json.dumps(json_dict)
        restored = AgentState(**json.loads(json_str))
        assert "" in restored.input
        assert "" in restored.messages[0]["content"]
