"""
Tests for session display utilities.

Tests the shared session utilities that eliminate duplication
across CLI modules for session restoration, save, and detection display.
"""

import pytest
from tests.helpers import MockIO


class TestDisplaySessionRestored:
    """Test display_session_restored function."""

    def test_displays_basic_restoration_stats(self):
        """Should display all restored counts when session is loaded."""
        from src.cli.utils.session_utils import display_session_restored

        io = MockIO()
        result = {
            'status': 'loaded',
            'saved_at': '2024-01-15 10:30:00',
            'files_restored': 5,
            'searches_restored': 3,
            'git_ops_restored': 2,
            'discoveries_restored': 4,
            'tasks_restored': 7,
            'conversation_history': []
        }

        display_session_restored(io, result)
        output = io.get_output()

        assert '2024-01-15 10:30:00' in output
        assert 'Files restored: 5' in output
        assert 'Searches restored: 3' in output
        assert 'Git ops restored: 2' in output
        assert 'Discoveries restored: 4' in output
        assert 'Task history: 7' in output

    def test_displays_conversation_count(self):
        """Should display conversation message count when conversation exists."""
        from src.cli.utils.session_utils import display_session_restored

        io = MockIO()
        result = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 0,
            'searches_restored': 0,
            'git_ops_restored': 0,
            'discoveries_restored': 0,
            'tasks_restored': 0,
            'conversation_history': [
                {'role': 'user', 'content': 'Hello'},
                {'role': 'assistant', 'content': 'Hi there'},
                {'role': 'user', 'content': 'How are you?'}
            ]
        }

        display_session_restored(io, result)
        output = io.get_output()

        assert 'Conversation: 3 messages restored' in output

    def test_displays_last_conversation_messages(self):
        """Should display last few conversation messages."""
        from src.cli.utils.session_utils import display_session_restored

        io = MockIO()
        conversation = [
            {'role': 'user', 'content': 'First message'},
            {'role': 'assistant', 'content': 'First response'},
            {'role': 'user', 'content': 'Second message'},
            {'role': 'assistant', 'content': 'Second response'},
            {'role': 'user', 'content': 'Third message'},
            {'role': 'assistant', 'content': 'Third response'}
        ]
        result = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 0,
            'searches_restored': 0,
            'git_ops_restored': 0,
            'discoveries_restored': 0,
            'tasks_restored': 0,
            'conversation_history': conversation
        }

        display_session_restored(io, result)
        output = io.get_output()

        # Should show last 4 messages by default
        assert 'Second message' in output
        assert 'Second response' in output
        assert 'Third message' in output
        assert 'Third response' in output
        # First messages should not appear
        assert 'First message' not in output

    def test_truncates_long_messages(self):
        """Should truncate messages longer than 100 characters."""
        from src.cli.utils.session_utils import display_session_restored

        io = MockIO()
        long_message = 'A' * 150  # 150 character message
        result = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 0,
            'searches_restored': 0,
            'git_ops_restored': 0,
            'discoveries_restored': 0,
            'tasks_restored': 0,
            'conversation_history': [
                {'role': 'user', 'content': long_message}
            ]
        }

        display_session_restored(io, result)
        output = io.get_output()

        # Should show truncated message with ellipsis
        assert 'A' * 100 in output
        assert '...' in output
        # Full message should not appear
        assert long_message not in output

    def test_handles_empty_conversation(self):
        """Should not display conversation section when no conversation."""
        from src.cli.utils.session_utils import display_session_restored

        io = MockIO()
        result = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 5,
            'searches_restored': 3,
            'git_ops_restored': 2,
            'discoveries_restored': 4,
            'tasks_restored': 7,
            'conversation_history': []
        }

        display_session_restored(io, result)
        output = io.get_output()

        # Should not show conversation section
        assert 'Conversation:' not in output
        assert 'Last conversation' not in output

    def test_uses_green_styling_for_success(self):
        """Should use green color for success message."""
        from src.cli.utils.session_utils import display_session_restored

        io = MockIO()
        result = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 0,
            'searches_restored': 0,
            'git_ops_restored': 0,
            'discoveries_restored': 0,
            'tasks_restored': 0,
            'conversation_history': []
        }

        display_session_restored(io, result)
        styled = io.get_styled_outputs()

        # First styled output should be green success message
        assert any(s['fg'] == 'green' for s in styled)

    def test_handles_missing_conversation_key(self):
        """Should handle result without conversation_history key."""
        from src.cli.utils.session_utils import display_session_restored

        io = MockIO()
        result = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 5,
            'searches_restored': 3,
            'git_ops_restored': 2,
            'discoveries_restored': 4,
            'tasks_restored': 7
            # No conversation_history key
        }

        # Should not raise
        display_session_restored(io, result)
        output = io.get_output()

        assert '2024-01-15' in output
        assert 'Conversation:' not in output

    def test_returns_conversation_for_assignment(self):
        """Should return conversation history for external assignment."""
        from src.cli.utils.session_utils import display_session_restored

        io = MockIO()
        conversation = [
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi'}
        ]
        result = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 0,
            'searches_restored': 0,
            'git_ops_restored': 0,
            'discoveries_restored': 0,
            'tasks_restored': 0,
            'conversation_history': conversation
        }

        returned_conversation = display_session_restored(io, result)

        assert returned_conversation == conversation


