"""Input capture manager for inline prompts/confirms.

Replaces modal dialogs with inline input capture for a more natural CLI experience.
"""

from dataclasses import dataclass
from queue import Queue, Empty
from typing import Any, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from .textual_app import ThreadSafeAsyncBridge


class InputCaptureProtocol(Protocol):
    """Contract for inline input capture behavior."""

    @property
    def is_capturing(self) -> bool:
        """Whether capture mode is currently active."""
        ...

    def enter_capture_mode(
        self,
        prompt_id: str,
        message: str,
        input_type: str,
        default: str = ""
    ) -> None:
        """Enter capture mode for a pending input request."""
        ...

    def exit_capture_mode(self) -> Optional["InputRequest"]:
        """Exit capture mode and restore normal input handling.

        Returns next queued request if any.
        """
        ...

    def handle_captured_input(self, user_input: str) -> Any:
        """Process captured input and return result to bridge."""
        ...

    def cancel(self) -> None:
        """Cancel current capture (escape/ctrl+c)."""
        ...


@dataclass
class InputRequest:
    """Represents a pending input request."""

    prompt_id: str
    message: str
    input_type: str  # "prompt" or "confirm"
    default: str = ""


class InputCaptureManager:
    """Manages inline input capture state and behavior.

    Single Responsibility: Handle capture mode state transitions
    and input processing for prompts/confirms.
    """

    def __init__(self, bridge: "ThreadSafeAsyncBridge") -> None:
        """Initialize capture manager.

        Args:
            bridge: The ThreadSafeAsyncBridge to provide results to
        """
        self._bridge = bridge
        self._mode = False
        self._id: Optional[str] = None
        self._type: Optional[str] = None
        self._default: str = ""
        self._queue: Queue[InputRequest] = Queue()

    @property
    def is_capturing(self) -> bool:
        """Whether capture mode is currently active."""
        return self._mode

    @property
    def current_type(self) -> Optional[str]:
        """The type of the current capture ('prompt' or 'confirm')."""
        return self._type

    def enter_capture_mode(
        self,
        prompt_id: str,
        message: str,
        input_type: str,
        default: str = ""
    ) -> None:
        """Enter capture mode or queue if already capturing.

        Args:
            prompt_id: Unique ID for this request
            message: Message to display to user
            input_type: Either "prompt" or "confirm"
            default: Default value for prompts
        """
        request = InputRequest(prompt_id, message, input_type, default)

        if self._mode:
            # Queue concurrent request
            self._queue.put(request)
            return

        self._mode = True
        self._id = prompt_id
        self._type = input_type
        self._default = default

    def exit_capture_mode(self) -> Optional[InputRequest]:
        """Exit capture mode. Returns next queued request if any."""
        self._mode = False
        self._id = None
        self._type = None
        self._default = ""

        # Check for queued requests
        try:
            return self._queue.get_nowait()
        except Empty:
            return None

    def handle_captured_input(self, user_input: str) -> None:
        """Process input and provide result to bridge.

        Args:
            user_input: The user's input string
        """
        if self._type == "confirm":
            result = user_input.lower() in ('y', 'yes', '1', 'true')
        else:
            result = user_input if user_input else self._default

        self._bridge.provide_result(self._id, result)

    def cancel(self) -> None:
        """Cancel current capture (escape/ctrl+c)."""
        if self._type == "confirm":
            result = False
        else:
            result = self._default

        self._bridge.provide_result(self._id, result)
