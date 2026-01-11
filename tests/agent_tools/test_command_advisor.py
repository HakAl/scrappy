"""
Tests for CommandAdvisor component.

These tests verify the pre-execution advice and output enrichment
functionality of the command advisor.
"""

from scrappy.agent_tools.components.command_advisor import CommandAdvisor


class TestCommandAdvisorAnalyze:
    """Tests for CommandAdvisor.analyze_command method."""

    def test_npm_init_without_y_returns_advice(self):
        """npm init without -y flag should return advice."""
        advisor = CommandAdvisor()

        result = advisor.analyze_command("npm init")

        assert result is not None
        assert "-y" in result
        assert "skip" in result.lower()

    def test_npm_init_with_y_returns_none(self):
        """npm init with -y flag should not return advice."""
        advisor = CommandAdvisor()

        result = advisor.analyze_command("npm init -y")

        assert result is None

    def test_npm_init_with_yes_flag_returns_none(self):
        """npm init -y in longer command should not return advice."""
        advisor = CommandAdvisor()

        result = advisor.analyze_command("npm init -y my-package")

        assert result is None

    def test_npx_without_y_returns_advice(self):
        """npx without -y flag should return advice."""
        advisor = CommandAdvisor()

        result = advisor.analyze_command("npx create-react-app my-app")

        assert result is not None
        assert "-y" in result

    def test_npx_with_y_returns_none(self):
        """npx with -y flag should not return advice."""
        advisor = CommandAdvisor()

        result = advisor.analyze_command("npx -y create-react-app my-app")

        assert result is None

    def test_yarn_create_returns_advice(self):
        """yarn create should return advice about interactive prompts."""
        advisor = CommandAdvisor()

        result = advisor.analyze_command("yarn create react-app my-app")

        assert result is not None
        assert "interactive" in result.lower()

    def test_safe_command_returns_none(self):
        """Safe commands should not return advice."""
        advisor = CommandAdvisor()

        safe_commands = [
            "ls -la",
            "git status",
            "python script.py",
            "cat file.txt",
            "mkdir new-dir",
            "pip install package",
        ]

        for cmd in safe_commands:
            result = advisor.analyze_command(cmd)
            assert result is None, f"Expected None for '{cmd}', got '{result}'"

    def test_case_insensitive_matching(self):
        """Command matching should be case insensitive."""
        advisor = CommandAdvisor()

        # Mixed case npm init
        result = advisor.analyze_command("NPM INIT")
        assert result is not None

        # Mixed case npx
        result = advisor.analyze_command("NPX create-next-app")
        assert result is not None

        # Mixed case yarn create
        result = advisor.analyze_command("YARN CREATE vite")
        assert result is not None

    def test_npm_init_in_longer_command(self):
        """npm init as part of longer command should still match."""
        advisor = CommandAdvisor()

        result = advisor.analyze_command("cd project && npm init")

        assert result is not None
        assert "-y" in result


class TestCommandAdvisorEnrichOutput:
    """Tests for CommandAdvisor.enrich_output method."""

    def test_enrich_output_returns_unchanged(self):
        """enrich_output currently returns output unchanged."""
        advisor = CommandAdvisor()

        output = "Some command output\nwith multiple lines"
        command = "test command"

        result = advisor.enrich_output(output, command)

        assert result == output

    def test_enrich_output_with_empty_string(self):
        """enrich_output handles empty string."""
        advisor = CommandAdvisor()

        result = advisor.enrich_output("", "test")

        assert result == ""

    def test_enrich_output_preserves_special_characters(self):
        """enrich_output preserves special characters in output."""
        advisor = CommandAdvisor()

        output = "Error: \t\nSpecial chars: \u2603"

        result = advisor.enrich_output(output, "test")

        assert result == output


class TestCommandAdvisorInitialization:
    """Tests for CommandAdvisor initialization."""

    def test_multiple_instances_independent(self):
        """Multiple instances are independent."""
        advisor1 = CommandAdvisor()
        advisor2 = CommandAdvisor()

        # Both should work independently
        result1 = advisor1.analyze_command("npm init")
        result2 = advisor2.analyze_command("git status")

        assert result1 is not None
        assert result2 is None
