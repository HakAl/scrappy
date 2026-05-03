"""Clipboard implementations for the Textual TUI."""

from scrappy.cli.protocols import ClipboardProtocol


class PyperclipClipboard(ClipboardProtocol):
    """Clipboard adapter backed by the pyperclip package."""

    def copy_text(self, text: str) -> None:
        import pyperclip

        pyperclip.copy(text)

    def paste_text(self) -> str:
        import pyperclip

        clipboard_text = pyperclip.paste()
        if isinstance(clipboard_text, str):
            return clipboard_text
        return str(clipboard_text)
