"""
Tests for persistence.py - Session management (simplified).

Tests verify behavior of session commands:
- Show session info (stats display)
- Clear session
"""


import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestPersistenceShowInfo:
    """Tests for showing session info (no args)."""

    def test_show_info_displays_header(self):
        """Should display session management header."""
        from scrappy.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        persistence = SessionPersistence(orchestrator, io)

        persistence.manage_session(args="")

        output = io.get_all_output()
        assert "Session" in output

    def test_show_info_displays_current_memory_stats(self):
        """Should display current session memory statistics."""
        from scrappy.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        persistence = SessionPersistence(orchestrator, io)

        persistence.manage_session(args="")

        output = io.get_all_output()
        assert "Files" in output
        assert "Searches" in output


class TestPersistenceClear:
    """Tests for clear session command."""

    def test_clear_calls_orchestrator_clear_session(self):
        """Should call orchestrator's clear_session method."""
        from scrappy.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        clear_called = []
        orchestrator.clear_session = lambda: clear_called.append(True)

        io = MockIO()
        persistence = SessionPersistence(orchestrator, io)

        persistence.manage_session(args="clear")

        assert clear_called == [True]

    def test_clear_shows_success_message(self):
        """Should display success message after clearing."""
        from scrappy.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        persistence = SessionPersistence(orchestrator, io)

        persistence.manage_session(args="clear")

        output = io.get_all_output()
        assert "clear" in output.lower() or "reset" in output.lower()


class TestPersistenceInvalidCommand:
    """Tests for invalid/unknown commands."""

    def test_invalid_command_shows_usage(self):
        """Should display usage information for unknown commands."""
        from scrappy.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        persistence = SessionPersistence(orchestrator, io)

        persistence.manage_session(args="invalid")

        output = io.get_all_output()
        assert "Usage:" in output
        assert "clear" in output


class TestPersistenceCaseInsensitivity:
    """Tests for command case handling."""

    def test_commands_are_case_insensitive(self):
        """Commands should work regardless of case."""
        from scrappy.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()

        for cmd in ["CLEAR", "Clear", "clear", "ClEaR"]:
            io = MockIO()
            persistence = SessionPersistence(orchestrator, io)
            persistence.manage_session(args=cmd)
            output = io.get_all_output()
            # Should not show error for valid command
            assert "Unknown subcommand" not in output
