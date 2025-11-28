import pytest
from unittest.mock import Mock, MagicMock, patch, call
from src.agent_tools.formatters.output_formatter import (
    NullFormatter,
    GitOutputFormatter,
    RichDirectoryFormatter,
    HAS_RICH
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_output_interface():
    """
    Mocks the output interface (like Click or a custom styler).
    Instead of actual coloring, it wraps text in tags for easy assertion.
    e.g. style("foo", color="red") -> "[red]foo[/red]"
    """
    mock = Mock()

    def fake_style(text, color=None, bold=False):
        tag = f"{color}"
        if bold:
            tag += "+bold"
        return f"[{tag}]{text}[/{tag}]"

    mock.style.side_effect = fake_style
    return mock


@pytest.fixture
def mock_rich_console():
    """Mocks the Rich Console and its capture context manager."""
    mock_console = MagicMock()
    # Setup the capture context manager
    mock_capture = MagicMock()
    mock_capture.get.return_value = "Rendered Output"

    # When console.capture() is called, return the mock context
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_capture
    mock_console.capture.return_value = mock_context

    return mock_console


# -----------------------------------------------------------------------------
# NullFormatter Tests
# -----------------------------------------------------------------------------

def test_null_formatter_returns_unchanged():
    formatter = NullFormatter()
    data = "Some\nRandom\nText"
    assert formatter.format(data) == data
    assert formatter.format(data, output_type="diff") == data


# -----------------------------------------------------------------------------
# GitOutputFormatter Tests
# -----------------------------------------------------------------------------

class TestGitOutputFormatter:

    def test_init_without_interface(self):
        """If no interface provided, returns raw output."""
        formatter = GitOutputFormatter(output_interface=None)
        raw = "commit 12345"
        assert formatter.format(raw, "log") == raw

    def test_log_formatting(self, mock_output_interface):
        formatter = GitOutputFormatter(output_interface=mock_output_interface)

        # A standard one-line git log
        input_line = "a1b2c3d Initial commit"
        result = formatter.format(input_line, "log")

        # Expect the hash to be yellow
        assert "[yellow]a1b2c3d[/yellow] Initial commit" in result

    # def test_log_formatting_ignores_non_hashes(self, mock_output_interface):
    #     formatter = GitOutputFormatter(output_interface=mock_output_interface)
    #     input_line = "    indentation without hash"
    #     result = formatter.format(input_line, "log")
    #     assert result == input_line

    def test_diff_formatting(self, mock_output_interface):
        formatter = GitOutputFormatter(output_interface=mock_output_interface)

        diff_output = """diff --git a/test.py b/test.py
+++ b/test.py
--- a/test.py
@@ -1,1 +1,1 @@
+added line
-removed line"""

        result = formatter.format(diff_output, "diff")

        # Verify specific color mappings
        assert "[bright_white+bold]diff --git" in result
        assert "[cyan+bold]+++ b/test.py" in result
        assert "[cyan+bold]--- a/test.py" in result
        assert "[cyan]@@" in result
        assert "[green]+added line" in result
        assert "[red]-removed line" in result

    def test_blame_formatting(self, mock_output_interface):
        formatter = GitOutputFormatter(output_interface=mock_output_interface)

        # Blame line usually starts with hash or ^hash
        lines = [
            "a1b2c3d4 (Author 2023-01-01) code",
            "^x9y8z76 (Author 2023-01-01) init"
        ]

        result = formatter.format("\n".join(lines), "blame")

        assert "[yellow]a1b2c3d4[/yellow]" in result
        assert "[yellow]^x9y8z76[/yellow]" in result

    def test_show_formatting(self, mock_output_interface):
        formatter = GitOutputFormatter(output_interface=mock_output_interface)

        show_output = """commit a1b2c3d
Author: John Doe
Date:   Mon Jan 1
Message: My Commit
+New Line"""

        result = formatter.format(show_output, "show")

        assert "[yellow+bold]commit a1b2c3d" in result
        assert "[cyan]Author:" in result
        assert "[cyan]Date:" in result
        assert "[bright_white+bold]Message:" in result
        assert "[green]+New Line" in result

    def test_unknown_output_type(self, mock_output_interface):
        """Falls back to raw line if type is unknown."""
        formatter = GitOutputFormatter(output_interface=mock_output_interface)
        line = "+++ line"
        # If type is 'unknown', it shouldn't colorize the '+++'
        assert formatter.format(line, "unknown") == line


# -----------------------------------------------------------------------------
# RichDirectoryFormatter Tests
# -----------------------------------------------------------------------------

class TestRichDirectoryFormatter:

    def test_init_raises_without_rich(self):
        """Verify ImportError is raised if HAS_RICH is False."""
        with patch('src.agent_tools.formatters.output_formatter.HAS_RICH', False):
            with pytest.raises(ImportError) as exc:
                RichDirectoryFormatter()
            assert "Rich library is required" in str(exc.value)

    def test_init_creates_default_console(self):
        """Verify a default console is created if none provided."""
        # Patch Console so we don't actually create a real system console
        with patch('src.agent_tools.formatters.output_formatter.Console') as MockConsole:
            # Ensure HAS_RICH is True for this test
            with patch('src.agent_tools.formatters.output_formatter.HAS_RICH', True):
                formatter = RichDirectoryFormatter()
                assert formatter._console is not None
                MockConsole.assert_called_once()


    # @pytest.mark.parametrize("ext,expected_style", [
    #     (".py", "green"),
    #     (".js", "yellow"),
    #     (".ts", "yellow"),
    #     (".md", "white"),
    #     (".txt", "white"),
    #     (".json", "magenta"),
    #     (".yml", "magenta"),
    #     (".unknown", None)  # No style arg passed implies default or inheritance
    # ])
    # def test_format_file_name_extensions(self, mock_rich_console, ext, expected_style):
    #     """Test color mapping for different file extensions."""
    #     with patch('src.agent_tools.formatters.output_formatter.HAS_RICH', True):
    #         formatter = RichDirectoryFormatter(console=mock_rich_console)
    #
    #         with patch('src.agent_tools.formatters.output_formatter.Text') as MockText:
    #             filename = f"test{ext}"
    #             formatter.format_file_name(filename, ext)
    #
    #             # Extract call args
    #             args, kwargs = MockText.call_args
    #             assert args[0] == filename
    #
    #             if expected_style:
    #                 assert kwargs['style'] == expected_style

# todo

    def test_format_tree_line_passthrough(self, mock_rich_console):
        """Test that tree structural lines are passed through."""
        with patch('src.agent_tools.formatters.output_formatter.HAS_RICH', True):
            formatter = RichDirectoryFormatter(console=mock_rich_console)
            line = "|-- "
            assert formatter.format_tree_line(line) == line


# -----------------------------------------------------------------------------
# Theme Integration Tests (GIT_COLORS and SYNTAX_COLORS)
# -----------------------------------------------------------------------------

from src.infrastructure.theme import GIT_COLORS, SYNTAX_COLORS


class TestGitOutputFormatterThemeColors:
    """Tests verifying GitOutputFormatter uses GIT_COLORS."""

    def test_log_uses_git_colors_commit(self, mock_output_interface):
        """Log formatting uses GIT_COLORS.commit for hashes."""
        formatter = GitOutputFormatter(output_interface=mock_output_interface)
        input_line = "a1b2c3d Initial commit"
        result = formatter.format(input_line, "log")

        # GIT_COLORS.commit is "yellow"
        assert f"[{GIT_COLORS.commit}]a1b2c3d[/{GIT_COLORS.commit}]" in result

    def test_diff_uses_git_colors_add(self, mock_output_interface):
        """Diff formatting uses GIT_COLORS.add for added lines."""
        formatter = GitOutputFormatter(output_interface=mock_output_interface)
        result = formatter.format("+added line", "diff")

        assert f"[{GIT_COLORS.add}]+added line[/{GIT_COLORS.add}]" in result

    def test_diff_uses_git_colors_remove(self, mock_output_interface):
        """Diff formatting uses GIT_COLORS.remove for removed lines."""
        formatter = GitOutputFormatter(output_interface=mock_output_interface)
        result = formatter.format("-removed line", "diff")

        assert f"[{GIT_COLORS.remove}]-removed line[/{GIT_COLORS.remove}]" in result

    def test_diff_uses_git_colors_header(self, mock_output_interface):
        """Diff formatting uses GIT_COLORS.header for file headers."""
        formatter = GitOutputFormatter(output_interface=mock_output_interface)

        # Test +++ header
        result1 = formatter.format("+++ b/test.py", "diff")
        assert f"[{GIT_COLORS.header}+bold]+++ b/test.py[/{GIT_COLORS.header}+bold]" in result1

        # Test --- header
        result2 = formatter.format("--- a/test.py", "diff")
        assert f"[{GIT_COLORS.header}+bold]--- a/test.py[/{GIT_COLORS.header}+bold]" in result2

        # Test @@ chunk header
        result3 = formatter.format("@@ -1,1 +1,1 @@", "diff")
        assert f"[{GIT_COLORS.header}]@@" in result3

    def test_diff_uses_git_colors_meta(self, mock_output_interface):
        """Diff formatting uses GIT_COLORS.meta for diff --git line."""
        formatter = GitOutputFormatter(output_interface=mock_output_interface)
        result = formatter.format("diff --git a/test.py b/test.py", "diff")

        assert f"[{GIT_COLORS.meta}+bold]diff --git" in result

    def test_blame_uses_git_colors_commit(self, mock_output_interface):
        """Blame formatting uses GIT_COLORS.commit for hashes."""
        formatter = GitOutputFormatter(output_interface=mock_output_interface)
        result = formatter.format("a1b2c3d4 (Author 2023-01-01) code", "blame")

        assert f"[{GIT_COLORS.commit}]a1b2c3d4[/{GIT_COLORS.commit}]" in result

    def test_show_uses_git_colors_commit(self, mock_output_interface):
        """Show formatting uses GIT_COLORS.commit for commit line."""
        formatter = GitOutputFormatter(output_interface=mock_output_interface)
        result = formatter.format("commit a1b2c3d", "show")

        assert f"[{GIT_COLORS.commit}+bold]commit a1b2c3d[/{GIT_COLORS.commit}+bold]" in result

    def test_show_uses_git_colors_header_for_author(self, mock_output_interface):
        """Show formatting uses GIT_COLORS.header for author/date."""
        formatter = GitOutputFormatter(output_interface=mock_output_interface)

        result1 = formatter.format("Author: John Doe", "show")
        assert f"[{GIT_COLORS.header}]Author:" in result1

        result2 = formatter.format("Date:   Mon Jan 1", "show")
        assert f"[{GIT_COLORS.header}]Date:" in result2

    def test_show_uses_git_colors_meta_for_message(self, mock_output_interface):
        """Show formatting uses GIT_COLORS.meta for message header."""
        formatter = GitOutputFormatter(output_interface=mock_output_interface)
        result = formatter.format("Message: My Commit", "show")

        assert f"[{GIT_COLORS.meta}+bold]Message:" in result

    def test_show_uses_git_colors_add_remove(self, mock_output_interface):
        """Show formatting uses GIT_COLORS for +/- lines."""
        formatter = GitOutputFormatter(output_interface=mock_output_interface)

        result1 = formatter.format("+New Line", "show")
        assert f"[{GIT_COLORS.add}]+New Line[/{GIT_COLORS.add}]" in result1

        result2 = formatter.format("-Old Line", "show")
        assert f"[{GIT_COLORS.remove}]-Old Line[/{GIT_COLORS.remove}]" in result2


class TestRichDirectoryFormatterSyntaxColors:
    """Tests verifying RichDirectoryFormatter uses SYNTAX_COLORS."""

    @pytest.mark.skipif(not HAS_RICH, reason="Rich not installed")
    def test_format_file_name_uses_syntax_colors_python(self, mock_rich_console):
        """Python files use SYNTAX_COLORS.python."""
        with patch('src.agent_tools.formatters.output_formatter.HAS_RICH', True):
            with patch('src.agent_tools.formatters.output_formatter.Text') as MockText:
                formatter = RichDirectoryFormatter(console=mock_rich_console)
                formatter.format_file_name("test.py", ".py")

                args, kwargs = MockText.call_args
                assert kwargs.get('style') == SYNTAX_COLORS.python

    @pytest.mark.skipif(not HAS_RICH, reason="Rich not installed")
    def test_format_file_name_uses_syntax_colors_javascript(self, mock_rich_console):
        """JavaScript/TypeScript files use SYNTAX_COLORS.javascript."""
        with patch('src.agent_tools.formatters.output_formatter.HAS_RICH', True):
            with patch('src.agent_tools.formatters.output_formatter.Text') as MockText:
                formatter = RichDirectoryFormatter(console=mock_rich_console)

                for ext in ['.js', '.ts', '.jsx', '.tsx']:
                    MockText.reset_mock()
                    formatter.format_file_name(f"test{ext}", ext)
                    args, kwargs = MockText.call_args
                    assert kwargs.get('style') == SYNTAX_COLORS.javascript, f"Failed for {ext}"

    @pytest.mark.skipif(not HAS_RICH, reason="Rich not installed")
    def test_format_file_name_uses_syntax_colors_docs(self, mock_rich_console):
        """Documentation files use SYNTAX_COLORS.docs."""
        with patch('src.agent_tools.formatters.output_formatter.HAS_RICH', True):
            with patch('src.agent_tools.formatters.output_formatter.Text') as MockText:
                formatter = RichDirectoryFormatter(console=mock_rich_console)

                for ext in ['.md', '.txt', '.rst']:
                    MockText.reset_mock()
                    formatter.format_file_name(f"test{ext}", ext)
                    args, kwargs = MockText.call_args
                    assert kwargs.get('style') == SYNTAX_COLORS.docs, f"Failed for {ext}"

    @pytest.mark.skipif(not HAS_RICH, reason="Rich not installed")
    def test_format_file_name_uses_syntax_colors_config(self, mock_rich_console):
        """Config files use SYNTAX_COLORS.config."""
        with patch('src.agent_tools.formatters.output_formatter.HAS_RICH', True):
            with patch('src.agent_tools.formatters.output_formatter.Text') as MockText:
                formatter = RichDirectoryFormatter(console=mock_rich_console)

                for ext in ['.json', '.yaml', '.yml', '.toml']:
                    MockText.reset_mock()
                    formatter.format_file_name(f"test{ext}", ext)
                    args, kwargs = MockText.call_args
                    assert kwargs.get('style') == SYNTAX_COLORS.config, f"Failed for {ext}"

    @pytest.mark.skipif(not HAS_RICH, reason="Rich not installed")
    def test_format_file_name_returns_unformatted_for_unknown(self, mock_rich_console):
        """Unknown extensions return plain filename without formatting."""
        with patch('src.agent_tools.formatters.output_formatter.HAS_RICH', True):
            formatter = RichDirectoryFormatter(console=mock_rich_console)
            result = formatter.format_file_name("test.xyz", ".xyz")
            assert result == "test.xyz"


class TestGitColorsValues:
    """Tests verifying GIT_COLORS has expected default values."""

    def test_git_colors_add_is_green(self):
        """GIT_COLORS.add should be green."""
        assert GIT_COLORS.add == "green"

    def test_git_colors_remove_is_red(self):
        """GIT_COLORS.remove should be red."""
        assert GIT_COLORS.remove == "red"

    def test_git_colors_header_is_cyan(self):
        """GIT_COLORS.header should be cyan."""
        assert GIT_COLORS.header == "cyan"

    def test_git_colors_commit_is_yellow(self):
        """GIT_COLORS.commit should be yellow."""
        assert GIT_COLORS.commit == "yellow"

    def test_git_colors_meta_is_bright_white(self):
        """GIT_COLORS.meta should be bright_white."""
        assert GIT_COLORS.meta == "bright_white"


class TestSyntaxColorsValues:
    """Tests verifying SYNTAX_COLORS has expected default values."""

    def test_syntax_colors_python_is_green(self):
        """SYNTAX_COLORS.python should be green."""
        assert SYNTAX_COLORS.python == "green"

    def test_syntax_colors_javascript_is_yellow(self):
        """SYNTAX_COLORS.javascript should be yellow."""
        assert SYNTAX_COLORS.javascript == "yellow"

    def test_syntax_colors_config_is_magenta(self):
        """SYNTAX_COLORS.config should be magenta."""
        assert SYNTAX_COLORS.config == "magenta"

    def test_syntax_colors_docs_is_white(self):
        """SYNTAX_COLORS.docs should be white."""
        assert SYNTAX_COLORS.docs == "white"

    def test_syntax_colors_default_is_white(self):
        """SYNTAX_COLORS.default should be white."""
        assert SYNTAX_COLORS.default == "white"