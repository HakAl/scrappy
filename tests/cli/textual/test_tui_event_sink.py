"""Tests for typed TUI event sink foundation."""

from __future__ import annotations

import threading
import time

from scrappy.cli.protocols import ActivityState
from scrappy.cli.textual.event_sink import TextualTuiEventSink
from scrappy.cli.textual.output_adapter import TextualOutputAdapter
from scrappy.cli.textual.tui_events import (
    ActivityChanged,
    FlushRequested,
    TasksUpdated,
    TranscriptAppend,
    TuiEventMessage,
    tui_event_from_legacy_output_message,
)


class RecordingApp:
    """Minimal app double that records posted Textual messages."""

    def __init__(self) -> None:
        self.messages: list[TuiEventMessage] = []

    def post_message(self, message: TuiEventMessage) -> None:
        self.messages.append(message)


def wait_for(predicate, timeout: float = 1.0) -> None:
    """Wait until predicate returns true."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached before timeout")


def test_sink_posts_typed_events_as_single_textual_message_type() -> None:
    """Typed sink posts events through one boundary message type."""
    app = RecordingApp()
    sink = TextualTuiEventSink(app)

    sink.post_event(TranscriptAppend(content="hello"))

    assert len(app.messages) == 1
    assert isinstance(app.messages[0], TuiEventMessage)
    assert app.messages[0].event == TranscriptAppend(content="hello")


def test_flush_event_observes_prior_events_in_same_sink_sequence() -> None:
    """Flush is posted after earlier events and waits for acknowledgement."""
    app = RecordingApp()
    sink = TextualTuiEventSink(app)
    result: list[bool] = []

    sink.post_event(TranscriptAppend(content="before flush"))

    flush_thread = threading.Thread(
        target=lambda: result.append(sink.flush(timeout=2.0))
    )
    flush_thread.start()

    wait_for(lambda: len(app.messages) == 2)

    first_event = app.messages[0].event
    second_event = app.messages[1].event

    assert isinstance(first_event, TranscriptAppend)
    assert isinstance(second_event, FlushRequested)

    second_event.acknowledge(second_event.flush_id)
    flush_thread.join(timeout=1.0)

    assert not flush_thread.is_alive()
    assert result == [True]


def test_sink_shutdown_unblocks_pending_flush() -> None:
    """Sink flush returns false promptly when shutdown is requested."""
    app = RecordingApp()
    sink = TextualTuiEventSink(app)
    result: list[bool] = []

    flush_thread = threading.Thread(
        target=lambda: result.append(sink.flush(timeout=30.0))
    )
    flush_thread.start()

    wait_for(lambda: len(app.messages) == 1)
    sink.request_shutdown()
    flush_thread.join(timeout=1.0)

    assert not flush_thread.is_alive()
    assert result == [False]


def test_output_adapter_shutdown_unblocks_pending_flush() -> None:
    """Legacy adapter flush cannot wait for timeout after shutdown."""
    adapter = TextualOutputAdapter()
    result: list[bool] = []

    flush_thread = threading.Thread(
        target=lambda: result.append(adapter.flush(timeout=30.0))
    )
    flush_thread.start()

    queued_message = adapter.get_message(block=True, timeout=1.0)
    assert queued_message is not None
    assert queued_message[0] == "flush"

    adapter.request_shutdown()
    flush_thread.join(timeout=1.0)

    assert not flush_thread.is_alive()
    assert result == [False]


def test_legacy_tuple_adapter_messages_convert_to_typed_events() -> None:
    """Tuple adapter messages enter the typed event model."""
    acknowledgements: list[str] = []

    output_event = tui_event_from_legacy_output_message(
        ("output", "hello"),
        acknowledge_flush=acknowledgements.append,
    )
    renderable = object()
    renderable_event = tui_event_from_legacy_output_message(
        ("renderable", renderable),
        acknowledge_flush=acknowledgements.append,
    )
    tasks_event = tui_event_from_legacy_output_message(
        ("tasks", [{"description": "test"}]),
        acknowledge_flush=acknowledgements.append,
    )
    activity_event = tui_event_from_legacy_output_message(
        ("activity", (ActivityState.THINKING, "working", 42)),
        acknowledge_flush=acknowledgements.append,
    )
    flush_event = tui_event_from_legacy_output_message(
        ("flush", "flush-id"),
        acknowledge_flush=acknowledgements.append,
    )

    assert output_event == TranscriptAppend(content="hello")
    assert renderable_event == TranscriptAppend(renderable=renderable)
    assert tasks_event == TasksUpdated([{"description": "test"}])
    assert activity_event == ActivityChanged(
        state=ActivityState.THINKING,
        message="working",
        elapsed_ms=42,
    )
    assert isinstance(flush_event, FlushRequested)

    flush_event.acknowledge(flush_event.flush_id)
    assert acknowledgements == ["flush-id"]
