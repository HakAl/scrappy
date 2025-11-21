"""
Tests for persistence.py - Session save/restore split from session.py.

Tests verify behavior of session persistence commands:
- Show session info
- Save session
- Load session
- Clear session
- Toggle auto-save
"""

import pytest
import json
from unittest.mock import Mock, patch, mock_open
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestPersistenceShowInfo:
    """Tests for showing session info (no args)."""

    def test_show_info_displays_header(self):
        """Should display session management header."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(args="", io=io)

        output = io.get_output()
        assert "Session" in output

    def test_show_info_displays_session_file_path(self):
        """Should display session file location."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.context.project_path = Path('/my/project')
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(args="", io=io)

        output = io.get_output()
        assert "Session File:" in output

    def test_show_info_displays_session_exists_status(self):
        """Should indicate whether session file exists."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(args="", io=io)

        output = io.get_output()
        assert "Session Exists:" in output or "Exists:" in output

    def test_show_info_displays_current_memory_stats(self):
        """Should display current session memory statistics."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(args="", io=io)

        output = io.get_output()
        assert "Files" in output
        assert "Searches" in output

    def test_show_info_displays_conversation_message_count(self):
        """Should display number of conversation messages."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        conversation = [
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi'}
        ]

        persistence.manage_session(
            args="",
            conversation_history=conversation,
            io=io
        )

        output = io.get_output()
        assert "2" in output
        assert "Conversation:" in output or "messages" in output.lower()

    def test_show_info_displays_auto_save_status(self):
        """Should display whether auto-save is enabled."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(
            args="",
            auto_save=True,
            io=io
        )

        output = io.get_output()
        assert "Auto-save:" in output or "auto-save" in output.lower()


class TestPersistenceShowSavedSessionInfo:
    """Tests for displaying saved session file info."""

    def test_displays_saved_session_details(self):
        """Should display details when session file exists."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        # Create a mock session file path that "exists"
        session_data = {
            'saved_at': '2024-01-15T10:30:00',
            'file_reads': {'a.py': 'content', 'b.py': 'content'},
            'search_results': [{'query': 'test'}],
            'git_operations': [{'op': 'status'}],
            'discoveries': [{'content': 'found something'}],
            'conversation_history': [{'role': 'user', 'content': 'hi'}]
        }

        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(session_data))):
                persistence = SessionPersistence(orchestrator)
                io = MockIO()

                persistence.manage_session(args="", io=io)

                output = io.get_output()
                assert "Last Saved:" in output
                assert "2024-01-15" in output

    def test_handles_corrupted_session_file(self):
        """Should handle errors when session file is corrupted."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()

        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data='invalid json')):
                persistence = SessionPersistence(orchestrator)
                io = MockIO()

                persistence.manage_session(args="", io=io)

                output = io.get_output()
                # Should handle error gracefully
                assert "Error" in output or "error" in output.lower()


class TestPersistenceSave:
    """Tests for save session command."""

    def test_save_calls_orchestrator_save_session(self):
        """Should call orchestrator's save_session method."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        save_calls = []
        orchestrator.save_session = lambda history: (
            save_calls.append(history),
            '/test/session.json'
        )[1]

        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        conversation = [{'role': 'user', 'content': 'test'}]
        persistence.manage_session(
            args="save",
            conversation_history=conversation,
            io=io
        )

        assert len(save_calls) == 1
        assert save_calls[0] == conversation

    def test_save_shows_success_message(self):
        """Should display success message after saving."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(
            args="save",
            conversation_history=[],
            io=io
        )

        output = io.get_output()
        assert "saved" in output.lower()

    def test_save_shows_message_count(self):
        """Should display number of messages saved."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        conversation = [
            {'role': 'user', 'content': '1'},
            {'role': 'assistant', 'content': '2'},
            {'role': 'user', 'content': '3'}
        ]
        persistence.manage_session(
            args="save",
            conversation_history=conversation,
            io=io
        )

        output = io.get_output()
        assert "3" in output

    def test_save_handles_error(self):
        """Should handle save errors gracefully."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.save_session = Mock(side_effect=Exception("Disk full"))

        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(
            args="save",
            conversation_history=[],
            io=io
        )

        output = io.get_output()
        assert "Error" in output or "error" in output.lower()

    def test_save_success_styled_green(self):
        """Should style success message in green."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(
            args="save",
            conversation_history=[],
            io=io
        )

        styled = io.get_styled_outputs()
        green_saves = [s for s in styled if s['fg'] == 'green' and 'saved' in s['text'].lower()]
        assert len(green_saves) > 0


class TestPersistenceLoad:
    """Tests for load session command."""

    def test_load_calls_orchestrator_load_session(self):
        """Should call orchestrator's load_session method."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        load_called = []
        original_load = orchestrator.load_session
        orchestrator.load_session = lambda: (
            load_called.append(True),
            original_load()
        )[1]

        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(args="load", io=io)

        assert load_called == [True]

    def test_load_shows_restored_counts(self):
        """Should display counts of restored items."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.load_session = lambda: {
            'status': 'loaded',
            'saved_at': '2024-01-01',
            'files_restored': 10,
            'searches_restored': 5,
            'git_ops_restored': 3,
            'discoveries_restored': 2,
            'conversation_history': []
        }

        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(args="load", io=io)

        output = io.get_output()
        assert "10" in output  # files
        assert "5" in output   # searches
        assert "3" in output   # git ops

    def test_load_returns_conversation_history(self):
        """Should return loaded conversation history."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        loaded_conversation = [
            {'role': 'user', 'content': 'previous'},
            {'role': 'assistant', 'content': 'response'}
        ]
        orchestrator.load_session = lambda: {
            'status': 'loaded',
            'saved_at': '2024-01-01',
            'files_restored': 0,
            'searches_restored': 0,
            'git_ops_restored': 0,
            'discoveries_restored': 0,
            'conversation_history': loaded_conversation
        }

        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        result = persistence.manage_session(args="load", io=io)

        assert result['conversation_history'] == loaded_conversation

    def test_load_no_session_shows_message(self):
        """Should show message when no session exists."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.load_session = lambda: {'status': 'no_session'}

        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(args="load", io=io)

        output = io.get_output()
        assert "No saved session" in output or "No previous session" in output

    def test_load_error_shows_message(self):
        """Should show error message when load fails."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.load_session = lambda: {
            'status': 'error',
            'message': 'File corrupted'
        }

        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(args="load", io=io)

        output = io.get_output()
        assert "Error" in output or "corrupted" in output.lower()


