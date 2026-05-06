"""Protocol and Textual implementation for ordered TUI events."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Protocol

from .tui_events import FlushRequested, TuiEvent, TuiEventMessage


class TuiEventSinkProtocol(Protocol):
    """Thread-safe sink for typed TUI events."""

    def post_event(self, event: TuiEvent) -> None:
        """Post an event into the UI event sequence."""
        ...

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait until all previously posted events have been handled."""
        ...


class TextualMessagePosterProtocol(Protocol):
    """Minimal Textual app surface required by the event sink."""

    def post_message(self, message: TuiEventMessage) -> Any:
        """Post a Textual message."""
        ...


class TextualTuiEventSink(TuiEventSinkProtocol):
    """TUI event sink backed by Textual's message sequence."""

    def __init__(self, app: TextualMessagePosterProtocol) -> None:
        self._app = app
        self._flush_events: dict[str, threading.Event] = {}
        self._flush_lock = threading.Lock()
        self._shutdown_requested = False

    def post_event(self, event: TuiEvent) -> None:
        """Post an event as one Textual boundary message."""
        if self._shutdown_requested and not isinstance(event, FlushRequested):
            return
        self._app.post_message(TuiEventMessage(event))

    def flush(self, timeout: float = 5.0) -> bool:
        """Post a flush event and wait for the main loop acknowledgement."""
        if self._shutdown_requested:
            return False

        flush_id = str(uuid.uuid4())
        event = threading.Event()
        deadline = time.monotonic() + timeout

        with self._flush_lock:
            self._flush_events[flush_id] = event

        try:
            self.post_event(
                FlushRequested(flush_id=flush_id)
            )

            while True:
                if self._shutdown_requested:
                    return False

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False

                if event.wait(timeout=min(0.05, remaining)):
                    return not self._shutdown_requested
        finally:
            with self._flush_lock:
                self._flush_events.pop(flush_id, None)

    def acknowledge_flush(self, flush_id: str) -> None:
        """Acknowledge a processed flush event."""
        with self._flush_lock:
            event = self._flush_events.get(flush_id)
            if event is not None:
                event.set()

    def request_shutdown(self) -> None:
        """Unblock pending flush calls and stop accepting normal events."""
        self._shutdown_requested = True
        with self._flush_lock:
            for event in self._flush_events.values():
                event.set()

    def is_shutdown_requested(self) -> bool:
        """Return whether shutdown has been requested."""
        return self._shutdown_requested
