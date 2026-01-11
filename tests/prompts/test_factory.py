"""Tests for PromptFactory.

Tests cover:
- AgentPromptConfig creation and validation
- create_agent_system_prompt output structure
- Dynamic state inclusion (errors, files, memory, RAG)
- Platform-specific sections
"""

import pytest

from scrappy.prompts.factory import PromptFactory
from scrappy.prompts.protocols import AgentPromptConfig, Platform


class TestAgentPromptConfig:
    """Test AgentPromptConfig dataclass."""

    def test_required_fields_only(self):
        """Config with only required fields should work."""
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file", "write_file"),
            original_task="Fix the bug",
            working_dir="/home/user/project",
        )
        assert config.platform == Platform.UNIX
        assert config.tool_names == ("read_file", "write_file")
        assert config.iteration == 0  # default
        assert config.last_error is None

    def test_all_fields(self):
        """Config with all fields should work."""
        config = AgentPromptConfig(
            platform=Platform.WINDOWS,
            tool_names=("read_file",),
            original_task="Add feature",
            working_dir="C:\\Users\\dev\\project",
            iteration=5,
            last_error="File not found",
            files_changed=("src/main.py", "tests/test_main.py"),
            working_memory_context="Previous context here",
            search_strategy="Use semantic search first",
            rag_context="Relevant code snippets",
        )
        assert config.iteration == 5
        assert config.last_error == "File not found"
        assert len(config.files_changed) == 2


class TestPromptFactoryAgent:
    """Test PromptFactory.create_agent_system_prompt."""

    @pytest.fixture
    def factory(self):
        return PromptFactory()

    @pytest.fixture
    def basic_config(self):
        return AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file", "write_file", "complete"),
            original_task="Help me fix the login bug",
            working_dir="/home/user/myproject",
        )

    def test_includes_user_task(self, factory, basic_config):
        """Prompt should include the users task in XML tags."""
        prompt = factory.create_agent_system_prompt(basic_config)
        assert "<user_input>" in prompt
        assert "Help me fix the login bug" in prompt
        assert "</user_input>" in prompt

    def test_includes_tools_list(self, factory, basic_config):
        """Prompt should list available tools."""
        prompt = factory.create_agent_system_prompt(basic_config)
        assert "read_file" in prompt
        assert "write_file" in prompt
        assert "complete" in prompt

    def test_includes_working_dir(self, factory, basic_config):
        """Prompt should include working directory in XML tags."""
        prompt = factory.create_agent_system_prompt(basic_config)
        assert "<working_dir>" in prompt
        assert "/home/user/myproject" in prompt

    def test_includes_iteration(self, factory, basic_config):
        """Prompt should include iteration count."""
        prompt = factory.create_agent_system_prompt(basic_config)
        assert "## Iteration" in prompt
        assert "0" in prompt

    def test_unix_platform_section(self, factory, basic_config):
        """Unix config should include Unix-specific instructions."""
        prompt = factory.create_agent_system_prompt(basic_config)
        assert "Unix" in prompt or "unix" in prompt.lower()

    def test_windows_platform_section(self, factory):
        """Windows config should include Windows-specific instructions."""
        config = AgentPromptConfig(
            platform=Platform.WINDOWS,
            tool_names=("read_file",),
            original_task="Task",
            working_dir="C:\\Project",
        )
        prompt = factory.create_agent_system_prompt(config)
        assert "Windows" in prompt

    def test_includes_error_context(self, factory):
        """Prompt should include error context when present."""
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Task",
            working_dir="/tmp",
            last_error="FileNotFoundError: config.yaml not found",
        )
        prompt = factory.create_agent_system_prompt(config)
        assert "## Previous Error" in prompt
        assert "<error_context>" in prompt
        assert "FileNotFoundError" in prompt

    def test_excludes_error_when_none(self, factory, basic_config):
        """Prompt should not have error section when no error."""
        prompt = factory.create_agent_system_prompt(basic_config)
        assert "## Previous Error" not in prompt

    def test_includes_files_changed(self, factory):
        """Prompt should include files changed list."""
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Task",
            working_dir="/tmp",
            files_changed=("src/main.py", "README.md"),
        )
        prompt = factory.create_agent_system_prompt(config)
        assert "## Files Modified" in prompt
        assert "src/main.py" in prompt
        assert "README.md" in prompt

    def test_excludes_files_when_empty(self, factory, basic_config):
        """Prompt should not have files section when none changed."""
        prompt = factory.create_agent_system_prompt(basic_config)
        assert "## Files Modified" not in prompt

    def test_includes_working_memory(self, factory):
        """Prompt should include working memory context."""
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Task",
            working_dir="/tmp",
            working_memory_context="User prefers Python 3.11",
        )
        prompt = factory.create_agent_system_prompt(config)
        assert "## Session Context" in prompt
        assert "User prefers Python 3.11" in prompt

    def test_includes_search_strategy(self, factory):
        """Prompt should include search strategy when provided."""
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Task",
            working_dir="/tmp",
            search_strategy="Use semantic_search for concepts, grep for literals",
        )
        prompt = factory.create_agent_system_prompt(config)
        assert "semantic_search" in prompt

    def test_includes_rag_context(self, factory):
        """Prompt should include RAG context when provided."""
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Task",
            working_dir="/tmp",
            rag_context="## Relevant Code\ndef login(): pass",
        )
        prompt = factory.create_agent_system_prompt(config)
        assert "def login():" in prompt

    def test_includes_safety_section(self, factory, basic_config):
        """Prompt should include safety guidelines."""
        prompt = factory.create_agent_system_prompt(basic_config)
        assert "Safety" in prompt

    def test_includes_security_section(self, factory, basic_config):
        """Prompt should include security guidelines."""
        prompt = factory.create_agent_system_prompt(basic_config)
        assert "Security" in prompt

    def test_no_emojis_guideline(self, factory, basic_config):
        """Prompt should instruct not to use emojis."""
        prompt = factory.create_agent_system_prompt(basic_config)
        assert "Do not use emojis" in prompt


class TestPromptFactoryChat:
    """Test PromptFactory chat methods."""

    @pytest.fixture
    def factory(self):
        return PromptFactory()

    def test_chat_system_prompt_simple(self, factory):
        """Chat system prompt should be simple and direct."""
        prompt = factory.create_chat_system_prompt()
        assert "Scrappy" in prompt
        assert len(prompt) < 500  # Should be concise

    def test_chat_user_prompt_passthrough(self, factory):
        """Chat user prompt should just return the query."""
        query = "How do I use pytest fixtures?"
        prompt = factory.create_chat_user_prompt(query)
        assert prompt == query
