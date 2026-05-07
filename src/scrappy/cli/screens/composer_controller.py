"""Shared composer state and cursor policy for TUI chat surfaces."""

from __future__ import annotations

import logging
from typing import Protocol

from textual.widgets import TextArea

from ..input_capture import InputRequest

logger = logging.getLogger(__name__)


class ClipboardTextSourceProtocol(Protocol):
    """Clipboard surface needed by the composer."""

    def paste_text(self) -> str:
        """Return text from the OS clipboard."""
        ...


class ComposerControllerProtocol(Protocol):
    """Shared contract for composer text, focus, paste, and cursor movement."""

    @property
    def text(self) -> str:
        """Return the current composer text."""
        ...

    @text.setter
    def text(self, value: str) -> None:
        """Replace the current composer text."""
        ...

    @property
    def has_focus(self) -> bool:
        """Return whether the composer has keyboard focus."""
        ...

    def clear(self) -> str:
        """Clear the composer and return its previous text."""
        ...

    def focus(self) -> None:
        """Focus the composer."""
        ...

    def set_placeholder(self, text: str) -> None:
        """Set the composer placeholder."""
        ...

    def restore_default_placeholder(self) -> None:
        """Restore the surface's default placeholder."""
        ...

    def paste_from_clipboard(self, clipboard: ClipboardTextSourceProtocol) -> bool:
        """Paste clipboard text into the composer."""
        ...

    def move_up_before_history(self) -> bool:
        """Move the cursor up if it is not on the first line."""
        ...

    def move_down_before_history(self) -> bool:
        """Move the cursor down if it is not on the last line."""
        ...

    def prepare_capture(self, request: InputRequest) -> None:
        """Apply capture-specific composer prompt text."""
        ...


class ComposerController(ComposerControllerProtocol):
    """Own shared TextArea behavior that must be consistent across screens."""

    def __init__(self, widget: TextArea, default_placeholder: str = "") -> None:
        self._widget = widget
        self._default_placeholder = default_placeholder
        if default_placeholder:
            self._widget.placeholder = default_placeholder

    @property
    def text(self) -> str:
        """Return the current composer text."""
        return self._widget.text

    @text.setter
    def text(self, value: str) -> None:
        """Replace the current composer text."""
        self._widget.text = value

    @property
    def has_focus(self) -> bool:
        """Return whether the composer has keyboard focus."""
        return self._widget.has_focus

    def clear(self) -> str:
        """Clear the composer and return its previous text."""
        text = self._widget.text
        self._widget.clear()
        return text

    def focus(self) -> None:
        """Focus the composer."""
        self._widget.focus()

    def set_placeholder(self, text: str) -> None:
        """Set the composer placeholder."""
        self._widget.placeholder = text

    def restore_default_placeholder(self) -> None:
        """Restore the surface's default placeholder."""
        self._widget.placeholder = self._default_placeholder

    def paste_from_clipboard(self, clipboard: ClipboardTextSourceProtocol) -> bool:
        """Paste clipboard text into the composer."""
        try:
            text = clipboard.paste_text()
        except Exception as exc:
            logger.warning("Failed to paste from clipboard: %s", exc)
            return False

        if not text:
            return False

        self._widget.replace(
            text,
            self._widget.selection.start,
            self._widget.selection.end,
            maintain_selection_offset=True,
        )
        return True

    def move_up_before_history(self) -> bool:
        """Move the cursor up if it is not on the first line."""
        row, _ = self._widget.cursor_location
        if row <= 0:
            return False
        self._widget.action_cursor_up()
        return True

    def move_down_before_history(self) -> bool:
        """Move the cursor down if it is not on the last line."""
        row, _ = self._widget.cursor_location
        if row >= self._widget.document.line_count - 1:
            return False
        self._widget.action_cursor_down()
        return True

    def prepare_capture(self, request: InputRequest) -> None:
        """Apply capture-specific composer prompt text."""
        if request.input_type == "confirm":
            self.set_placeholder("Type y or n...")
        elif request.input_type == "confirm_yna":
            self.set_placeholder("Type y, n, or a (allow all)...")
        elif request.input_type == "checkpoint":
            self.set_placeholder("Type c, g, a, or s...")
        else:
            hint = f" (default: {request.default})" if request.default else ""
            self.set_placeholder(f"Enter value{hint}...")
