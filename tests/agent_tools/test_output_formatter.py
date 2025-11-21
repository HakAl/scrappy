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
  # Defined in mock_rich_console fixture