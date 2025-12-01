"""Setup wizard screen for Scrappy TUI."""

from typing import TYPE_CHECKING, Optional, Callable, Any
import logging

from textual.screen import Screen
from textual.app import ComposeResult
from textual.binding import Binding

from .chat_layout import ChatLayout

if TYPE_CHECKING:
    from ..unified_io import UnifiedIO

logger = logging.getLogger(__name__)


class WizardOutputSink:
    """Output sink that writes directly to the wizard's ChatLayout.

    Implements the same interface as TextualOutputAdapter so SetupWizard
    can output via io.output_sink pattern, but writes go directly to
    the screen's RichLog instead of the app's message queue.
    """

    def __init__(self, layout: ChatLayout) -> None:
        self._layout = layout

    def clear_output(self) -> None:
        """Clear the output area."""
        self._layout.clear_output()

    def post_output(self, content: str) -> None:
        """Write plain text to output."""
        self._layout.write(content)

    def post_renderable(self, obj: Any) -> None:
        """Write Rich renderable to output."""
        self._layout.write(obj)


class SetupWizardScreen(Screen):
    """Provider setup wizard screen.

    Full-screen replacement that handles API key configuration.
    Uses ChatLayout for consistent UI and direct output writing.
    """

    BINDINGS = [
        Binding("enter", "submit_input", "Submit", priority=True),
    ]

    def __init__(
        self,
        io: "UnifiedIO",
        allow_cancel: bool = True,
        on_complete: Optional[Callable[[bool], None]] = None,
    ):
        """Initialize wizard screen.

        Args:
            io: UnifiedIO for output routing
            allow_cancel: If False, user must configure at least one provider
            on_complete: Callback when wizard completes (receives has_provider bool)
        """
        super().__init__()
        self._io = io
        self._allow_cancel = allow_cancel
        self._on_complete = on_complete

        # Wizard business logic (created on mount)
        self._wizard = None

        # Layout component
        self._layout: Optional[ChatLayout] = None

        # Store original output sink to restore on unmount
        self._original_output_sink = None

    def compose(self) -> ComposeResult:
        """Create wizard UI using ChatLayout."""
        yield ChatLayout(
            show_status_bar=False,
            input_placeholder="Select provider (1-5 or q)",
            id="chat_layout"
        )

    def on_mount(self) -> None:
        """Called when screen is mounted - start the wizard."""
        from ..setup_wizard import SetupWizard

        # Get layout and focus input
        self._layout = self.query_one(ChatLayout)
        self._layout.focus_input()

        # Swap output sink to write directly to our layout
        self._original_output_sink = self._io._output_sink
        self._io._output_sink = WizardOutputSink(self._layout)

        # Create and start wizard
        self._wizard = SetupWizard(self._io)
        self._wizard.start(
            allow_cancel=self._allow_cancel,
            on_complete=self._handle_wizard_complete
        )

        # Update placeholder with current prompt
        self._update_placeholder()

    def on_unmount(self) -> None:
        """Restore original output sink on unmount."""
        if self._original_output_sink is not None:
            self._io._output_sink = self._original_output_sink

    def _handle_wizard_complete(self, has_provider: bool) -> None:
        """Handle wizard completion."""
        if self._on_complete:
            self._on_complete(has_provider)
        self.app.pop_screen()

    def on_click(self, event) -> None:
        """Handle clicks - right-click to paste, otherwise refocus input."""
        if self._layout is None:
            return

        # Right-click (button=3) pastes from clipboard
        if hasattr(event, 'button') and event.button == 3:
            try:
                import pyperclip
                text = pyperclip.paste()
                if text:
                    self._layout.input.replace(
                        text,
                        self._layout.input.selection.start,
                        self._layout.input.selection.end,
                        maintain_selection_offset=True
                    )
            except Exception:
                pass
            return

        self._layout.focus_input()

    def action_submit_input(self) -> None:
        """Handle Enter to submit input to wizard."""
        if self._wizard is None or self._layout is None:
            return

        # Get and clear input
        user_input = self._layout.clear_input().strip()

        # Track state before handling input
        from ..setup_wizard import WizardState
        state_before = self._wizard._state

        # Pass to wizard state machine
        self._wizard.handle_input(user_input)

        # If we transitioned back to MENU, clear and re-show fresh menu
        state_after = self._wizard._state
        if state_after == WizardState.MENU and state_before != WizardState.MENU:
            output_sink = self._io._output_sink
            if isinstance(output_sink, WizardOutputSink):
                output_sink.clear_output()
            self._wizard._show_menu()

        # Update placeholder for next prompt
        self._update_placeholder()

    def _update_placeholder(self) -> None:
        """Update input placeholder based on wizard state."""
        if self._wizard is None or not self._wizard.is_active:
            return

        prompt = self._wizard.current_prompt
        if prompt and self._layout:
            self._layout.input.placeholder = prompt
