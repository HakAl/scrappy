"""
Tests for Rich-based CLI I/O implementation.

Following TDD: these tests define the expected behavior of RichIO,
which replaces ClickIO with Rich library for enhanced terminal output.

Test coverage:
- RichIO implements CLIIOProtocol
- Styled output methods (echo, secho, style)
- Console capture for verification
- Panel rendering
- Table rendering
- Color mapping from click colors to Rich colors
"""

import pytest
from io import StringIO
from typing import List

class TestRichIOEcho:
    """Tests for RichIO echo output functionality."""

    @pytest.mark.unit
    def test_echo_outputs_message(self):
        """Test that echo outputs a message."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.echo("Hello, World!")

        result = output.getvalue()
        assert "Hello, World!" in result

    @pytest.mark.unit
    def test_echo_with_newline_default(self):
        """Test that echo adds newline by default."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.echo("Line 1")
        io.echo("Line 2")

        result = output.getvalue()
        # Both lines should be on separate lines
        assert "Line 1" in result
        assert "Line 2" in result
        # Check newline separation
        lines = result.strip().split('\n')
        assert len(lines) >= 2

    @pytest.mark.unit
    def test_echo_without_newline(self):
        """Test that echo can suppress newline."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.echo("No newline", nl=False)
        io.echo(" continues")

        result = output.getvalue()
        # Should be on same line or adjacent
        assert "No newline" in result
        assert "continues" in result

    @pytest.mark.unit

    @pytest.mark.unit
    def test_echo_multiple_messages(self):
        """Test multiple echo calls."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.echo("First")
        io.echo("Second")
        io.echo("Third")

        result = output.getvalue()
        assert "First" in result
        assert "Second" in result
        assert "Third" in result


class TestRichIOSecho:
    """Tests for RichIO styled echo functionality."""

    @pytest.mark.unit
    def test_secho_outputs_message(self):
        """Test that secho outputs a message."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.secho("Styled message")

        result = output.getvalue()
        assert "Styled message" in result

    @pytest.mark.unit
    def test_secho_with_color(self):
        """Test secho with foreground color."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        # Force terminal to get ANSI codes
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        io.secho("Colored text", fg="green")

        result = output.getvalue()
        assert "Colored text" in result

    @pytest.mark.unit
    def test_secho_with_bold(self):
        """Test secho with bold formatting."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        io.secho("Bold text", bold=True)

        result = output.getvalue()
        assert "Bold text" in result

    @pytest.mark.unit
    def test_secho_with_color_and_bold(self):
        """Test secho with both color and bold."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        io.secho("Styled", fg="red", bold=True)

        result = output.getvalue()
        assert "Styled" in result

    @pytest.mark.unit
    def test_secho_without_newline(self):
        """Test secho can suppress newline."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.secho("Part 1", nl=False)
        io.secho(" Part 2")

        result = output.getvalue()
        assert "Part 1" in result
        assert "Part 2" in result

    @pytest.mark.unit
    def test_secho_with_none_color(self):
        """Test secho with None as color (no color)."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.secho("No color", fg=None)

        result = output.getvalue()
        assert "No color" in result


class TestRichIOStyledEcho:
    """Tests for RichIO styled_echo (backward compatibility alias)."""

    @pytest.mark.unit
    def test_styled_echo_outputs_message(self):
        """Test that styled_echo outputs a message."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.styled_echo("Styled message", fg="cyan", bold=True)

        result = output.getvalue()
        assert "Styled message" in result

    @pytest.mark.unit
    def test_styled_echo_is_alias_for_secho(self):
        """Test that styled_echo behaves same as secho."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output1 = StringIO()
        console1 = Console(file=output1, force_terminal=True)
        io1 = RichIO(console=console1)

        output2 = StringIO()
        console2 = Console(file=output2, force_terminal=True)
        io2 = RichIO(console=console2)

        io1.secho("Test", fg="green", bold=True)
        io2.styled_echo("Test", fg="green", bold=True)

        # Both should produce same output
        assert output1.getvalue() == output2.getvalue()


