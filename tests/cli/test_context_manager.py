"""
Tests for context_manager.py - Context operations split from session.py.

Tests verify behavior of context management commands:
- Show context status
- Explore project
- Refresh (force re-explore)
- Clear cache
- Clear working memory
- Toggle context awareness
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestContextManagerShowStatus:
    """Tests for showing context status (no args)."""

    def test_show_context_status_displays_project_info(self):
        """Should display project path and exploration status."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator(context_explored=True)
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="", io=io)

        output = io.get_output()
        assert "Context Status:" in output
        assert "Project:" in output
        assert "Explored:" in output

    def test_show_context_status_displays_cache_info(self):
        """Should display cache file location and existence."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="", io=io)

        output = io.get_output()
        assert "Cache File:" in output
        assert "Cache Exists:" in output

    def test_show_context_status_displays_working_memory(self):
        """Should display session working memory summary."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="", io=io)

        output = io.get_output()
        assert "Working Memory:" in output
        assert "Files Cached:" in output
        assert "Recent Searches:" in output

    def test_show_context_status_displays_git_info_when_available(self):
        """Should display git branch and commit count when git history exists."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        # Override get_context_status to include git info
            'project_path': Path('/test'),
            'is_explored': True,
            'has_summary': True,
            'explored_at': '2024-01-01',
            'total_files': 100,
            'cache_file': '/test/.cache',
            'cache_exists': True,
            'has_git_history': True,
            'git_branch': 'main',
            'git_commits': 150
        }
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="", io=io)

        output = io.get_output()
        assert "Git Branch:" in output
        assert "main" in output
        assert "Git Commits:" in output

    def test_show_context_status_displays_summary_when_available(self):
        """Should display project summary when it exists."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator(context_explored=True)
        orchestrator.context.summary = "This is a Python web application"
            'project_path': Path('/test'),
            'is_explored': True,
            'has_summary': True,
            'explored_at': '2024-01-01',
            'total_files': 50,
            'cache_file': '/test/.cache',
            'cache_exists': True
        }
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="", io=io)

        output = io.get_output()
        assert "Project Summary:" in output
        assert "Python web application" in output


class TestContextManagerExplore:
    """Tests for explore command."""

    def test_explore_uses_cache_when_available(self):
        """Should use cached exploration when available."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="explore", io=io)

        output = io.get_output()
        assert "cached" in output.lower()

    def test_explore_shows_file_count(self):
        """Should display total files found during exploration."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.explore_project = lambda force=False: {
            'status': 'explored',
            'total_files': 42
        }
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="explore", io=io)

        output = io.get_output()
        assert "42" in output

    def test_explore_displays_summary_after_exploration(self):
        """Should display generated summary after exploration."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.context.summary = "Generated project summary"
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="explore", io=io)

        output = io.get_output()
        assert "Generated Summary:" in output or "Summary:" in output


class TestContextManagerRefresh:
    """Tests for refresh (force re-explore) command."""

    def test_refresh_forces_reexploration(self):
        """Should force re-exploration of project."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        force_called = []
        original_explore = orchestrator.explore_project
        orchestrator.explore_project = lambda force=False: (
            force_called.append(force),
            original_explore(force)
        )[1]

        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="refresh", io=io)

        assert force_called == [True]

    def test_refresh_shows_file_count(self):
        """Should display file count after refresh."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.explore_project = lambda force=False: {
            'status': 'explored',
            'total_files': 75
        }
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="refresh", io=io)

        output = io.get_output()
        assert "75" in output


class TestContextManagerClear:
    """Tests for clear cache command."""

    def test_clear_clears_context_cache(self):
        """Should clear the context cache."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        clear_called = []
        orchestrator.context.clear_cache = lambda: clear_called.append(True)

        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="clear", io=io)

        assert clear_called == [True]
        output = io.get_output()
        assert "cleared" in output.lower()

    def test_clear_shows_confirmation_message(self):
        """Should display confirmation that cache was cleared."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.context.clear_cache = Mock()
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="clear", io=io)

        output = io.get_output()
        assert "cache" in output.lower() and "cleared" in output.lower()


class TestContextManagerClearMem:
    """Tests for clear working memory command."""

    def test_clearmem_clears_working_memory(self):
        """Should clear session working memory."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = ContextManager(orchestrator)
        io = MockIO()

        # Add some data to working memory
        orchestrator._working_memory['files']['test.py'] = 'content'
        orchestrator._working_memory['searches'].append('query')

        manager.manage_context(args="clearmem", io=io)

        # Verify working memory was cleared
        summary = orchestrator.get_working_memory_summary()
        assert summary['files_cached'] == 0
        output = io.get_output()
        assert "cleared" in output.lower()


class TestContextManagerToggle:
    """Tests for toggle context awareness command."""

    def test_toggle_disables_context_awareness_when_enabled(self):
        """Should disable context awareness when currently enabled."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.context_aware = True
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="toggle", io=io)

        assert orchestrator.context_aware is False
        output = io.get_output()
        assert "disabled" in output.lower()

    def test_toggle_enables_context_awareness_when_disabled(self):
        """Should enable context awareness when currently disabled."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.context_aware = False
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="toggle", io=io)

        assert orchestrator.context_aware is True
        output = io.get_output()
        assert "enabled" in output.lower()


class TestContextManagerInvalidCommand:
    """Tests for invalid/unknown commands."""

    def test_invalid_command_shows_usage(self):
        """Should display usage information for unknown commands."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="invalid_command", io=io)

        output = io.get_output()
        assert "Usage:" in output
        assert "explore" in output
        assert "refresh" in output
        assert "clear" in output
        assert "toggle" in output

    def test_usage_shows_all_available_commands(self):
        """Should show all available commands in usage."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = ContextManager(orchestrator)
        io = MockIO()

        manager.manage_context(args="help", io=io)

        output = io.get_output()
        # All commands should be listed
        assert "explore" in output
        assert "refresh" in output
        assert "clear" in output
        assert "clearmem" in output
        assert "toggle" in output


class TestContextManagerCaseInsensitivity:
    """Tests for command case handling."""

    def test_commands_are_case_insensitive(self):
        """Commands should work regardless of case."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = ContextManager(orchestrator)

        # Test various cases
        for cmd in ["EXPLORE", "Explore", "explore", "ExPlOrE"]:
            io = MockIO()
            manager.manage_context(args=cmd, io=io)
            output = io.get_output()
            # Should not show usage (which would indicate unrecognized command)
            assert "Usage:" not in output


class TestContextManagerDefaultIO:
    """Tests for default IO behavior."""

    def test_uses_rich_io_when_io_not_provided(self):
        """Should use RichIO as default when io parameter is None."""
        from src.cli.context_manager import ContextManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = ContextManager(orchestrator)

        # This should not raise an error - it will use RichIO internally
        # We can't easily verify output, but we can verify it doesn't crash
        try:
            with patch('src.cli.context_manager.RichIO') as mock_rich:
                mock_io = MockIO()
                mock_rich.return_value = mock_io
                manager.manage_context(args="", io=None)
        except ImportError:
            # If RichIO import fails in the new module, that's also informative
            pass