class TestDisplaySessionLoadError:
    """Test display_session_load_error function."""

    def test_displays_no_session_message(self):
        """Should display appropriate message when no session exists."""
        from src.cli.utils.session_utils import display_session_load_error

        io = MockIO()
        result = {'status': 'no_session'}

        display_session_load_error(io, result)
        output = io.get_output()

        assert 'No previous session found' in output or 'No saved session' in output

    def test_uses_yellow_for_no_session(self):
        """Should use yellow color for no session warning."""
        from src.cli.utils.session_utils import display_session_load_error

        io = MockIO()
        result = {'status': 'no_session'}

        display_session_load_error(io, result)
        styled = io.get_styled_outputs()

        assert any(s['fg'] == 'yellow' for s in styled)

    def test_displays_error_message(self):
        """Should display error message for other failures."""
        from src.cli.utils.session_utils import display_session_load_error

        io = MockIO()
        result = {
            'status': 'error',
            'message': 'File corrupted'
        }

        display_session_load_error(io, result)
        output = io.get_output()

        assert 'File corrupted' in output

    def test_uses_red_for_error(self):
        """Should use red color for error message."""
        from src.cli.utils.session_utils import display_session_load_error

        io = MockIO()
        result = {
            'status': 'error',
            'message': 'Something went wrong'
        }

        display_session_load_error(io, result)
        styled = io.get_styled_outputs()

        assert any(s['fg'] == 'red' for s in styled)

    def test_handles_missing_error_message(self):
        """Should display 'unknown' when error message is missing."""
        from src.cli.utils.session_utils import display_session_load_error

        io = MockIO()
        result = {'status': 'error'}

        display_session_load_error(io, result)
        output = io.get_output()

        assert 'unknown' in output.lower()


class TestDisplaySessionSaved:
    """Test display_session_saved function."""

    def test_displays_save_path(self):
        """Should display the path where session was saved."""
        from src.cli.utils.session_utils import display_session_saved

        io = MockIO()

        display_session_saved(io, '/path/to/session.json', 5)
        output = io.get_output()

        assert '/path/to/session.json' in output

    def test_displays_conversation_count(self):
        """Should display number of conversation messages saved."""
        from src.cli.utils.session_utils import display_session_saved

        io = MockIO()

        display_session_saved(io, '/path/session.json', 10)
        output = io.get_output()

        assert '10' in output
        assert 'message' in output.lower()

    def test_displays_resume_help_when_requested(self):
        """Should display resume help text when with_help=True."""
        from src.cli.utils.session_utils import display_session_saved

        io = MockIO()

        display_session_saved(io, '/path/session.json', 5, with_help=True)
        output = io.get_output()

        assert '--resume' in output

    def test_no_help_by_default(self):
        """Should not display help text by default."""
        from src.cli.utils.session_utils import display_session_saved

        io = MockIO()

        display_session_saved(io, '/path/session.json', 5)
        output = io.get_output()

        assert '--resume' not in output

    def test_uses_green_for_success(self):
        """Should use green color for success message."""
        from src.cli.utils.session_utils import display_session_saved

        io = MockIO()

        display_session_saved(io, '/path/session.json', 5)
        styled = io.get_styled_outputs()

        assert any(s['fg'] == 'green' for s in styled)


class TestDisplaySessionSaveError:
    """Test display_session_save_error function."""

    def test_displays_error_message(self):
        """Should display the error that occurred during save."""
        from src.cli.utils.session_utils import display_session_save_error

        io = MockIO()
        error = Exception("Permission denied")

        display_session_save_error(io, error)
        output = io.get_output()

        assert 'Permission denied' in output

    def test_uses_yellow_for_warning(self):
        """Should use yellow color for save warning."""
        from src.cli.utils.session_utils import display_session_save_error

        io = MockIO()
        error = Exception("Disk full")

        display_session_save_error(io, error)
        styled = io.get_styled_outputs()

        assert any(s['fg'] == 'yellow' for s in styled)