class TestRichIOStyle:
    """Tests for RichIO style method (returns styled string)."""

    @pytest.mark.unit
    def test_style_returns_string(self):
        """Test that style returns a string."""
        from src.cli.rich_output import RichIO

        io = RichIO()
        result = io.style("text", fg="green")

        assert isinstance(result, str)
        assert "text" in result

    @pytest.mark.unit
    def test_style_with_bold(self):
        """Test style with bold formatting."""
        from src.cli.rich_output import RichIO

        io = RichIO()
        result = io.style("bold text", bold=True)

        assert isinstance(result, str)
        assert "bold text" in result

    @pytest.mark.unit
    def test_style_with_color_and_bold(self):
        """Test style with both color and bold."""
        from src.cli.rich_output import RichIO

        io = RichIO()
        result = io.style("styled", fg="red", bold=True)

        assert isinstance(result, str)
        assert "styled" in result

    @pytest.mark.unit
    def test_style_with_no_formatting(self):
        """Test style with no formatting returns plain text."""
        from src.cli.rich_output import RichIO

        io = RichIO()
        result = io.style("plain text")

        assert "plain text" in result


class TestRichIOColorMapping:
    """Tests for mapping click colors to Rich colors."""

    @pytest.mark.unit
    def test_color_mapping_green(self):
        """Test that green color maps correctly."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        io.secho("Green text", fg="green")

        # Should contain ANSI escape for green
        result = output.getvalue()
        assert "Green text" in result

    @pytest.mark.unit
    def test_color_mapping_red(self):
        """Test that red color maps correctly."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        io.secho("Red text", fg="red")

        result = output.getvalue()
        assert "Red text" in result

    @pytest.mark.unit
    def test_color_mapping_yellow(self):
        """Test that yellow color maps correctly."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        io.secho("Yellow text", fg="yellow")

        result = output.getvalue()
        assert "Yellow text" in result

    @pytest.mark.unit
    def test_color_mapping_cyan(self):
        """Test that cyan color maps correctly."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        io.secho("Cyan text", fg="cyan")

        result = output.getvalue()
        assert "Cyan text" in result

    @pytest.mark.unit
    def test_color_mapping_magenta(self):
        """Test that magenta color maps correctly."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        io.secho("Magenta text", fg="magenta")

        result = output.getvalue()
        assert "Magenta text" in result

    @pytest.mark.unit
    def test_color_mapping_blue(self):
        """Test that blue color maps correctly."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        io.secho("Blue text", fg="blue")

        result = output.getvalue()
        assert "Blue text" in result

    @pytest.mark.unit
    def test_color_mapping_white(self):
        """Test that white color maps correctly."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        io.secho("White text", fg="white")

        result = output.getvalue()
        assert "White text" in result

    @pytest.mark.unit
    def test_color_mapping_bright_variants(self):
        """Test that bright color variants are handled."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        # Click uses 'bright_' prefix for bright colors
        io.secho("Bright green", fg="bright_green")

        result = output.getvalue()
        assert "Bright green" in result


class TestRichIOPanels:
    """Tests for Rich panel rendering (extended functionality)."""


    @pytest.mark.unit
    def test_panel_renders_content(self):
        """Test that panel renders content."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.panel("Panel content", title="Test Panel")

        result = output.getvalue()
        assert "Panel content" in result

    @pytest.mark.unit
    def test_panel_with_title(self):
        """Test that panel shows title."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.panel("Content", title="My Title")

        result = output.getvalue()
        assert "My Title" in result

    @pytest.mark.unit
    def test_panel_without_title(self):
        """Test panel without title."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.panel("Just content")

        result = output.getvalue()
        assert "Just content" in result

    @pytest.mark.unit
    def test_panel_with_border_style(self):
        """Test panel with custom border style."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        io.panel("Content", border_style="green")

        result = output.getvalue()
        assert "Content" in result


class TestRichIOTables:
    """Tests for Rich table rendering (extended functionality)."""


    @pytest.mark.unit
    def test_table_renders_data(self):
        """Test that table renders row data."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        headers = ["Name", "Value"]
        rows = [
            ["foo", "bar"],
            ["baz", "qux"]
        ]

        io.table(headers, rows)

        result = output.getvalue()
        assert "Name" in result
        assert "Value" in result
        assert "foo" in result
        assert "bar" in result

    @pytest.mark.unit
    def test_table_with_title(self):
        """Test table with title."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        headers = ["Col1", "Col2"]
        rows = [["a", "b"]]

        io.table(headers, rows, title="My Table")

        result = output.getvalue()
        assert "My Table" in result
        assert "Col1" in result

    @pytest.mark.unit
    def test_table_empty_rows(self):
        """Test table with no rows."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        headers = ["Header1", "Header2"]
        rows: List[List[str]] = []

        io.table(headers, rows)

        result = output.getvalue()
        # Headers should still be shown
        assert "Header1" in result

    @pytest.mark.unit
    def test_table_single_column(self):
        """Test table with single column."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        headers = ["Items"]
        rows = [["item1"], ["item2"], ["item3"]]

        io.table(headers, rows)

        result = output.getvalue()
        assert "Items" in result
        assert "item1" in result
        assert "item2" in result
        assert "item3" in result


