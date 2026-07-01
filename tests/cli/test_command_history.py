"""Tests for CommandHistory class."""

from pathlib import Path


class TestCommandHistory:
    """Tests for CommandHistory class."""

    def test_in_memory_when_no_file_provided(self):
        """CommandHistory works without file (in-memory only)."""
        from scrappy.cli.command_history import CommandHistory

        history = CommandHistory(history_file=None)
        history.add_to_history("test")

        assert history.get_previous() == "test"

    def test_creates_directory_if_needed(self, tmp_path):
        """CommandHistory creates parent directory for history file."""
        from scrappy.cli.command_history import CommandHistory

        history_file = tmp_path / "subdir" / "history"
        history = CommandHistory(history_file=history_file)
        history.add_to_history("test")

        assert history_file.parent.exists()


class TestInMemoryCommandHistory:
    """Tests for InMemoryCommandHistory class."""

    def test_basic_functionality(self):
        """InMemoryCommandHistory stores and retrieves entries."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()
        history.add_to_history("first")
        history.add_to_history("second")

        assert history.get_previous() == "second"
        assert history.get_previous() == "first"


class TestGetDefaultHistoryPath:
    """Tests for get_default_history_path function."""

    def test_returns_path_in_home_directory(self):
        """get_default_history_path returns path under ~/.scrappy/."""
        from scrappy.cli.command_history import get_default_history_path

        path = get_default_history_path()

        assert isinstance(path, Path)
        assert ".scrappy" in str(path)
        assert "command_history" in str(path)

    def test_path_is_under_home(self):
        """get_default_history_path returns path under user's home."""
        from scrappy.cli.command_history import get_default_history_path

        path = get_default_history_path()
        home = Path.home()

        assert str(path).startswith(str(home))


class TestCommandHistoryAddToHistory:
    """Tests for add_to_history method."""

    def test_add_to_history_stores_command(self):
        """add_to_history stores valid command."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()
        history.add_to_history("test command")

        assert history.get_previous() == "test command"

    def test_add_to_history_strips_whitespace(self):
        """add_to_history strips whitespace from commands."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()
        history.add_to_history("  command with spaces  ")

        assert history.get_previous() == "command with spaces"

    def test_add_to_history_ignores_empty_strings(self):
        """add_to_history ignores empty strings."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()
        history.add_to_history("")
        history.add_to_history("   ")

        assert history.get_previous() is None

    def test_add_to_history_ignores_none(self):
        """add_to_history handles None gracefully."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()
        history.add_to_history(None)

        assert history.get_previous() is None

    def test_avoids_consecutive_duplicates(self):
        """add_to_history skips consecutive duplicate entries."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()
        history.add_to_history("same")
        history.add_to_history("same")
        history.add_to_history("same")

        assert history.get_previous() == "same"
        assert history.get_previous() is None  # Only one entry


class TestInputHandlerWithHistory:
    """Tests for InputHandler with command history integration."""

    def test_input_handler_accepts_history_parameter(self):
        """InputHandler accepts optional history parameter."""
        from scrappy.cli.input_handler import InputHandler
        from scrappy.cli.command_history import InMemoryCommandHistory
        from tests.helpers import MockIO

        io = MockIO()
        history = InMemoryCommandHistory()

        handler = InputHandler(io, history=history)

        assert handler._history is history

    def test_input_handler_none_history_is_valid(self):
        """InputHandler works without history (None)."""
        from scrappy.cli.input_handler import InputHandler
        from tests.helpers import MockIO

        io = MockIO()
        handler = InputHandler(io, history=None)

        assert handler._history is None


class TestHistoryNavigation:
    """Tests for history navigation methods (TUI mode)."""

    def test_get_previous_returns_none_when_empty(self):
        """get_previous returns None when history is empty."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()

        assert history.get_previous() is None

    def test_get_next_returns_none_when_empty(self):
        """get_next returns None when history is empty."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()

        assert history.get_next() is None

    def test_get_previous_navigates_history(self):
        """get_previous navigates backwards through history."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()
        history.add_to_history("first")
        history.add_to_history("second")
        history.add_to_history("third")

        assert history.get_previous() == "third"
        assert history.get_previous() == "second"
        assert history.get_previous() == "first"
        assert history.get_previous() is None  # At start

    def test_get_next_navigates_history(self):
        """get_next navigates forwards through history."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()
        history.add_to_history("first")
        history.add_to_history("second")
        history.add_to_history("third")

        # Navigate to start
        history.get_previous()  # third
        history.get_previous()  # second
        history.get_previous()  # first

        assert history.get_next() == "second"
        assert history.get_next() == "third"
        assert history.get_next() is None  # At end

    def test_reset_position_moves_to_end(self):
        """reset_position moves navigation position to end."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()
        history.add_to_history("first")
        history.add_to_history("second")

        # Navigate up
        history.get_previous()  # second
        history.get_previous()  # first

        # Reset
        history.reset_position()

        # Next get_previous should return last item
        assert history.get_previous() == "second"

    def test_add_resets_position_to_end(self):
        """Adding new entry resets position to end."""
        from scrappy.cli.command_history import InMemoryCommandHistory

        history = InMemoryCommandHistory()
        history.add_to_history("first")
        history.add_to_history("second")

        # Navigate up
        history.get_previous()  # second
        history.get_previous()  # first

        # Add new entry
        history.add_to_history("third")

        # get_previous should return new entry
        assert history.get_previous() == "third"


class TestHistoryPersistence:
    """Tests for history file persistence."""

    def test_saves_to_file(self, tmp_path):
        """History is saved to file."""
        from scrappy.cli.command_history import CommandHistory

        history_file = tmp_path / "history"
        history = CommandHistory(history_file=history_file)
        history.add_to_history("test command")

        assert history_file.exists()
        content = history_file.read_text()
        assert "test command" in content

    def test_loads_from_file(self, tmp_path):
        """History is loaded from existing file."""
        from scrappy.cli.command_history import CommandHistory

        history_file = tmp_path / "history"
        history_file.write_text("old command\nanother command")

        history = CommandHistory(history_file=history_file)

        assert history.get_previous() == "another command"
        assert history.get_previous() == "old command"

    def test_respects_max_size(self, tmp_path):
        """History respects max_size limit."""
        from scrappy.cli.command_history import CommandHistory

        history_file = tmp_path / "history"
        history = CommandHistory(history_file=history_file, max_size=3)

        for i in range(5):
            history.add_to_history(f"cmd{i}")

        # Should only have last 3
        assert history.get_previous() == "cmd4"
        assert history.get_previous() == "cmd3"
        assert history.get_previous() == "cmd2"
        assert history.get_previous() is None
