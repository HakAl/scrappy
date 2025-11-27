"""Tests for PromptDisplay status bar component."""

import pytest
from textual.widgets import Label


class TestPromptDisplay:
    """Tests for PromptDisplay component."""

    def test_component_id_is_prompt_display(self):
        """component_id returns 'prompt_display'."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        assert prompt.component_id == "prompt_display"

    def test_not_visible_by_default(self):
        """is_visible returns False when no message set."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        assert prompt.is_visible is False

    def test_show_prompt_makes_visible(self):
        """show_prompt() makes component visible."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        prompt.show_prompt("Enter your name:")
        assert prompt.is_visible is True

    def test_hide_prompt_makes_invisible(self):
        """hide_prompt() makes component invisible."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        prompt.show_prompt("Enter your name:")
        prompt.hide_prompt()
        assert prompt.is_visible is False

    def test_format_prompt_basic_message(self):
        """_format_prompt returns message for text input."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        prompt.show_prompt("Enter your name:")
        assert prompt._format_prompt() == "Enter your name:"

    def test_format_prompt_confirm_adds_yn_hint(self):
        """_format_prompt adds [y/n] for confirm type."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        prompt.show_prompt("Continue?", input_type="confirm")
        assert prompt._format_prompt() == "Continue? [y/n]"

    def test_format_prompt_with_default_value(self):
        """_format_prompt includes default hint when provided."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        prompt.show_prompt("Enter port:", default="8080")
        assert prompt._format_prompt() == "Enter port: (default: 8080)"

    def test_format_prompt_confirm_with_default(self):
        """_format_prompt shows both [y/n] and default for confirm."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        prompt.show_prompt("Overwrite?", input_type="confirm", default="n")
        assert prompt._format_prompt() == "Overwrite? [y/n] (default: n)"

    def test_widget_returns_label(self):
        """widget property returns a Label widget."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        assert isinstance(prompt.widget, Label)

    def test_widget_has_correct_id(self):
        """widget has id matching component_id."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        assert prompt.widget.id == "prompt_display"

    def test_widget_is_cached(self):
        """widget property returns same instance on repeated calls."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        widget1 = prompt.widget
        widget2 = prompt.widget
        assert widget1 is widget2

    def test_empty_message_not_visible(self):
        """Empty message string is not visible."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        prompt.show_prompt("")
        assert prompt.is_visible is False

    def test_hide_clears_all_state(self):
        """hide_prompt clears message, input_type, and default."""
        from src.cli.textual_app import PromptDisplay

        prompt = PromptDisplay()
        prompt.show_prompt("Test?", input_type="confirm", default="y")
        prompt.hide_prompt()

        assert prompt._message == ""
        assert prompt._input_type == ""
        assert prompt._default == ""
        assert prompt._visible is False
