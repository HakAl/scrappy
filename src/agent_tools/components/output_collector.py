"""
Thread-safe output collector for subprocess output.

This module provides a synchronized container for collecting output lines
from subprocess streams, ensuring data integrity when accessed from multiple
threads concurrently.
"""

import threading
import time
from typing import List


class ThreadSafeOutputCollector:
    """Thread-safe collector for subprocess output.

    Provides synchronized access to output lines collected from subprocess
    streams. Uses a lock to ensure thread-safety when appending from a reader
    thread while the main thread monitors progress.

    Example:
        collector = ThreadSafeOutputCollector()

        def reader():
            for line in process.stdout:
                collector.append(line.rstrip())

        thread = Thread(target=reader)
        thread.start()

        # Main thread can safely check progress
        while process.poll() is None:
            stall_time = time.time() - collector.get_last_output_time()
            if stall_time > 30:
                print("No output for 30s")
            time.sleep(0.5)

        stdout = "\\n".join(collector.get_lines())
    """

    def __init__(self) -> None:
        """Initialize the collector with empty state."""
        self._lines: List[str] = []
        self._last_output_time: float = time.time()
        self._lock = threading.Lock()

    def append(self, line: str) -> None:
        """Thread-safe append of output line.

        Updates both the lines list and the last output timestamp
        atomically within a lock.

        Args:
            line: Output line to append
        """
        with self._lock:
            self._lines.append(line)
            self._last_output_time = time.time()

    def get_lines(self) -> List[str]:
        """Get copy of all collected lines.

        Returns a copy to prevent external modification and ensure
        the caller has a consistent snapshot.

        Returns:
            Copy of the lines list (not a reference)
        """
        with self._lock:
            return list(self._lines)

    def get_last_output_time(self) -> float:
        """Get timestamp of last output.

        Returns:
            Unix timestamp of last append operation
        """
        with self._lock:
            return self._last_output_time

    def line_count(self) -> int:
        """Get current line count.

        Returns:
            Number of lines collected
        """
        with self._lock:
            return len(self._lines)
