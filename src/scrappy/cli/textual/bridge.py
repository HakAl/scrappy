"""
Thread-safe async bridge for worker thread to main thread communication.

This module provides ThreadSafeAsyncBridge which allows worker threads
to block while waiting for async results from the main Textual event loop.
"""

from typing import TYPE_CHECKING, Any, Dict
import logging
import threading
import uuid

if TYPE_CHECKING:
    from .app import ScrappyApp

from .messages import RequestInlineInput

logger = logging.getLogger(__name__)


class ThreadSafeAsyncBridge:
    """Allows worker thread to block while waiting for async result from main thread.

    This bridge solves the threading problem where InteractiveMode._process_input()
    runs in a worker thread (via @work decorator) but needs to show modal dialogs
    that run on the main thread's event loop.
    """

    def __init__(self, app: "ScrappyApp") -> None:
        self.app = app
        self._pending_prompts: Dict[str, threading.Event] = {}
        self._prompt_results: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._shutting_down = False

    def shutdown(self) -> None:
        """Signal all pending prompts to unblock - call when app is closing."""
        self._shutting_down = True
        with self._lock:
            for event in self._pending_prompts.values():
                event.set()

    def blocking_prompt(self, message: str, default: str = "") -> str:
        """Called from worker thread - blocks until main thread provides result."""
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "CRITICAL ERROR: blocking_prompt() called from Main Thread! "
                "This will cause a deadlock."
            )

        if self._shutting_down:
            return default

        prompt_id = str(uuid.uuid4())

        with self._lock:
            event = threading.Event()
            self._pending_prompts[prompt_id] = event

        self.app.post_message(RequestInlineInput(prompt_id, message, "prompt", default))

        # Wait with timeout to allow for shutdown
        while not event.wait(timeout=0.5):
            if self._shutting_down:
                return default

        with self._lock:
            result = self._prompt_results.pop(prompt_id, default)
            self._pending_prompts.pop(prompt_id, None)

        return result

    def blocking_confirm(self, question: str) -> bool:
        """Called from worker thread - blocks until main thread provides result."""
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "CRITICAL ERROR: blocking_confirm() called from Main Thread! "
                "This will cause a deadlock."
            )

        if self._shutting_down:
            return False

        prompt_id = str(uuid.uuid4())

        with self._lock:
            event = threading.Event()
            self._pending_prompts[prompt_id] = event

        self.app.post_message(RequestInlineInput(prompt_id, question, "confirm"))

        # Wait with timeout to allow for shutdown
        while not event.wait(timeout=0.5):
            if self._shutting_down:
                return False

        with self._lock:
            result = self._prompt_results.pop(prompt_id, False)
            self._pending_prompts.pop(prompt_id, None)

        return result

    def blocking_confirm_yna(self, question: str) -> str:
        """Called from worker thread - blocks until user responds y/n/a.

        Returns:
            "y" - yes, allow this operation
            "n" - no, deny this operation
            "a" - allow all remaining operations this run
        """
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "CRITICAL ERROR: blocking_confirm_yna() called from Main Thread! "
                "This will cause a deadlock."
            )

        if self._shutting_down:
            return "n"

        prompt_id = str(uuid.uuid4())

        with self._lock:
            event = threading.Event()
            self._pending_prompts[prompt_id] = event

        self.app.post_message(RequestInlineInput(prompt_id, question, "confirm_yna"))

        # Wait with timeout to allow for shutdown
        while not event.wait(timeout=0.5):
            if self._shutting_down:
                return "n"

        with self._lock:
            result = self._prompt_results.pop(prompt_id, "n")
            self._pending_prompts.pop(prompt_id, None)

        # Normalize to y/n/a
        if result in ("y", "n", "a"):
            return result
        return "n"

    def blocking_checkpoint(self, message: str, default: str = "c") -> str:
        """Called from worker thread for checkpoint prompts.

        Similar to blocking_prompt but uses input_type="checkpoint" which
        displays ONLY in activity bar (not in chat log).
        """
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "CRITICAL ERROR: blocking_checkpoint() called from Main Thread! "
                "This will cause a deadlock."
            )

        if self._shutting_down:
            return default

        prompt_id = str(uuid.uuid4())

        with self._lock:
            event = threading.Event()
            self._pending_prompts[prompt_id] = event

        # Use "checkpoint" input_type to skip log output
        self.app.post_message(RequestInlineInput(prompt_id, message, "checkpoint", default))

        # Wait with timeout to allow for shutdown
        while not event.wait(timeout=0.5):
            if self._shutting_down:
                return default

        with self._lock:
            result = self._prompt_results.pop(prompt_id, default)
            self._pending_prompts.pop(prompt_id, None)

        return result

    def provide_result(self, prompt_id: str, result: Any) -> None:
        """Called from main thread after input is captured."""
        with self._lock:
            if prompt_id not in self._pending_prompts:
                logger.warning(f"provide_result: unknown prompt_id {prompt_id}, ignoring")
                return
            self._prompt_results[prompt_id] = result
            self._pending_prompts[prompt_id].set()
