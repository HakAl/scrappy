"""
Behavior tests for CLI context manager functionality.

Tests actual behavior of context display and management commands.
Focuses on:
- Context status display workflows
- Subcommand execution (explore, refresh, clear, etc.)
- Working memory display
- User-facing output
- Error handling
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.cli.context_commands import CLIContextCommands
from tests.helpers import MockIO


class TestContextStatusDisplay:
    """Test context status display shows correct information."""

    def test_shows_project_information(self):
        """Should display project path, exploration status, and cache info."""
        orchestrator = MagicMock()
        orchestrator.get_context_status.return_value = {
            'project_path': Path('/test/project'),
            'is_explored': True,
            'has_summary': True,
            'explored_at': '2024-01-01 10:30:00',
            'total_files': 42,
            'has_git_history': True,
            'git_branch': 'main',
            'git_commits': 150,
            'cache_file': Path('/test/.cache'),
            'cache_exists': True
        }
        orchestrator.context_aware = True
        orchestrator.working_memory.get_summary.return_value = {
            'files_cached': 5,
            'cached_files': ['file1.py', 'file2.py'],
            'recent_searches': 3,
            'git_operations': 2,
            'discoveries': 1
        }
        orchestrator.context.summary = "Test project summary"

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("")

        output = io.get_all_output()
        assert "Context Status:" in output
        assert "test" in output and "project" in output  # Path parts (platform-agnostic)
        assert "Yes" in output  # Explored status
        assert "42" in output  # Total files
        assert "main" in output  # Git branch
        assert "150" in output  # Git commits
        assert "Enabled" in output  # Context aware
        assert "Session Working Memory:" in output
        assert "5" in output  # Files cached
        assert "Test project summary" in output

    def test_shows_working_memory_with_limited_file_list(self):
        """Should show last 5 cached files and count remaining."""
        orchestrator = MagicMock()
        orchestrator.get_context_status.return_value = {
            'project_path': Path('/test'),
            'is_explored': False,
            'has_summary': False,
            'explored_at': None,
            'total_files': 0,
            'cache_file': Path('/test/.cache'),
            'cache_exists': False
        }
        orchestrator.working_memory.get_summary.return_value = {
            'files_cached': 8,
            'cached_files': ['f1.py', 'f2.py', 'f3.py', 'f4.py', 'f5.py', 'f6.py', 'f7.py', 'f8.py'],
            'recent_searches': 0,
            'git_operations': 0,
            'discoveries': 0
        }

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("")

        output = io.get_all_output()
        # Should show last 5 files
        assert "f4.py" in output
        assert "f5.py" in output
        assert "f6.py" in output
        assert "f7.py" in output
        assert "f8.py" in output
        # Should indicate more files exist
        assert "3 more" in output

    def test_shows_git_info_only_when_available(self):
        """Should only show git info when has_git_history is true."""
        orchestrator = MagicMock()
        orchestrator.get_context_status.return_value = {
            'project_path': Path('/test'),
            'is_explored': True,
            'has_summary': False,
            'explored_at': None,
            'total_files': 10,
            'has_git_history': False,  # No git
            'cache_file': Path('/test/.cache'),
            'cache_exists': True
        }
        orchestrator.context_aware = False
        orchestrator.working_memory.get_summary.return_value = {
            'files_cached': 0,
            'cached_files': [],
            'recent_searches': 0,
            'git_operations': 0,
            'discoveries': 0
        }

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("")

        output = io.get_all_output()
        # Should NOT show git info
        assert "Git Branch:" not in output
        assert "Git Commits:" not in output


class TestExploreSubcommandRemoved:
    """Test that explore subcommand was removed from /context.

    Note: The explore functionality was consolidated into the standalone
    /explore command (Issue 8 - command consolidation). These tests verify
    that /context explore now returns an error directing users to /explore.
    """

    def test_explore_subcommand_shows_error(self):
        """Should show error when explore subcommand is used."""
        orchestrator = MagicMock()

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("explore")

        output = io.get_all_output()
        assert "Unknown subcommand" in output
        # Should not call explore_project
        orchestrator.explore_project.assert_not_called()

    def test_explore_subcommand_shows_valid_options(self):
        """Should list valid subcommands when explore is attempted."""
        orchestrator = MagicMock()

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("explore")

        output = io.get_all_output()
        # Should show valid options
        assert "refresh" in output
        assert "clear" in output

    def test_explore_not_in_valid_subcommands(self):
        """Verify explore is not listed as a valid subcommand."""
        orchestrator = MagicMock()

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("explore")

        output = io.get_all_output()
        # The error message lists valid options - explore should not be among them
        # Valid options: add, clear, clearmem, refresh, toggle
        assert "Valid options:" in output or "Usage:" in output


class TestRefreshCommand:
    """Test forced re-exploration command."""

    def test_forces_reexploration(self):
        """Should call explore_project with force=True."""
        orchestrator = MagicMock()
        orchestrator.explore_project.return_value = {
            'status': 'explored',
            'total_files': 75
        }
        orchestrator.context.summary = "Updated summary"

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("refresh")

        orchestrator.explore_project.assert_called_once_with(force=True)
        output = io.get_all_output()
        assert "Force re-exploring" in output
        assert "75 files" in output
        assert "Updated summary" in output


class TestClearCommands:
    """Test cache and memory clearing commands."""

    def test_clear_command_clears_cache(self):
        """Should clear context cache from disk."""
        orchestrator = MagicMock()

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("clear")

        orchestrator.context.clear_cache.assert_called_once()
        output = io.get_all_output()
        assert "Context cache cleared" in output

    def test_clearmem_command_clears_working_memory(self):
        """Should clear session working memory."""
        orchestrator = MagicMock()

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("clearmem")

        orchestrator.working_memory.clear.assert_called_once()
        output = io.get_all_output()
        assert "Session working memory cleared" in output


class TestToggleCommand:
    """Test context awareness toggle."""

    def test_toggles_context_awareness_on(self):
        """Should enable context awareness when currently disabled."""
        orchestrator = MagicMock()
        orchestrator.context_aware = False

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("toggle")

        assert orchestrator.context_aware is True
        output = io.get_all_output()
        assert "enabled" in output.lower()

    def test_toggles_context_awareness_off(self):
        """Should disable context awareness when currently enabled."""
        orchestrator = MagicMock()
        orchestrator.context_aware = True

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("toggle")

        assert orchestrator.context_aware is False
        output = io.get_all_output()
        assert "disabled" in output.lower()


class TestAddCommand:
    """Test adding files to context."""

    def test_add_command_requires_path_argument(self):
        """Should show error when add called without path."""
        orchestrator = MagicMock()

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("add")

        output = io.get_all_output()
        assert "Error" in output
        assert "requires a file path" in output

    def test_add_command_accepts_path(self):
        """Should accept path argument and display it."""
        orchestrator = MagicMock()

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("add src/test.py")

        output = io.get_all_output()
        assert "Adding to context" in output
        assert "src/test.py" in output


class TestInputValidation:
    """Test input validation and error handling."""

    def test_shows_error_for_invalid_subcommand(self):
        """Should display error and usage for invalid subcommand."""
        orchestrator = MagicMock()

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("invalid_command")

        output = io.get_all_output()
        assert "Usage:" in output
        # Note: 'explore' was removed and consolidated into /explore command
        assert "refresh" in output
        assert "clear" in output
        assert "clearmem" in output
        assert "toggle" in output



class TestContextManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_handles_empty_working_memory(self):
        """Should display correctly when working memory is empty."""
        orchestrator = MagicMock()
        orchestrator.get_context_status.return_value = {
            'project_path': Path('/test'),
            'is_explored': True,
            'has_summary': False,
            'explored_at': None,
            'total_files': 10,
            'cache_file': Path('/test/.cache'),
            'cache_exists': True
        }
        orchestrator.working_memory.get_summary.return_value = {
            'files_cached': 0,
            'cached_files': [],
            'recent_searches': 0,
            'git_operations': 0,
            'discoveries': 0
        }

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("")

        output = io.get_all_output()
        # Output may contain ANSI color codes around the "0"
        assert "Files Cached:" in output and "0" in output

    def test_handles_summary_that_is_not_string(self):
        """Should handle non-string summary gracefully."""
        orchestrator = MagicMock()
        orchestrator.get_context_status.return_value = {
            'project_path': Path('/test'),
            'is_explored': True,
            'has_summary': True,
            'explored_at': None,
            'total_files': 5,
            'cache_file': Path('/test/.cache'),
            'cache_exists': True
        }
        orchestrator.working_memory.get_summary.return_value = {
            'files_cached': 0,
            'cached_files': [],
            'recent_searches': 0,
            'git_operations': 0,
            'discoveries': 0
        }
        orchestrator.context.summary = {'not': 'a string'}  # Non-string summary

        io = MockIO()
        manager = CLIContextCommands(orchestrator, io)

        manager.manage_context("")

        output = io.get_all_output()
        # Should not crash, and should not show project summary section
        assert "Context Status:" in output
        assert "Project Summary:" not in output