class TestDisplayPreviousSessionDetected:
    """Test display_previous_session_detected function."""

    def test_displays_session_info(self):
        """Should display all session metadata."""
        from src.cli.utils.session_utils import display_previous_session_detected

        io = MockIO()
        session_info = {
            'saved_at': '2024-01-15 14:30:00',
            'file_count': 10,
            'search_count': 5,
            'discovery_count': 3,
            'task_count': 8
        }

        display_previous_session_detected(io, session_info)
        output = io.get_output()

        assert '2024-01-15 14:30:00' in output
        assert '10' in output  # file_count
        assert '5' in output   # search_count
        assert '3' in output   # discovery_count
        assert '8' in output   # task_count

    def test_displays_conversation_indicator_when_present(self):
        """Should show conversation indicator when has_conversation is True."""
        from src.cli.utils.session_utils import display_previous_session_detected

        io = MockIO()
        session_info = {
            'saved_at': '2024-01-15',
            'file_count': 0,
            'search_count': 0,
            'discovery_count': 0,
            'task_count': 0,
            'has_conversation': True
        }

        display_previous_session_detected(io, session_info)
        output = io.get_output()

        assert 'conversation' in output.lower()
        assert 'Yes' in output

    def test_no_conversation_indicator_when_absent(self):
        """Should not show conversation indicator when has_conversation is False."""
        from src.cli.utils.session_utils import display_previous_session_detected

        io = MockIO()
        session_info = {
            'saved_at': '2024-01-15',
            'file_count': 0,
            'search_count': 0,
            'discovery_count': 0,
            'task_count': 0,
            'has_conversation': False
        }

        display_previous_session_detected(io, session_info)
        output = io.get_output()

        # Should not show "Yes" for conversation
        lines = output.split('\n')
        conversation_lines = [l for l in lines if 'conversation' in l.lower()]
        for line in conversation_lines:
            assert 'Yes' not in line

    def test_uses_yellow_bold_header(self):
        """Should use yellow bold styling for detection header."""
        from src.cli.utils.session_utils import display_previous_session_detected

        io = MockIO()
        session_info = {
            'saved_at': '2024-01-15',
            'file_count': 0,
            'search_count': 0,
            'discovery_count': 0,
            'task_count': 0
        }

        display_previous_session_detected(io, session_info)
        styled = io.get_styled_outputs()

        # First styled output should be yellow and bold
        assert styled[0]['fg'] == 'yellow'
        assert styled[0]['bold'] is True

    def test_handles_unknown_saved_at(self):
        """Should display 'unknown' when saved_at is missing."""
        from src.cli.utils.session_utils import display_previous_session_detected

        io = MockIO()
        session_info = {
            'file_count': 0,
            'search_count': 0,
            'discovery_count': 0,
            'task_count': 0
        }

        display_previous_session_detected(io, session_info)
        output = io.get_output()

        assert 'unknown' in output.lower()


