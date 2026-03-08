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

    def _ensure_worker_thread(self, method_name: str) -> None:
        """Reject main-thread calls that would deadlock."""
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                f"CRITICAL ERROR: {method_name}() called from Main Thread! "
                "This will cause a deadlock."
            )

    def _register_prompt(self) -> tuple[str, threading.Event]:
        """Register a pending prompt and return its synchronization event."""
        prompt_id = str(uuid.uuid4())
        event = threading.Event()
        with self._lock:
            self._pending_prompts[prompt_id] = event
        return prompt_id, event

    def _await_result(self, prompt_id: str, event: threading.Event, default: Any) -> Any:
        """Wait for prompt completion or shutdown and return the resolved value."""
        while not event.wait(timeout=0.5):
            if self._shutting_down:
                return default

        with self._lock:
            result = self._prompt_results.pop(prompt_id, default)
            self._pending_prompts.pop(prompt_id, None)

        return result

    def blocking_prompt(self, message: str, default: str = "") -> str:
        """Called from worker thread - blocks until main thread provides result."""
        self._ensure_worker_thread("blocking_prompt")

        if self._shutting_down:
            return default

        prompt_id, event = self._register_prompt()

        self.app.post_message(RequestInlineInput(prompt_id, message, "prompt", default))
        return self._await_result(prompt_id, event, default)

    def blocking_confirm(self, question: str) -> bool:
        """Called from worker thread - blocks until main thread provides result."""
        self._ensure_worker_thread("blocking_confirm")

        if self._shutting_down:
            return False

        prompt_id, event = self._register_prompt()

        self.app.post_message(RequestInlineInput(prompt_id, question, "confirm"))
        return self._await_result(prompt_id, event, False)

    def blocking_confirm_yna(self, question: str) -> str:
        """Called from worker thread - blocks until user responds y/n/a.

        Returns:
            "y" - yes, allow this operation
            "n" - no, deny this operation
            "a" - allow all remaining operations this run
        """
        self._ensure_worker_thread("blocking_confirm_yna")

        if self._shutting_down:
            return "n"

        prompt_id, event = self._register_prompt()

        self.app.post_message(RequestInlineInput(prompt_id, question, "confirm_yna"))
        result = self._await_result(prompt_id, event, "n")

        # Normalize to y/n/a
        if result in ("y", "n", "a"):
            return result
        return "n"

    def blocking_checkpoint(self, message: str, default: str = "c") -> str:
        """Called from worker thread for checkpoint prompts.

        Similar to blocking_prompt but uses input_type="checkpoint" which
        displays ONLY in activity bar (not in chat log).
        """
        self._ensure_worker_thread("blocking_checkpoint")

        if self._shutting_down:
            return default

        prompt_id, event = self._register_prompt()

        # Use "checkpoint" input_type to skip log output
        self.app.post_message(RequestInlineInput(prompt_id, message, "checkpoint", default))
        return self._await_result(prompt_id, event, default)

    def provide_result(self, prompt_id: str, result: Any) -> None:
        """Called from main thread after input is captured."""
        with self._lock:
            if prompt_id not in self._pending_prompts:
                logger.warning(f"provide_result: unknown prompt_id {prompt_id}, ignoring")
                return
            self._prompt_results[prompt_id] = result
            self._pending_prompts[prompt_id].set()
