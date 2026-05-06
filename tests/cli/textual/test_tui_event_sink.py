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
    TranscriptAppendRenderable,
    TranscriptAppendText,
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

    sink.post_event(TranscriptAppendText(content="hello"))

    assert len(app.messages) == 1
    assert isinstance(app.messages[0], TuiEventMessage)
    assert app.messages[0].event == TranscriptAppendText(content="hello")


def test_flush_event_observes_prior_events_in_same_sink_sequence() -> None:
    """Flush is posted after earlier events and waits for acknowledgement."""
    app = RecordingApp()
    sink = TextualTuiEventSink(app)
    result: list[bool] = []

    sink.post_event(TranscriptAppendText(content="before flush"))

    flush_thread = threading.Thread(
        target=lambda: result.append(sink.flush(timeout=2.0))
    )
    flush_thread.start()

    wait_for(lambda: len(app.messages) == 2)

    first_event = app.messages[0].event
    second_event = app.messages[1].event

    assert isinstance(first_event, TranscriptAppendText)
    assert isinstance(second_event, FlushRequested)

    sink.acknowledge_flush(second_event.flush_id)
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
    """Output adapter flush cannot wait for timeout after shutdown."""
    app = RecordingApp()
    sink = TextualTuiEventSink(app)
    adapter = TextualOutputAdapter(sink)
    result: list[bool] = []

    flush_thread = threading.Thread(
        target=lambda: result.append(adapter.flush(timeout=30.0))
    )
    flush_thread.start()

    wait_for(lambda: len(app.messages) == 1)
    assert isinstance(app.messages[0].event, FlushRequested)

    adapter.request_shutdown()
    flush_thread.join(timeout=1.0)

    assert not flush_thread.is_alive()
    assert result == [False]


def test_legacy_tuple_adapter_messages_convert_to_typed_events() -> None:
    """Tuple adapter messages enter the typed event model."""
    output_event = tui_event_from_legacy_output_message(
        ("output", "hello"),
    )
    renderable = object()
    renderable_event = tui_event_from_legacy_output_message(
        ("renderable", renderable),
    )
    tasks_event = tui_event_from_legacy_output_message(
        ("tasks", [{"description": "test"}]),
    )
    activity_event = tui_event_from_legacy_output_message(
        ("activity", (ActivityState.THINKING, "working", 42)),
    )
    flush_event = tui_event_from_legacy_output_message(
        ("flush", "flush-id"),
    )

    assert output_event == TranscriptAppendText(content="hello")
    assert renderable_event == TranscriptAppendRenderable(renderable=renderable)
    assert tasks_event == TasksUpdated([{"description": "test"}])
    assert activity_event == ActivityChanged(
        state=ActivityState.THINKING,
        message="working",
        elapsed_ms=42,
    )
    assert isinstance(flush_event, FlushRequested)


def test_unknown_legacy_tuple_tag_logs_warning(caplog) -> None:
    """Unknown tuple tags are visible instead of being silently dropped."""
    with caplog.at_level("WARNING", logger="scrappy.cli.textual.tui_events"):
        event = tui_event_from_legacy_output_message(("unknown-tag", object()))

    assert event is None
    assert "unknown-tag" in caplog.text


def test_output_adapter_event_order_matches_direct_typed_sink_order() -> None:
    """Adapter output cannot render after a later typed sink event."""
    app = RecordingApp()
    sink = TextualTuiEventSink(app)
    adapter = TextualOutputAdapter(sink)

    adapter.post_output("from adapter")
    sink.post_event(TranscriptAppendText(content="direct typed"))

    assert [message.event for message in app.messages] == [
        TranscriptAppendText(content="from adapter"),
        TranscriptAppendText(content="direct typed"),
    ]
