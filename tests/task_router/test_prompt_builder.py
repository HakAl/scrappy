"""
Tests for PromptBuilder.

Tests the behavior of prompt construction for research tasks,
including tool instructions and context integration.
"""

import pytest
from src.task_router.strategies.prompt_builder import PromptBuilder
from src.task_router.classifier import ClassifiedTask, TaskType


def make_task(
    original_input: str,
    extracted_files: list = None,
    extracted_directories: list = None,
    task_type: TaskType = TaskType.RESEARCH,
    complexity_score: int = 1,
    confidence: float = 0.9,
    reasoning: str = "Test classification"
) -> ClassifiedTask:
    """Factory for creating test tasks."""
    return ClassifiedTask(
        original_input=original_input,
        task_type=task_type,
        confidence=confidence,
        reasoning=reasoning,
        complexity_score=complexity_score,
        extracted_files=tuple(extracted_files or []),
        extracted_directories=tuple(extracted_directories or [])
    )


def mock_tool_descriptions() -> str:
    """Mock tool descriptions provider."""
    return "- web_fetch: Fetch web content\n- read_file: Read a file"


class TestPromptBuilderSystemPrompt:
    """Test system prompt building."""

    def test_builds_basic_prompt_without_tools(self):
        """System prompt without tools returns base prompt only."""
        builder = PromptBuilder()

        result = builder.build_system_prompt(has_tools=False)

        assert result == "You are a helpful research assistant. Provide concise, accurate information."
        assert "Available tools" not in result

    def test_builds_basic_prompt_when_no_tool_provider(self):
        """System prompt with no tool provider returns base prompt."""
        builder = PromptBuilder(tool_descriptions_provider=None)

        result = builder.build_system_prompt(has_tools=True)

        assert result == "You are a helpful research assistant. Provide concise, accurate information."

    def test_builds_full_prompt_with_tools(self):
        """System prompt with tools includes tool instructions and examples."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)

        result = builder.build_system_prompt(has_tools=True)

        assert "You are a helpful research assistant" in result
        assert "Available tools:" in result
        assert "web_fetch: Fetch web content" in result
        assert "read_file: Read a file" in result
        assert "HOW TO USE TOOLS:" in result
        assert "```json" in result
        assert "EXAMPLES FOR WEB/EXTERNAL INFO:" in result
        assert "EXAMPLES FOR CODEBASE SEARCHES:" in result
        assert "CRITICAL RULES:" in result

    def test_system_prompt_includes_json_format_example(self):
        """System prompt shows correct JSON tool call format."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)

        result = builder.build_system_prompt(has_tools=True)

        assert '{"tool": "tool_name", "parameters": {"param1": "value1"}}' in result

    def test_system_prompt_includes_file_search_patterns(self):
        """System prompt explains recursive file search patterns."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)

        result = builder.build_system_prompt(has_tools=True)

        assert "**/" in result
        assert "RECURSIVE search" in result
        assert "CASE-SENSITIVE" in result


class TestPromptBuilderResearchPrompt:
    """Test research prompt building."""

    def test_builds_simple_prompt_without_context(self):
        """Research prompt without context includes only task input."""
        builder = PromptBuilder()
        task = make_task("What is Django?")

        result = builder.build_research_prompt(task)

        assert "User Request:" in result
        assert "What is Django?" in result
        assert "Project Context:" not in result

    def test_builds_prompt_with_context_summary(self):
        """Research prompt with context includes summary."""
        builder = PromptBuilder()
        task = make_task("What is Django?")

        result = builder.build_research_prompt(
            task,
            context_summary="Python web framework project"
        )

        assert "User Request:" in result
        assert "What is Django?" in result
        assert "Project Context:" in result
        assert "Python web framework project" in result

    def test_prompt_ends_with_instruction(self):
        """Research prompt ends with appropriate instruction."""
        builder = PromptBuilder()
        task = make_task("Tell me about React")

        result = builder.build_research_prompt(task)

        assert result.endswith("Respond appropriately. If information is needed, use a tool first.")


class TestPromptBuilderToolHints:
    """Test tool hint generation based on task characteristics."""

    def test_detects_web_query_with_fetch_keyword(self):
        """Detects web query when 'fetch' keyword is present."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task("fetch the latest Django version from PyPI")

        result = builder.build_research_prompt(task)

        assert "This request requires fetching external information" in result
        assert "web_fetch or web_search" in result
        assert "JSON tool call first" in result

    def test_detects_web_query_with_version_keyword(self):
        """Detects web query when 'version' or 'latest' keywords are present."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task("what is the latest version of React?")

        result = builder.build_research_prompt(task)

        assert "This request requires fetching external information" in result

    def test_detects_web_query_with_url(self):
        """Detects web query when URL is present."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task("check https://example.com/docs")

        result = builder.build_research_prompt(task)

        assert "This request requires fetching external information" in result

    def test_detects_codebase_query_with_file_extension(self):
        """Detects codebase query when file extension is mentioned."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task("find all .py files with tests")

        result = builder.build_research_prompt(task)

        assert "LOCAL CODEBASE" in result
        assert "search_code" in result
        assert "read_file" in result
        assert "list_directory" in result

    def test_detects_codebase_query_with_file_path(self):
        """Detects codebase query when file path is mentioned."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task("check the src/main.py file")

        result = builder.build_research_prompt(task)

        assert "LOCAL CODEBASE" in result
        assert "do not guess or make assumptions" in result

    def test_detects_codebase_query_with_keywords(self):
        """Detects codebase query with keywords like 'does the', 'is there'."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task("does the codebase have authentication?")

        result = builder.build_research_prompt(task)

        assert "LOCAL CODEBASE" in result

    def test_excludes_http_from_path_detection(self):
        """Does not treat http:// as a file path."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task("check http://example.com/path")

        result = builder.build_research_prompt(task)

        # Should be detected as web, not codebase
        assert "fetching external information" in result
        assert "LOCAL CODEBASE" not in result

    def test_provides_generic_hint_for_ambiguous_query(self):
        """Provides generic hint when query type is unclear."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task("tell me about the system architecture")

        result = builder.build_research_prompt(task)

        assert "tools available if you need" in result
        assert "This request requires fetching external information" not in result
        assert "LOCAL CODEBASE" not in result

    def test_no_hint_without_tool_provider(self):
        """No tool hint when no tool provider is available."""
        builder = PromptBuilder()
        task = make_task("fetch the latest Django version")

        result = builder.build_research_prompt(task)

        # No tool hints at all
        assert "web_fetch" not in result
        assert "LOCAL CODEBASE" not in result


class TestPromptBuilderCodebaseHints:
    """Test detailed codebase hints with extracted files/directories."""

    def test_includes_detected_files_in_hint(self):
        """Hint includes detected file references."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task(
            "check app.js",
            extracted_files=["frontend/src/app.js"]
        )

        result = builder.build_research_prompt(task)

        assert "Detected file reference(s): frontend/src/app.js" in result

    def test_suggests_search_patterns_for_files(self):
        """Hint suggests file_pattern for search_code."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task(
            "check app.js",
            extracted_files=["frontend/src/app.js"]
        )

        result = builder.build_research_prompt(task)

        assert '-> To search in app.js, use file_pattern: "**/app.js"' in result

    def test_includes_detected_directories_in_hint(self):
        """Hint includes detected directory references."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task(
            "explore frontend folder",
            extracted_directories=["frontend"]
        )

        result = builder.build_research_prompt(task)

        assert "Detected directory reference(s): frontend" in result

    def test_suggests_list_directory_for_directories(self):
        """Hint suggests list_directory for directories."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task(
            "explore frontend folder",
            extracted_directories=["frontend"]
        )

        result = builder.build_research_prompt(task)

        assert '-> To explore frontend/, use: list_directory with path="frontend"' in result

    def test_limits_file_hints_to_two(self):
        """Only suggests search patterns for first two files."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task(
            "check multiple files",
            extracted_files=["file1.js", "file2.js", "file3.js", "file4.js"]
        )

        result = builder.build_research_prompt(task)

        # Should list all files but only suggest patterns for first two
        assert "file1.js, file2.js, file3.js, file4.js" in result
        assert "file1.js" in result
        assert "file2.js" in result
        # file3 and file4 should not have individual suggestions
        suggestion_count = result.count("-> To search in")
        assert suggestion_count == 2

    def test_limits_directory_hints_to_two(self):
        """Only suggests list_directory for first two directories."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task(
            "check the src/ and tests/ folders",
            extracted_directories=["dir1", "dir2", "dir3", "dir4"]
        )

        result = builder.build_research_prompt(task)

        # Should list all but only suggest for first two
        assert "dir1, dir2, dir3, dir4" in result
        suggestion_count = result.count("-> To explore")
        assert suggestion_count == 2


class TestPromptBuilderEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_handles_empty_task_input(self):
        """Handles task with empty input string."""
        builder = PromptBuilder()
        task = make_task("")

        result = builder.build_research_prompt(task)

        assert "User Request:" in result
        assert "Respond appropriately" in result

    def test_handles_none_context_summary(self):
        """Handles None context summary gracefully."""
        builder = PromptBuilder()
        task = make_task("test query")

        result = builder.build_research_prompt(task, context_summary=None)

        assert "Project Context:" not in result

    def test_handles_empty_context_summary(self):
        """Handles empty string context summary."""
        builder = PromptBuilder()
        task = make_task("test query")

        result = builder.build_research_prompt(task, context_summary="")

        # Empty context summary should not be included
        assert "Project Context:" not in result

    def test_handles_task_with_empty_extracted_lists(self):
        """Handles task with empty extracted files/directories."""
        builder = PromptBuilder(tool_descriptions_provider=mock_tool_descriptions)
        task = make_task(
            "check the codebase",
            extracted_files=[],
            extracted_directories=[]
        )

        result = builder.build_research_prompt(task)

        # Should still provide codebase hint but without specific file suggestions
        assert "LOCAL CODEBASE" in result
        assert "Detected file reference" not in result
        assert "Detected directory reference" not in result