class TestDisplayLastConversationMessages:
    """Test display_last_conversation_messages function."""

    def test_displays_user_messages_with_you_prefix(self):
        """Should prefix user messages with 'You:'."""
        from src.cli.utils.session_utils import display_last_conversation_messages

        io = MockIO()
        conversation = [
            {'role': 'user', 'content': 'Hello there'}
        ]

        display_last_conversation_messages(io, conversation)
        output = io.get_output()

        assert 'You:' in output
        assert 'Hello there' in output

    def test_displays_assistant_messages_with_assistant_prefix(self):
        """Should prefix assistant messages with 'Assistant:'."""
        from src.cli.utils.session_utils import display_last_conversation_messages

        io = MockIO()
        conversation = [
            {'role': 'assistant', 'content': 'How can I help?'}
        ]

        display_last_conversation_messages(io, conversation)
        output = io.get_output()

        assert 'Assistant:' in output
        assert 'How can I help?' in output

    def test_limits_to_max_messages(self):
        """Should only display last N messages."""
        from src.cli.utils.session_utils import display_last_conversation_messages

        io = MockIO()
        conversation = [
            {'role': 'user', 'content': f'Message {i}'} for i in range(10)
        ]

        display_last_conversation_messages(io, conversation, max_messages=3)
        output = io.get_output()

        # Should only have last 3 messages
        assert 'Message 7' in output
        assert 'Message 8' in output
        assert 'Message 9' in output
        assert 'Message 0' not in output
        assert 'Message 6' not in output

    def test_truncates_at_specified_length(self):
        """Should truncate messages at specified character limit."""
        from src.cli.utils.session_utils import display_last_conversation_messages

        io = MockIO()
        long_message = 'X' * 200
        conversation = [
            {'role': 'user', 'content': long_message}
        ]

        display_last_conversation_messages(io, conversation, truncate_at=50)
        output = io.get_output()

        # Should have truncated message with ellipsis
        assert 'X' * 50 in output
        assert '...' in output
        # Full message should not appear
        assert long_message not in output

    def test_shows_header_by_default(self):
        """Should display 'Last conversation:' header."""
        from src.cli.utils.session_utils import display_last_conversation_messages

        io = MockIO()
        conversation = [
            {'role': 'user', 'content': 'Hello'}
        ]

        display_last_conversation_messages(io, conversation)
        output = io.get_output()

        assert 'Last conversation' in output

    def test_uses_cyan_for_header(self):
        """Should use cyan color for header."""
        from src.cli.utils.session_utils import display_last_conversation_messages

        io = MockIO()
        conversation = [
            {'role': 'user', 'content': 'Hello'}
        ]

        display_last_conversation_messages(io, conversation)
        styled = io.get_styled_outputs()

        assert any(s['fg'] == 'cyan' for s in styled)


    def test_handles_missing_role(self):
        """Should handle messages with missing role key."""
        from src.cli.utils.session_utils import display_last_conversation_messages

        io = MockIO()
        conversation = [
            {'content': 'No role here'}
        ]

        # Should not raise
        display_last_conversation_messages(io, conversation)
        output = io.get_output()

        assert 'No role here' in output

    def test_handles_missing_content(self):
        """Should handle messages with missing content key."""
        from src.cli.utils.session_utils import display_last_conversation_messages

        io = MockIO()
        conversation = [
            {'role': 'user'}
        ]

        # Should not raise
        display_last_conversation_messages(io, conversation)


class TestDisplaySessionNotSavedWarning:
    """Test display_session_not_saved_warning function."""

    def test_displays_not_saved_message(self):
        """Should display message that session was not saved."""
        from src.cli.utils.session_utils import display_session_not_saved_warning

        io = MockIO()

        display_session_not_saved_warning(io)
        output = io.get_output()

        assert 'not saved' in output.lower() or 'auto-save disabled' in output.lower()

    def test_displays_manual_save_hint(self):
        """Should hint about manual save option."""
        from src.cli.utils.session_utils import display_session_not_saved_warning

        io = MockIO()

        display_session_not_saved_warning(io)
        output = io.get_output()

        assert '/session save' in output

    def test_uses_yellow_for_warning(self):
        """Should use yellow color for warning."""
        from src.cli.utils.session_utils import display_session_not_saved_warning

        io = MockIO()

        display_session_not_saved_warning(io)
        styled = io.get_styled_outputs()

        assert any(s['fg'] == 'yellow' for s in styled)


class TestIntegration:
    """Integration tests for combined session display utilities."""

    def test_full_session_restore_flow(self):
        """Test complete session restoration display flow."""
        from src.cli.utils.session_utils import (
            display_session_restored,
            display_session_load_error
        )

        io = MockIO()

        # Test successful load
        result = {
            'status': 'loaded',
            'saved_at': '2024-01-15 10:00:00',
            'files_restored': 3,
            'searches_restored': 2,
            'git_ops_restored': 1,
            'discoveries_restored': 4,
            'tasks_restored': 5,
            'conversation_history': [
                {'role': 'user', 'content': 'Previous question'},
                {'role': 'assistant', 'content': 'Previous answer'}
            ]
        }

        conversation = display_session_restored(io, result)
        output = io.get_output()

        # Verify all information displayed
        assert '2024-01-15' in output
        assert 'Files restored: 3' in output
        assert 'Conversation: 2 messages' in output
        assert 'Previous question' in output
        assert conversation == result['conversation_history']

    def test_handles_all_error_states(self):
        """Test that all error states are handled correctly."""
        from src.cli.utils.session_utils import display_session_load_error

        # No session
        io = MockIO()
        display_session_load_error(io, {'status': 'no_session'})
        assert 'No' in io.get_output()

        # Error with message
        io = MockIO()
        display_session_load_error(io, {'status': 'error', 'message': 'Test error'})
        assert 'Test error' in io.get_output()

        # Error without message
        io = MockIO()
        display_session_load_error(io, {'status': 'error'})
        assert 'unknown' in io.get_output().lower()
