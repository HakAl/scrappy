"""
Tests for Phase 6 theme integration.

Verifies that remaining CLI and Tools components properly accept and use theme parameters:
- context_commands.py (Step 15)
- interactive.py (Step 15)
- textual_app.py (Step 15)
- tools/base.py (Step 16)
- tools/file_tools.py (Step 16)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from io import StringIO
from pathlib import Path
from dataclasses import dataclass

from scrappy.infrastructure.theme import (
    ThemeProtocol,
    ScrappyTheme,
    LightTheme,
    NoColorTheme,
    DEFAULT_THEME,
    SYNTAX_COLORS,
)
from scrappy.cli.textual import ScrappyApp, TextualOutputAdapter


class TestContextCommandsThemeIntegration:
    """Tests for context_commands.py theme integration."""

    def setup_method(self):
        """Create test fixtures."""
        self.io = Mock()
        self.io.secho = Mock()
        self.io.echo = Mock()
        self.io.style = Mock(return_value="styled")
        self.orchestrator = Mock()
        self.orchestrator.context_aware = True
        self.orchestrator.get_context_status = Mock(return_value={
            "project_path": "/test/path",
            "is_explored": True,
            "has_summary": False,
            "explored_at": None,
            "total_files": 10,
            "cache_file": "/test/cache",
            "cache_exists": True,
        })
        self.orchestrator.working_memory = Mock()
        self.orchestrator.working_memory.get_summary = Mock(return_value={
            "files_cached": 5,
            "cached_files": [],
            "recent_searches": 0,
            "git_operations": 0,
            "discoveries": 0,
        })
        self.theme = ScrappyTheme()
        self.light_theme = LightTheme()

    def test_accepts_theme_parameter(self):
        """CLIContextCommands accepts theme parameter."""
        from scrappy.cli.context_commands import CLIContextCommands

        cmd = CLIContextCommands(
            orchestrator=self.orchestrator,
            io=self.io,
            theme=self.theme,
        )
        assert cmd._theme == self.theme

    def test_uses_default_theme_when_not_provided(self):
        """CLIContextCommands uses DEFAULT_THEME when not provided."""
        from scrappy.cli.context_commands import CLIContextCommands

        cmd = CLIContextCommands(
            orchestrator=self.orchestrator,
            io=self.io,
        )
        assert cmd._theme == DEFAULT_THEME

    def test_context_status_uses_theme_primary_for_header(self):
        """manage_context uses theme.primary for Context Status header."""
        from scrappy.cli.context_commands import CLIContextCommands

        cmd = CLIContextCommands(
            orchestrator=self.orchestrator,
            io=self.io,
            theme=self.theme,
        )

        cmd.manage_context("")

        # Check that secho was called with theme.primary for headers
        calls = [call for call in self.io.secho.call_args_list
                 if "Context Status" in str(call)]
        assert len(calls) > 0
        _, kwargs = calls[0]
        assert kwargs["fg"] == self.theme.primary

    def test_context_status_uses_theme_success_for_explored(self):
        """manage_context uses theme.success when explored is True."""
        from scrappy.cli.context_commands import CLIContextCommands

        cmd = CLIContextCommands(
            orchestrator=self.orchestrator,
            io=self.io,
            theme=self.theme,
        )

        cmd.manage_context("")

        # style was called with theme.success for "Yes" (explored)
        calls = self.io.style.call_args_list
        success_calls = [call for call in calls if self.theme.success in str(call)]
        assert len(success_calls) > 0

    def test_validation_error_uses_theme_error(self):
        """manage_context uses theme.error for validation errors."""
        from scrappy.cli.context_commands import CLIContextCommands

        cmd = CLIContextCommands(
            orchestrator=self.orchestrator,
            io=self.io,
            theme=self.theme,
        )

        cmd.manage_context("invalid_subcommand")

        # secho should be called with theme.error
        calls = self.io.secho.call_args_list
        error_calls = [call for call in calls if call[1].get("fg") == self.theme.error]
        assert len(error_calls) > 0

    def test_toggle_uses_theme_success_when_enabled(self):
        """manage_context toggle uses theme.success when context becomes enabled."""
        from scrappy.cli.context_commands import CLIContextCommands

        self.orchestrator.context_aware = False  # Will become True after toggle

        cmd = CLIContextCommands(
            orchestrator=self.orchestrator,
            io=self.io,
            theme=self.theme,
        )

        cmd.manage_context("toggle")

        calls = self.io.secho.call_args_list
        success_calls = [call for call in calls if call[1].get("fg") == self.theme.success]
        assert len(success_calls) > 0

    def test_toggle_uses_theme_warning_when_disabled(self):
        """manage_context toggle uses theme.warning when context becomes disabled."""
        from scrappy.cli.context_commands import CLIContextCommands

        self.orchestrator.context_aware = True  # Will become False after toggle

        cmd = CLIContextCommands(
            orchestrator=self.orchestrator,
            io=self.io,
            theme=self.theme,
        )

        cmd.manage_context("toggle")

        calls = self.io.secho.call_args_list
        warning_calls = [call for call in calls if call[1].get("fg") == self.theme.warning]
        assert len(warning_calls) > 0


class TestInteractiveModeThemeIntegration:
    """Tests for interactive.py theme integration."""

    def setup_method(self):
        """Create test fixtures."""
        self.io = Mock()
        self.io.secho = Mock()
        self.io.echo = Mock()
        self.orchestrator = Mock()
        self.session_context = Mock()
        self.session_context.conversation_history = []
        self.session_context.verbose_mode = False
        self.session_context.auto_save = False
        self.state_manager = Mock()
        self.state_manager.plan_active = False
        self.input_handler = Mock()
        self.input_handler.is_command = Mock(return_value=False)
        self.command_router = Mock()
        self.display = Mock()
        self.smart = Mock()
        self.task_router = Mock()
        self.task_router.handle_auto_route = Mock(return_value=Mock(
            success=True,
            output="test output",
            provider_used="test",
            tokens_used=100,
            execution_time=0.1,
            metadata={},
        ))
        self.tasks = Mock()
        self.logger = Mock()
        self.theme = ScrappyTheme()

    def test_accepts_theme_parameter(self):
        """InteractiveMode accepts theme parameter."""
        from scrappy.cli.interactive import InteractiveMode

        mode = InteractiveMode(
            io=self.io,
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            state_manager=self.state_manager,
            input_handler=self.input_handler,
            command_router=self.command_router,
            display=self.display,
            smart=self.smart,
            task_router=self.task_router,
            tasks=self.tasks,
            logger=self.logger,
            theme=self.theme,
        )
        assert mode._theme == self.theme

    def test_uses_default_theme_when_not_provided(self):
        """InteractiveMode uses DEFAULT_THEME when not provided."""
        from scrappy.cli.interactive import InteractiveMode

        mode = InteractiveMode(
            io=self.io,
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            state_manager=self.state_manager,
            input_handler=self.input_handler,
            command_router=self.command_router,
            display=self.display,
            smart=self.smart,
            task_router=self.task_router,
            tasks=self.tasks,
            logger=self.logger,
        )
        assert mode._theme == DEFAULT_THEME

    def test_process_input_echoes_with_theme_text(self):
        """_process_input uses theme.text for user input echo."""
        from scrappy.cli.interactive import InteractiveMode

        mode = InteractiveMode(
            io=self.io,
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            state_manager=self.state_manager,
            input_handler=self.input_handler,
            command_router=self.command_router,
            display=self.display,
            smart=self.smart,
            task_router=self.task_router,
            tasks=self.tasks,
            logger=self.logger,
            theme=self.theme,
        )

        mode._process_input("test input")

        # Find the echo call with user input
        calls = [call for call in self.io.secho.call_args_list
                 if "test input" in str(call)]
        assert len(calls) > 0
        _, kwargs = calls[0]
        assert kwargs["fg"] == self.theme.text

    def test_handle_eof_uses_theme_warning(self):
        """_handle_eof uses theme.warning for EOF message."""
        from scrappy.cli.interactive import InteractiveMode

        mode = InteractiveMode(
            io=self.io,
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            state_manager=self.state_manager,
            input_handler=self.input_handler,
            command_router=self.command_router,
            display=self.display,
            smart=self.smart,
            task_router=self.task_router,
            tasks=self.tasks,
            logger=self.logger,
            theme=self.theme,
        )

        mode._handle_eof()

        calls = [call for call in self.io.secho.call_args_list
                 if "EOF" in str(call)]
        assert len(calls) > 0
        _, kwargs = calls[0]
        assert kwargs["fg"] == self.theme.warning

    def test_handle_eof_uses_theme_primary_for_goodbye(self):
        """_handle_eof uses theme.primary for Goodbye message."""
        from scrappy.cli.interactive import InteractiveMode

        mode = InteractiveMode(
            io=self.io,
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            state_manager=self.state_manager,
            input_handler=self.input_handler,
            command_router=self.command_router,
            display=self.display,
            smart=self.smart,
            task_router=self.task_router,
            tasks=self.tasks,
            logger=self.logger,
            theme=self.theme,
        )

        mode._handle_eof()

        calls = [call for call in self.io.secho.call_args_list
                 if "Goodbye" in str(call)]
        assert len(calls) > 0
        _, kwargs = calls[0]
        assert kwargs["fg"] == self.theme.primary

    def test_handle_error_uses_theme_error(self):
        """_handle_error uses theme.error for error messages."""
        from scrappy.cli.interactive import InteractiveMode

        mode = InteractiveMode(
            io=self.io,
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            state_manager=self.state_manager,
            input_handler=self.input_handler,
            command_router=self.command_router,
            display=self.display,
            smart=self.smart,
            task_router=self.task_router,
            tasks=self.tasks,
            logger=self.logger,
            theme=self.theme,
        )

        mode._handle_error(Exception("test error"))

        calls = [call for call in self.io.secho.call_args_list
                 if call[1].get("fg") == self.theme.error]
        assert len(calls) > 0


class TestTextualAppThemeIntegration:
    """Tests for textual_app.py theme integration."""

    def test_accepts_theme_parameter(self):
        """ScrappyApp accepts theme parameter."""
        interactive_mode = Mock()
        output_adapter = TextualOutputAdapter()
        theme = ScrappyTheme()

        app = ScrappyApp(
            interactive_mode=interactive_mode,
            output_adapter=output_adapter,
            theme=theme,
        )
        assert app._theme == theme

    def test_uses_default_theme_when_not_provided(self):
        """ScrappyApp uses DEFAULT_THEME when not provided."""
        interactive_mode = Mock()
        output_adapter = TextualOutputAdapter()

        app = ScrappyApp(
            interactive_mode=interactive_mode,
            output_adapter=output_adapter,
        )
        assert app._theme == DEFAULT_THEME


class TestToolResultThemeIntegration:
    """Tests for tools/base.py ToolResult theme integration."""

    def test_tool_result_rich_uses_default_theme_error(self):
        """ToolResult.__rich__ uses DEFAULT_THEME.error for error styling."""
        from scrappy.agent_tools.tools.base import ToolResult

        result = ToolResult(success=False, output="", error="test error")
        rich_output = result.__rich__()

        # Style should include DEFAULT_THEME.error
        assert DEFAULT_THEME.error in rich_output.style


class TestFileToolsThemeIntegration:
    """Tests for tools/file_tools.py theme integration."""

    def test_list_directory_uses_theme_primary_for_directories(self):
        """ListDirectoryTool uses DEFAULT_THEME.primary for directory names."""
        from scrappy.agent_tools.tools.file_tools import ListDirectoryTool
        from scrappy.agent_tools.tools.base import ToolContext
        import tempfile
        import os

        # Create a mock output interface
        output = Mock()
        output.style = Mock(return_value="styled_text")

        tool = ListDirectoryTool(output_interface=output)

        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a subdirectory
            subdir = Path(tmpdir) / "test_subdir"
            subdir.mkdir()

            # Create a mock config
            config = Mock()
            config.skip_directories = set()
            config.allowed_hidden_files = set()
            config.max_directory_tree_lines = 100

            context = ToolContext(
                project_root=Path(tmpdir),
                config=config,
            )

            tool.execute(context, path=".", depth=1)

            # Check that style was called with DEFAULT_THEME.primary for directories
            style_calls = output.style.call_args_list
            primary_calls = [call for call in style_calls
                           if call[1].get("color") == DEFAULT_THEME.primary]
            assert len(primary_calls) > 0

    def test_list_directory_uses_syntax_colors_for_files(self):
        """ListDirectoryTool uses SYNTAX_COLORS for file type colors."""
        from scrappy.agent_tools.tools.file_tools import ListDirectoryTool
        from scrappy.agent_tools.tools.base import ToolContext
        import tempfile

        # Create a mock output interface
        output = Mock()
        output.style = Mock(return_value="styled_text")

        tool = ListDirectoryTool(output_interface=output)

        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a Python file
            py_file = Path(tmpdir) / "test.py"
            py_file.write_text("# test")

            # Create a mock config
            config = Mock()
            config.skip_directories = set()
            config.allowed_hidden_files = set()
            config.max_directory_tree_lines = 100

            context = ToolContext(
                project_root=Path(tmpdir),
                config=config,
            )

            tool.execute(context, path=".", depth=1)

            # Check that style was called with SYNTAX_COLORS.python for .py files
            style_calls = output.style.call_args_list
            python_calls = [call for call in style_calls
                          if call[1].get("color") == SYNTAX_COLORS.python]
            assert len(python_calls) > 0

    def test_list_directory_uses_theme_text_muted_for_size(self):
        """ListDirectoryTool uses DEFAULT_THEME.text_muted for file sizes."""
        from scrappy.agent_tools.tools.file_tools import ListDirectoryTool
        from scrappy.agent_tools.tools.base import ToolContext
        import tempfile

        # Create a mock output interface
        output = Mock()
        output.style = Mock(return_value="styled_text")

        tool = ListDirectoryTool(output_interface=output)

        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("content")

            # Create a mock config
            config = Mock()
            config.skip_directories = set()
            config.allowed_hidden_files = set()
            config.max_directory_tree_lines = 100

            context = ToolContext(
                project_root=Path(tmpdir),
                config=config,
            )

            tool.execute(context, path=".", depth=1)

            # Check that style was called with DEFAULT_THEME.text_muted for sizes
            style_calls = output.style.call_args_list
            muted_calls = [call for call in style_calls
                         if call[1].get("color") == DEFAULT_THEME.text_muted]
            assert len(muted_calls) > 0


class TestNoColorThemePhase6Integration:
    """Tests that NoColorTheme works with Phase 6 components."""

    def setup_method(self):
        """Create test fixtures."""
        self.theme = NoColorTheme()


    def test_interactive_mode_with_no_color_theme(self):
        """InteractiveMode works with NoColorTheme."""
        from scrappy.cli.interactive import InteractiveMode

        io = Mock()
        io.secho = Mock()
        io.echo = Mock()
        orchestrator = Mock()
        session_context = Mock()
        session_context.conversation_history = []
        session_context.verbose_mode = False
        session_context.auto_save = False
        state_manager = Mock()
        state_manager.plan_active = False
        input_handler = Mock()
        input_handler.is_command = Mock(return_value=False)
        command_router = Mock()
        display = Mock()
        smart = Mock()
        task_router = Mock()
        task_router.handle_auto_route = Mock(return_value=Mock(
            success=True,
            output="test",
            provider_used="test",
            tokens_used=0,
            execution_time=0,
            metadata={},
        ))
        tasks = Mock()
        logger = Mock()

        mode = InteractiveMode(
            io=io,
            orchestrator=orchestrator,
            session_context=session_context,
            state_manager=state_manager,
            input_handler=input_handler,
            command_router=command_router,
            display=display,
            smart=smart,
            task_router=task_router,
            tasks=tasks,
            logger=logger,
            theme=self.theme,
        )
        assert mode._theme == self.theme
        assert mode._theme.error == ""

    def test_textual_app_with_no_color_theme(self):
        """ScrappyApp works with NoColorTheme."""
        interactive_mode = Mock()
        output_adapter = TextualOutputAdapter()

        app = ScrappyApp(
            interactive_mode=interactive_mode,
            output_adapter=output_adapter,
            theme=self.theme,
        )
        assert app._theme == self.theme
        assert app._theme.error == ""
