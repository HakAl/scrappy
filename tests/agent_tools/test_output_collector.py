"""
Tests for ThreadSafeOutputCollector.

These tests verify thread-safety and correct behavior of the output
collector used in subprocess execution.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from scrappy.agent_tools.components.output_collector import ThreadSafeOutputCollector


class TestThreadSafeOutputCollector:
    """Tests for ThreadSafeOutputCollector thread-safety and behavior."""

    def test_append_and_get_lines(self):
        """Basic append and retrieval works correctly."""
        collector = ThreadSafeOutputCollector()

        collector.append("line 1")
        collector.append("line 2")
        collector.append("line 3")

        lines = collector.get_lines()
        assert lines == ["line 1", "line 2", "line 3"]

    def test_get_lines_returns_copy(self):
        """get_lines returns a copy, not a reference."""
        collector = ThreadSafeOutputCollector()
        collector.append("original")

        lines = collector.get_lines()
        lines.append("modified")

        # Original should be unchanged
        assert collector.get_lines() == ["original"]

    def test_line_count_accurate(self):
        """line_count returns correct count."""
        collector = ThreadSafeOutputCollector()

        assert collector.line_count() == 0

        collector.append("one")
        assert collector.line_count() == 1

        collector.append("two")
        collector.append("three")
        assert collector.line_count() == 3

    def test_last_output_time_updated_on_append(self):
        """last_output_time is updated on each append."""
        collector = ThreadSafeOutputCollector()

        initial_time = collector.get_last_output_time()
        time.sleep(0.01)  # Small delay to ensure time difference

        collector.append("line")
        updated_time = collector.get_last_output_time()

        assert updated_time > initial_time

    def test_last_output_time_initialized(self):
        """last_output_time is initialized to current time on creation."""
        before = time.time()
        collector = ThreadSafeOutputCollector()
        after = time.time()

        last_time = collector.get_last_output_time()
        assert before <= last_time <= after

    def test_concurrent_append_is_thread_safe(self):
        """Multiple threads appending should not cause data corruption."""
        collector = ThreadSafeOutputCollector()
        num_threads = 10
        lines_per_thread = 100

        def append_lines(thread_id: int):
            for i in range(lines_per_thread):
                collector.append(f"thread{thread_id}-line{i}")

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=append_lines, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have exactly num_threads * lines_per_thread lines
        expected_count = num_threads * lines_per_thread
        assert collector.line_count() == expected_count

        # All lines should be unique (no corruption)
        lines = collector.get_lines()
        assert len(set(lines)) == expected_count

    def test_concurrent_read_write(self):
        """Concurrent reading and writing should not cause errors."""
        collector = ThreadSafeOutputCollector()
        stop_event = threading.Event()
        errors = []

        def writer():
            for i in range(100):
                collector.append(f"line-{i}")
                time.sleep(0.001)

        def reader():
            while not stop_event.is_set():
                try:
                    _ = collector.get_lines()
                    _ = collector.line_count()
                    _ = collector.get_last_output_time()
                except Exception as e:
                    errors.append(e)
                time.sleep(0.001)

        writer_thread = threading.Thread(target=writer)
        reader_threads = [threading.Thread(target=reader) for _ in range(3)]

        for rt in reader_threads:
            rt.start()
        writer_thread.start()

        writer_thread.join()
        stop_event.set()
        for rt in reader_threads:
            rt.join()

        assert len(errors) == 0, f"Errors during concurrent access: {errors}"
        assert collector.line_count() == 100

    def test_empty_collector(self):
        """Empty collector behaves correctly."""
        collector = ThreadSafeOutputCollector()

        assert collector.get_lines() == []
        assert collector.line_count() == 0
        assert collector.get_last_output_time() > 0

    def test_empty_string_append(self):
        """Empty strings can be appended."""
        collector = ThreadSafeOutputCollector()

        collector.append("")
        collector.append("non-empty")
        collector.append("")

        assert collector.get_lines() == ["", "non-empty", ""]
        assert collector.line_count() == 3

    def test_special_characters(self):
        """Lines with special characters are handled correctly."""
        collector = ThreadSafeOutputCollector()

        special_lines = [
            "line with\ttab",
            "line with\nnewline",
            "unicode: \u2603",
            "null char: \x00",
            "backslash: \\path\\to\\file",
        ]

        for line in special_lines:
            collector.append(line)

        assert collector.get_lines() == special_lines

    def test_high_volume_stress(self):
        """Handles high volume of appends under stress."""
        collector = ThreadSafeOutputCollector()
        num_lines = 10000

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(collector.append, f"line-{i}")
                for i in range(num_lines)
            ]
            for f in futures:
                f.result()

        assert collector.line_count() == num_lines
