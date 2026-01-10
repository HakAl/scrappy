"""
Threading infrastructure for background task management.

Provides thread-safe event queues, managed thread lifecycle, and
cooperative cancellation for background-to-main-thread communication.
"""

from .protocols import (
    EventType,
    BackgroundEvent,
    EventQueueProtocol,
    MainThreadCallbackProtocol,
    ManagedThreadProtocol,
    CancellationTokenProtocol,
)
from .event_queue import ThreadSafeEventQueue
from .managed_thread import ManagedThread
from .cancellation import CancellationToken

__all__ = [
    "EventType",
    "BackgroundEvent",
    "EventQueueProtocol",
    "MainThreadCallbackProtocol",
    "ManagedThreadProtocol",
    "CancellationTokenProtocol",
    "ThreadSafeEventQueue",
    "ManagedThread",
    "CancellationToken",
]
