"""Tests for PromptFactory - stateless prompt generation."""


from scrappy.prompts.factory import PromptFactory
from scrappy.prompts.protocols import (
    AgentPromptConfig,
    Platform,
    ResearchPromptConfig,
    ResearchSubtype,
)


class TestChatMode:
    """Tests for chat mode prompts."""

    def test_chat_system_prompt_has_no_tool_instructions(self):
        factory = PromptFactory()
        prompt = factory.create_chat_system_prompt()

        assert "tool" not in prompt.lower()
        assert "json" not in prompt.lower()

    def test_chat_system_prompt_is_simple(self):
        factory = PromptFactory()
        prompt = factory.create_chat_system_prompt()

        # Should have assistant identity and guidelines
        assert "scrappy" in prompt.lower() or "assistant" in prompt.lower()
        # Should be concise (not a complex agent prompt with tools/actions)
        assert len(prompt) < 500  # Chat prompt should be short
        assert "action" not in prompt.lower()  # No agent action instructions

    def test_chat_user_prompt_is_just_query(self):
        factory = PromptFactory()
        query = "What is Python?"
        prompt = factory.create_chat_user_prompt(query)

        assert prompt == query

    def test_chat_user_prompt_preserves_multiline_queries(self):
        factory = PromptFactory()
        query = "Line 1\nLine 2\nLine 3"
        prompt = factory.create_chat_user_prompt(query)

        assert prompt == query


