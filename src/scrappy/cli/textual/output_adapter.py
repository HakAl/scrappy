"""Output adapter for routing legacy OutputSink calls to typed TUI events."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import logging
from typing import TYPE_CHECKING, Any, Generator

from .tui_events import (
    ActivityChanged,
    TasksUpdated,
    TranscriptAppendRenderable,
    TranscriptAppendText,
    TuiEvent,
    TuiEventTarget,
)

if TYPE_CHECKING:
    from ..protocols import ActivityState
    from .event_sink import TuiEventSinkProtocol

logger = logging.getLogger(__name__)


class TextualOutputAdapter:
    """Adapter that bridges OutputSink calls to the typed TUI event sink."""

    def __init__(self, event_sink: "TuiEventSinkProtocol | None" = None) -> None:
        self._event_sink = event_sink
        self._shutdown_requested = False
        self._transcript_target: ContextVar[TuiEventTarget] = ContextVar(
            "scrappy_tui_transcript_target",
            default=TuiEventTarget.MAIN_TRANSCRIPT,
        )

    def bind_event_sink(self, event_sink: "TuiEventSinkProtocol") -> None:
        """Bind the app-owned event sink exactly once."""
        if self._event_sink is not None and self._event_sink is not event_sink:
            raise RuntimeError("TextualOutputAdapter event sink is already bound")
        self._event_sink = event_sink

    def _post_event(self, event: TuiEvent) -> None:
        """Post an event if the adapter has been bound to the app sink."""
        if self._shutdown_requested:
            return
        if self._event_sink is None:
            logger.debug("Dropping TUI output before event sink is bound: %s", type(event).__name__)
            return
        self._event_sink.post_event(event)

    @contextmanager
    def transcript_target(
        self,
        target: TuiEventTarget,
    ) -> Generator[None, None, None]:
        """Temporarily route transcript output to a target surface."""
        token = self._transcript_target.set(target)
        try:
            yield
        finally:
            self._transcript_target.reset(token)

    def post_output(self, content: str) -> None:
        """Post plain text output to the current transcript target."""
        self._post_event(
            TranscriptAppendText(
                content=content,
                target=self._transcript_target.get(),
            )
        )

    def post_renderable(self, obj: Any) -> None:
        """Post a Rich renderable to the current transcript target."""
        self._post_event(
            TranscriptAppendRenderable(
                renderable=obj,
                target=self._transcript_target.get(),
            )
        )

    def post_tasks_updated(self, tasks: list[Any]) -> None:
        """Post task list update to UI."""
        self._post_event(TasksUpdated(tasks))

    def post_activity(
        self,
        state: "ActivityState",
        message: str = "",
        elapsed_ms: int = 0,
    ) -> None:
        """Post activity state change to UI."""
        self._post_event(
            ActivityChanged(state=state, message=message, elapsed_ms=elapsed_ms)
        )

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait for all previously posted typed events to be processed."""
        if self._shutdown_requested:
            return False
        if self._event_sink is None:
            return True
        return self._event_sink.flush(timeout=timeout)

    def request_shutdown(self) -> None:
        """Stop accepting output and unblock pending flush calls."""
        self._shutdown_requested = True
        request_shutdown = getattr(self._event_sink, "request_shutdown", None)
        if request_shutdown is not None:
            request_shutdown()

    def is_shutdown_requested(self) -> bool:
        """Return whether shutdown has been requested."""
        return self._shutdown_requested
