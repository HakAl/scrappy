"""
Tests for ThreadSafeEventQueue.

Tests thread safety, event handling, and the handler registration pattern.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

import pytest

from scrappy.infrastructure.threading import (
    ThreadSafeEventQueue,
    BackgroundEvent,
    EventType,
)


class TestThreadSafeEventQueue:
    """Tests for ThreadSafeEventQueue."""

    def test_put_and_get_event(self):
        """Events can be put and retrieved."""
        queue = ThreadSafeEventQueue()
        event = BackgroundEvent(
            event_type=EventType.INIT_COMPLETE,
            source="test",
            data="test_data",
        )

        queue.put(event)
        retrieved = queue.get(timeout=1.0)

        assert retrieved is not None
        assert retrieved.event_type == EventType.INIT_COMPLETE
        assert retrieved.source == "test"
        assert retrieved.data == "test_data"

    def test_get_nowait_returns_none_when_empty(self):
        """get_nowait returns None when queue is empty."""
        queue = ThreadSafeEventQueue()

        result = queue.get_nowait()

        assert result is None

    def test_get_timeout_returns_none(self):
        """get returns None when timeout expires."""
        queue = ThreadSafeEventQueue()

        start = time.time()
        result = queue.get(timeout=0.1)
        elapsed = time.time() - start

        assert result is None
        assert elapsed >= 0.1
        assert elapsed < 0.5  # Should not wait too long

    def test_register_handler_and_process_pending(self):
        """Registered handlers are called by process_pending."""
        queue = ThreadSafeEventQueue()
        received_events: List[BackgroundEvent] = []

        def handler(event: BackgroundEvent):
            received_events.append(event)

        queue.register_handler("test", handler)

        event1 = BackgroundEvent(EventType.INIT_COMPLETE, "test", data=1)
        event2 = BackgroundEvent(EventType.INIT_COMPLETE, "test", data=2)
        queue.put(event1)
        queue.put(event2)

        count = queue.process_pending()

        assert count == 2
        assert len(received_events) == 2
        assert received_events[0].data == 1
        assert received_events[1].data == 2

    def test_unregistered_source_logs_warning(self):
        """Events from unregistered sources are handled gracefully."""
        queue = ThreadSafeEventQueue()
        event = BackgroundEvent(EventType.INIT_COMPLETE, "unknown_source")

        queue.put(event)
        count = queue.process_pending()

        # Should not crash, just log warning and continue
        assert count == 1

    def test_unregister_handler(self):
        """Handlers can be unregistered."""
        queue = ThreadSafeEventQueue()
        received_events: List[BackgroundEvent] = []

        def handler(event: BackgroundEvent):
            received_events.append(event)

        queue.register_handler("test", handler)
        queue.unregister_handler("test")

        event = BackgroundEvent(EventType.INIT_COMPLETE, "test")
        queue.put(event)
        queue.process_pending()

        # Handler was unregistered, should not receive event
        assert len(received_events) == 0

    def test_multiple_sources_with_different_handlers(self):
        """Different sources can have different handlers."""
        queue = ThreadSafeEventQueue()
        source_a_events: List[BackgroundEvent] = []
        source_b_events: List[BackgroundEvent] = []

        queue.register_handler("source_a", lambda e: source_a_events.append(e))
        queue.register_handler("source_b", lambda e: source_b_events.append(e))

        queue.put(BackgroundEvent(EventType.INIT_COMPLETE, "source_a", data="A"))
        queue.put(BackgroundEvent(EventType.INIT_FAILED, "source_b", error=ValueError()))
        queue.put(BackgroundEvent(EventType.PROGRESS, "source_a", data="A2"))

        queue.process_pending()

        assert len(source_a_events) == 2
        assert len(source_b_events) == 1
        assert source_a_events[0].data == "A"
        assert source_a_events[1].data == "A2"
        assert source_b_events[0].event_type == EventType.INIT_FAILED

    def test_pending_count(self):
        """pending_count returns approximate queue size."""
        queue = ThreadSafeEventQueue()

        assert queue.pending_count() == 0

        queue.put(BackgroundEvent(EventType.INIT_COMPLETE, "test"))
        queue.put(BackgroundEvent(EventType.INIT_COMPLETE, "test"))

        assert queue.pending_count() == 2

        queue.get_nowait()

        assert queue.pending_count() == 1

    def test_clear(self):
        """clear removes all pending events."""
        queue = ThreadSafeEventQueue()

        queue.put(BackgroundEvent(EventType.INIT_COMPLETE, "test"))
        queue.put(BackgroundEvent(EventType.INIT_COMPLETE, "test"))
        queue.put(BackgroundEvent(EventType.INIT_COMPLETE, "test"))

        cleared = queue.clear()

        assert cleared == 3
        assert queue.pending_count() == 0
        assert queue.get_nowait() is None

    def test_handler_exception_does_not_break_processing(self):
        """Exceptions in handlers don't prevent processing other events."""
        queue = ThreadSafeEventQueue()
        processed: List[str] = []

        def bad_handler(event: BackgroundEvent):
            raise ValueError("Intentional error")

        def good_handler(event: BackgroundEvent):
            processed.append(event.data)

        queue.register_handler("bad", bad_handler)
        queue.register_handler("good", good_handler)

        queue.put(BackgroundEvent(EventType.INIT_COMPLETE, "bad", data="will_fail"))
        queue.put(BackgroundEvent(EventType.INIT_COMPLETE, "good", data="will_succeed"))

        count = queue.process_pending()

        # Both events should be processed even if one handler fails
        assert count == 2
        assert processed == ["will_succeed"]