class TestPersistenceToggle:
    """Tests for toggle auto-save command."""

    def test_toggle_disables_auto_save_when_enabled(self):
        """Should disable auto-save when currently enabled."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        result = persistence.manage_session(
            args="toggle",
            auto_save=True,
            io=io
        )

        assert result['auto_save'] is False
        output = io.get_output()
        assert "OFF" in output

    def test_toggle_enables_auto_save_when_disabled(self):
        """Should enable auto-save when currently disabled."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        result = persistence.manage_session(
            args="toggle",
            auto_save=False,
            io=io
        )

        assert result['auto_save'] is True
        output = io.get_output()
        assert "ON" in output

    def test_toggle_shows_behavior_explanation(self):
        """Should explain auto-save behavior after toggle."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(
            args="toggle",
            auto_save=False,
            io=io
        )

        output = io.get_output()
        assert "quit" in output.lower() or "exit" in output.lower()


class TestPersistenceInvalidCommand:
    """Tests for invalid/unknown commands."""

    def test_invalid_command_shows_usage(self):
        """Should display usage information for unknown commands."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(args="invalid", io=io)

        output = io.get_output()
        assert "Usage:" in output
        assert "save" in output
        assert "load" in output
        assert "clear" in output
        assert "toggle" in output

    def test_usage_shows_auto_save_status(self):
        """Should show current auto-save status in usage."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        persistence.manage_session(
            args="help",
            auto_save=True,
            io=io
        )

        output = io.get_output()
        assert "Auto-save:" in output


class TestPersistenceReturnValues:
    """Tests for return value handling."""

    def test_returns_dict_with_conversation_history(self):
        """Should always return dict with conversation_history key."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        conversation = [{'role': 'user', 'content': 'test'}]
        result = persistence.manage_session(
            args="",
            conversation_history=conversation,
            io=io
        )

        assert 'conversation_history' in result
        assert result['conversation_history'] == conversation

    def test_returns_dict_with_auto_save(self):
        """Should always return dict with auto_save key."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        result = persistence.manage_session(
            args="",
            auto_save=True,
            io=io
        )

        assert 'auto_save' in result
        assert result['auto_save'] is True

    def test_preserves_original_values_when_not_modified(self):
        """Should preserve original values when command doesn't modify them."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        conversation = [{'role': 'user', 'content': 'test'}]
        result = persistence.manage_session(
            args="",  # Show info doesn't modify
            conversation_history=conversation,
            auto_save=True,
            io=io
        )

        assert result['conversation_history'] == conversation
        assert result['auto_save'] is True


class TestPersistenceCaseInsensitivity:
    """Tests for command case handling."""

    def test_commands_are_case_insensitive(self):
        """Commands should work regardless of case."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)

        for cmd in ["SAVE", "Save", "save", "SaVe"]:
            io = MockIO()
            persistence.manage_session(
                args=cmd,
                conversation_history=[],
                io=io
            )
            output = io.get_output()
            # Should not show usage
            assert "Usage:" not in output


class TestPersistenceDefaultParameters:
    """Tests for default parameter handling."""

    def test_handles_none_conversation_history(self):
        """Should handle None conversation_history gracefully."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        # Should not raise error
        result = persistence.manage_session(
            args="",
            conversation_history=None,
            io=io
        )

        assert 'conversation_history' in result

    def test_handles_default_auto_save(self):
        """Should use default auto_save value when not specified."""
        from src.cli.persistence import SessionPersistence

        orchestrator = ConfigurableTestOrchestrator()
        persistence = SessionPersistence(orchestrator)
        io = MockIO()

        result = persistence.manage_session(args="", io=io)

        # Should have auto_save in result with default value
        assert 'auto_save' in result