class TestAgentMode:
    """Tests for agent mode prompts."""

    def test_agent_system_prompt_has_tool_instructions(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Read a file",
            working_dir="/test",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "read_file" in prompt
        assert "Tool Usage Rules" in prompt

    def test_agent_system_prompt_includes_platform_windows(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.WINDOWS,
            tool_names=("read_file",),
            original_task="Test task",
            working_dir="C:\\test",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "Windows" in prompt
        assert "cmd.exe" in prompt

    def test_agent_system_prompt_includes_platform_unix(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Test task",
            working_dir="/test",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "Unix" in prompt or "Linux" in prompt

    def test_agent_system_prompt_includes_original_task(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Implement authentication",
            working_dir="/test",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "Implement authentication" in prompt

    def test_agent_system_prompt_includes_working_dir(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Test task",
            working_dir="/my/project/path",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "/my/project/path" in prompt

    def test_agent_system_prompt_includes_tool_usage_rules(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Test task",
            working_dir="/test",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "Tool Usage Rules" in prompt

    def test_agent_system_prompt_includes_efficiency_section(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Test task",
            working_dir="/test",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "Efficiency" in prompt
        assert "redundant" in prompt.lower()

    def test_agent_system_prompt_includes_quality_section(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Test task",
            working_dir="/test",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "Quality" in prompt

    def test_agent_system_prompt_includes_safety_section(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Test task",
            working_dir="/test",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "Safety" in prompt

    def test_agent_system_prompt_includes_security_section(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Test task",
            working_dir="/test",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "Security" in prompt

    def test_agent_system_prompt_includes_error_context(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Test task",
            working_dir="/test",
            last_error="File not found: missing.py",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "File not found: missing.py" in prompt
        assert "Previous Error" in prompt

    def test_agent_system_prompt_includes_files_changed(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Test task",
            working_dir="/test",
            files_changed=("src/main.py", "tests/test_main.py"),
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "src/main.py" in prompt
        assert "tests/test_main.py" in prompt
        assert "Files Modified" in prompt

    def test_agent_user_prompt_includes_task(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Original request",
            working_dir="/test",
        )
        task = "Implement user authentication"
        prompt = factory.create_agent_user_prompt(task, config)

        assert task in prompt
        assert "complete" in prompt.lower() or "task" in prompt.lower()


class TestResearchMode:
    """Tests for research mode prompts."""

    def test_research_general_without_tools_is_simple(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.GENERAL,
            tool_descriptions=None,
        )
        prompt = factory.create_research_system_prompt(config)

        assert "tool" not in prompt.lower()
        assert "helpful" in prompt.lower() or "assistant" in prompt.lower()

    def test_research_general_with_tools_includes_tool_instructions(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.GENERAL,
            tool_descriptions="web_search: Search the web",
        )
        prompt = factory.create_research_system_prompt(config)

        assert "web_search" in prompt
        assert "json" in prompt.lower()

    def test_research_codebase_has_tool_instructions(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.CODEBASE,
            tool_descriptions="search_code: Search in codebase",
        )
        prompt = factory.create_research_system_prompt(config)

        assert "search_code" in prompt
        assert "json" in prompt.lower()

    def test_research_codebase_mentions_codebase_tools(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.CODEBASE,
            tool_descriptions="search_code, read_file, list_directory",
        )
        prompt = factory.create_research_system_prompt(config)

        assert "codebase" in prompt.lower()

    def test_research_codebase_without_tools_still_works(self):
        """Codebase research can work without tool descriptions (might use later)."""
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.CODEBASE,
            tool_descriptions=None,
        )
        prompt = factory.create_research_system_prompt(config)

        assert "codebase" in prompt.lower()

    def test_research_user_prompt_includes_query(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(subtype=ResearchSubtype.GENERAL)
        query = "What is dependency injection?"
        prompt = factory.create_research_user_prompt(query, config)

        assert query in prompt

    def test_research_user_prompt_includes_context_summary(self):
        factory = PromptFactory()
        context = "This is a Python project using FastAPI"
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.CODEBASE,
            context_summary=context,
        )
        prompt = factory.create_research_user_prompt("explain routing", config)

        assert context in prompt

    def test_research_user_prompt_includes_file_hints(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.CODEBASE,
            extracted_files=("src/main.py", "tests/test_main.py"),
        )
        prompt = factory.create_research_user_prompt("explain main.py", config)

        assert "src/main.py" in prompt
        assert "tests/test_main.py" in prompt

    def test_research_user_prompt_includes_directory_hints(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.CODEBASE,
            extracted_directories=("src/utils/", "tests/unit/"),
        )
        prompt = factory.create_research_user_prompt("explain utils", config)

        assert "src/utils/" in prompt
        assert "tests/unit/" in prompt

    def test_research_user_prompt_no_hints_for_general_queries(self):
        """General research shouldn't include file/directory hints."""
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.GENERAL,
            extracted_files=("some_file.py",),  # Should be ignored for GENERAL
        )
        prompt = factory.create_research_user_prompt("what is Python?", config)

        # File hints should NOT appear for GENERAL queries
        assert "some_file.py" not in prompt

    def test_research_user_prompt_encourages_tool_use(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(subtype=ResearchSubtype.CODEBASE)
        prompt = factory.create_research_user_prompt("find error handlers", config)

        assert "tool" in prompt.lower()


class TestFactoryIsStateless:
    """Tests that factory has no state and can be reused."""

    def test_same_factory_instance_produces_consistent_results(self):
        factory = PromptFactory()

        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Read a file",
            working_dir="/test",
        )

        prompt1 = factory.create_agent_system_prompt(config)
        prompt2 = factory.create_agent_system_prompt(config)

        assert prompt1 == prompt2

    def test_factory_can_be_used_for_different_modes(self):
        """Single factory instance can generate prompts for all modes."""
        factory = PromptFactory()

        chat_prompt = factory.create_chat_system_prompt()
        agent_prompt = factory.create_agent_system_prompt(
            AgentPromptConfig(
                platform=Platform.UNIX,
                tool_names=("read_file",),
                original_task="Test task",
                working_dir="/test",
            )
        )
        research_prompt = factory.create_research_system_prompt(
            ResearchPromptConfig(subtype=ResearchSubtype.GENERAL)
        )

        # All prompts should be different
        assert chat_prompt != agent_prompt
        assert chat_prompt != research_prompt
        assert agent_prompt != research_prompt

        # Agent should be most complex (has efficiency, safety, etc.)
        assert len(agent_prompt) > len(chat_prompt)
        assert len(agent_prompt) > len(research_prompt)


class TestDegradedMode:
    """Tests for degraded mode awareness when semantic search unavailable."""

    def test_prompt_includes_degraded_caveat(self):
        """System prompt includes limitation warning when degraded."""
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.CODEBASE,
            semantic_available=False,
        )
        prompt = factory.create_research_system_prompt(config)

        assert "degraded mode" in prompt.lower()
        assert "semantic" in prompt.lower()

    def test_no_caveat_when_semantic_ready(self):
        """No warning when semantic search is ready."""
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.CODEBASE,
            semantic_available=True,
        )
        prompt = factory.create_research_system_prompt(config)

        assert "degraded mode" not in prompt.lower()

    def test_degraded_mode_only_affects_codebase_research(self):
        """General research should not include degraded mode warning."""
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.GENERAL,
            semantic_available=False,
        )
        prompt = factory.create_research_system_prompt(config)

        assert "degraded mode" not in prompt.lower()


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_tool_names_still_works(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=(),
            original_task="Test task",
            working_dir="/test",
        )
        prompt = factory.create_agent_system_prompt(config)

        # Should still have structure even with no tools
        assert "Safety" in prompt
        assert "Efficiency" in prompt

    def test_working_memory_context_included(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_names=("read_file",),
            original_task="Test task",
            working_dir="/test",
            working_memory_context="Previous context from session",
        )
        prompt = factory.create_agent_system_prompt(config)

        # Should work without crashing and include context
        assert "Previous context from session" in prompt

    def test_empty_extracted_files_handled_gracefully(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.CODEBASE,
            extracted_files=(),
        )
        prompt = factory.create_research_user_prompt("test query", config)

        # Should work without crashing
        assert "test query" in prompt
