"""Tests for pure prompt section functions."""

import pytest

from scrappy.prompts.protocols import Platform
from scrappy.prompts.sections import (
    codebase_hint_section,
    codebase_structure_section,
    completion_section,
    efficiency_section,
    platform_section,
    project_section,
    safety_section,
    strategy_section,
    tool_format_section,
)


class TestPlatformSection:
    """Tests for platform_section function."""

    def test_windows_platform_includes_cmd_exe(self):
        result = platform_section(Platform.WINDOWS)

        assert "cmd.exe" in result
        assert "Windows" in result

    def test_windows_platform_warns_against_powershell(self):
        result = platform_section(Platform.WINDOWS)

        assert "PowerShell" in result
        assert "NOT" in result

    def test_windows_platform_includes_backslash_info(self):
        result = platform_section(Platform.WINDOWS)

        assert "backslash" in result

    def test_unix_platform_includes_unix_commands(self):
        result = platform_section(Platform.UNIX)

        assert "Unix" in result or "Linux" in result
        assert "mkdir -p" in result or "cp" in result

    def test_unix_platform_includes_forward_slash_info(self):
        result = platform_section(Platform.UNIX)

        assert "forward slash" in result or "/" in result


class TestProjectSection:
    """Tests for project_section function."""










class TestCodebaseStructureSection:
    """Tests for codebase_structure_section function."""





class TestToolFormatSection:
    """Tests for tool_format_section function."""

    def test_with_json_true_includes_json_format(self):
        result = tool_format_section(use_json=True)

        assert "json" in result.lower()
        assert "tool" in result.lower()

    def test_with_json_true_includes_lowercase_boolean_warning(self):
        result = tool_format_section(use_json=True)

        assert "lowercase" in result.lower()
        assert "true/false" in result.lower()


    def test_default_is_json_true(self):
        result = tool_format_section()

        assert "json" in result.lower()


class TestStrategySection:
    """Tests for strategy_section function."""

    def test_includes_write_file_preference(self):
        result = strategy_section()

        assert "write_file" in result.lower()

    def test_mentions_scaffolding_tools(self):
        result = strategy_section()

        assert "scaffolding" in result.lower() or "curl" in result or "npm create" in result


class TestEfficiencySection:
    """Tests for efficiency_section function."""

    def test_mentions_avoiding_redundancy(self):
        result = efficiency_section()

        assert "redundant" in result.lower()

    def test_mentions_reusing_information(self):
        result = efficiency_section()

        assert "reuse" in result.lower()

    def test_mentions_not_rereading_files(self):
        result = efficiency_section()

        assert "re-read" in result.lower() or "already seen" in result.lower()


class TestCompletionSection:
    """Tests for completion_section function."""

    def test_mentions_marking_complete_when_done(self):
        result = completion_section()

        assert "complete" in result.lower()
        assert "primary goal" in result.lower() or "main goal" in result.lower() or "done" in result.lower()

    def test_warns_against_optional_extras(self):
        result = completion_section()

        assert "optional" in result.lower() or "extras" in result.lower()


class TestSafetySection:
    """Tests for safety_section function."""

    def test_warns_about_json_boolean_format(self):
        result = safety_section()

        assert "true/false" in result.lower()
        assert "lowercase" in result.lower()

    def test_warns_against_empty_files(self):
        result = safety_section()

        assert "empty file" in result.lower()

    def test_encourages_incremental_changes(self):
        result = safety_section()

        assert "incremental" in result.lower() or "careful" in result.lower()


class TestCodebaseHintSection:
    """Tests for codebase_hint_section function."""

    def test_with_files_includes_file_references(self):
        files = ("src/main.py", "tests/test_main.py")
        result = codebase_hint_section(files, ())

        assert "src/main.py" in result
        assert "tests/test_main.py" in result
        assert "file reference" in result.lower()

    def test_with_directories_includes_directory_references(self):
        dirs = ("src/utils", "tests/unit")
        result = codebase_hint_section((), dirs)

        assert "src/utils" in result
        assert "tests/unit" in result
        assert "directory reference" in result.lower()

    def test_with_both_includes_both_sections(self):
        files = ("src/main.py",)
        dirs = ("tests/",)
        result = codebase_hint_section(files, dirs)

        assert "src/main.py" in result
        assert "tests/" in result
        assert "file reference" in result.lower()
        assert "directory reference" in result.lower()


    def test_starts_with_newlines_for_spacing(self):
        files = ("src/main.py",)
        result = codebase_hint_section(files, ())

        assert result.startswith("\n")
