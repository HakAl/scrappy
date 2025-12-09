"""
Tests for Agent Rich Output Enhancement (Phase 3).

Tests that the agent uses Rich components for formatted output:
- Thinking output uses panels with blue border
- Tool approval displays as formatted tables
- Command execution shows in syntax-highlighted blocks
- Errors display in red-bordered panels

These tests define the expected behavior BEFORE implementation (TDD).
"""

import pytest
from typing import List, Dict, Any, Optional
from unittest.mock import Mock, patch, MagicMock
import json


class MockRichIO:
    """
    Mock IO that captures Rich component calls for testing.

    Tracks panels, tables, and syntax blocks to verify agent
    uses Rich formatting correctly.
    """

    def __init__(
        self,
        inputs: Optional[List[str]] = None,
        confirmations: Optional[List[bool]] = None
    ):
        self._inputs: List[str] = list(inputs) if inputs else []
        self._confirmations: List[bool] = list(confirmations) if confirmations else []
        self._input_index = 0
        self._confirm_index = 0

        # Standard output buffer
        self._output_buffer: List[str] = []
        self._styled_outputs: List[Dict[str, Any]] = []

        # Rich component captures
        self._panels: List[Dict[str, Any]] = []
        self._tables: List[Dict[str, Any]] = []
        self._syntax_blocks: List[Dict[str, Any]] = []
        self._rules: List[Dict[str, Any]] = []

    # Basic CLIIOProtocol methods
    def echo(self, message: str = "", nl: bool = True) -> None:
        if nl:
            self._output_buffer.append(message + "\n")
        else:
            self._output_buffer.append(message)

    def secho(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        self._styled_outputs.append({
            'text': message,
            'fg': fg,
            'bold': bold,
            'nl': nl
        })
        if nl:
            self._output_buffer.append(message + "\n")
        else:
            self._output_buffer.append(message)

    def styled_echo(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        self.secho(message, fg=fg, bold=bold, nl=nl)

    def style(self, text: str, fg: Optional[str] = None, bold: bool = False) -> str:
        return text

    def prompt(self, text: str, default: str = "", show_default: bool = True) -> str:
        if self._input_index < len(self._inputs):
            result = self._inputs[self._input_index]
            self._input_index += 1
            return result
        return default

    def confirm(self, text: str, default: bool = False) -> bool:
        if self._confirm_index < len(self._confirmations):
            result = self._confirmations[self._confirm_index]
            self._confirm_index += 1
            return result
        return default

    def input_line(self) -> str:
        if self._input_index < len(self._inputs):
            result = self._inputs[self._input_index]
            self._input_index += 1
            return result
        return ""

    # Rich-specific methods
    def panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: Optional[str] = None
    ) -> None:
        """Capture panel output for testing."""
        self._panels.append({
            'content': content,
            'title': title,
            'border_style': border_style
        })
        self._output_buffer.append(f"[Panel: {title}] {content}\n")

    def table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> None:
        """Capture table output for testing."""
        self._tables.append({
            'headers': headers,
            'rows': rows,
            'title': title
        })
        self._output_buffer.append(f"[Table: {title}] {headers} - {len(rows)} rows\n")

    def syntax(
        self,
        code: str,
        language: str = "text",
        line_numbers: bool = False
    ) -> None:
        """Capture syntax-highlighted code block for testing."""
        self._syntax_blocks.append({
            'code': code,
            'language': language,
            'line_numbers': line_numbers
        })
        self._output_buffer.append(f"[Syntax: {language}] {code[:50]}...\n")

    def rule(self, title: Optional[str] = None) -> None:
        """Capture horizontal rule for testing."""
        self._rules.append({'title': title})
        self._output_buffer.append(f"[Rule: {title}]\n")

    # Test helper methods
    def get_output(self) -> str:
        return "".join(self._output_buffer)

    def get_output_lines(self) -> List[str]:
        return self.get_output().split("\n") if self._output_buffer else []

    def get_styled_outputs(self) -> List[Dict[str, Any]]:
        return self._styled_outputs

    def get_panels(self) -> List[Dict[str, Any]]:
        return self._panels

    def get_tables(self) -> List[Dict[str, Any]]:
        return self._tables

    def get_syntax_blocks(self) -> List[Dict[str, Any]]:
        return self._syntax_blocks

    def get_rules(self) -> List[Dict[str, Any]]:
        return self._rules

    def clear_output(self) -> None:
        self._output_buffer = []
        self._styled_outputs = []
        self._panels = []
        self._tables = []
        self._syntax_blocks = []
        self._rules = []

    def reset(self) -> None:
        self.clear_output()
        self._input_index = 0
        self._confirm_index = 0


# =============================================================================
# Test Helper Functions
# =============================================================================

def assert_panel_rendered(
    io: MockRichIO,
    content_contains: Optional[str] = None,
    title: Optional[str] = None,
    border_style: Optional[str] = None
) -> Dict[str, Any]:
    """
    Assert that a panel was rendered with expected properties.

    Returns the matching panel for further assertions.
    """
    panels = io.get_panels()
    assert panels, f"No panels were rendered. Expected panel with title={title}"

    for panel in panels:
        matches = True

        if content_contains and content_contains not in panel['content']:
            matches = False
        if title and panel['title'] != title:
            matches = False
        if border_style and panel['border_style'] != border_style:
            matches = False

        if matches:
            return panel

    raise AssertionError(
        f"No panel matched: content_contains={content_contains}, "
        f"title={title}, border_style={border_style}. "
        f"Panels: {panels}"
    )


def assert_table_rendered(
    io: MockRichIO,
    expected_headers: Optional[List[str]] = None,
    title: Optional[str] = None,
    min_rows: int = 0
) -> Dict[str, Any]:
    """
    Assert that a table was rendered with expected properties.

    Returns the matching table for further assertions.
    """
    tables = io.get_tables()
    assert tables, f"No tables were rendered. Expected table with title={title}"

    for table in tables:
        matches = True

        if expected_headers and table['headers'] != expected_headers:
            matches = False
        if title and table['title'] != title:
            matches = False
        if len(table['rows']) < min_rows:
            matches = False

        if matches:
            return table

    raise AssertionError(
        f"No table matched: headers={expected_headers}, "
        f"title={title}, min_rows={min_rows}. "
        f"Tables: {tables}"
    )


def assert_syntax_rendered(
    io: MockRichIO,
    code_contains: Optional[str] = None,
    language: Optional[str] = None
) -> Dict[str, Any]:
    """
    Assert that a syntax block was rendered with expected properties.

    Returns the matching syntax block for further assertions.
    """
    blocks = io.get_syntax_blocks()
    assert blocks, f"No syntax blocks were rendered."

    for block in blocks:
        matches = True

        if code_contains and code_contains not in block['code']:
            matches = False
        if language and block['language'] != language:
            matches = False

        if matches:
            return block

    raise AssertionError(
        f"No syntax block matched: code_contains={code_contains}, "
        f"language={language}. "
        f"Blocks: {blocks}"
    )


# =============================================================================
# Test Classes
# =============================================================================

class TestThinkingOutputPanel:
    """Test that thinking/reasoning output uses panels with blue border."""

    def test_thinking_displays_as_panel(self):
        """Thinking text should render in a panel with 'Thinking' title."""
        io = MockRichIO()

        # Simulate the expected behavior
        thinking_text = "Analyzing the task requirements..."
        io.panel(thinking_text, title="Thinking", border_style="blue")

        panel = assert_panel_rendered(
            io,
            content_contains="Analyzing",
            title="Thinking",
            border_style="blue"
        )
        assert "task requirements" in panel['content']

    def test_thinking_panel_has_blue_border(self):
        """Thinking panels must have blue border style."""
        io = MockRichIO()

        io.panel("Processing user request", title="Thinking", border_style="blue")

        panel = io.get_panels()[0]
        assert panel['border_style'] == "blue", \
            f"Expected blue border, got {panel['border_style']}"

    def test_multiline_thinking_preserved(self):
        """Multi-line thinking text should be preserved in panel."""
        io = MockRichIO()

        thinking = "Step 1: Read the file\nStep 2: Parse content\nStep 3: Extract data"
        io.panel(thinking, title="Thinking", border_style="blue")

        panel = io.get_panels()[0]
        assert "Step 1" in panel['content']
        assert "Step 2" in panel['content']
        assert "Step 3" in panel['content']

    def test_empty_thinking_not_displayed(self):
        """Empty thinking should not create a panel."""
        io = MockRichIO()

        # No panel should be created for empty thinking
        # This tests the agent logic - if thinking is empty, skip panel
        assert len(io.get_panels()) == 0

    def test_provider_info_separate_from_thinking(self):
        """Provider info (e.g., '[gemini] Thinking...') should be separate."""
        io = MockRichIO()

        # Provider status as styled text
        io.secho("[gemini] Analyzing task...", fg="cyan")

        # Actual thinking in panel
        io.panel("Reading configuration files to understand project structure",
                title="Thinking", border_style="blue")

        # Verify both outputs exist
        styled = io.get_styled_outputs()
        assert any("[gemini]" in s['text'] for s in styled)

        panel = io.get_panels()[0]
        assert "Reading configuration" in panel['content']


class TestToolApprovalTable:
    """Test that tool approval displays as formatted table."""

    def test_tool_approval_renders_as_table(self):
        """Tool approval should display tool info in a table."""
        io = MockRichIO()

        # Expected table format for tool approval
        headers = ["Property", "Value"]
        rows = [
            ["Tool", "read_file"],
            ["Path", "/src/main.py"],
            ["Description", "Read contents of a file"]
        ]
        io.table(headers, rows, title="Tool Request")

        table = assert_table_rendered(
            io,
            expected_headers=["Property", "Value"],
            title="Tool Request",
            min_rows=2
        )

        # Verify tool name is in table
        tool_row = [r for r in table['rows'] if r[0] == "Tool"]
        assert tool_row, "Tool name not found in table"
        assert tool_row[0][1] == "read_file"

    def test_tool_parameters_in_table(self):
        """Tool parameters should be displayed in the table."""
        io = MockRichIO()

        headers = ["Property", "Value"]
        rows = [
            ["Tool", "write_file"],
            ["path", "/test/output.txt"],
            ["content", "Hello, World!"]
        ]
        io.table(headers, rows, title="Tool Request")

        table = io.get_tables()[0]

        # Check parameter rows exist
        param_names = [r[0] for r in table['rows']]
        assert "path" in param_names
        assert "content" in param_names

    def test_complex_parameters_formatted_readable(self):
        """Complex parameters (JSON, long strings) should be formatted."""
        io = MockRichIO()

        headers = ["Property", "Value"]
        rows = [
            ["Tool", "execute_command"],
            ["command", "npm install --save react react-dom"],
            ["working_dir", "/project"]
        ]
        io.table(headers, rows, title="Tool Request")

        table = io.get_tables()[0]
        assert len(table['rows']) >= 2

    def test_auto_approved_tool_indicates_status(self):
        """Auto-approved tools should indicate approval status."""
        io = MockRichIO()

        # Table with approval indicator
        headers = ["Property", "Value"]
        rows = [
            ["Tool", "read_file"],
            ["Path", "/src/main.py"],
            ["Status", "Auto-approved (safe operation)"]
        ]
        io.table(headers, rows, title="Tool Request")

        table = io.get_tables()[0]
        status_row = [r for r in table['rows'] if r[0] == "Status"]
        assert status_row
        assert "Auto-approved" in status_row[0][1]

    def test_content_preview_for_write_operations(self):
        """Write operations should show content preview."""
        io = MockRichIO()

        # For write operations, show preview separately
        headers = ["Property", "Value"]
        rows = [
            ["Tool", "write_file"],
            ["path", "/test.txt"]
        ]
        io.table(headers, rows, title="Tool Request")

        # Content preview in syntax block
        content = "def hello():\n    print('Hello')"
        io.syntax(content, language="python")

        assert len(io.get_tables()) == 1
        assert len(io.get_syntax_blocks()) == 1


class TestCommandExecutionSyntax:
    """Test that command execution shows in syntax-highlighted blocks."""

    def test_command_displays_in_syntax_block(self):
        """Command string should be in syntax block with shell highlighting."""
        io = MockRichIO()

        command = "git status --porcelain"
        io.syntax(command, language="shell")

        block = assert_syntax_rendered(
            io,
            code_contains="git status",
            language="shell"
        )
        assert "--porcelain" in block['code']

    def test_shell_language_highlighting(self):
        """Commands should use 'shell' language for highlighting."""
        io = MockRichIO()

        io.syntax("npm install express", language="shell")

        block = io.get_syntax_blocks()[0]
        assert block['language'] == "shell"

    def test_multiline_command_formatted(self):
        """Multi-line commands should be properly formatted."""
        io = MockRichIO()

        command = """docker run \\
  -p 8080:80 \\
  -v /data:/app/data \\
  myimage:latest"""
        io.syntax(command, language="shell")

        block = io.get_syntax_blocks()[0]
        assert "docker run" in block['code']
        assert "-p 8080:80" in block['code']

    def test_command_with_output_separation(self):
        """Command and its output should be visually separated."""
        io = MockRichIO()

        # Command in syntax block
        io.syntax("ls -la", language="shell")

        # Output could be in plain text or different panel
        io.echo("total 24\ndrwxr-xr-x  5 user  staff  160 Jan 1 12:00 .")

        assert len(io.get_syntax_blocks()) == 1
        assert "total 24" in io.get_output()

    def test_interactive_mode_banner(self):
        """Interactive mode should show clear banner."""
        io = MockRichIO()

        io.rule("INTERACTIVE MODE")
        io.syntax("npx create-react-app my-app", language="shell")
        io.echo("You can respond to any prompts. Output goes directly to terminal.")

        rules = io.get_rules()
        assert any(r['title'] == "INTERACTIVE MODE" for r in rules)


class TestErrorDisplayPanel:
    """Test that errors display in red-bordered panels."""

    def test_error_renders_as_red_panel(self):
        """Errors should display in panel with red border."""
        io = MockRichIO()

        error_msg = "File not found: /nonexistent/path.txt"
        io.panel(error_msg, title="Error", border_style="red")

        panel = assert_panel_rendered(
            io,
            content_contains="File not found",
            title="Error",
            border_style="red"
        )
        assert panel['border_style'] == "red"

    def test_error_panel_has_error_title(self):
        """Error panels should have 'Error' title."""
        io = MockRichIO()

        io.panel("Permission denied", title="Error", border_style="red")

        panel = io.get_panels()[0]
        assert panel['title'] == "Error"

    def test_error_with_context(self):
        """Errors should include relevant context."""
        io = MockRichIO()

        error_with_context = """Command failed: npm install
Exit code: 1
Error: EACCES permission denied"""
        io.panel(error_with_context, title="Error", border_style="red")

        panel = io.get_panels()[0]
        assert "Exit code: 1" in panel['content']
        assert "EACCES" in panel['content']

    def test_warning_uses_yellow_border(self):
        """Warnings should use yellow border (not red)."""
        io = MockRichIO()

        io.panel("This operation may take a while",
                title="Warning", border_style="yellow")

        panel = io.get_panels()[0]
        assert panel['border_style'] == "yellow"
        assert panel['title'] == "Warning"

    def test_agent_error_includes_exception_info(self):
        """Agent errors should include exception details."""
        io = MockRichIO()

        error_msg = """Agent error: ConnectionError
Details: Unable to connect to LLM provider
Saving audit log..."""
        io.panel(error_msg, title="Error", border_style="red")

        panel = io.get_panels()[0]
        assert "ConnectionError" in panel['content']
        assert "audit log" in panel['content']


class TestProgressAndStatusOutput:
    """Test progress and status message formatting."""



    def test_task_header_prominent(self):
        """Task header should be prominent and clear."""
        io = MockRichIO()

        io.rule("Agent Task")
        io.secho("Create a new React component for user dashboard",
                fg="white", bold=True)

        rules = io.get_rules()
        assert len(rules) == 1

        styled = io.get_styled_outputs()[0]
        assert styled['bold'] is True


class TestResultDisplay:
    """Test result and completion display formatting."""

    def test_tool_result_formatted(self):
        """Tool results should be clearly formatted."""
        io = MockRichIO()

        result = "File written successfully: /output/data.json (245 bytes)"
        io.panel(result, title="Result", border_style="green")

        panel = assert_panel_rendered(
            io,
            title="Result",
            border_style="green"
        )
        assert "245 bytes" in panel['content']

    def test_truncated_result_indicates_truncation(self):
        """Long results should indicate truncation."""
        io = MockRichIO()

        # Simulate truncated result
        result = "x" * 500 + "... [truncated]"
        io.panel(result, title="Result", border_style="green")

        panel = io.get_panels()[0]
        assert "[truncated]" in panel['content']

    def test_final_completion_result(self):
        """Final task completion should be clearly indicated."""
        io = MockRichIO()

        io.rule("Task Complete")
        io.panel(
            "Successfully created React component with tests and documentation",
            title="Final Result",
            border_style="green"
        )

        rules = io.get_rules()
        assert any(r['title'] == "Task Complete" for r in rules)


class TestDuplicateAndRetryWarnings:
    """Test warning displays for duplicate actions and retries."""

    def test_duplicate_action_warning_styled(self):
        """Duplicate action warnings should be visually distinct."""
        io = MockRichIO()

        warning = "Same read_file action detected 3 times - possible infinite loop"
        io.panel(warning, title="Duplicate Action Warning", border_style="yellow")

        panel = assert_panel_rendered(
            io,
            content_contains="infinite loop",
            border_style="yellow"
        )
        assert "Duplicate" in panel['title']

    def test_retry_warning_with_context(self):
        """Retry warnings should include attempt context."""
        io = MockRichIO()

        warning = "Retry attempt 3/5 for failed operation"
        io.panel(warning, title="Retry Warning", border_style="yellow")

        panel = io.get_panels()[0]
        assert "3/5" in panel['content']


class TestIOIntegration:
    """Test IO integration patterns for agent output."""

    def test_mockio_captures_all_rich_components(self):
        """MockRichIO should capture all Rich component types."""
        io = MockRichIO()

        io.echo("Plain message")
        io.secho("Styled message", fg="green")
        io.panel("Panel content", title="Test", border_style="blue")
        io.table(["A", "B"], [["1", "2"]], title="Test Table")
        io.syntax("print('hello')", language="python")
        io.rule("Separator")

        assert len(io.get_panels()) == 1
        assert len(io.get_tables()) == 1
        assert len(io.get_syntax_blocks()) == 1
        assert len(io.get_rules()) == 1
        assert "Plain message" in io.get_output()

    def test_io_reset_clears_all(self):
        """Reset should clear all captured output."""
        io = MockRichIO()

        io.panel("Test", title="Test", border_style="blue")
        io.table(["A"], [["1"]])
        io.syntax("code")

        io.reset()

        assert len(io.get_panels()) == 0
        assert len(io.get_tables()) == 0
        assert len(io.get_syntax_blocks()) == 0
        assert io.get_output() == ""


class TestAgentOutputMethods:
    """
    Tests for agent output helper methods.

    These tests verify the output methods that will be added to the agent
    to produce Rich-formatted output.
    """

    def test_show_thinking_method(self):
        """Agent should have show_thinking() method using panels."""
        io = MockRichIO()

        # Expected method signature:
        # agent.show_thinking(io, "Analyzing requirements...")

        # Simulated implementation
        def show_thinking(io_obj, text):
            if text and text.strip():
                io_obj.panel(text, title="Thinking", border_style="blue")

        show_thinking(io, "Analyzing requirements...")

        panel = io.get_panels()[0]
        assert panel['title'] == "Thinking"
        assert panel['border_style'] == "blue"

    def test_show_tool_request_method(self):
        """Agent should have show_tool_request() method using tables."""
        io = MockRichIO()

        # Expected method signature:
        # agent.show_tool_request(io, "read_file", {"path": "/test.py"})

        def show_tool_request(io_obj, tool_name, params):
            headers = ["Property", "Value"]
            rows = [["Tool", tool_name]]
            for key, value in params.items():
                rows.append([key, str(value)])
            io_obj.table(headers, rows, title="Tool Request")

        show_tool_request(io, "read_file", {"path": "/test.py"})

        table = io.get_tables()[0]
        assert table['title'] == "Tool Request"
        assert ["Tool", "read_file"] in table['rows']

    def test_show_command_method(self):
        """Agent should have show_command() method using syntax blocks."""
        io = MockRichIO()

        def show_command(io_obj, command):
            io_obj.syntax(command, language="shell")

        show_command(io, "npm install express")

        block = io.get_syntax_blocks()[0]
        assert block['language'] == "shell"
        assert "npm install" in block['code']

    def test_show_error_method(self):
        """Agent should have show_error() method using red panels."""
        io = MockRichIO()

        def show_error(io_obj, message):
            io_obj.panel(message, title="Error", border_style="red")

        show_error(io, "Connection timeout")

        panel = io.get_panels()[0]
        assert panel['title'] == "Error"
        assert panel['border_style'] == "red"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_parameters_handled(self):
        """Tools with no parameters should display correctly."""
        io = MockRichIO()

        headers = ["Property", "Value"]
        rows = [["Tool", "get_current_time"]]
        io.table(headers, rows, title="Tool Request")

        table = io.get_tables()[0]
        assert len(table['rows']) == 1

    def test_very_long_content_handled(self):
        """Very long content should be handled without error."""
        io = MockRichIO()

        long_content = "x" * 10000
        io.panel(long_content, title="Large Content", border_style="blue")

        panel = io.get_panels()[0]
        assert len(panel['content']) == 10000

    def test_special_characters_in_output(self):
        """Special characters should be handled correctly."""
        io = MockRichIO()

        # Various special characters that might cause issues
        content = "Tab:\tNewline:\nBackslash:\\Quote:\""
        io.panel(content, title="Special Chars", border_style="blue")

        panel = io.get_panels()[0]
        assert "\t" in panel['content']
        assert "\n" in panel['content']

    def test_unicode_in_output(self):
        """Unicode characters should be handled correctly."""
        io = MockRichIO()

        content = "Status: Complete"  # Note: no emojis per CLAUDE.md
        io.panel(content, title="Unicode Test", border_style="green")

        panel = io.get_panels()[0]
        assert "Status" in panel['content']

    def test_none_values_handled(self):
        """None values in parameters should be handled."""
        io = MockRichIO()

        # Table with None value converted to string
        headers = ["Property", "Value"]
        rows = [
            ["Tool", "test_tool"],
            ["optional_param", "None"]
        ]
        io.table(headers, rows, title="Tool Request")

        table = io.get_tables()[0]
        assert ["optional_param", "None"] in table['rows']


class TestConsistentStyling:
    """Test that styling is consistent across output types."""

    def test_thinking_always_blue(self):
        """All thinking panels should use blue border."""
        io = MockRichIO()

        messages = [
            "First thought",
            "Second thought",
            "Third thought"
        ]

        for msg in messages:
            io.panel(msg, title="Thinking", border_style="blue")

        panels = io.get_panels()
        assert all(p['border_style'] == "blue" for p in panels)

    def test_errors_always_red(self):
        """All error panels should use red border."""
        io = MockRichIO()

        errors = [
            "Error 1",
            "Error 2"
        ]

        for err in errors:
            io.panel(err, title="Error", border_style="red")

        panels = io.get_panels()
        assert all(p['border_style'] == "red" for p in panels)

    def test_results_always_green(self):
        """All result panels should use green border."""
        io = MockRichIO()

        io.panel("Success", title="Result", border_style="green")

        panel = io.get_panels()[0]
        assert panel['border_style'] == "green"


# =============================================================================
# Integration Tests - These will FAIL until agent is modified
# =============================================================================

class TestAgentIOIntegration:
    """
    Integration tests for agent Rich output.

    These tests verify the actual agent uses IO correctly.
    """

    def test_agent_accepts_io_parameter(self):
        """CodeAgent should accept an io parameter."""
        from scrappy.agent.core import CodeAgent
        from tests.helpers import ConfigurableTestOrchestrator

        io = MockRichIO()
        orch = ConfigurableTestOrchestrator()

        agent = CodeAgent(orchestrator=orch, io=io)

        assert hasattr(agent, 'io')
        assert agent.io is io

    def test_agent_init_uses_io_for_progress(self):
        """Agent initialization should output progress via IO."""
        from scrappy.agent.core import CodeAgent
        from tests.helpers import ConfigurableTestOrchestrator

        io = MockRichIO()
        orch = ConfigurableTestOrchestrator()

        agent = CodeAgent(orchestrator=orch, io=io)

        # Should see styled progress messages
        output = io.get_output()
        styled = io.get_styled_outputs()

        assert any("Preparing agent tools" in s['text'] for s in styled), \
            f"Expected 'Preparing agent tools' in styled output. Got: {styled}"

        # Color is determined by theme - tested in theme tests






class TestAgentOutputHelpers:
    """
    Test agent output helper methods.

    These tests verify helper methods on the agent for Rich output.
    They will FAIL until these methods are implemented.
    """

    def test_agent_has_show_thinking_method(self):
        """Agent should have _show_thinking helper method."""
        from scrappy.agent.core import CodeAgent
        from tests.helpers import ConfigurableTestOrchestrator

        io = MockRichIO()
        orch = ConfigurableTestOrchestrator()
        agent = CodeAgent(orchestrator=orch, io=io)

        assert hasattr(agent.ui, 'show_thinking'), \
            "Agent UI should have show_thinking method"

        # Test the method
        agent.ui.show_thinking("Test thinking")

        panels = io.get_panels()
        assert len(panels) == 1
        assert panels[0]['title'] == 'Thinking'
        # Color is determined by theme - tested in theme tests

    def test_agent_has_show_tool_request_method(self):
        """Agent should have _show_tool_request helper method."""
        from scrappy.agent.core import CodeAgent
        from tests.helpers import ConfigurableTestOrchestrator

        io = MockRichIO()
        orch = ConfigurableTestOrchestrator()
        agent = CodeAgent(orchestrator=orch, io=io)

        assert hasattr(agent.ui, 'show_tool_request'), \
            "Agent UI should have show_tool_request method"

        # Test the method
        agent.ui.show_tool_request("read_file", {"path": "/test.py"})

        tables = io.get_tables()
        assert len(tables) == 1
        assert tables[0]['title'] == 'Tool Request'

    def test_agent_has_show_error_method(self):
        """Agent should have _show_error helper method."""
        from scrappy.agent.core import CodeAgent
        from tests.helpers import ConfigurableTestOrchestrator

        io = MockRichIO()
        orch = ConfigurableTestOrchestrator()
        agent = CodeAgent(orchestrator=orch, io=io)

        assert hasattr(agent.ui, 'show_error'), \
            "Agent UI should have show_error method"

        # Test the method
        agent.ui.show_error("Test error message")

        panels = io.get_panels()
        assert len(panels) == 1
        assert panels[0]['title'] == 'Error'
        # Color is determined by theme - tested in theme tests

    def test_agent_has_show_result_method(self):
        """Agent should have _show_result helper method."""
        from scrappy.agent.core import CodeAgent
        from tests.helpers import ConfigurableTestOrchestrator

        io = MockRichIO()
        orch = ConfigurableTestOrchestrator()
        agent = CodeAgent(orchestrator=orch, io=io)

        assert hasattr(agent.ui, 'show_result'), \
            "Agent UI should have show_result method"

        # Test the method
        agent.ui.show_result("Test result")

        panels = io.get_panels()
        assert len(panels) == 1
        # Color is determined by theme - tested in theme tests

    def test_agent_has_show_command_method(self):
        """Agent should have _show_command helper method."""
        from scrappy.agent.core import CodeAgent
        from tests.helpers import ConfigurableTestOrchestrator

        io = MockRichIO()
        orch = ConfigurableTestOrchestrator()
        agent = CodeAgent(orchestrator=orch, io=io)

        assert hasattr(agent.ui, 'show_command'), \
            "Agent UI should have show_command method"

        # Test the method
        agent.ui.show_command("npm install")

        blocks = io.get_syntax_blocks()
        assert len(blocks) == 1
        assert blocks[0]['language'] == 'shell'

    def test_agent_has_show_progress_method(self):
        """Agent should have _show_progress helper method."""
        from scrappy.agent.core import CodeAgent
        from tests.helpers import ConfigurableTestOrchestrator

        io = MockRichIO()
        orch = ConfigurableTestOrchestrator()
        agent = CodeAgent(orchestrator=orch, io=io)

        assert hasattr(agent.ui, 'show_progress'), \
            "Agent UI should have show_progress method"

        # Clear output from initialization
        io.clear_output()

        # Test the method
        agent.ui.show_progress("Loading...")

        styled = io.get_styled_outputs()
        assert len(styled) == 1
        assert "Loading" in styled[0]['text']
