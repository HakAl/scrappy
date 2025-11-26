"""
Threading infrastructure for background task management.

Provides thread-safe event queues and managed thread lifecycle for
background-to-main-thread communication.
"""

from .protocols import (
    EventType,
    BackgroundEvent,
    EventQueueProtocol,
    MainThreadCallbackProtocol,
    ManagedThreadProtocol,
)
from .event_queue import ThreadSafeEventQueue
from .managed_thread import ManagedThread

__all__ = [
    "EventType",
    "BackgroundEvent",
    "EventQueueProtocol",
    "MainThreadCallbackProtocol",
    "ManagedThreadProtocol",
    "ThreadSafeEventQueue",
    "ManagedThread",
]