class TestThreadSafeEventQueueConcurrency:
    """Tests for thread safety of ThreadSafeEventQueue."""

    def test_concurrent_put_from_multiple_threads(self):
        """Multiple threads can put events concurrently without corruption."""
        queue = ThreadSafeEventQueue()
        num_threads = 10
        events_per_thread = 100

        def put_events(thread_id: int):
            for i in range(events_per_thread):
                queue.put(
                    BackgroundEvent(
                        EventType.PROGRESS,
                        f"thread_{thread_id}",
                        data=f"{thread_id}_{i}",
                    )
                )

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=put_events, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have exactly num_threads * events_per_thread events
        assert queue.pending_count() == num_threads * events_per_thread

        # Verify no corruption - all events should be retrievable
        retrieved = 0
        while queue.get_nowait() is not None:
            retrieved += 1

        assert retrieved == num_threads * events_per_thread

    def test_concurrent_put_and_process(self):
        """One thread puts events while another processes them."""
        queue = ThreadSafeEventQueue()
        processed: List[str] = []
        lock = threading.Lock()

        def handler(event: BackgroundEvent):
            with lock:
                processed.append(event.data)

        queue.register_handler("test", handler)

        num_events = 100
        producer_done = threading.Event()

        def producer():
            for i in range(num_events):
                queue.put(BackgroundEvent(EventType.PROGRESS, "test", data=str(i)))
                time.sleep(0.001)  # Small delay to allow interleaving
            producer_done.set()

        def consumer():
            while not producer_done.is_set() or queue.pending_count() > 0:
                queue.process_pending()
                time.sleep(0.001)
            # Final drain
            queue.process_pending()

        producer_thread = threading.Thread(target=producer)
        consumer_thread = threading.Thread(target=consumer)

        producer_thread.start()
        consumer_thread.start()

        producer_thread.join(timeout=5.0)
        consumer_thread.join(timeout=5.0)

        # All events should be processed
        assert len(processed) == num_events

    def test_high_volume_stress(self):
        """High volume test with ThreadPoolExecutor."""
        queue = ThreadSafeEventQueue()
        num_producers = 20
        events_per_producer = 500

        def produce(producer_id: int):
            for i in range(events_per_producer):
                queue.put(
                    BackgroundEvent(
                        EventType.PROGRESS,
                        f"producer_{producer_id}",
                        data=f"{producer_id}_{i}",
                    )
                )

        with ThreadPoolExecutor(max_workers=num_producers) as executor:
            futures = [
                executor.submit(produce, i) for i in range(num_producers)
            ]
            for future in futures:
                future.result()  # Wait for all to complete

        expected_count = num_producers * events_per_producer
        assert queue.pending_count() == expected_count

        # Drain and verify
        count = 0
        while queue.get_nowait() is not None:
            count += 1

        assert count == expected_count


class TestBackgroundEvent:
    """Tests for BackgroundEvent dataclass."""

    def test_create_complete_event(self):
        """Can create INIT_COMPLETE event with data."""
        event = BackgroundEvent(
            event_type=EventType.INIT_COMPLETE,
            source="semantic_search",
            data={"provider": "test"},
        )

        assert event.event_type == EventType.INIT_COMPLETE
        assert event.source == "semantic_search"
        assert event.data == {"provider": "test"}
        assert event.error is None

    def test_create_failed_event(self):
        """Can create INIT_FAILED event with error."""
        error = ValueError("Test error")
        event = BackgroundEvent(
            event_type=EventType.INIT_FAILED,
            source="semantic_search",
            error=error,
        )

        assert event.event_type == EventType.INIT_FAILED
        assert event.source == "semantic_search"
        assert event.data is None
        assert event.error is error

    def test_create_progress_event(self):
        """Can create PROGRESS event."""
        event = BackgroundEvent(
            event_type=EventType.PROGRESS,
            source="indexer",
            data={"progress": 50, "total": 100},
        )

        assert event.event_type == EventType.PROGRESS
        assert event.data["progress"] == 50


class TestEventType:
    """Tests for EventType enum."""

    def test_event_types_have_string_values(self):
        """EventType enum values are strings."""
        assert EventType.INIT_COMPLETE.value == "init_complete"
        assert EventType.INIT_FAILED.value == "init_failed"
        assert EventType.PROGRESS.value == "progress"

    def test_all_event_types_defined(self):
        """All expected event types are defined."""
        types = list(EventType)
        assert len(types) == 3
        assert EventType.INIT_COMPLETE in types
        assert EventType.INIT_FAILED in types
        assert EventType.PROGRESS in types
