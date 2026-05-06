"""Setup wizard screen for Scrappy TUI."""

from contextlib import nullcontext
from typing import TYPE_CHECKING, Optional, Callable, Any
import logging

from textual.screen import Screen
from textual.app import ComposeResult
from textual.binding import Binding

from .chat_surface import (
    AppendTranscript,
    ChatSurface,
    ChatSurfaceConfig,
    ClearTranscript,
    SubmitResult,
)
from scrappy.cli.protocols import ClipboardProtocol
from scrappy.cli.textual.tui_events import TuiEventTarget
from scrappy.orchestrator.protocols import KeyValidatorProtocol

if TYPE_CHECKING:
    from ..setup_wizard import SetupWizard
    from ..unified_io import UnifiedIO

logger = logging.getLogger(__name__)


class SetupWizardScreen(Screen):
    """Provider setup wizard screen.

    Full-screen replacement that handles API key configuration.
    Uses ChatSurface for consistent UI and direct output writing.
    """

    BINDINGS = [
        Binding("enter", "submit_input", "Submit", priority=True),
    ]

    def __init__(
        self,
        io: "UnifiedIO",
        key_validator: KeyValidatorProtocol,
        clipboard: ClipboardProtocol,
        allow_cancel: bool = True,
        on_complete: Optional[Callable[[bool], None]] = None,
    ):
        """Initialize wizard screen.

        Args:
            io: UnifiedIO for output routing
            key_validator: Lightweight key validator for testing API keys
            clipboard: Clipboard service for OS clipboard integration
            allow_cancel: If False, user must configure at least one provider
            on_complete: Callback when wizard completes (receives has_provider bool)
        """
        super().__init__()
        self._io = io
        self._key_validator = key_validator
        self._clipboard = clipboard
        self._allow_cancel = allow_cancel
        self._on_complete = on_complete

        # Wizard business logic (created on mount)
        self._wizard: Optional["SetupWizard"] = None

        # Shared chat surface
        self._surface: Optional[ChatSurface] = None

    def compose(self) -> ComposeResult:
        """Create wizard UI using ChatSurface."""
        yield ChatSurface(
            config=ChatSurfaceConfig(
                show_status_bar=False,
                input_placeholder="Select provider (1-5 or q)",
            ),
            id="chat_surface"
        )

    def on_mount(self) -> None:
        """Called when screen is mounted - start the wizard."""
        from ..setup_wizard import SetupWizard

        # Get surface and focus input
        self._surface = self.query_one(ChatSurface)
        self._surface.focus_input()

        # Create and start wizard
        self._wizard = SetupWizard(self._io, self._key_validator)
        with self._wizard_output_context():
            self._wizard.start(
                allow_cancel=self._allow_cancel,
                on_complete=self._handle_wizard_complete
            )

        # Update placeholder with current prompt
        self._update_placeholder()

    def _handle_wizard_complete(self, has_provider: bool) -> None:
        """Handle wizard completion."""
        if self._on_complete:
            self._on_complete(has_provider)
        self.app.pop_screen()

    def on_click(self, event) -> None:
        """Handle clicks - right-click to paste, otherwise refocus input."""
        if self._surface is None:
            return
        self._surface.handle_click(event, self._clipboard)

    def action_submit_input(self) -> None:
        """Handle Enter to submit input to wizard."""
        if self._wizard is None or self._surface is None:
            return

        result = self._surface.submit(self)
        self._apply_submit_follow_up_actions(result)

        # Update placeholder for next prompt
        self._update_placeholder()

    def handle_submit(self, user_input: str) -> SubmitResult:
        """Handle wizard input behind the shared surface protocol."""
        if self._wizard is None:
            return SubmitResult(accepted=False)

        # Track state before handling input
        from ..setup_wizard import WizardState
        state_before = self._wizard._state

        # Pass to wizard state machine
        with self._wizard_output_context():
            self._wizard.handle_input(user_input)

        # If we transitioned to MENU from AWAITING_KEY, clear and re-show fresh menu
        # (DISCLAIMER -> MENU transition already shows menu, don't clear it)
        state_after = self._wizard._state
        if state_after == WizardState.MENU and state_before in {
            WizardState.AWAITING_KEY,
            WizardState.CONFIRM_REMOVE,
        }:
            return SubmitResult(
                accepted=True,
                follow_up_actions=(
                    ClearTranscript(target=TuiEventTarget.WIZARD_TRANSCRIPT),
                    AppendTranscript(
                        entries=self._wizard.menu_renderables(),
                        target=TuiEventTarget.WIZARD_TRANSCRIPT,
                    ),
                ),
            )

        return SubmitResult(accepted=True)

    def _apply_submit_follow_up_actions(self, result: SubmitResult) -> None:
        """Apply wizard submit follow-up actions."""
        if self._surface is None:
            return
        self._surface.apply_follow_up_actions(result.follow_up_actions)

    def _update_placeholder(self) -> None:
        """Update input placeholder based on wizard state."""
        if self._wizard is None or not self._wizard.is_active:
            return

        prompt = self._wizard.current_prompt
        if prompt and self._surface:
            self._surface.input.placeholder = prompt

    def write_output(self, content: str) -> None:
        """Write plain text to the wizard transcript."""
        if self._surface is not None:
            self._surface.write(content)

    def write_renderable(self, renderable: Any) -> None:
        """Write a Rich renderable to the wizard transcript."""
        if self._surface is not None:
            self._surface.write(renderable)

    def clear_output(self) -> None:
        """Clear the wizard transcript."""
        if self._surface is not None:
            self._surface.clear_output()

    def _wizard_output_context(self):
        """Route wizard business output to the wizard transcript target."""
        sink = self._io.output_sink
        transcript_target = getattr(sink, "transcript_target", None)
        if callable(transcript_target):
            return transcript_target(TuiEventTarget.WIZARD_TRANSCRIPT)
        return nullcontext()

    # Note: ctrl+q and escape are handled at app level (ScrappyApp.on_key)