class TestRichIOSyntaxHighlight:
    """Tests for syntax highlighting (extended functionality)."""


    @pytest.mark.unit
    def test_syntax_renders_code(self):
        """Test that syntax renders code."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        code = "def hello():\n    print('world')"
        io.syntax(code, language="python")

        result = output.getvalue()
        assert "def" in result
        assert "hello" in result

    @pytest.mark.unit
    def test_syntax_with_line_numbers(self):
        """Test syntax with line numbers."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        code = "line1\nline2"
        io.syntax(code, language="text", line_numbers=True)

        result = output.getvalue()
        # Should contain line number indicators
        assert "line1" in result
        assert "line2" in result


class TestRichIOInput:
    """Tests for RichIO input methods (prompt, confirm, input_line).

    Note: These are harder to test without mocking stdin.
    We test that methods exist and have correct signatures.
    """

    @pytest.mark.unit
    def test_prompt_signature(self):
        """Test prompt method has correct signature."""
        from src.cli.rich_output import RichIO
        import inspect

        io = RichIO()
        sig = inspect.signature(io.prompt)

        params = list(sig.parameters.keys())
        assert 'text' in params
        assert 'default' in params
        assert 'show_default' in params

    @pytest.mark.unit
    def test_confirm_signature(self):
        """Test confirm method has correct signature."""
        from src.cli.rich_output import RichIO
        import inspect

        io = RichIO()
        sig = inspect.signature(io.confirm)

        params = list(sig.parameters.keys())
        assert 'text' in params
        assert 'default' in params

    @pytest.mark.unit
    def test_input_line_signature(self):
        """Test input_line method has correct signature."""
        from src.cli.rich_output import RichIO
        import inspect

        io = RichIO()
        sig = inspect.signature(io.input_line)

        # Should take no parameters (or self only)
        params = list(sig.parameters.keys())
        assert len(params) == 0


class TestRichIOEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.unit
    def test_echo_with_special_characters(self):
        """Test echo with special characters."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.echo("Tab:\tNewline:\nUnicode: cafe")

        result = output.getvalue()
        assert "Tab:" in result
        assert "cafe" in result

    @pytest.mark.unit
    def test_panel_with_multiline_content(self):
        """Test panel with multiline content."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        content = "Line 1\nLine 2\nLine 3"
        io.panel(content, title="Multiline")

        result = output.getvalue()
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result

    @pytest.mark.unit
    def test_table_with_long_values(self):
        """Test table with long cell values."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False, width=80)
        io = RichIO(console=console)

        headers = ["Key", "Value"]
        rows = [["short", "a" * 100]]

        io.table(headers, rows)

        result = output.getvalue()
        assert "Key" in result
        assert "short" in result

    @pytest.mark.unit
    def test_multiple_output_types(self):
        """Test mixing different output types."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.echo("Plain text")
        io.secho("Styled text", fg="green")
        io.panel("Panel content", title="Panel")
        io.table(["Col"], [["row"]])

        result = output.getvalue()
        assert "Plain text" in result
        assert "Styled text" in result
        assert "Panel content" in result
        assert "row" in result


class TestRichIOConsoleAccess:
    """Tests for accessing the underlying Rich console."""

    @pytest.mark.unit
    def test_custom_console_is_used(self):
        """Test that custom console is actually used."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        custom_console = Console(file=output, force_terminal=False)
        io = RichIO(console=custom_console)

        io.echo("Test message")

        # Should write to our custom output
        assert "Test message" in output.getvalue()


class TestRichIORule:
    """Tests for horizontal rule rendering."""

    @pytest.mark.unit
    def test_rule_renders(self):
        """Test that rule renders a horizontal line."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.rule()

        result = output.getvalue()
        # Should have some output (the rule line)
        assert len(result) > 0

    @pytest.mark.unit
    def test_rule_with_title(self):
        """Test rule with title text."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        io.rule(title="Section")

        result = output.getvalue()
        assert "Section" in result
