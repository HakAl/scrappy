"""
Managed thread with proper lifecycle management.

Provides threads that support graceful shutdown instead of being killed
abruptly like daemon threads.
"""

import logging
import threading
from typing import Optional, Callable, TypeVar, Generic

logger = logging.getLogger(__name__)


# Type variable for the result type
T = TypeVar("T")


class ManagedThread(Generic[T]):
    """
    Thread with proper lifecycle management and graceful shutdown.

    Unlike daemon threads which are killed abruptly when the process exits,
    ManagedThread supports graceful shutdown where the worker function can
    check for shutdown requests and clean up properly.

    The worker function receives the ManagedThread instance and should
    periodically check the shutdown_requested property to know when to exit.

    Example:
        def worker(thread: ManagedThread) -> None:
            while not thread.shutdown_requested:
                # Do some work
                time.sleep(0.1)
            # Clean up resources
            print("Worker shutting down cleanly")

        managed = ManagedThread(target=worker, name="MyWorker")
        managed.start()

        # Later, request graceful shutdown
        if managed.stop(timeout=5.0):
            print("Thread stopped cleanly")
        else:
            print("Thread did not stop within timeout")

    Attributes:
        shutdown_requested: Property to check if shutdown was requested
    """

    def __init__(
        self,
        target: Callable[["ManagedThread[T]"], Optional[T]],
        name: Optional[str] = None,
    ):
        """
        Initialize managed thread.

        Args:
            target: Function to run in thread. Receives this ManagedThread
                   instance so it can check shutdown_requested. May return
                   a result value.
            name: Thread name for debugging
        """
        self._target = target
        self._name = name
        self._thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._started = False
        self._result: Optional[T] = None
        self._error: Optional[Exception] = None
        self._lock = threading.Lock()

    @property
    def shutdown_requested(self) -> bool:
        """
        Check if shutdown has been requested.

        Worker functions should poll this property periodically and exit
        cleanly when it returns True.

        Returns:
            True if shutdown was requested via stop()
        """
        return self._shutdown_event.is_set()

    def start(self) -> None:
        """
        Start the thread.

        Does nothing if thread is already started.
        """
        with self._lock:
            if self._started:
                logger.debug(f"Thread {self._name} already started")
                return

            self._thread = threading.Thread(
                target=self._run,
                name=self._name,
                daemon=False,  # NOT a daemon - we manage lifecycle explicitly
            )
            self._thread.start()
            self._started = True
            logger.debug(f"Started managed thread: {self._name}")

    def _run(self) -> None:
        """Internal wrapper that passes self to target and captures result/error."""
        try:
            self._result = self._target(self)
        except Exception as e:
            logger.warning(f"Thread {self._name} raised exception: {e}")
            self._error = e

    def stop(self, timeout: float = 5.0) -> bool:
        """
        Request thread stop and wait for completion.

        Sets the shutdown flag and waits for the thread to exit.
        The worker function should check shutdown_requested periodically
        and exit cleanly.

        Args:
            timeout: Maximum seconds to wait for thread to stop

        Returns:
            True if thread stopped within timeout, False if still running
        """
        with self._lock:
            if not self._started or self._thread is None:
                return True

        logger.debug(f"Requesting shutdown for thread: {self._name}")
        self._shutdown_event.set()
        self._thread.join(timeout=timeout)

        is_alive = self._thread.is_alive()
        if is_alive:
            logger.warning(
                f"Thread {self._name} did not stop within {timeout}s timeout"
            )
        else:
            logger.debug(f"Thread {self._name} stopped cleanly")

        return not is_alive

    def is_running(self) -> bool:
        """
        Check if thread is currently running.

        Returns:
            True if thread is alive and running
        """
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def join(self, timeout: Optional[float] = None) -> None:
        """
        Wait for thread to complete.

        Args:
            timeout: Maximum seconds to wait (None = wait forever)
        """
        if self._thread:
            self._thread.join(timeout=timeout)

    def get_result(self) -> Optional[T]:
        """
        Get the result returned by the worker function.

        Returns:
            Result from worker function, or None if not complete or no result
        """
        return self._result

    def get_error(self) -> Optional[Exception]:
        """
        Get any exception raised by the worker function.

        Returns:
            Exception if worker raised one, None otherwise
        """
        return self._error

    def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for shutdown to be requested.

        Useful for worker functions that want to block until shutdown.

        Args:
            timeout: Maximum seconds to wait (None = wait forever)

        Returns:
            True if shutdown was requested, False if timed out
        """
        return self._shutdown_event.wait(timeout=timeout)
