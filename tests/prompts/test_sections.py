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

    def test_python_project_includes_pip(self):
        result = project_section("python")

        assert "pip" in result
        assert "pytest" in result

    def test_python_project_includes_venv(self):
        result = project_section("python")

        assert "venv" in result or "virtualenv" in result

    def test_nodejs_project_includes_npm(self):
        result = project_section("nodejs")

        assert "npm" in result or "yarn" in result
        assert "package.json" in result

    def test_java_project_includes_maven_or_gradle(self):
        result = project_section("java")

        assert "Maven" in result or "Gradle" in result
        assert "JUnit" in result

    def test_go_project_includes_go_mod(self):
        result = project_section("go")

        assert "go.mod" in result
        assert "go test" in result

    def test_rust_project_includes_cargo(self):
        result = project_section("rust")

        assert "Cargo" in result
        assert "cargo test" in result or "cargo build" in result

    def test_unknown_project_returns_empty_string(self):
        result = project_section("unknown_language")

        assert result == ""

    def test_none_project_returns_empty_string(self):
        result = project_section(None)

        assert result == ""


class TestCodebaseStructureSection:
    """Tests for codebase_structure_section function."""

    def test_with_structure_returns_formatted_section(self):
        structure = "src/\n  main.py\n  utils.py"
        result = codebase_structure_section(structure)

        assert "Codebase Structure" in result
        assert structure in result

    def test_with_none_returns_empty_string(self):
        result = codebase_structure_section(None)

        assert result == ""

    def test_with_empty_string_returns_empty_string(self):
        result = codebase_structure_section("")

        assert result == ""


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

    def test_with_json_false_returns_empty_string(self):
        result = tool_format_section(use_json=False)

        assert result == ""

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

    def test_with_no_references_returns_empty_string(self):
        result = codebase_hint_section((), ())

        assert result == ""

    def test_starts_with_newlines_for_spacing(self):
        files = ("src/main.py",)
        result = codebase_hint_section(files, ())

        assert result.startswith("\n")
